"""将核查与版本见证追加到既有语料库 research_note，不改事实/原文表。

默认只读；--apply 才写。写前在事务锁内备份目标记录到仓库外；同修订幂等，冲突回滚。
"""
import argparse
import json
import sys
from pathlib import Path
from research import ROOT, connect, dump, now, read
sys.path.insert(0, str(ROOT / 'server'))
from corpus.research_rules import validate_record


def run(credentials, apply, backup_dir):
    docs = [read(p) for p in sorted((ROOT / 'data/research').glob('*.json'))]
    for doc in docs:
        errors = validate_record(doc)
        if errors: raise ValueError(doc['id'] + ': ' + ', '.join(errors))
    with connect(credentials, readonly=not apply) as conn:
        with conn.cursor() as q:
            if apply: q.execute('SELECT pg_advisory_xact_lock(734210011)')
            q.execute("SELECT id,subject_key,topic,body,decision,created_at FROM research_note WHERE topic LIKE 'jiangshan-research:%' ORDER BY id")
            columns = [c.name for c in q.description]
            prior = [dict(zip(columns, row)) for row in q.fetchall()]
            existing = {(r['subject_key'], r['topic']): r for r in prior}
            missing = []
            for doc in docs:
                subject = doc['subject']['type'] + ':' + doc['subject']['key']
                topic = f'jiangshan-research:{doc["id"]}:r{doc["revision"]}'
                body = json.dumps(doc, ensure_ascii=False, sort_keys=True)
                old = existing.get((subject, topic))
                if old and old['body'] != body: raise ValueError('旧修订冲突，整批回滚：' + doc['id'])
                if not old: missing.append((subject, topic, body))
            if not apply:
                print(f'只读预检：现有 {len(prior)}，拟新增 {len(missing)}；不修改任何数据库。')
                return
            stamp = now().replace(':', '-').replace('+', '_')
            backup = backup_dir / ('research-notes-before-' + stamp + '.json')
            dump(backup, {'createdAt': now(), 'table': 'research_note', 'scope': '仅jiangshan-research前缀',
                'rows': [{**r, 'created_at': str(r['created_at'])} for r in prior],
                'plannedTopics': [r[1] for r in missing], 'mode': 'append-only'})
            inserted = []
            for subject, topic, body in missing:
                q.execute('INSERT INTO research_note(subject_key,topic,body,decision) VALUES (%s,%s,%s,%s) RETURNING id',
                          (subject, topic, body, 'pending'))
                inserted.append(q.fetchone()[0])
            dump(backup.with_name(backup.stem + '-inserted.json'), {'ids': inserted, 'topics': [r[1] for r in missing],
                 'note': '只增研究线索，不改事实/原文；回退须逐条核对topic与body后删除本批新增ID。'})
        # 上下文退出提交事务；异常则整批回滚。
    dump(ROOT / 'data/corpus-research-import.json', {'checkedAt': now(), 'table': 'research_note',
         'existingBefore': len(prior), 'inserted': len(inserted), 'factsChanged': False, 'originalTextsChanged': False,
         'backup': '仓库外本地备份，含目标表前态与本批新增ID，不包含凭据'})
    print(f'已备份并追加 {len(inserted)} 条研究记录；原文和事实表未修改。')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--credentials')
    p.add_argument('--apply', action='store_true')
    p.add_argument('--backup-dir', type=Path, default=ROOT.parent / '.local/backups')
    a = p.parse_args()
    run(a.credentials, a.apply, a.backup_dir)
