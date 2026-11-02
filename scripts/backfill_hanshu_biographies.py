"""Append fixed WYG Hanshu volumes 31-50 to the verified existing edition.

Preview is offline; apply requires the exact prior annals batch, backup and locks.
Does not modify old text, edition, provenance, or prior batch manifests.
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
from backfill_shiji import ROOT, apply, verify, rollback, digest, require, fingerprints, batch
from research import cached_response, connect, dump, now

PARSER = 'hanshu-wyg-biographies-31-50-source-pages-v1'
VOLUMES = range(31, 51)


def make_plan(cache, permission_sha):
    prior = annals_plan(cache, permission_sha)
    info = copy.deepcopy(prior['manifest'])
    units = []
    with zipfile.ZipFile(io.BytesIO(cached_response(cache, info['source']['url'], ARCHIVE_SHA))) as zipped:
        files = sorted(p for p in zipped.namelist() if re.search(r'/KR2a0007_0(?:3[1-9]|4[0-9]|50)\.txt$', p))
        require(len(files) == 20, 'Expected twenty fixed biography files')
        for path in files:
            parsed = parse_file(path.split('/', 1)[1], zipped.read(path), allowed_volumes=VOLUMES, parser=PARSER)
            number = int(re.search(r'_([0-9]{3})\.txt$', path).group(1))
            require(len(parsed) == 2 and all(u['origin']['volumeNumber'] == number for u in parsed), 'Unexpected biography components')
            require([u['origin']['kind'] for u in parsed] == ['body-volume', 'edition-examination'], 'Missing separate examination')
            units.extend(parsed)
    info.update({'parser': PARSER, 'reuseEditionId': 9, 'previousBatchId': prior['batchId'],
                 'edition': '前汉书·颜师古注·文渊阁四库本（转录待校；本批列传卷三十一至五十及独立考證）',
                 'coverage': {'included': '列传卷三十一至五十20卷及对应20考證，共40单元；十二本纪已由前批收录',
                              'excludedVolumes': list(range(1, 31)) + list(range(51, 101)),
                              'reason': '本批范围为31–50；卷首、八表、诸志及51–100等仍待后续处理，不认定全书完整'},
                 'unitDigests': [digest({'juan': u['juan'], 'textSha256': u['sha256'], 'origin': u['origin'],
                                        'pageOrigins': [p['origin'] for p in u['paragraphs']]}) for u in units],
                 'counts': {'units': len(units), 'bodyVolumes': 20, 'bodyComponents': 20,
                            'editionExaminations': 20, 'frontMatter': 0,
                            'sourcePageBlocks': sum(len(u['paragraphs']) for u in units),
                            'emptySourcePages': sum(not bool(p['body']) for u in units for p in u['paragraphs']),
                            'unresolvedGlyphTokenOccurrences': sum(len(re.findall(r'&KR[0-9A-Za-z]+;', u['body'])) for u in units)}})
    return {'batchId': digest(info), 'manifest': info, 'units': units, 'previousPlan': prior}


def backup_existing(conn, folder, plan):
    from psycopg import sql
    book_id = plan['manifest']['bookId']
    conn.execute('SELECT id FROM public.book WHERE id=%s FOR UPDATE', (book_id,)).fetchall()
    # Lock all pre-existing components, provenance and edition before verifying
    # their immutable predecessor. Normal editors/FK writers cannot race this.
    conditions = {
        'book': ('id', [book_id]), 'edition': ('book_id', [book_id]),
        'text_unit': ('book_id', [book_id]),
    }
    unit_ids = [r[0] for r in conn.execute('SELECT id FROM text_unit WHERE book_id=%s ORDER BY id', (book_id,))]
    paragraph_ids = [r[0] for r in conn.execute('SELECT id FROM paragraph WHERE unit_id=ANY(%s) ORDER BY id', (unit_ids,))]
    conditions.update({'paragraph': ('id', paragraph_ids), 'corpus_unit_origin': ('unit_id', unit_ids),
                       'corpus_paragraph_origin': ('paragraph_id', paragraph_ids),
                       'corpus_ingest_batch': ('book_id', [book_id])})
    snapshot = {}
    for table, (field, values) in conditions.items():
        key = {'corpus_unit_origin': 'unit_id', 'corpus_paragraph_origin': 'paragraph_id',
               'corpus_ingest_batch': 'batch_id'}.get(table, 'id')
        rows = conn.execute(sql.SQL('SELECT to_jsonb(t) FROM public.{} t WHERE {}=ANY(%s) ORDER BY {} FOR UPDATE').format(
            sql.Identifier(table), sql.Identifier(field), sql.Identifier(key)), (values,)).fetchall()
        snapshot[table] = [r[0] for r in rows]
    require(snapshot['book'][0]['title'] == '《汉书》', 'Wrong existing book')
    verify(conn, plan['previousPlan'])
    _, previous, state = batch(conn, plan['manifest']['previousBatchId'])
    require(state == 'applied' and previous['editionIds'] == [9], 'Unexpected predecessor edition')
    require(set(unit_ids) == set(previous['unitIds']), 'Unrecognized existing units; refuse merge')
    require(len(snapshot['edition']) == 1 and snapshot['edition'][0]['id'] == 9, 'Unexpected book editions')
    snapshot.update({'batchId': plan['batchId'], 'createdAt': now(), 'publicBefore': fingerprints(conn)})
    path = folder / ('corpus-before-' + plan['batchId'][:12] + '-' + now().replace(':', '-') + '.json')
    dump(path, snapshot)
    require(json.loads(path.read_text('utf-8')) == snapshot, 'Backup readback mismatch')
    return snapshot, hashlib.sha256(path.read_bytes()).hexdigest()


def verify_chain(conn, plan):
    verify(conn, plan['previousPlan'])
    return {**verify(conn, plan), 'previousBatchVerified': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['preview', 'apply', 'verify', 'rollback'], default='preview', nargs='?')
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
        require(args.credentials is not None, 'Credentials required; never echoed')
        require(args.operation != 'apply' or args.backup_dir is not None, 'Backup directory required')
        with connect(args.credentials, readonly=args.operation == 'verify') as conn:
            result = apply(conn, plan, args.backup_dir, backup_fn=backup_existing) if args.operation == 'apply' else (
                rollback(conn, plan) if args.operation == 'rollback' else verify_chain(conn, plan))
    if args.output:
        dump(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k != 'manifest'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
