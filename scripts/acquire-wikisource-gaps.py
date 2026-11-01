"""固定维基修订补原典；完整原始响应和维基文本保留，不当作已核正文。"""
import argparse
import json
import re
from urllib.parse import urlencode
from research import ROOT, read, dump, fetch, now
from raw_ingest import sha

API = 'https://zh.wikisource.org/w/api.php'
BOOK = '三國志 (四庫全書本)'


def query(params, cache):
    url = API + '?' + urlencode({'format': 'json', 'formatversion': 2, **params})
    info, raw = fetch(url, cache)
    return info, json.loads(raw) if raw else None


def capture(title, cache):
    # 查询最新只用来发现修订号；实际原件再请求该固定修订，避免后续页面变化。
    probe, doc = query({'action': 'query', 'prop': 'revisions', 'rvprop': 'ids', 'titles': title}, cache)
    if not doc or 'error' in doc: return None, probe
    page = doc['query']['pages'][0]
    if page.get('missing') or not page.get('revisions'): return None, probe
    revision = page['revisions'][0]['revid']
    info, fixed = query({'action': 'query', 'prop': 'revisions', 'rvprop': 'ids|timestamp|content',
                         'rvslots': 'main', 'revids': revision}, cache)
    if not fixed or 'error' in fixed: return None, info
    p = fixed['query']['pages'][0]
    r = p['revisions'][0]
    if p['title'] != title or p['pageid'] != page['pageid'] or r['revid'] != revision: raise ValueError('修订原件与所选页面不符')
    text = r['slots']['main']['content']
    if not text.strip(): raise ValueError('空白页面不能代替原典')
    return {'provider': 'wikisource', 'sourceId': 'wikisource-sanguozhi-siku', 'title': title,
            'pageId': p['pageid'], 'revisionId': revision, 'revisionTimestamp': r['timestamp'],
            'url': info['url'], 'permalink': 'https://zh.wikisource.org/w/index.php?oldid=' + str(revision),
            'captureSha256': info['sha256'], 'textSha256': sha(text.encode('utf-8')), 'fetchedAt': info['checkedAt'],
            'baseEdition': '维基文库标示四库全书本；底本影像与转录质量待核',
            'permissions': {'read': True, 'download': 'public-api', 'ingest': 'research-copy', 'redistribute': 'not-cleared'},
            'reviewStatus': 'pending'}, info


def main(cache):
    manifest_path = ROOT / 'data/wikisource-acquisition.json'
    manifest = read(manifest_path) if manifest_path.exists() else {'schemaVersion': '1.0', 'pages': [], 'attempts': []}
    current = {p['title']: p for p in manifest['pages']}
    titles = [(BOOK, 'contents', None)]
    titles += [(f'{BOOK}/{section}/卷{n:02d}', section, n) for section, total in [('蜀志', 15), ('吳志', 20)] for n in range(1, total + 1)]
    for title, section, number in titles:
        if title in current: continue
        entry, probe = capture(title, cache)
        manifest['attempts'].append({'title': title, 'section': section, 'juan': number, 'probe': probe,
                                     'status': 'acquired' if entry else 'unresolved'})
        if entry:
            entry.update({'section': section, 'juanNumber': number, 'kind': 'contents' if number is None else 'body'})
            manifest['pages'].append(entry)
            current[title] = entry
            print(title + ' @' + str(entry['revisionId']), flush=True)
        else: print(title + '：受阻，保留缺口', flush=True)
        dump(manifest_path, manifest)
    sources = read(ROOT / 'shared/sources.json')
    if not any(s['id'] == 'wikisource-sanguozhi-siku' for s in sources['sources']):
        sources['sources'].append({'id': 'wikisource-sanguozhi-siku', 'name': '三国志四库本 · 维基转录', 'kind': 'text',
            'url': 'https://zh.wikisource.org/wiki/' + BOOK.replace(' ', '_'), 'sourceFamily': 'sanguozhi-siku',
            'upstream': ['wikisource', '四库全书文渊阁本（标示底本，待核影像）'], 'baseEdition': '维基标示四库本，未人工鉴定',
            'coverage': ['按固定页面修订保存目录及蜀、吴两部分；原卷题和文本完整性另核'],
            'permissions': {'read': True, 'download': 'public-api', 'ingest': 'research-copy', 'redistribute': 'not-cleared'},
            'usageNote': '转录与底本分开；与同四库底本的Git转载不自动计独立佐证；完整原件仅隔离研究保存。'})
    dump(ROOT / 'shared/sources.json', sources)
    print('取得页数：' + str(len(manifest['pages'])) + '；仍须入库整理与回读。', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache', type=__import__('pathlib').Path, default=ROOT.parent / '.local/research-cache')
    main(p.parse_args().cache)
