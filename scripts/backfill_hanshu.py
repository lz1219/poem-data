"""Fixed WYG Hanshu first batch: twelve annals, with their separate examinations.

Offline preview is the default. Never substitutes another edition or decodes
unresolved &KR...; glyph tokens. Remaining volumes and front matter stay pending.
"""
import argparse
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

from corpus_preview import ROOT, JUAN, PAGE, chinese_number, visible_text
from research import cached_response, connect, dump
from backfill_shiji import (PERMISSION_URL, PERMISSION_TEXT, apply, rollback,
                            verify, digest, require, spans)

COMMIT = '683113d4baf6febecaf2ccb7913df87c4d68d454'
ARCHIVE_SHA = '1bb47d3cada5dc434048256bb19ffaed62fbc2dcd1f3cc264bb906c5dcf2cd17'
PARSER = 'hanshu-wyg-annals-source-pages-v1'


def parse_file(path, raw, *, allowed_volumes=range(1, 13), parser=PARSER):
    """Use explicit JUAN boundaries, preserving upper/lower and 考證 identities."""
    text = raw.decode('utf-8', errors='strict')
    require(re.search(r'^#\+PROPERTY: BASEEDITION WYG\s*$', text, re.M), 'Source is not marked WYG')
    marks = list(JUAN.finditer(text))
    require(bool(marks), 'Missing JUAN metadata')
    units = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        title = mark.group(1).strip()
        title_match = re.fullmatch(r'卷([一二三四五六七八九十百]+)(上|下)?(考證)?', title)
        require(bool(title_match), 'Unsupported title in annals batch')
        volume = chinese_number(title_match.group(1))
        require(volume in allowed_volumes, 'Volume outside selected batch')
        chunk = text[mark.end():end]
        pages = list(PAGE.finditer(chunk))
        require(bool(pages) and not visible_text(chunk[:pages[0].start()]), 'Unlocated source text')
        blocks = []
        depth = 0
        for i, page in enumerate(pages):
            stop = pages[i + 1].start() if i + 1 < len(pages) else len(chunk)
            body = visible_text(chunk[page.end():stop])
            structure, depth = spans(body, depth)
            byte_start = len(text[:mark.end()].encode()) + len(chunk[:page.start()].encode())
            byte_end = len(text[:mark.end()].encode()) + len(chunk[:stop].encode())
            blocks.append({'body': body, 'origin': {
                'pageLabel': page.group(1), 'emptyTranscription': not bool(body),
                'sourceByteStart': byte_start, 'sourceByteEnd': byte_end,
                'sourceLineStart': raw[:byte_start].count(b'\n') + 1,
                'sourceLineEnd': raw[:byte_end].count(b'\n') + (0 if raw[byte_end-1:byte_end] == b'\n' else 1),
                'segmentation': 'source-page', 'offsetUnit': 'unicode-code-point', 'spans': structure,
            }})
        require(depth == 0, 'Unclosed source note')
        labels = [p['origin']['pageLabel'] for p in blocks]
        require(len(labels) == len(set(labels)), 'Duplicate source page')
        body = '\n\n'.join(p['body'] for p in blocks)
        origin = {'sourcePath': path, 'sourceSha256': hashlib.sha256(raw).hexdigest(),
                  'sourceByteStart': len(text[:mark.start()].encode()),
                  'sourceByteEnd': len(text[:end].encode()), 'volumeNumber': volume,
                  'kind': 'edition-examination' if title_match.group(3) else 'body-volume',
                  'sourcePages': len(blocks),
                  'emptySourcePageLabels': [p['origin']['pageLabel'] for p in blocks if not p['body']],
                  'unresolvedGlyphTokens': sorted(set(re.findall(r'&KR[0-9A-Za-z]+;', body))),
                  'parser': parser, 'textStatus': 'transcription-unreviewed',
                  'noteAttribution': 'unreviewed; spans describe parentheses only; 考證 is a separate edition component'}
        units.append({'juan': title, 'body': body, 'sha256': hashlib.sha256(body.encode()).hexdigest(),
                      'origin': origin, 'paragraphs': blocks})
    return units


def make_plan(cache, permission_sha, manifest_path=ROOT / 'data/acquisition-manifest.json'):
    manifest = json.loads(manifest_path.read_text('utf-8'))
    sources = [r for r in manifest['repositories'] if r['repository'] == 'kanripo/KR2a0007']
    require(len(sources) == 1 and sources[0]['commit'] == COMMIT and sources[0]['archiveSha256'] == ARCHIVE_SHA,
            'This importer is locked to the reviewed Hanshu WYG source')
    item = sources[0]
    expected_url = 'https://codeload.github.com/kanripo/KR2a0007/zip/' + COMMIT
    require(item['url'] == expected_url, 'Unexpected fixed source URL')
    permission = cached_response(cache, PERMISSION_URL, permission_sha)
    require(PERMISSION_TEXT in permission.decode('utf-8'), 'Provider permission capture does not match')
    source = {k: item[k] for k in ('repository', 'commit', 'url', 'archiveSha256')}
    archive = cached_response(cache, source['url'], ARCHIVE_SHA)
    units = []
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        notices = [p.split('/', 1)[1] for p in zipped.namelist()
                   if re.search(r'/(?:license|copying|notice|readme)(?:\.|$)', p, re.I)]
        selected = sorted(p for p in zipped.namelist() if re.search(r'/KR2a0007_0(?:0[1-9]|1[012])\.txt$', p))
        require(len(selected) == 12, 'Expected twelve fixed annals files')
        for path in selected:
            units.extend(parse_file(path.split('/', 1)[1], zipped.read(path)))
    titles = ['卷一上', '卷一下'] + ['卷' + t for t in ['二', '三', '四', '五', '六', '七', '八', '九', '十', '十一', '十二']]
    expected_titles = [name for title in titles for name in (title, title + '考證')]
    require([u['juan'] for u in units] == expected_titles, 'Unexpected annals/examination sequence')
    info = {'parser': PARSER, 'bookId': 8, 'bookTitle': '《汉书》',
            'editionName': '前汉书·颜师古注·文渊阁四库本（Kanripo电子转录）',
            'edition': '前汉书·颜师古注·文渊阁四库本（转录待校；本批仅十二本纪及各卷考证）',
            'source': source, 'license': 'CC-BY-SA-4.0',
            'permissionBasis': {'url': PERMISSION_URL, 'sha256': permission_sha,
                                'scope': 'provider collection declaration; not a per-file license notice',
                                'archiveNoticeFiles': notices, 'humanRightsReview': 'not-recorded'},
            'attribution': 'Kanripo 漢籍リポジトリ；原字符、古注和考證保留，仅去电子页标/断行标记并按来源页编目',
            'coverage': {'included': '十二本纪：卷一上、一下及卷二至十二；每个分卷另列本版考證，共26单元',
                         'excludedVolumes': list(range(13, 101)),
                         'reason': '本批只收本纪；卷首、八表、诸志列传及考證跋语尚未入库，不认定全书完整'},
            'reviewStatus': '转录待校；未逐叶影像校勘；考證独立于班固正文；&KR…;原录缺字标记未释读',
            'unitDigests': [digest({'juan': u['juan'], 'textSha256': u['sha256'], 'origin': u['origin'],
                                   'pageOrigins': [p['origin'] for p in u['paragraphs']]}) for u in units],
            'counts': {'units': len(units), 'bodyVolumes': 12, 'bodyComponents': 13,
                       'editionExaminations': 13, 'frontMatter': 0,
                       'sourcePageBlocks': sum(len(u['paragraphs']) for u in units),
                       'emptySourcePages': sum(not bool(p['body']) for u in units for p in u['paragraphs']),
                       'unresolvedGlyphTokenOccurrences': sum(len(re.findall(r'&KR[0-9A-Za-z]+;', u['body'])) for u in units)}}
    return {'batchId': digest(info), 'manifest': info, 'units': units}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['preview', 'apply', 'verify', 'rollback'], nargs='?', default='preview')
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--permission-sha', required=True)
    parser.add_argument('--credentials', type=Path)
    parser.add_argument('--backup-dir', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    plan = make_plan(args.cache, args.permission_sha)
    if args.operation == 'preview':
        result = {k: plan[k] for k in ('batchId', 'manifest')}
    else:
        require(args.credentials is not None, 'Credentials are required, never echoed')
        if args.operation == 'apply':
            require(args.backup_dir is not None, 'A backup directory is required')
        with connect(args.credentials, readonly=args.operation == 'verify') as conn:
            result = apply(conn, plan, args.backup_dir) if args.operation == 'apply' else (
                rollback(conn, plan) if args.operation == 'rollback' else verify(conn, plan))
    if args.output:
        dump(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k != 'manifest'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
