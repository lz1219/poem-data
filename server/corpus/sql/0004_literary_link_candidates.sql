-- Rebuildable candidate mappings; editor keys refer to the separately published JSON.
-- Candidate rows are not confirmed historical facts or default map routes.
CREATE TABLE IF NOT EXISTS public.corpus_editor_person_candidate (
    editor_person_key text NOT NULL,
    person_id integer NOT NULL REFERENCES public.person(id) ON DELETE RESTRICT,
    editor_sha256 text NOT NULL CHECK (editor_sha256 ~ '^[0-9a-f]{64}$'),
    metadata jsonb NOT NULL,
    PRIMARY KEY (editor_person_key, person_id)
);
CREATE TABLE IF NOT EXISTS public.corpus_editor_work_poem_candidate (
    editor_work_key text NOT NULL,
    poem_id integer NOT NULL REFERENCES public.corpus_poem(id) ON DELETE RESTRICT,
    editor_sha256 text NOT NULL CHECK (editor_sha256 ~ '^[0-9a-f]{64}$'),
    poem_sha256 text NOT NULL CHECK (poem_sha256 ~ '^[0-9a-f]{64}$'),
    metadata jsonb NOT NULL,
    PRIMARY KEY (editor_work_key, poem_id)
);
CREATE TABLE IF NOT EXISTS public.corpus_editor_stop_work_candidate (
    journey_key text NOT NULL,
    stop_seq integer NOT NULL CHECK (stop_seq > 0),
    editor_work_key text NOT NULL,
    stop_sha256 text NOT NULL CHECK (stop_sha256 ~ '^[0-9a-f]{64}$'),
    relation text NOT NULL CHECK (relation = 'stop-quotes-work'),
    metadata jsonb NOT NULL,
    PRIMARY KEY (journey_key, stop_seq, editor_work_key, relation)
);
