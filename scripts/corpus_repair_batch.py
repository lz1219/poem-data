"""Preview, apply and verify fixed-source repairs in short per-volume transactions."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path

import psycopg
from backfill_shiji import canonical, require
from corpus_repair import snapshot, apply, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('preview', 'apply'))
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--plans', type=Path)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    directory = args.directory
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / 'manifest.json'
    dsn = os.environ['CORPUS_DSN']
    if args.operation == 'preview':
        require(args.plans and not manifest_path.exists(), 'New batch and plans required')
        plans = json.loads(args.plans.read_text('utf-8'))
        manifest = {'ready': [], 'rejected': []}
        with psycopg.connect(dsn, autocommit=True, options='-c statement_timeout=10000') as conn:
            for item in plans:
                try:
                    with conn.transaction():
                        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                        data = json.loads(canonical(snapshot(conn, item['plan'], item['juan'], item['unitId'], True)))
                    raw = gzip.compress(canonical(data), compresslevel=1)
                    name = str(item['unitId']) + '-before.json.gz'
                    path = directory / name
                    with path.open('xb') as f:
                        f.write(raw)
                    require(json.loads(gzip.decompress(path.read_bytes())) == data, 'Backup readback differs')
                    manifest['ready'].append({'unitId': item['unitId'], 'juan': item['juan'], 'backup': name,
                        'sha256': hashlib.sha256(raw).hexdigest(),
                        'numbers': data['source']['origin']['sourceNumberSeparation']['count'],
                        'blocks': len(data['rows'])})
                except Exception as exc:
                    manifest['rejected'].append({'unitId': item['unitId'], 'juan': item['juan'],
                                                 'error': str(exc)})
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(manifest, ensure_ascii=False))
    else:
        manifest = json.loads(manifest_path.read_text('utf-8'))
        results_path = directory / 'results.jsonl'
        completed = set()
        if results_path.exists():
            require(args.resume, 'Existing results require explicit resume')
            for line in results_path.read_text('utf-8').splitlines():
                item = json.loads(line)
                if item['status'] == 'verified':
                    completed.add(item['unitId'])
        else:
            require(not args.resume, 'No existing results to resume')
        with psycopg.connect(dsn, autocommit=True, application_name='corpus-repair-batch') as conn, \
             psycopg.connect(dsn, autocommit=True, options='-c default_transaction_read_only=on -c statement_timeout=10000') as reader, \
             results_path.open('a' if args.resume else 'x', encoding='utf-8') as output:
            for item in manifest['ready']:
                if item['unitId'] in completed:
                    continue
                raw = (directory / item['backup']).read_bytes()
                require(hashlib.sha256(raw).hexdigest() == item['sha256'], 'Backup checksum differs')
                data = json.loads(gzip.decompress(raw))
                try:
                    for index in ('text_unit_simp_trgm', 'paragraph_trgm'):
                        pages = conn.execute('SELECT pending_pages FROM pgstatginindex(%s)', (index,)).fetchone()[0]
                        if pages >= 250:
                            cleaned = conn.execute('SELECT gin_clean_pending_list(%s)', (index,)).fetchone()[0]
                            print(json.dumps({'maintenance': index, 'pages': cleaned}), flush=True)
                    result = apply(conn, data, item['sha256'], directory / 'events.jsonl')
                    result.update(verify(reader, data))
                    record = {'unitId': item['unitId'], 'juan': item['juan'], 'status': 'verified', **result}
                except Exception as exc:
                    record = {'unitId': item['unitId'], 'juan': item['juan'], 'status': 'failed',
                              'error': str(exc), 'sqlstate': getattr(exc, 'sqlstate', None)}
                    output.write(json.dumps(record, ensure_ascii=False)+'\n'); output.flush()
                    raise
                output.write(json.dumps(record, ensure_ascii=False)+'\n'); output.flush()
                print(json.dumps({'unitId': item['unitId'], 'juan': item['juan'], 'status': 'verified',
                                  'transactionSeconds': result.get('transactionSeconds')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
