"""卷28影像观察及龙场原态诗文；默认预览，--apply 保存待核修订。"""
import argparse
import copy
import io
import re
import sys
import zipfile
from research import ROOT,read,dump,cached_response,now
from raw_ingest import sha
from research_records import save_record,build_index


def segment(raw,begin,end):
    text=raw.decode('utf-8');a=text.index(begin);b=text.index(end,a+len(begin));quote=text[a:b].rstrip()
    pages=list(re.finditer(r'<pb:([^>]+)>',text[:a]))
    return {'quote':quote,'startByte':len(text[:a].encode()),'endByte':len(text[:a+len(quote)].encode()),
            'page':pages[-1][1] if pages else None}


def make_evidence(meta,path,raw,part):
    digest=sha(part['quote'].encode())
    return {'sourceId':'kanripo-kr4e0157','quote':part['quote'],'locator':path+'，'+str(part['page']),
        'url':'https://github.com/'+meta['repository']+'/blob/'+meta['commit']+'/'+path,'commit':meta['commit'],
        'originalFileSha256':sha(raw),'sha256':digest,'textFile':'data/witnesses/'+digest+'.txt',
        'startByte':part['startByte'],'endByte':part['endByte'],'verifiedQuote':True,
        'verification':'固定电子文件逐字节对应，不等于核定原影像、作年或现代地点','stance':'context','grade':'ungraded'}


def prior(key):
    path=ROOT/'data/research'/(key+'.json')
    return read(path) if path.exists() else None


def provenance(old,marker=None):
    reuse=old and (marker is None or marker in old)
    return {'origin':'mixed','model':'Codex','modelVersion':'运行环境未提供精确模型快照',
        'generatedAt':old['provenance']['generatedAt'] if reuse else now(),
        'method':'程序截取固定原文；AI目读平台预览并说明证据边界，未经人工学术审校'}


def asset_descriptor(row):
    return {'fileTitle':row['title'],'originalSha256':row['artifactProbe']['sha256'],
        'originalMetadataSha256':row['metadataProbe']['sha256'],'metadataRevisionId':row['revisionId'],
        'sourceUrl':'https://commons.wikimedia.org/w/index.php?oldid='+str(row['revisionId']),
        'previews':[{'page':p['page'],'previewSha256':p['probe']['sha256'],
            'previewMetadataSha256':p.get('metadataProbe',row['metadataProbe'])['sha256'],'previewUrl':p['probe']['url']} for p in row.get('previews',[])]}


def main(apply):
    discovery=read(ROOT/'data/source-discovery.json');ident='guizhou-image-CADAL06044369'
    image=next((copy.deepcopy(x) for x in discovery['items'] if x['id']==ident),None)
    if image is None:image=read(ROOT.parent/'.local/source-staging/guizhou-volume28-image.json')
    for p in image['previews']:p.setdefault('metadataProbe',image['metadataProbe'])
    image.update(status='image-captured-research-only',relationship='平台标四库本；卷首及版心AI目读候选与Git有差异，底本同版关系及误差原因仍待核',
        metadataNote='第111–113图为平台渲染预览，原DjVu另存；目读不冒充原始文本或人工校勘',
        permissions={'read':True,'download':'public-original','ingest':'research-copy','redistribute':'not-cleared'})
    asset=asset_descriptor(image);old=prior('guizhou-volume28-conflict');observations=[]
    for page,reading in [(112,'貴州通志卷二十八'),(113,'卷二十八')]:
        preview=next(p for p in asset['previews'] if p['page']==page)
        previous=next((p for p in old.get('imageObservations',[]) if p['page']==page and p['originalSha256']==asset['originalSha256']),None)
        if previous and (previous.get('reviewHistory') or previous.get('status')=='rejected'):
            observations.append(copy.deepcopy(previous));continue
        observations.append({'sourceId':'commons-guizhou-siku',**{k:v for k,v in asset.items() if k!='previews'},**preview,
            'reading':reading,'method':'AI目读平台渲染图；第112图读卷首，第113图读版心，字形及底本关系待人工复核',
            'origin':'ai','generatedAt':previous['generatedAt'] if previous else now(),
            'status':previous['status'] if previous else 'pending','reviewHistory':previous['reviewHistory'] if previous else []})
    meta=next(x for x in read(ROOT/'data/acquisition-manifest.json')['repositories'] if x['repository']=='kanripo/KR4e0157' and not x.get('branch'))
    z=zipfile.ZipFile(io.BytesIO(cached_response(ROOT.parent/'.local/research-cache',meta['url'],meta['archiveSha256'])))
    cases=[('021','三年戊辰先生三十七歲','龍場在貴州'),('021','乃為石墎','乆之胸中'),
        ('021','始知聖人之道吾性自','乃以黙記五經'),
        ('014','始得東洞遂改為陽明小洞天三首','謫居粮絶請學于農'),
        ('018','昔孔子欲居九夷','獨其結題鳥言')]
    evidence=[]
    for no,begin,end in cases:
        path='KR4e0157_'+no+'.txt';raw=z.read(next(n for n in z.namelist() if n.endswith('/'+path)))
        evidence.append(make_evidence(meta,path,raw,segment(raw,begin,end)))
    print('卷28影像观察2项；年谱片段3项、本人诗文片段2项；尚未人工审校。')
    if not apply:return
    sys.path.insert(0,str(ROOT/'server'))
    from corpus.image_evidence import verify_observation_assets,observation_hashes
    journey=read(ROOT/'data/journeys/wangyangming.json');stop=next(s for s in journey['stops'] if s['seq']==5)
    earlier=prior('longchang-self-writings')
    old_desc=next((x['legacyStop']['descZh'] for x in (earlier or {}).get('searchLog',[]) if 'legacyStop' in x),stop['descZh'])
    new_desc='【AI辅助整理·未经人工审校】《年谱》记“春至龍場”，并叙其格物致知之悟；所收东洞诗又有“移居”“洞居”之语。两类记述分别保留，具体居址与过程仍待核。'
    if stop['descZh'] not in [old_desc,new_desc]:raise ValueError('站点叙述已有其他修订，禁止生成脚本覆盖')
    if any((prior(k) or {}).get('reviewHistory') for k in ['longchang-self-writings','longchang-chronicle-context','guizhou-yangming-cave']):
        raise ValueError('已有人工作业，禁止生成脚本改写相关研究与站点')
    cache=ROOT.parent/'.local/research-cache'
    for item in observations:
        verify_observation_assets(item,{h:(cache/'objects'/h).read_bytes() for h in observation_hashes(item)})
    if next((x for x in discovery['items'] if x['id']==ident),None)!=image:discovery['checkedAt']=now()
    discovery['items']=[x for x in discovery['items'] if x['id']!=ident]+[image];dump(ROOT/'data/source-discovery.json',discovery)
    registry=read(ROOT/'shared/sources.json');source=next(s for s in registry['sources'] if s['id']=='commons-guizhou-siku')
    source['imageAssets']=[asset_descriptor(x) for x in discovery['items'] if x.get('collection')=='guizhou-tongzhi-research' and x['channel']=='image' and x.get('artifactProbe',{}).get('status')=='reachable']
    source['coverage']=['已取卷4–5、8–9、19–20、27–28四份平台标四库影像；版刻关系和全文待核']
    dump(ROOT/'shared/sources.json',registry)
    for ev in evidence:
        path=ROOT/ev['textFile'];raw=ev['quote'].encode()
        if path.exists() and path.read_bytes()!=raw:raise ValueError('原态摘引冲突')
        path.write_bytes(raw)
    revised=copy.deepcopy(old)
    for key in ['revision','updatedAt','sha256']:revised.pop(key,None)
    revised.update(imageObservations=observations,provenance=provenance(old,'imageObservations'),
        claim='AI辅助资料解释·未经人工审校。电子卷首三十八与卷末二十八有冲突；另取CADAL图112卷首、图113版心，AI目读均为二十八。原转录保留，未裁定差异原因。',
        reasoning='所取影像两处题名与电子卷末相合、与电子卷首不同；只能形成局部图文差异候选，不能由同名四库标签断定同一物理底本或直接判定原刻/转录错误。',
        nextAction='人工对图112卷首、图113版心和电子上下文核字形、版本关系；未裁定前不改原转录。')
    save_record(ROOT,revised)
    for rid,title,subject,ev,claim in [
        ('longchang-chronicle-context','龙场年谱：到达、石墎自誓与悟学分段',{'type':'work','key':'王阳明年谱'},evidence[:3],
         '《年谱》分别记春至龙场、石墎自誓及格物致知之悟；没有把这三个片段改写成居东洞石棺。'),
        ('longchang-self-writings','东洞诗与何陋轩记：居处自述候选',{'type':'journey','key':'wangyangming'},evidence[3:],
         '所收东洞诗有移居、洞居之语，何陋轩记有谪居龙场自述；不能仅凭文字认定现代精确居址或把不同记述合为一景。')]:
        previous=prior(rid)
        legacy=next((x['legacyStop'] for x in (previous or {}).get('searchLog',[]) if 'legacyStop' in x),{k:stop[k] for k in ['titleZh','descZh','source']})
        doc={'id':rid,'subject':subject,'kind':'witness','status':'partial','visibility':'public','title':title,
            'claim':'AI辅助资料解释·未经人工审校。'+claim,'provenance':provenance(previous),'evidence':ev,
            'issues':['年谱为后编叙述，诗文为所收作品，文献性质分别保留；原卷/字形与影像尚待核。','旧基线引文和反推繁体不因相关片段而自动核定。'],
            'reasoning':'只按所取原态材料拆分叙述依据，不以同书片段数充当独立佐证。',
            'counterEvidence':'尚未完成独立版本和影像核查；未据这些文本确证居址、全部细节或默认纪年。',
            'alternatives':['不同材料可能记不同居处或阶段，不自动连成同一场景。'],'reviewHistory':[],
            'searchLog':[{'sourceId':'kanripo-kr4e0157','relatedStop':'wangyangming:5','legacyStop':legacy}],
            'nextAction':'核各篇原卷及独立版本，分别确认居住、悟学、石墎叙事，不以现代纪念建筑代证。'}
        save_record(ROOT,doc)
    cave=prior('guizhou-yangming-cave');updated=copy.deepcopy(cave)
    for key in ['revision','updatedAt','sha256']:updated.pop(key,None)
    updated.update(provenance=provenance(cave,'relatedResearch'),relatedResearch=['longchang-self-writings/1','longchang-chronicle-context/1'],
        evidence=[cave['evidence'][0],evidence[3]],
        claim='AI辅助资料解释·未经人工审校。方志的游息条不能单独证明居住；新取所收东洞诗确有移居、洞居之语。分别保留文献性质，居址及细节仍待核。')
    save_record(ROOT,updated)
    stop['titleZh']='谪居龙场·悟道记述'
    stop['descZh']=new_desc
    stop['source']='《王文成公全書》原卷三十二《年譜一》（SBCK，KR4e0157_021，13b–14a）；原卷十九《始得東洞遂改為陽明小洞天三首》（014，44b–45a）。AI辅助整理·未经人工审校；居址与纪年待核。'
    dump(ROOT/'data/journeys/wangyangming.json',journey);build_index(ROOT)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');main(p.parse_args().apply)
