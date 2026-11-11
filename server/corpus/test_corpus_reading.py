"""Reading compatibility does not require a configured PostgreSQL corpus."""
from unittest.mock import patch
import copy
import hashlib

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from . import views, views_corpus, corpus_origins
from . import reading


class CorpusReadingCompatibilityTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_legacy_poem_without_new_provenance_table_keeps_old_response(self):
        poem = {'id': 1, 'body': '原文', 'author': '旧作者'}
        with patch.object(views_corpus.db, 'available', return_value=True), \
             patch.object(views_corpus.db, 'one', side_effect=[poem, {'ok': False}]):
            result = views_corpus.poem_detail(self.factory.get('/api/corpus/poems/1'), 1)
        self.assertEqual(result.data, poem)
        self.assertNotIn('origin', result.data)

    def test_poetry_book_is_paginated_and_percent_query_stays_literal(self):
        book = {'id': 53, 'title': '全宋词'}
        poem = {'id': 99, 'author': '作者', 'title': '词牌', 'head': '正文'}
        with patch.object(views_corpus.db, 'available', return_value=True), \
             patch.object(corpus_origins, 'attach_book'), \
             patch.object(views_corpus.db, 'one', side_effect=[book, {'c': 21046}]), \
             patch.object(views_corpus.db, 'query', side_effect=[[], [poem]]) as query:
            result = views_corpus.book_detail(self.factory.get('/api/texts/53', {
                'q': '%', 'limit': '1000', 'offset': '50'}), 53)
        self.assertEqual(result.data['juan'], [])
        self.assertEqual(result.data['total'], 0)
        self.assertEqual(result.data['poems'], [poem])
        self.assertEqual(result.data['poemLimit'], 200)
        self.assertEqual(result.data['poemOffset'], 50)
        self.assertEqual(query.call_args.args[1], (53, '%', ['%'], 200, 50))
        self.assertNotIn('LIKE', query.call_args.args[0])

    def test_bad_poetry_pagination_is_client_error(self):
        with patch.object(views_corpus.db, 'available', return_value=True), \
             patch.object(corpus_origins, 'attach_book'), \
             patch.object(views_corpus.db, 'one', return_value={'id': 53}), \
             patch.object(views_corpus.db, 'query', return_value=[]):
            result = views_corpus.book_detail(self.factory.get('/api/texts/53', {'offset': 'oops'}), 53)
        self.assertEqual(result.status_code, 400)

    def test_old_book_without_origin_tables_remains_readable(self):
        book = {'id': 7, 'title': '旧书目', 'edition': None, 'source_url': None}
        units = [{'id': 4, 'juan': '一', 'title': '卷一', 'chars': 2, 'punctuated': False}]
        with patch.object(views_corpus.db, 'available', return_value=True), \
             patch.object(views_corpus.db, 'one', side_effect=[book, {'ok': False}]), \
             patch.object(views_corpus.db, 'query', return_value=units):
            result = views_corpus.book_detail(self.factory.get('/api/texts/7'), 7)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data, {'book': book, 'total': 1, 'juan': units})
        self.assertNotIn('corpusEditions', result.data['book'])

    def test_old_unit_keeps_paragraphs_without_origin_tables(self):
        unit = {'id': 4, 'body': '原文', 'title': '卷一'}
        paragraphs = [{'id': 9, 'seq': 1, 'body': '原文'}]
        with patch.object(views_corpus.db, 'available', return_value=True), \
             patch.object(views_corpus.db, 'one', side_effect=[unit, {'ok': False}]), \
             patch.object(views_corpus.db, 'query', return_value=paragraphs):
            result = views_corpus.juan_detail(self.factory.get('/api/texts/juan/4'), 4)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['paragraphs'], paragraphs)
        self.assertNotIn('origin', result.data)

    def test_missing_corpus_is_not_an_empty_successful_text_search(self):
        with patch.object(views_corpus.db, 'available', return_value=False):
            result = views.search(self.factory.get('/api/search', {'scope': 'text', 'q': '史记'}))
        self.assertEqual(result.status_code, 503)

    def test_invalid_search_numbers_are_a_client_error(self):
        for params in ({'limit': 'bad'}, {'book_id': 'bad'}):
            result = views.search(self.factory.get('/api/search', {'scope': 'text', 'q': '史记', **params}))
            self.assertEqual(result.status_code, 400)

    def test_same_edition_keeps_two_distinct_batch_scopes(self):
        book = {'id': 8}
        batches = [{'batch_id': 'a', 'edition_id': 9, 'name': '颜注本', 'provenance': {'coverage': '本纪'}},
                   {'batch_id': 'b', 'edition_id': 9, 'name': '颜注本', 'provenance': {'coverage': '列传'}}]
        with patch.object(corpus_origins, 'available', return_value=True), \
             patch.object(corpus_origins.db, 'query', side_effect=[batches, []]):
            corpus_origins.attach_book(book, [])
        self.assertEqual(len(book['corpusEditions']), 1)
        self.assertEqual(book['corpusBatches'], batches)
        self.assertEqual(book['corpusEditions'][0]['batches'], batches)
        self.assertEqual(book['corpusEditions'][0]['provenance'], {'coverage': '本纪'})

    def test_appended_front_matter_and_split_components_follow_source_order(self):
        units = [{'id': i} for i in (1, 2, 9, 10)]
        origins = [{'unit_id': i, 'edition_id': 9, 'metadata': {'sourcePath': path, 'sourceByteStart': start}}
                   for i, path, start in [(1, 'KR_002.txt', 0), (2, 'KR_001.txt', 0),
                                           (9, 'KR_000.txt', 100), (10, 'KR_000.txt', 0)]]
        with patch.object(corpus_origins, 'available', return_value=True), \
             patch.object(corpus_origins.db, 'query', side_effect=[[], origins]):
            corpus_origins.attach_book({'id': 8}, units)
        self.assertEqual([u['id'] for u in units], [10, 9, 2, 1])

    def test_explicit_upper_middle_lower_order_precedes_title_collation(self):
        units = [{'id': i} for i in (1, 3, 2)]
        origins = [{'unit_id': i, 'edition_id': 10, 'metadata': {'sourcePath': '傳習錄/' + title,
                    'sourceByteStart': 0, 'sourceOrder': order}}
                   for i, title, order in [(1, '卷上', 1), (2, '卷中', 2), (3, '卷下', 3)]]
        with patch.object(corpus_origins, 'available', return_value=True), \
             patch.object(corpus_origins.db, 'query', side_effect=[[], origins]):
            corpus_origins.attach_book({'id': 20}, units)
        self.assertEqual([u['id'] for u in units], [1, 2, 3])


class CorpusReadingViewTests(SimpleTestCase):
    def setUp(self):
        reading._page.cache_clear()

    def test_conversion_and_page_reflow_leave_original_and_offsets_unchanged(self):
        raw = '陳勝\n(古/注)𠮷&KR0912;'
        spans = [{'kind': 'source-text', 'start': 0, 'end': 3},
                 {'kind': 'source-parenthetical', 'start': 3, 'end': 8},
                 {'kind': 'source-text', 'start': 8, 'end': len(raw)}]
        pages = [{'id': 3, 'seq': 1, 'body': raw,
                  'origin': {'segmentation': 'source-page', 'pageLabel': 'source-1a', 'spans': spans}}]
        before = copy.deepcopy(pages)
        unit = {'body': raw}
        reading.attach_reading(unit, pages)
        self.assertEqual(pages, before)
        self.assertEqual(unit['body'], raw)
        self.assertEqual(unit['reading']['originalSha256'], hashlib.sha256(raw.encode()).hexdigest())
        segments = unit['reading']['pages'][0]['segments']
        self.assertEqual(segments[0]['simplified'], '陈胜')
        self.assertEqual(segments[1], {'kind': 'parenthetical', 'original': '(古注)', 'simplified': '(古注)'})
        self.assertIn('&KR0912;', segments[2]['simplified'])

    def test_legacy_paragraphs_keep_line_breaks_and_slashes(self):
        raw = '原文\n次行/正文'
        unit = {'body': raw}
        reading.attach_reading(unit, [{'body': raw, 'seq': 1}])
        self.assertEqual(unit['reading']['pages'][0]['segments'][0]['original'], raw)
        self.assertFalse(unit['reading']['pages'][0]['sourcePage'])

    def test_source_heading_and_event_context_are_exposed_without_guessing_years(self):
        paragraphs = [{'id': 1, 'body': '安王元年', 'origin': {'kind': 'heading', 'headingLevel': 3}},
                      {'id': 2, 'body': '1　原文。', 'origin': {'eventNumber': '1',
                       'headingPath': [{'level': 3, 'title': '安王元年'}]}}]
        unit = {'body': '安王元年\n\n1　原文。'}
        before = copy.deepcopy(paragraphs)
        reading.attach_reading(unit, paragraphs)
        heading, event = unit['reading']['pages']
        self.assertEqual((heading['kind'], heading['headingLevel']), ('heading', 3))
        self.assertEqual(event['eventNumber'], '1')
        self.assertEqual(event['headingPath'][0]['title'], '安王元年')
        self.assertNotIn('year', event)
        self.assertEqual(paragraphs, before)

    def test_invalid_spans_fall_back_to_complete_text(self):
        unit = {'body': '𠮷原文'}
        reading.attach_reading(unit, [{'body': unit['body'], 'origin': {'spans': [
            {'kind': 'source-text', 'start': 1, 'end': 3}]}}])
        self.assertEqual(unit['reading']['pages'][0]['segments'][0]['original'], '𠮷原文')

    def test_empty_page_does_not_invent_reading_text(self):
        unit = {'body': ''}
        reading.attach_reading(unit, [{'body': '', 'seq': 4, 'origin': {'segmentation': 'source-page'}}])
        self.assertEqual(unit['reading']['pages'][0]['segments'], [])
        self.assertEqual(unit['reading']['pages'][0]['seq'], 4)

    def test_optional_converter_unavailable_is_explicit(self):
        with patch.object(reading, 'converter', return_value=(None, None)):
            unit = {'body': '未配置的原字'}
            reading.attach_reading(unit, [])
        self.assertFalse(unit['reading']['simplifiedAvailable'])
        self.assertEqual(unit['reading']['pages'][0]['segments'][0]['original'], unit['body'])
        self.assertIsNone(unit['reading']['pages'][0]['segments'][0]['simplified'])

    def test_search_queries_keep_literal_input_and_both_character_forms(self):
        self.assertEqual(reading.query_forms('%'), ['%'])
        self.assertEqual(set(reading.query_forms('陈胜')), {'陈胜', '陳勝'})

    def test_editorial_notes_keep_main_text_and_unicode_anchors_separate(self):
        unit = {'body': '𠮷原文'}
        paragraph = {'body': unit['body'], 'origin': {'segmentation': 'source-paragraph',
            'annotations': [{'anchor': 1, 'body': '注中繁體'}, {'anchor': 3, 'body': '末注'}]}}
        before = copy.deepcopy(paragraph)
        reading.attach_reading(unit, [paragraph])
        parts = unit['reading']['pages'][0]['segments']
        self.assertEqual(''.join(s['original'] for s in parts if s['kind'] == 'text'), unit['body'])
        notes = [s for s in parts if s['kind'] == 'parenthetical']
        self.assertEqual(len(notes), 2)
        self.assertIn('维基编者注·注者待核', notes[0]['original'])
        self.assertIn('注中繁体', notes[0]['simplified'])
        self.assertEqual(paragraph, before)

    def test_editorial_note_outside_main_text_is_rejected(self):
        with self.assertRaises(ValueError):
            reading.attach_reading({'body': '原文'}, [{'body': '原文', 'origin': {
                'annotations': [{'anchor': 3, 'body': '注'}]}}])


class RetiredImporterTests(SimpleTestCase):
    def test_legacy_wiki_command_cannot_write_even_without_dry_run(self):
        from django.core.management import call_command, CommandError
        with patch.object(views_corpus.db, 'execute') as execute:
            with self.assertRaisesMessage(CommandError, '旧维基导入器已停用'):
                call_command('import_wikisource', page='資治通鑑', book='資治通鑑')
            execute.assert_not_called()

    def test_txt_command_defaults_to_preview(self):
        import io
        import tempfile
        from pathlib import Path
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.txt'
            source.write_text('\u3000卷一\n原文。\n', encoding='utf-8')
            output = io.StringIO()
            with patch.object(views_corpus.db, 'execute') as execute:
                call_command('import_daizhige', file=str(source), book='原书', stdout=output)
                execute.assert_not_called()
            self.assertIn('仅预览，未写入数据库', output.getvalue())
