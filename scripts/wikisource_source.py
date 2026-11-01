"""核目录与逐卷原题，不把URL存在当正文完整。"""
import json
import re
import hashlib
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, parse_qs
from research import ROOT, read, dump, now, cached_response


def sha(raw): return hashlib.sha256(raw).hexdigest()


def chinese(n):
    if n < 10: return '一二三四五六七八九'[n - 1]
    if n == 10: return '十'
    if n < 20: return '十' + chinese(n - 10)
    if n == 20: return '二十'
    raise ValueError('此批只核1到20卷')


def chinese_number(value):
    total, digit = 0, 0
    numbers = {c:i for i,c in enumerate('零一二三四五六七八九')}
    for char in value:
        if char in numbers: digit = numbers[char]
        elif char in ('十','百','千'):
            total += (digit or 1) * {'十':10,'百':100,'千':1000}[char]
            digit = 0
        else: raise ValueError('未支持的卷号字符')
    return total + digit


def decode_capture(meta, raw):
    """响应字节另存；只解码原态维基文本，不展开模板或补字。"""
    if meta.get('captureFormat','json') == 'json':
        pages = json.loads(raw)['query']['pages']
        selected = [p for p in pages if p['title'] == meta['title']]
        if len(selected)!=1 or len(selected[0]['revisions'])!=1: raise ValueError('捕获响应的页面/修订不唯一')
        p=selected[0];r=p['revisions'][0]
        return {'pageid':p['pageid'],'title':p['title'],'revid':r['revid'],'timestamp':r['timestamp'],'text':r['slots']['main']['content']}
    if meta.get('captureFormat') != 'mediawiki-export-xml': raise ValueError('未知捕获格式')
    if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw: raise ValueError('不接受XML实体声明')
    root=ET.fromstring(raw)
    ns={'m':root.tag.split('}')[0][1:]}
    selected=[p for p in root.findall('m:page',ns) if p.findtext('m:title',namespaces=ns)==meta['title']]
    if len(selected)!=1: raise ValueError('XML页面身份不唯一')
    p=selected[0];revisions=p.findall('m:revision',ns)
    if len(revisions)!=1: raise ValueError('XML未限定单一修订')
    r=revisions[0]
    return {'pageid':int(p.findtext('m:id',namespaces=ns)),'title':p.findtext('m:title',namespaces=ns),
            'revid':int(r.findtext('m:id',namespaces=ns)),'timestamp':r.findtext('m:timestamp',namespaces=ns),
            'text':r.findtext('m:text',namespaces=ns) or ''}


def inspect(meta, raw):
    if sha(raw) != meta['captureSha256']: raise ValueError('固定响应哈希错误')
    capture=decode_capture(meta,raw);text=capture['text']
    if (capture['pageid'],capture['title'],capture['revid'],capture['timestamp']) != (meta['pageId'],meta['title'],meta['revisionId'],meta['revisionTimestamp']): raise ValueError('页面修订不符')
    url = urlparse(meta['url'])
    if url.scheme!='https' or url.netloc!='zh.wikisource.org': raise ValueError('采集地址不是维基原始入口')
    q=parse_qs(url.query)
    if meta.get('captureFormat','json')=='json':
        if url.path!='/w/api.php' or q.get('revids')!=[str(meta['revisionId'])]: raise ValueError('采集地址不是固定修订API')
    elif url.path!='/w/index.php' or q.get('title')!=['Special:Export'] or q.get('curonly')!=['1'] or meta['title'] not in q.get('pages',[''])[0].splitlines():
        raise ValueError('导出地址与页面选择不符')
    if meta['permalink'] != 'https://zh.wikisource.org/w/index.php?oldid=' + str(meta['revisionId']): raise ValueError('永久链接与修订不符')
    if sha(text.encode('utf-8')) != meta['textSha256']: raise ValueError('原态文本哈希不符')
    body = text.split('<poem>', 1)[-1]
    if meta.get('sourceId') == 'wikisource-ouyang-wenzhong-siku':
        return inspect_ouyang(meta, body, text)
    if meta.get('sourceId')!='wikisource-sanguozhi-siku': raise ValueError('未登记的维基文献集合')
    header = re.search(r'(蜀志|[吳吴呉]志)\s*卷\s*([一二三四五六七八九十]+)', body[:800])
    if meta['kind'] == 'contents':
        if meta['title']!='三國志 (四庫全書本)': raise ValueError('三国志目录身份不符')
        quote = re.search(r'魏志三十卷蜀志十五卷[吳吴呉]志二十卷', re.sub(r'\s+', '', body))
        if not quote: raise ValueError('未在所取目录核得魏30蜀15吴20的明文')
        return {'title': meta['title'], 'revisionId': meta['revisionId'], 'directoryQuote': quote[0], 'status': 'directory-counts-present'}
    expected_section = '蜀志' if meta['section'] == '蜀志' else '吳志'
    if meta['title']!=f'三國志 (四庫全書本)/{expected_section}/卷{meta["juanNumber"]:02d}': raise ValueError('三国志卷目页面身份不符')
    if not header or header[1].replace('吴', '吳').replace('呉', '吳') != expected_section or header[2] != chinese(meta['juanNumber']):
        raise ValueError('卷题与所采卷目不符：' + meta['title'])
    return {'title': meta['title'], 'revisionId': meta['revisionId'], 'originalHeading': header[0],
            'textBytes': len(text.encode('utf-8')), 'status': 'heading-and-revision-present',
            'limitation': '仅核卷题与修订原态；模板字、缺字和全文转录仍须对照影像'}


def inspect_ouyang(meta, body, text):
    book='文忠集 (歐陽修, 四庫全書本)'
    if meta['kind']=='contents':
        if meta['title']!=book: raise ValueError('欧阳修目录身份不符')
        quote=re.search(r'文忠集一百五十三[卷巻]附[録錄录]五[卷巻]',re.sub(r'\s+','',body))
        if not quote: raise ValueError('未核得欧阳文集153卷及附录5卷明文')
        return {'title':meta['title'],'revisionId':meta['revisionId'],'directoryQuote':quote[0],'status':'directory-counts-present'}
    title=re.fullmatch(re.escape(book)+r'/卷(\d{3})',meta['title'])
    header=re.search(r'文忠集\s*[卷巻]\s*([一二三四五六七八九十百千零]+)',body[:1000])
    if not title or not header or chinese_number(header[1])!=int(title[1]) or int(title[1])!=meta.get('juanNumber'):
        raise ValueError('欧阳修实际卷题与所选卷目不符：'+meta['title'])
    return {'title':meta['title'],'revisionId':meta['revisionId'],'originalHeading':header[0],
            'textBytes':len(text.encode()),'status':'heading-and-revision-present','limitation':'153卷正文；附录、年谱另核，不代表全文已校'}


def collection_coverage(pages):
    configs={'wikisource-sanguozhi-siku':{'蜀志':15,'吳志':20},'wikisource-ouyang-wenzhong-siku':{'正文':153}}
    result={}
    for source,expected in configs.items():
        selected=[p for p in pages if p.get('sourceId')==source]
        if not selected: continue
        if len({p['title'] for p in selected})!=len(selected): raise ValueError('同一卷目重复')
        actual={(p['section'],p['juanNumber']) for p in selected if p['kind']=='body'}
        wanted={(s,n) for s,count in expected.items() for n in range(1,count+1)}
        if actual-wanted: raise ValueError('出现计划外的卷目，不能混计覆盖')
        roots=sum(p['kind']=='contents' for p in selected)
        if roots!=1: raise ValueError('目录缺失或重复')
        result[source]={'expectedBodyVolumes':sum(expected.values()),'acquiredBodyVolumes':len(actual),
                        'directoryPages':roots,'missing':[f'{s}卷{n}' for s,n in sorted(wanted-actual)],
                        'selectedScopeComplete':actual==wanted,'academicReview':'pending'}
        if source=='wikisource-ouyang-wenzhong-siku':
            result[source]['appendixCoverage']='原目录附录5卷及年谱的独立范围仍待核，不把153正文卷声称全书无缺'
    if not result: raise ValueError('没有已登记的文献集合')
    return result


def front_matter_findings(meta,text):
    result={'title':meta['title'],'revisionId':meta['revisionId'],'sectionCandidates':[],'markerCandidates':[]}
    for label in ['文忠集本傳','文忠集年譜']:
        marks=list(re.finditer(r'(?m)^[^\S\r\n]*'+label+r'[^\S\r\n]*$',text))
        if len(marks)==2:
            start,end=marks[0].start(),marks[-1].end()
            raw=text[start:end].encode('utf-8')
            result['sectionCandidates'].append({'label':label,'startByte':len(text[:start].encode()),'endByte':len(text[:end].encode()),'sha256':sha(raw),'status':'heading-bounded-candidate','limitation':'标题边界候选，不代替人工篇界审校'})
    for marker in re.finditer(r'cq=\d+',text):
        result['markerCandidates'].append({'marker':marker[0],'startByte':len(text[:marker.start()].encode()),'context':text[max(0,marker.start()-15):marker.end()+15],'status':'unexplained-transcription-marker','action':'保留原字符，对照影像，不补字或自动删除'})
    return result


def main(cache=None):
    cache = cache or ROOT.parent / '.local/research-cache'
    path = ROOT / 'data/wikisource-acquisition.json'
    manifest = read(path)
    rows = []
    findings=[]
    for meta in manifest['pages']:
        raw = cached_response(cache,meta['url'],meta['captureSha256'])
        row = inspect(meta, raw)
        if meta['sourceId']=='wikisource-ouyang-wenzhong-siku' and meta['kind']=='contents':
            findings.append(front_matter_findings(meta,decode_capture(meta,raw)['text']))
        if row.get('originalHeading'): meta['originalHeading'] = row['originalHeading']
        rows.append(row)
    coverage=collection_coverage(manifest['pages'])
    report = {'schemaVersion':'2.0','checkedAt': now(), 'collections':coverage,
              'acquired': len(rows), 'revisionAndHeadingCheckPassed': True, 'academicReview': 'pending', 'items': rows,
              'limitation': '只核实际取得修订及卷题；missing未销项，不证明原底本全文无缺或已完成校勘'}
    dump(path, manifest)
    dump(ROOT / 'data/wikisource-coverage.json', report)
    if findings: dump(ROOT/'data/ouyang-front-matter-findings.json',{'checkedAt':report['checkedAt'],'items':findings,'academicReview':'pending'})
    print(json.dumps(coverage,ensure_ascii=False))


if __name__ == '__main__': main()
