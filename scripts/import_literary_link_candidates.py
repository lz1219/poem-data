"""Store validated, explicitly provisional cross-database links in the corpus."""
import argparse
import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from validate_literary_links import validate, require


def validate_current(conn, link, data_root, lock=False):
    def load(group, key):
        require(isinstance(key,str) and key and key not in ('.','..') and '/' not in key and '\\' not in key,
                'Invalid editor key')
        return json.loads((data_root/group/(key+'.json')).read_text('utf-8'))
    p,w,j=link['person'],link['work'],link['journey']
    person=load('persons',p['editorKey']);work=load('works',w['editorKey']);journey=load('journeys',j['key'])
    corpus_person=conn.execute('SELECT id,key,zh,cbdb_id FROM public.person WHERE id=%s'+(' FOR SHARE' if lock else ''),
                               (p['corpusPersonId'],)).fetchone()
    poem=conn.execute('''SELECT p.id,p.body,o.edition_id,o.batch_id,o.metadata
        FROM public.corpus_poem p JOIN public.corpus_poem_origin o ON o.poem_id=p.id WHERE p.id=%s'''+
        (' FOR SHARE OF p,o' if lock else ''),(w['corpusPoemId'],)).fetchone()
    require(corpus_person is not None and poem is not None,'Missing corpus target or provenance')
    return validate(link,person,work,journey,corpus_person,poem)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('preview','exercise','apply'))
    parser.add_argument('--link',type=Path,required=True)
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--schema',type=Path,required=True)
    args=parser.parse_args()
    link=json.loads(args.link.read_text('utf-8'))
    p,w,j=link['person'],link['work'],link['journey']
    with psycopg.connect(os.environ['CORPUS_DSN'],autocommit=True,row_factory=dict_row) as conn:
        if args.operation=='preview':
            with conn.transaction():
                conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                result=validate_current(conn,link,args.data_root)
                present=conn.execute("SELECT to_regclass('public.corpus_editor_person_candidate') IS NOT NULL AS ok").fetchone()['ok']
            print(json.dumps({'operation':'preview','tableExists':present,**result},ensure_ascii=False));return
        try:
            with conn.transaction():
                conn.execute("SET LOCAL lock_timeout='3s'")
                conn.execute("SET LOCAL statement_timeout='8s'")
                require(conn.execute('SELECT pg_try_advisory_xact_lock(730017,1) AS ok').fetchone()['ok'],
                        'Another candidate import is running')
                result=validate_current(conn,link,args.data_root,lock=True)
                conn.execute(args.schema.read_text('utf-8'))
                records=[
                    ('corpus_editor_person_candidate',('editor_person_key','person_id','editor_sha256','metadata'),
                     (p['editorKey'],p['corpusPersonId'],p['editorSha256'],p)),
                    ('corpus_editor_work_poem_candidate',('editor_work_key','poem_id','editor_sha256','poem_sha256','metadata'),
                     (w['editorKey'],w['corpusPoemId'],w['editorSha256'],w['corpusBodySha256'],w)),
                    ('corpus_editor_stop_work_candidate',('journey_key','stop_seq','editor_work_key','stop_sha256','relation','metadata'),
                     (j['key'],j['stopSeq'],w['editorKey'],j['stopSha256'],j['relation'],j)),
                ]
                for table,columns,values in records:
                    # Identifiers are constants above; all content uses parameters.
                    wrapped=tuple(Jsonb(v) if isinstance(v,dict) else v for v in values)
                    inserted=conn.execute('INSERT INTO public.'+table+' ('+','.join(columns)+') VALUES ('+
                        ','.join(['%s']*len(columns))+') ON CONFLICT DO NOTHING RETURNING 1',wrapped).fetchone()
                    if not inserted:
                        predicates=' AND '.join(col+'=%s' for col in columns[:-1])
                        existing=conn.execute('SELECT metadata FROM public.'+table+' WHERE '+predicates,values[:-1]).fetchone()
                        require(existing and existing['metadata']==values[-1], 'Existing candidate differs; refusing overwrite')
                if args.operation=='exercise':raise _RollbackExercise()
        except _RollbackExercise:
            print(json.dumps({'operation':'exercise-rolled-back',**result},ensure_ascii=False));return
        print(json.dumps({'operation':'applied-or-already-present',**result},ensure_ascii=False))


class _RollbackExercise(Exception):
    pass


if __name__=='__main__':
    main()
