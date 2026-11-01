"""从固定维基原态取得已有作品的逐字片段候选，不改基线正文或系年。"""
import json
import re
import argparse
from research import ROOT, read, dump, cached_response
from raw_ingest import sha
from research_records import save_record, build_index
from wikisource_source import decode_capture


def normalize(text):
    blocked = {i for m in re.finditer(r'\[[^\]]*\]', text) for i in range(m.start(),m.end())}
    offsets = [i for i,c in enumerate(text) if '\u3400' <= c <= '\u9fff' and i not in blocked]
    return ''.join(text[i] for i in offsets), offsets


def main(ouyang=False):
    suffix='/卷149' if ouyang else '/蜀志/卷05'
    source='wikisource-ouyang-wenzhong-siku' if ouyang else 'wikisource-sanguozhi-siku'
    meta = next(p for p in read(ROOT / 'data/wikisource-acquisition.json')['pages'] if p['sourceId']==source and p['title'].endswith(suffix))
    raw = cached_response(ROOT.parent/'.local/research-cache',meta['url'],meta['captureSha256'])
    if sha(raw) != meta['captureSha256']: raise ValueError('固定修订响应哈希错误')
    body = decode_capture(meta,raw)['text']
    if sha(body.encode()) != meta['textSha256']: raise ValueError('原态文本哈希错误')
    normalized, indexes = normalize(body)
    for path in sorted((ROOT / 'data/works').glob('*.json')):
        work = read(path)
        if work['key'] not in (['与梅圣俞书'] if ouyang else ['出师表', '三国志·诸葛亮传']): continue
        hits = []
        for paragraph in work['text']['paragraphs']:
            target, _ = normalize(paragraph)
            offset = normalized.find(target)
            if len(target) >= 12 and offset >= 0: hits.append((len(target), offset))
        if not hits: raise ValueError('没有逐字见证，不创建记录：' + work['key'])
        length, offset = max(hits)
        quote = body[indexes[offset]:indexes[offset + length - 1] + 1]
        artifact = quote.encode('utf-8')
        digest = sha(artifact)
        target = ROOT / 'data/witnesses' / (digest + '.txt')
        if target.exists() and target.read_bytes() != artifact: raise ValueError('摘引原件冲突')
        target.write_bytes(artifact)
        label=meta['originalHeading'] if ouyang else '蜀志卷五'
        doc = {'id': ('wiki-ouyang-witness-' if ouyang else 'wiki-witness-') + sha(work['key'].encode())[:20], 'subject': {'type':'work','key':work['key']},
            'kind':'witness','status':'partial','visibility':'public','title':work['titleZh'] + ' · '+label+'固定修订片段',
            'claim':'在维基文库所标四库本'+label+'中取得对应原态片段；只证明所引片段存在，不能据此核定整篇或系年。',
            'provenance':{'origin':'machine','method':'固定页面修订，去编排符号比较后截取实际原字符'},
            'evidence':[{'sourceId':meta['sourceId'],'quote':quote,'locator':meta['title'] + '，修订' + str(meta['revisionId']),
                'url':meta['permalink'],'revisionId':meta['revisionId'],'pageId':meta['pageId'],
                'sha256':digest,'textFile':'data/witnesses/' + digest + '.txt','originalFileSha256':meta['textSha256'],
                'captureSha256':meta['captureSha256'],'verifiedQuote':True,'verification':'固定维基原态逐字命中，不等于影像校核',
                'stance':'support','grade':'ungraded'}],
            'issues':['仅'+str(len(hits))+'个段落片段命中；其他段落及版本差异待核。','所标四库底本尚待影像对校；同底本转录不算独立证据。'],
            'reasoning':'','counterEvidence':'尚未完成该篇影像校核与版本异文比较；没有因片段命中判定全文、作年或人物行迹。',
            'alternatives':[],'reviewHistory':[],'searchLog':[{'sourceId':meta['sourceId'],'mode':'固定修订原态匹配','revisionId':meta['revisionId']}],
            'nextAction':'对照四库影像核篇题、上下文、模板字与异文，再决定是否建立校记或替换版本。'}
        saved = save_record(ROOT,doc)
        print(work['key'] + '：修订' + str(saved['revision']) + '，'+str(length)+'个可比汉字的原态片段')
    build_index(ROOT)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ouyang',action='store_true')
    main(p.parse_args().ouyang)
