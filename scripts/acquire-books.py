"""按缺口清单固定提交采集完整原典；不生成史实、赏析或改写旧正文。"""
import argparse
import io
import json
import re
import zipfile
from pathlib import Path
from research import ROOT, read, dump, fetch, now


def acquire(cache, retry_blocked=False):
    plan = read(ROOT / 'data/book-acquisition-plan.json')
    manifest = read(ROOT / 'data/acquisition-manifest.json')
    sources = read(ROOT / 'shared/sources.json')
    previous_path = ROOT / 'data/book-acquisition-log.json'
    previous = {x['repository']: x for x in read(previous_path)['items']} if previous_path.exists() else {}
    existing = {r['repository'] for r in manifest['repositories']}
    log = []
    for candidate in plan['candidates']:
        repo = candidate['repository']
        if not re.fullmatch(r'KR[0-9a-z]+', repo): raise ValueError('非法仓库名')
        if 'kanripo/' + repo in existing:
            log.append({**candidate, 'status': 'already-acquired'}); continue
        if not retry_blocked and previous.get(repo, {}).get('status', '').endswith('unavailable'):
            log.append(previous[repo])
            print(candidate['title'] + '：保留受阻记录，换其他来源', flush=True); continue
        info, data = fetch(f'https://api.github.com/repos/kanripo/{repo}/commits/master', cache)
        if not data:
            log.append({**candidate, 'status': 'commit-unavailable', 'probe': info}); continue
        commit = json.loads(data)['sha']
        if not re.fullmatch('[a-f0-9]{40}', commit): raise ValueError('提交标识不合法')
        info, archive = fetch(f'https://codeload.github.com/kanripo/{repo}/zip/{commit}', cache)
        if not archive:
            log.append({**candidate, 'status': 'archive-unavailable', 'commit': commit, 'probe': info}); continue
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            texts = [name for name in z.namelist() if re.search('/' + repo + r'_\d+\.txt$', name)]
            notices = [z.read(n).decode('utf-8', 'strict') for n in z.namelist() if n.lower().endswith(('.org', 'readme.md', 'license', 'license.txt'))]
        if not texts: raise ValueError('原典包没有文本文件：' + repo)
        meta = {'repository': 'kanripo/' + repo, 'commit': commit, 'archiveSha256': info['sha256'],
                'url': info['url'], 'fetchedAt': info['checkedAt'], 'textFiles': len(texts),
                'licenseNotice': '\n'.join(notices)[:14000], 'matches': [], 'acquisitionPurpose': candidate['purpose']}
        manifest['repositories'].append(meta)
        source_id = 'kanripo-' + repo.lower()
        if not any(s['id'] == source_id for s in sources['sources']):
            sources['sources'].append({'id': source_id, 'name': candidate['title'] + ' · Kanripo原典',
                'url': f'https://github.com/kanripo/{repo}/tree/{commit}', 'kind': 'github',
                'coverage': ['已取得完整仓库；实际卷篇及缺卷待核'], 'sourceFamily': repo,
                'upstream': ['kanripo'], 'baseEdition': '以原文件卷首版本标记为准',
                'permissions': {'read': True, 'download': 'public-repository', 'ingest': 'research-copy', 'redistribute': 'not-cleared'},
                'usageNote': '仅用于隔离研究区保存；待核材料不进入公开正文，未确认完整文本再分发条件。',
                'probe': info, 'repository': 'kanripo/' + repo, 'commit': commit})
        log.append({**candidate, 'status': 'acquired', 'commit': commit, 'textFiles': len(texts)})
        # 每书落清单，可续传；失败不会丢掉已完成原件。
        dump(ROOT / 'shared/sources.json', sources)
        dump(ROOT / 'data/acquisition-manifest.json', manifest)
        print(candidate['title'] + '：取得 ' + str(len(texts)) + ' 个文本文件', flush=True)
    dump(ROOT / 'data/book-acquisition-log.json', {'checkedAt': now(), 'items': log})
    print('采集完成；原件仍需 land / organize / verify 后才算入库整理。', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=ROOT.parent / '.local/research-cache')
    parser.add_argument('--retry-blocked', action='store_true', help='明确要求重新尝试历史受阻入口，每入口仍最多两次')
    args = parser.parse_args()
    acquire(args.cache, args.retry_blocked)
