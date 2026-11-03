"""Repair one existing corpus unit from a fixed source plan, preserving matched IDs.

Default preview prepares a recoverable backup. Apply consumes that exact backup;
source fetching, parsing and backup I/O never run inside its database transaction.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import time

from backfill_shiji import canonical, copy_rows, digest, require
from normalize_corpus import guard_references


def emit(path, operation, **fields):
    if path:
        with path.open('a', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps({'at': time.time(), 'operation': operation, **fields}, ensure_ascii=False) + '\n')


def step(conn, events, name, statement, params=()):
    start = time.monotonic()
    emit(events, 'start', step=name)
    try:
        result = conn.execute(statement, params)
    except Exception as exc:
        emit(events, 'error', step=name, seconds=round(time.monotonic()-start, 5),
             error=type(exc).__name__, sqlstate=getattr(exc, 'sqlstate', None))
        raise
    emit(events, 'finish', step=name, seconds=round(time.monotonic()-start, 5))
    return result


def validate_source(plan, volume):
    require(plan['batchId'] == digest(plan['manifest']), 'Source manifest checksum differs')
    require(len(plan['units']) == len(plan['manifest']['unitDigests']) and
            [digest(u) for u in plan['units']] == plan['manifest']['unitDigests'], 'Source unit checksums differ')
    selected = [u for u in plan['units'] if u['juan'] == volume]
    require(len(selected) == 1, 'Volume selection must be unique')
    unit = selected[0]
    require(unit.get('legacyProjection', {}).get('parser') == 'legacy-wikisource-clean-v1', 'Missing legacy source mapping')
    require(unit['body'] == '\n\n'.join(p['body'] for p in unit['paragraphs']) and
            unit['sha256'] == hashlib.sha256(unit['body'].encode()).hexdigest(), 'Body and blocks disagree')
    require(unit['sourceUrl'] == unit['origin']['sourceUrl'] and
            unit['sourceUrl'] == 'https://zh.wikisource.org/w/index.php?oldid=' + str(unit['origin']['revisionId']),
            'Missing fixed revision URL')
    return unit


def map_rows(old, source):
    """Allow restored headings and unchanged text; changed display text stays pending."""
    require(hashlib.sha256('\n'.join(p['body'] for p in old).encode()).hexdigest() ==
            source['legacyProjection']['bodySha256'], 'Fixed source does not reproduce the existing text')
    mapped, cursor = [], 0
    for block in source['paragraphs']:
        legacy = block.get('legacyText')
        identity = None
        if legacy is None:
            require(block['origin']['kind'] == 'heading', 'Only explicit source headings may create new blocks')
        else:
            require(cursor < len(old) and old[cursor]['body'] == legacy, 'Old paragraph mapping differs')
            require(legacy == block['body'], 'Display/text normalization needs a separately reviewed change')
            identity = old[cursor]['id']
            cursor += 1
        mapped.append({'id': identity, 'body': block['body'], 'origin': block['origin']})
    retired = old[cursor:]
    require([p['body'] for p in retired] == source['legacyProjection']['trailer'], 'Unexplained old paragraphs')
    return mapped, [p['id'] for p in retired]


def snapshot(conn, plan, volume, identity):
    source = validate_source(plan, volume)
    row = conn.execute('SELECT to_jsonb(t),md5(to_jsonb(t)::text) FROM text_unit t WHERE id=%s', (identity,)).fetchone()
    require(row is not None, 'Target unit missing')
    unit, unit_hash = row
    require(unit['book_id'] == plan['manifest']['bookId'] and unit['juan'] == volume, 'Wrong book or volume mapping')
    book, book_hash = conn.execute('SELECT to_jsonb(b),md5(to_jsonb(b)::text) FROM book b WHERE id=%s', (unit['book_id'],)).fetchone()
    require(book['title'] == plan['manifest']['bookTitle'], 'Wrong book identity')
    paragraphs = conn.execute('SELECT to_jsonb(p),md5(to_jsonb(p)::text) FROM paragraph p WHERE unit_id=%s ORDER BY seq', (identity,)).fetchall()
    require('\n'.join(p[0]['body'] for p in paragraphs) == unit['body'], 'Existing unit and paragraph text disagree')
    rows, retired = map_rows([p[0] for p in paragraphs], source)
    guard_references(conn, [identity])
    manifest = {**plan['manifest'], 'sourcePlanId': plan['batchId'], 'unitDigests': [digest(source)],
        'coverage': {'included': source['origin']['sourcePath'],
                     'reason': 'Only this fixed source unit was repaired; no claim of human textual collation'},
        'counts': {'units': 1, 'sourceParagraphBlocks': len(rows),
                   'headings': sum(r['origin']['kind'] == 'heading' for r in rows),
                   'editorialNotes': sum(len(r['origin']['annotations']) for r in rows)}}
    return {'format': 'corpus-repair-v1', 'book': book, 'bookHash': book_hash,
            'unit': unit, 'unitHash': unit_hash, 'paragraphs': paragraphs,
            'source': source, 'rows': rows, 'retiredParagraphIds': retired, 'manifest': manifest,
            'batchId': 'repair-' + digest({'unitId': identity, 'source': source})}


def apply(conn, data, backup_sha, events):
    from psycopg.types.json import Jsonb
    identity, book_id = data['unit']['id'], data['unit']['book_id']
    require(data['format'] == 'corpus-repair-v1', 'Unsupported backup format')
    expected_rows, expected_retired = map_rows([p[0] for p in data['paragraphs']], data['source'])
    require(expected_rows == data['rows'] and expected_retired == data['retiredParagraphIds'], 'Backup mapping changed')
    start = time.monotonic()
    with conn.transaction():
        conn.execute("SET LOCAL lock_timeout='3s'")
        conn.execute("SET LOCAL statement_timeout='8s'")
        if conn.info.server_version >= 170000:
            conn.execute("SET LOCAL transaction_timeout='15s'")
        require(conn.execute('SELECT pg_try_advisory_xact_lock(730015,%s)', (book_id,)).fetchone()[0], 'Book is being processed')
        existing = conn.execute("SELECT result FROM corpus_ingest_batch WHERE batch_id=%s AND state='applied'", (data['batchId'],)).fetchone()
        if existing:
            return {'operation': 'already-applied; no writes', **existing[0]}
        for name, query, key, expected in [
            ('lock-book', 'SELECT md5(to_jsonb(t)::text) FROM book t WHERE id=%s FOR UPDATE', book_id, data['bookHash']),
            ('lock-unit', 'SELECT md5(to_jsonb(t)::text) FROM text_unit t WHERE id=%s FOR UPDATE', identity, data['unitHash'])]:
            actual = step(conn, events, name, query, (key,)).fetchone()
            require(actual is not None and actual[0] == expected, 'Target changed since backup: ' + name)
        step(conn, events, 'lock-paragraphs', 'SELECT id FROM paragraph WHERE unit_id=%s ORDER BY id FOR UPDATE', (identity,)).fetchall()
        actual = conn.execute('SELECT to_jsonb(p),md5(to_jsonb(p)::text) FROM paragraph p WHERE unit_id=%s ORDER BY seq', (identity,)).fetchall()
        require(json.loads(json.dumps(actual)) == data['paragraphs'], 'Paragraphs changed since backup')
        guard_references(conn, [identity])
        source = data['source']
        # Update the one reading record before adding references; keep every
        # other unit, existing main-text body and matched paragraph ID intact.
        step(conn, events, 'update-unit', 'UPDATE text_unit SET body=%s,body_simplified=%s,sha256=%s,source_url=%s WHERE id=%s',
             (source['body'],source.get('bodySimplified'),source['sha256'],source['sourceUrl'],identity))
        new_count = sum(r['id'] is None for r in data['rows'])
        new_ids = iter(r[0] for r in conn.execute("SELECT nextval(pg_get_serial_sequence('paragraph','id')) FROM generate_series(1,%s)", (new_count,)))
        rows = [{**r, 'id': r['id'] if r['id'] is not None else next(new_ids)} for r in data['rows']]
        edition_id = step(conn, events, 'create-edition', 'INSERT INTO edition(book_id,name,kind,note) VALUES(%s,%s,%s,%s) RETURNING id',
            (book_id,source['origin']['sourcePath']+'·固定修订'+str(source['origin']['revisionId']),
             '电子转录',data['manifest']['reviewStatus'])).fetchone()[0]
        step(conn, events, 'create-batch', "INSERT INTO corpus_ingest_batch(batch_id,book_id,edition_id,state,manifest,result) VALUES(%s,%s,%s,'applied',%s,'{}')",
             (data['batchId'],book_id,edition_id,Jsonb(data['manifest'])))
        step(conn, events, 'retire-source-trailer', 'DELETE FROM paragraph WHERE unit_id=%s AND id=ANY(%s)', (identity,data['retiredParagraphIds']))
        offset = max([p[0]['seq'] for p in data['paragraphs']] + [len(rows)]) + 1
        step(conn, events, 'move-sequence-keys', 'UPDATE paragraph SET seq=seq+%s WHERE unit_id=%s', (offset,identity))
        conn.execute('CREATE TEMP TABLE repair_sequence(id integer PRIMARY KEY,seq integer NOT NULL) ON COMMIT DROP')
        copy_rows(conn, 'COPY repair_sequence(id,seq) FROM STDIN', ((r['id'],seq) for seq,r in enumerate(rows,1)))
        step(conn, events, 'restore-sequence-keys', 'UPDATE paragraph p SET seq=s.seq FROM repair_sequence s WHERE p.id=s.id AND p.unit_id=%s', (identity,))
        old_ids = {p[0]['id'] for p in data['paragraphs']}
        copy_start = time.monotonic()
        emit(events, 'start', step='copy-headings-and-origins')
        copy_rows(conn, 'COPY paragraph(id,unit_id,seq,body) FROM STDIN',
                  ((r['id'],identity,seq,r['body']) for seq,r in enumerate(rows,1) if r['id'] not in old_ids))
        copy_rows(conn, 'COPY corpus_paragraph_origin(paragraph_id,batch_id,metadata) FROM STDIN',
                  ((r['id'],data['batchId'],Jsonb(r['origin'])) for r in rows))
        emit(events, 'finish', step='copy-headings-and-origins', seconds=round(time.monotonic()-copy_start,5))
        step(conn, events, 'create-unit-origin', 'INSERT INTO corpus_unit_origin(unit_id,batch_id,edition_id,ordinal,metadata) VALUES(%s,%s,%s,1,%s)',
             (identity,data['batchId'],edition_id,Jsonb(source['origin'])))
        result = {'unitId': identity, 'editionId': edition_id, 'paragraphIds': [r['id'] for r in rows],
            'retainedParagraphIds': [r['id'] for r in rows if r['id'] in old_ids],
            'newHeadingIds': [r['id'] for r in rows if r['id'] not in old_ids],
            'retiredParagraphIds': data['retiredParagraphIds'], 'backupSha256': backup_sha}
        step(conn, events, 'record-result', 'UPDATE corpus_ingest_batch SET result=%s WHERE batch_id=%s', (Jsonb(result),data['batchId']))
    result.update({'operation': 'applied', 'transactionSeconds': round(time.monotonic()-start,5)})
    emit(events, 'committed', transactionSeconds=result['transactionSeconds'])
    return result


def verify(conn, data):
    identity, source = data['unit']['id'], data['source']
    row = conn.execute('SELECT book_id,juan,body,body_simplified,sha256,source_url FROM text_unit WHERE id=%s', (identity,)).fetchone()
    require(row == (data['unit']['book_id'],source['juan'],source['body'],source.get('bodySimplified'),source['sha256'],source['sourceUrl']), 'Repaired unit differs')
    rows = conn.execute('SELECT p.id,p.seq,p.body,o.metadata,o.batch_id FROM paragraph p LEFT JOIN corpus_paragraph_origin o ON o.paragraph_id=p.id WHERE p.unit_id=%s ORDER BY p.seq', (identity,)).fetchall()
    require(len(rows) == len(data['rows']) and [r[1] for r in rows] == list(range(1,len(rows)+1)), 'Paragraph scope or sequence differs')
    require(all(actual[2:] == (expected['body'],expected['origin'],data['batchId']) and
                (expected['id'] is None or actual[0] == expected['id']) for actual,expected in zip(rows,data['rows'])),
            'Paragraph IDs, text or provenance differs')
    batch = conn.execute('SELECT state,result,manifest,edition_id FROM corpus_ingest_batch WHERE batch_id=%s', (data['batchId'],)).fetchone()
    require(batch is not None and batch[0] == 'applied' and batch[2] == data['manifest'] and
            batch[1]['paragraphIds'] == [r[0] for r in rows], 'Batch manifest or paragraph identities differ')
    origin = conn.execute('SELECT metadata,batch_id,edition_id FROM corpus_unit_origin WHERE unit_id=%s', (identity,)).fetchone()
    require(origin == (source['origin'],data['batchId'],batch[3]), 'Unit provenance differs')
    return {'verifiedBlocks': len(rows), 'retainedMainTextIds': sum(r['id'] is not None for r in data['rows']),
        'restoredHeadings': sum(r['id'] is None for r in data['rows']),
        'editorialNotes': sum(len(r['origin']['annotations']) for r in data['rows']),
        'fixedRevisionId': source['origin']['revisionId']}


def main():
    import psycopg
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('preview','apply','verify'), nargs='?', default='preview')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--unit-id', type=int)
    parser.add_argument('--volume')
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--backup-sha')
    parser.add_argument('--events', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    dsn = os.environ.get('CORPUS_DSN')
    require(bool(dsn), 'Use the existing protected CORPUS_DSN')
    try:
        if args.operation == 'preview':
            require(args.plan is not None and args.unit_id is not None and args.volume, 'Preview requires a plan and explicit target mapping')
            plan = json.loads(args.plan.read_text('utf-8'))
            with psycopg.connect(dsn, autocommit=True, options='-c statement_timeout=10000') as conn:
                with conn.transaction():
                    conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                    data = json.loads(canonical(snapshot(conn, plan, args.volume, args.unit_id)))
            require(not args.backup.exists(), 'Do not overwrite a backup')
            args.backup.parent.mkdir(parents=True,exist_ok=True)
            raw = gzip.compress(canonical(data), compresslevel=1)
            with args.backup.open('xb') as stream:
                stream.write(raw)
            require(json.loads(gzip.decompress(args.backup.read_bytes())) == data, 'Backup readback differs')
            result = {'operation':'preview','unitId':args.unit_id,'newHeadings':sum(r['id'] is None for r in data['rows']),
                      'retainedParagraphs':sum(r['id'] is not None for r in data['rows']),
                      'retiredParagraphs':len(data['retiredParagraphIds']),
                      'backupSha256':hashlib.sha256(raw).hexdigest(),'backupBytes':len(raw)}
        else:
            raw = args.backup.read_bytes()
            require(hashlib.sha256(raw).hexdigest() == args.backup_sha, 'Fixed backup checksum required')
            data = json.loads(gzip.decompress(raw))
            result = {}
            if args.operation == 'apply':
                require(args.events is not None, 'Apply requires a persistent events path')
                with psycopg.connect(dsn,autocommit=True,application_name='corpus-repair') as conn:
                    result = apply(conn,data,args.backup_sha,args.events)
            with psycopg.connect(dsn,autocommit=True,options='-c default_transaction_read_only=on -c statement_timeout=10000') as conn:
                result.update(verify(conn,data))
        if args.output:
            args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
        print(json.dumps(result,ensure_ascii=False))
    except Exception as exc:
        emit(args.events, 'failed', error=type(exc).__name__, sqlstate=getattr(exc,'sqlstate',None))
        raise


if __name__ == '__main__':
    main()
