"""Regression cases for source loss and false completeness in the preview."""
import unittest

from corpus_preview import chinese_number, inspect_file, visible_text


class PreviewTests(unittest.TestCase):
    def test_front_components_are_separate_units(self):
        raw = ('#+PROPERTY: JUAN 提要\n<pb:book_000-1a>¶\n提要¶\n'
               '#+PROPERTY: JUAN 序\n<pb:book_000-2a>¶\n序¶\n').encode()
        units = inspect_file('book_000.txt', raw)
        self.assertEqual([u['juan'] for u in units], ['提要', '序'])
        self.assertTrue(all(u['volumeNumber'] is None for u in units))
        self.assertEqual(raw[units[1]['sourceByteStart']:units[1]['sourceByteEnd']].decode(),
                         '#+PROPERTY: JUAN 序\n<pb:book_000-2a>¶\n序¶\n')

    def test_empty_pages_and_broken_notes_are_visible(self):
        raw = ('#+PROPERTY: JUAN 卷十九\n<pb:x-1a>¶\n原字𠮷(古注¶\n'
               '<pb:x-1b>¶\n續注)多一括號)¶\n<pb:x-2a>¶\n¶\n').encode()
        unit, = inspect_file('book_019.txt', raw)
        self.assertEqual(unit['volumeNumber'], 19)
        self.assertEqual(unit['emptySourcePageLabels'], ['x-2a'])
        self.assertEqual(unit['parenthesisAudit']['pagesStartingInsideParentheses'], 1)
        self.assertEqual(unit['parenthesisAudit']['unexpectedClosingPages'], ['x-1b'])
        self.assertIn('𠮷(古注', unit['openingLines'][0])

    def test_missing_page_location_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unlocated'):
            inspect_file('book_001.txt', '#+PROPERTY: JUAN 卷一\n未定位正文'.encode())

    def test_original_notation_is_not_silently_rewritten(self):
        self.assertEqual(visible_text('<pb:x>¶\n#正文𠮷(古/注)¶'), '#正文𠮷(古/注)')
        self.assertEqual(chinese_number('一百三十'), 130)
        with self.assertRaises(ValueError):
            chinese_number('上')


if __name__ == '__main__':
    unittest.main()
