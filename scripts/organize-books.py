"""整理现有书目与新增版本的真实库存；不把出处占位和异名当完整典籍。"""
import argparse
import collections
import io
import zipfile
from research import ROOT, read, dump, connect, now
from raw_ingest import sha, source_unit


def render_register(doc):
    lines = ['# 典籍库存与补书台账', '',
             '原件入库服务公共阅读、文学历史研读和专业考据；以下是库存与编目状态，不是学术核定结论。', '',
             '27个原典仓库，29个固定版本快照；同源分支不算独立典籍或佐证。最终处理状态见 `data/ingestion-report.json`。', '',
             '## 已取得的原典', '', '| 实际文件题名 | 底本标记 | 仓库与提交 | 文件单元 |', '|---|---|---|---|']
    for e in doc['acquiredEditions']:
        repo, commit = e['repository'], e['commit']
        lines.append('| ' + ' / '.join(e['titles']) + ' | ' + ', '.join(e['baseCodes']) + ' | [' + repo.split('/')[1] + '@' + commit[:8] + '](https://github.com/' + repo + '/tree/' + commit + ') | ' + str(e['textFiles']) + ' |')
    lines += ['', '文件数不是原书卷数。ZIP和每个原文件均保存，卷首、附录、重排编号和缺卷另核。', '',
              '## 当前已识别的问题与下一步', '',
              '- 《三国志》Git master与WYG仍仅有魏志；已另取维基蜀15、吴20及目录固定修订，须对照影像，不拼成未经说明的混合底本。',
              '- 《文忠集》入口受阻。另一个目录题《欧阳文粹》的仓库实际文件题《欧阳文忠公集》，须按SBCK组件和原卷编目，不能直接称选本或全集。',
              '- 《王文成公全书》的数字JUAN是重排编号候选，原FILE含不同卷号；主文、年谱、附录分别核目录，保留对应关系。',
              '- 《白氏文集》《韦刺史诗集》《刘梦得文集》等实际题名与目录存在异名，保留实际文件题名，不自动合并版本。',
              '- 地方志尚按具体站点争议选书；正史其余版本、独立年谱和影像继续寻源，不以现有单元数反推缺卷数。', '',
              '## 现有38条书目', '',
              '9条已有卷篇，2条仅有诗歌库记录，27条目前仅出处占位。零卷篇不等于全项目没有相关材料；新增原件仍在隔离研究区，不自动覆盖旧书目。', '',
              '| ID | 原登记题名 | 卷篇单元 | 诗曲记录 | 库存类别 |', '|---|---|---|---|---|']
    labels = {'has-text-units': '已有卷篇，覆盖待核', 'has-poem-records': '仅诗歌库记录', 'citation-only': '出处占位'}
    for b in doc['legacyBooks']:
        lines.append(f'| {b["id"]} | {b["title"]} | {b["textUnits"]} | {b["poemRecords"]} | {labels[b["status"]]} |')
    lines += ['', '同书异名、版本并列与现代栏目名关系候选见 `data/book-register.json`，未自动删除、合并或补造书目。', '']
    if doc.get('wikiRevisions'):
        lines += ['## 续补：维基固定修订与影像', '',
                  '取得蜀志15卷、吴志20卷及目录，共36页固定修订；已核页面身份和实际卷题，全文转录/模板字仍待影像对校。Git与维基分别保留，不当独立佐证。', '',
                  '| 卷目 | 固定修订 | 文本SHA-256 |', '|---|---|---|']
        for p in doc['wikiRevisions']:
            lines.append('| ' + p['title'] + ' | [' + str(p['revisionId']) + '](' + p['permalink'] + ') | ' + p['textSha256'] + ' |')
        lines += ['', '另取得CADAL蜀志卷五至八影像及平台版本元数据（完整原件仅隔离保存），登记NDL其他版本机构书目作为寻源线索；不据此宣称影像已经对校或底本一致。', '']
    return '\n'.join(lines)


def organize(credentials=None):
    inventory = read(ROOT / 'data/corpus-inventory.json')
    units = inventory['units']
    poem_counts = {}
    with connect(credentials) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT book_id,count(*) FROM public.corpus_poem GROUP BY book_id')
            poem_counts = dict(cur.fetchall())
            cur.execute('SELECT book_id,count(*) FROM public.text_unit GROUP BY book_id')
            actual_units = dict(cur.fetchall())
    expected_units = collections.Counter(u['book_id'] for u in units)
    if actual_units != dict(expected_units): raise ValueError('卷篇库存已变化，先刷新 research.py inventory，不能沿用旧数')
    books = []
    for book in inventory['books']:
        own = [u for u in units if u['book_id'] == book['id']]
        versions = []
        for edition in sorted({u['edition'] or '未记版本' for u in own}):
            group = [u for u in own if (u['edition'] or '未记版本') == edition]
            versions.append({'edition': edition, 'units': len(group), 'locators': [u['juan'] for u in group],
                             'sourceUrls': sorted({u['source_url'] for u in group if u['source_url']})})
        count = poem_counts.get(book['id'], 0)
        books.append({**book, 'textUnits': len(own), 'poemRecords': count, 'versions': versions,
                      'status': 'has-text-units' if own else ('has-poem-records' if count else 'citation-only'),
                      'coverage': '未据完整版本目录逐卷判定，不按单元条数声称全本'})
    cache = ROOT.parent / '.local/research-cache'
    acquired = []
    observations = []
    for meta in read(ROOT / 'data/acquisition-manifest.json')['repositories']:
        raw = (cache / sha(meta['url'].encode())).read_bytes()
        if sha(raw) != meta['archiveSha256']: raise ValueError('原典包哈希不符')
        entries = []
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name in archive.namelist():
                path = name.split('/', 1)[-1]
                if not path.endswith('.txt') or not path.startswith(meta['repository'].split('/')[1] + '_'): continue
                data = archive.read(name)
                header, pages = source_unit(data, path)
                entries.append({'path': path, 'sha256': sha(data), **header, 'sourcePageSpans': len(pages)})
        acquired.append({'repository': meta['repository'], 'commit': meta['commit'], 'archiveSha256': meta['archiveSha256'],
                         'units': entries, 'textFiles': len(entries), 'status': 'acquired-pending-ingestion',
                         'titles': sorted({u['title'] for u in entries if u['title']}),
                         'baseCodes': sorted({u['base'] for u in entries if u['base']}),
                         'coverage': '完整固定提交的文件清单；全书卷数、存佚、序跋和附录尚待人工核目录'})
        if meta['repository'].endswith('KR2a0012'):
            sections = {label: sum(any(label + '卷' in line for line in e['openingLines']) for e in entries)
                        for label in ['魏志', '蜀志', '吳志']}
            observations.append({'repository': meta['repository'], 'commit': meta['commit'],
                'code': 'section-coverage', 'sectionHeadingCounts': sections,
                'nextAction': 'Git仅检出魏志；维基另取蜀吴固定修订，须对照影像，不认作Git全本或自动拼合底本'})
        if meta['repository'].endswith('KR4e0157'):
            observations.append({'repository': meta['repository'], 'commit': meta['commit'], 'code': 'reordered-file-index',
                'example': {k: entries[1].get(k) for k in ['path', 'juanHeader', 'fileLabel', 'juan']},
                'nextAction': '按原FILE/正文卷题重新编目；JUAN数字仅保留为整理编号，逐卷确认附录、年谱和主文覆盖'})
        if meta['repository'].endswith('KR4d0069'):
            observations.append({'repository': meta['repository'], 'commit': meta['commit'], 'code': 'catalog-file-title-differs',
                'catalogTitle': '歐陽文粹', 'observedTitles': sorted({e['title'] for e in entries if e['title']}),
                'nextAction': 'SBCK实际文件题为欧阳文忠公集，含重排组件；不能按目录名称断言其为欧阳文粹全本或欧阳修全集'})
    plan = read(ROOT / 'data/book-acquisition-plan.json')
    acquired_ids = {m['repository'].split('/')[1] for m in acquired}
    blocked = [c for c in plan['candidates'] if c['repository'] not in acquired_ids]
    # 仅给出可明确识别的题名关系候选；不合并书目或版本。
    title_groups = [{'bookIds': [14, 81, 161], 'relationship': '旧唐书同书异名及不同版本，不能加总冒充独立典籍'},
                    {'bookIds': [19, 28], 'relationship': '明史出处占位与正文书目，保留各自来源'},
                    {'bookIds': [24, 26], 'relationship': '竹山词繁简异名，版本关系待核'},
                    {'bookIds': [78, 109], 'relationship': '全唐诗同名书目，一条含诗库记录，一条可能仅出处占位'},
                    {'bookIds': [18, 20, 21, 22, 23], 'relationship': '王阳明全集、传习录与旧栏目名混列，不能当五部独立原书'}]
    wiki_path = ROOT / 'data/wikisource-acquisition.json'
    wiki_pages = read(wiki_path)['pages'] if wiki_path.exists() else []
    doc = {'checkedAt': now(), 'inventoryCheckedAt': inventory['checkedAt'], 'legacyBooks': books, 'wikiRevisions': wiki_pages,
           'titleRelationshipsPendingReview': title_groups, 'acquiredEditions': acquired, 'coverageObservations': observations,
           'blockedCandidates': blocked, 'remainingResearchNeeds': plan['remaining'],
           'counts': {'legacyBookRows': len(books), 'citationOnly': sum(b['status'] == 'citation-only' for b in books),
                      'withTextUnits': sum(b['status'] == 'has-text-units' for b in books),
                      'withPoemsOnly': sum(b['status'] == 'has-poem-records' for b in books),
                      'acquiredRepositories': len({m['repository'] for m in acquired}), 'sourceSnapshots': len(acquired),
                      'acquiredTextFiles': sum(x['textFiles'] for x in acquired),
                      'wikiPages': len(wiki_pages), 'wikiBodyVolumes': sum(p['kind']=='body' for p in wiki_pages),
                      'blockedCandidates': len(blocked)},
           'limitation': '书目身份和储存完整性检查，不是全文校勘；不沿用旧缺卷数字，不删除或合并现有书目。'}
    dump(ROOT / 'data/book-register.json', doc)
    (ROOT / 'docs/book-register.md').write_text(render_register(doc), encoding='utf-8', newline='\n')
    print(doc['counts'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials')
    organize(parser.parse_args().credentials)
