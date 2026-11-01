"""原页范围和研究证据隔离的回归检查；无需数据库或网络。"""
import unittest
from raw_ingest import source_unit, derive, sha, record_identity


class SourcePagesTests(unittest.TestCase):
    def test_byte_offsets_survive_bom_multibyte_and_hard_wraps(self):
        raw = ('\ufeff#+TITLE: 測試\n#+PROPERTY: BASEEDITION WYG\n#+PROPERTY: JUAN 卷一\n'
               '<pb:BOOK_001-1a>¶江頭\n送客¶\n<pb:BOOK_001-1b>秋風\n').encode('utf-8')
        meta, pages = source_unit(raw, 'BOOK_001.txt')
        self.assertEqual(meta['kind'], 'body')
        self.assertEqual(len(pages), 3)
        self.assertEqual(b''.join(p[4].encode('utf-8') for p in pages), raw)
        for _, locator, start, end, text, digest in pages:
            self.assertEqual(raw[start:end], text.encode('utf-8'))
            self.assertEqual(digest, sha(raw[start:end]))
        self.assertIn('江頭\n送客¶', pages[1][4])

    def test_numeric_juan_is_preserved_without_inventing_page(self):
        raw = '#+TITLE: 集\n#+PROPERTY: JUAN 72\n正文'.encode('utf-8')
        meta, pages = source_unit(raw, 'BOOK_072.txt')
        self.assertEqual(meta['kind'], 'unclassified')
        self.assertIsNone(meta['juan'])
        self.assertEqual(meta['juanHeader'], '72')
        self.assertIsNone(meta['base'])
        self.assertEqual(pages[0][4].encode('utf-8'), raw)
        missing, _ = source_unit(b'#+TITLE: Book\n', 'BOOK_001.txt')
        self.assertEqual(missing['kind'], 'unclassified')

    def test_front_and_back_matter_are_not_counted_as_body(self):
        front, _ = source_unit(b'#+TITLE: Book\n', 'BOOK_000.txt')
        back, _ = source_unit('#+PROPERTY: JUAN 跋\n'.encode(), 'BOOK_002.txt')
        self.assertEqual(front['kind'], 'front_matter')
        self.assertEqual(back['kind'], 'back_matter')

    def test_quote_requires_exact_raw_bytes_and_keeps_ai_revision(self):
        raw = '#+TITLE: 集\n#+PROPERTY: BASEEDITION WYG\n<pb:b>江頭\n送客'.encode()
        commit = 'a' * 40
        url = f'https://github.com/kanripo/KR4c0012/blob/{commit}/KR4c0012_001.txt'
        subject = {'id': 'ai-note', 'revision': 1, 'subject': {'type': 'work', 'key': 'w'},
                   'provenance': {'origin': 'ai'}, 'evidence': [{'url': url, 'quote': '江頭\n送客'}]}
        bundle = {'snapshots': [('s', 'kanripo/KR4c0012', commit, 'archive', {})],
                  'entries': [('s', 'KR4c0012_001.txt', 'text', sha(raw), raw)],
                  'records': [('r', 'research_revision', 'ai-note', 1, subject, 'note.json', 'hash')]}
        result = derive(bundle, 'batch')
        self.assertEqual(len(result['quote_match']), 1)
        self.assertEqual(subject['provenance']['origin'], 'ai')
        subject['evidence'][0]['quote'] = '江頭送客'
        result = derive(bundle, 'batch')
        self.assertEqual(result['quote_match'], [])
        self.assertIn('quote-not-exact', [i[3] for i in result['issue']])

    def test_invalid_utf8_is_rejected_instead_of_replaced(self):
        with self.assertRaises(UnicodeDecodeError): source_unit(b'\xff', 'BOOK_001.txt')

    def test_unchanged_stop_in_changed_parent_gets_new_source_identity(self):
        payload = {'seq': 1, 'year': 1082}
        before = record_identity('stop', 'sushi:1', 0, payload, 'journey.json#/stops/1', 'old-parent-sha')
        after = record_identity('stop', 'sushi:1', 0, payload, 'journey.json#/stops/1', 'new-parent-sha')
        self.assertNotEqual(before, after)
        self.assertEqual(before, record_identity('stop', 'sushi:1', 0, payload, 'journey.json#/stops/1', 'old-parent-sha'))

    def test_unsupported_and_malformed_locations_are_not_silently_skipped(self):
        doc = {'evidence': [{'quote': '一', 'url': 'https://github.com/kanripo/KR4c0012/blob/bad/file.txt'},
                            {'quote': '二', 'source': '待核文献'}]}
        bundle = {'snapshots': [], 'entries': [], 'records': [('r', 'research_revision', 'note', 1, doc, 'note.json', 'hash')]}
        issues = derive(bundle, 'batch')['issue']
        self.assertEqual({i[3] for i in issues}, {'invalid-evidence-url', 'unsupported-evidence-location'})
        self.assertEqual({i[4]['index'] for i in issues}, {0, 1})

    def test_reordered_index_cannot_replace_original_juan(self):
        raw = ('#+TITLE: 王文成公全書\n#+PROPERTY: BASEEDITION SBCK\n'
               '#+PROPERTY: JUAN 1\n#+PROPERTY: FILE SB04-037全書世德紀-卷第三十七.\n'
               '<pb:book>王文成公全書卷之三十七¶\n附錄(六)世德紀¶').encode()
        meta, _ = source_unit(raw, 'BOOK_001.txt')
        self.assertEqual(meta['juanHeader'], '1')
        self.assertEqual(meta['juan'], '卷第三十七')
        self.assertEqual(meta['kind'], 'back_matter')


if __name__ == '__main__': unittest.main()
