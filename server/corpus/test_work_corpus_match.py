from django.test import SimpleTestCase

from .views_corpus import _corpus_search_prefix, _matching_corpus_texts


class WorkCorpusMatchTests(SimpleTestCase):
    def test_same_tune_does_not_override_matching_poem(self):
        wrong = {'body': '落日绣帘卷，亭下水连空。', 'title': '水调歌头'}
        right = {'body_simplified': '明月几时有，把酒问青天。\n不知天上宫阙。', 'title': '水调歌头'}
        self.assertEqual(_matching_corpus_texts(['明月几时有？把酒问青天。'], [wrong, right]), [right])

    def test_short_or_different_original_does_not_guess(self):
        row = {'body': '明月几时有，把酒问青天。'}
        self.assertEqual(_matching_corpus_texts(['明月几时有'], [row]), [])
        self.assertEqual(_matching_corpus_texts(['不相同的古诗词原文'], [row]), [])

    def test_alternative_title_candidates_still_require_matching_text(self):
        right = {'title': '江神子・江城子', 'body_simplified': '十年生死两茫茫。不思量。自难忘。'}
        wrong = {'title': '江城子・密州出猎', 'body_simplified': '老夫聊发少年狂，左牵黄，右擎苍。'}
        self.assertEqual(_matching_corpus_texts(['十年生死两茫茫，不思量，自难忘。'], [right, wrong]), [right])

    def test_fallback_prefix_does_not_cross_punctuation(self):
        self.assertEqual(_corpus_search_prefix(['卖炭翁，伐薪烧炭南山中。']), '伐薪烧炭')
        self.assertEqual(_corpus_search_prefix(['白发三千丈，缘愁似个长。']), '白发三千')
        self.assertEqual(_corpus_search_prefix(['山，水。']), '')

    def test_fallback_never_accepts_four_character_match_alone(self):
        original = ['白发三千丈，缘愁似个长。']
        right = {'title': '秋浦歌十七首 十五', 'body_simplified': '白发三千丈，缘愁似个长。'}
        wrong = {'title': '别篇', 'body_simplified': '白发三千年来仍有另一段内容。'}
        self.assertEqual(_matching_corpus_texts(original, [wrong, right]), [right])
