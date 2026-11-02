"""Disposable reading views. Original text, offsets and database rows are untouched."""
from functools import lru_cache
from importlib.metadata import version
import hashlib
import re


@lru_cache(maxsize=2)
def converter(config='t2s.json'):
    try:
        from opencc import OpenCC
        return OpenCC(config), version('opencc')
    except ImportError:
        return None, None


def query_forms(text):
    forms = [text]
    for config in ('t2s.json', 's2t.json'):
        cc, _ = converter(config)
        if cc:
            value = cc.convert(text)
            if value not in forms:
                forms.append(value)
    return forms


def _spans(body, origin):
    spans = origin.get('spans') or []
    position = 0
    for span in spans:
        if (span.get('kind') not in ('source-text', 'source-parenthetical') or
                span.get('start') != position or not isinstance(span.get('end'), int) or
                not position < span['end'] <= len(body)):
            return ((0, len(body), 'source-text'),) if body else ()
        position = span['end']
    if position != len(body):
        return ((0, len(body), 'source-text'),) if body else ()
    return tuple((s['start'], s['end'], s['kind']) for s in spans)


@lru_cache(maxsize=256)
def _page(body, spans, source_page):
    cc, _ = converter()
    output = []
    for start, end, kind in spans:
        text = body[start:end]
        if source_page:
            # Source-page line breaks and indentation are physical layout.
            text = ''.join(line.strip(' \t\u3000') for line in text.splitlines())
            text = re.sub(r'[ \t\u3000]+', ' ', text)
            if kind == 'source-parenthetical':
                text = text.replace('/', '')
        output.append((kind, text, cc.convert(text) if cc else None))
    return tuple(output)


def attach_reading(unit, paragraphs):
    cc, release = converter()
    raw = unit.get('body') or ''
    pages = []
    for index, paragraph in enumerate(paragraphs or [{'body': raw, 'seq': 1}], 1):
        origin = paragraph.get('origin') or {}
        body = paragraph.get('body') or ''
        source_page = origin.get('segmentation') == 'source-page'
        segments = [{'kind': 'parenthetical' if k == 'source-parenthetical' else 'text',
                     'original': original, 'simplified': simplified}
                    for k, original, simplified in _page(body, _spans(body, origin), source_page)]
        pages.append({'seq': paragraph.get('seq', index), 'paragraphId': paragraph.get('id'),
                      'pageLabel': origin.get('pageLabel'), 'sourcePage': source_page, 'segments': segments})
    unit['reading'] = {
        'simplifiedAvailable': cc is not None,
        'conversion': {'engine': 'OpenCC', 'version': release, 'config': 't2s.json',
                       'status': 'machine-converted; not a translation or verified source text'},
        'originalSha256': hashlib.sha256(raw.encode()).hexdigest(),
        'layout': 'Source-page hard wraps joined and layout whitespace normalized; parenthetical slash layout markers hidden. Other paragraph line breaks retained.',
        'noteGrouping': '原录括号分组，仅供阅读，非注者归属核定',
        'pages': pages,
    }
