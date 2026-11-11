"""Fixed JSON poetry -> existing corpus_poem, with traceable, reversible batches.

Default offline preview. The first audited adapter is chinese-poetry Songci at
the exact commit and file set in the selection; no arbitrary source import.
"""
import argparse
import hashlib
import json
import re
from importlib.metadata import version
from pathlib import Path

from research import ROOT, cached_response, connect, dump, now
from backfill_shiji import (require, digest, backup, batch, has_schema,
                            fingerprints, new_fingerprints, guard_references, allocate, copy_rows)

REPOSITORY = 'chinese-poetry/chinese-poetry'
COMMIT = 'b8594f81a89752241442f2ce267d6f66f96704ee'


def parse_records(rows, location, seen):
    """Only identical complete records share an ID; preserve every location."""
    result = []
    for index, record in enumerate(rows):
        require(isinstance(record, dict), 'Source record must be an object')
        require(set(record) <= {'author', 'rhythmic', 'paragraphs', 'tags', 'prologue'}, 'Unknown source field')
        require(all(isinstance(record.get(k), str) and record[k] for k in ('author', 'rhythmic')), 'Missing author/ci tune')
        require(isinstance(record.get('paragraphs'), list) and record['paragraphs'] and
                all(isinstance(p, str) for p in record['paragraphs']), 'Invalid source paragraphs')
        require('tags' not in record or (isinstance(record['tags'], list) and
                all(isinstance(t, str) for t in record['tags'])), 'Invalid source tags')
        require('prologue' not in record or isinstance(record['prologue'], str), 'Invalid source prologue')
        key = digest(record)
        pointer = {**location, 'jsonPointer': '/' + str(index)}
        if key in seen:
            seen[key]['origin']['locations'].append(pointer)
            continue
        position, boundaries = 0, []
        for part in record['paragraphs']:
            boundaries.append({'start': position, 'end': position + len(part)})
            position += len(part) + 1
        body = '\n'.join(record['paragraphs'])
        require(bool(body.strip()), 'Empty source poem')
        item = {'author': record['author'], 'title': record['rhythmic'], 'body': body,
                'ext_id': 'chinese-poetry@' + COMMIT + ':' + key,
                'origin': {'sourceRecordSha256': key, 'locations': [pointer], 'paragraphs': boundaries,
                           'titleKind': 'source-ci-tune', 'sourceFields': list(record),
                           'reviewStatus': '转录待校；底本、归属及文字未作具名人工审校',
                           'unresolvedReplacementOffsets': [i for i, c in enumerate(body) if c == '\ufffd']}}
        for field in ('tags', 'prologue'):
            if field in record:
                item['origin'][field] = record[field]
        seen[key] = item
        result.append(item)
    return result


def make_plan(cache, selection):
    source = selection['source']
    require((source['repository'], source['commit'], selection['bookId'], selection['bookTitle']) ==
            (REPOSITORY, COMMIT, 53, '全宋词'), 'Unsupported source or book mapping')
    license_capture = selection['licenseCapture']
    notice = cached_response(cache, license_capture['url'], license_capture['sha256']).decode()
    require(notice.startswith('The MIT License (MIT)') and 'Copyright (c) 2016 JackeyGao' in notice,
            'Fixed provider license not present')
    require(len(selection['files']) == 22, 'Expected 22 fixed Songci files')
    poems, seen, ordered_files = [], {}, []
    for file in selection['files']:
        match = re.fullmatch(r'宋词/ci\.song\.(\d+)\.json', file['path'])
        require(match is not None, 'Unexpected collection file')
        ordered_files.append(int(match[1]))
        capture = file['capture']
        raw = cached_response(cache, capture['url'], capture['sha256'])
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        require(blob == file['gitBlobSha'], 'Git blob identity differs')
        from urllib.parse import quote
        require(capture['url'] == f'https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/' + quote(file['path']),
                'File capture is not the pinned repository path')
        rows = json.loads(raw)
        require(len(rows) == (50 if int(match[1]) == 21000 else 1000), 'Source record count differs')
        location = {'path': file['path'], 'sourceSha256': capture['sha256'], 'gitBlobSha': blob,
                    'url': f'https://github.com/{REPOSITORY}/blob/{COMMIT}/' + quote(file['path'])}
        poems.extend(parse_records(rows, location, seen))
    require(ordered_files == list(range(0, 21001, 1000)), 'Files not in fixed numeric order')
    require(len(poems) == 21046, 'Exact full-record duplicate count differs')
    info = {'parser': 'fixed-json-poetry-v1', 'bookId': 53, 'bookTitle': '全宋词',
            'editionName': '宋词·chinese-poetry固定电子汇编（底本及文字待核）',
            'source': source, 'files': selection['files'], 'licenseCapture': license_capture,
            'license': 'MIT (repository provider declaration; upstream base edition not established)',
            'attribution': 'chinese-poetry/chinese-poetry contributors; retain JackeyGao MIT notice',
            'reviewStatus': '转录待校；非核定全宋词，纸本底本与网络上游逐条对应待核',
            'coverage': {'included': '固定提交ci.song.0至21000共22文件；仅完整相同记录合并来源位置',
                         'reason': '来源记录数不是独立作品数或完整性证明；序文/标签归属待核，不自动成为译注、事实或古人评点'},
            'upstreamCaptures': selection['upstreamCaptures'],
            'conversion': {'engine': 'OpenCC', 'version': version('opencc'), 'config': 't2s.json', 'scope': 'derived search/display fields; originals retained'},
            'recordsDigest': digest(poems),
            'counts': {'poems': len(poems), 'sourceRecords': sum(len(p['origin']['locations']) for p in poems),
                       'exactDuplicateLocations': sum(len(p['origin']['locations']) - 1 for p in poems),
                       'replacementCharacterRecords': sum(bool(p['origin']['unresolvedReplacementOffsets']) for p in poems),
                       'recordsWithTags': sum('tags' in p['origin'] for p in poems),
                       'recordsWithPrologue': sum('prologue' in p['origin'] for p in poems)}}
    return {'batchId': digest(info), 'manifest': info, 'poems': poems}


def verify(conn, plan):
    info, result, state = batch(conn, plan['batchId'])
    require(state == 'applied' and info == plan['manifest'], 'Batch state or manifest changed')
    require(new_fingerprints(conn, result) == result['newFingerprints'], 'Imported rows were changed or deleted')
    require(conn.execute('SELECT count(*) FROM corpus_poem_origin WHERE batch_id=%s',
                         (plan['batchId'],)).fetchone()[0] == len(plan['poems']), 'Unexpected source row count')
    # Full metadata can exceed a single result-transfer timeout. Bound each
    # indexed ordinal range without changing the surrounding transaction.
    for start in range(0, len(plan['poems']), 128):
        end = min(start + 128, len(plan['poems']))
        rows = conn.execute('''SELECT p.author,p.title,p.body,p.ext_id,o.metadata FROM public.corpus_poem p
            JOIN public.corpus_poem_origin o ON o.poem_id=p.id
            WHERE o.batch_id=%s AND o.ordinal>%s AND o.ordinal<=%s ORDER BY o.ordinal''',
            (plan['batchId'], start, end)).fetchall()
        expected = [(p['author'], p['title'], p['body'], p['ext_id'], p['origin']) for p in plan['poems'][start:end]]
        require(rows == expected, 'Poems or complete source metadata differ from fixed files')
    return {'batchId': plan['batchId'], 'sourceRoundTrip': 'passed', 'counts': info['counts']}


def apply(conn, plan, folder):
    from psycopg.types.json import Jsonb
    from opencc import OpenCC
    conn.execute('SELECT pg_advisory_xact_lock(730015,%s)', (plan['manifest']['bookId'],))
    if has_schema(conn):
        row = conn.execute('SELECT state FROM corpus_ingest_batch WHERE batch_id=%s', (plan['batchId'],)).fetchone()
        if row and row[0] == 'applied':
            return {**verify(conn, plan), 'operation': 'already-applied; no writes'}
    conn.execute('SELECT id FROM book WHERE id=%s FOR UPDATE', (plan['manifest']['bookId'],)).fetchall()
    require(conn.execute('SELECT count(*) FROM corpus_poem WHERE book_id=%s', (plan['manifest']['bookId'],)).fetchone()[0] == 0,
            'Target already has untracked poems; refuse merge')
    before, backup_sha = backup(conn, folder, plan)
    for name in ('0001_corpus_origins.sql', '0002_corpus_poem_origins.sql'):
        conn.execute((ROOT / 'server/corpus/sql' / name).read_text('utf-8'))
    edition = conn.execute('INSERT INTO edition(book_id,name,kind,note) VALUES(%s,%s,%s,%s) RETURNING id',
        (plan['manifest']['bookId'], plan['manifest']['editionName'], '电子汇编', plan['manifest']['reviewStatus'])).fetchone()[0]
    ids = allocate(conn, 'corpus_poem', len(plan['poems']))
    result = {'poemIds': ids, 'unitIds': [], 'paragraphIds': [], 'editionIds': [edition],
              'backupSha256': backup_sha, 'publicBefore': before['publicBefore']}
    conn.execute('''INSERT INTO corpus_ingest_batch(batch_id,book_id,edition_id,state,manifest,result)
        VALUES(%s,%s,%s,'applied',%s,%s) ON CONFLICT(batch_id) DO UPDATE
        SET state='applied',edition_id=EXCLUDED.edition_id,result=EXCLUDED.result''',
        (plan['batchId'], plan['manifest']['bookId'], edition, Jsonb(plan['manifest']), Jsonb(result)))
    cc = OpenCC('t2s.json')
    copy_rows(conn, '''COPY corpus_poem(id,book_id,genre,author,title,body,body_simplified,ext_id,
        author_simplified,title_display,title_simp) FROM STDIN''',
        ((i, 53, '词', p['author'], p['title'], p['body'], cc.convert(p['body']), p['ext_id'],
          cc.convert(p['author']), p['title'], cc.convert(p['title'])) for i, p in zip(ids, plan['poems'])))
    copy_rows(conn, 'COPY corpus_poem_origin(poem_id,batch_id,edition_id,ordinal,metadata) FROM STDIN',
        ((i, plan['batchId'], edition, n, Jsonb(p['origin'])) for n, (i, p) in enumerate(zip(ids, plan['poems']), 1)))
    require(fingerprints(conn, result) == before['publicBefore'], 'Original corpus changed')
    result['newFingerprints'] = new_fingerprints(conn, result)
    conn.execute('UPDATE corpus_ingest_batch SET result=%s,events=events || %s::jsonb WHERE batch_id=%s',
        (Jsonb(result), Jsonb([{'operation': 'apply', 'at': now()}]), plan['batchId']))
    return {**verify(conn, plan), 'operation': 'applied', 'originalRowsUnchanged': True}


def rollback(conn, plan):
    from psycopg.types.json import Jsonb
    conn.execute('SELECT pg_advisory_xact_lock(730015,%s)', (plan['manifest']['bookId'],))
    row = conn.execute('SELECT result,state FROM corpus_ingest_batch WHERE batch_id=%s FOR UPDATE', (plan['batchId'],)).fetchone()
    require(row is not None and row[1] == 'applied', 'Batch is not applied')
    result = row[0]
    conn.execute('SELECT id FROM edition WHERE id=ANY(%s) ORDER BY id FOR UPDATE', (result['editionIds'],)).fetchall()
    conn.execute('SELECT id FROM corpus_poem WHERE id=ANY(%s) ORDER BY id FOR UPDATE', (result['poemIds'],)).fetchall()
    conn.execute('SELECT poem_id FROM corpus_poem_origin WHERE batch_id=%s ORDER BY poem_id FOR UPDATE', (plan['batchId'],)).fetchall()
    verify(conn, plan)
    guard_references(conn, plan, result)
    preserved = fingerprints(conn, result)
    conn.execute('DELETE FROM corpus_poem_origin WHERE batch_id=%s', (plan['batchId'],))
    conn.execute('DELETE FROM corpus_poem WHERE id=ANY(%s)', (result['poemIds'],))
    conn.execute("UPDATE corpus_ingest_batch SET state='rolled-back',edition_id=NULL,events=events || %s::jsonb WHERE batch_id=%s",
        (Jsonb([{'operation': 'rollback', 'at': now()}]), plan['batchId']))
    conn.execute('DELETE FROM edition WHERE id=ANY(%s)', (result['editionIds'],))
    require(fingerprints(conn) == preserved, 'Rollback changed original data')
    return {'batchId': plan['batchId'], 'operation': 'rolled-back', 'originalRowsUnchanged': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('preview', 'apply', 'verify', 'rollback'), nargs='?', default='preview')
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--credentials', type=Path)
    parser.add_argument('--backup-dir', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    plan = make_plan(args.cache, json.loads(args.selection.read_text('utf-8')))
    result = {k: plan[k] for k in ('batchId', 'manifest')}
    if args.operation != 'preview':
        require(args.credentials is not None, 'Private credentials required; never echoed')
        require(args.operation != 'apply' or args.backup_dir is not None, 'Backup directory required')
        with connect(args.credentials, readonly=args.operation == 'verify') as conn:
            result = apply(conn, plan, args.backup_dir) if args.operation == 'apply' else (
                verify(conn, plan) if args.operation == 'verify' else rollback(conn, plan))
    if args.output:
        dump(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k != 'manifest'}, ensure_ascii=False))
