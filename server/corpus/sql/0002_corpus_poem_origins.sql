-- Provenance for poems in the existing corpus; no second text store.
CREATE TABLE IF NOT EXISTS public.corpus_poem_origin (
    poem_id integer PRIMARY KEY REFERENCES public.corpus_poem(id) ON DELETE RESTRICT,
    batch_id text NOT NULL REFERENCES public.corpus_ingest_batch(batch_id),
    edition_id integer NOT NULL REFERENCES public.edition(id),
    ordinal integer NOT NULL CHECK (ordinal > 0),
    metadata jsonb NOT NULL,
    UNIQUE(batch_id, ordinal)
);
