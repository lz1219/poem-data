"""Append the remaining fixed WYG non-table Hanshu and edition front/back matter.

The eight tables (13-20) are excluded. No cross-edition repairs or glyph filling.
Requires the exact two existing Hanshu batches and shared edition 9.
"""
import argparse
import copy
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

from backfill_hanshu import make_plan as annals_plan, parse_file, ARCHIVE_SHA
from backfill_hanshu_biographies import make_plan as biographies_plan, backup_existing, verify_chain
from backfill_shiji import apply, rollback, require, digest
from research import cached_response, connect, dump
from corpus_preview import JUAN, PAGE, visible_text

PARSER = 'hanshu-wyg-remaining-nontables-source-pages-v1'
VOLUMES = tuple(range(21, 31)) + tuple(range(51, 101))
FRONT_TITLES = ('御製題宋版前漢書', '御製讀漢書', '御製讀叔孫通傳', '御製讀前漢書汲黯傳',
                '御製讀蘇武傳', '御製讀蕭望之傳', '御製讀史丹傳', '御製讀翟方進傳',
                '御製讀龔遂傳', '敘例', '敘例考證', '目錄', '[提要]')
BACK_TITLES = ('[考證跋語]',)


def audit_source(cache, plan):
    """Read every fixed file, including the excluded tables; never infer completeness."""
    components = []
    with zipfile.ZipFile(io.BytesIO(cached_response(cache, plan['manifest']['source']['url'], ARCHIVE_SHA))) as zipped:
        for path in sorted(zipped.namelist()):
            file_match = re.search(r'/KR2a0007_([0-9]{3})\.txt$', path)
            if not file_match:
                continue
            raw = zipped.read(path)
            text = raw.decode('utf-8')
            base = re.search(r'^#\+PROPERTY: BASEEDITION (\S+)', text, re.M)
            marks = list(JUAN.finditer(text))
            for i, mark in enumerate(marks):
                end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
                chunk = text[mark.end():end]
                pages = list(PAGE.finditer(chunk))
                empty, issues = [], []
                depth = 0
                for j, page in enumerate(pages):
                    body = visible_text(chunk[page.end():pages[j + 1].start() if j + 1 < len(pages) else len(chunk)])
                    if not body:
                        empty.append(page.group(1))
                    for char in body:
                        if char == '(':
                            depth += 1
                        elif char == ')':
                            if depth:
                                depth -= 1
                            else:
                                issues.append(page.group(1))
                body = visible_text(chunk)
                components.append({'sourcePath': path.split('/', 1)[1], 'fileNumber': int(file_match.group(1)),
                                   'baseEdition': base.group(1) if base else None,
                                   'sourceSha256': hashlib.sha256(raw).hexdigest(),
                                   'sourceByteStart': len(text[:mark.start()].encode()),
                                   'sourceByteEnd': len(text[:end].encode()), 'juan': mark.group(1).strip(),
                                   'pages': len(pages), 'emptyPages': empty,
                                   'unclosedParentheses': depth, 'unexpectedClosings': len(issues),
                                   'closingIssuePages': issues,
                                   'unresolvedTokens': len(re.findall(r'&KR[0-9A-Za-z]+;', body)),
                                   'unlocatedOpeningText': bool(pages and visible_text(chunk[:pages[0].start()])),
                                   'openingLines': body.splitlines()[:7]})
    require(len({c['sourcePath'] for c in components}) == 102, 'Incomplete source inventory')
    table = [c for c in components if 13 <= c['fileNumber'] <= 20]
    table_body = [c for c in table if not c['juan'].endswith(('考證', '考証'))]
    return {'source': plan['manifest']['source'],
            'scope': 'Complete fixed source; source-page and character structure only, not academic completeness certification',
            'counts': {'files': 102, 'components': len(components),
                       'sourcePages': sum(c['pages'] for c in components),
                       'emptySourcePages': sum(len(c['emptyPages']) for c in components),
                       'tableComponents': len(table), 'tableAllComponentPages': sum(c['pages'] for c in table),
                       'tableBodyPages': sum(c['pages'] for c in table_body),
                       'tableEmptyBodyPages': sum(len(c['emptyPages']) for c in table_body)},
            'components': components}


def make_plan(cache, permission_sha):
    annals = annals_plan(cache, permission_sha)
    biographies = biographies_plan(cache, permission_sha)
    info = copy.deepcopy(annals['manifest'])
    units = []
    files_seen = []
    with zipfile.ZipFile(io.BytesIO(cached_response(cache, info['source']['url'], ARCHIVE_SHA))) as zipped:
        for path in sorted(zipped.namelist()):
            match = re.search(r'/KR2a0007_([0-9]{3})\.txt$', path)
            if not match:
                continue
            number = int(match.group(1))
            if number not in (*VOLUMES, 0, 101):
                continue
            files_seen.append(number)
            parsed = parse_file(path.split('/', 1)[1], zipped.read(path), allowed_volumes=VOLUMES,
                                parser=PARSER, named_components=FRONT_TITLES + BACK_TITLES)
            if number in (0, 101):
                require(tuple(u['juan'] for u in parsed) == (FRONT_TITLES if number == 0 else BACK_TITLES),
                        'Unexpected front/back components')
                require(all(u['origin']['volumeNumber'] is None for u in parsed), 'Unexpected body in front/back file')
            else:
                require(len(parsed) % 2 == 0 and all(u['origin']['volumeNumber'] == number for u in parsed),
                        'Unexpected split-volume mapping')
                for body, examination in zip(parsed[::2], parsed[1::2]):
                    require(body['origin']['kind'] == 'body-volume' and
                            examination['origin']['kind'] == 'edition-examination' and
                            examination['juan'] == body['juan'] + '考證', 'Unpaired edition examination')
            units.extend(parsed)
    require(files_seen == [0, *VOLUMES, 101], 'Missing or duplicate source file')
    require(len(units) == 168, 'Unexpected component count')
    info.update({'parser': PARSER, 'reuseEditionId': 9,
                 'previousBatchIds': [annals['batchId'], biographies['batchId']],
                 'edition': '前汉书·颜师古注·文渊阁四库本（转录待校；本批诸志、列传51–100及卷首卷末）',
                 'coverage': {'included': '诸志卷21–30、列传卷51–100及原版卷首/卷末；168组件，正文分卷、考證及附记分别编目',
                              'excludedVolumes': list(range(1, 21)) + list(range(31, 51)),
                              'reason': '本版先前已收十二本纪和列传31–50；本批后仅八表13–20整段未入。其原录426空电子页，表格结构/全文待核；其余文字仍转录待校'},
                 'reviewStatus': '转录待校；未逐叶影像校勘；古注、清代考證、御製篇及附记依原录分组件，缺字和目录/提要边界待核',
                 'unitDigests': [digest({'juan': u['juan'], 'textSha256': u['sha256'], 'origin': u['origin'],
                                        'pageOrigins': [p['origin'] for p in u['paragraphs']]}) for u in units],
                 'counts': {'units': len(units), 'bodyVolumes': len(VOLUMES),
                            'bodyComponents': sum(u['origin']['kind'] == 'body-volume' for u in units),
                            'editionExaminations': sum(u['origin']['kind'] == 'edition-examination' for u in units),
                            'frontMatter': sum(u['origin']['kind'] == 'front-matter' for u in units),
                            'backMatter': sum(u['origin']['kind'] == 'back-matter' for u in units),
                            'sourcePageBlocks': sum(len(u['paragraphs']) for u in units),
                            'emptySourcePages': sum(not bool(p['body']) for u in units for p in u['paragraphs']),
                            'unresolvedGlyphTokenOccurrences': sum(len(re.findall(r'&KR[0-9A-Za-z]+;', u['body'])) for u in units),
                            'unreviewedComponentBoundaries': sum('boundaryNote' in u['origin'] for u in units)}})
    return {'batchId': digest(info), 'manifest': info, 'units': units, 'previousPlans': [annals, biographies]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['preview', 'audit', 'apply', 'verify', 'rollback'], nargs='?', default='preview')
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--permission-sha', required=True)
    parser.add_argument('--credentials', type=Path)
    parser.add_argument('--backup-dir', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    plan = make_plan(args.cache, args.permission_sha)
    if args.operation == 'audit':
        result = audit_source(args.cache, plan)
    elif args.operation == 'preview':
        result = {k: plan[k] for k in ('batchId', 'manifest')}
    else:
        require(args.credentials is not None, 'Credentials required; never echoed')
        require(args.operation != 'apply' or args.backup_dir is not None, 'Backup directory required')
        with connect(args.credentials, readonly=args.operation == 'verify') as conn:
            result = apply(conn, plan, args.backup_dir, backup_fn=backup_existing) if args.operation == 'apply' else (
                rollback(conn, plan) if args.operation == 'rollback' else verify_chain(conn, plan))
    if args.output:
        dump(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in ('manifest', 'components')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
