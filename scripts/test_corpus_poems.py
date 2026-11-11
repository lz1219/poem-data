"""No loss of source fields, Unicode positions or distinct source records."""
import copy
import unittest
from unittest.mock import patch

from corpus_poems import parse_records
import corpus_poems


class PoetrySourceTests(unittest.TestCase):
    def test_exact_records_combine_locations_without_dropping_source_fields(self):
        source = {'author': '原作者', 'rhythmic': '原词牌', 'paragraphs': ['𠮷原文', '第二行'],
                  'tags': ['标签待核'], 'prologue': '序文待核'}
        before = copy.deepcopy(source)
        seen = {}
        first = parse_records([source], {'path': 'first.json'}, seen)
        self.assertEqual(parse_records([source], {'path': 'second.json'}, seen), [])
        self.assertEqual(source, before)
        self.assertEqual(first[0]['origin']['locations'], [
            {'path': 'first.json', 'jsonPointer': '/0'}, {'path': 'second.json', 'jsonPointer': '/0'}])
        self.assertEqual(first[0]['origin']['prologue'], '序文待核')
        self.assertEqual(first[0]['origin']['tags'], ['标签待核'])
        self.assertEqual([first[0]['body'][p['start']:p['end']] for p in first[0]['origin']['paragraphs']], source['paragraphs'])

    def test_same_body_with_different_author_or_notes_remains_distinct(self):
        record = {'author': '甲', 'rhythmic': '词牌', 'paragraphs': ['同文']}
        records = [record, {**record, 'author': '乙'}, {**record, 'prologue': '异序'}]
        self.assertEqual(len(parse_records(records, {'path': 'file'}, {})), 3)

    def test_replacement_characters_remain_in_raw_text_with_unicode_locations(self):
        poem, = parse_records([{'author': '甲', 'rhythmic': '词牌', 'paragraphs': ['𠮷\ufffd原文']}], {}, {})
        self.assertEqual(poem['body'], '𠮷\ufffd原文')
        self.assertEqual(poem['origin']['unresolvedReplacementOffsets'], [1])

    def test_invalid_records_fail_instead_of_dropping_unknown_fields(self):
        good = {'author': '甲', 'rhythmic': '词牌', 'paragraphs': ['文']}
        for record in (None, {**good, 'unknown': 'value'}, {**good, 'paragraphs': []},
                       {**good, 'tags': 'not a list'}, {**good, 'prologue': None}):
            with self.assertRaises(ValueError):
                parse_records([record], {}, {})

    def test_large_source_verification_bounds_each_result_and_checks_last_record(self):
        poems = [{'author': '作者', 'title': '词牌', 'body': str(i), 'ext_id': str(i), 'origin': {}}
                 for i in range(300)]
        plan = {'batchId': 'batch', 'manifest': {'counts': {'poems': 300}}, 'poems': poems}
        result = {'newFingerprints': {}}

        class ReadLimitConnection:
            def __init__(self, change_last=False):
                self.ranges = []
                self.change_last = change_last

            def execute(self, query, params):
                if query.startswith('SELECT count(*)'):
                    self.rows = [(300,)]
                else:
                    if len(params) != 3 or params[2] - params[1] > 128:
                        raise TimeoutError('oversized source-result transfer')
                    self.ranges.append((params[1], params[2]))
                    self.rows = [(p['author'], p['title'], p['body'], p['ext_id'], p['origin'])
                                 for p in poems[params[1]:params[2]]]
                    if self.change_last and params[2] == 300:
                        self.rows[-1] = ('changed', *self.rows[-1][1:])
                return self

            def fetchone(self):
                return self.rows[0]

            def fetchall(self):
                return self.rows

        with patch.object(corpus_poems, 'batch', return_value=(plan['manifest'], result, 'applied')), \
             patch.object(corpus_poems, 'new_fingerprints', return_value={}):
            connection = ReadLimitConnection()
            self.assertEqual(corpus_poems.verify(connection, plan)['sourceRoundTrip'], 'passed')
            self.assertEqual(sum(b - a for a, b in connection.ranges), 300)
            with self.assertRaisesRegex(ValueError, 'differ from fixed files'):
                corpus_poems.verify(ReadLimitConnection(change_last=True), plan)


if __name__ == '__main__':
    unittest.main()
