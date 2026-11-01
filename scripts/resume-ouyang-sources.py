"""从保存的维基API暂存续补欧阳修原件；改用XML导出，保留失败历史。"""
import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlencode
from research import ROOT,read,dump,fetch,now,cached_response
from wikisource_source import sha

BOOK='文忠集 (歐陽修, 四庫全書本)'
SOURCE='wikisource-ouyang-wenzhong-siku'


def export_pages(raw,probe,directory):
    if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw: raise ValueError('拒绝XML实体声明')
    tree=ET.fromstring(raw);ns={'m':tree.tag.split('}')[0][1:]};result=[]
    for p in tree.findall('m:page',ns):
        title=p.findtext('m:title',namespaces=ns)
        hit=re.fullmatch(re.escape(BOOK)+r'/卷(\d{3})',title or '')
        if not hit or title not in directory: raise ValueError('导出中出现非所选欧阳修卷目')
        pageid=int(p.findtext('m:id',namespaces=ns))
        if pageid!=directory[title]['pageid']: raise ValueError('目录与导出的页面ID不同')
        revisions=p.findall('m:revision',ns)
        if len(revisions)!=1: raise ValueError('导出未限定单一修订')
        revision=revisions[0];rid=int(revision.findtext('m:id',namespaces=ns));text=revision.findtext('m:text',namespaces=ns) or ''
        if not text.strip(): raise ValueError('导出正文为空')
        result.append({'provider':'wikisource','sourceId':SOURCE,'title':title,'bookTitle':BOOK,
            'pageId':pageid,'revisionId':rid,'revisionTimestamp':revision.findtext('m:timestamp',namespaces=ns),
            'captureFormat':'mediawiki-export-xml','selectionMethod':'export-current-revision-captured',
            'url':probe['url'],'permalink':'https://zh.wikisource.org/w/index.php?oldid='+str(rid),
            'captureSha256':probe['sha256'],'textSha256':sha(text.encode()),'fetchedAt':probe['checkedAt'],
            'baseEdition':'维基标示欧阳修四库本；底本与全文转录待核',
            'permissions':{'read':True,'download':'public-export','ingest':'research-copy','redistribute':'not-cleared'},
            'reviewStatus':'pending','kind':'body','section':'正文','juanNumber':int(hit[1])})
    return result


def main(staging,cache):
    directory=read(staging/'ouyang-directory.json');body={p['title']:p for p in directory['pages'] if re.fullmatch(re.escape(BOOK)+r'/卷\d{3}',p['title'])}
    if len(body)!=153: raise ValueError('目录未核得153个正文卷页')
    path=staging/'ouyang-captures.json';state=read(path)
    for p in state['pages']:
        p['bookTitle']=BOOK;p['section']='contents' if p['kind']=='contents' else '正文'
        p['juanNumber']=None if p['kind']=='contents' else int(p['title'].rsplit('卷',1)[1])
    known={p['title'] for p in state['pages']}
    # 首次探测已取得卷004的XML，先复用，不再次请求同一入口。
    first=staging/'ouyang-export-probe.json'
    if first.exists():
        probe=read(first)['probe']
        if probe['status']=='reachable':
            raw=cached_response(cache,probe['url'],probe['sha256'])
            if sha(raw)!=probe['sha256']: raise ValueError('已存导出响应哈希不符')
            for p in export_pages(raw,probe,body):
                if p['title'] not in known: state['pages'].append(p);known.add(p['title'])
    missing=sorted(set(body)-known)
    for offset in range(0,len(missing),5):
        selected=missing[offset:offset+5]
        url='https://zh.wikisource.org/w/index.php?'+urlencode({'title':'Special:Export','pages':'\n'.join(selected),'curonly':'1'})
        probe,raw=fetch(url,cache);captured=[];error=None
        if raw:
            try: captured=export_pages(raw,probe,body)
            except (ValueError,ET.ParseError) as exc: error=type(exc).__name__
        actual={p['title'] for p in captured}
        if actual-set(selected): raise ValueError('返回计划外卷目')
        state['attempts'].append({'titles':selected,'method':'mediawiki-export-xml','probe':probe,
                                  'status':'acquired' if actual==set(selected) else 'partial','missing':sorted(set(selected)-actual),'error':error})
        for p in captured:
            if p['title'] not in known: state['pages'].append(p);known.add(p['title'])
        dump(path,state)
        print('欧阳修正文取得 '+str(len(known)-1)+'/153；本组缺 '+str(len(set(selected)-actual)),flush=True)
    state['updatedAt']=now();dump(path,state)
    target=ROOT/'data/wikisource-acquisition.json';manifest=read(target)
    old=[p for p in manifest['pages'] if p['sourceId']!=SOURCE]
    manifest['pages']=old+sorted(state['pages'],key=lambda p:p['title'])
    manifest['attempts']=[a for a in manifest['attempts'] if a.get('collection')!=SOURCE]+[{'collection':SOURCE,**a} for a in state['attempts']]
    dump(target,manifest)
    dump(ROOT/'data/ouyang-source-directory.json',directory)
    registry=read(ROOT/'shared/sources.json')
    if not any(s['id']==SOURCE for s in registry['sources']):
        registry['sources'].append({'id':SOURCE,'name':'欧阳修文忠集 · 维基标四库本转录','kind':'text',
            'url':'https://zh.wikisource.org/wiki/'+BOOK.replace(' ','_'),'sourceFamily':'ouyang-wenzhong-siku',
            'upstream':['wikisource','四库全书（标示底本，待核影像）'],'baseEdition':'欧阳修四库本标示，待核影像',
            'coverage':['153卷正文与根页按修订保存；附录5卷及年谱独立范围另核'],
            'permissions':{'read':True,'download':'public-api-and-export','ingest':'research-copy','redistribute':'not-cleared'},
            'usageNote':'同底本转载不自动计独立佐证。API失败历史与XML导出并存，原字符不扩模板、不补字，不自动成为核定正文。'})
    dump(ROOT/'shared/sources.json',registry)
    print('已合并已取得原件清单；须检查原卷题、入库及回读，不据清单宣布全文已校。',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--staging',type=Path,default=ROOT.parent/'.local/source-staging')
    p.add_argument('--cache',type=Path,default=ROOT.parent/'.local/research-cache')
    a=p.parse_args();main(a.staging,a.cache)
