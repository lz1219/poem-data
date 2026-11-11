"""影像页链、错误位置及冒充人工审校的负例。"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from corpus.image_evidence import validate_observation,verify_observation_assets
from raw_ingest import derive


def fixture():
    original=b'AT&T synthetic DjVu for identity tests';preview=b'\xff\xd8\xff synthetic preview'
    url='https://thumb.wikimedia.org/example/page2-100px-Test.djvu.jpg'
    info={'sha1':hashlib.sha1(original).hexdigest(),'pagecount':3,'thumburl':url}
    meta={'query':{'pages':[{'title':'File:Test.djvu','revisions':[{'revid':7}],'imageinfo':[info]}]}}
    raw_meta=json.dumps(meta).encode();blobs={}
    def add(raw):
        h=hashlib.sha256(raw).hexdigest();blobs[h]=raw;return h
    item={'sourceId':'image-source','fileTitle':'File:Test.djvu','page':2,'metadataRevisionId':7,
        'originalSha256':add(original),'originalMetadataSha256':add(raw_meta),
        'previewSha256':add(preview),'previewMetadataSha256':add(raw_meta),'previewUrl':url,
        'sourceUrl':'https://commons.wikimedia.org/w/index.php?oldid=7',
        'reading':'卷二十八','method':'AI目读','origin':'ai','generatedAt':'2026-11-01T00:00:00Z','status':'pending','reviewHistory':[]}
    asset={k:item[k] for k in ['fileTitle','originalSha256','originalMetadataSha256','metadataRevisionId','sourceUrl']}
    asset['previews']=[{k:item[k] for k in ['page','previewSha256','previewMetadataSha256','previewUrl']}]
    source={'id':'image-source','imageAssets':[asset]}
    return item,source,blobs


class ImageEvidenceTests(unittest.TestCase):
    def test_registered_page_is_locatable_without_claiming_reading_is_verified(self):
        item,source,blobs=fixture()
        self.assertEqual(validate_observation(item,{'image-source':source}),[])
        self.assertTrue(verify_observation_assets(item,blobs))
        self.assertEqual(item['status'],'pending')

    def test_wrong_page_revision_and_asset_cannot_pass(self):
        item,source,blobs=fixture()
        for key,value in [('page',0),('page',1),('metadataRevisionId',8),('previewSha256','0'*64)]:
            bad={**item,key:value}
            with self.subTest(key=key,value=value):self.assertTrue(validate_observation(bad,{'image-source':source}))
        bad={**item,'page':1}
        with self.assertRaisesRegex(ValueError,'页序'):verify_observation_assets(bad,blobs)
        bad={**item,'metadataRevisionId':8}
        with self.assertRaisesRegex(ValueError,'修订'):verify_observation_assets(bad,blobs)

    def test_tampering_missing_blob_and_changed_file_metadata_are_rejected(self):
        item,source,blobs=fixture();broken=dict(blobs);broken.pop(item['previewSha256'])
        with self.assertRaisesRegex(ValueError,'缺失'):verify_observation_assets(item,broken)
        broken=dict(blobs);broken[item['previewSha256']]+=b'changed'
        with self.assertRaisesRegex(ValueError,'哈希'):verify_observation_assets(item,broken)
        meta=json.loads(blobs[item['previewMetadataSha256']]);meta['query']['pages'][0]['imageinfo'][0]['sha1']='0'*40
        raw=json.dumps(meta).encode();key=hashlib.sha256(raw).hexdigest();blobs[key]=raw;item['previewMetadataSha256']=key
        with self.assertRaisesRegex(ValueError,'SHA1'):verify_observation_assets(item,blobs)

    def test_verified_requires_an_individual_named_scope(self):
        item,source,_=fixture();item['status']='verified'
        self.assertIn('影像已核须逐项具名审校',validate_observation(item,{'image-source':source}))
        item['reviewHistory']=[{'reviewer':'fixture-reviewer','reviewedAt':'fixture-date','scope':'此图卷题读文','decision':'verified'}]
        self.assertEqual(validate_observation(item,{'image-source':source}),[])

    def test_ingestion_requires_image_assets_in_this_batch(self):
        item,source,blobs=fixture();note={'subject':{'type':'source','key':'image-source'},'imageObservations':[item]}
        records=[('s','source','image-source',0,source,'sources','h'),('r','research_revision','note',1,note,'note','h')]
        bundle={'entries':[],'snapshots':[],'records':records,'manifest':{'assets':[]}}
        self.assertIn('invalid-image-observation',[r[3] for r in derive(bundle,'b')['issue']])
        bundle['manifest']['assets']=[(str(i),'image-original',h) for i,h in enumerate(blobs)]
        result=derive(bundle,'b')
        self.assertNotIn('invalid-image-observation',[r[3] for r in result['issue']])
        self.assertEqual(result['quote_match'],[])
        self.assertIn('image-reading-unreviewed',[r[3] for r in result['issue']])


if __name__=='__main__':unittest.main()
