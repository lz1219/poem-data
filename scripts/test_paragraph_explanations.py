import copy
import json
from pathlib import Path
import unittest
from paragraph_explanations import validate

ROOT=Path(__file__).resolve().parent.parent


class ExplanationCandidatesTests(unittest.TestCase):
    def setUp(self):
        self.bundle=json.loads((ROOT/'data/paragraph-explanations/zztj-volume001-candidates.json').read_text('utf-8'))
        self.inventory=json.loads((ROOT/'docs/reports/ai-reading-0001-inventory.json').read_text('utf-8'))

    def test_real_representatives_have_independent_translation_and_original_anchors(self):
        result=validate(self.bundle,self.inventory)
        self.assertEqual((result['paragraphs'],result['notes'],result['humanReviewed']),(2,7,0))

    def test_source_revision_or_text_change_is_rejected(self):
        for mutate in [lambda b:b.update(sourceRevision=0),
                       lambda b:b['items'][0].update(sourceText='不同的原文')]:
            bundle=copy.deepcopy(self.bundle);mutate(bundle)
            with self.assertRaises(ValueError):validate(bundle,self.inventory)

    def test_annotation_range_and_quote_must_match_original(self):
        for values in [{'start':-1},{'end':99999},{'quote':'其他文字'}]:
            bundle=copy.deepcopy(self.bundle);bundle['items'][0]['notes'][0].update(values)
            with self.assertRaises(ValueError):validate(bundle,self.inventory)

    def test_missing_ai_marker_and_fake_commentary_are_rejected(self):
        for values in [{'aiLabel':''},{'reviewStatus':'reviewed'},{'commentary':'假托古人'}]:
            bundle=copy.deepcopy(self.bundle);bundle['items'][0].update(values)
            with self.assertRaises(ValueError):validate(bundle,self.inventory)

    def test_duplicate_paragraph_is_rejected(self):
        self.bundle['items'].append(copy.deepcopy(self.bundle['items'][0]))
        with self.assertRaises(ValueError):validate(self.bundle,self.inventory)


if __name__=='__main__':unittest.main()
