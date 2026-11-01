"""Source-character and segmentation regressions, independent of database access."""
import unittest
import json
import tempfile
from pathlib import Path

from backfill_shiji import spans, make_plan


class SpanTests(unittest.TestCase):
    def test_cross_page_notes_and_rare_characters_survive(self):
        left, depth = spans('原𠮷(古注')
        self.assertEqual(depth, 1)
        body = '續注(再注)/)原文'
        right, depth = spans(body, depth)
        self.assertEqual(depth, 0)
        self.assertEqual(''.join(body[s['start']:s['end']] for s in right), body)
        self.assertEqual(right[0]['kind'], 'source-parenthetical')
        self.assertEqual(right[-1]['kind'], 'source-text')
        self.assertEqual(left[0], {'kind': 'source-text', 'start': 0, 'end': 2})

    def test_broken_close_is_rejected_without_repair(self):
        with self.assertRaisesRegex(ValueError, 'Unmatched'):
            spans('原文)')

    def test_empty_page_inside_note_preserves_depth(self):
        self.assertEqual(spans('', 1), ([], 1))

    def test_other_commit_cannot_inherit_the_wyg_label(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'manifest.json'
            path.write_text(json.dumps({'repositories': [{'repository': 'kanripo/KR2a0002',
                            'commit': '0' * 40, 'archiveSha256': '0' * 64}]}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'locked'):
                make_plan(Path(folder), '0' * 64, path)


if __name__ == '__main__':
    unittest.main()
