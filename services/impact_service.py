def list_impacts(repo, product_id=None, event_id=None):
    clauses, params = ["e.old_fact_id IS NOT NULL"], []
    if product_id is not None:
        clauses.append("e.product_id=?")
        params.append(product_id)
    if event_id is not None:
        clauses.append("e.id=?")
        params.append(event_id)
    rows = repo.all("""SELECT c.*,e.id AS event_id,e.field AS changed_field,e.context AS changed_context,
        e.old_fact_id,e.new_fact_id,e.reason AS change_reason,e.created_at AS changed_at,
        old.value AS old_value,new.value AS new_value FROM change_events e
        JOIN content_dependencies d ON d.fact_revision_id=e.old_fact_id
        JOIN content_revisions c ON c.id=d.content_revision_id
        JOIN fact_revisions old ON old.id=e.old_fact_id
        LEFT JOIN fact_revisions new ON new.id=e.new_fact_id WHERE """ + " AND ".join(clauses) +
        " ORDER BY e.id DESC,c.id DESC", params)
    result = {}
    for row in rows:
        item = result.setdefault(row["id"], {**row, "triggers": []})
        item["triggers"].append({k: row[k] for k in ("event_id", "changed_field", "changed_context", "old_value", "new_value", "change_reason")})
    return list(result.values())


def impact_worklist(repo, product_id):
    """One task per logical content, resolved against its latest real basis."""
    import json
    from services.fact_service import current_basis
    from services.text_check_service import text_issues
    groups = {}
    for old in list_impacts(repo, product_id):
        groups.setdefault(old['logical_id'], []).append(old)
    result = []
    with repo.connect() as db:
        for logical_id, history in groups.items():
            row = dict(db.execute('SELECT * FROM content_revisions WHERE logical_id=? ORDER BY revision DESC LIMIT 1', (logical_id,)).fetchone())
            basis = current_basis(db, json.loads(row['snapshot_json']))
            valid = not basis['missing'] and basis['snapshot_hash'] == row['snapshot_hash']
            valid = valid and not text_issues(row['title'], row['body'], basis['snapshot'])
            if valid and row['state'] == 'ready':
                approved = db.execute("SELECT 1 FROM review_records WHERE content_id=? AND decision='approved' AND basis_hash=?",
                                      (row['id'], row['snapshot_hash'])).fetchone()
                status = 'resolved' if approved else 'needs_review'
            elif valid and row['state'] in ('draft', 'review'):
                status = 'needs_review'
            else:
                status = 'needs_update'
            triggers = {t['event_id']: t for old in history for t in old['triggers']}
            result.append({**row, 'resolution': status, 'triggers': list(triggers.values()), 'history': history})
    return result
