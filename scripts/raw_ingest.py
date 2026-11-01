"""先落库、再整理、最后验证；完整原件保存在隔离的研究工作区。

命令：land / organize / verify / status。land、organize 默认预览，--apply 才写。
仅依赖项目已有 psycopg 和 Python 标准库，不修改公开阅读表。
"""
import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath

from research import ROOT, connect, dump, now, read, cached_response

GIT_PARSER = 'kanripo-source-pages-v3'
WIKI_PARSER = 'wikisource-revision-v1'
PARSER = 'research-source-pages-v5'
SUPPORTED_PARSERS = [GIT_PARSER, WIKI_PARSER]
PUBLIC_TABLES = ['book', 'text_unit', 'paragraph', 'corpus_poem', 'person', 'work',
                 'journey', 'stop', 'claim', 'evidence', 'research_note', 'place']


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(doc):
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def record_identity(kind, key, revision, payload, name, source_sha):
    return sha(canonical([kind, key, revision, payload, name, source_sha]))


def public_fingerprints(cur):
    from psycopg import sql
    result = {}
    for table in PUBLIC_TABLES:
        cur.execute(sql.SQL("SELECT count(*), md5(coalesce(string_agg(md5(to_jsonb(t)::text), '' ORDER BY id), '')) FROM public.{} t").format(sql.Identifier(table)))
        count, digest = cur.fetchone()
        result[table] = {'rows': count, 'fingerprint': digest}
    return result


def input_bundle(root=ROOT, cache=None):
    """只读取固定清单，不请求网络；保护原始字节，不执行或解压到磁盘。"""
    cache = cache or root.parent / '.local/research-cache'
    manifest = read(root / 'data/acquisition-manifest.json')
    sources = read(root / 'shared/sources.json')
    blobs, snapshots, entries, assets, records = {}, [], [], [], []

    def blob(raw):
        key = sha(raw)
        blobs[key] = raw
        return key

    def asset(name, raw, role):
        key = blob(raw)
        assets.append((name, role, key))
        return key

    def record(kind, key, revision, payload, name, source_sha):
        rid = record_identity(kind, key, revision, payload, name, source_sha)
        records.append((rid, kind, key, revision, payload, name, source_sha))

    for meta in manifest['repositories']:
        raw = cached_response(cache,meta['url'],meta['archiveSha256'])
        archive_sha = blob(raw)
        if archive_sha != meta['archiveSha256']:
            raise ValueError('缓存ZIP哈希与固定清单不符：' + meta['repository'])
        if not re.fullmatch(r'kanripo/KR[0-9a-z]+', meta['repository']) or not re.fullmatch(r'[a-f0-9]{40}', meta['commit']):
            raise ValueError('固定来源标识无效')
        sid = sha(canonical([meta['repository'], meta['commit'], archive_sha, meta]))
        snapshots.append((sid, meta['repository'], meta['commit'], archive_sha, meta))
        text_count = 0
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            seen = set()
            for member in archive.infolist():
                if member.is_dir(): continue
                parts = PurePosixPath(member.filename).parts
                expected_prefix = meta['repository'].split('/')[1] + '-' + meta['commit']
                if len(parts) < 2 or parts[0] != expected_prefix or '..' in parts or PurePosixPath(member.filename).is_absolute():
                    raise ValueError('ZIP文件路径不属于固定来源')
                name = '/'.join(parts[1:])
                if name in seen: raise ValueError('ZIP中重复路径：' + name)
                seen.add(name)
                role = 'text' if re.fullmatch(meta['repository'].split('/')[1] + r'_\d+\.txt', name) else ('metadata' if name.lower().endswith(('.org', '.md', 'license', 'license.txt')) else 'other')
                text_count += role == 'text'
                entries.append((sid, name, role, blob(archive.read(member))))
        if text_count != meta['textFiles']:
            raise ValueError('原典文件数与固定清单不符：' + meta['repository'])

    wiki_file = root / 'data/wikisource-acquisition.json'
    if wiki_file.exists():
        asset('data/wikisource-acquisition.json', wiki_file.read_bytes(), 'manifest')
        for meta in read(wiki_file)['pages']:
            raw = cached_response(cache,meta['url'],meta['captureSha256'])
            from wikisource_source import inspect, decode_capture
            checked = inspect(meta, raw)
            if meta.get('kind') != 'contents' and checked.get('originalHeading') != meta.get('originalHeading'):
                raise ValueError('维基卷题尚未按原件核对，先运行check-wikisource-coverage.py')
            if sha(raw) != meta['captureSha256']: raise ValueError('维基固定修订响应哈希不符')
            capture=decode_capture(meta,raw)
            content = capture['text'].encode('utf-8')
            if sha(content) != meta['textSha256']: raise ValueError('维基文本原态哈希不符')
            sid = sha(canonical(['wikisource', meta['pageId'], meta['revisionId'], meta['captureSha256'], meta]))
            snapshots.append((sid, 'wikisource/zh/page/' + str(meta['pageId']), None, blob(raw), meta))
            entries.append((sid, 'page.wiki', 'wikitext', blob(content)))

    for rel in ['data/acquisition-manifest.json', 'data/corpus-inventory.json', 'shared/sources.json', 'shared/editions.json',
                'data/book-acquisition-plan.json', 'data/book-acquisition-log.json', 'data/catalog-recovery.json', 'data/book-register.json', 'data/branch-survey.json', 'data/gap-search.json', 'data/wikisource-coverage.json', 'data/source-discovery.json', 'data/ouyang-source-directory.json','data/ouyang-front-matter-findings.json','data/guizhou-gazetteer.json']:
        if not (root / rel).exists(): continue
        asset(rel, (root / rel).read_bytes(), 'manifest')
    for rel in ['data/original-volume-locators.json', 'data/wangyangming-source-notes.json', 'data/wangyangming-work-audit.json']:
        path = root / rel
        if not path.exists(): continue
        digest = asset(rel, path.read_bytes(), 'manifest')
        doc = read(path)
        if rel.endswith('original-volume-locators.json'):
            for item in doc['items']:
                record('volume_heading', item['id'], 0, item, rel + '#/items/' + item['id'], digest)
        elif rel.endswith('wangyangming-source-notes.json'):
            probe = doc['institutionCatalog']['probe']
            if probe['status'] == 'reachable':
                raw = cached_response(cache, probe['url'], probe['sha256'])
                asset('catalog/wangyangming-institution', raw, 'source-response')
    discovery = root / 'data/source-discovery.json'
    if discovery.exists():
        for item in read(discovery)['items']:
            for key in ['probe','metadataProbe','artifactProbe']:
                probe = item.get(key,{})
                if probe.get('status') != 'reachable': continue
                raw = cached_response(cache,probe['url'],probe['sha256'])
                if sha(raw) != probe['sha256']: raise ValueError('寻源/影像原始响应哈希不符')
                asset('source-discovery/' + item['id'] + '/' + key, raw, 'image-original' if key == 'artifactProbe' else 'source-response')
    gap_search = root / 'data/gap-search.json'
    if gap_search.exists():
        for item in read(gap_search)['items']:
            probe = item['probe']
            if probe.get('status') != 'reachable': continue
            raw = cached_response(cache,probe['url'],probe['sha256'])
            if sha(raw) != probe['sha256']: raise ValueError('缺口调查响应哈希不符')
            asset('gap-search/' + item['id'], raw, 'source-response')
    directory=root/'data/ouyang-source-directory.json'
    if directory.exists():
        probe=read(directory)['probe'];raw=cached_response(cache,probe['url'],probe['sha256'])
        if sha(raw)!=probe['sha256']: raise ValueError('欧阳修子页目录响应哈希不符')
        asset('catalog/ouyang-wiki-directory.json',raw,'catalog-api-response')
    for meta in read(root / 'data/catalog-recovery.json').get('catalogs', []) if (root / 'data/catalog-recovery.json').exists() else []:
        if meta['probe']['status'] == 'reachable':
            raw = cached_response(cache,meta['probe']['url'],meta['probe']['sha256'])
            if sha(raw) != meta['probe']['sha256']: raise ValueError('恢复目录响应哈希不符')
            asset('catalog-recovery/' + meta['path'] + '.json', raw, 'catalog-api-response')
    for meta in read(root / 'data/branch-survey.json').get('items', []) if (root / 'data/branch-survey.json').exists() else []:
        if meta['probe']['status'] == 'reachable':
            raw = cached_response(cache,meta['probe']['url'],meta['probe']['sha256'])
            if sha(raw) != meta['probe']['sha256']: raise ValueError('分支调查响应哈希不符')
            asset('branch-survey/' + meta['repository'] + '.json', raw, 'branch-api-response')
    inventory = read(root / 'data/corpus-inventory.json')
    digest = sha((root / 'data/corpus-inventory.json').read_bytes())
    for book in inventory['books']: record('corpus_book', str(book['id']), 0, book, 'data/corpus-inventory.json#/books/' + str(book['id']), digest)
    for meta in sources.get('catalogs', []):
        if meta['status'] != 'reachable': continue
        raw = cached_response(cache,meta['url'],meta['sha256'])
        if sha(raw) != meta['sha256']: raise ValueError('来源目录哈希不符')
        asset('catalog/' + meta['path'], raw, 'catalog')
    for folder, kind in [('works', 'work'), ('persons', 'person'), ('journeys', 'journey')]:
        for path in sorted((root / 'data' / folder).glob('*.json')):
            name = 'data/' + folder + '/' + path.name
            raw = path.read_bytes()
            digest = asset(name, raw, 'curated-json')
            doc = json.loads(raw)
            record(kind, doc['key'], 0, doc, name, digest)
            if kind == 'journey':
                for stop in doc['stops']:
                    record('stop', f'{doc["key"]}:{stop["seq"]}', 0, stop, name + '#/stops/' + str(stop['seq']), digest)
    for rel, kind, values in [('shared/sources.json', 'source', sources['sources']),
                              ('shared/editions.json', 'edition', [{'id': k, **v} for k, v in read(root / 'shared/editions.json').items()])]:
        digest = sha((root / rel).read_bytes())
        for doc in values: record(kind, doc['id'], 0, doc, rel + '#/' + doc['id'], digest)
    for folder, prefix in [(root / 'data/research-history', 'data/research-history'),
                           (root.parent / '.local/research-private/research-history', 'private/research-history')]:
        for path in sorted(folder.glob('*/*.json')):
            name = prefix + '/' + path.parent.name + '/' + path.name
            raw = path.read_bytes()
            digest = asset(name, raw, 'research-json')
            doc = json.loads(raw)
            record('research_revision', doc['id'], doc['revision'], doc, name, digest)
    for path in sorted((root / 'data/witnesses').glob('*.txt')):
        raw = path.read_bytes()
        if sha(raw) != path.stem: raise ValueError('研究摘引原件哈希不符')
        asset('data/witnesses/' + path.name, raw, 'witness')
    counts = {}
    for _, kind, *_ in records: counts[kind] = counts.get(kind, 0) + 1
    summary = {'formatVersion': 1, 'repositories': sorted((s[1], s[2], s[3]) for s in snapshots),
               'assets': sorted(assets), 'recordIds': sorted(r[0] for r in records),
               'textFiles': sum(e[2] in ('text', 'wikitext') for e in entries), 'archiveEntries': len(entries),
               'recordCounts': counts, 'parser': PARSER}
    return {'id': sha(canonical(summary)), 'manifest': summary, 'blobs': blobs,
            'snapshots': snapshots, 'entries': entries, 'assets': assets, 'records': records}


def missing_page_rows(rows, present):
    """只省略INSERT必然冲突的完整主键区间；内容正确性仍由全量回读校验。"""
    expected={}
    for row in rows:
        count,low,high=expected.get(row[0],(0,row[1],row[1]))
        expected[row[0]]=(count+1,min(low,row[1]),max(high,row[1]))
    complete={uid for uid,stats in present.items() if stats==expected.get(uid) and stats[0]==stats[2]-stats[1]+1}
    return [row for row in rows if row[0] not in complete]


def copy_rows(cur, table, columns, rows):
    from psycopg import sql
    rows = list(rows)
    if not rows: return
    if table=='page':
        cur.execute('SELECT unit_id,count(*),min(seq),max(seq) FROM research_ingest.page WHERE unit_id=ANY(%s) GROUP BY unit_id',(sorted({row[0] for row in rows}),))
        present={uid:(count,low,high) for uid,count,low,high in cur.fetchall()}
        rows=missing_page_rows(rows,present)
        print('仅追加缺少原页范围：'+str(len(rows)),flush=True)
        if not rows:return
    # 本批固定临时表名，仅在同一事务使用；批量COPY后INSERT，不逐行走公网。
    cur.execute(sql.SQL('CREATE TEMP TABLE incoming (LIKE research_ingest.{} INCLUDING DEFAULTS) ON COMMIT DROP').format(sql.Identifier(table)))
    # 公网连接有单语句时限。COPY按负载分组，但仍属于同一原子事务。
    chunks, chunk, weight = [], [], 0
    for row in rows:
        row_weight = sum(len(x) if isinstance(x, (bytes, str)) else 64 for x in row)
        if chunk and weight + row_weight > 512 * 1024:
            chunks.append(chunk); chunk, weight = [], 0
        chunk.append(row); weight += row_weight
    if chunk: chunks.append(chunk)
    for chunk in chunks:
        with cur.copy(sql.SQL('COPY incoming ({}) FROM STDIN').format(sql.SQL(',').join(map(sql.Identifier, columns)))) as writer:
            for row in chunk: writer.write_row(row)
    cur.execute(sql.SQL('INSERT INTO research_ingest.{} ({}) SELECT {} FROM incoming ON CONFLICT DO NOTHING').format(
        sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier, columns)), sql.SQL(',').join(map(sql.Identifier, columns))))
    cur.execute('DROP TABLE incoming')


def read_blobs(cur, keys):
    """大ZIP也分片回读，单次响应不超过256KiB（小文件按组读取）。"""
    cur.execute('SELECT sha256,byte_count FROM research_ingest.blob WHERE sha256=ANY(%s)', (list(keys),))
    sizes = cur.fetchall()
    result, pending, pending_bytes = {}, [], 0
    limit = 256 * 1024
    def flush():
        if not pending: return
        cur.execute('SELECT sha256,payload,byte_count FROM research_ingest.blob WHERE sha256=ANY(%s)', (pending,), binary=True)
        result.update({key: (bytes(payload), count) for key, payload, count in cur.fetchall()})
        pending.clear()
    for key, size in sizes:
        if size > limit:
            flush()
            pending_bytes = 0
            parts = []
            for start in range(0, size, limit):
                cur.execute('SELECT substring(payload FROM %s FOR %s) FROM research_ingest.blob WHERE sha256=%s', (start + 1, limit, key), binary=True)
                parts.append(bytes(cur.fetchone()[0]))
            result[key] = (b''.join(parts), size)
        else:
            if pending_bytes + size > limit: flush(); pending_bytes = 0
            pending.append(key)
            pending_bytes += size
    flush()
    return result


def land(args):
    from psycopg.types.json import Jsonb
    bundle = input_bundle(cache=args.cache)
    if args.batch and args.batch != bundle['id']: raise ValueError('当前输入与指定批次不符，未进行写入')
    print(json.dumps({'batchId': bundle['id'], **{k: bundle['manifest'][k] for k in ['textFiles', 'archiveEntries', 'recordCounts']}}, ensure_ascii=False), flush=True)
    if not args.apply:
        print('输入预览；未修改数据库。加 --apply 落库。'); return
    with connect(args.credentials, readonly=False) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(734210014)')
            before = public_fingerprints(cur)
            cur.execute("SELECT to_regclass('research_ingest.batch')")
            existing = []
            if cur.fetchone()[0]:
                cur.execute('SELECT id,status FROM research_ingest.batch ORDER BY id')
                existing = cur.fetchall()
            backup = args.backup_dir / ('raw-ingest-before-' + now().replace(':', '-') + '.json')
            dump(backup, {'createdAt': now(), 'mode': 'append-only', 'batchId': bundle['id'],
                          'existingBatches': existing, 'publicFingerprints': before,
                          'note': '只新增隔离研究区；不修改公开表。原始输入由本地固定哈希缓存另存。'})
            cur.execute((ROOT / 'research/ingest.sql').read_text('utf-8'))
            cur.execute('REVOKE ALL ON SCHEMA research_ingest FROM PUBLIC')
            cur.execute('INSERT INTO research_ingest.batch(id,manifest,public_before) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                        (bundle['id'], Jsonb(bundle['manifest']), Jsonb(before)))
            cur.execute('SELECT manifest,status,created_at FROM research_ingest.batch WHERE id=%s', (bundle['id'],))
            batch_manifest, phase, landed_at = cur.fetchone()
            if batch_manifest != json.loads(canonical(bundle['manifest'])): raise ValueError('同批次清单冲突')
            cur.execute('SELECT sha256,byte_count FROM research_ingest.blob WHERE sha256=ANY(%s)', (list(bundle['blobs']),))
            existing_blobs = dict(cur.fetchall())
            if any(existing_blobs[k] != len(bundle['blobs'][k]) for k in existing_blobs): raise ValueError('既有原件长度冲突')
            print('追加缺少的原件：' + str(len(bundle['blobs']) - len(existing_blobs)), flush=True)
            copy_rows(cur, 'blob', ['sha256', 'payload', 'byte_count'], [(k, v, len(v)) for k, v in bundle['blobs'].items() if k not in existing_blobs])
            print('追加来源、文件目录和对象快照', flush=True)
            copy_rows(cur, 'source_snapshot', ['id', 'repository', 'commit_sha', 'archive_sha256', 'metadata', 'provider', 'revision_id'],
                      [(a, b, c, d, Jsonb(e), e.get('provider', 'github'), str(e['revisionId']) if e.get('provider') == 'wikisource' else None) for a, b, c, d, e in bundle['snapshots']])
            copy_rows(cur, 'batch_source', ['batch_id', 'snapshot_id'], [(bundle['id'], s[0]) for s in bundle['snapshots']])
            copy_rows(cur, 'file_entry', ['snapshot_id', 'path', 'role', 'blob_sha256'], bundle['entries'])
            copy_rows(cur, 'batch_asset', ['batch_id', 'path', 'role', 'blob_sha256'], [(bundle['id'], *r) for r in bundle['assets']])
            copy_rows(cur, 'record_snapshot', ['id', 'kind', 'record_key', 'revision', 'payload', 'source_path', 'source_sha256'],
                      [(a, b, c, d, Jsonb(e), f, g) for a, b, c, d, e, f, g in bundle['records']])
            copy_rows(cur, 'batch_record', ['batch_id', 'record_id'], [(bundle['id'], r[0]) for r in bundle['records']])
    current_path = ROOT / 'data/ingestion-current.json'
    if current_path.exists() and read(current_path).get('batchId') == bundle['id'] and phase == 'verified':
        print('此批已完成验证；重复落库未改变已验证状态。', flush=True); return
    dump(current_path, {'batchId': bundle['id'], 'phase': phase,
         'counts': bundle['manifest']['recordCounts'], 'textFiles': bundle['manifest']['textFiles'],
         'archiveEntries': bundle['manifest']['archiveEntries'], 'landedAt': landed_at.isoformat(),
         'publicExposure': False, 'academicReview': 'pending'})
    print('完整原件与数据快照已提交数据库；当前阶段：' + phase + '。', flush=True)


def batch_id(args):
    return args.batch or read(ROOT / 'data/ingestion-current.json')['batchId']


def source_unit(raw, path):
    """页是原文件范围，不把排版换行或¶猜成自然段。"""
    text = raw.decode('utf-8-sig')
    header = text.split('<pb:', 1)[0]
    def field(pattern):
        hit = re.search(pattern, header, re.M)
        return hit.group(1).strip() if hit else None
    title = field(r'^#\+TITLE:\s*(.+)$')
    base = field(r'^#\+PROPERTY:\s+BASEEDITION\s+(.+)$')
    juan_header = field(r'^#\+PROPERTY:\s+JUAN\s+(.+)$')
    file_label = field(r'^#\+PROPERTY:\s+FILE\s+(.+)$')
    opening = text.split('<pb:', 1)[1].split('>', 1)[-1] if '<pb:' in text else ''
    opening_lines = [s.replace('¶', '').strip() for s in opening.splitlines() if s.replace('¶', '').strip()][:6]
    # SBCK的JUAN常是重排编号；FILE及正文卷题才是原书卷号的候选定位。
    numeral = r'[一二三四五六七八九十百千零〇兩两0-9]+'
    original = re.search(r'卷(?:之|第)?' + numeral + r'[上中下]?', file_label or '')
    if not original:
        original = re.search(r'卷(?:之|第)?' + numeral + r'[上中下]?', juan_header or '')
    juan = original.group(0) if original else None
    front_or_back = juan_header or ''
    if re.search(r'跋|後序|后序|附[錄録录]|補遺|补遗', front_or_back) or any(re.match(r'^(?:附[錄録录]|補遺|补遗|跋)', line) for line in opening_lines): kind = 'back_matter'
    elif re.search(r'_000\.txt$', path): kind = 'front_matter'
    elif juan: kind = 'body'
    else: kind = 'unclassified'
    marks = list(re.finditer(rb'<pb:([^>]+)>', raw))
    boundaries = [(0, None)] if not marks or marks[0].start() else []
    boundaries += [(m.start(), m.group(1).decode('utf-8')) for m in marks]
    pages = []
    for seq, (start, locator) in enumerate(boundaries):
        end = boundaries[seq + 1][0] if seq + 1 < len(boundaries) else len(raw)
        part = raw[start:end]
        pages.append((seq, locator, start, end, part.decode('utf-8'), sha(part)))
    return {'title': title, 'base': base, 'juan': juan, 'juanHeader': juan_header,
            'fileLabel': file_label, 'openingLines': opening_lines, 'kind': kind, 'parser': GIT_PARSER}, pages


def db_bundle(cur, bid):
    """整理只读已经落库的快照，不从工作区重新拼装正文。"""
    cur.execute('SELECT manifest,public_before,status FROM research_ingest.batch WHERE id=%s', (bid,))
    row = cur.fetchone()
    if not row: raise ValueError('批次不存在')
    print('回读固定来源快照', flush=True)
    cur.execute('SELECT s.id,s.repository,s.commit_sha,s.archive_sha256,s.metadata FROM research_ingest.source_snapshot s JOIN research_ingest.batch_source bs ON bs.snapshot_id=s.id WHERE bs.batch_id=%s', (bid,))
    snapshots = cur.fetchall()
    print('回读全部文件原件', flush=True)
    cur.execute('SELECT f.snapshot_id,f.path,f.role,f.blob_sha256 FROM research_ingest.file_entry f JOIN research_ingest.batch_source bs ON bs.snapshot_id=f.snapshot_id WHERE bs.batch_id=%s ORDER BY f.snapshot_id,f.path', (bid,))
    files = cur.fetchall()
    blobs = read_blobs(cur, {f[3] for f in files})
    if any(f[3] not in blobs for f in files): raise ValueError('入库文件原件缺失')
    entries = [(*f, blobs[f[3]][0]) for f in files]
    print('回读对象和研究修订', flush=True)
    cur.execute('SELECT r.id,r.kind,r.record_key,r.revision,r.payload,r.source_path,r.source_sha256 FROM research_ingest.record_snapshot r JOIN research_ingest.batch_record br ON br.record_id=r.id WHERE br.batch_id=%s', (bid,))
    records = cur.fetchall()
    return {'manifest': row[0], 'public_before': row[1], 'status': row[2], 'snapshots': snapshots, 'entries': entries, 'records': records}


def derive(bundle, bid):
    editions, units, pages, links, matches, issues = {}, [], [], set(), [], []
    def issue(subject, code, detail):
        key = sha(canonical([bid, subject, code, detail]))
        issues.append((key, bid, subject, code, detail))
    paths = {}
    wiki_paths = {}
    wiki_sources = {}
    repos = {s[0]: (s[1], s[2]) for s in bundle['snapshots']}
    source_metadata = {s[0]: s[4] for s in bundle['snapshots']}
    for sid, path, role, digest, payload in bundle['entries']:
        if role not in ('text', 'wikitext'): continue
        raw = bytes(payload)
        parser = GIT_PARSER if role == 'text' else WIKI_PARSER
        if role == 'text': meta, spans = source_unit(raw, path)
        else:
            source = source_metadata[sid]
            meta = {'title': source['title'], 'base': 'wikisource-transcription', 'juan': source.get('originalHeading'),
                    'kind': 'front_matter' if source.get('kind') == 'contents' else 'body', 'parser': WIKI_PARSER,
                    'revisionId': source['revisionId'], 'section': source.get('section'), 'originalFormat': 'wikitext',
                    'basis': '固定页面修订及所选卷目；维基编号不等于已核影像页码'}
            spans = [(0, 'oldid=' + str(source['revisionId']), 0, len(raw), raw.decode('utf-8'), sha(raw))]
        base = meta['base'] or 'UNRECORDED'
        eid = sha(canonical([sid, base, parser]))
        uid = sha(canonical([sid, path, parser]))
        editions.setdefault(eid, (eid, sid, base, meta['title'] or path,
                                  {'parser': parser, 'basis': '原文件卷首标记，不代表版本已鉴定'}))
        units.append((uid, sid, path, eid, meta['title'] or path, meta['juan'], meta['kind'], meta))
        pages.extend((uid, *p) for p in spans)
        paths[(*repos[sid], path)] = (uid, raw)
        if role == 'wikitext':
            wiki_paths[str(meta['revisionId'])] = (uid, raw)
            wiki_sources[str(meta['revisionId'])] = source_metadata[sid]
        if not meta['base'] or not meta['title']: issue(uid, 'missing-header', meta)
        if meta['kind'] == 'unclassified': issue(uid, 'unclassified-unit', {'path': path, 'juan': meta['juan']})
    records = bundle['records']
    objects = {(r[1], r[2]): r[0] for r in records if r[1] != 'research_revision'}
    volume_records = [r for r in records if r[1] == 'volume_heading']
    if volume_records or any(repo == 'kanripo/KR4e0157' for repo, _, _ in paths):
        from original_volume_locators import scan_headings, validate_locator
        # 重扫全部目标原件而非只检查清单已有行；缺一条、重复一条都不能通过。
        expected_headings = sorted(canonical([repo, commit, path, h])
            for (repo, commit, path), (_, raw) in paths.items() if repo == 'kanripo/KR4e0157'
            for h in scan_headings(raw))
        observed_headings = []
        fields = ['volume','header','startByte','endByte','headerSha256','fileSha256','sourcePageMarker','parser','status','scope']
        for rid, _, key, _, doc, _, _ in volume_records:
            try:
                repo, commit, path = doc['repository'], doc['commit'], doc['path']
                _, raw = paths[repo, commit, path]
                validate_locator(doc, raw)
                wanted_id = sha(json.dumps([repo, commit, path, doc['startByte']], ensure_ascii=False).encode())
                if key != doc['id'] or key != wanted_id: raise ValueError('卷题稳定标识不符')
                snapshot = next(s for s in bundle['snapshots'] if (s[1],s[2]) == (repo,commit))
                if doc['archiveSha256'] != snapshot[3]: raise ValueError('卷题归属原始包不符')
                observed_headings.append(canonical([repo,commit,path,{k:doc[k] for k in fields}]))
            except (ValueError, KeyError, StopIteration, UnicodeError) as exc:
                issue(rid, 'invalid-volume-heading', {'reason': str(exc)})
        if sorted(observed_headings) != expected_headings:
            issue('volume-headings', 'volume-heading-set-mismatch', {'expected':len(expected_headings),'actual':len(observed_headings)})
    for rid, kind, key, revision, doc, name, digest in records:
        targets = []
        if kind == 'work':
            targets.append(('person', doc.get('authorKey'), 'author'))
            if doc['text'].get('traditionalDerived'): issue(rid, 'traditional-derived', {'action': '找到底本并人工核对前保留反推标识'})
            if any(re.fullmatch(r'-?\d+', e.get('quote', '').strip()) for d in doc.get('dating', []) for e in d.get('evidence', [])):
                issue(rid, 'year-placeholder', {'action': '年份不是史料引文，系年保持待核'})
        elif kind == 'journey': targets.append(('person', doc.get('personKey'), 'person'))
        elif kind == 'stop':
            targets.append(('journey', key.rsplit(':', 1)[0], 'part-of'))
            issue(rid, 'stop-fact-review-pending', {'action': '年、地、事须另核原句；现有source文字不是已核证明'})
        elif kind == 'research_revision':
            subject = doc.get('subject', {})
            targets.append((subject.get('type'), subject.get('key'), 'research-subject'))
            for index, evidence in enumerate(doc.get('evidence', [])):
                url = evidence.get('url', '')
                hit = re.fullmatch(r'https://github\.com/(kanripo/KR[0-9a-z]+)/blob/([a-f0-9]{40})/(.+)', url)
                wiki_hit = re.fullmatch(r'https://zh\.wikisource\.org/w/index\.php\?oldid=([1-9][0-9]*)', url)
                if not hit and not wiki_hit:
                    code = 'invalid-evidence-url' if 'github.com/kanripo/' in url else 'unsupported-evidence-location'
                    issue(rid, code, {'index': index, 'hasUrl': bool(url), 'action': '原始证据保留，尚未机器定位，不视为已核'})
                    continue
                found = paths.get(hit.groups()) if hit else wiki_paths.get(wiki_hit[1])
                if not found:
                    issue(rid, 'evidence-file-not-landed', {'index': index, 'url': url}); continue
                if wiki_hit:
                    pinned = wiki_sources[wiki_hit[1]]
                    if (evidence.get('revisionId'), evidence.get('pageId'), evidence.get('sourceId')) != (pinned['revisionId'], pinned['pageId'], pinned['sourceId']):
                        issue(rid, 'evidence-revision-mismatch', {'index': index})
                uid, raw = found
                quote = evidence.get('quote', '').encode('utf-8')
                start = raw.find(quote) if quote else -1
                if 'startByte' in evidence or 'endByte' in evidence:
                    a, b = evidence.get('startByte'), evidence.get('endByte')
                    if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(raw) or raw[a:b] != quote:
                        issue(rid, 'evidence-byte-range-mismatch', {'index':index})
                    else: start = a
                if start < 0:
                    issue(rid, 'quote-not-exact', {'index': index, 'unit': uid}); continue
                expected = evidence.get('originalFileSha256')
                if expected and expected not in (sha(raw), sha(raw.decode('utf-8-sig').encode('utf-8'))):
                    issue(rid, 'evidence-file-hash-mismatch', {'index': index})
                if evidence.get('sha256') and evidence['sha256'] != sha(quote):
                    issue(rid, 'quote-hash-mismatch', {'index': index})
                if 'startByte' not in evidence and raw.find(quote, start + 1) >= 0: issue(rid, 'quote-occurs-multiple-times', {'index': index, 'action': '暂存首处定位，需人工判篇'})
                matches.append((bid, rid, index, uid, start, start + len(quote), sha(quote)))
        for target_kind, target_key, relation in targets:
            target = objects.get((target_kind, target_key))
            if target: links.add((bid, rid, target, relation))
            elif target_key: issue(rid, 'unresolved-object', {'kind': target_kind, 'key': target_key})
    return {'edition': list(editions.values()), 'unit': units, 'page': pages,
            'record_link': sorted(links), 'quote_match': matches, 'issue': issues}


DERIVED_COLUMNS = {
    'edition': ['id', 'snapshot_id', 'base_code', 'title', 'metadata'],
    'unit': ['id', 'snapshot_id', 'path', 'edition_id', 'title', 'juan', 'kind', 'metadata'],
    'page': ['unit_id', 'seq', 'locator', 'start_byte', 'end_byte', 'text', 'sha256'],
    'record_link': ['batch_id', 'from_id', 'to_id', 'relation'],
    'quote_match': ['batch_id', 'record_id', 'evidence_index', 'unit_id', 'start_byte', 'end_byte', 'quote_sha256'],
    'issue': ['id', 'batch_id', 'subject', 'code', 'detail']}


def organize(args):
    from psycopg.types.json import Jsonb
    bid = batch_id(args)
    with connect(args.credentials, readonly=not args.apply) as conn:
        with conn.cursor() as cur:
            if args.apply: cur.execute('SELECT pg_advisory_xact_lock(734210014)')
            cur.execute('SELECT status,manifest FROM research_ingest.batch WHERE id=%s', (bid,))
            previous = cur.fetchone()
            if previous and previous[1].get('parser') != PARSER: raise ValueError('解析器版本与批次不符，请重新land形成新批次')
            if args.apply and previous and previous[0] in ('organized', 'verified'):
                print('此批已整理；重复执行未追加或覆盖数据。完整性请继续verify。', flush=True); return
            bundle = db_bundle(cur, bid)
            rows = derive(bundle, bid)
            counts = {k: len(v) for k, v in rows.items()}
            print(json.dumps(counts), flush=True)
            if not args.apply: return
            dump(args.backup_dir / ('raw-organize-before-' + now().replace(':', '-') + '.json'),
                 {'batchId': bid, 'previousStatus': bundle['status'], 'mode': 'append-only', 'counts': counts})
            for table, values in rows.items():
                adapted = [tuple(Jsonb(x) if isinstance(x, dict) else x for x in row) for row in values]
                copy_rows(cur, table, DERIVED_COLUMNS[table], adapted)
            cur.execute("UPDATE research_ingest.batch SET status=CASE WHEN status='verified' THEN status ELSE 'organized' END,organized_at=coalesce(organized_at,clock_timestamp()) WHERE id=%s", (bid,))
    print('库内原件整理已提交，学术审校仍待进行。', flush=True)


def verify(args):
    """回读全部原件和派生范围；校验通过仅表示存储完整，不表示内容已确证。"""
    from psycopg import sql
    bid = batch_id(args)
    expected = input_bundle(cache=args.cache)
    if expected['id'] != bid: raise ValueError('输入已变更：应先另建落库批次，不能把旧批次标为新资料已核')
    repeat_checked = False
    if args.repeat:
        if not args.apply: raise ValueError('--repeat 会实际重放幂等导入，须同时加 --apply')
        def counts():
            with connect(args.credentials) as conn:
                with conn.cursor() as cur:
                    result = {}
                    for table in ['blob', 'batch', 'source_snapshot', 'batch_source', 'file_entry', 'batch_asset',
                                  'record_snapshot', 'batch_record', *DERIVED_COLUMNS]:
                        cur.execute(sql.SQL('SELECT count(*) FROM research_ingest.{}').format(sql.Identifier(table)))
                        result[table] = cur.fetchone()[0]
                    return result
        before_repeat = counts()
        land(args)
        organize(args)
        if counts() != before_repeat: raise ValueError('重复执行新增了行，请核查批次与身份稳定性')
        repeat_checked = True
        print('实际重复落库及整理：全部表行数未增加。', flush=True)
    checks = []
    def require(ok, label):
        if not ok: raise ValueError('验证失败：' + label)
        checks.append(label)
    normalize = lambda x: json.loads(canonical(x))
    with connect(args.credentials, readonly=not args.apply) as conn:
        with conn.cursor() as cur:
            if args.apply: cur.execute('SELECT pg_advisory_xact_lock(734210014)')
            bundle = db_bundle(cur, bid)
            require(bundle['status'] in ('organized', 'verified'), 'ordered-phases')
            require(bundle['manifest'] == normalize(expected['manifest']), 'batch-manifest')
            require(normalize(sorted(bundle['snapshots'])) == normalize(sorted(expected['snapshots'])), 'pinned-repository-snapshots')
            cur.execute('SELECT id,provider,revision_id FROM research_ingest.source_snapshot WHERE id=ANY(%s)', ([s[0] for s in bundle['snapshots']],))
            identities = sorted((s[0], s[4].get('provider','github'), str(s[4]['revisionId']) if s[4].get('provider') == 'wikisource' else None) for s in expected['snapshots'])
            require(sorted(cur.fetchall()) == identities, 'provider-revision-identities')
            wiki = [s[4] for s in bundle['snapshots'] if s[4].get('provider') == 'wikisource']
            wiki_coverage={}
            if wiki:
                from wikisource_source import collection_coverage
                wiki_coverage=collection_coverage(wiki)
                require(wiki_coverage.get('wikisource-sanguozhi-siku',{}).get('selectedScopeComplete'), 'sanguozhi-wiki-volume-coverage')
            require(sorted(tuple(r[:4]) for r in bundle['entries']) == sorted(expected['entries']), 'all-archive-entry-paths')
            require(normalize(sorted(bundle['records'])) == normalize(sorted(expected['records'])), 'all-record-snapshots')
            # 以完整输入的哈希集合逐个回读，不能用条数或数据库内自报哈希替代。
            print('逐字节核对全部原件及ZIP', flush=True)
            actual_blobs = {r[3]: (bytes(r[4]), len(r[4])) for r in bundle['entries']}
            actual_blobs.update(read_blobs(cur, set(expected['blobs']) - set(actual_blobs)))
            require(set(actual_blobs) == set(expected['blobs']), 'all-original-blobs-present')
            require(all(actual_blobs[key] == (raw, len(raw)) and sha(actual_blobs[key][0]) == key for key, raw in expected['blobs'].items()), 'all-original-bytes-and-sha256')
            cur.execute('SELECT path,role,blob_sha256 FROM research_ingest.batch_asset WHERE batch_id=%s', (bid,))
            require(sorted(cur.fetchall()) == sorted(expected['assets']), 'all-source-assets')
            derived = derive(bundle, bid)
            blocking = {'quote-not-exact', 'quote-hash-mismatch', 'evidence-file-hash-mismatch',
                        'invalid-volume-heading', 'volume-heading-set-mismatch', 'evidence-byte-range-mismatch',
                        'evidence-file-not-landed', 'unresolved-object', 'invalid-evidence-url', 'evidence-revision-mismatch'}
            require(not any(row[3] in blocking for row in derived['issue']), 'no-broken-evidence-or-object-links')
            expected_evidence = {(r[0], i) for r in bundle['records'] if r[1] == 'research_revision'
                                 for i, e in enumerate(r[4].get('evidence', []))}
            located = {(r[1], r[2]) for r in derived['quote_match']}
            unresolved = {(r[2], r[4]['index']) for r in derived['issue'] if r[3] in
                          ('unsupported-evidence-location', 'invalid-evidence-url', 'evidence-file-not-landed', 'quote-not-exact')}
            require(expected_evidence == located | unresolved, 'every-evidence-has-location-status')
            sids = [s[0] for s in bundle['snapshots']]
            uids = [u[0] for u in derived['unit']]
            for table, columns in DERIVED_COLUMNS.items():
                print('回读整理表：' + table, flush=True)
                if table in ('edition', 'unit'): where, ids = 'snapshot_id', sids
                elif table == 'page': where, ids = 'unit_id', uids
                else: where, ids = 'batch_id', [bid]
                query = sql.SQL('SELECT {} FROM research_ingest.{} WHERE {}=ANY(%s)').format(
                    sql.SQL(',').join(map(sql.Identifier, columns)), sql.Identifier(table), sql.Identifier(where))
                if table in ('edition', 'unit'): query += sql.SQL(" AND metadata->>'parser'=ANY(%s)")
                values = []
                for offset in range(0, len(ids), 8):
                    params = (ids[offset:offset + 8], SUPPORTED_PARSERS) if table in ('edition', 'unit') else (ids[offset:offset + 8],)
                    cur.execute(query, params)
                    values.extend(cur.fetchall())
                actual = sorted(values, key=lambda row: canonical(row))
                wanted = sorted(derived[table], key=lambda row: canonical(row))
                require(normalize(actual) == normalize(wanted), 'derived-' + table)
            cur.execute('SELECT count(*) FROM research_ingest.edition WHERE id=ANY(%s) AND review_status<>%s', ([row[0] for row in derived['edition']], 'pending'))
            require(cur.fetchone()[0] == 0, 'no-false-academic-review')
            # 独立检查范围拼合与证据定位，避免仅仅重复同一个解析器。
            raws = {(sid, path): bytes(payload) for sid, path, role, digest, payload in bundle['entries'] if role in ('text','wikitext')}
            spans_by_unit = {}
            for p in derived['page']: spans_by_unit.setdefault(p[0], []).append(p)
            for uid, sid, path, *_ in derived['unit']:
                spans = sorted(spans_by_unit.get(uid, []), key=lambda p: p[1])
                raw = raws[sid, path]
                position = 0
                for _, seq, locator, start, end, text, digest in spans:
                    require(start == position and raw[start:end] == text.encode('utf-8') and sha(raw[start:end]) == digest,
                            'page-span:' + path + ':' + str(seq))
                    position = end
                require(position == len(raw), 'whole-file-covered:' + path)
            records = {r[0]: r[4] for r in bundle['records']}
            unit_raw = {u[0]: raws[u[1], u[2]] for u in derived['unit']}
            for _, rid, index, uid, start, end, digest in derived['quote_match']:
                evidence = records[rid]['evidence'][index]
                raw = unit_raw[uid][start:end]
                require(raw == evidence['quote'].encode('utf-8') and sha(raw) == digest,
                        'exact-evidence:' + rid + ':' + str(index))
                if evidence.get('textFile'):
                    require(expected['blobs'].get(evidence.get('sha256')) == raw, 'witness-artifact:' + rid + ':' + str(index))
            print('核对既有公开语料指纹', flush=True)
            require(public_fingerprints(cur) == bundle['public_before'], 'public-tables-unchanged')
            issues = {}
            for row in derived['issue']: issues[row[3]] = issues.get(row[3], 0) + 1
            report = {'batchId': bid, 'phase': 'verified' if args.apply else 'verification-preview', 'verifiedAt': now(),
                      'integrityPassed': True, 'academicReview': 'pending', 'publicExposure': False,
                      'repeatImportChecked': repeat_checked,
                      'originalBlobs': len(expected['blobs']), 'originalBytes': sum(map(len, expected['blobs'].values())),
                      'sourceSnapshotCounts': {'github': len(bundle['snapshots']) - len(wiki), 'wikisource': len(wiki)},
                      'wikiCollectionCoverage':wiki_coverage,
                      'textUnitCounts': {'gitFiles': sum(e[2]=='text' for e in bundle['entries']), 'wikiPages': len(wiki), 'wikiBodyVolumes': sum(p['kind']=='body' for p in wiki)},
                      'volumeHeadingCandidates':sum(r[1]=='volume_heading' for r in bundle['records']),
                      'textFiles': len(derived['unit']), 'archiveEntries': len(expected['entries']),
                      'recordCounts': expected['manifest']['recordCounts'], 'derivedCounts': {k: len(v) for k, v in derived.items()},
                      'unitKinds': {kind: sum(u[6] == kind for u in derived['unit']) for kind in ['front_matter', 'body', 'back_matter', 'unclassified']},
                      'issues': issues, 'checksPassed': len(checks), 'publicTableCounts': {k: v['rows'] for k, v in bundle['public_before'].items()},
                      'evidenceLocations': {'total': len(expected_evidence), 'exact': len(located), 'unresolved': len(unresolved)},
                      'scope': '原件及快照全量存储回读验证；不等于学术内容已核，不等于原典全本无缺卷。'}
            if args.apply:
                dump(args.backup_dir / ('raw-verify-before-' + now().replace(':', '-') + '.json'),
                     {'batchId': bid, 'previousStatus': bundle['status'], 'mode': 'status-only'})
                cur.execute("UPDATE research_ingest.batch SET status='verified',verified_at=%s WHERE id=%s", (report['verifiedAt'], bid))
    if args.apply:
        dump(ROOT / 'data/ingestion-report.json', report)
        dump(ROOT / 'data/ingestion-current.json', report)
    print(json.dumps(report, ensure_ascii=False), flush=True)


def status(args):
    with connect(args.credentials) as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT id,status,created_at,organized_at,verified_at,manifest FROM research_ingest.batch WHERE id=%s', (batch_id(args),))
            row = cur.fetchone()
            if not row: raise ValueError('批次不存在')
            summary = dict(zip(['batchId', 'status', 'createdAt', 'organizedAt', 'verifiedAt'], row[:5]))
            summary.update({key: row[5][key] for key in ['recordCounts', 'textFiles', 'archiveEntries', 'parser']})
            print(json.dumps(summary, ensure_ascii=False, default=str))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['land', 'organize', 'verify', 'status'])
    parser.add_argument('--credentials')
    parser.add_argument('--cache', type=Path, default=ROOT.parent / '.local/research-cache')
    parser.add_argument('--backup-dir', type=Path, default=ROOT.parent / '.local/backups')
    parser.add_argument('--batch')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--repeat', action='store_true', help='verify前实际重放本批落库与整理，核对不增重复行；须--apply')
    args = parser.parse_args()
    try:
        if args.command == 'land': land(args)
        elif args.command == 'status': status(args)
        elif args.command == 'organize': organize(args)
        elif args.command == 'verify': verify(args)
    except Exception as exc:
        print('操作未完成；写事务已回滚。错误类型：' + type(exc).__name__, file=sys.stderr)
        # 本地数据错误可安全说明；连接异常不回显连接串或凭据。
        if isinstance(exc, (ValueError, FileNotFoundError)): print(str(exc), file=sys.stderr)
        raise SystemExit(1)
