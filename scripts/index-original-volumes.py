"""逐字定位王文成公全书原卷题，保留合卷、重复和跨文件候选。"""
import io
import json
import re
import zipfile
from research import ROOT,read,dump,cached_response,now
from original_volume_locators import scan_headings,validate_locator,sha


def main():
    items=[];summaries=[]
    for meta in read(ROOT/'data/acquisition-manifest.json')['repositories']:
        if meta['repository']!='kanripo/KR4e0157':continue
        archive=cached_response(ROOT.parent/'.local/research-cache',meta['url'],meta['archiveSha256']);rows=[]
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            for path in sorted(z.namelist()):
                name=path.split('/',1)[-1]
                if not re.fullmatch(r'KR4e0157_\d+\.txt',name):continue
                raw=z.read(path)
                for candidate in scan_headings(raw):
                    validate_locator(candidate,raw)
                    key=sha(json.dumps([meta['repository'],meta['commit'],name,candidate['startByte']],ensure_ascii=False).encode())
                    item={'id':key,'repository':meta['repository'],'commit':meta['commit'],'archiveSha256':meta['archiveSha256'],
                          'path':name,**candidate,'url':'https://github.com/'+meta['repository']+'/blob/'+meta['commit']+'/'+name}
                    items.append(item);rows.append(item)
        observed=sorted({r['volume'] for r in rows})
        summaries.append({'repository':meta['repository'],'commit':meta['commit'],'expectedHeadingNumbers':list(range(1,39)),
                          'observedHeadingNumbers':observed,'missingHeadingNumbers':sorted(set(range(1,39))-set(observed)),
                          'unexpectedHeadingNumbers':sorted(set(observed)-set(range(1,39))),
                          'headingOccurrences':len(rows),'crossFileVolumes':[v for v in observed if len({r['path'] for r in rows if r['volume']==v})>1],
                          'limitation':'原卷题编号检索覆盖，不证明卷内无缺页；同卷多处全部保留，不拼接原文'})
    if not items:raise ValueError('没有原卷题候选')
    dump(ROOT/'data/original-volume-locators.json',{'schemaVersion':'1.0','checkedAt':now(),'items':items,'coverage':summaries,'academicReview':'pending'})
    source=read(ROOT.parent/'.local/source-staging/wangyangming-institution-catalog.json')
    dump(ROOT/'data/wangyangming-source-notes.json',{'institutionCatalog':source,'extentMethod':'机构著录38卷与原件显式卷题分别保留，不把同名书目直接当同版','academicReview':'pending'})
    print('显式卷题位置：'+str(len(items))+'；固定提交：'+str(len(summaries)))
    print([(s['missingHeadingNumbers'],s['crossFileVolumes']) for s in summaries])


if __name__=='__main__':main()
