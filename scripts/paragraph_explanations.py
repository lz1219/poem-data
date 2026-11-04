"""Offline candidate validation against a fixed paragraph inventory; never calls AI or writes a DB."""
import argparse
import hashlib
import json
from pathlib import Path


def require(value, message):
    if not value:
        raise ValueError(message)


def validate(bundle, inventory):
    require(bundle['schemaVersion'] == 1, 'Unknown candidate format')
    require(bundle['unitId'] == inventory['unitId'] and bundle['sourceRevision'] == inventory['sourceRevision'] and
            bundle['unitSha256'] == inventory['unitSha256'], 'Source unit or revision mismatch')
    by_id = {p['paragraphId']:p for p in inventory['paragraphs']}
    generation = bundle['generation']
    require(generation.get('method') == 'ai-batch' and generation.get('model') and
            generation.get('generatedAt') and generation.get('promptVersion') and
            'modelSnapshot' in generation and generation.get('snapshotAvailability'), 'Missing generation record')
    seen = set()
    for row in bundle['items']:
        require(set(row) == {'id','revision','paragraphId','sourceSha256','sourceText','translation',
                             'reviewStatus','aiLabel','basis','notes'}, 'Unsupported candidate fields')
        identity = row['paragraphId']
        require(row['id'] == f'paragraph-{identity}-explanation' and type(row['revision']) is int and
                row['revision'] > 0, 'Missing stable explanation identity or revision')
        require(identity not in seen, 'Duplicate paragraph')
        seen.add(identity)
        source = by_id.get(identity)
        require(source and source['kind'] == 'paragraph', 'Not a source paragraph')
        require(row['sourceSha256'] == source['sourceSha256'] and
                hashlib.sha256(row['sourceText'].encode()).hexdigest() == source['sourceSha256'], 'Paragraph source hash mismatch')
        require(row['reviewStatus'] == 'unreviewed' and row['aiLabel'] == 'AI生成·未经人工审校', 'Missing AI status')
        require(row.get('translation', '').strip() and 'meaning' not in row, 'Missing independent full translation')
        require(row.get('basis') == {'kind':'source-text','paragraphId':identity}, 'Missing source-text basis')
        for note in row['notes']:
            start, end = note['start'], note['end']
            require(type(start) is int and type(end) is int and 0 <= start < end <= len(row['sourceText']), 'Annotation outside original text')
            require(row['sourceText'][start:end] == note['quote'], 'Annotation quote mismatch')
            require(note.get('explanation') and note.get('basis') == {'kind':'source-text','paragraphId':identity} and
                    note.get('attribution') == '本站AI拟释', 'Missing annotation basis or attribution')
        require('commentary' not in row, 'AI content cannot impersonate ancient commentary')
    return {'scope':'candidate structure and exact source anchors; not semantic or human review',
            'paragraphs':len(seen),'sourceParagraphs':inventory['counts']['paragraph'],
            'pendingParagraphs':inventory['counts']['paragraph']-len(seen),
            'notes':sum(len(r['notes']) for r in bundle['items']), 'humanReviewed':0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates',type=Path,required=True)
    parser.add_argument('--inventory',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    result = validate(json.loads(args.candidates.read_text('utf-8')),json.loads(args.inventory.read_text('utf-8')))
    if args.output:
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(result,ensure_ascii=False))
