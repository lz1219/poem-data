"""固定修订、原卷题与维基原态隔离的回归检查。"""
import json
import unittest
from wikisource_source import inspect, sha, decode_capture, collection_coverage, front_matter_findings
from raw_ingest import derive


def fixture():
    text = '<!-- 吳志卷一，仅导航不能充当正文卷题 -->{{header|section=卷一}}<poem>欽定四庫全書\n蜀志卷五\n諸葛亮傳\n臣本布衣</poem>'
    raw = json.dumps({'query':{'pages':[{'pageid':12,'title':'三國志 (四庫全書本)/蜀志/卷05',
        'revisions':[{'revid':34,'timestamp':'2026-01-01T00:00:00Z','slots':{'main':{'content':text}}}]}]}},ensure_ascii=False).encode()
    meta = {'provider':'wikisource','sourceId':'wikisource-sanguozhi-siku','pageId':12,'title':'三國志 (四庫全書本)/蜀志/卷05','revisionId':34,
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
        with self.assertRaisesRegex(ValueError,'卷题|卷目'): inspect(meta, raw)

    def test_capture_and_content_hashes_are_both_required(self):
        meta, raw, _ = fixture()
        with self.assertRaisesRegex(ValueError,'响应哈希'): inspect(meta, raw + b' ')
        meta['textSha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError,'文本哈希'): inspect(meta, raw)

    def test_wiki_unit_preserves_markup_and_does_not_get_fake_git_commit(self):
        meta, _, text = fixture()
        evidence = {'quote':'臣本布衣','url':meta['permalink'],'revisionId':34,'pageId':12,'sourceId':meta['sourceId']}
        bundle = {'snapshots':[('s','wikisource/zh/page/12',None,'hash',meta)],
                  'entries':[('s','page.wiki','wikitext',sha(text),text)],
                  'records':[('r','research_revision','note',1,{'evidence':[evidence]},'note','hash')]}
        result = derive(bundle,'batch')
        self.assertEqual(result['unit'][0][5], '蜀志卷五')
        self.assertEqual(result['page'][0][5].encode(), text)
        self.assertEqual(len(result['quote_match']),1)
        evidence['revisionId'] = 35
        self.assertIn('evidence-revision-mismatch',[i[3] for i in derive(bundle,'batch')['issue']])

    def test_xml_export_selects_actual_page_and_revision(self):
        from xml.sax.saxutils import escape
        title='文忠集 (歐陽修, 四庫全書本)/卷103'
        text='<poem>欽定四庫全書\n文忠集卷一百三\n原態{{模板|字}}</poem>'
        raw=('<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/"><page><title>'+title+'</title><id>45</id><revision><id>67</id><timestamp>2026-01-01T00:00:00Z</timestamp><text>'+escape(text)+'</text></revision></page></mediawiki>').encode()
        from urllib.parse import urlencode
        meta={'sourceId':'wikisource-ouyang-wenzhong-siku','kind':'body','title':title,'pageId':45,'revisionId':67,
              'revisionTimestamp':'2026-01-01T00:00:00Z','section':'正文','juanNumber':103,'captureFormat':'mediawiki-export-xml',
              'url':'https://zh.wikisource.org/w/index.php?'+urlencode({'title':'Special:Export','pages':title,'curonly':'1'}),
              'permalink':'https://zh.wikisource.org/w/index.php?oldid=67','captureSha256':sha(raw),'textSha256':sha(text.encode())}
        self.assertEqual(decode_capture(meta,raw)['text'],text)
        self.assertEqual(inspect(meta,raw)['originalHeading'],'文忠集卷一百三')
        meta['revisionId']=68
        with self.assertRaisesRegex(ValueError,'修订'): inspect(meta,raw)
        with self.assertRaisesRegex(ValueError,'实体'): decode_capture(meta,b'<!DOCTYPE mediawiki>'+raw)

    def test_missing_ouyang_volume_does_not_disappear_from_scope(self):
        pages=[{'sourceId':'wikisource-ouyang-wenzhong-siku','kind':'contents','title':'root'}]
        pages += [{'sourceId':'wikisource-ouyang-wenzhong-siku','kind':'body','title':str(n),'section':'正文','juanNumber':n} for n in range(1,153)]
        summary=collection_coverage(pages)['wikisource-ouyang-wenzhong-siku']
        self.assertFalse(summary['selectedScopeComplete'])
        self.assertEqual(summary['expectedBodyVolumes'],153)
        self.assertEqual(summary['missing'],['正文卷153'])

    def test_front_matter_candidates_preserve_markers_and_utf8_byte_offsets(self):
        text='前言\n文忠集年譜\n年次原文cq=161不补字\n文忠集年譜\n尾'
        result=front_matter_findings({'title':'book','revisionId':1},text)
        part=result['sectionCandidates'][0];raw=text.encode()[part['startByte']:part['endByte']]
        self.assertEqual(sha(raw),part['sha256'])
        self.assertIn(b'cq=161',raw)
        self.assertEqual(result['markerCandidates'][0]['marker'],'cq=161')


class WikiReadingTests(unittest.TestCase):
    def wrapped(self, body):
        return '{{header\n| title = 原书\n}}\n\n' + body + '\n\n==註釋==\n{{reflist}}'

    def test_heading_reference_and_main_references_keep_utf8_locations(self):
        from wikisource_source import reading_paragraphs
        raw = self.wrapped('==題<ref>題注</ref>==\n𠮷<u>原</u><ref>注[[卷|名]]</ref>文。')
        heading, paragraph = reading_paragraphs(raw)
        self.assertEqual(heading['body'], '題')
        self.assertEqual(heading['origin']['kind'], 'heading')
        self.assertEqual(paragraph['body'], '𠮷原文。')
        self.assertEqual(paragraph['origin']['annotations'][0]['anchor'], 2)
        for p in (heading, paragraph):
            note = p['origin']['annotations'][0]
            captured = raw.encode()[note['sourceByteStart']:note['sourceByteEnd']].decode()
            self.assertTrue(captured.startswith('<ref>') and captured.endswith('</ref>'))

    def test_notes_are_not_silently_discarded_or_reattributed(self):
        from wikisource_source import reading_paragraphs
        p, = reading_paragraphs(self.wrapped('原<ref>注\n</br>保留注的後行</ref>文。'))
        self.assertEqual(p['body'], '原文。')
        note, = p['origin']['annotations']
        self.assertIn('保留注的後行', note['body'])
        self.assertEqual(note['attribution'], '维基编者注·注者待核')

    def test_unknown_markup_and_unclosed_note_refuse_import(self):
        from wikisource_source import reading_paragraphs
        for body in ('原{{未知模板}}文', '原<ref>未闭合', '原<span>未支持标签</span>'):
            with self.assertRaises(ValueError):
                reading_paragraphs(self.wrapped(body))

    def test_literal_source_error_is_preserved_and_heading_marks_removed(self):
        from wikisource_source import reading_paragraphs
        title, body = reading_paragraphs(self.wrapped('===201===\n<<u>有苗</u>來格，-{云}-。'))
        self.assertEqual(title['body'], '201')
        self.assertEqual(body['body'], '<有苗來格，云。')


class ChronicleReadingTests(unittest.TestCase):
    def wrapped(self, body):
        return '{{header2\n|title=資治通鑑\n}}\n\n' + body + '\n\n==校刊記==\n<div class="references-small"><references /></div>\n[[category:資治通鑑|周]]\n{{北宋作品}}'

    def test_year_headings_event_reset_and_editorial_note_all_survive(self):
        from wikisource_source import chronicle_paragraphs
        raw = self.wrapped('== 安王 ==\n\n=== 安王元年 ===\n\n\'\'\'1\'\'\'　𠮷原<ref>增補[[史記|據文]]</ref>文。\n\n=== 安王二年 ===\n\n\'\'\'1\'\'\'　次年事。')
        blocks = chronicle_paragraphs(raw)
        self.assertEqual([b['body'] for b in blocks], ['安王','安王元年','1　𠮷原文。','安王二年','1　次年事。'])
        self.assertEqual(blocks[-1]['origin']['headingPath'][-1]['title'],'安王二年')
        self.assertEqual(blocks[-1]['origin']['eventNumber'],'1')
        note = blocks[2]['origin']['annotations'][0]
        self.assertEqual(note['anchor'],4)
        self.assertEqual(raw.encode()[note['sourceByteStart']:note['sourceByteEnd']].decode(),'<ref>增補[[史記|據文]]</ref>')

    def test_year_template_is_displayed_without_dating_inference(self):
        from wikisource_source import chronicle_paragraphs
        p, = chronicle_paragraphs(self.wrapped('==顯王元年{{*|癸-{丑}-，西元前三六八年}}=='))
        self.assertEqual(p['body'],'顯王元年（癸丑，西元前三六八年）')
        self.assertNotIn('year',p['origin'])
        self.assertEqual(p['origin']['headingLevel'],2)

    def test_unknown_table_template_and_trailer_are_not_silently_removed(self):
        from wikisource_source import chronicle_paragraphs
        for body in ['原{{不明|字}}文','{|\n| 年 || 事\n|}', '原<ref>未閉合']:
            with self.assertRaises(ValueError): chronicle_paragraphs(self.wrapped(body))
        with self.assertRaises(ValueError): chronicle_paragraphs(self.wrapped('正文。')+'\n失落的附記')


if __name__ == '__main__': unittest.main()
