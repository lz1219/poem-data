"""Normalize an audited existing reading edition on the database server.

First adapter: book 80, 294 existing Wikisource volumes. Preview exports one
recoverable backup; apply uses that fixed backup in one short transaction.
No remote downloads, text conversion, or full-library verification in the lock.
Preview title mappings are suggestions only: apply preserves every preferred
unit's title and volume key; public label formatting belongs to the reader.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import time


def require(condition, message):
    if not condition:
        raise ValueError(message)


def chinese_number(value):
    total = digit = 0
    digits = {c: i for i, c in enumerate('零一二三四五六七八九')}
    for char in value:
        if char in digits:
            digit = digits[char]
        elif char in '十百千':
            total += (digit or 1) * {'十': 10, '百': 100, '千': 1000}[char]
            digit = 0
        else:
            raise ValueError('Unsupported source volume number')
    return total + digit


def source_titles(raw_units, warnings=None):
    result = {}
    for row in raw_units:
        text = re.sub(r'\s+', '', (row['body'] or '')[:1200])
        if row['juan'] == 'KR2b0007_000':
            require('提要' in text[:100], 'Unexpected front-matter identity')
            continue
        volume = re.search(r'資治通鑑[卷巻]([一二三四五六七八九十百千零]+)', text)
        if not volume:
            continue
        number = chinese_number(volume[1])
        if row['juan'] != f'KR2b0007_{number:03d}':
            if warnings is not None:
                warnings.append({'filename': row['juan'], 'heading': volume[0],
                                 'action': 'Do not use inconsistent old heading for the preferred title'})
            continue
        require(number not in result, 'Duplicate source volume heading')
        section = re.search(r'(?:後梁|後唐|後晉|後漢|後周|周|秦|漢|魏|晉|宋|齊|梁|陳|隋|唐)紀[一二三四五六七八九十百千]+', text)
        result[number] = '卷' + volume[1] + (' · ' + section[0] if section else '')
    return result


def make_changes(units, warnings=None):
    raw = [u for u in units if u['edition'] == 'Kanripo KR2b0007 / 四庫全書文淵閣本']
    preferred = [u for u in units if u['edition'] == '維基文庫 標點本']
    require(len(units) == 589 and len(raw) == 295 and len(preferred) == 294, 'Existing edition scope changed')
    require(all(not u['punctuated'] and u['source_url'] == 'https://github.com/kanripo/KR2b0007' for u in raw),
            'Unexpected original-source status')
    titles = source_titles(raw, warnings)
    changes, numbers = [], []
    from urllib.parse import unquote, urlparse
    for unit in preferred:
        match = re.fullmatch(r'卷(\d{3})', unit['juan'])
        require(match is not None and unit['punctuated'] and bool(unit['body']), 'Unsupported preferred volume')
        number = int(match[1])
        url = urlparse(unit['source_url'] or '')
        require(url.scheme == 'https' and url.netloc == 'zh.wikisource.org' and
                unquote(url.path) == '/wiki/資治通鑑/' + unit['juan'], 'Preferred source/volume mismatch')
        numbers.append(number)
        changes.append({'id': unit['id'], 'oldJuan': unit['juan'], 'newJuan': str(number),
                        'oldTitle': unit['title'], 'newTitle': titles.get(number, unit['juan'])})
    require(sorted(numbers) == list(range(1, 295)), 'Preferred volumes incomplete or repeated')
    return raw, preferred, changes


def snapshot(conn):
    book, book_hash = conn.execute('SELECT to_jsonb(b),md5(to_jsonb(b)::text) FROM book b WHERE id=80').fetchone()
    require(book['title'] == '資治通鑑', 'Unexpected book identity')
    units = conn.execute('SELECT to_jsonb(t),md5(to_jsonb(t)::text) FROM text_unit t WHERE book_id=80 ORDER BY id').fetchall()
    warnings = []
    raw, preferred, changes = make_changes([u[0] for u in units], warnings)
    paragraphs = conn.execute('SELECT to_jsonb(p),md5(to_jsonb(p)::text) FROM paragraph p JOIN text_unit t ON t.id=p.unit_id WHERE t.book_id=80 ORDER BY p.id').fetchall()
    return {'book': book, 'bookHash': book_hash, 'units': units, 'paragraphs': paragraphs,
            'rawIds': [u['id'] for u in raw], 'preferredIds': [u['id'] for u in preferred],
            'changes': changes, 'headingWarnings': warnings}


def fingerprint(rows):
    return hashlib.md5(''.join(r[1] for r in rows).encode()).hexdigest()


def guard_references(conn, raw_ids):
    from psycopg import sql
    known = {('paragraph', 'unit_id', 'text_unit'), ('evidence', 'unit_id', 'text_unit'),
             ('evidence', 'paragraph_id', 'paragraph'), ('person_source', 'unit_id', 'text_unit'),
             ('text_variant', 'unit_id', 'text_unit'), ('corpus_unit_origin', 'unit_id', 'text_unit'),
             ('corpus_paragraph_origin', 'paragraph_id', 'paragraph')}
    refs = conn.execute('''SELECT ns.nspname,t.relname,a.attname,target.relname,cardinality(k.conkey)
        FROM pg_constraint k JOIN pg_class t ON t.oid=k.conrelid JOIN pg_namespace ns ON ns.oid=t.relnamespace
        JOIN pg_class target ON target.oid=k.confrelid JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=k.conkey[1]
        WHERE k.contype='f' AND k.confrelid IN('public.text_unit'::regclass,'public.paragraph'::regclass)''').fetchall()
    for schema, table, field, target, width in refs:
        require(schema == 'public' and width == 1 and (table, field, target) in known,
                'Unreviewed reference prevents retirement')
        if table == 'paragraph':
            continue
        subquery = 'SELECT id FROM text_unit WHERE id=ANY(%s)' if target == 'text_unit' else 'SELECT id FROM paragraph WHERE unit_id=ANY(%s)'
        query = sql.SQL('SELECT count(*) FROM public.{} WHERE {} IN (' + subquery + ')').format(sql.Identifier(table), sql.Identifier(field))
        require(conn.execute(query, (raw_ids,)).fetchone()[0] == 0, 'Referenced original cannot be retired: ' + table)


def apply(conn, data):
    raw, preferred, changes = make_changes([u[0] for u in data['units']])
    require(data['book']['id'] == 80 and all(u[0]['book_id'] == 80 for u in data['units']), 'Wrong backup scope')
    require((data['rawIds'], data['preferredIds'], data['changes']) ==
            ([u['id'] for u in raw], [u['id'] for u in preferred], changes), 'Backup plan mismatch')
    start = time.monotonic()
    with conn.transaction():
        conn.execute("SET LOCAL lock_timeout='3s'")
        conn.execute("SET LOCAL statement_timeout='15s'")
        if conn.info.server_version >= 170000:
            conn.execute("SET LOCAL transaction_timeout='20s'")
        require(conn.execute('SELECT pg_try_advisory_xact_lock(730015,80)').fetchone()[0], 'Book is being processed')
        # Protect check-then-delete from concurrent edits and newly added FK references.
        require(conn.execute('SELECT md5(to_jsonb(b)::text) FROM book b WHERE id=80 FOR UPDATE').fetchone()[0] == data['bookHash'], 'Book changed since backup')
        conn.execute('SELECT id FROM text_unit WHERE book_id=80 ORDER BY id FOR UPDATE').fetchall()
        conn.execute('SELECT id FROM paragraph WHERE unit_id IN(SELECT id FROM text_unit WHERE book_id=80) ORDER BY id FOR UPDATE').fetchall()
        for table, condition, params, expected in [
            ('text_unit', 'book_id=80', (), data['units']),
            ('paragraph', 'unit_id IN(SELECT id FROM text_unit WHERE book_id=80)', (), data['paragraphs'])]:
            actual = conn.execute('SELECT count(*),md5(coalesce(string_agg(md5(to_jsonb(t)::text),\'\' ORDER BY id),\'\')) FROM '+table+' t WHERE '+condition, params).fetchone()
            require(actual == (len(expected), fingerprint(expected)), 'Data changed since backup: ' + table)
        guard_references(conn, data['rawIds'])
        # Existing Wiki identities are already meaningful (卷001, etc.). Keep
        # them and all text rows intact; formatting belongs to the reader.
        # Rewriting them needlessly touches the large text table's indexes.
        conn.execute('DELETE FROM paragraph WHERE unit_id=ANY(%s)', (data['rawIds'],))
        deleted = conn.execute('DELETE FROM text_unit WHERE book_id=80 AND id=ANY(%s)', (data['rawIds'],)).rowcount
        require(deleted == 295, 'Unexpected retirement count')
        conn.execute("UPDATE book SET edition=%s,source_url=%s WHERE id=80", (
            '维基文库标点转录（原导入修订未记录，待校）', 'https://zh.wikisource.org/wiki/資治通鑑'))
    return {'retiredUnits': deleted, 'retainedUnitsUpdated': 0, 'transactionSeconds': round(time.monotonic()-start, 4)}


def verify(conn, data):
    units = conn.execute('SELECT id,juan,title,md5(body),sha256,source_url FROM text_unit WHERE book_id=80 ORDER BY id').fetchall()
    require([u[0] for u in units] == data['preferredIds'], 'Preferred IDs changed')
    originals = {u[0]['id']: u[0] for u in data['units']}
    for identity, juan, title, body_md5, sha, url in units:
        old = originals[identity]
        require((juan, title) == (old['juan'], old['title']), 'Preferred identity was changed')
        require((body_md5, sha, url) == (hashlib.md5(old['body'].encode()).hexdigest(), old['sha256'], old['source_url']), 'Preferred original was changed')
    preferred_ids = set(data['preferredIds'])
    retained = [p for p in data['paragraphs'] if p[0]['unit_id'] in preferred_ids]
    actual = conn.execute("SELECT count(*),md5(coalesce(string_agg(md5(to_jsonb(p)::text),'' ORDER BY p.id),'')) FROM paragraph p JOIN text_unit t ON t.id=p.unit_id WHERE t.book_id=80").fetchone()
    require(actual == (len(retained), fingerprint(retained)), 'Preferred paragraph IDs or content changed')
    return {'retainedUnits': len(units), 'retainedParagraphs': len(retained), 'originalBodyAndIdsPreserved': True,
            'names': [{'id': u[0], 'juan': u[1], 'title': u[2]} for u in units[:3]],
            'readerTitleSuggestions': data['changes'][:3]}


if __name__ == '__main__':
    import psycopg
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('preview', 'apply', 'verify'), nargs='?', default='preview')
    parser.add_argument('--backup', type=Path, required=True)
    parser.add_argument('--backup-sha')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    dsn = os.environ.get('CORPUS_DSN')
    require(bool(dsn), 'Use the existing protected CORPUS_DSN environment')
    if args.operation == 'preview':
        with psycopg.connect(dsn, autocommit=True, options='-c default_transaction_read_only=on -c statement_timeout=15000') as conn:
            data = snapshot(conn)
            guard_references(conn, data['rawIds'])
        require(not args.backup.exists(), 'Do not overwrite a backup')
        args.backup.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False).encode()
        args.backup.write_bytes(gzip.compress(payload, compresslevel=1))
        require(json.loads(gzip.decompress(args.backup.read_bytes())) == json.loads(payload), 'Backup readback failed')
        result = {'operation': 'preview', 'bookId': 80, 'retire': len(data['rawIds']), 'keep': len(data['preferredIds']),
                  'backupSha256': hashlib.sha256(args.backup.read_bytes()).hexdigest(), 'backupBytes': args.backup.stat().st_size,
                  'examples': data['changes'][:3], 'headingWarnings': data['headingWarnings']}
    else:
        raw = args.backup.read_bytes()
        require(args.backup_sha == hashlib.sha256(raw).hexdigest(), 'Fixed backup checksum required')
        data = json.loads(gzip.decompress(raw))
        result = {}
        if args.operation == 'apply':
            with psycopg.connect(dsn, autocommit=True) as conn:
                result = apply(conn, data)
        # Full readback uses a separate, read-only connection after commit.
        with psycopg.connect(dsn, autocommit=True, options='-c default_transaction_read_only=on -c statement_timeout=15000') as conn:
            result.update(verify(conn, data))
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
