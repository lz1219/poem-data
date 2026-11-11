"""研究记录准入；机器定位原句不等于人工审校或事实确证。"""
import re
import hashlib
import json
from pathlib import Path


def validate_record(doc, root=None, artifacts=None, source_ids=None, source_documents=None):
    root = Path(root) if root else Path(__file__).resolve().parents[2]
    errors = []
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,119}', doc.get('id', '')):
        errors.append('研究id非法')
    if not isinstance(doc.get('revision'), int) or doc['revision'] < 1:
        errors.append('研究revision非法')
    if doc.get('status') not in ['pending', 'partial', 'verified', 'restricted', 'rejected']:
        errors.append('核查状态非法')
    if doc.get('kind') not in ['audit', 'inference', 'witness']:
        errors.append('研究类型非法')
    if doc.get('visibility') not in ['public', 'internal']:
        errors.append('公开状态非法')
    for key in ['title', 'claim', 'subject', 'provenance', 'reviewHistory', 'counterEvidence']:
        if key not in doc: errors.append('缺字段：' + key)
    subject = doc.get('subject', {})
    if not isinstance(subject, dict) or subject.get('type') not in ['work', 'person', 'journey', 'stop', 'source']:
        errors.append('研究对象类型非法')
        subject = {}
    if not isinstance(subject.get('key'), str) or not subject.get('key', '').strip():
        errors.append('研究对象标识为空')
    origin = doc.get('provenance', {}).get('origin')
    image_items=doc.get('imageObservations',[]) if isinstance(doc.get('imageObservations',[]),list) else []
    if origin not in ['human', 'ai', 'mixed', 'unknown', 'machine']:
        errors.append('生成方式非法')
    if doc.get('kind') == 'inference' and doc.get('visibility') == 'public':
        for key in ['claim', 'reasoning', 'counterEvidence']:
            if not str(doc.get(key, '')).strip(): errors.append('公开推测缺' + key)
        if origin in ['ai', 'mixed']:
            for key in ['model', 'modelVersion', 'generatedAt']:
                if not doc['provenance'].get(key): errors.append('AI推测缺' + key)
        evidence = doc.get('evidence', [])
        if not evidence and not any(isinstance(x,dict) and x.get('status') in ['pending','verified'] for x in image_items): errors.append('公开推测缺真实证据')
        for e in evidence:
            if not all(e.get(k) for k in ['quote', 'sourceId', 'sha256', 'locator', 'verifiedQuote']):
                errors.append('公开推测缺原句定位与核验')
    for event in doc.get('reviewHistory', []):
        if not all(event.get(k) for k in ['reviewer', 'reviewedAt', 'decision']):
            errors.append('人工审校缺具名记录')
        if event.get('decision') not in ['verified', 'revise', 'rejected']:
            errors.append('审校决定非法')
    if doc.get('status') == 'verified':
        grounded=doc.get('evidence') or any(isinstance(x,dict) and x.get('status')=='verified' for x in image_items)
        if not grounded or not any(e.get('decision') == 'verified' for e in doc.get('reviewHistory', [])):
            errors.append('已核状态须有证据及具名核验决定')
    if doc.get('visibility') == 'public':
        source_file = root / 'shared/sources.json'
        if source_documents is None:
            source_documents = {s['id']:s for s in json.loads(source_file.read_text('utf-8'))['sources']} if source_ids is None and source_file.exists() else {}
        if source_ids is None:
            source_ids = set(source_documents)
        if subject.get('type') == 'source' and subject.get('key') not in source_ids:
            errors.append('研究对象来源不存在')
        from .image_evidence import validate_observation
        observations=doc.get('imageObservations',[])
        if not isinstance(observations,list):errors.append('影像观察列表非法');observations=[]
        for item in observations:
            errors.extend(validate_observation(item,source_documents))
            if isinstance(item,dict) and item.get('origin')=='ai':
                for key in ['model','modelVersion','generatedAt']:
                    if not doc.get('provenance',{}).get(key):errors.append('AI影像观察缺'+key)
        for e in doc.get('evidence', []):
            if e.get('sourceId') not in source_ids: errors.append('来源标识不存在')
            rel = e.get('textFile', '')
            if artifacts is not None:
                if rel != 'data/witnesses/' + str(e.get('sha256')) + '.txt' or e.get('sha256') not in artifacts:
                    errors.append('数据库证据原件不存在或路径不匹配'); continue
                raw = artifacts[e['sha256']].encode('utf-8')
                if hashlib.sha256(raw).hexdigest() != e.get('sha256'): errors.append('摘引哈希不匹配')
                if not e.get('quote') or e['quote'] not in raw.decode('utf-8'): errors.append('原句未在摘引文件中命中')
                continue
            target = (root / rel).resolve()
            base = (root / 'data/witnesses').resolve()
            if not rel or base not in target.parents or not target.is_file():
                errors.append('证据摘引文件不存在或越界'); continue
            raw = target.read_bytes()
            if hashlib.sha256(raw).hexdigest() != e.get('sha256'): errors.append('摘引哈希不匹配')
            if not e.get('quote') or e['quote'] not in raw.decode('utf-8'): errors.append('原句未在摘引文件中命中')
    return errors


def publishable(doc, **context):
    return doc.get('visibility') == 'public' and doc.get('status') != 'rejected' and not validate_record(doc, **context)
