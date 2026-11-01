"""定位显式原卷题；不据文件编号分卷，不改原文。"""
import bisect
import hashlib
import re
from wikisource_source import chinese_number

HEADING=re.compile(r'(?m)^(?:\ufeff)?[^\S\r\n]*(?P<header>王文成公全書[卷巻](?:之)?(?:第)?(?P<number>[一二三四五六七八九十百零]+))')
BARE=re.compile(r'王文成公全書[卷巻](?:之)?(?:第)?([一二三四五六七八九十百零]+)')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def scan_headings(raw):
    text=raw.decode('utf-8');pages=list(re.finditer(r'<pb:([^>]+)>',text));offsets=[m.start() for m in pages];rows=[]
    for match in HEADING.finditer(text):
        start,end=match.span('header');page=bisect.bisect_right(offsets,start)-1
        rows.append({'volume':chinese_number(match['number']),'header':match['header'],
                     'startByte':len(text[:start].encode()),'endByte':len(text[:end].encode()),
                     'headerSha256':sha(text[start:end].encode()),'fileSha256':sha(raw),
                     'sourcePageMarker':pages[page][1] if page>=0 else None,
                     'parser':'explicit-volume-heading-v1','status':'pending',
                     'scope':'仅卷题位置；不是已核卷文边界或完整卷文本'})
    return rows


def validate_locator(doc,raw):
    if sha(raw)!=doc['fileSha256']:raise ValueError('卷题原件哈希不符')
    start,end=doc['startByte'],doc['endByte']
    if type(start) is not int or type(end) is not int or not 0<=start<end<=len(raw):raise ValueError('卷题字节范围非法')
    fragment=raw[start:end]
    if fragment.decode('utf-8')!=doc['header'] or sha(fragment)!=doc['headerSha256']:raise ValueError('卷题原句与范围不符')
    hit=BARE.fullmatch(doc['header'])
    if not hit or type(doc['volume']) is not int or chinese_number(hit[1])!=doc['volume']:raise ValueError('原卷号与卷题不符')
    line=raw[raw.rfind(b'\n',0,start)+1:start].decode('utf-8')
    if line.strip('\ufeff').strip():raise ValueError('卷题候选并非行首标题')
    pages=list(re.finditer(rb'<pb:([^>]+)>',raw[:start]));marker=pages[-1][1].decode('utf-8') if pages else None
    if marker!=doc.get('sourcePageMarker'):raise ValueError('源页标记与卷题位置不符')
    return True
