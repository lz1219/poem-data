import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
from django.test import SimpleTestCase, TestCase

from . import literary_links


class LiteraryLinksReadTests(SimpleTestCase):
    def setUp(self):
        root=Path(__file__).resolve().parents[2]/'data'
        read=lambda p:json.loads((root/p).read_text('utf-8'))
        self.link=read('links/sushi-dingfengbo.json')
        self.docs={'works':read('works/定风波.json'),'persons':read('persons/sushi.json'),
                   'journeys':read('journeys/sushi.json')}
        body='莫听穿林打叶声。竹杖芒鞋轻胜马。一蓑烟雨任平生。'
        w=self.link['work']; p=self.link['person']; j=self.link['journey']
        self.person=[{'editor_sha256':p['editorSha256'],'key':'sushi','zh':'苏轼','cbdb_id':'3767'}]
        self.rows=[{'editor_sha256':w['editorSha256'],'poem_sha256':hashlib.sha256(body.encode()).hexdigest(),
                    'metadata':w,'id':112266,'title':'定风波','author':'苏轼','body':body,
                    'edition_id':14,'batch_id':w['corpusBatchId'],
                    'origin':{'locations':[{'url':w['sourceUrl'],'jsonPointer':w['sourcePointer']}]}}]
        self.stops=[{'journey_key':'sushi','stop_seq':8,'stop_sha256':j['stopSha256'],
                     'relation':'stop-quotes-work','metadata':j}]

    def run_query(self):
        with patch.object(literary_links,'_load',side_effect=lambda group,key:self.docs.get(group)), \
             patch.object(literary_links,'_editor_work_matches',return_value=True), \
             patch.object(literary_links,'_editor_stop_matches',return_value=True), \
             patch.object(literary_links.db,'one',return_value={'ok':True}), \
             patch.object(literary_links.db,'query',side_effect=[self.person,self.rows,self.stops]):
            return literary_links.work_candidates('定风波')

    def test_candidate_keeps_status_and_quote_relation(self):
        items=self.run_query()
        self.assertEqual((items[0]['status'],items[0]['poemId']),('candidate',112266))
        self.assertEqual(items[0]['stops'][0]['relation'],'stop-quotes-work')

    def test_changed_poem_or_work_hides_old_candidate(self):
        self.rows[0]['body']='变化的正文'
        self.assertEqual(self.run_query(),[])
        self.setUp()
        self.docs['works']['titleZh']='变化的作品'
        self.assertEqual(self.run_query(),[])

    def test_changed_stop_is_not_exposed(self):
        self.stops[0]['stop_sha256']='0'*64
        self.assertEqual(self.run_query()[0]['stops'],[])

    def test_reverse_link_rechecks_forward_candidate(self):
        with patch.object(literary_links.db,'one',return_value={'ok':True}), \
             patch.object(literary_links.db,'query',return_value=[{'editor_work_key':'定风波'}]), \
             patch.object(literary_links,'_load',return_value=self.docs['works']), \
             patch.object(literary_links,'work_candidates',return_value=[{'poemId':112266,'differences':'异文待核','stops':[]}]) as check:
            result=literary_links.poem_candidates(112266)
            self.assertEqual(result[0]['workKey'],'定风波')
            self.assertEqual(result[0]['status'],'candidate')
            check.assert_called_once_with('定风波')
        with patch.object(literary_links.db,'one',return_value={'ok':True}), \
             patch.object(literary_links.db,'query',return_value=[{'editor_work_key':'定风波'}]), \
             patch.object(literary_links,'work_candidates',return_value=[]):
            self.assertEqual(literary_links.poem_candidates(112266),[])


class EditorConsistencyTests(TestCase):
    def test_editor_source_edition_and_stop_must_match_published_json(self):
        from .models import Edition, Person, Work, Journey, Stop
        root=Path(__file__).resolve().parents[2]/'data'
        read=lambda p:json.loads((root/p).read_text('utf-8'))
        work=read('works/定风波.json'); person=read('persons/sushi.json'); journey=read('journeys/sushi.json')
        stop=next(s for s in journey['stops'] if s['seq']==8)
        editor=Person.objects.create(key='sushi',zh='苏轼')
        edition=Edition.objects.create(key=work['text']['sourceEdition'],name='样本')
        row=Work.objects.create(key=work['key'],title_zh=work['titleZh'],author=editor,source_edition=edition,
            paragraphs=work['text']['paragraphs'],paragraphs_simplified=work['text']['paragraphsSimplified'])
        trip=Journey.objects.create(key='sushi',person=editor,title_zh='样本')
        place=Stop.objects.create(journey=trip,seq=8,year=stop['year'],place_ancient=stop['place']['ancient'],
                                  title_zh='样本',desc_zh='样本',quote_zh=stop['quote'],source='样本')
        self.assertTrue(literary_links._editor_work_matches(work,person))
        self.assertTrue(literary_links._editor_stop_matches(journey,stop))
        other=Edition.objects.create(key='different-edition',name='另一版本')
        row.source_edition=other;row.save()
        self.assertFalse(literary_links._editor_work_matches(work,person))
        place.quote_zh='不同引文';place.save()
        self.assertFalse(literary_links._editor_stop_matches(journey,stop))
