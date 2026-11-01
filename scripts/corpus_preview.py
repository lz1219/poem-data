"""Inspect a fixed Kanripo archive without network requests or database writes.

This preview records source units/pages, not reconstructed natural paragraphs.
It deliberately does not determine copyright clearance or academic correctness.
"""
import argparse
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

from research import cached_response, dump

ROOT = Path(__file__).resolve().parents[1]
JUAN = re.compile(r'^#\+PROPERTY: JUAN (.+)$', re.MULTILINE)
PAGE = re.compile(r'<pb:([^>]+)>')
FILE = re.compile(r'(KR2a0002_([0-9]{3})\.txt)$')


def chinese_number(text):
    digits = dict(zip('零一二三四五六七八九', range(10)))
    result = digit = 0
    for char in text:
        if char in digits:
            digit = digits[char]
        elif char in '十百':
            result += (digit or 1) * {'十': 10, '百': 100}[char]
            digit = 0
        else:
            raise ValueError(f'Unsupported volume number: {text}')
    return result + digit


def visible_text(raw):
    # Only known transport/layout markers are removed. Original character forms,
    # parentheses, slash markers and line wrapping remain available for inspection.
    raw = PAGE.sub('', raw)
    return '\n'.join(line.replace('¶', '') for line in raw.splitlines()
                     if not line.startswith(('#+', '# -*- mode:'))).strip()


def inspect_file(path, raw):
    text = raw.decode('utf-8', errors='strict')
    marks = list(JUAN.finditer(text))
    if not marks:
        raise ValueError(f'Missing JUAN metadata: {path}')
    units = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        chunk = text[mark.end():end]
        pages = list(PAGE.finditer(chunk))
        if not pages or visible_text(chunk[:pages[0].start()]):
            raise ValueError(f'Unlocated source text: {path}/{mark.group(1)}')
        title = mark.group(1).strip()
        volume = chinese_number(title[1:]) if title.startswith('卷') else None
        depth = 0
        unexpected_closings = 0
        nonempty_pages = 0
        crossing_pages = 0
        page_labels = []
        empty_page_labels = []
        closing_issue_pages = []
        for n, page in enumerate(pages):
            stop = pages[n + 1].start() if n + 1 < len(pages) else len(chunk)
            body = visible_text(chunk[page.end():stop])
            nonempty_pages += bool(body)
            if not body:
                empty_page_labels.append(page.group(1))
            crossing_pages += depth > 0
            page_labels.append(page.group(1))
            for char in body:
                if char == '(':
                    depth += 1
                elif char == ')':
                    if depth:
                        depth -= 1
                    else:
                        unexpected_closings += 1
                        closing_issue_pages.append(page.group(1))
        body = visible_text(chunk)
        units.append({
            'sourcePath': path,
            'sourceSha256': hashlib.sha256(raw).hexdigest(),
            'sourceByteStart': len(text[:mark.start()].encode('utf-8')),
            'sourceByteEnd': len(text[:end].encode('utf-8')),
            'juan': title,
            'volumeNumber': volume,
            'kind': 'body-volume' if volume is not None else 'front-matter',
            'sourcePages': len(pages),
            'nonemptySourcePages': nonempty_pages,
            'emptySourcePageLabels': empty_page_labels,
            'firstPage': page_labels[0],
            'lastPage': page_labels[-1],
            'pageLabelsUnique': len(page_labels) == len(set(page_labels)),
            'characters': len(body),
            'displaySha256': hashlib.sha256(body.encode('utf-8')).hexdigest(),
            'openingLines': body.splitlines()[:6],
            'parenthesisAudit': {
                'unclosed': depth, 'unexpectedClosings': unexpected_closings,
                'unexpectedClosingPages': closing_issue_pages,
                'pagesStartingInsideParentheses': crossing_pages,
                'interpretation': 'Structural hint only; parentheses do not establish authorship.'
            }
        })
    return units


def preview(manifest, cache):
    source = next(x for x in manifest['repositories']
                  if x.get('repository') == 'kanripo/KR2a0002')
    if not re.fullmatch(r'[a-f0-9]{40}', source['commit']):
        raise ValueError('A full fixed Git commit is required')
    archive = cached_response(cache, source['url'], source['archiveSha256'])
    units = []
    files = 0
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        for name in sorted(zipped.namelist()):
            if not FILE.search(name):
                continue
            files += 1
            path = name.split('/', 1)[1]
            units.extend(inspect_file(path, zipped.read(name)))
    volumes = [u['volumeNumber'] for u in units if u['volumeNumber'] is not None]
    checks = {
        'fileCountMatchesManifest': files == source['textFiles'],
        'bodyVolumesExactly1Through130': sorted(volumes) == list(range(1, 131)),
        'frontMatterExactlyTiYaoAndXu': [u['juan'] for u in units
                                      if u['volumeNumber'] is None] == ['提要', '序'],
        'pageLabelsUniqueWithinUnits': all(u['pageLabelsUnique'] for u in units),
    }
    issues = [{'sourcePath': u['sourcePath'], 'juan': u['juan'],
               **u['parenthesisAudit']} for u in units
              if u['parenthesisAudit']['unclosed'] or u['parenthesisAudit']['unexpectedClosings']]
    return {
        'schemaVersion': 1, 'operation': 'read-only-preview',
        'target': {'bookId': 7, 'bookTitle': '《史记》'},
        'source': {k: source[k] for k in ('repository', 'commit', 'archiveSha256', 'url')},
        'edition': '史记集解·文渊阁四库本（Kanripo转录待校，含古注）',
        'textStatus': '转录待校；未完成影像逐叶对校',
        'segmentation': 'source-page; not natural paragraph',
        'summary': {'files': files, 'bodyVolumes': len(volumes),
                    'frontMatterUnits': len(units) - len(volumes),
                    'catalogUnits': len(units),
                    'sourcePages': sum(u['sourcePages'] for u in units),
                    'emptySourcePages': sum(len(u['emptySourcePageLabels']) for u in units),
                    'unitsWithEmptySourcePages': sum(bool(u['emptySourcePageLabels']) for u in units)},
        'checks': checks, 'parenthesisIssues': issues,
        'coverageCaveat': '目录卷号齐全不能证明文本完整；空电子页标须核对影像，特别是表格。',
        'writeStatus': 'not-imported; permission and transformation review required',
        'units': units,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'data/acquisition-manifest.json')
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = preview(json.loads(args.manifest.read_text('utf-8')), args.cache)
    dump(args.output, result)
    print(json.dumps({k: result[k] for k in ('summary', 'checks')}, ensure_ascii=False))
    print(f'Parenthesis issues requiring inspection: {len(result["parenthesisIssues"])}')
    if not all(result['checks'].values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
