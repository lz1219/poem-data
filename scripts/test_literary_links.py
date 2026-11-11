import copy
import hashlib
import json
from pathlib import Path
import unittest

from validate_literary_links import validate

ROOT = Path(__file__).resolve().parent.parent


class LiteraryLinksTest(unittest.TestCase):
    def setUp(self):
        self.link = json.loads((ROOT/'data/links/sushi-dingfengbo.json').read_text('utf-8'))
        self.person = json.loads((ROOT/'data/persons/sushi.json').read_text('utf-8'))
        self.work = json.loads((ROOT/'data/works/定风波.json').read_text('utf-8'))
        self.journey = json.loads((ROOT/'data/journeys/sushi.json').read_text('utf-8'))
        self.corpus_person = {'id':58,'key':'sushi','zh':'苏轼','cbdb_id':'3767'}
        self.poem = {'id':112266,'body':'莫听穿林打叶声。竹杖芒鞋轻胜马。一蓑烟雨任平生。',
                     'edition_id':14,'batch_id':self.link['work']['corpusBatchId'],
                     'metadata':{'locations':[{'url':self.link['work']['sourceUrl'],'jsonPointer':'/509'}]}}
        self.link['work']['corpusBodySha256'] = hashlib.sha256(self.poem['body'].encode()).hexdigest()

    def check(self):
        return validate(self.link,self.person,self.work,self.journey,self.corpus_person,self.poem)

    def test_exact_evidence_is_candidate_only(self):
        self.assertEqual(self.check()['status'],'candidate')

    def test_changed_source_or_identity_cannot_be_published_as_same_link(self):
        for attr, value in [('body','错误正文'),('id',112534),('edition_id',15)]:
            old=copy.deepcopy(self.poem)
            self.poem[attr]=value
            with self.assertRaises(ValueError):self.check()
            self.poem=old
        self.person['zh']='另一个人物'
        with self.assertRaises(ValueError):self.check()

    def test_missing_evidence_and_unaudited_status_are_rejected(self):
        for mutate in (lambda x:x['work'].update(matchingText=[]),
                       lambda x:x['journey'].update(relation='visited'),
                       lambda x:x.update(status='verified')):
            old=copy.deepcopy(self.link);mutate(self.link)
            with self.assertRaises(ValueError):self.check()
            self.link=old


if __name__ == '__main__':
    unittest.main()
