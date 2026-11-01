"""只读检查研究来源、原句、修订快照与公开索引。"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'server'))
from corpus.research_rules import validate_record, publishable


def check(root=ROOT):
    errors = []
    expected = []
    sources = json.loads((root / 'shared/sources.json').read_text('utf-8'))['sources']
    ids = [s['id'] for s in sources]
    if len(ids) != len(set(ids)): errors.append('来源id重复')
    for path in sorted((root / 'data/research-history').glob('*/*.json')):
        d = json.loads(path.read_text('utf-8'))
        errors += [str(path.relative_to(root)) + ': ' + e for e in validate_record(d, root)]
        if d.get('visibility') != 'public': errors.append(str(path) + ': 内部快照不得静态发布')
        payload = {k: v for k, v in d.items() if k not in ['sha256', 'revision', 'updatedAt']}
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if digest != d.get('sha256'): errors.append(str(path) + ': 历史快照哈希不匹配')
        if path.parent.name != d.get('id') or path.stem != str(d.get('revision')): errors.append(str(path) + ': 修订路径不匹配')
    for path in sorted((root / 'data/research').glob('*.json')):
        d = json.loads(path.read_text('utf-8'))
        errors += [path.name + ': ' + e for e in validate_record(d, root)]
        # 内部修订不能发布，故公开修订号允许有缺口；数据库/私有工作台保存完整序列。
        snap = root / 'data/research-history' / d['id'] / f'{d["revision"]}.json'
        if not snap.is_file(): errors.append(path.name + ': 当前修订历史缺失')
        elif json.loads(snap.read_text('utf-8')) != d: errors.append(path.name + ': 当前快照不一致')
        payload = {k: v for k, v in d.items() if k not in ['sha256', 'revision', 'updatedAt']}
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if digest != d.get('sha256'): errors.append(path.name + ': 研究记录哈希不匹配')
        if d.get('visibility') != 'public': errors.append(path.name + ': 内部记录不得放在静态发布目录')
        if publishable(d, root=root): expected.append({k: d[k] for k in ['id', 'revision', 'subject', 'kind', 'status', 'title', 'provenance']})
    actual = json.loads((root / 'data/research-index.json').read_text('utf-8'))['records']
    if actual != expected: errors.append('研究索引不同步或包含非公开记录')
    return errors, len(expected)


if __name__ == '__main__':
    errors, count = check()
    if errors:
        for e in errors[:30]: print(e)
        raise SystemExit(1)
    print(f'研究记录 {count} 条：原句、来源、哈希、修订和发布隔离校验通过。')
