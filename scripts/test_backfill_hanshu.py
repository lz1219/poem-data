"""Guards against silently merging edition components or repairing source text."""
import json
import tempfile
import unittest
from pathlib import Path

from backfill_hanshu import make_plan, parse_file


def source(parts, base='WYG'):
    return ('#+PROPERTY: BASEEDITION ' + base + '\n' + ''.join(
        '#+PROPERTY: JUAN ' + title + '\n' + body for title, body in parts)).encode()


class HanshuSourceTests(unittest.TestCase):
    def test_annals_and_examination_remain_distinct_with_exact_ranges(self):
        raw = source([('卷一上', '<pb:A-1a>班𠮷(注/文)¶\n<pb:A-1b>¶\n'),
                      ('卷一上考證', '<pb:A-2a>考證&KR0912;  原錄¶\n')])
        annals, examination = parse_file('fixture.txt', raw)
        self.assertEqual(annals['origin']['kind'], 'body-volume')
        self.assertEqual(examination['origin']['kind'], 'edition-examination')
        self.assertEqual(annals['body'], '班𠮷(注/文)\n\n')
        self.assertEqual(examination['body'], '考證&KR0912;  原錄')
        self.assertEqual(examination['origin']['unresolvedGlyphTokens'], ['&KR0912;'])
        page = examination['paragraphs'][0]['origin']
        self.assertEqual(raw[page['sourceByteStart']:page['sourceByteEnd']].decode(), '<pb:A-2a>考證&KR0912;  原錄¶\n')
        self.assertEqual(annals['origin']['sourceByteEnd'], examination['origin']['sourceByteStart'])
        self.assertTrue(annals['paragraphs'][1]['origin']['emptyTranscription'])

    def test_brackets_may_cross_a_page_but_not_an_edition_component(self):
        raw = source([('卷二', '<pb:A>原(注¶\n<pb:B>續)原¶\n')])
        unit = parse_file('fixture.txt', raw)[0]
        self.assertEqual(unit['paragraphs'][1]['origin']['spans'][0]['kind'], 'source-parenthetical')
        raw = source([('卷二', '<pb:A>原(注¶\n'), ('卷二考證', '<pb:B>續)¶\n')])
        with self.assertRaisesRegex(ValueError, 'Unclosed'):
            parse_file('fixture.txt', raw)

    def test_table_volume_wrong_edition_or_unlocated_text_is_rejected(self):
        for raw in [source([('卷十三', '<pb:A>表¶\n')]),
                    source([('卷二', '<pb:A>文¶\n')], 'TLS'),
                    source([('卷二', '無頁定位原文\n<pb:A>文¶\n')])]:
            with self.assertRaises(ValueError):
                parse_file('fixture.txt', raw)

    def test_other_commit_cannot_inherit_hanshu_edition_label(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'manifest.json'
            path.write_text(json.dumps({'repositories': [{'repository': 'kanripo/KR2a0007',
                            'commit': '0' * 40, 'archiveSha256': '0' * 64}]}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'locked'):
                make_plan(Path(folder), '0' * 64, path)


if __name__ == '__main__':
    unittest.main()
