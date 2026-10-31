PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS product_versions (
 id INTEGER PRIMARY KEY, brand_code TEXT NOT NULL, sku TEXT NOT NULL,
 version TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
 UNIQUE(brand_code, sku, version)
);
CREATE TABLE IF NOT EXISTS sources (
 id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL UNIQUE, original_name TEXT NOT NULL,
 stored_path TEXT NOT NULL, encoding TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
 id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources(id),
 row_no INTEGER NOT NULL, product_id INTEGER REFERENCES product_versions(id),
 field TEXT NOT NULL, context TEXT NOT NULL, raw TEXT NOT NULL,
 normalized TEXT, state TEXT NOT NULL CHECK(state IN ('pending','adopted','excluded','duplicate','error')),
 source_label TEXT NOT NULL, source_locator TEXT NOT NULL, effective_from TEXT NOT NULL,
 fingerprint TEXT, error TEXT, reason TEXT, operator TEXT, handled_at TEXT,
 UNIQUE(source_id,row_no)
);
CREATE INDEX IF NOT EXISTS ix_observations_group ON observations(product_id,field,context,state);
CREATE INDEX IF NOT EXISTS ix_observations_fingerprint ON observations(fingerprint);
CREATE TABLE IF NOT EXISTS fact_revisions (
 id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES product_versions(id),
 field TEXT NOT NULL, context TEXT NOT NULL, value TEXT NOT NULL,
 source_observation_id INTEGER NOT NULL REFERENCES observations(id),
 state TEXT NOT NULL CHECK(state IN ('current','superseded','withdrawn')),
 supersedes_id INTEGER REFERENCES fact_revisions(id), operator TEXT NOT NULL,
 reason TEXT NOT NULL, confirmed_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fact_current ON fact_revisions(product_id,field,context) WHERE state='current';
CREATE TABLE IF NOT EXISTS generation_jobs (
 id INTEGER PRIMARY KEY, request_key TEXT NOT NULL UNIQUE,
 product_id INTEGER NOT NULL REFERENCES product_versions(id), snapshot_hash TEXT NOT NULL,
 snapshot_json TEXT NOT NULL, content_type TEXT NOT NULL, context TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('running','succeeded','failed')),
 attempts INTEGER NOT NULL DEFAULT 0, model TEXT NOT NULL, prompt_version TEXT NOT NULL,
 error_code TEXT, usage_json TEXT, created_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS content_revisions (
 id INTEGER PRIMARY KEY, logical_id TEXT NOT NULL, revision INTEGER NOT NULL,
 product_id INTEGER NOT NULL REFERENCES product_versions(id), content_type TEXT NOT NULL,
 context TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
 snapshot_json TEXT NOT NULL, snapshot_hash TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('draft','review','ready','stale','archived')),
 mode TEXT NOT NULL, job_id INTEGER REFERENCES generation_jobs(id),
 reason TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(logical_id,revision)
);
CREATE TABLE IF NOT EXISTS content_dependencies (
 content_revision_id INTEGER NOT NULL REFERENCES content_revisions(id),
 fact_revision_id INTEGER NOT NULL REFERENCES fact_revisions(id),
 PRIMARY KEY(content_revision_id,fact_revision_id)
);
CREATE INDEX IF NOT EXISTS ix_dependencies_fact ON content_dependencies(fact_revision_id);
CREATE TABLE IF NOT EXISTS change_events (
 id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES product_versions(id),
 field TEXT NOT NULL, context TEXT NOT NULL, old_fact_id INTEGER REFERENCES fact_revisions(id),
 new_fact_id INTEGER REFERENCES fact_revisions(id), reason TEXT NOT NULL,
 operator TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_records (
 id INTEGER PRIMARY KEY, content_id INTEGER NOT NULL REFERENCES content_revisions(id),
 operator TEXT NOT NULL, decision TEXT NOT NULL, basis_hash TEXT NOT NULL,
 reason TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS export_records (
 id INTEGER PRIMARY KEY, content_id INTEGER NOT NULL REFERENCES content_revisions(id),
 operator TEXT NOT NULL, basis_hash TEXT NOT NULL, body_hash TEXT NOT NULL,
 stored_path TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observation_actions (
 id INTEGER PRIMARY KEY, observation_id INTEGER NOT NULL REFERENCES observations(id),
 action TEXT NOT NULL, operator TEXT NOT NULL, reason TEXT NOT NULL,
 old_product_id INTEGER REFERENCES product_versions(id), new_product_id INTEGER REFERENCES product_versions(id),
 created_at TEXT NOT NULL
);
