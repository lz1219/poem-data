"""原卷定位与证据范围的负例，不访问网络或数据库。"""
import copy
import json
import unittest
from original_volume_locators import scan_headings,validate_locator,sha
from raw_ingest import derive


class OriginalVolumeTests(unittest.TestCase):
    RAW=('\ufeff#+PROPERTY: JUAN 1\n#+PROPERTY: FILE 原卷三十八\n'
         '<pb:SB_001-1a>¶\n　王文成公全書卷之三十七¶\n甲乙\n'
         '　王文成公全書卷之三十八¶\n丙丁\n　王文成公全書卷之三十八¶').encode()

    def test_explicit_headings_preserve_duplicates_and_byte_offsets(self):
        rows=scan_headings(self.RAW)
        self.assertEqual([r['volume'] for r in rows],[37,38,38])
        for row in rows:
            self.assertTrue(validate_locator(row,self.RAW))
            self.assertEqual(self.RAW[row['startByte']:row['endByte']].decode(),row['header'])
        self.assertEqual(scan_headings('\ufeff王文成公全書卷之一¶'.encode())[0]['volume'],1)

    def test_wrong_volume_range_hash_or_page_is_rejected(self):
        row=scan_headings(self.RAW)[0]
        for key,value in [('volume',1),('startByte',row['startByte']+1),('fileSha256','0'*64),('sourcePageMarker','bad')]:
            bad={**row,key:value}
            with self.subTest(key=key),self.assertRaises((ValueError,UnicodeError)):validate_locator(bad,self.RAW)

    def test_missing_all_or_one_heading_and_duplicates_are_blocked(self):
        repo,commit,path='kanripo/KR4e0157','a'*40,'KR4e0157_001.txt'
        records=[]
        for row in scan_headings(self.RAW):
            key=sha(json.dumps([repo,commit,path,row['startByte']],ensure_ascii=False).encode())
            doc={'id':key,'repository':repo,'commit':commit,'path':path,'archiveSha256':'archive',**row}
            records.append((key,'volume_heading',key,0,doc,'manifest.json','hash'))
        bundle={'snapshots':[('s',repo,commit,'archive',{})],
                'entries':[('s',path,'text',sha(self.RAW),self.RAW)],'records':records}
        self.assertNotIn('volume-heading-set-mismatch',[r[3] for r in derive(bundle,'b')['issue']])
        for invalid in [[],records[:-1],records+[records[0]]]:
            bad={**bundle,'records':invalid}
            self.assertIn('volume-heading-set-mismatch',[r[3] for r in derive(bad,'b')['issue']])

    def test_claimed_evidence_range_must_point_to_the_quote(self):
        repo,commit,path='kanripo/KR4c0012','a'*40,'KR4c0012_001.txt'
        raw='甲乙丙'.encode()
        doc={'evidence':[{'url':f'https://github.com/{repo}/blob/{commit}/{path}',
                         'quote':'乙','startByte':0,'endByte':3}]}
        bundle={'snapshots':[('s',repo,commit,'archive',{})],'entries':[('s',path,'text',sha(raw),raw)],
                'records':[('r','research_revision','note',1,doc,'n','h')]}
        self.assertIn('evidence-byte-range-mismatch',[r[3] for r in derive(bundle,'b')['issue']])
        doc['evidence'][0].update(startByte=3,endByte=6)
        self.assertNotIn('evidence-byte-range-mismatch',[r[3] for r in derive(bundle,'b')['issue']])


if __name__=='__main__':unittest.main()
