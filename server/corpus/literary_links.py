"""Read explicitly provisional cross-database links and suppress stale candidates."""
import hashlib
import json
import unicodedata
from pathlib import Path

from django.conf import settings
from . import db


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _load(group, key):
    if not isinstance(key, str) or not key or key in ('.', '..') or '/' in key or '\\' in key:
        return None
    try:
        return json.loads((Path(settings.DATA_DIR) / group / (key + '.json')).read_text('utf-8'))
    except (OSError, ValueError):
        return None


def _plain(value):
    return ''.join(ch for ch in value if not ch.isspace() and not unicodedata.category(ch).startswith(('P','Z')))


def _editor_work_matches(work, person):
    from .models import Work
    row=Work.objects.filter(key=work['key']).values('author__key','paragraphs','paragraphs_simplified',
                                                   'source_edition__key').first()
    text=work.get('text') or {}
    return bool(row and row['author__key']==person['key'] and row['paragraphs']==text.get('paragraphs') and
                row['paragraphs_simplified']==text.get('paragraphsSimplified') and
                row['source_edition__key']==text.get('sourceEdition'))


def _editor_stop_matches(journey, stop):
    from .models import Stop
    row=Stop.objects.filter(journey__key=journey['key'],seq=stop['seq']).values(
        'journey__person__key','quote_zh','year','place_ancient').first()
    return bool(row and row['journey__person__key']==journey.get('personKey') and
                row['quote_zh']==(stop.get('quote') or '') and row['year']==stop.get('year') and
                row['place_ancient']==stop.get('place',{}).get('ancient'))


def work_candidates(work_key):
    present=db.one("""SELECT to_regclass('public.corpus_editor_work_poem_candidate') IS NOT NULL
        AND to_regclass('public.corpus_editor_person_candidate') IS NOT NULL
        AND to_regclass('public.corpus_editor_stop_work_candidate') IS NOT NULL AS ok""")
    work=_load('works',work_key)
    if not present or not present['ok'] or not work or work.get('key') != work_key:
        return []
    person=_load('persons',work.get('authorKey'))
    if not person or not person.get('externalIds',{}).get('cbdb') or not _editor_work_matches(work,person):
        return []
    identity=db.query('''SELECT l.editor_sha256,p.key,p.zh,p.cbdb_id FROM public.corpus_editor_person_candidate l
        JOIN public.person p ON p.id=l.person_id WHERE l.editor_person_key=%s''',(person['key'],))
    if not any(x['editor_sha256']==_digest(person) and x['key']==person['key'] and x['zh']==person['zh'] and
               str(x['cbdb_id'])==str(person.get('externalIds',{}).get('cbdb')) for x in identity):
        return []
    rows=db.query('''SELECT l.editor_sha256,l.poem_sha256,l.metadata,p.id,p.title,p.author,p.body,
        o.edition_id,o.batch_id,o.metadata AS origin FROM public.corpus_editor_work_poem_candidate l
        JOIN public.corpus_poem p ON p.id=l.poem_id JOIN public.corpus_poem_origin o ON o.poem_id=p.id
        WHERE l.editor_work_key=%s''',(work_key,))
    stops=db.query('''SELECT journey_key,stop_seq,stop_sha256,relation,metadata
        FROM public.corpus_editor_stop_work_candidate WHERE editor_work_key=%s''',(work_key,))
    results=[]
    for row in rows:
        meta=row['metadata'];body=row['body'] or ''
        if (row['editor_sha256']!=_digest(work) or row['poem_sha256']!=hashlib.sha256(body.encode()).hexdigest()
                or row['edition_id']!=meta.get('corpusEditionId') or row['batch_id']!=meta.get('corpusBatchId')):
            continue
        locations=(row.get('origin') or {}).get('locations') or []
        if not any(x.get('url')==meta.get('sourceUrl') and x.get('jsonPointer')==meta.get('sourcePointer') for x in locations):
            continue
        terms=meta.get('matchingText') or []
        selected=_plain(''.join(work.get('text',{}).get('paragraphsSimplified',[])))
        if not terms or any(not isinstance(x,str) or not x or _plain(x) not in selected or _plain(x) not in _plain(body) for x in terms):
            continue
        valid_stops=[]
        for stop in stops:
            journey=_load('journeys',stop['journey_key'])
            if not journey or journey.get('personKey')!=person['key'] or stop['relation']!='stop-quotes-work':
                continue
            hits=[s for s in journey.get('stops',[]) if s.get('seq')==stop['stop_seq']]
            if len(hits)!=1 or _digest(hits[0])!=stop['stop_sha256'] or not _editor_stop_matches(journey,hits[0]):
                continue
            phrases=stop['metadata'].get('matchingText') or []
            if phrases and all(isinstance(x,str) and x and _plain(x) in _plain(hits[0].get('quote','')) and _plain(x) in _plain(body) for x in phrases):
                valid_stops.append({'journeyKey':stop['journey_key'],'stopSeq':stop['stop_seq'],'relation':'stop-quotes-work'})
        results.append({'status':'candidate','poemId':row['id'],'title':row['title'],'author':row['author'],
                        'differences':meta.get('differences',''),'sourceUrl':meta['sourceUrl'],
                        'personKey':person['key'],'stops':valid_stops})
    return results


def poem_candidates(poem_id):
    present=db.one("SELECT to_regclass('public.corpus_editor_work_poem_candidate') IS NOT NULL AS ok")
    if not present or not present['ok']:
        return []
    rows=db.query('SELECT editor_work_key FROM public.corpus_editor_work_poem_candidate WHERE poem_id=%s', (poem_id,))
    result=[]
    for row in rows:
        key=row['editor_work_key']
        for item in work_candidates(key):
            if item['poemId']==poem_id:
                work=_load('works',key)
                if work:
                    result.append({'workKey':key,'title':work.get('titleZh',key),'status':'candidate',
                                   'differences':item['differences'],'stops':item['stops']})
    return result
