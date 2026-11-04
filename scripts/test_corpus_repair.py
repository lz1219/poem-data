import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import corpus_repair
from corpus_repair import map_rows, validate_source, snapshot, apply, verify
from backfill_shiji import digest


class RepairMappingTests(unittest.TestCase):
    def source(self):
        return {'paragraphs': [
            {'body':'安王元年','legacyText':None,'origin':{'kind':'heading'}},
            {'body':'1　原文。','legacyText':'1　原文。','origin':{'kind':'paragraph'}}],
            'legacyProjection': {'bodySha256':hashlib.sha256('1　原文。\n周'.encode()).hexdigest(),
                                 'trailer':['周']}}

    def test_unchanged_main_text_keeps_its_id_and_source_category_is_explicit(self):
        old=[{'id':91,'body':'1　原文。'},{'id':92,'body':'周'}]
        mapped, retired=map_rows(old,self.source())
        self.assertEqual([p['id'] for p in mapped],[None,91])
        self.assertEqual(retired,[92])

    def test_old_text_change_cannot_be_hidden_by_a_source_plan(self):
        with self.assertRaisesRegex(ValueError,'reproduce'):
            map_rows([{'id':91,'body':'1　改文。'},{'id':92,'body':'周'}],self.source())

    def test_display_normalization_is_not_implicitly_approved(self):
        source=self.source();source['paragraphs'][1]['body']='1　原文！'
        with self.assertRaisesRegex(ValueError,'separately reviewed'):
            map_rows([{'id':91,'body':'1　原文。'},{'id':92,'body':'周'}],source)

    def test_unexplained_tail_and_unmapped_main_text_are_rejected(self):
        source=self.source();source['legacyProjection']['trailer']=[]
        with self.assertRaisesRegex(ValueError,'Unexplained'):
            map_rows([{'id':91,'body':'1　原文。'},{'id':92,'body':'周'}],source)
        source=self.source();source['paragraphs'][0]['origin']['kind']='paragraph'
        with self.assertRaisesRegex(ValueError,'Only explicit'):
            map_rows([{'id':91,'body':'1　原文。'},{'id':92,'body':'周'}],source)

    def test_source_divider_retires_only_its_explicit_old_row(self):
        source=self.source()
        source['paragraphs'][1]['legacyRetiredBefore']=['----']
        source['legacyProjection']['bodySha256']=hashlib.sha256('----\n1　原文。\n周'.encode()).hexdigest()
        old=[{'id':90,'body':'----'},{'id':91,'body':'1　原文。'},{'id':92,'body':'周'}]
        mapped,retired=map_rows(old,source)
        self.assertEqual([x['id'] for x in mapped],[None,91])
        self.assertEqual(retired,[90,92])
        source['paragraphs'][1]['legacyRetiredBefore']=['正文']
        with self.assertRaisesRegex(ValueError,'divider'):map_rows(old,source)

    def test_modified_source_unit_invalidates_the_manifest(self):
        unit={'juan':'卷001','body':'原文'}
        manifest={'unitDigests':[digest(unit)]}
        plan={'manifest':manifest,'batchId':digest(manifest),'units':[unit]}
        tampered=copy.deepcopy(plan);tampered['units'][0]['body']='改文'
        with self.assertRaisesRegex(ValueError,'unit checksums'):
            validate_source(tampered,'卷001')

    def test_audited_markup_and_number_profile_rejects_real_character_changes(self):
        source=self.source();source['normalizationProfile']='zztj-volume002-wiki-events-v1'
        source['paragraphs'][1]['legacyText']='1　原-{文}-。'
        source['paragraphs'][1]['body']='原文。'
        source['paragraphs'][1]['origin']['sourceEventPrefix']='1　'
        source['legacyProjection']['bodySha256']=hashlib.sha256('1　原-{文}-。\n周'.encode()).hexdigest()
        old=[{'id':91,'body':'1　原-{文}-。'},{'id':92,'body':'周'}]
        self.assertEqual(map_rows(old,source)[0][1]['id'],91)
        source['paragraphs'][1]['body']='改文。'
        with self.assertRaisesRegex(ValueError,'Unsupported character change'):
            map_rows(old,source)

    def test_batch_profile_moves_number_and_note_anchor_without_changing_original(self):
        body='1　原文。'
        block={'body':body,'origin':{'kind':'paragraph','eventNumber':'1',
            'spans':[{'kind':'source-text','start':0,'end':len(body)}],
            'annotations':[{'anchor':4,'body':'校记'}]}}
        source={'juan':'卷003','body':body,'bodySimplified':body,
            'origin':{'parser':'wikisource-chronicle-batch-v1','revisionId':7},'paragraphs':[block]}
        result=corpus_repair.prepare_wiki_events(source)
        self.assertEqual(result['paragraphs'][0]['body'],'原文。')
        self.assertEqual(result['paragraphs'][0]['origin']['annotations'][0]['anchor'],2)
        self.assertEqual(result['paragraphs'][0]['origin']['sourceEventPrefix'],'1　')
        self.assertEqual(source['paragraphs'][0]['body'],body)
        source['paragraphs'][0]['origin']['eventNumber']='2'
        with self.assertRaisesRegex(ValueError,'Invalid source number'):
            corpus_repair.prepare_wiki_events(source)


@unittest.skipUnless(os.environ.get('CORPUS_REPAIR_TEST_DSN'), 'Explicit isolated PostgreSQL fixture connection required')
class RepairTransactionTests(unittest.TestCase):
    def test_failure_rolls_back_all_tables_and_repeated_apply_writes_nothing(self):
        import psycopg
        schema = '''
            CREATE TEMP TABLE book(id integer PRIMARY KEY,title text);
            CREATE TEMP TABLE text_unit(id integer PRIMARY KEY,book_id integer REFERENCES book(id),
                juan text,title text,body text,body_simplified text,sha256 text,edition text,source_url text);
            CREATE TEMP TABLE paragraph(id serial PRIMARY KEY,unit_id integer REFERENCES text_unit(id),
                seq integer,body text,UNIQUE(unit_id,seq));
            CREATE TEMP TABLE edition(id serial PRIMARY KEY,book_id integer REFERENCES book(id),name text,kind text,note text);
            CREATE TEMP TABLE corpus_ingest_batch(batch_id text PRIMARY KEY,book_id integer REFERENCES book(id),
                edition_id integer REFERENCES edition(id),state text,manifest jsonb,result jsonb);
            CREATE TEMP TABLE corpus_unit_origin(unit_id integer PRIMARY KEY REFERENCES text_unit(id),
                batch_id text REFERENCES corpus_ingest_batch(batch_id),edition_id integer REFERENCES edition(id),ordinal integer,metadata jsonb);
            CREATE TEMP TABLE corpus_paragraph_origin(paragraph_id integer PRIMARY KEY REFERENCES paragraph(id),
                batch_id text REFERENCES corpus_ingest_batch(batch_id),metadata jsonb);
        '''
        with psycopg.connect(os.environ['CORPUS_REPAIR_TEST_DSN'],autocommit=True) as c, tempfile.TemporaryDirectory() as directory:
            c.execute(schema)
            # Every writer target, FK and owned ID sequence lives in pg_temp.
            for name in ('book','text_unit','paragraph','edition','corpus_ingest_batch','corpus_unit_origin','corpus_paragraph_origin'):
                self.assertTrue(c.execute('SELECT relnamespace=pg_my_temp_schema() FROM pg_class WHERE oid=%s::regclass',(name,)).fetchone()[0])
            c.execute("INSERT INTO book VALUES(-80,'测试书')")
            c.execute("INSERT INTO text_unit VALUES(-2080,-80,'卷一','卷一','原文。'||chr(10)||'分类',NULL,'old','旧版','old-source')")
            c.execute("INSERT INTO paragraph(id,unit_id,seq,body) VALUES(-1,-2080,1,'原文。'),(-2,-2080,2,'分类')")
            source={'juan':'卷一','body':'源标题\n\n原文。','bodySimplified':None,
                'sourceUrl':'https://zh.wikisource.org/w/index.php?oldid=1',
                'origin':{'sourceUrl':'https://zh.wikisource.org/w/index.php?oldid=1','sourcePath':'测试书/卷一','revisionId':1},
                'paragraphs':[{'body':'源标题','legacyText':None,'origin':{'kind':'heading','annotations':[]}},
                              {'body':'原文。','legacyText':'原文。','origin':{'kind':'paragraph','annotations':[]}}],
                'legacyProjection':{'parser':'legacy-wikisource-clean-v1',
                    'bodySha256':hashlib.sha256('原文。\n分类'.encode()).hexdigest(),'trailer':['分类']}}
            source['sha256']=hashlib.sha256(source['body'].encode()).hexdigest()
            manifest={'bookId':-80,'bookTitle':'测试书','unitDigests':[digest(source)],'reviewStatus':'isolated-test-fixture'}
            plan={'manifest':manifest,'batchId':digest(manifest),'units':[source]}
            data=json.loads(corpus_repair.canonical(snapshot(c,plan,'卷一',-2080)))
            tables=('book','text_unit','paragraph','edition','corpus_ingest_batch','corpus_unit_origin','corpus_paragraph_origin')
            def fingerprints():
                return [c.execute('SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),\'[]\') FROM '+t+' t').fetchone()[0] for t in tables]
            before=fingerprints();original_step=corpus_repair.step
            def fail_last(conn,events,name,statement,params=()):
                if name=='record-result':raise RuntimeError('injected before commit')
                return original_step(conn,events,name,statement,params)
            with patch.object(corpus_repair,'step',side_effect=fail_last):
                with self.assertRaisesRegex(RuntimeError,'injected'):
                    apply(c,data,'test-backup',Path(directory)/'events.jsonl')
            self.assertEqual(fingerprints(),before)
            result=apply(c,data,'test-backup',Path(directory)/'events.jsonl')
            self.assertEqual(result['operation'],'applied')
            self.assertEqual(verify(c,data)['verifiedBlocks'],2)
            after=fingerprints()
            self.assertEqual(apply(c,data,'test-backup',Path(directory)/'events.jsonl')['operation'],'already-applied; no writes')
            self.assertEqual(fingerprints(),after)
            c.execute("INSERT INTO paragraph(unit_id,seq,body) VALUES(-2080,3,'未映射额外段落')")
            with self.assertRaisesRegex(ValueError,'scope or sequence'):verify(c,data)

    @unittest.skipUnless(os.environ.get('CORPUS_REPAIR_VOLUME2_BACKUP'),'Fixed volume-002 backup required')
    def test_fixed_volume002_transaction_rolls_back_and_keeps_source_numbers(self):
        import gzip
        import psycopg
        from psycopg.types.json import Jsonb
        data=json.loads(gzip.decompress(Path(os.environ['CORPUS_REPAIR_VOLUME2_BACKUP']).read_bytes()))
        tables=('book','text_unit','paragraph','edition','corpus_ingest_batch','corpus_unit_origin','corpus_paragraph_origin')
        with psycopg.connect(os.environ['CORPUS_REPAIR_TEST_DSN'],autocommit=True) as c, tempfile.TemporaryDirectory() as directory:
            for name in tables:
                c.execute('CREATE TEMP TABLE '+name+' (LIKE public.'+name+' INCLUDING ALL)')
                self.assertTrue(c.execute('SELECT relnamespace=pg_my_temp_schema() FROM pg_class WHERE oid=%s::regclass',(name,)).fetchone()[0])
            for name in ('paragraph','edition'):
                c.execute('CREATE TEMP SEQUENCE fixture_'+name+'_seq START 2000000000')
                c.execute('ALTER SEQUENCE fixture_'+name+'_seq OWNED BY '+name+'.id')
                c.execute("ALTER TABLE "+name+" ALTER COLUMN id SET DEFAULT nextval('fixture_"+name+"_seq')")
            fixtures={'book':[data['book']],'text_unit':[data['unit']],
                      'paragraph':[r[0] for r in data['paragraphs']]}
            for name,rows in fixtures.items():
                c.execute('INSERT INTO '+name+' SELECT * FROM jsonb_populate_recordset(NULL::'+name+',%s)',(Jsonb(rows),))
            def fingerprints():
                return [c.execute("SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]') FROM "+name+' t').fetchone()[0] for name in tables]
            before=fingerprints();step=corpus_repair.step
            def fail_last(conn,events,name,statement,params=()):
                if name=='record-result':raise RuntimeError('injected before commit')
                return step(conn,events,name,statement,params)
            # This historical fixture reuses production IDs, whose real origins now exist.
            # The separate negative-ID transaction test exercises the unpatched guard.
            with patch.object(corpus_repair,'guard_references'):
                with patch.object(corpus_repair,'step',side_effect=fail_last):
                    with self.assertRaisesRegex(RuntimeError,'injected'):apply(c,data,'fixture',Path(directory)/'events.jsonl')
                self.assertEqual(fingerprints(),before)
                result=apply(c,data,'fixture',Path(directory)/'events.jsonl')
            check=verify(c,data)
            self.assertEqual((result['operation'],check['verifiedBlocks'],check['retainedMainTextIds'],check['editorialNotes']),('applied',163,121,53))
            self.assertEqual(data['source']['origin']['sourceNumberSeparation']['count'],96)
            after=fingerprints()
            self.assertEqual(apply(c,data,'fixture',Path(directory)/'events.jsonl')['operation'],'already-applied; no writes')
            self.assertEqual(fingerprints(),after)

    @unittest.skipUnless(os.environ.get('CORPUS_REPAIR_VOLUME2_BACKUP'),'Fixed volume-002 backup required')
    def test_all_volume002_source_note_anchors_survive_number_removal(self):
        import gzip
        backup=Path(os.environ['CORPUS_REPAIR_VOLUME2_BACKUP'])
        data=json.loads(gzip.decompress(backup.read_bytes()))
        plan=json.loads(backup.with_name('source-plan.json').read_text('utf-8'))
        original=next(u for u in plan['units'] if u['juan']=='卷002')
        restored=data['source'];self.assertEqual(len(original['paragraphs']),len(restored['paragraphs']))
        total=0
        for before,after in zip(original['paragraphs'],restored['paragraphs']):
            shift=len(before['body'])-len(after['body'])
            self.assertIn(shift,(0,2,3))
            self.assertEqual(before['body'][shift:],after['body'])
            notes_before=before['origin']['annotations'];notes_after=after['origin']['annotations']
            self.assertEqual(len(notes_before),len(notes_after))
            for old,new in zip(notes_before,notes_after):
                self.assertEqual(old['anchor']-shift,new['anchor'])
                self.assertEqual(before['body'][old['anchor']:],after['body'][new['anchor']:])
                self.assertEqual((old['sourceByteStart'],old['sourceByteEnd'],old['body']),
                                 (new['sourceByteStart'],new['sourceByteEnd'],new['body']))
                total+=1
        self.assertEqual(total,53)


if __name__ == '__main__': unittest.main()
