from config import FIELDS
from repository import BusinessError, now
from typing import Any


def pending_groups(db, product_id):
    rows = db.execute("SELECT * FROM observations WHERE product_id=? AND state='pending' ORDER BY field,context,id", (product_id,)).fetchall()
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["field"], row["context"]), []).append(dict(row))
    return groups


def detect_issues(repo, product_id):
    with repo.connect() as db:
        groups = pending_groups(db, product_id)
        current = {(r["field"], r["context"]): dict(r) for r in db.execute(
            "SELECT * FROM fact_revisions WHERE product_id=? AND state='current'", (product_id,))}
        issues: list[dict[str, Any]] = []
        for field in ("product_name", "net_weight_g"):
            if (field, "general") not in current:
                issues.append({"issue_id": f"{product_id}:{field}:general:missing", "type": "missing",
                               "field": field, "context": "general", "message": "必需信息尚未确认"})
        for (field, context), observations in groups.items():
            values = {r["normalized"] for r in observations}
            if (field, context) in current:
                values.add(current[(field, context)]["value"])
            conflict = len(values) > 1
            issues.append({"issue_id": f"{product_id}:{field}:{context}", "type": "conflict" if conflict else "pending",
                           "field": field, "context": context, "message": "存在不同值，请人工取舍" if conflict else "候选信息待确认",
                           "observations": observations, "current": current.get((field, context))})
        return issues


def exclude_observation(repo, observation_id, operator, reason):
    if not operator.strip() or not reason.strip():
        raise BusinessError("排除候选必须填写操作人和原因。")
    with repo.connect(write=True) as db:
        row = db.execute("SELECT * FROM observations WHERE id=?", (observation_id,)).fetchone()
        if not row or row["state"] != "pending":
            raise BusinessError("候选已处理，请刷新。", "concurrent_change")
        db.execute("UPDATE observations SET state='excluded',operator=?,reason=?,handled_at=? WHERE id=?",
                   (operator.strip(), reason.strip(), now(), observation_id))
        db.execute("INSERT INTO observation_actions(observation_id,action,operator,reason,created_at) VALUES(?,?,?,?,?)",
                   (observation_id, "exclude", operator.strip(), reason.strip(), now()))


def reassign_observation(repo, observation_id, new_product_id, operator, reason):
    if not operator.strip() or not reason.strip():
        raise BusinessError("重新分配必须填写操作人和原因。")
    with repo.connect(write=True) as db:
        row = db.execute("SELECT * FROM observations WHERE id=?", (observation_id,)).fetchone()
        if not row or row["state"] != "pending":
            raise BusinessError("只能重新分配待确认候选。")
        if not db.execute("SELECT 1 FROM product_versions WHERE id=?", (new_product_id,)).fetchone():
            raise BusinessError("目标产品不存在。")
        db.execute("UPDATE observations SET product_id=?,fingerprint=NULL WHERE id=?", (new_product_id, observation_id))
        db.execute("""INSERT INTO observation_actions(observation_id,action,operator,reason,old_product_id,new_product_id,created_at)
                   VALUES(?,?,?,?,?,?,?)""", (observation_id, "reassign", operator.strip(), reason.strip(), row["product_id"], new_product_id, now()))
