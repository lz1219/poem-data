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

    def test_modified_source_unit_invalidates_the_manifest(self):
        unit={'juan':'卷001','body':'原文'}
        manifest={'unitDigests':[digest(unit)]}
        plan={'manifest':manifest,'batchId':digest(manifest),'units':[unit]}
        tampered=copy.deepcopy(plan);tampered['units'][0]['body']='改文'
        with self.assertRaisesRegex(ValueError,'unit checksums'):
            validate_source(tampered,'卷001')


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


if __name__ == '__main__': unittest.main()
