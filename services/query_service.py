"""Read models for views. Critical facts are always read directly from SQLite."""
import json
from typing import Any
from repository import Repository
from services.fact_service import current_basis
from services.date_service import today_iso

Row = dict[str, Any]


def products(repo: Repository) -> list[Row]:
    return repo.products()


def channels(repo: Repository, product_id: int) -> list[str]:
    rows = repo.all("SELECT DISTINCT context FROM observations WHERE product_id=? AND field='price_cent' AND state!='error'", (product_id,))
    return list(dict.fromkeys(['retail', 'wholesale'] + [r['context'] for r in rows if r['context'] != 'general']))


def current_facts(repo: Repository, product_id: int) -> list[Row]:
    return repo.all("""SELECT f.*,o.raw,o.source_label,o.source_locator,o.row_no,o.effective_from
        FROM fact_revisions f JOIN observations o ON o.id=f.source_observation_id
        WHERE f.product_id=? AND f.state='current' ORDER BY f.field,f.context""", (product_id,))


def sources(repo: Repository) -> list[Row]:
    return repo.all("""SELECT s.id,s.original_name,s.sha256,s.created_at,COUNT(o.id) AS total,
        SUM(o.state='error') AS errors FROM sources s LEFT JOIN observations o ON o.source_id=s.id GROUP BY s.id ORDER BY s.id DESC""")


def source_observations(repo: Repository, source_id: int) -> list[Row]:
    return repo.all('SELECT * FROM observations WHERE source_id=? ORDER BY row_no', (source_id,))


def source_record(repo: Repository, source_id: int) -> Row | None:
    return repo.one('SELECT * FROM sources WHERE id=?', (source_id,))


def content_history(repo: Repository, product_id: int, include_history: bool = True) -> list[Row]:
    rows = repo.all('SELECT * FROM content_revisions WHERE product_id=? ORDER BY id DESC', (product_id,))
    if include_history:
        return rows
    seen = set()
    latest = []
    for row in rows:
        if row['logical_id'] not in seen:
            latest.append(row)
            seen.add(row['logical_id'])
    return latest


def generation_jobs(repo: Repository, product_id: int) -> list[Row]:
    return repo.all('SELECT id,request_key,state,attempts,model,prompt_version,error_code,usage_json,created_at,finished_at FROM generation_jobs WHERE product_id=? ORDER BY id DESC', (product_id,))


def content_basis(repo: Repository, row: Row) -> Row:
    with repo.connect() as db:
        db.execute('BEGIN')
        try:
            return current_basis(db, json.loads(row['snapshot_json']))
        finally:
            db.execute('ROLLBACK')


def content_evidence(repo: Repository, content_id: int) -> list[Row]:
    return repo.all('''SELECT f.id,f.field,f.context,f.value,f.state,o.source_label,o.source_locator,o.row_no,o.raw
        FROM content_dependencies d JOIN fact_revisions f ON f.id=d.fact_revision_id
        JOIN observations o ON o.id=f.source_observation_id WHERE d.content_revision_id=?''', (content_id,))


def content_reviews(repo: Repository, content_id: int) -> list[Row]:
    return repo.all('SELECT * FROM review_records WHERE content_id=? ORDER BY id', (content_id,))


def content_exports(repo: Repository, content_id: int) -> list[Row]:
    return repo.all('SELECT id,operator,basis_hash,created_at FROM export_records WHERE content_id=? ORDER BY id', (content_id,))


def observation_actions(repo: Repository, product_id: int) -> list[Row]:
    return repo.all('''SELECT a.* FROM observation_actions a JOIN observations o ON o.id=a.observation_id
        WHERE o.product_id=? OR a.old_product_id=? ORDER BY a.id DESC''', (product_id, product_id))


def fact_history(repo: Repository, product_id: int) -> list[Row]:
    return repo.all('SELECT * FROM fact_revisions WHERE product_id=? ORDER BY id DESC', (product_id,))


def change_history(repo: Repository, product_id: int) -> list[Row]:
    return repo.all('SELECT * FROM change_events WHERE product_id=? ORDER BY id DESC', (product_id,))


def dated_candidates(repo: Repository, product_id: int) -> list[Row]:
    rows = repo.all("SELECT * FROM observations WHERE product_id=? AND state='pending' AND effective_from!='' ORDER BY effective_from,id", (product_id,))
    today = today_iso()
    return [{**r, 'availability': 'future' if r['effective_from'] > today else 'due'} for r in rows]


def dependent_content_count(repo: Repository, fact_id: int) -> int:
    row = repo.one('SELECT COUNT(*) AS total FROM content_dependencies WHERE fact_revision_id=?', (fact_id,))
    return int(row['total']) if row else 0
