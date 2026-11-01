"""固定修订、原卷题与维基原态隔离的回归检查。"""
import json
import unittest
from wikisource_source import inspect, sha
from raw_ingest import derive


def fixture():
    text = '<!-- 吳志卷一，仅导航不能充当正文卷题 -->{{header|section=卷一}}<poem>欽定四庫全書\n蜀志卷五\n諸葛亮傳\n臣本布衣</poem>'
    raw = json.dumps({'query':{'pages':[{'pageid':12,'title':'三國志/蜀志/卷05',
        'revisions':[{'revid':34,'timestamp':'2026-01-01T00:00:00Z','slots':{'main':{'content':text}}}]}]}},ensure_ascii=False).encode()
    meta = {'provider':'wikisource','sourceId':'wiki','pageId':12,'title':'三國志/蜀志/卷05','revisionId':34,
            'revisionTimestamp':'2026-01-01T00:00:00Z','url':'https://zh.wikisource.org/w/api.php?revids=34',
            'permalink':'https://zh.wikisource.org/w/index.php?oldid=34','captureSha256':sha(raw),
            'textSha256':sha(text.encode()),'kind':'body','section':'蜀志','juanNumber':5,'originalHeading':'蜀志卷五'}
    return meta, raw, text.encode()


class WikiSourcesTests(unittest.TestCase):
    def test_fixed_revision_and_actual_body_heading(self):
        meta, raw, _ = fixture()
        self.assertEqual(inspect(meta, raw)['originalHeading'], '蜀志卷五')

    def test_current_title_lookup_cannot_stand_in_for_fixed_revision(self):
        meta, raw, _ = fixture()
        meta['url'] = 'https://zh.wikisource.org/w/api.php?titles=some-title'
        with self.assertRaisesRegex(ValueError,'固定修订'): inspect(meta, raw)

    def test_wrong_revision_or_wrong_volume_is_rejected(self):
        meta, raw, _ = fixture()
        meta['revisionId'] = 35
        with self.assertRaisesRegex(ValueError,'修订'): inspect(meta, raw)
        meta, raw, _ = fixture()
        meta['juanNumber'] = 6
        with self.assertRaisesRegex(ValueError,'卷题'): inspect(meta, raw)

    def test_capture_and_content_hashes_are_both_required(self):
        meta, raw, _ = fixture()
        with self.assertRaisesRegex(ValueError,'响应哈希'): inspect(meta, raw + b' ')
        meta['textSha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError,'文本哈希'): inspect(meta, raw)

    def test_wiki_unit_preserves_markup_and_does_not_get_fake_git_commit(self):
        meta, _, text = fixture()
        evidence = {'quote':'臣本布衣','url':meta['permalink'],'revisionId':34,'pageId':12,'sourceId':'wiki'}
        bundle = {'snapshots':[('s','wikisource/zh/page/12',None,'hash',meta)],
                  'entries':[('s','page.wiki','wikitext',sha(text),text)],
                  'records':[('r','research_revision','note',1,{'evidence':[evidence]},'note','hash')]}
        result = derive(bundle,'batch')
        self.assertEqual(result['unit'][0][5], '蜀志卷五')
        self.assertEqual(result['page'][0][5].encode(), text)
        self.assertEqual(len(result['quote_match']),1)
        evidence['revisionId'] = 35
        self.assertIn('evidence-revision-mismatch',[i[3] for i in derive(bundle,'batch')['issue']])


if __name__ == '__main__': unittest.main()
