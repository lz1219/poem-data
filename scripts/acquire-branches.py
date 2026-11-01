"""针对已发现的截断/重排，补取已调查到的固定版本分支；不覆盖master。"""
import io
import zipfile
from research import ROOT, read, dump, fetch


def main():
    manifest = read(ROOT / 'data/acquisition-manifest.json')
    sources = read(ROOT / 'shared/sources.json')
    survey = read(ROOT / 'data/branch-survey.json')
    for repo, branch in [('KR2a0012', 'WYG'), ('KR4e0157', 'SBCK')]:
        entry = next(item for item in survey['items'] if item['repository'] == repo)
        selected = next((b for b in entry['branches'] if b['name'] == branch), None)
        if selected is None: print(repo + '：目标分支未取得'); continue
        commit = selected['commit']['sha']
        if any(m['repository'] == 'kanripo/' + repo and m['commit'] == commit for m in manifest['repositories']): continue
        info, raw = fetch(f'https://codeload.github.com/kanripo/{repo}/zip/{commit}', ROOT.parent / '.local/research-cache')
        if not raw: print(repo + '：补充分支受阻'); continue
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            texts = [name for name in z.namelist() if name.endswith('.txt') and name.split('/')[-1].startswith(repo + '_')]
            notices = [z.read(n).decode('utf-8') for n in z.namelist() if n.lower().endswith(('.org', 'readme.md', 'license'))]
        manifest['repositories'].append({'repository': 'kanripo/' + repo, 'branch': branch, 'commit': commit,
            'archiveSha256': info['sha256'], 'url': info['url'], 'fetchedAt': info['checkedAt'], 'textFiles': len(texts),
            'licenseNotice': '\n'.join(notices)[:14000], 'matches': [],
            'acquisitionPurpose': 'master仅部分原书或卷号重排，补取显式版本分支；原master并存，不自动认定全本'})
        sources['sources'].append({'id': 'kanripo-' + repo.lower() + '-' + branch.lower(),
            'name': repo + ' · ' + branch + ' 固定版本分支', 'url': f'https://github.com/kanripo/{repo}/tree/{commit}',
            'kind': 'github', 'coverage': ['固定版本分支的全部文件；原书覆盖待核'], 'sourceFamily': repo,
            'upstream': ['kanripo'], 'baseEdition': '以原文件标记为准',
            'permissions': {'read': True, 'download': 'public-repository', 'ingest': 'research-copy', 'redistribute': 'not-cleared'},
            'usageNote': '与master同来源链；仅隔离研究保存，不作为独立佐证或自动公开正文。',
            'probe': info, 'repository': 'kanripo/' + repo, 'commit': commit, 'branch': branch})
        dump(ROOT / 'data/acquisition-manifest.json', manifest)
        dump(ROOT / 'shared/sources.json', sources)
        print(repo + '/' + branch + '：' + str(len(texts)) + ' 文件', flush=True)


if __name__ == '__main__': main()
