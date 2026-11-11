"""影像观察与文字见证分开：登记身份校验和原始资产回读校验。"""
import hashlib
import json
import re


HASH=re.compile(r'[a-f0-9]{64}')


def validate_observation(item, sources):
    errors=[]
    if not isinstance(item,dict):return ['影像观察格式非法']
    source=sources.get(item.get('sourceId'),{})
    if not source:errors.append('影像观察来源不存在')
    for key in ['originalSha256','originalMetadataSha256','previewSha256','previewMetadataSha256']:
        if not isinstance(item.get(key),str) or not HASH.fullmatch(item[key]):errors.append('影像观察哈希非法：'+key)
    if type(item.get('page')) is not int or item['page']<1:errors.append('影像观察页序非法')
    if type(item.get('metadataRevisionId')) is not int or item['metadataRevisionId']<1:errors.append('影像来源修订非法')
    for key in ['fileTitle','reading','method','previewUrl','sourceUrl','generatedAt']:
        if not isinstance(item.get(key),str) or not item[key].strip():errors.append('影像观察缺'+key)
    if item.get('origin') not in ['ai','human','unknown']:errors.append('影像读取方式非法')
    if item.get('status') not in ['pending','verified','rejected']:errors.append('影像观察状态非法')
    history=item.get('reviewHistory',[])
    if not isinstance(history,list):errors.append('影像审校历史非法');history=[]
    for event in history:
        if not isinstance(event,dict) or not all(event.get(k) for k in ['reviewer','reviewedAt','decision','scope']):
            errors.append('影像审校缺具名范围')
        elif event['decision'] not in ['verified','revise','rejected']:errors.append('影像审校决定非法')
    if item.get('status')=='verified' and not any(isinstance(e,dict) and e.get('decision')=='verified' and all(e.get(k) for k in ['reviewer','reviewedAt','scope']) for e in history):
        errors.append('影像已核须逐项具名审校')
    asset=next((a for a in source.get('imageAssets',[]) if all(a.get(k)==item.get(k) for k in
        ['fileTitle','originalSha256','originalMetadataSha256','metadataRevisionId','sourceUrl'])),None)
    if not asset:errors.append('影像原件未登记或身份不符')
    elif not any(all(p.get(k)==item.get(k) for k in ['page','previewSha256','previewMetadataSha256','previewUrl']) for p in asset.get('previews',[])):
        errors.append('影像预览未登记或页序不符')
    return errors


def observation_hashes(item):
    return [item[k] for k in ['originalSha256','originalMetadataSha256','previewSha256','previewMetadataSha256']]


def verify_observation_assets(item, blobs):
    """仅核文件/元数据/页链；不把AI目读核定为史实或逐字原文。"""
    for key in observation_hashes(item):
        if key not in blobs or hashlib.sha256(blobs[key]).hexdigest()!=key:raise ValueError('影像资产缺失或哈希不符')
    original=blobs[item['originalSha256']]
    if not original.startswith(b'AT&T'):raise ValueError('预期DjVu原件格式不符')
    meta=json.loads(blobs[item['originalMetadataSha256']])['query']['pages'][0]
    preview=json.loads(blobs[item['previewMetadataSha256']])['query']['pages'][0]
    norm=lambda s:s.replace('_',' ')
    if any(norm(p['title'])!=norm(item['fileTitle']) for p in [meta,preview]):raise ValueError('影像元数据文件名不符')
    if meta['revisions'][0]['revid']!=item['metadataRevisionId']:raise ValueError('影像描述页修订不符')
    info=meta['imageinfo'][0];thumb=preview['imageinfo'][0]
    if info['sha1']!=hashlib.sha1(original).hexdigest() or thumb['sha1']!=info['sha1']:raise ValueError('影像预览原件SHA1不符')
    if item['page']>info['pagecount']:raise ValueError('影像页序超出原件范围')
    if thumb.get('thumburl')!=item['previewUrl'] or not re.search(r'/page'+str(item['page'])+r'-\d+px-',item['previewUrl']):
        raise ValueError('影像缩略图与声明页序不符')
    expected_source='https://commons.wikimedia.org/w/index.php?oldid='+str(item['metadataRevisionId'])
    if item['sourceUrl']!=expected_source:raise ValueError('影像描述页未固定修订')
    image=blobs[item['previewSha256']]
    if not image.startswith((b'\xff\xd8\xff',b'\x89PNG\r\n\x1a\n')):raise ValueError('预览并非JPEG或PNG')
    return True
