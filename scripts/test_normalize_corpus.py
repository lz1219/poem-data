import unittest

from normalize_corpus import chinese_number, source_titles


class ReadingNamesTests(unittest.TestCase):
    def test_volume_numbers_and_chapter_are_from_actual_heading(self):
        source = {'juan': 'KR2b0007_001', 'body': '欽定四庫全書 資治通鑑巻一 宋司馬光撰 胡三省音注 周紀一'}
        self.assertEqual(source_titles([source]), {1: '卷一 · 周紀一'})
        self.assertEqual(chinese_number('二百九十四'), 294)

    def test_inconsistent_old_heading_cannot_become_a_new_volume_title(self):
        warnings = []
        source = {'juan': 'KR2b0007_158', 'body': '資治通鑑卷一百五十 梁紀十四'}
        self.assertEqual(source_titles([source], warnings), {})
        self.assertEqual(warnings[0]['filename'], 'KR2b0007_158')

    def test_front_matter_does_not_supply_another_volume_heading(self):
        self.assertEqual(source_titles([{'juan': 'KR2b0007_000',
            'body': '資治通鑑 提要 引用資治通鑑卷一'}]), {})


if __name__ == '__main__':
    unittest.main()
