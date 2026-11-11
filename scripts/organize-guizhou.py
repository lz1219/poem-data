"""贵州通志卷题与龙场相关原态片段整理；不产生已核行迹。"""
import io
import json
import re
import zipfile
from research import ROOT,read,dump,cached_response,now
from raw_ingest import sha
from research_records import save_record,build_index
from wikisource_source import chinese_number

HEAD=re.compile(r'(?m)^[^\S\r\n]*(?P<header>貴州通志[卷巻](?P<number>[一二三四五六七八九十百零]+))')
CASES=[('yangming-cave','005','陽明洞(','石天洞','阳明洞：游息与居所的证据边界',
        '原条记旧名东洞及王守仁游息；“游息”不能单独证明以洞为住所，更不能证明石棺细节或现代精确坐标。'),
       ('longgang-academy','009','龍岡書院(','石壁書院','龙冈书院：后出地方志与现存设施',
        '原条所记正德间建、修文县城内及“今废”属于清代编纂视角；不能把现存纪念设施直接当作明代现场。'),
       ('xi-shu-academy','019','席　書(','張　庠','席书传中的文明书院论学线索',
        '正德四年是席书任职的叙述纪年，不能直接当王守仁讲学的确切日期；文明书院所在及行程另核，不自动新增路线站点。')]


def headings(raw):
    text=raw.decode('utf-8');rows=[]
    for m in HEAD.finditer(text):
        a,b=m.span('header');before=text[:a];pages=list(re.finditer(r'<pb:([^>]+)>',before))
        rows.append({'header':m['header'],'volume':chinese_number(m['number']),
            'startByte':len(before.encode()),'endByte':len(text[:b].encode()),
            'sourcePageMarker':pages[-1][1] if pages else None})
    return rows


def excerpt(raw,begin,end):
    text=raw.decode('utf-8');a=text.index(begin);b=text.index(end,a+len(begin));quote=text[a:b].rstrip()
    pages=list(re.finditer(r'<pb:([^>]+)>',text[:a]))
    return {'quote':quote,'startByte':len(text[:a].encode()),'endByte':len(text[:a+len(quote)].encode()),
            'page':pages[-1][1] if pages else None}


def evidence(meta,path,raw,found):
    digest=sha(found['quote'].encode());target=ROOT/'data/witnesses'/(digest+'.txt')
    if target.exists() and target.read_bytes()!=found['quote'].encode():raise ValueError('原态片段冲突')
    target.write_bytes(found['quote'].encode())
    return {'sourceId':'kanripo-kr2k0056','quote':found['quote'],'locator':path+'，'+str(found['page']),
        'url':'https://github.com/'+meta['repository']+'/blob/'+meta['commit']+'/'+path,'commit':meta['commit'],
        'originalFileSha256':sha(raw),'sha256':digest,'textFile':'data/witnesses/'+digest+'.txt',
        'startByte':found['startByte'],'endByte':found['endByte'],'verifiedQuote':True,
        'verification':'只核片段与固定电子文件逐字节对应；未对影像或人工学术审校','stance':'context','grade':'ungraded'}


def save_candidate(key,title,claim,issues,ev,subject):
    rid='guizhou-'+key;path=ROOT/'data/research'/(rid+'.json');old=read(path) if path.exists() else None
    if old and (old.get('imageObservations') or old.get('relatedResearch')):
        if {e['sha256'] for e in ev}<={e['sha256'] for e in old['evidence']}:return old
        raise ValueError('已增强记录的原件片段变化，须保留增补后另核')
    doc={'id':rid,'subject':subject,'kind':'audit' if key=='volume28-conflict' else 'witness',
        'status':'pending' if key=='volume28-conflict' else 'partial','visibility':'public','title':title,
        'claim':'AI辅助资料解释·未经人工审校。'+claim,
        'provenance':{'origin':'mixed','model':'Codex','modelVersion':'运行环境未提供精确模型快照',
            'generatedAt':old['provenance']['generatedAt'] if old else now(),
            'method':'程序截取真实原件字节；AI辅助解释证据边界，不形成确定行迹或校定版本'},
        'evidence':ev,'issues':issues,'reasoning':'原态记载只提供继续核查的出处，不自动证明明代事件、亲历、因果或现代精确位置。',
        'counterEvidence':'清代后出编纂与明代事件有时间距离；所取四库转录尚未完成影像对校。暂无足够依据裁定版本差异或现有站点叙述。',
        'alternatives':['同名志书有康熙37卷及乾隆46卷等不同版本，不能按书名混用。'],
        'reviewHistory':[],'searchLog':[{'sourceId':'kanripo-kr2k0056','mode':'明确条题边界逐字截取',
            **({'relatedStop':'wangyangming:5'} if subject['type']=='journey' else {})}],
        'nextAction':'核原影像、版本及明代同时资料；卷题冲突先存疑，地点和系年不自动采信。'}
    return save_record(ROOT,doc)


def main():
    meta=next(x for x in read(ROOT/'data/acquisition-manifest.json')['repositories'] if x['repository']=='kanripo/KR2k0056')
    raw=cached_response(ROOT.parent/'.local/research-cache',meta['url'],meta['archiveSha256']);files={};rows=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in z.namelist():
            path=name.split('/',1)[-1]
            if not re.fullmatch(r'KR2k0056_\d+\.txt',path):continue
            content=z.read(name);files[path]=content;heads=headings(content)
            prop=re.search(r'(?m)^#\+PROPERTY: JUAN ([^\r\n]+)',content.decode())
            rows.append({'path':path,'sha256':sha(content),'juanHeader':prop[1].strip() if prop else None,'explicitHeadings':heads,
                'headingConflict':len({h['volume'] for h in heads})>1})
    observed=sorted({h['volume'] for r in rows for h in r['explicitHeadings']})
    doc={'repository':meta['repository'],'commit':meta['commit'],'archiveSha256':meta['archiveSha256'],'checkedAt':now(),
        'units':sorted(rows,key=lambda r:r['path']),'observedHeadingNumbers':observed,'expectedCatalogVolumes':46,
        'missingHeadingNumbers':sorted(set(range(1,47))-set(observed)),
        'limitation':'卷题检索与目录候选，不证明卷内无缺叶；卷首文件另列，卷28首末冲突未改。','academicReview':'pending'}
    dump(ROOT/'data/guizhou-gazetteer.json',doc)
    for key,num,begin,end,title,issue in CASES:
        path='KR2k0056_'+num+'.txt';raw=files[path];found=excerpt(raw,begin,end)
        save_candidate(key,title,'取得《贵州通志》相关原条，供龙场及相关行程复核；不改默认地图事实。',[issue],
                       [evidence(meta,path,raw,found)],{'type':'journey','key':'wangyangming'})
    path='KR2k0056_028.txt';raw=files[path];heads=headings(raw)
    if {h['volume'] for h in heads}!={28,38}:raise ValueError('已知卷题冲突已变化，须重新核查')
    ev=[evidence(meta,path,raw,{'quote':h['header'],'startByte':h['startByte'],'endByte':h['endByte'],'page':h['sourcePageMarker']}) for h in [heads[0],heads[-1]]]
    save_candidate('volume28-conflict','贵州通志：028文件卷首与卷末题名冲突',
        '同一固定文件JUAN记卷二十八、卷首题三十八、卷末题二十八；不静默修正或认定原因。',
        ['可能涉及转录、底本或卷题刊误，须对照影像；文件编号与元数据不能裁决原题。'],ev,{'type':'source','key':'kanripo-kr2k0056'})
    build_index(ROOT)
    print('贵州原件 '+str(len(rows))+' 文件；卷题号 '+str(len(observed))+'；冲突文件 '+str(sum(r['headingConflict'] for r in rows))+'；新增4条待核研究。')


if __name__=='__main__':main()
