"""Read the latest explanation only when its source text and version still match."""
import hashlib

from . import db


def attach_explanations(unit, paragraphs):
    if not unit.get('origin'):
        return
    present = db.one("SELECT to_regclass('public.corpus_paragraph_explanation') IS NOT NULL AS ok")
    if not present or not present['ok']:
        return
    rows = db.query('''SELECT DISTINCT ON (paragraph_id) paragraph_id,revision,source_sha256,
             source_revision,edition_id,state,content,generation
        FROM public.corpus_paragraph_explanation WHERE unit_id=%s
        ORDER BY paragraph_id,revision DESC''', (unit['id'],))
    by_id = {p['id']: p for p in paragraphs}
    origin = (unit.get('origin') or {}).get('metadata') or {}
    edition_id = (unit.get('origin') or {}).get('edition_id')
    for row in rows:
        paragraph = by_id.get(row['paragraph_id'])
        if not paragraph or row['state'] != 'unreviewed':
            continue
        if (hashlib.sha256((paragraph.get('body') or '').encode()).hexdigest() != row['source_sha256']
                or origin.get('revisionId') != row['source_revision'] or edition_id != row['edition_id']):
            continue
        item = row['content']
        if not isinstance(item, dict) or item.get('aiLabel') != 'AI生成·未经人工审校' or item.get('reviewStatus') != 'unreviewed':
            continue
        body = paragraph.get('body') or ''
        notes = item.get('notes')
        if (item.get('paragraphId') != paragraph['id'] or item.get('revision') != row['revision']
                or item.get('sourceText') != body or item.get('sourceSha256') != row['source_sha256']
                or not isinstance(item.get('translation'), str) or not item['translation'].strip()
                or not isinstance(notes, list)):
            continue
        if any(not isinstance(n, dict) or type(n.get('start')) is not int or type(n.get('end')) is not int
               or not 0 <= n['start'] < n['end'] <= len(body) or body[n['start']:n['end']] != n.get('quote')
               or not isinstance(n.get('explanation'), str) or not n['explanation'].strip() for n in notes):
            continue
        paragraph['explanation'] = {'revision': row['revision'], 'translation': item['translation'],
            'notes': item['notes'], 'aiLabel': item['aiLabel'], 'generation': row['generation']}
