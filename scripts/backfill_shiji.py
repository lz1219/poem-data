"""Add the fixed WYG Shiji transcription to the ORIGINAL corpus, preserving old IDs.

Scope: front matter and volumes 1-12,23-130 only. The ten table volumes stay pending.
Default is offline preview. apply requires credentials, verified permission capture,
and a backup directory. verify is read-only; rollback refuses changed/dependent rows.
"""
import argparse
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

from corpus_preview import ROOT, PAGE, inspect_file, preview, visible_text
from research import cached_response, connect, dump, now

PARSER = 'shiji-wyg-source-pages-v1'
BOOK = 7
EDITION = '史记集解·文渊阁四库本（Kanripo转录待校；十表待补）'
TABLES = ('book', 'edition', 'text_unit', 'paragraph', 'corpus_poem', 'person',
          'work', 'journey', 'stop', 'claim', 'evidence', 'research_note', 'place')
PERMISSION_URL = 'https://github.com/kanripo'
PERMISSION_TEXT = 'Comprehensive collection of premodern Chinese texts. Licensed as CC BY SA 4.0.'
SOURCE_COMMIT = '73c4d2ba067d99a6de924ac952fd6921a958c7e7'
SOURCE_ARCHIVE_SHA = 'aa79474501442604f707177d2f56e739b27fabf591132e7fc841b8632b561b0e'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def require(test, message):
    if not test:
        raise ValueError(message)


def spans(text, depth=0):
    """Structural spans in Unicode code points; do not assign note authorship."""
    parts = []
    for i, char in enumerate(text):
        kind = 'source-parenthetical' if depth or char == '(' else 'source-text'
        if char == '(':
            depth += 1
        elif char == ')':
            require(depth > 0, 'Unmatched source parenthesis')
            depth -= 1
        if parts and parts[-1]['kind'] == kind:
            parts[-1]['end'] = i + 1
        else:
            parts.append({'kind': kind, 'start': i, 'end': i + 1})
    return parts, depth


def make_plan(cache, permission_sha, manifest_path=ROOT / 'data/acquisition-manifest.json'):
    manifest = json.loads(manifest_path.read_text('utf-8'))
    candidates = [s for s in manifest['repositories'] if s.get('repository') == 'kanripo/KR2a0002']
    require(len(candidates) == 1 and candidates[0]['commit'] == SOURCE_COMMIT and
            candidates[0]['archiveSha256'] == SOURCE_ARCHIVE_SHA, 'This importer is locked to the reviewed WYG source')
    audit = preview(manifest, cache)
    require(all(audit['checks'].values()), 'Source structure check failed')
    permission = cached_response(cache, PERMISSION_URL, permission_sha)
    require(PERMISSION_TEXT in permission.decode('utf-8'), 'Provider permission capture does not match')
    source = audit['source']
    archive = cached_response(cache, source['url'], source['archiveSha256'])
    units = []
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        notice_files = [p.split('/', 1)[1] for p in zipped.namelist()
                        if re.search(r'/(?:license|copying|notice|readme)(?:\.|$)', p, re.I)]
        for path in sorted(zipped.namelist()):
            if not re.search(r'/KR2a0002_[0-9]{3}\.txt$', path):
                continue
            raw = zipped.read(path)
            require(re.search(rb'^#\+PROPERTY: BASEEDITION WYG\s*$', raw, re.M), 'Source is not marked WYG')
            short = path.split('/', 1)[1]
            for unit in inspect_file(short, raw):
                if unit['volumeNumber'] in range(13, 23):
                    continue
                require(not unit['parenthesisAudit']['unclosed'] and
                        not unit['parenthesisAudit']['unexpectedClosings'], 'Source bracket issue in selected unit')
                start, end = unit['sourceByteStart'], unit['sourceByteEnd']
                chunk = raw[start:end].decode('utf-8')
                pages = list(PAGE.finditer(chunk))
                blocks = []
                depth = 0
                for i, page in enumerate(pages):
                    stop = pages[i + 1].start() if i + 1 < len(pages) else len(chunk)
                    body = visible_text(chunk[page.end():stop])
                    structure, depth = spans(body, depth)
                    byte_start = start + len(chunk[:page.start()].encode())
                    byte_end = start + len(chunk[:stop].encode())
                    blocks.append({'body': body, 'origin': {
                        'pageLabel': page.group(1), 'emptyTranscription': not bool(body),
                        'sourceByteStart': byte_start, 'sourceByteEnd': byte_end,
                        'sourceLineStart': raw[:byte_start].count(b'\n') + 1,
                        'sourceLineEnd': raw[:byte_end].count(b'\n') + (0 if raw[byte_end-1:byte_end] == b'\n' else 1),
                        'segmentation': 'source-page', 'offsetUnit': 'unicode-code-point',
                        'spans': structure,
                    }})
                require(depth == 0, 'Unclosed source note in selected unit')
                body = '\n\n'.join(p['body'] for p in blocks)
                origin = {k: unit[k] for k in ('sourcePath', 'sourceSha256', 'sourceByteStart',
                          'sourceByteEnd', 'volumeNumber', 'kind', 'sourcePages', 'emptySourcePageLabels')}
                origin.update({'parser': PARSER, 'textStatus': 'transcription-unreviewed',
                               'noteAttribution': 'unreviewed; spans describe parentheses only'})
                units.append({'juan': unit['juan'], 'body': body,
                              'sha256': hashlib.sha256(body.encode()).hexdigest(),
                              'origin': origin, 'paragraphs': blocks})
    require(len(units) == 122, 'Expected 120 body volumes and two front components')
    info = {'parser': PARSER, 'bookId': BOOK, 'edition': EDITION,
            'source': source, 'license': 'CC-BY-SA-4.0',
            'permissionBasis': {'url': PERMISSION_URL, 'sha256': permission_sha,
                                'scope': 'provider collection declaration; not a per-file license notice',
                                'archiveNoticeFiles': notice_files,
                                'humanRightsReview': 'not-recorded'},
            'attribution': 'Kanripo 漢籍リポジトリ；原录字符与古注保留，仅去电子页标/断行标记并按来源页编目',
            'coverage': {'included': '卷首提要、序；卷一至十二、卷二十三至一百三十',
                         'excludedVolumes': list(range(13, 23)),
                         'reason': '十表存在大量空电子页；待影像与其他文本核查，不跨版拼补'},
            'reviewStatus': '转录待校；未完成逐叶影像校勘；不认定全文完整',
            'unitDigests': [digest({'juan': u['juan'], 'textSha256': u['sha256'],
                                   'origin': u['origin'], 'pageOrigins': [p['origin'] for p in u['paragraphs']]}) for u in units],
            'counts': {'units': len(units), 'bodyVolumes': 120, 'frontMatter': 2,
                       'sourcePageBlocks': sum(len(u['paragraphs']) for u in units),
                       'emptySourcePages': sum(not bool(p['body']) for u in units for p in u['paragraphs'])}}
    return {'batchId': digest(info), 'manifest': info, 'units': units}


def has_schema(conn):
    return conn.execute("SELECT to_regclass('public.corpus_ingest_batch') IS NOT NULL").fetchone()[0]


def fingerprints(conn, exclusion=None):
    from psycopg import sql
    result = {}
    for table in TABLES:
        clause = sql.SQL('')
        params = ()
        if exclusion and table in ('text_unit', 'paragraph', 'edition'):
            ids = exclusion[{'text_unit': 'unitIds', 'paragraph': 'paragraphIds', 'edition': 'editionIds'}[table]]
            clause = sql.SQL(' WHERE NOT (id = ANY(%s))')
            params = (ids,)
        query = sql.SQL("SELECT count(*),md5(coalesce(string_agg(md5(to_jsonb(t)::text),'' ORDER BY id),'')) FROM public.{} t{}").format(sql.Identifier(table), clause)
        count, sha = conn.execute(query, params).fetchone()
        result[table] = {'rows': count, 'md5': sha}
    return result


def new_fingerprints(conn, result):
    from psycopg import sql
    hashes = {}
    for table, field, ids in [
        ('text_unit', 'id', result['unitIds']), ('paragraph', 'id', result['paragraphIds']),
        ('edition', 'id', result['editionIds']),
        ('corpus_unit_origin', 'unit_id', result['unitIds']),
        ('corpus_paragraph_origin', 'paragraph_id', result['paragraphIds'])]:
        query = sql.SQL("SELECT count(*),md5(coalesce(string_agg(md5(to_jsonb(t)::text),'' ORDER BY {}),'')) FROM public.{} t WHERE {}=ANY(%s)").format(sql.Identifier(field), sql.Identifier(table), sql.Identifier(field))
        count, sha = conn.execute(query, (ids,)).fetchone()
        hashes[table] = {'rows': count, 'md5': sha}
    return hashes


def batch(conn, identity):
    row = conn.execute('SELECT manifest,result,state FROM public.corpus_ingest_batch WHERE batch_id=%s', (identity,)).fetchone()
    require(row is not None, 'Unknown batch')
    return row


def verify(conn, plan):
    info, result, state = batch(conn, plan['batchId'])
    require(state == 'applied', 'Batch is not applied')
    require(info == plan['manifest'], 'Batch manifest changed')
    require(new_fingerprints(conn, result) == result['newFingerprints'], 'Imported rows were changed or deleted')
    units = conn.execute('SELECT t.id,t.juan,t.body,t.sha256 FROM public.text_unit t JOIN public.corpus_unit_origin o ON o.unit_id=t.id WHERE o.batch_id=%s ORDER BY o.ordinal', (plan['batchId'],)).fetchall()
    require(len(units) == len(plan['units']), 'Unexpected unit count')
    for actual, expected in zip(units, plan['units']):
        require(actual[1:] == (expected['juan'], expected['body'], expected['sha256']), 'Unit differs from fixed source')
        rows = conn.execute('SELECT p.body,o.metadata FROM public.paragraph p JOIN public.corpus_paragraph_origin o ON o.paragraph_id=p.id WHERE p.unit_id=%s ORDER BY p.seq', (actual[0],)).fetchall()
        require(len(rows) == len(expected['paragraphs']), 'Page-block count mismatch')
        require(all(body == p['body'] and meta == p['origin'] for (body, meta), p in zip(rows, expected['paragraphs'])), 'Page text or location mismatch')
    return {'batchId': plan['batchId'], 'state': state, 'counts': info['counts'],
            'sourceRoundTrip': 'passed', 'newRowsIntact': True}


def backup(conn, folder, plan):
    # First batch is deliberately restricted to an empty legacy book entry.
    require(conn.execute('SELECT count(*) FROM public.text_unit WHERE book_id=%s', (BOOK,)).fetchone()[0] == 0,
            'Target book already has untracked text; refuse automatic merge')
    book = conn.execute('SELECT to_jsonb(b) FROM public.book b WHERE id=%s', (BOOK,)).fetchone()
    require(book is not None and book[0]['title'] == '《史记》', 'Wrong book mapping')
    snapshot = {'batchId': plan['batchId'], 'book': book[0],
                'editions': [r[0] for r in conn.execute('SELECT to_jsonb(e) FROM public.edition e WHERE book_id=%s ORDER BY id', (BOOK,))],
                'units': [], 'paragraphs': [], 'publicBefore': fingerprints(conn), 'createdAt': now()}
    path = folder / ('corpus-before-' + plan['batchId'][:12] + '-' + now().replace(':', '-') + '.json')
    dump(path, snapshot)
    require(json.loads(path.read_text('utf-8')) == snapshot, 'Backup cannot be read back')
    return snapshot, hashlib.sha256(path.read_bytes()).hexdigest()


def allocate(conn, table, count):
    return [r[0] for r in conn.execute('SELECT nextval(pg_get_serial_sequence(%s,\'id\')) FROM generate_series(1,%s)', ('public.' + table, count))]


def copy_rows(conn, statement, rows):
    """Bound each COPY statement; paragraph's existing trigram GIN index is costly.

    All chunks remain in the ONE surrounding transaction. Do not raise or disable
    the database's statement timeout to force a large write through.
    """
    chunk = []
    size = 0

    def flush():
        with conn.cursor() as cur, cur.copy(statement) as copying:
            for item in chunk:
                copying.write_row(item)

    for row in rows:
        length = sum(len(canonical(value.obj)) if hasattr(value, 'obj') else
                     len(str(value).encode('utf-8')) for value in row) + 32
        if chunk and (len(chunk) >= 32 or size + length > 128 * 1024):
            flush()
            chunk = []
            size = 0
        chunk.append(row)
        size += length
    if chunk:
        flush()


def apply(conn, plan, backup_dir):
    from psycopg.types.json import Jsonb
    conn.execute('SELECT pg_advisory_xact_lock(730015,%s)', (BOOK,))
    if has_schema(conn):
        row = conn.execute('SELECT state FROM public.corpus_ingest_batch WHERE batch_id=%s', (plan['batchId'],)).fetchone()
        if row and row[0] == 'applied':
            result = verify(conn, plan)
            result['operation'] = 'already-applied; no writes'
            return result
    before, backup_sha = backup(conn, backup_dir, plan)
    conn.execute((ROOT / 'server/corpus/sql/0001_corpus_origins.sql').read_text('utf-8'))
    edition_id = conn.execute('INSERT INTO public.edition(book_id,name,kind,note) VALUES(%s,%s,%s,%s) RETURNING id',
                              (BOOK, '史记集解·文渊阁四库本（Kanripo电子转录）', '电子转录', EDITION)).fetchone()[0]
    ids = allocate(conn, 'text_unit', len(plan['units']))
    paragraph_ids = allocate(conn, 'paragraph', plan['manifest']['counts']['sourcePageBlocks'])
    result = {'unitIds': ids, 'paragraphIds': paragraph_ids, 'editionIds': [edition_id],
              'backupSha256': backup_sha, 'publicBefore': before['publicBefore']}
    conn.execute("INSERT INTO public.corpus_ingest_batch(batch_id,book_id,edition_id,state,manifest,result) VALUES(%s,%s,%s,'applied',%s,%s) ON CONFLICT(batch_id) DO UPDATE SET state='applied',edition_id=EXCLUDED.edition_id,result=EXCLUDED.result",
                 (plan['batchId'], BOOK, edition_id, Jsonb(plan['manifest']), Jsonb(result)))
    unit_rows = []
    for identity, unit in zip(ids, plan['units']):
        url = 'https://github.com/' + plan['manifest']['source']['repository'] + '/blob/' + plan['manifest']['source']['commit'] + '/' + unit['origin']['sourcePath']
        unit_rows.append((identity, BOOK, unit['juan'], unit['juan'], unit['body'], unit['sha256'], EDITION, url, False))
    copy_rows(conn, 'COPY public.text_unit(id,book_id,juan,title,body,sha256,edition,source_url,punctuated) FROM STDIN', unit_rows)
    copy_rows(conn, 'COPY public.corpus_unit_origin(unit_id,batch_id,edition_id,ordinal,metadata) FROM STDIN',
              ((identity, plan['batchId'], edition_id, ordinal, Jsonb(unit['origin']))
               for ordinal, (identity, unit) in enumerate(zip(ids, plan['units']), 1)))
    rows = []
    origins = []
    iterator = iter(paragraph_ids)
    for identity, unit in zip(ids, plan['units']):
        for seq, page in enumerate(unit['paragraphs'], 1):
            paragraph_id = next(iterator)
            rows.append((paragraph_id, identity, seq, page['body']))
            origins.append((paragraph_id, plan['batchId'], Jsonb(page['origin'])))
    copy_rows(conn, 'COPY public.paragraph(id,unit_id,seq,body) FROM STDIN', rows)
    copy_rows(conn, 'COPY public.corpus_paragraph_origin(paragraph_id,batch_id,metadata) FROM STDIN', origins)
    require(fingerprints(conn, result) == before['publicBefore'], 'Existing corpus rows changed during import')
    result['newFingerprints'] = new_fingerprints(conn, result)
    conn.execute('UPDATE public.corpus_ingest_batch SET result=%s,events=events || %s::jsonb WHERE batch_id=%s',
                 (Jsonb(result), Jsonb([{'operation': 'apply', 'at': now(), 'result': result}]), plan['batchId']))
    output = verify(conn, plan)
    output['operation'] = 'applied'
    output['existingCorpusRowsUnchanged'] = True
    return output


def guard_references(conn, plan, result):
    from psycopg import sql
    allowed = {'paragraph': ('id', result['paragraphIds']),
               'corpus_unit_origin': ('batch_id', [plan['batchId']]),
               'corpus_paragraph_origin': ('batch_id', [plan['batchId']]),
               'corpus_ingest_batch': ('batch_id', [plan['batchId']])}
    for table, ids in [('text_unit', result['unitIds']), ('paragraph', result['paragraphIds']), ('edition', result['editionIds'])]:
        refs = conn.execute("""SELECT n.nspname,r.relname,a.attname,cardinality(c.conkey)
            FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid
            JOIN pg_namespace n ON n.oid=r.relnamespace
            JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=c.conkey[1]
            WHERE c.contype='f' AND c.confrelid=to_regclass(%s)""", ('public.' + table,)).fetchall()
        for schema, referencing, field, width in refs:
            require(width == 1, 'Unrecognized composite dependency; refuse rollback')
            clause = sql.SQL('')
            params = [ids]
            if schema == 'public' and referencing in allowed:
                key, values = allowed[referencing]
                clause = sql.SQL(' AND NOT ({}=ANY(%s))').format(sql.Identifier(key))
                params.append(values)
            query = sql.SQL('SELECT count(*) FROM {}.{} WHERE {}=ANY(%s){}').format(sql.Identifier(schema), sql.Identifier(referencing), sql.Identifier(field), clause)
            require(conn.execute(query, params).fetchone()[0] == 0,
                    'Later reference prevents rollback: ' + schema + '.' + referencing + '.' + field)


def rollback(conn, plan):
    from psycopg import sql
    from psycopg.types.json import Jsonb
    conn.execute('SELECT pg_advisory_xact_lock(730015,%s)', (BOOK,))
    row = conn.execute('SELECT result,state FROM public.corpus_ingest_batch WHERE batch_id=%s FOR UPDATE', (plan['batchId'],)).fetchone()
    require(row is not None and row[1] == 'applied', 'Batch is not applied')
    locked_result = row[0]
    # FK writers take KEY SHARE on referenced rows; FOR UPDATE closes the gap
    # between dependency inspection and DELETE, including CASCADE/SET NULL FKs.
    for table, field, ids in [
        ('edition', 'id', locked_result['editionIds']),
        ('text_unit', 'id', locked_result['unitIds']),
        ('paragraph', 'id', locked_result['paragraphIds']),
        ('corpus_unit_origin', 'unit_id', locked_result['unitIds']),
        ('corpus_paragraph_origin', 'paragraph_id', locked_result['paragraphIds'])]:
        conn.execute(sql.SQL('SELECT {} FROM public.{} WHERE {}=ANY(%s) ORDER BY {} FOR UPDATE').format(
            sql.Identifier(field), sql.Identifier(table), sql.Identifier(field), sql.Identifier(field)), (ids,)).fetchall()
    verify(conn, plan)
    _, result, _ = batch(conn, plan['batchId'])
    guard_references(conn, plan, result)
    preserved = fingerprints(conn, result)
    conn.execute('DELETE FROM public.corpus_paragraph_origin WHERE batch_id=%s', (plan['batchId'],))
    conn.execute('DELETE FROM public.paragraph WHERE id=ANY(%s)', (result['paragraphIds'],))
    conn.execute('DELETE FROM public.corpus_unit_origin WHERE batch_id=%s', (plan['batchId'],))
    conn.execute('DELETE FROM public.text_unit WHERE id=ANY(%s)', (result['unitIds'],))
    conn.execute("UPDATE public.corpus_ingest_batch SET state='rolled-back',edition_id=NULL,events=events || %s::jsonb WHERE batch_id=%s",
                 (Jsonb([{'operation': 'rollback', 'at': now()}]), plan['batchId']))
    conn.execute('DELETE FROM public.edition WHERE id=ANY(%s)', (result['editionIds'],))
    require(fingerprints(conn) == preserved, 'Rollback changed rows outside this batch')
    return {'batchId': plan['batchId'], 'operation': 'rolled-back', 'existingCorpusRowsUnchanged': True}


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
            if args.operation == 'apply':
                result = apply(conn, plan, args.backup_dir)
            elif args.operation == 'rollback':
                result = rollback(conn, plan)
            else:
                result = verify(conn, plan)
    if args.output:
        dump(args.output, result)
    printed = {**result}
    if 'manifest' in printed:
        printed['manifest'] = {k: v for k, v in printed['manifest'].items() if k != 'unitDigests'}
    print(json.dumps(printed, ensure_ascii=False))


if __name__ == '__main__':
    main()
