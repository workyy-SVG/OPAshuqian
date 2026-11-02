CREATE INDEX IF NOT EXISTS ix_content_product ON content_revisions(product_id,id DESC);
CREATE INDEX IF NOT EXISTS ix_content_logical_latest ON content_revisions(logical_id,revision DESC);
CREATE INDEX IF NOT EXISTS ix_events_product ON change_events(product_id,id DESC);
CREATE INDEX IF NOT EXISTS ix_jobs_product ON generation_jobs(product_id,id DESC);
