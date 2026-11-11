"""Preview or append validated explanation revisions to the existing corpus database."""
import argparse
import hashlib
import json
import os
from pathlib import Path

from paragraph_explanations import validate, require


def prepare(conn, bundle, inventory):
    validation = validate(bundle, inventory)
    unit = conn.execute('''SELECT t.sha256,o.edition_id,o.metadata->>'revisionId'
        FROM public.text_unit t JOIN public.corpus_unit_origin o ON o.unit_id=t.id
        WHERE t.id=%s''', (bundle['unitId'],)).fetchone()
    require(unit and unit[0] == bundle['unitSha256'] and unit[1] == inventory['editionId']
            and str(unit[2]) == str(bundle['sourceRevision']), 'Current unit or source version differs')
    ids = [item['paragraphId'] for item in bundle['items']]
    rows = conn.execute('SELECT id,body FROM public.paragraph WHERE unit_id=%s AND id=ANY(%s)',
                        (bundle['unitId'], ids)).fetchall()
    actual = {r[0]: hashlib.sha256(r[1].encode()).hexdigest() for r in rows}
    require(len(actual) == len(ids), 'Missing or duplicate source paragraph')
    for item in bundle['items']:
        require(actual[item['paragraphId']] == item['sourceSha256'], 'Current paragraph hash differs')
    return validation


def main():
    import psycopg
    from psycopg.types.json import Jsonb
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('preview', 'exercise', 'apply'))
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--schema', type=Path, required=True)
    args = parser.parse_args()
    bundle = json.loads(args.bundle.read_text('utf-8'))
    inventory = json.loads(args.inventory.read_text('utf-8'))
    with psycopg.connect(os.environ['CORPUS_DSN'], autocommit=True) as conn:
        if args.operation == 'preview':
            with conn.transaction():
                conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                result = prepare(conn, bundle, inventory)
                exists = conn.execute("SELECT to_regclass('public.corpus_paragraph_explanation') IS NOT NULL").fetchone()[0]
            print(json.dumps({'operation': 'preview', 'tableExists': exists, **result}, ensure_ascii=False))
            return
        try:
          with conn.transaction():
            conn.execute("SET LOCAL lock_timeout='3s'")
            conn.execute("SET LOCAL statement_timeout='8s'")
            require(conn.execute('SELECT pg_try_advisory_xact_lock(730016,%s)', (bundle['unitId'],)).fetchone()[0],
                    'Another explanation import is active')
            conn.execute('SELECT id FROM public.text_unit WHERE id=%s FOR UPDATE', (bundle['unitId'],))
            conn.execute('SELECT id FROM public.paragraph WHERE unit_id=%s AND id=ANY(%s) ORDER BY id FOR UPDATE',
                         (bundle['unitId'], [item['paragraphId'] for item in bundle['items']]))
            result = prepare(conn, bundle, inventory)
            conn.execute(args.schema.read_text('utf-8'))
            for item in bundle['items']:
                values = (item['paragraphId'], bundle['unitId'], inventory['editionId'], item['revision'],
                          bundle['sourceRevision'], item['sourceSha256'], 'unreviewed', Jsonb(item), Jsonb(bundle['generation']))
                conn.execute('''INSERT INTO public.corpus_paragraph_explanation
                    (paragraph_id,unit_id,edition_id,revision,source_revision,source_sha256,state,content,generation)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (paragraph_id,revision) DO NOTHING''', values)
                stored = conn.execute('''SELECT unit_id,edition_id,source_revision,source_sha256,state,content,generation
                    FROM public.corpus_paragraph_explanation WHERE paragraph_id=%s AND revision=%s''',
                    (item['paragraphId'],item['revision'])).fetchone()
                require(stored == (bundle['unitId'],inventory['editionId'],bundle['sourceRevision'],
                                   item['sourceSha256'],'unreviewed',item,bundle['generation']),
                        'Existing revision differs; refusing overwrite')
            if args.operation == 'exercise':
                raise _RollbackExercise()
        except _RollbackExercise:
            print(json.dumps({'operation': 'exercise-rolled-back', **result}, ensure_ascii=False))
            return
        print(json.dumps({'operation': 'applied-or-already-present', **result}, ensure_ascii=False))


class _RollbackExercise(Exception):
    pass


if __name__ == '__main__':
    main()
