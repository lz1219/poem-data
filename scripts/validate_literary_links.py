"""Validate candidate links against published JSON and a fresh read-only corpus snapshot."""
import argparse
import hashlib
import json
from pathlib import Path
import unicodedata

ROOT = Path(__file__).resolve().parent.parent


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def text_only(value):
    return ''.join(ch for ch in value if not ch.isspace() and not unicodedata.category(ch).startswith(('P', 'Z')))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_local(link, person, work, journey=None):
    require(link.get('schemaVersion') == 1 and link.get('status') == 'candidate', 'Only candidate links are supported')
    lp, lw = link['person'], link['work']
    lj = link.get('journey')
    entries = [lp, lw] + ([lj] if lj else [])
    for entry in entries:
        require(isinstance(entry.get('basis'), str) and entry['basis'].strip(), 'Missing relationship basis')
    require(person['key'] == lp['editorKey'] and digest(person) == lp['editorSha256'], 'Person snapshot changed')
    require(work['key'] == lw['editorKey'] and work['authorKey'] == person['key'] and
            digest(work) == lw['editorSha256'], 'Work or author snapshot changed')
    require(isinstance(lw.get('differences'), str) and lw['differences'].strip(), 'Text differences must be stated')
    selected = text_only(''.join(work['text']['paragraphsSimplified']))
    require(isinstance(lw.get('matchingText'), list) and lw['matchingText'], 'Missing work evidence text')
    for phrase in lw['matchingText']:
        require(isinstance(phrase,str) and phrase and text_only(phrase) in selected, 'Work evidence does not match editor text')
    if lj:
        require(journey and journey['key'] == lj['key'] and
                lj['relation'] == 'stop-quotes-work', 'Journey relation changed')
        stops = [s for s in journey['stops'] if s['seq'] == lj['stopSeq']]
        require(len(stops) == 1 and digest(stops[0]) == lj['stopSha256'], 'Stop snapshot changed')
        require(isinstance(lj.get('matchingText'), list) and lj['matchingText'], 'Missing stop evidence text')
        for phrase in lj['matchingText']:
            require(isinstance(phrase,str) and phrase and text_only(phrase) in text_only(stops[0]['quote']),
                    'Stop evidence does not match editor quote')


def validate(link, person, work, journey, corpus_person, poem):
    validate_local(link,person,work,journey)
    lp,lw=link['person'],link['work']
    lj=link.get('journey')
    require(person.get('externalIds',{}).get('cbdb'), 'Missing person identity basis')
    require(corpus_person['id'] == lp['corpusPersonId'] and corpus_person['key'] == person['key'] and
            corpus_person['zh'] == person['zh'] and str(corpus_person['cbdb_id']) == str(person['externalIds']['cbdb']),
            'Person identity evidence changed')
    require(poem['id'] == lw['corpusPoemId'] and hashlib.sha256(poem['body'].encode()).hexdigest() == lw['corpusBodySha256'],
            'Poem text changed')
    require(poem['edition_id'] == lw['corpusEditionId'] and poem['batch_id'] == lw['corpusBatchId'], 'Poem source changed')
    locations = (poem.get('metadata') or {}).get('locations') or []
    require(any(x.get('url') == lw['sourceUrl'] and x.get('jsonPointer') == lw['sourcePointer'] for x in locations),
            'Poem source location changed')
    corpus = text_only(poem['body'])
    for phrase in lw['matchingText']:
        require(text_only(phrase) in corpus, 'Work evidence does not match corpus text')
    if lj:
        for phrase in lj['matchingText']:
            require(text_only(phrase) in corpus,'Stop quotation does not match the witness')
    res = {'status': 'candidate', 'personKey': person['key'], 'workKey': work['key'],
           'poemId': poem['id'],
           'scope': 'structural and source snapshot checks only; not human review or proof of place/date'}
    if lj and journey:
        res.update({'journeyKey': journey['key'], 'stopSeq': lj['stopSeq']})
    return res


def main():
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--link', type=Path)
    source.add_argument('--link-dir', type=Path, help='Check every JSON candidate in a directory (offline only)')
    parser.add_argument('--data-root', type=Path, default=ROOT / 'data')
    parser.add_argument('--offline', action='store_true', help='Check published JSON only, without claiming corpus validation')
    args = parser.parse_args()
    load = lambda p: json.loads(p.read_text('utf-8'))
    require(not args.link_dir or args.offline, 'Directory mode is offline only')
    paths=sorted(args.link_dir.glob('*.json')) if args.link_dir else [args.link]
    require(bool(paths), 'No link records')
    def load_editor(path):
        link=load(path)
        keys = [link['person']['editorKey'], link['work']['editorKey']]
        if link.get('journey'):
            keys.append(link['journey']['key'])
        for key in keys:
            require(isinstance(key,str) and key and key not in ('.','..') and '/' not in key and '\\' not in key,
                    'Invalid editor key')
        j_data = load(args.data_root/'journeys'/(link['journey']['key']+'.json')) if link.get('journey') else None
        return (link,load(args.data_root/'persons'/(link['person']['editorKey']+'.json')),
                load(args.data_root/'works'/(link['work']['editorKey']+'.json')),
                j_data)
    if args.offline:
        for path in paths:
            validate_local(*load_editor(path))
        print(json.dumps({'status':'candidate','count':len(paths),'scope':'published JSON only; corpus not checked'},ensure_ascii=False))
        return
    import psycopg
    from psycopg.rows import dict_row
    link,person,work,journey=load_editor(paths[0])
    with psycopg.connect(os.environ['CORPUS_DSN'], autocommit=True, row_factory=dict_row,
                         options='-c default_transaction_read_only=on -c statement_timeout=10000') as conn:
        corpus_person = conn.execute('SELECT id,key,zh,cbdb_id FROM person WHERE id=%s',
                                     (link['person']['corpusPersonId'],)).fetchone()
        poem = conn.execute('''SELECT p.id,p.body,o.edition_id,o.batch_id,o.metadata
            FROM corpus_poem p JOIN corpus_poem_origin o ON o.poem_id=p.id WHERE p.id=%s''',
                            (link['work']['corpusPoemId'],)).fetchone()
    require(corpus_person is not None and poem is not None, 'Corpus target or provenance is missing')
    print(json.dumps(validate(link, person, work, journey, corpus_person, poem), ensure_ascii=False))


if __name__ == '__main__':
    main()
