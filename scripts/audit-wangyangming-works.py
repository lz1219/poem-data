"""六作品按实际篇题和原态片段核查；不把相近匹配升级为核定正文。"""
import argparse
import io
import json
import re
import zipfile
from research import ROOT,read,dump,cached_response,now
from original_volume_locators import scan_headings,sha
from research_records import save_record,build_index

CASES={
 '与杨仕德薛尚谦书':('004','與楊仕徳薛尚誠','寄聞人邦英邦正','破山中賊易','破心中賊難','witness','篇题所载尚誠与本站尚谦不同；不据转录自动统一收信人姓名。'),
 '传习录':('003','先生曰衆人只說格物要依晦翁','初年與錢友','衆人只說','我着實曾用来','witness','本站旧引上录，所取片段在原卷三；字形及卷次待核。'),
 '天泉证道·四句教':('003','丁亥年九月先生起復征思田','徳洪曰此意如何','無善無惡是心之體','爲善去惡是格物','witness','本站有噁/惡、是字等差异；不得由回推文本代替原录。原1521缺可靠依据，丁亥九月是论学线索，录文写定年另核。'),
 '泛海':('014','泛海','武夷次壁間韻','險夷原不滯胸中','月明飛錫下天風','witness','所取转录用静、里；本站回推为靜、裡。保留字形差异，不先定为古籍实质异文。'),
 '告谕庐陵父老':('011','告諭廬陵父老子弟','廬陵縣公移',None,None,'audit','原篇已定位，但未在所选篇段确认本站吉神/厉鬼摘句；不以未命中判伪造，须查别本与影像。'),
 '擒获宸濠捷音疏':('007','擒獲宸濠捷音䟽','益王助軍餉䟽',None,None,'audit','原篇已定位，但未确认本站一鼓而克其巢穴等摘句；不以相关军报通用词充当逐字佐证。')}


def han(text):
    positions=[i for i,c in enumerate(text) if '\u3400'<=c<='\u9fff']
    return ''.join(text[i] for i in positions),positions


def case_source(raw,case):
    text=raw.decode('utf-8');_,begin,end,focus_first,focus_last,kind,_=case
    start=text.index(begin);stop=text.find(end,start+len(begin))
    if stop<0:raise ValueError('未找到下一明确篇段边界：'+begin)
    frame=text[start:stop];norm,offsets=han(frame)
    if focus_first:
        a=norm.find(focus_first);b=norm.find(focus_last,a)
        if a<0 or b<0:raise ValueError('未在所选原篇段取得焦点原句')
        fs,fe=start+offsets[a],start+offsets[b+len(focus_last)-1]+1
        focus=text[fs:fe]
        # 保留简短上下文，引用仍是同一连续原片段；不用生成句重构原文。
        qs=max(start,fs-45);qe=min(stop,fe+25)
    else:
        focus='';qs=start;qe=start+offsets[min(65,len(offsets)-1)]+1
    heads=[h for h in scan_headings(raw) if h['startByte']<=len(text[:qs].encode())]
    pages=list(re.finditer(r'<pb:([^>]+)>',text[:qs]))
    return {'quote':text[qs:qe],'focusOriginal':focus,'startByte':len(text[:qs].encode()),'endByte':len(text[:qe].encode()),
            'scopeStartByte':len(text[:start].encode()),'scopeEndByte':len(text[:stop].encode()),
            'nearestOriginalVolumeHeading':heads[-1]['header'] if heads else None,
            'sourcePageMarker':pages[-1][1] if pages else None,'scopeText':frame}


def main(apply):
    source=next(s for s in read(ROOT/'data/acquisition-manifest.json')['repositories'] if s['repository']=='kanripo/KR4e0157' and not s.get('branch'))
    rawzip=cached_response(ROOT.parent/'.local/research-cache',source['url'],source['archiveSha256']);report=[]
    with zipfile.ZipFile(io.BytesIO(rawzip)) as archive:
        for key,case in CASES.items():
            path=ROOT/'data/works'/(key+'.json');work=read(path);name='KR4e0157_'+case[0]+'.txt';member=next(n for n in archive.namelist() if n.endswith('/'+name));raw=archive.read(member)
            found=case_source(raw,case);target=''.join(han(p)[0] for p in work['text']['paragraphs']);candidate=han(found['scopeText'])[0]
            exact=target in candidate;digest=sha(found['quote'].encode());rid='wang-source-'+sha(key.encode())[:20]
            prior=ROOT/'data/research'/(rid+'.json');old=read(prior) if prior.exists() else None
            citation=work.get('citation','')
            if old:legacy=old['searchLog'][0]['legacyCitation']
            else:legacy=citation
            row={'workKey':key,'legacyCitation':legacy,'file':name,**{k:v for k,v in found.items() if k!='scopeText'},
                 'canonicalHanOnlyMatch':exact,'matchLimitation':'只作去非汉字检索；不等于原字符/标点或版本已核',
                 'result':'text-correspondence-candidate' if case[5]=='witness' else 'document-located-quote-unconfirmed','issues':[case[6]],'reviewStatus':'pending'}
            report.append(row)
            print(key+'：'+row['result']+'；近前原卷题 '+str(found['nearestOriginalVolumeHeading']),flush=True)
            if not apply:continue
            artifact=ROOT/'data/witnesses'/(digest+'.txt')
            if artifact.exists() and artifact.read_bytes()!=found['quote'].encode():raise ValueError('原态摘引冲突')
            artifact.write_bytes(found['quote'].encode())
            # 来源状态纠正只标未核，原来引名保留；不替编辑选择已核底本。
            if '《王阳明全集·' in citation and '待核' not in citation:work['citation']='旧引'+citation+'（来源名及原典卷篇待核）'
            if key=='传习录' and citation=='《传习录》上':work['citation']='旧引《传习录》上（卷次待核；所取SBCK转录候选见原卷三）'
            if key=='天泉证道·四句教' and work.get('composed',{}).get('year')==1521:
                work['composed']['year']=None
                for dating in work.get('dating',[]):
                    if dating.get('claim')=='1521':dating['note']+=' 当前默认作年撤出无据数字；旧占位1521与背景所载嘉靖六年不一致；原录另见丁亥九月论学线索，口授与录文时间须另核，不自动改采另一公历年。'
            dump(path,work)
            url='https://github.com/'+source['repository']+'/blob/'+source['commit']+'/'+name
            doc={'id':rid,'subject':{'type':'work','key':key},'kind':case[5],'status':'partial' if case[5]=='witness' else 'pending','visibility':'public',
                 'title':work['titleZh']+' · 原典出处/字形候选核查',
                 'claim':'取得相关原篇及原态片段，存在字形/篇题/卷次等待核差异；不直接取代本站基线。' if case[5]=='witness' else '取得原篇题和正文片段，尚未在所选篇段确认本站摘句；未判该句不存在或伪造。',
                 'provenance':{'origin':'mixed','model':'Codex','modelVersion':'运行环境未提供精确模型快照','generatedAt':old['provenance']['generatedAt'] if old else now(),
                               'method':'程序按原篇题截取真实字节；AI辅助说明检索边界与差异，未经人工学术审校'},
                 'evidence':[{'sourceId':'kanripo-kr4e0157','quote':found['quote'],'locator':name+'，'+str(found['sourcePageMarker'])+'，近前原卷题候选'+str(found['nearestOriginalVolumeHeading']),
                              'url':url,'commit':source['commit'],'originalFileSha256':sha(raw),'sha256':digest,'textFile':'data/witnesses/'+digest+'.txt',
                              'startByte':found['startByte'],'endByte':found['endByte'],'verifiedQuote':True,'verification':'保存片段与原文件逐字节对应；不代表本站摘句已核','stance':'context','grade':'ungraded'}],
                 'issues':[case[6],'旧基线与电子转录分别保留；去排版检索不裁定古本异文，版刻和模板字需对影像。'],
                 'reasoning':'原片段和明确篇题提供继续考证的依据；检索相同、相近或未命中均不自动形成核定结论。',
                 'counterEvidence':'本次仅检索所取SBCK电子转录；其他版本、转录缺字或异体字可能改变结果，尚未完成反证与影像核验。',
                 'alternatives':['可能涉及回推字形、转录异体或不同版本；原句未确证者也可能是旧引范围或引名有误，均待核。'],
                 'reviewHistory':[],'searchLog':[{'sourceId':'kanripo-kr4e0157','legacyCitation':legacy,'file':name,'scopeStartByte':found['scopeStartByte'],'scopeEndByte':found['scopeEndByte'],'hanOnlyMatch':exact,'mode':'原篇段检索，不是全文学术校勘'}],
                 'nextAction':'对原影像核篇题、卷次和字形；未确证摘句继续寻别本/上游引文，不编造原文或系年。'}
            save_record(ROOT,doc)
    if apply:
        dump(ROOT/'data/wangyangming-work-audit.json',{'checkedAt':now(),'repository':source['repository'],'commit':source['commit'],'items':report,'academicReview':'pending'})
        build_index(ROOT)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');main(p.parse_args().apply)
