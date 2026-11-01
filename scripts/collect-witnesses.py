"""固定 GitHub 提交采集原典，保存完整原件到仓库外；只发布定位摘引。

默认从独立别集核对现有作品，不覆盖基线正文或自动判定系年。
"""
import argparse
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from research import ROOT, dump, fetch, now, read
from research_records import save_record, build_index


def normalize(s):
    # 页码标记与编排符号只用于匹配，不修改保存的原文。
    index = []
    chars = []
    blocked = {i for m in re.finditer(r'\[[^\]]*\]', s) for i in range(m.start(), m.end())}
    for i, c in enumerate(s):
        if '\u3400' <= c <= '\u9fff' and i not in blocked:
            chars.append(c)
            index.append(i)
    return ''.join(chars), index


def collect(cache, repositories):
    sources_path = ROOT / 'shared/sources.json'
    registry = read(sources_path)
    works = [read(f) for f in sorted((ROOT / 'data/works').glob('*.json'))]
    manifests = []
    for repo in repositories:
        info, data = fetch(f'https://api.github.com/repos/kanripo/{repo}/commits/master', cache)
        if not data:
            manifests.append({'repository': repo, 'probe': info}); continue
        commit = json.loads(data)['sha']
        info, archive = fetch(f'https://codeload.github.com/kanripo/{repo}/zip/{commit}', cache)
        if not archive:
            manifests.append({'repository': repo, 'commit': commit, 'probe': info}); continue
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            texts = []
            readme = []
            for name in z.namelist():
                if name.lower().endswith(('.org', 'license', 'license.txt', 'readme.md')):
                    readme.append(z.read(name).decode('utf-8', 'replace'))
                if re.search(r'/' + repo + r'_\d+\.txt$', name):
                    content = z.read(name).decode('utf-8-sig')
                    norm, idx = normalize(content)
                    texts.append((name.split('/', 1)[1], content, norm, idx))
            meta = {'repository': 'kanripo/' + repo, 'commit': commit, 'archiveSha256': info['sha256'],
                    'url': info['url'], 'fetchedAt': info['checkedAt'], 'textFiles': len(texts),
                    'licenseNotice': '\n'.join(readme)[:14000], 'matches': []}
            source_id = 'kanripo-' + repo.lower()
            if not any(s['id'] == source_id for s in registry['sources']):
                registry['sources'].append({'id': source_id, 'name': repo + ' · Kanripo原典',
                    'url': f'https://github.com/kanripo/{repo}/tree/{commit}', 'kind': 'github',
                    'coverage': ['按文件卷目核对，尚未宣称全本'], 'sourceFamily': repo,
                    'upstream': ['kanripo'], 'baseEdition': '以原文件卷首版本标记为准',
                    'permissions': {'read': True, 'download': 'public-repository', 'ingest': 'research-copy', 'redistribute': 'excerpt-only'},
                    'usageNote': '完整原件仅存研究缓存；公开定位摘引，版权与版本说明保留。',
                    'probe': info, 'repository': 'kanripo/' + repo, 'commit': commit})
            for w in works:
                parts = w['text']['paragraphs']
                # 太短的摘句不足以判同篇；仅报告较长片段，不把机器命中判成学术审校。
                targets = [normalize(p)[0] for p in parts if len(normalize(p)[0]) >= 12]
                if not targets: continue
                best = None
                for file, body, normalized, indexes in texts:
                    positions = [(t, normalized.find(t)) for t in targets]
                    hits = [(t, i) for t, i in positions if i >= 0]
                    if not hits: continue
                    if best and len(hits) <= best[0]: continue
                    t, i = hits[0]
                    start, end = indexes[i], indexes[i + len(t) - 1] + 1
                    # 精确保留出处中的实际字符，不反向生成所谓原文。
                    quote = body[start:end]
                    best = (len(hits), file, body, quote)
                if not best: continue
                hit_count, file, body, quote = best
                excerpt = quote.encode('utf-8')
                sha = hashlib.sha256(excerpt).hexdigest()
                artifact = ROOT / 'data/witnesses' / (sha + '.txt')
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_bytes(excerpt)
                full_sha = hashlib.sha256(body.encode('utf-8')).hexdigest()
                evidence = {'sourceId': source_id, 'quote': quote, 'locator': file,
                    'url': f'https://github.com/kanripo/{repo}/blob/{commit}/{file}', 'commit': commit,
                    'sha256': sha, 'originalFileSha256': full_sha, 'textFile': 'data/witnesses/' + sha + '.txt',
                    'verifiedQuote': True, 'verification': '原始版本逐字摘引；匹配时仅去编排符号',
                    'stance': 'support', 'grade': 'ungraded'}
                doc = {'id': 'witness-' + hashlib.sha256((w['key'] + repo).encode()).hexdigest()[:20],
                    'subject': {'type': 'work', 'key': w['key']}, 'kind': 'witness', 'status': 'partial', 'visibility': 'public',
                    'title': w['titleZh'] + ' · ' + repo + ' 版本见证',
                    'claim': '在固定提交的独立原典文件中发现正文片段；不能据此确定作年或地点。',
                    'provenance': {'origin': 'machine', 'method': '去编排符号匹配后逐字提取原始片段'},
                    'evidence': [evidence], 'issues': [f'{len(targets)}个可比片段中命中{hit_count}个；尚待人工核对篇题、底本及上下文。'],
                    'reasoning': '', 'counterEvidence': '尚未系统检索其他版本；未作异文裁决。',
                    'alternatives': [], 'reviewHistory': [], 'searchLog': [{'sourceId': source_id, 'query': w['titleZh'], 'mode': '正文片段比对'}],
                    'nextAction': '人工核对卷首版本、篇题与上下文，再决定全文替换、校记或系年证据。'}
                save_record(ROOT, doc)
                meta['matches'].append({'workKey': w['key'], 'recordId': doc['id'], 'locator': file, 'matchedParts': hit_count, 'totalParts': len(targets)})
            manifests.append(meta)
        print(repo + ': 原典文件 ' + str(len(texts)) + '，候选命中 ' + str(len(meta['matches'])), flush=True)
    dump(sources_path, registry)
    dump(ROOT / 'data/acquisition-manifest.json', {'schemaVersion': '1.0', 'repositories': manifests})
    build_index(ROOT)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache', type=Path, default=ROOT.parent / '.local/research-cache')
    p.add_argument('--repositories', nargs='+', default=['KR4c0012', 'KR4c0015', 'KR4c0069', 'KR4d0076', 'KR4j0005', 'KR4j0053'])
    args = p.parse_args()
    collect(args.cache, args.repositories)
