import hashlib
import json
import tempfile
import sys
from pathlib import Path
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.test import override_settings
from django.core.management import call_command
from io import StringIO
from .models import Person, Work, ResearchRevision, ResearchArtifact, SourceRecord
from .research_rules import validate_record


class ResearchContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.person = Person.objects.create(key='dufu', zh='杜甫', born=712, died=770, journey_key='dufu')
        cls.work = Work.objects.create(key='春望', title_zh='春望', author=cls.person,
            paragraphs=['白頭搔更短，渾欲不勝簪。'], paragraphs_simplified=['白头搔更短，浑欲不胜簪。'],
            notes=[{'term': '簪', 'explain': '插不住簪子'}], appreciation='赏析', place_key='changan')

    def test_simplified_body_and_note_search(self):
        for query in ['白頭搔更短', '白头搔更短', '插不住簪子']:
            r = self.client.get('/api/search', {'q': query, 'scope': 'works'})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()['works'][0]['key'], '春望')

    def test_dynamic_shape_matches_static_reader(self):
        d = self.client.get('/api/works/春望').json()
        self.assertEqual(d['appreciation']['text'], '赏析')
        self.assertEqual(d['appreciation'], d['appreciation_field'])
        self.assertEqual(d['composed']['placeKey'], 'changan')
        p = self.client.get('/api/persons/dufu').json()
        self.assertEqual(p['journeyKey'], 'dufu')

    def record(self, revision=1, visibility='public'):
        return {'id': 'test-record', 'revision': revision, 'kind': 'audit', 'status': 'pending', 'visibility': visibility,
                'subject': {'type': 'work', 'key': '春望'}, 'title': '测试', 'claim': '待核',
                'provenance': {'origin': 'unknown'}, 'counterEvidence': '尚未检索', 'reviewHistory': [], 'evidence': []}

    def test_rejected_latest_never_falls_back_to_public_old_revision(self):
        for revision in [1, 2]:
            d = self.record(revision)
            if revision == 2: d['status'] = 'rejected'
            ResearchRevision.objects.create(record_id=d['id'], revision=revision, payload=d)
        self.assertEqual(self.client.get('/api/research').json()['records'], [])
        self.assertEqual(self.client.get('/api/research/test-record').status_code, 404)
        self.assertEqual(self.client.get('/api/research/test-record/1').status_code, 200)
        self.assertEqual(self.client.get('/api/research/test-record/2').status_code, 404)

    def test_internal_is_not_served_and_public_cannot_turn_private(self):
        d = self.record(1, 'internal')
        ResearchRevision.objects.create(record_id=d['id'], revision=1, payload=d)
        self.assertEqual(self.client.get('/api/research/test-record/1').status_code, 404)
        d = self.record(2, 'public')
        ResearchRevision.objects.create(record_id=d['id'], revision=2, payload=d)
        d = self.record(3, 'internal')
        with self.assertRaises(ValidationError):
            ResearchRevision.objects.create(record_id=d['id'], revision=3, payload=d)

    def test_old_revision_cannot_be_changed(self):
        row = ResearchRevision.objects.create(record_id='test-record', revision=1, payload=self.record())
        row.payload['claim'] = 'changed'
        with self.assertRaises(ValidationError): row.save()

    def test_ai_missing_model_or_grounded_evidence_is_rejected(self):
        d = self.record()
        d.update(kind='inference', reasoning='推理', provenance={'origin': 'ai'})
        errors = validate_record(d)
        self.assertIn('AI推测缺model', errors)
        self.assertIn('公开推测缺真实证据', errors)

    def test_forged_verified_flag_does_not_pass(self):
        d = self.record()
        d['evidence'] = [{'verifiedQuote': True, 'quote': '伪造', 'sourceId': 'kanripo', 'sha256': 'f' * 64,
                          'locator': 'fake', 'textFile': '../outside.txt'}]
        self.assertTrue(any('越界' in e for e in validate_record(d)))

    def test_verified_requires_named_review_and_evidence(self):
        d = self.record()
        d['status'] = 'verified'
        self.assertIn('已核状态须有证据及具名核验决定', validate_record(d))

    def test_database_validation_does_not_read_repository_sources(self):
        content = '测试原句来自数据库独有版本。'
        sha = hashlib.sha256(content.encode()).hexdigest()
        ResearchArtifact.objects.create(sha256=sha, text=content)
        SourceRecord.objects.create(key='test-only-source', payload={'id': 'test-only-source'})
        d = self.record()
        d['evidence'] = [{'sourceId': 'test-only-source', 'sha256': sha, 'quote': content,
                          'textFile': f'data/witnesses/{sha}.txt', 'locator': '测试卷', 'verifiedQuote': True}]
        row = ResearchRevision.objects.create(record_id=d['id'], revision=1, payload=d)
        self.assertEqual(self.client.get('/api/research/test-record/1').status_code, 200)

    def test_source_subject_requires_registered_source_and_is_readable(self):
        SourceRecord.objects.create(key='edition-quality', payload={'id':'edition-quality'})
        d = self.record()
        d['subject'] = {'type':'source','key':'edition-quality'}
        ResearchRevision.objects.create(record_id=d['id'], revision=1, payload=d)
        self.assertEqual(self.client.get('/api/research/test-record/1').json()['subject'], d['subject'])
        self.assertEqual(self.client.get('/api/research').json()['records'][0]['subject'], d['subject'])
        d = self.record(2)
        d['subject'] = {'type':'source','key':'missing-source'}
        with self.assertRaises(ValidationError):
            ResearchRevision.objects.create(record_id=d['id'], revision=2, payload=d)
        d['subject'] = {'type':'unsupported','key':'edition-quality'}
        self.assertIn('研究对象类型非法', validate_record(d, source_ids={'edition-quality'}, artifacts={}))

    def test_image_observation_roundtrip_uses_database_registry_and_keeps_pending(self):
        image={'sourceId':'image-test','fileTitle':'File:Test.djvu','page':2,'metadataRevisionId':7,
            'originalSha256':'a'*64,'originalMetadataSha256':'b'*64,'previewSha256':'c'*64,'previewMetadataSha256':'d'*64,
            'previewUrl':'https://example.org/page2.jpg','sourceUrl':'https://example.org/source',
            'reading':'卷二十八','method':'AI目读','origin':'ai','generatedAt':'fixture-date','status':'pending','reviewHistory':[]}
        asset={k:image[k] for k in ['fileTitle','originalSha256','originalMetadataSha256','metadataRevisionId','sourceUrl']}
        asset['previews']=[{k:image[k] for k in ['page','previewSha256','previewMetadataSha256','previewUrl']}]
        SourceRecord.objects.create(key='image-test',payload={'id':'image-test','imageAssets':[asset]})
        d=self.record();d['imageObservations']=[image]
        d['provenance']={'origin':'mixed','model':'fixture','modelVersion':'fixture','generatedAt':'fixture-date'}
        ResearchRevision.objects.create(record_id=d['id'],revision=1,payload=d)
        self.assertEqual(self.client.get('/api/research/test-record/1').json()['imageObservations'],[image])
        d=self.record(2);d['provenance']={'origin':'mixed','model':'fixture','modelVersion':'fixture','generatedAt':'fixture-date'}
        d['imageObservations']=[{**image,'page':1}]
        with self.assertRaises(ValidationError):ResearchRevision.objects.create(record_id=d['id'],revision=2,payload=d)
        d['imageObservations']=[image];d['status']='verified';d['reviewHistory']=[{'reviewer':'fixture','reviewedAt':'fixture','decision':'verified'}]
        with self.assertRaises(ValidationError):ResearchRevision.objects.create(record_id=d['id'],revision=2,payload=d)

    def test_internal_to_public_script_keeps_one_revision_sequence(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
        from research_records import save_record
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'
            a = self.record(1, 'internal')
            first = save_record(root, a)
            a['visibility'] = 'public'
            second = save_record(root, a)
            self.assertEqual(first['revision'], 1)
            self.assertEqual(second['revision'], 2)
            self.assertFalse((root / 'data/research-history/test-record/1.json').exists())
            self.assertTrue((Path(tmp) / '.local/research-private/research-history/test-record/1.json').exists())

    def test_independent_export_contains_index_artifact_registry_and_immutable_history(self):
        content = '独立导出包中的原句。'
        sha = hashlib.sha256(content.encode()).hexdigest()
        ResearchArtifact.objects.create(sha256=sha, text=content)
        source = {'id': 'portable-source', 'name': '独立测试版本'}
        SourceRecord.objects.create(key=source['id'], payload=source)
        SourceRecord.objects.create(key='__registry__', payload={'schemaVersion': '1.0', 'sources': [source], 'catalogs': []})
        d = self.record()
        d['evidence'] = [{'sourceId': source['id'], 'sha256': sha, 'quote': content, 'textFile': f'data/witnesses/{sha}.txt', 'locator': '测试卷', 'verifiedQuote': True}]
        ResearchRevision.objects.create(record_id=d['id'], revision=1, payload=d)
        with tempfile.TemporaryDirectory() as tmp, override_settings(PRIVATE_RESEARCH_DIR=Path(tmp) / 'private'):
            out = Path(tmp) / 'data'
            call_command('export_json', out=str(out), stdout=StringIO())
            self.assertEqual(json.loads((out / 'research-index.json').read_text('utf-8'))['records'][0]['id'], d['id'])
            self.assertEqual((out / 'witnesses' / f'{sha}.txt').read_text('utf-8'), content)
            self.assertEqual(json.loads((out.parent / 'shared/sources.json').read_text('utf-8'))['sources'], [source])
            call_command('import_json', data_dir=str(out), keep=True, stdout=StringIO())
            history = out / 'research-history/test-record/1.json'
            history.write_text('{"changed":true}', encoding='utf-8')
            with self.assertRaises(ValueError): call_command('export_json', out=str(out), stdout=StringIO())
