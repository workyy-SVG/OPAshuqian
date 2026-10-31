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
