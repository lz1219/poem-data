"""Scope expansion must preserve first-batch defaults and original source glyphs."""
import unittest
from backfill_hanshu import parse_file, PARSER


class AppendScopeTests(unittest.TestCase):
    def test_existing_annals_default_does_not_accept_biography(self):
        raw = '#+PROPERTY: BASEEDITION WYG\n#+PROPERTY: JUAN 卷三十一\n<pb:p>原(注)𠮷&KR0912;¶\n'.encode()
        with self.assertRaisesRegex(ValueError, 'outside'):
            parse_file('fixture.txt', raw)
        unit = parse_file('fixture.txt', raw, allowed_volumes=range(31, 51), parser='new-parser')[0]
        self.assertEqual(unit['body'], '原(注)𠮷&KR0912;')
        self.assertEqual(unit['origin']['parser'], 'new-parser')
        self.assertEqual(PARSER, 'hanshu-wyg-annals-source-pages-v1')

    def test_selected_scope_still_rejects_wrong_component_volume(self):
        raw = '#+PROPERTY: BASEEDITION WYG\n#+PROPERTY: JUAN 卷五十一考證\n<pb:p>文¶\n'.encode()
        with self.assertRaises(ValueError):
            parse_file('fixture.txt', raw, allowed_volumes=range(31, 51))
