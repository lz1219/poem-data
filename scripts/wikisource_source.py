"""核目录与逐卷原题，不把URL存在当正文完整。"""
import json
import re
import hashlib
from urllib.parse import urlparse, parse_qs
from research import ROOT, read, dump, now


def sha(raw): return hashlib.sha256(raw).hexdigest()


def chinese(n):
    if n < 10: return '一二三四五六七八九'[n - 1]
    if n == 10: return '十'
    if n < 20: return '十' + chinese(n - 10)
    if n == 20: return '二十'
    raise ValueError('此批只核1到20卷')


def inspect(meta, raw):
    if sha(raw) != meta['captureSha256']: raise ValueError('固定响应哈希错误')
    doc = json.loads(raw)
    page = doc['query']['pages'][0]
    revision = page['revisions'][0]
    text = revision['slots']['main']['content']
    if (page['pageid'],page['title'],revision['revid'],revision['timestamp']) != (meta['pageId'],meta['title'],meta['revisionId'],meta['revisionTimestamp']): raise ValueError('页面修订不符')
    url = urlparse(meta['url'])
    if url.scheme != 'https' or url.netloc != 'zh.wikisource.org' or url.path != '/w/api.php' or parse_qs(url.query).get('revids') != [str(meta['revisionId'])]: raise ValueError('采集地址不是固定修订API')
    if meta['permalink'] != 'https://zh.wikisource.org/w/index.php?oldid=' + str(meta['revisionId']): raise ValueError('永久链接与修订不符')
    if sha(text.encode('utf-8')) != meta['textSha256']: raise ValueError('原态文本哈希不符')
    body = text.split('<poem>', 1)[-1]
    header = re.search(r'(蜀志|[吳吴呉]志)\s*卷\s*([一二三四五六七八九十]+)', body[:800])
    if meta['kind'] == 'contents':
        quote = re.search(r'魏志三十卷蜀志十五卷[吳吴呉]志二十卷', re.sub(r'\s+', '', body))
        if not quote: raise ValueError('未在所取目录核得魏30蜀15吴20的明文')
        return {'title': meta['title'], 'revisionId': meta['revisionId'], 'directoryQuote': quote[0], 'status': 'directory-counts-present'}
    expected_section = '蜀志' if meta['section'] == '蜀志' else '吳志'
    if not header or header[1].replace('吴', '吳').replace('呉', '吳') != expected_section or header[2] != chinese(meta['juanNumber']):
        raise ValueError('卷题与所采卷目不符：' + meta['title'])
    return {'title': meta['title'], 'revisionId': meta['revisionId'], 'originalHeading': header[0],
            'textBytes': len(text.encode('utf-8')), 'status': 'heading-and-revision-present',
            'limitation': '仅核卷题与修订原态；模板字、缺字和全文转录仍须对照影像'}


def main(cache=None):
    cache = cache or ROOT.parent / '.local/research-cache'
    path = ROOT / 'data/wikisource-acquisition.json'
    manifest = read(path)
    rows = []
    for meta in manifest['pages']:
        raw = (cache / sha(meta['url'].encode())).read_bytes()
        row = inspect(meta, raw)
        if row.get('originalHeading'): meta['originalHeading'] = row['originalHeading']
        rows.append(row)
    expected = {(s, n) for s, count in [('蜀志', 15), ('吳志', 20)] for n in range(1, count + 1)}
    actual = {(p['section'], p['juanNumber']) for p in manifest['pages'] if p['kind'] != 'contents'}
    if actual != expected or len(rows) != 36: raise ValueError('逐卷清单未齐或出现重复；不得标记覆盖完整')
    report = {'checkedAt': now(), 'expected': {'蜀志': 15, '吳志': 20, '目录': 1},
              'acquired': len(rows), 'revisionAndHeadingCheckPassed': True, 'academicReview': 'pending', 'items': rows,
              'limitation': '取得所选维基修订的35卷原态及目录；不证明原底本全文无缺或已完成校勘'}
    dump(path, manifest)
    dump(ROOT / 'data/wikisource-coverage.json', report)
    print('目录明载魏30蜀15吴20；所取蜀15吴20卷题、修订及字节哈希全部对应。')


if __name__ == '__main__': main()
