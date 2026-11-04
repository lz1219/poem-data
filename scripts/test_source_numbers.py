import copy,gzip,json,os,unittest
from pathlib import Path
from unittest.mock import patch
from separate_source_numbers import make_plan,apply,verify,read_snapshot


@unittest.skipUnless(os.environ.get('SOURCE_NUMBER_TEST_BACKUP'), 'Server-side fixed backup required')
class SourceNumberTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads(gzip.decompress(Path(os.environ['SOURCE_NUMBER_TEST_BACKUP']).read_bytes()))

    def test_real_plan_keeps_number_and_moves_note_anchors(self):
        snap=self.data['snapshot'];plan=make_plan(snap)
        self.assertEqual((plan['separated'],plan['notesMoved']),(75,26))
        self.assertEqual(plan['gaps'][0]['observed'],[1,2,3,4,6])
        old=next(r for r in snap['rows'] if r['paragraph']['id']==129632)
        new=next(r for r in plan['rows'] if r['paragraph']['id']==129632)
        self.assertEqual(new['origin']['metadata']['eventNumber'],'1')
        self.assertEqual(new['origin']['metadata']['annotations'][0]['anchor'],old['origin']['metadata']['annotations'][0]['anchor']-2)
        self.assertEqual(new['paragraph']['body'],old['paragraph']['body'][2:])

    def test_unmatched_number_or_unsafe_anchor_is_rejected(self):
        for change in ('number','anchor','span'):
            snap=copy.deepcopy(self.data['snapshot']);row=next(r for r in snap['rows'] if r['paragraph']['id']==129632)
            if change=='number':row['origin']['metadata']['eventNumber']='7'
            elif change=='anchor':row['origin']['metadata']['annotations'][0]['anchor']=1
            else:row['origin']['metadata']['spans'][0]['start']=1
            with self.assertRaises(ValueError):make_plan(snap)

    @unittest.skipUnless(os.environ.get('CORPUS_REPAIR_TEST_DSN'),'Explicit database fixture connection required')
    def test_transaction_rollback_idempotence_and_full_readback_in_temp_tables(self):
        import psycopg
        from psycopg.types.json import Jsonb
        snap=self.data['snapshot'];plan=self.data['plan']
        tables=['text_unit','paragraph','corpus_ingest_batch','corpus_unit_origin','corpus_paragraph_origin']
        with psycopg.connect(os.environ['CORPUS_REPAIR_TEST_DSN'],autocommit=True) as conn:
            for table in tables:
                conn.execute('CREATE TEMP TABLE '+table+' (LIKE public.'+table+' INCLUDING ALL)')
                self.assertTrue(conn.execute('SELECT relnamespace=pg_my_temp_schema() FROM pg_class WHERE oid=%s::regclass',(table,)).fetchone()[0])
            fixtures={'text_unit':[snap['unit']],'paragraph':[r['paragraph'] for r in snap['rows']],
                      'corpus_ingest_batch':[snap['oldBatch']],'corpus_unit_origin':[snap['unitOrigin']],
                      'corpus_paragraph_origin':[r['origin'] for r in snap['rows']]}
            for table,records in fixtures.items():
                conn.execute('INSERT INTO '+table+' SELECT * FROM jsonb_populate_recordset(NULL::'+table+',%s)',(Jsonb(records),))
            def fingerprints():
                return [conn.execute("SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]') FROM "+name+' t').fetchone()[0] for name in tables]
            before=fingerprints()
            with patch('separate_source_numbers.copy_rows',side_effect=RuntimeError('injected failure')):
                with self.assertRaisesRegex(RuntimeError,'injected'):apply(conn,snap,plan,'fixture')
            self.assertEqual(fingerprints(),before)
            self.assertEqual(apply(conn,snap,plan,'fixture')['operation'],'applied')
            result=verify(conn,snap,plan)
            self.assertEqual((result['paragraphs'],result['sourceNotesRetained']),(125,33))
            after=fingerprints()
            self.assertEqual(apply(conn,snap,plan,'fixture')['operation'],'already-applied; no writes')
            self.assertEqual(fingerprints(),after)


if __name__=='__main__':unittest.main()
