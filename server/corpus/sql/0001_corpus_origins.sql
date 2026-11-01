-- Additive provenance for the existing corpus tables, not Django's editor DB.
CREATE TABLE IF NOT EXISTS public.corpus_ingest_batch (
    batch_id text PRIMARY KEY,
    book_id integer NOT NULL REFERENCES public.book(id),
    edition_id integer REFERENCES public.edition(id),
    state text NOT NULL CHECK (state IN ('applied', 'rolled-back')),
    manifest jsonb NOT NULL,
    result jsonb NOT NULL,
    events jsonb NOT NULL DEFAULT '[]',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.corpus_unit_origin (
    unit_id integer PRIMARY KEY REFERENCES public.text_unit(id) ON DELETE RESTRICT,
    batch_id text NOT NULL REFERENCES public.corpus_ingest_batch(batch_id),
    edition_id integer NOT NULL REFERENCES public.edition(id),
    ordinal integer NOT NULL CHECK (ordinal > 0),
    metadata jsonb NOT NULL,
    UNIQUE(batch_id, ordinal)
);
CREATE TABLE IF NOT EXISTS public.corpus_paragraph_origin (
    paragraph_id integer PRIMARY KEY REFERENCES public.paragraph(id) ON DELETE RESTRICT,
    batch_id text NOT NULL REFERENCES public.corpus_ingest_batch(batch_id),
    metadata jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS corpus_paragraph_origin_batch_idx
    ON public.corpus_paragraph_origin(batch_id);
