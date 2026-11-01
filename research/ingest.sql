-- 原件落库与整理工作区。与公开阅读的 public 表隔离，不自动发布或改写原文。
CREATE SCHEMA IF NOT EXISTS research_ingest;

CREATE TABLE IF NOT EXISTS research_ingest.blob (
    sha256 text PRIMARY KEY CHECK (sha256 ~ '^[a-f0-9]{64}$'),
    payload bytea NOT NULL,
    byte_count bigint NOT NULL CHECK (byte_count >= 0),
    CHECK (octet_length(payload) = byte_count)
);
CREATE TABLE IF NOT EXISTS research_ingest.batch (
    id text PRIMARY KEY,
    manifest jsonb NOT NULL,
    status text NOT NULL DEFAULT 'landed' CHECK (status IN ('landed', 'organized', 'verified')),
    public_before jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    organized_at timestamptz,
    verified_at timestamptz
);
CREATE TABLE IF NOT EXISTS research_ingest.source_snapshot (
    id text PRIMARY KEY,
    repository text NOT NULL,
    commit_sha text NOT NULL CHECK (commit_sha ~ '^[a-f0-9]{40}$'),
    archive_sha256 text NOT NULL REFERENCES research_ingest.blob(sha256),
    metadata jsonb NOT NULL
);
-- 旧版只按包身份唯一，无法并存修订后的采集元数据；保留旧行，身份由完整内容哈希确定。
ALTER TABLE research_ingest.source_snapshot
    DROP CONSTRAINT IF EXISTS source_snapshot_repository_commit_sha_archive_sha256_key;
ALTER TABLE research_ingest.source_snapshot ADD COLUMN IF NOT EXISTS provider text NOT NULL DEFAULT 'github';
ALTER TABLE research_ingest.source_snapshot ADD COLUMN IF NOT EXISTS revision_id text;
ALTER TABLE research_ingest.source_snapshot ALTER COLUMN commit_sha DROP NOT NULL;
ALTER TABLE research_ingest.source_snapshot DROP CONSTRAINT IF EXISTS source_snapshot_provider_identity_check;
ALTER TABLE research_ingest.source_snapshot ADD CONSTRAINT source_snapshot_provider_identity_check CHECK (
    (provider='github' AND commit_sha IS NOT NULL AND revision_id IS NULL)
    OR (provider='wikisource' AND commit_sha IS NULL AND revision_id IS NOT NULL AND revision_id ~ '^[1-9][0-9]*$')
);
CREATE TABLE IF NOT EXISTS research_ingest.batch_source (
    batch_id text REFERENCES research_ingest.batch(id),
    snapshot_id text REFERENCES research_ingest.source_snapshot(id),
    PRIMARY KEY (batch_id, snapshot_id)
);
CREATE TABLE IF NOT EXISTS research_ingest.file_entry (
    snapshot_id text REFERENCES research_ingest.source_snapshot(id),
    path text NOT NULL,
    role text NOT NULL CHECK (role IN ('text', 'metadata', 'other')),
    blob_sha256 text NOT NULL REFERENCES research_ingest.blob(sha256),
    PRIMARY KEY (snapshot_id, path)
);
ALTER TABLE research_ingest.file_entry DROP CONSTRAINT IF EXISTS file_entry_role_check;
ALTER TABLE research_ingest.file_entry ADD CONSTRAINT file_entry_role_check CHECK (role IN ('text','metadata','other','wikitext'));
CREATE TABLE IF NOT EXISTS research_ingest.batch_asset (
    batch_id text REFERENCES research_ingest.batch(id),
    path text NOT NULL,
    role text NOT NULL,
    blob_sha256 text NOT NULL REFERENCES research_ingest.blob(sha256),
    PRIMARY KEY (batch_id, path)
);
CREATE TABLE IF NOT EXISTS research_ingest.record_snapshot (
    id text PRIMARY KEY,
    kind text NOT NULL,
    record_key text NOT NULL,
    revision integer NOT NULL DEFAULT 0,
    payload jsonb NOT NULL,
    source_path text NOT NULL,
    source_sha256 text NOT NULL REFERENCES research_ingest.blob(sha256)
);
CREATE TABLE IF NOT EXISTS research_ingest.batch_record (
    batch_id text REFERENCES research_ingest.batch(id),
    record_id text REFERENCES research_ingest.record_snapshot(id),
    PRIMARY KEY (batch_id, record_id)
);
CREATE TABLE IF NOT EXISTS research_ingest.edition (
    id text PRIMARY KEY,
    snapshot_id text NOT NULL REFERENCES research_ingest.source_snapshot(id),
    base_code text NOT NULL,
    title text NOT NULL,
    metadata jsonb NOT NULL,
    review_status text NOT NULL DEFAULT 'pending'
);
ALTER TABLE research_ingest.edition DROP CONSTRAINT IF EXISTS edition_snapshot_id_base_code_key;
CREATE TABLE IF NOT EXISTS research_ingest.unit (
    id text PRIMARY KEY,
    snapshot_id text NOT NULL,
    path text NOT NULL,
    edition_id text NOT NULL REFERENCES research_ingest.edition(id),
    title text NOT NULL,
    juan text,
    kind text NOT NULL CHECK (kind IN ('front_matter', 'body', 'back_matter', 'unclassified')),
    metadata jsonb NOT NULL,
    FOREIGN KEY (snapshot_id, path) REFERENCES research_ingest.file_entry(snapshot_id, path)
);
ALTER TABLE research_ingest.unit DROP CONSTRAINT IF EXISTS unit_snapshot_id_path_key;
CREATE TABLE IF NOT EXISTS research_ingest.page (
    unit_id text REFERENCES research_ingest.unit(id),
    seq integer NOT NULL CHECK (seq >= 0),
    locator text,
    start_byte bigint NOT NULL CHECK (start_byte >= 0),
    end_byte bigint NOT NULL CHECK (end_byte >= start_byte),
    text text NOT NULL,
    sha256 text NOT NULL,
    PRIMARY KEY (unit_id, seq)
);
CREATE TABLE IF NOT EXISTS research_ingest.record_link (
    batch_id text REFERENCES research_ingest.batch(id),
    from_id text REFERENCES research_ingest.record_snapshot(id),
    to_id text REFERENCES research_ingest.record_snapshot(id),
    relation text NOT NULL,
    PRIMARY KEY (batch_id, from_id, to_id, relation)
);
CREATE TABLE IF NOT EXISTS research_ingest.quote_match (
    batch_id text REFERENCES research_ingest.batch(id),
    record_id text REFERENCES research_ingest.record_snapshot(id),
    evidence_index integer NOT NULL,
    unit_id text REFERENCES research_ingest.unit(id),
    start_byte bigint NOT NULL,
    end_byte bigint NOT NULL,
    quote_sha256 text NOT NULL,
    PRIMARY KEY (batch_id, record_id, evidence_index, unit_id)
);
CREATE TABLE IF NOT EXISTS research_ingest.issue (
    id text PRIMARY KEY,
    batch_id text REFERENCES research_ingest.batch(id),
    subject text NOT NULL,
    code text NOT NULL,
    detail jsonb NOT NULL
);
COMMENT ON SCHEMA research_ingest IS '研究原件暂存与整理；不属于公开正文，不代表学术已核。';
COMMENT ON TABLE research_ingest.blob IS '原始字节按SHA-256保存；保留ZIP和每个原始文件，禁止覆盖。';
COMMENT ON TABLE research_ingest.page IS '原文件字节范围及原页标记，不把20字硬换行误当段落。';
COMMENT ON TABLE research_ingest.record_snapshot IS '策展/研究JSON原态；未经核验的旧解释不升级为事实。';
