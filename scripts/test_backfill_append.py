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

    def test_split_middle_volume_keeps_its_identity(self):
        raw = '#+PROPERTY: BASEEDITION WYG\n#+PROPERTY: JUAN 卷二十七中之上\n<pb:p>原文(古注)𠮷¶\n'.encode()
        unit = parse_file('fixture.txt', raw, allowed_volumes=range(21, 31))[0]
        self.assertEqual((unit['juan'], unit['origin']['volumeNumber']), ('卷二十七中之上', 27))
        self.assertEqual(unit['body'], '原文(古注)𠮷')

    def test_named_front_and_back_require_explicit_scope_and_keep_catalog_tail(self):
        raw = ('#+PROPERTY: BASEEDITION WYG\n#+PROPERTY: JUAN [提要]\n<pb:a>傳第七十下\n敘傳\n提要原字¶\n'
               '#+PROPERTY: JUAN [考證跋語]\n<pb:b>侍讀(臣召南/)謹言¶\n').encode()
        with self.assertRaises(ValueError):
            parse_file('fixture.txt', raw)
        front, back = parse_file('fixture.txt', raw, named_components=('[提要]', '[考證跋語]'))
        self.assertEqual(front['origin']['kind'], 'front-matter')
        self.assertEqual(front['body'], '傳第七十下\n敘傳\n提要原字')
        self.assertIn('目录尾文', front['origin']['boundaryNote'])
        self.assertEqual(back['origin']['kind'], 'back-matter')
