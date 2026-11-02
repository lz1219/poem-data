"""Optional corpus provenance; old deployments without the additive tables still work."""
from . import db


def available():
    row = db.one("""SELECT to_regclass('public.corpus_unit_origin') IS NOT NULL
        AND to_regclass('public.corpus_paragraph_origin') IS NOT NULL
        AND to_regclass('public.corpus_ingest_batch') IS NOT NULL AS ok""")
    return bool(row and row['ok'])


def attach_book(book, units):
    if not available():
        return
    rows = db.query("""SELECT b.batch_id,e.id AS edition_id,e.name,b.manifest - 'unitDigests' AS provenance
        FROM public.corpus_ingest_batch b JOIN public.edition e ON e.id=b.edition_id
        WHERE b.book_id=%s AND b.state='applied' ORDER BY e.id,b.created_at,b.batch_id""", (book['id'],))
    book['corpusBatches'] = rows
    editions = {}
    for row in rows:
        if row['edition_id'] not in editions:
            editions[row['edition_id']] = {**row, 'batches': []}
        editions[row['edition_id']]['batches'].append(row)
    book['corpusEditions'] = list(editions.values())
    origins = db.query("""SELECT o.unit_id,o.edition_id,o.ordinal,o.metadata
        FROM public.corpus_unit_origin o JOIN public.text_unit t ON t.id=o.unit_id
        WHERE t.book_id=%s""", (book['id'],))
    by_id = {row['unit_id']: row for row in origins}
    for unit in units:
        if unit['id'] in by_id:
            unit['origin'] = by_id[unit['id']]
    # Appended front matter and earlier-numbered volumes keep source order,
    # rather than acquisition/sequence-ID order. Leave legacy mixed data alone.
    if units and all(isinstance(u.get('origin', {}).get('metadata', {}).get('sourceOrder'), int) for u in units):
        units.sort(key=lambda u: (u['origin']['edition_id'], u['origin']['metadata']['sourceOrder'], u['id']))
    elif units and all(u.get('origin', {}).get('metadata', {}).get('sourcePath') and
                     isinstance(u['origin']['metadata'].get('sourceByteStart'), int) for u in units):
        units.sort(key=lambda u: (u['origin']['edition_id'], u['origin']['metadata']['sourcePath'],
                                  u['origin']['metadata']['sourceByteStart'], u['id']))


def attach_unit(unit, paragraphs):
    if not available():
        return
    row = db.one("""SELECT o.batch_id,o.edition_id,o.ordinal,o.metadata,
        b.manifest - 'unitDigests' AS provenance
        FROM public.corpus_unit_origin o
        JOIN public.corpus_ingest_batch b ON b.batch_id=o.batch_id
        WHERE o.unit_id=%s AND b.state='applied'""", (unit['id'],))
    if not row:
        return
    unit['origin'] = row
    by_id = {r['paragraph_id']: r['metadata'] for r in db.query("""SELECT o.paragraph_id,o.metadata
        FROM public.corpus_paragraph_origin o JOIN public.paragraph p ON p.id=o.paragraph_id
        WHERE p.unit_id=%s""", (unit['id'],))}
    for paragraph in paragraphs:
        paragraph['origin'] = by_id.get(paragraph['id'])
