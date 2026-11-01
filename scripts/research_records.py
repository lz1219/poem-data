"""研究记录的修订与发布。旧快照不可覆盖；重复生成不产生新修订。"""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone


def text(doc):
    return json.dumps(doc, ensure_ascii=False, indent=2) + '\n'


def save_record(root, doc):
    public_path = root / 'data/research' / (doc['id'] + '.json')
    if doc.get('visibility') == 'internal' and public_path.exists():
        raise ValueError('公开过的记录不能追溯保密；请新增rejected公开修订退出默认展示')
    base = root / 'data' if doc.get('visibility') == 'public' else root.parent / '.local/research-private'
    folder = base / 'research'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (doc['id'] + '.json')
    candidates = [root / 'data/research' / (doc['id'] + '.json'), root.parent / '.local/research-private/research' / (doc['id'] + '.json')]
    prior = [json.loads(p.read_text('utf-8')) for p in candidates if p.exists()]
    previous = max(prior, key=lambda d: d['revision']) if prior else None
    if previous and previous.get('reviewHistory') and not doc.get('reviewHistory'):
        return previous  # 机器重跑不得抹去人工审校
    payload = {'schemaVersion': '1.0', **{k: v for k, v in doc.items() if k not in ['revision', 'updatedAt', 'sha256']}}
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if previous and previous.get('sha256') == digest:
        return previous
    revision = previous['revision'] + 1 if previous else 1
    doc = {**payload, 'schemaVersion': '1.0', 'revision': revision, 'updatedAt': datetime.now(timezone.utc).isoformat(), 'sha256': digest}
    archive = base / 'research-history' / doc['id'] / f'{revision}.json'
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        raise ValueError('不可覆盖旧研究修订')
    with archive.open('x', encoding='utf-8', newline='\n') as f:
        f.write(text(doc))  # exclusive create：并发写不能覆盖既有快照
    fd, temp = tempfile.mkstemp(dir=folder, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f: f.write(text(doc))
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    return doc


def publishable(doc):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'server'))
    from corpus.research_rules import publishable as check
    return check(doc)


def build_index(root):
    records = []
    for path in sorted((root / 'data/research').glob('*.json')):
        doc = json.loads(path.read_text('utf-8'))
        if publishable(doc):
            records.append({k: doc[k] for k in ['id', 'revision', 'subject', 'kind', 'status', 'title', 'provenance']})
    (root / 'data/research-index.json').write_text(text({'schemaVersion': '1.0', 'records': records}), encoding='utf-8', newline='\n')
