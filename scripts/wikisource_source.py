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


def plain_inline(text):
    """Only the explicitly audited inline subset; unknown markup stops import."""
    import html
    text = re.sub(r'\[\[([^\[\]]+)\]\]', lambda m: m[1].split('|')[-1], text)
    text = re.sub(r'-\{([^{};|:]+)\}-', r'\1', text)
    text = re.sub(r'</?u>', '', text)
    text = re.sub(r'</?br\s*/?>', '\n', text)
    if re.search(r'\{\{|\}\}|\[\[|\]\]|<[A-Za-z!/]|-\{|\}-', text):
        raise ValueError('Unsupported wiki markup; preserve capture and revise parser explicitly')
    return html.unescape(text)


def reading_paragraphs(text):
    """Keep wiki editorial notes separate, with anchors in rendered main text."""
    header = re.match(r'\{\{header\n.*?\}\}\s*', text, re.S)
    tail = re.search(r'\n==註釋==\s*\{\{reflist\}\}\s*$', text)
    if not header or not tail:
        raise ValueError('Expected audited header and reference-list boundary')
    result = []
    blocks = r'(?m)^={2,3}[^=\n]+={2,3}[ \t]*(?=\n|$)|\S[\s\S]*?(?=\n\s*\n|\n={2,3}[^=\n]+={2,3}(?:\n|$)|\Z)'
    for match in re.finditer(blocks, text[header.end():tail.start()]):
        start, end = header.end() + match.start(), header.end() + match.end()
        chunk = text[start:end].rstrip()
        end = start + len(chunk)
        heading = re.fullmatch(r'(={2,3})([^=\n]+)\1', chunk)
        inline_start = start
        if heading:
            inline_start += len(heading[1])
            chunk = heading[2]
        pieces, annotations, pos = [], [], 0
        for note in re.finditer(r'<ref>(.*?)</ref>', chunk, re.S):
            pieces.append(plain_inline(chunk[pos:note.start()]))
            value = plain_inline(note[1])
            if not value.strip():
                raise ValueError('Empty editorial note')
            annotations.append({'anchor': sum(len(p) for p in pieces), 'body': value,
                                'kind': 'wiki-editorial-note', 'attribution': '维基编者注·注者待核',
                                'sourceByteStart': len(text[:inline_start + note.start()].encode()),
                                'sourceByteEnd': len(text[:inline_start + note.end()].encode())})
            pos = note.end()
        pieces.append(plain_inline(chunk[pos:]))
        body = ''.join(pieces)
        if not body:
            raise ValueError('Empty paragraph after explicit markup conversion')
        result.append({'body': body, 'origin': {
            'segmentation': 'source-paragraph', 'offsetUnit': 'unicode-code-point',
            'sourceByteStart': len(text[:start].encode()), 'sourceByteEnd': len(text[:end].encode()),
            'kind': 'heading' if heading else 'paragraph', 'annotations': annotations,
            'spans': [{'kind': 'source-text', 'start': 0, 'end': len(body)}]}})
    if sum(len(p['origin']['annotations']) for p in result) != text.count('<ref>'):
        raise ValueError('Editorial-note count changed during parsing')
    return result


def chronicle_inline(text):
    """Audited Zizhi Tongjian display syntax; never evaluate arbitrary templates."""
    if re.search(r'(?m)^\s*(?:\{\||\|\}|\|)', text):
        raise ValueError('Wiki tables need a separate audited table adapter')
    text = re.sub(r'-\{([^{};|:]+)\}-', r'\1', text)
    text = re.sub(r'\{\{\*\|([^{}|]+)\}\}', r'（\1）', text)
    text = text.replace("'''", '')
    text = re.sub(r'(?m)^:{1,2}[ \t]?', '', text)
    return plain_inline(text)


def chronicle_paragraphs(text, *, allow_batch_shapes=False):
    """Keep source headings and within-year event numbers, without guessing dates.

    Limited to the header2 / 校刊記 profile in the audited first two volumes.
    All visible source blocks have byte ranges; reference text is stored apart.
    """
    quality = r'(?:\{\{textquality\|(?:25|50|75)%\}\}\s*)?' if allow_batch_shapes else ''
    header = re.match(quality+r'\{\{header2\n[^{}]*\}\}\s*', text, re.I if allow_batch_shapes else 0)
    tail_names = r'(?:校刊記|校改記|校記)' if allow_batch_shapes else '校刊記'
    tails = list(re.finditer(r'(?m)^(={1,6})[ \t]*'+tail_names+r'[ \t]*\1[ \t]*$', text))
    if not header or len(tails)>1:
        raise ValueError('Expected audited header and at most one reference boundary')
    if tails:
        tail_start,tail_end=tails[0].start(),tails[0].end()
    else:
        if not allow_batch_shapes or re.search(r'<ref\b|<references\b',text):
            raise ValueError('Missing audited reference boundary')
        trailer_start=re.search(r'(?im)^(?:\[\[category:資治通鑑(?:\|[^\[\]\n]*)?\]\]|\{\{\s*footer(?:\s*\n|\|))',text[header.end():])
        if not trailer_start:raise ValueError('Missing audited source footer')
        tail_start=tail_end=header.end()+trailer_start.start()
    trailer = text[tail_end:]
    trailer = re.sub(r'<div class="references-small">\s*<references\s*/>\s*</div>', '', trailer)
    trailer = re.sub(r'\[\[category:資治通鑑(?:\|[^\[\]\n]+)?\]\]', '', trailer, flags=re.I)
    trailer = re.sub(r'\{\{\s*footer(?:\s*\n|\|)[^{}]*\}\}|\{\{北宋作品\}\}', '', trailer)
    if trailer.strip():
        raise ValueError('Unsupported material after the reference-list boundary')
    source = text[header.end():tail_start]
    # Legacy paragraphs were line-based. Keep those boundaries while allowing
    # a single editorial reference to contain newlines; do not merge IDs merely
    # because several consecutive commentary lines share no blank line.
    pattern = r'(?m)^(?:<ref>[\s\S]*?</ref>|[^\n<]|<(?!ref>))+'
    result, path, cursor = [], [], 0
    for match in re.finditer(pattern, source):
        if source[cursor:match.start()].strip():
            raise ValueError('Unparsed source between blocks')
        cursor = match.end()
        start = header.end() + match.start()
        chunk = match[0].rstrip()
        if not chunk.strip():
            continue
        if re.fullmatch(r'\s*-{4,}\s*',chunk):
            if allow_batch_shapes:
                continue
            raise ValueError('Source divider requires explicit paragraph migration')
        end = start + len(chunk)
        heading = re.fullmatch(r'(={1,6})([^\n]+?)\1[ \t]*', chunk)
        inline_start = start
        if heading:
            inline_start += len(heading[1])
            chunk = heading[2]
        pieces, annotations, restorations, position = [], [], [], 0
        inline_pattern = r'<ref>(.*?)</ref>|\{\{参\|適\|同嫡\}\}' if allow_batch_shapes else r'<ref>(.*?)</ref>'
        for note in re.finditer(inline_pattern, chunk, re.S):
            pieces.append(chronicle_inline(chunk[position:note.start()]))
            if note[0].startswith('{{'):
                anchor = sum(map(len, pieces))
                pieces.append('適')
                restorations.append({'anchor': anchor, 'text': '適', 'reason': 'source-template-first-argument'})
                annotations.append({'anchor': anchor + 1, 'body': '同嫡', 'kind': 'wiki-editorial-note',
                    'attribution': '维基编者注·注者待核',
                    'sourceByteStart': len(text[:inline_start + note.start()].encode()),
                    'sourceByteEnd': len(text[:inline_start + note.end()].encode())})
                position = note.end()
                continue
            value = chronicle_inline(note[1])
            if not value.strip():
                raise ValueError('Empty editorial note')
            annotations.append({'anchor': sum(map(len, pieces)), 'body': value,
                'kind': 'wiki-editorial-note', 'attribution': '维基编者注·注者待核',
                'sourceByteStart': len(text[:inline_start + note.start()].encode()),
                'sourceByteEnd': len(text[:inline_start + note.end()].encode())})
            position = note.end()
        pieces.append(chronicle_inline(chunk[position:]))
        body = ''.join(pieces)
        if heading:
            # Source heading whitespace has no bibliographic meaning; retain it
            # in the capture/range, while exposing a readable heading string.
            leading = len(body) - len(body.lstrip())
            body = body.strip()
            for note in annotations:
                note['anchor'] -= leading
        elif allow_batch_shapes:
            leading = len(body) - len(body.lstrip())
            if leading:
                body = body[leading:]
                for note in annotations:
                    if note['anchor'] < leading:
                        raise ValueError('Note anchored in leading source whitespace')
                    note['anchor'] -= leading
                for restoration in restorations:
                    restoration['anchor'] -= leading
        if not body:
            raise ValueError('Empty source block')
        origin = {'segmentation': 'source-paragraph', 'offsetUnit': 'unicode-code-point',
            'sourceByteStart': len(text[:start].encode()), 'sourceByteEnd': len(text[:end].encode()),
            'kind': 'heading' if heading else 'paragraph', 'annotations': annotations,
            'spans': [{'kind': 'source-text', 'start': 0, 'end': len(body)}]}
        if restorations:
            origin['sourceInlineRestorations'] = restorations
        if heading:
            level = len(heading[1])
            path = [p for p in path if p['level'] < level] + [{'level': level, 'title': body}]
            origin['headingLevel'] = level
        else:
            event = re.match(r'^(\d+)\u3000', body)
            if event:
                origin['eventNumber'] = event[1]
                origin['numberMeaning'] = 'source within-year event label; not a year or verified original author numbering'
        origin['headingPath'] = [dict(p) for p in path]
        result.append({'body': body, 'origin': origin})
    if source[cursor:].strip() or not result:
        raise ValueError('Unparsed or empty source body')
    if sum(len(p['origin']['annotations']) for p in result) != text.count('<ref>') + (text.count('{{参|適|同嫡}}') if allow_batch_shapes else 0):
        raise ValueError('Editorial-note count changed during parsing')
    if sum(p['origin']['kind'] == 'heading' for p in result) != len(re.findall(r'(?m)^=+[^\n]+?=+[ \t]*$', source)):
        raise ValueError('Source heading count changed during parsing')
    return result


def legacy_projection(text):
    """Reproduce the retired parser solely to map old IDs to fixed source text."""
    value = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    value = re.sub(r'<ref[^>]*>.*?</ref>', '', value, flags=re.S)
    value = re.sub(r'\{\{[^{}]*\}\}', '', value)
    value = re.sub(r'<[^>]+>', '', value)
    value = re.sub(r'\[\[[^\]|]*\|([^\]]*)\]\]', r'\1', value)
    value = re.sub(r'\[\[([^\]]*)\]\]', r'\1', value)
    value = re.sub(r"'{2,}", '', value)
    result = []
    for line in value.split('\n'):
        line = line.strip('\u3000 \t\r')
        if not line or line.startswith(('==', '|', '{{')):
            continue
        line = re.sub(r'^[*#:]+', '', line).strip()
        if line:
            result.append(line)
    return result


def attach_legacy_mapping(unit, source):
    """Every retained/retired old row must be explained by an actual source range."""
    projected = []
    raw = source.encode()
    previous = 0
    for block in unit['paragraphs']:
        origin = block['origin']
        between = legacy_projection(raw[previous:origin['sourceByteStart']].decode())
        if any(not re.fullmatch(r'-{4,}', line) for line in between):
            raise ValueError('Unexpected legacy material between source blocks')
        block['legacyRetiredBefore'] = between
        projected.extend(between)
        old = legacy_projection(raw[origin['sourceByteStart']:origin['sourceByteEnd']].decode())
        if len(old) > 1:
            raise ValueError('New block merges existing paragraph boundaries')
        block['legacyText'] = old[0] if old else None
        projected.extend(old)
        previous = origin['sourceByteEnd']
    trailer = legacy_projection(raw[unit['paragraphs'][-1]['origin']['sourceByteEnd']:].decode())
    complete = legacy_projection(source)
    if projected + trailer != complete:
        raise ValueError('Source mapping does not account for every legacy paragraph')
    unit['legacyProjection'] = {'parser': 'legacy-wikisource-clean-v1',
        'bodySha256': sha('\n'.join(complete).encode()), 'trailer': trailer}


def reading_plan(cache, selection):
    """Build an immutable plan from fixed captures, never live page content."""
    from backfill_shiji import digest, require
    profile = selection.get('profile', 'chuanxilu')
    require(profile in ('chuanxilu', 'zztj-first-two', 'zztj-batch'), 'Unreviewed reading profile')
    chronicle = profile in ('zztj-first-two', 'zztj-batch')
    parser_name = ('wikisource-chronicle-batch-v1' if profile == 'zztj-batch' else
                   'wikisource-chronicle-headings-notes-v1' if chronicle
                   else 'wikisource-explicit-inline-and-notes-v1')
    permission = selection['permissionCapture']
    declaration = cached_response(cache, permission['url'], permission['sha256']).decode('utf-8')
    require('creativecommons.org/licenses/by-sa/4.0' in declaration,
            'Fixed provider permission declaration not found')
    capture = selection['capture']
    raw = cached_response(cache, capture['url'], capture['sha256'])
    units, revisions = [], []
    for spec in selection['volumes']:
        decoded = decode_capture({'title': spec['title'], 'captureFormat': 'mediawiki-export-xml'}, raw)
        require(decoded['revid'] == spec['revisionId'], 'Fixed revision differs from selection')
        require(sha(decoded['text'].encode()) == spec['textSha256'], 'Fixed wikitext differs')
        paragraphs = (chronicle_paragraphs(decoded['text'], allow_batch_shapes=profile == 'zztj-batch')
                      if chronicle else reading_paragraphs(decoded['text']))
        text_offset = 0
        for paragraph in paragraphs:
            paragraph['origin']['textStart'] = text_offset
            text_offset += len(paragraph['body'])
            paragraph['origin']['textEnd'] = text_offset
            text_offset += 2
        body = '\n\n'.join(p['body'] for p in paragraphs)
        url = 'https://zh.wikisource.org/w/index.php?oldid=' + str(decoded['revid'])
        origin = {'sourcePath': decoded['title'], 'sourceSha256': spec['textSha256'],
                  'sourceOrder': len(units) + 1,
                  'sourceByteStart': 0, 'sourceByteEnd': len(decoded['text'].encode()),
                  'kind': 'body-volume', 'parser': parser_name,
                  'revisionId': decoded['revid'], 'revisionTimestamp': decoded['timestamp'],
                  'reviewStatus': 'transcription-unreviewed', 'sourceUrl': url,
                  'noteAttribution': '维基编者注·注者待核；不视为古人评点',
                  'baseEdition': selection['baseEdition']}
        if profile == 'zztj-batch':
            quality = re.match(r'\{\{textquality\|((?:25|50|75)%)\}\}', decoded['text'], re.I)
            if quality:
                origin['sourceTextQualityIndicator'] = {'value': quality.group(1),
                    'status': 'source indicator; not a human review by this project'}
        units.append({'juan': spec['juan'], 'body': body, 'sha256': sha(body.encode()),
                      'sourceUrl': url, 'punctuated': True, 'origin': origin, 'paragraphs': paragraphs})
        if chronicle:
            attach_legacy_mapping(units[-1], decoded['text'])
            from importlib.metadata import version
            try:
                from opencc import OpenCC
                units[-1]['bodySimplified'] = OpenCC('t2s.json').convert(body)
                origin['readingConversion'] = {'engine': 'OpenCC', 'version': version('opencc'),
                    'config': 't2s.json', 'status': 'machine-converted; not a verified source or translation'}
            except ImportError:
                units[-1]['bodySimplified'] = None
        revisions.append({k: decoded[k] for k in ('pageid', 'title', 'revid', 'timestamp')})
    if profile == 'chuanxilu':
        require(selection['bookId'] == 20 and len(units) == 3 and
                [u['juan'] for u in units] == ['卷上', '卷中', '卷下'],
                'This audited selection must contain exactly three Chuanxilu volumes')
    elif profile == 'zztj-first-two':
        require(selection['bookId'] == 80 and selection['bookTitle'] == '資治通鑑' and
                [s['title'] for s in selection['volumes']] == ['資治通鑑/卷001', '資治通鑑/卷002'] and
                [u['juan'] for u in units] == ['卷001', '卷002'],
                'Chronicle specimen is restricted to the audited first two Zizhi Tongjian volumes')
    else:
        require(selection['bookId'] == 80 and selection['bookTitle'] == '資治通鑑' and units and
                len({u['juan'] for u in units}) == len(units) and
                all(re.fullmatch(r'卷\d{3}', u['juan']) and s['title'] == '資治通鑑/' + u['juan']
                    for u, s in zip(units, selection['volumes'])), 'Invalid batch volume selection')
    info = {'parser': parser_name, 'bookId': selection['bookId'],
            'bookTitle': selection['bookTitle'], 'edition': selection['editionName'],
            'editionName': selection['editionName'], 'source': {
                'provider': 'Wikisource', 'url': capture['url'], 'sha256': capture['sha256'],
                'revisions': revisions, 'baseEdition': selection['baseEdition']},
            'permissionBasis': permission, 'license': 'CC-BY-SA-4.0 (provider declaration)',
            'attribution': '中文维基文库贡献者；逐卷固定修订及编辑历史见来源链接。保留原标点；移除显示标记，编者注独立存储。',
            'reviewStatus': '转录待校；纸本底本与编者注归属待核，非具名人工审校',
            'coverage': {'included': ('维基通鉴固定修订及原页纪年标题和编者注；仅已选择卷'
                                      if chronicle else '维基传习录卷上、卷中、卷下及原页编者注'),
                         'reason': '仅该电子修订范围，不声称影像对校、异版附录、拾遗或现代译注已齐'},
            'counts': {'units': len(units), 'bodyVolumes': len(units),
                       'sourcePageBlocks': sum(len(u['paragraphs']) for u in units),
                       'sourceParagraphBlocks': sum(len(u['paragraphs']) for u in units),
                       'editorialNotes': sum(len(p['origin']['annotations']) for u in units for p in u['paragraphs'])},
            'unitDigests': [digest(u) for u in units]}
    return {'batchId': digest(info), 'manifest': info, 'units': units}


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reading-selection', type=Path)
    parser.add_argument('--cache', type=Path, default=ROOT.parent / '.local/research-cache')
    parser.add_argument('--operation', choices=('preview', 'apply', 'verify', 'rollback'), default='preview')
    parser.add_argument('--credentials', type=Path)
    parser.add_argument('--backup-dir', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--export-plan', type=Path, help='Export the full immutable candidate plan, preview only')
    args = parser.parse_args()
    if not args.reading_selection:
        if args.operation != 'preview':
            parser.error('A fixed reading selection is required for corpus operations')
        main(args.cache)
    else:
        from backfill_shiji import apply, verify, rollback, require
        from research import connect
        plan = reading_plan(args.cache, read(args.reading_selection))
        if args.export_plan:
            if args.operation != 'preview':
                parser.error('Plan export is preview-only')
            dump(args.export_plan, plan)
        if plan['manifest']['parser'] == 'wikisource-chronicle-headings-notes-v1' and args.operation != 'preview':
            parser.error('Chronicle specimen is preview-only; existing-book repair must preserve IDs and audit references first')
        result = {k: plan[k] for k in ('batchId', 'manifest')}
        if args.operation != 'preview':
            require(args.credentials is not None, 'Credentials required; never echoed')
            require(args.operation != 'apply' or args.backup_dir is not None, 'Backup directory required')
            with connect(args.credentials, readonly=args.operation == 'verify') as conn:
                result = apply(conn, plan, args.backup_dir) if args.operation == 'apply' else (
                    verify(conn, plan) if args.operation == 'verify' else rollback(conn, plan))
        if args.output:
            dump(args.output, result)
        print(json.dumps({k: v for k, v in result.items() if k != 'manifest'}, ensure_ascii=False))
