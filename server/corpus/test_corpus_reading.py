"""Reading compatibility does not require a configured PostgreSQL corpus."""
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from . import views, views_corpus


class CorpusReadingCompatibilityTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

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
