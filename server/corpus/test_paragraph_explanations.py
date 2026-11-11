import hashlib
from unittest.mock import patch

from django.test import SimpleTestCase

from . import paragraph_explanations


class ParagraphExplanationTests(SimpleTestCase):
    def test_only_latest_matching_source_is_exposed(self):
        unit = {'id': 1, 'origin': {'edition_id': 7, 'metadata': {'revisionId': 3}}}
        paragraph = {'id': 8, 'body': '原文'}
        row = {'paragraph_id': 8, 'revision': 2, 'source_sha256': hashlib.sha256('原文'.encode()).hexdigest(),
               'source_revision': 3, 'edition_id': 7, 'state': 'unreviewed',
               'content': {'paragraphId': 8, 'revision': 2, 'sourceText': '原文',
                           'sourceSha256': hashlib.sha256('原文'.encode()).hexdigest(),
                           'translation': '译文', 'notes': [], 'aiLabel': 'AI生成·未经人工审校',
                           'reviewStatus': 'unreviewed'}, 'generation': {'method': 'ai-batch'}}
        with patch.object(paragraph_explanations.db, 'one', return_value={'ok': True}), \
             patch.object(paragraph_explanations.db, 'query', return_value=[row]):
            paragraph_explanations.attach_explanations(unit, [paragraph])
            self.assertEqual(paragraph['explanation']['translation'], '译文')
            for changes in ({'source_sha256': '0'*64}, {'source_revision': 4}, {'edition_id': 8},
                            {'state': 'withdrawn'}):
                para = {'id': 8, 'body': '原文'}
                with patch.object(paragraph_explanations.db, 'query', return_value=[{**row, **changes}]):
                    paragraph_explanations.attach_explanations(unit, [para])
                self.assertNotIn('explanation', para)

    def test_old_unit_without_origin_does_not_query_new_table(self):
        with patch.object(paragraph_explanations.db, 'one') as query:
            paragraph_explanations.attach_explanations({'id': 1}, [])
            query.assert_not_called()
