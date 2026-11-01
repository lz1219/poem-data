"""来源调查、只读库存、全量结构审查。默认不修改任何数据库。

python scripts/research.py survey --cache <仓库外目录>
python scripts/research.py inventory --credentials <本地凭据文件>
python scripts/research.py audit
"""
import argparse
import hashlib
import json
import re
import time
import os
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def dump(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def read(p):
    return json.loads(p.read_text('utf-8'))


def now():
    return datetime.now(timezone.utc).isoformat()


def save_object(cache,body):
    """原件按内容寻址，完整写入后链接发布，不覆盖旧字节。"""
    digest=hashlib.sha256(body).hexdigest();folder=cache/'objects';folder.mkdir(parents=True,exist_ok=True);target=folder/digest
    if target.exists():
        if target.read_bytes()!=body: raise ValueError('内容哈希缓存对象已损坏')
        return digest
    fd,name=tempfile.mkstemp(prefix='.capture-',dir=folder)
    try:
        with os.fdopen(fd,'wb') as stream: stream.write(body);stream.flush();os.fsync(stream.fileno())
        try: os.link(name,target)
        except FileExistsError:
            if target.read_bytes()!=body: raise ValueError('并发原件缓存冲突')
    finally: Path(name).unlink(missing_ok=True)
    return digest


def cached_response(cache,url,expected_sha):
    if not re.fullmatch(r'[a-f0-9]{64}',expected_sha): raise ValueError('缓存哈希标识非法')
    target=cache/'objects'/expected_sha
    if not target.exists(): target=cache/hashlib.sha256(url.encode()).hexdigest()
    raw=target.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha: raise ValueError('缓存原件与固定哈希不符')
    return raw


def fetch(url, cache):
    """每入口最多两次；原始响应与错误元数据分开保存，不回显凭据。"""
    key = hashlib.sha256(url.encode()).hexdigest()
    target = cache / key
    failure = 'FetchError'
    for attempt in range(2):
        try:
            if attempt == 0:
                req = urllib.request.Request(url, headers={'User-Agent': 'JiangshanResearch/1.0'})
                with urllib.request.urlopen(req, timeout=15) as r:
                    body = r.read()
            else:
                import subprocess
                # 第二次换传输实现，应对本机 urllib 偶发 SSL EOF；不增加尝试次数。
                r = subprocess.run(['curl', '-fLsS', '--max-time', '20', '-A', 'JiangshanResearch/1.0', url], capture_output=True, timeout=22)
                if r.returncode: raise OSError('TransportError')
                body = r.stdout
            target.parent.mkdir(parents=True, exist_ok=True)
            save_object(cache,body)
            target.write_bytes(body)
            return {'url': url, 'checkedAt': now(), 'status': 'reachable',
                    'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body)}, body
        except Exception as exc:
            failure = type(exc).__name__
            if attempt == 0:
                time.sleep(.3)
    return {'url': url, 'checkedAt': now(), 'status': 'unavailable',
            'error': failure,
            'attempts': 2}, b''


SOURCES = [
    ('kanripo', 'Kanripo 汉籍', 'https://github.com/kanripo/KR-Catalog', 'github', ['别集', '总集', '史传', '诗文评']),
    ('chinese-poetry', 'chinese-poetry', 'https://github.com/chinese-poetry/chinese-poetry', 'github', ['唐诗', '宋诗', '宋词']),
    ('cbdb', 'CBDB', 'https://github.com/cbdb-project/cbdb_sqlite', 'github', ['人物', '仕历', '异名']),
    ('wikisource', '维基文库', 'https://zh.wikisource.org/w/api.php?action=query&meta=siteinfo&format=json', 'text', ['原典', '版本', '影像']),
    ('ctext', '中国哲学书电子化计划', 'https://ctext.org/tools/api', 'text', ['原典', '检索', '影像']),
    ('shidian', '识典古籍', 'https://www.shidianguji.com/', 'text', ['原典', '底本影像']),
    ('scripta-sinica', '中研院汉籍', 'https://hanchi.ihp.sinica.edu.tw/', 'text', ['史传', '集部']),
    ('nlc', '国家图书馆', 'https://www.nlc.cn/', 'catalog-image', ['古籍影像', '目录']),
    ('ncl', '台北国家图书馆', 'https://rbook.ncl.edu.tw/NCLSearch/Search', 'catalog-image', ['古籍影像', '目录']),
    ('harvard-yenching', '哈佛燕京图书馆', 'https://library.harvard.edu/collections/chinese-collection', 'catalog-image', ['别集', '方志', '古籍影像']),
    ('kyoto', '京都大学汉籍目录', 'https://kanji.zinbun.kyoto-u.ac.jp/kanseki/', 'catalog-image', ['目录', '版本']),
    ('tokyo', '东京大学东洋文化研究所', 'https://www.ioc.u-tokyo.ac.jp/kanseki/', 'catalog-image', ['目录', '影像']),
    ('shuge', '书格', 'https://www.shuge.org/', 'catalog-image', ['古籍影像']),
    ('wikidata', 'Wikidata', 'https://www.wikidata.org/wiki/Wikidata:Main_Page', 'structured', ['人物映射', '研究线索']),
    ('chgis', 'CHGIS', 'https://chgis.fas.harvard.edu/', 'structured', ['历史建置', '地名消歧']),
]


def survey(cache):
    from concurrent.futures import ThreadPoolExecutor
    def probe(item):
        key, name, url, kind, coverage = item
        meta, _ = fetch(url, cache)
        return {'id': key, 'name': name, 'url': url, 'kind': kind, 'coverage': coverage,
                'upstream': [], 'sourceFamily': key, 'baseEdition': '按具体文本核实',
                'permissions': {'read': meta['status'] == 'reachable', 'download': 'unknown',
                                'ingest': 'unknown', 'redistribute': 'unknown'},
                'usageNote': '入口测试不是具体文本授权；逐文件核验版本、上游与使用条款。',
                'probe': meta}
    with ThreadPoolExecutor(max_workers=5) as pool:
        sources = list(pool.map(probe, SOURCES))
    catalogs = []
    commit_meta, commit_body = fetch('https://api.github.com/repos/kanripo/KR-Catalog/commits/master', cache)
    commit = json.loads(commit_body).get('sha') if commit_body else None
    if commit:
        for code in ['KR2a', 'KR2g', 'KR2k', 'KR4b', 'KR4c', 'KR4d', 'KR4h', 'KR4i', 'KR4j']:
            url = f'https://raw.githubusercontent.com/kanripo/KR-Catalog/{commit}/KR/{code}.txt'
            meta, body = fetch(url, cache)
            catalogs.append({**meta, 'repository': 'kanripo/KR-Catalog', 'commit': commit, 'path': f'KR/{code}.txt'})
    dump(ROOT / 'shared/sources.json', {'schemaVersion': '1.0', 'sources': sources, 'catalogs': catalogs})
    # 保留目录原文作为允许公开的目录元数据，正文另行核验后采集。
    for meta in catalogs:
        if meta['status'] == 'reachable':
            raw = (cache / hashlib.sha256(meta['url'].encode()).hexdigest()).read_bytes()
            (cache / (Path(meta['path']).stem + '.txt')).write_bytes(raw)
    lines = ['# 来源调查', '', f'调查时间：{now()}。原始响应缓存在仓库外；每入口最多两次请求。', '',
             '| 来源 | 类型 | 入口状态 | 下载/入库/分发 |', '|---|---|---|---|']
    for s in sources:
        lines.append(f"| [{s['name']}]({s['url']}) | {s['kind']} | {s['probe']['status']} | 待具体资源核实 |")
    lines += ['', '## 调查边界', '', '入口可达不等于已查到所需底本。已下载并固定 Kanripo 史传、地理、别集、总集、诗文评及词曲目录；各条记录另列具体命中与未检索项。未取得可用文本的条目不得标为已核。', '',
              '## 优先次序', '', '反推繁体作品的底本 → 系年史料原句 → 行迹年地与人物身份 → 相关缺卷 → 独立版本校记与历代评点。', '',
              '## 受阻与切换', '', 'unavailable 来源保留错误类型和测试日期；不绕过登录/访问控制。转查其他来源或影像；权限未知仅发布目录链接。付费、账号申请与人工查阅不阻塞公开来源批次。']
    (ROOT / 'docs/source-survey.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    print(f'来源 {len(sources)}，目录尝试 {len(catalogs)}，取得 {sum(c["status"] == "reachable" for c in catalogs)}；未把入口可达视为资料核实。')


def connect(credentials=None, readonly=True):
    import os
    import psycopg
    dsn = os.getenv('CORPUS_DSN', '')
    if credentials:
        # 凭据仅在内存解析，不写入结果或异常输出。
        dsn = re.search(r'postgresql://[^\s`]+', Path(credentials).read_text('utf-8')).group(0)
    if not dsn:
        raise ValueError('需要 CORPUS_DSN 或 --credentials；不回显连接串')
    return psycopg.connect(dsn, connect_timeout=8, options='-c statement_timeout=20000' +
                          (' -c default_transaction_read_only=on' if readonly else ''))


def inventory(credentials):
    with connect(credentials) as conn:
        with conn.cursor() as cur:
            def rows(sql):
                cur.execute(sql)
                names = [c.name for c in cur.description]
                return [dict(zip(names, r)) for r in cur.fetchall()]
            counts = {}
            for table in ['book', 'text_unit', 'paragraph', 'corpus_poem', 'claim', 'evidence', 'person_source', 'place']:
                cur.execute('SELECT count(*) FROM ' + table)
                counts[table] = cur.fetchone()[0]
            books = rows('SELECT id,title,edition,license,source_url FROM book ORDER BY id')
            units = rows('SELECT id,book_id,juan,title,edition,sha256,source_url,punctuated FROM text_unit ORDER BY book_id,edition,id')
            duplicates = rows('SELECT book_id,edition,juan,count(*) AS copies FROM text_unit GROUP BY book_id,edition,juan HAVING count(*)>1')
            evidence = rows('SELECT id,claim_id,source_text,quote,unit_id,paragraph_id,match_kind FROM evidence ORDER BY id')
    dump(ROOT / 'data/corpus-inventory.json', {'schemaVersion': '1.0', 'checkedAt': now(), 'mode': 'read-only',
         'counts': counts, 'books': books, 'units': units, 'duplicateLocators': duplicates, 'evidence': evidence,
         'limitation': '卷数不代表完整度；目录中的序跋附录须按版本逐项核对。尚未核全书预期卷目。'})
    print(json.dumps(counts))


def audit(cache):
    from research_records import save_record, build_index
    catalogs = '\n'.join(p.read_text('utf-8') for p in cache.glob('KR*.txt')) if cache else ''
    total = {'works': 0, 'persons': 0, 'journeys': 0, 'stops': 0}
    for group in ['works', 'persons', 'journeys']:
        for file in sorted((ROOT / 'data' / group).glob('*.json')):
            item = read(file)
            subject = {'type': group[:-1] if group != 'persons' else 'person', 'key': item['key']}
            issues = []
            if group == 'works':
                if item['text'].get('traditionalDerived'):
                    issues.append('繁体由简体反推，尚缺可核底本；保留反推标识。')
                if any(re.fullmatch(r'-?\d+', e.get('quote', '').strip()) for d in item.get('dating', []) for e in d.get('evidence', [])):
                    issues.append('系年依据仅为年份占位，不是史料原句；既有年份待考据复核。')
                if not item.get('citation'):
                    issues.append('缺出处。')
                issues.append('正文、释义、背景、赏析尚未逐项对原书完成学术审校。')
            elif group == 'persons':
                issues.append('人物生卒、身份映射与别名需对本传/年谱逐项核验；现有字段不等于证据。')
                if item.get('spanNote'):
                    issues.append('有生卒异说，必须随展示保留。')
            else:
                issues.append('站点 source 已登记；叙述与年地关系仍需逐站核原句。')
            terms = [item.get('titleZh', ''), item.get('zh', '')]
            hits = [line for line in catalogs.splitlines() if any(len(t) >= 2 and t in line for t in terms if t)][:12]
            save_record(ROOT, {'id': f'audit-{subject["type"]}-' + hashlib.sha256(item['key'].encode()).hexdigest()[:16],
                'subject': subject, 'kind': 'audit', 'status': 'partial', 'visibility': 'public',
                'title': item.get('titleZh') or item.get('zh') or item['key'],
                'claim': '结构与证据缺口初审；不代表史实已经核定。',
                'provenance': {'origin': 'machine', 'method': '结构审查与公开目录检索，不是人工学术审校'},
                'issues': issues, 'evidence': [], 'reasoning': '', 'counterEvidence': '尚未完成系统反证检索。',
                'alternatives': [], 'reviewHistory': [], 'searchLog': [
                    {'sourceId': 'kanripo', 'queries': [t for t in terms if t], 'mode': '固定提交目录检索', 'hits': hits},
                    {'sourceId': 'nlc', 'mode': '影像与版本目录', 'status': 'pending', 'reason': '入口已列入调查，未逐条人工检索'},
                    {'sourceId': 'wikisource', 'mode': '篇卷文本检索', 'status': 'pending', 'reason': '需精确篇卷或别名继续检索'}],
                'nextAction': '依据候选底本核正文/史实并登记具体卷篇与原句；无命中时转查别集异名、影像及机构目录。'})
            total[group] += 1
            if group == 'journeys':
                for stop in item['stops']:
                    sid = f'{item["key"]}:{stop["seq"]}'
                    save_record(ROOT, {'id': 'audit-stop-' + hashlib.sha256(sid.encode()).hexdigest()[:16],
                        'subject': {'type': 'stop', 'key': sid}, 'kind': 'audit', 'status': 'pending', 'visibility': 'public',
                        'title': f'{item["titleZh"]} · 第{stop["seq"]}站 · {stop["place"]["ancient"]}',
                        'claim': stop['descZh'], 'provenance': {'origin': 'unknown', 'method': '历史叙述生成方式未记录'},
                        'issues': ['已有出处字符串，但尚缺原句与段落定位；有来源不等于该来源支持整段叙述。'] +
                                  (['未知年份不得当作0年排序或跳年。'] if stop['year'] is None else []),
                        'evidence': [], 'reasoning': '', 'counterEvidence': '尚未完成系统反证检索。',
                        'alternatives': [], 'reviewHistory': [], 'searchLog': [],
                        'nextAction': f'按原出处查卷篇：{stop["source"]}；结合年代消歧地名，缺证时缩减叙述。'})
                    total['stops'] += 1
    # 既有推测独立登记；不推断作者或模型身份。
    for file in sorted((ROOT / 'data/works').glob('*.json')):
        w = read(file)
        inf = w.get('appreciation', {}).get('inference')
        if not inf:
            continue
        save_record(ROOT, {'id': 'legacy-inference-' + hashlib.sha256(w['key'].encode()).hexdigest()[:16],
            'subject': {'type': 'work', 'key': w['key']}, 'kind': 'inference', 'status': 'pending', 'visibility': 'internal',
            'title': w['titleZh'] + ' · 历史推测', 'claim': inf['text'],
            'provenance': {'origin': 'unknown', 'method': '生成方式未记录'},
            'issues': ['历史推测未核引文，不追认成人工或AI。'], 'evidence': [], 'reasoning': inf['basis'],
            'counterEvidence': '尚未检索。', 'alternatives': [], 'reviewHistory': [], 'searchLog': [],
            'nextAction': '核依据原句、寻找反证，再决定是否公开。'})
    build_index(ROOT)
    lines = ['# 数据现状与核查缺口', '', f'生成时间：{now()}。由 scripts/research.py audit 生成。', '',
             '| 对象 | 已覆盖结构与缺口审查 |', '|---|---|']
    lines += [f'| {k} | {v} |' for k, v in total.items()]
    lines += ['', '所有记录均有核查状态、问题和下一步；结构初审不等于人工史实核定。', '',
              '69条旧系年依据的年份占位仍需原句；反推繁体未经核对不取消标识。实际卷篇库存见 data/corpus-inventory.json；来源状态见 docs/source-survey.md。', '',
              '## 复现', '', '```text', 'python scripts/research.py survey --cache <仓库外缓存>',
              'server/.venv/Scripts/python scripts/research.py inventory --credentials <本地凭据文件>',
              'python scripts/research.py audit --cache <同一缓存>', '```']
    (ROOT / 'docs/data-status.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(total))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['survey', 'inventory', 'audit'])
    p.add_argument('--cache', type=Path, default=ROOT.parent / '.local/research-cache')
    p.add_argument('--credentials')
    args = p.parse_args()
    if args.command == 'survey': survey(args.cache)
    elif args.command == 'inventory': inventory(args.credentials)
    else: audit(args.cache)
