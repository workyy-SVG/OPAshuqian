import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from config import CONTENT_TYPES, FIELDS
from repository import BusinessError, now
from services.quality_service import pending_groups


def canonical(snapshot):
    return json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def snapshot_hash(snapshot):
    return hashlib.sha256(canonical(snapshot).encode("utf-8")).hexdigest()


def _snapshot(db, product_id, context="retail", content_type="product_intro", include_price=True, selected_fields=None):
    if content_type not in CONTENT_TYPES:
        raise BusinessError("不支持的内容类型。")
    if not context.strip() or context == "general":
        raise BusinessError("请选择明确的价格渠道。")
    product = db.execute("SELECT * FROM product_versions WHERE id=?", (product_id,)).fetchone()
    if not product:
        raise BusinessError("产品不存在。")
    fields = set(selected_fields if selected_fields is not None else FIELDS)
    fields.update(("product_name", "net_weight_g"))
    if include_price:
        fields.add("price_cent")
    else:
        fields.discard("price_cent")
    if fields - FIELDS.keys():
        raise BusinessError("快照包含未知字段。")
    current = {(r["field"], r["context"]): r for r in db.execute(
        "SELECT * FROM fact_revisions WHERE product_id=? AND state='current'", (product_id,))}
    pending = pending_groups(db, product_id)
    facts, missing, conflicts = [], [], []
    required = {"product_name", "net_weight_g"} | ({"price_cent"} if include_price else set())
    for field in sorted(fields):
        scope = context if field == "price_cent" else "general"
        fact = current.get((field, scope))
        values = {r["normalized"] for r in pending.get((field, scope), [])}
        if fact:
            values.add(fact["value"])
        if len(values) > 1:
            conflicts.append(field)
            if field in required or selected_fields is not None:
                missing.append(field)
            continue
        if not fact:
            if field in required or selected_fields is not None:
                missing.append(field)
            continue
        facts.append({"field": field, "context": scope, "value": fact["value"], "fact_revision_id": fact["id"]})
    snapshot = {"product_id": product_id, "brand_code": product["brand_code"], "sku": product["sku"],
                "product_version": product["version"], "context": context, "content_type": content_type,
                "include_price": include_price, "selection": sorted(f["field"] for f in facts), "facts": facts}
    return {"snapshot": snapshot, "snapshot_hash": snapshot_hash(snapshot),
            "missing": sorted(set(missing)), "conflicts": sorted(set(conflicts))}


def build_snapshot(repo, product_id, context="retail", content_type="product_intro", include_price=True, selected_fields=None):
    with repo.connect() as db:
        # A read transaction prevents mixing facts from multiple committed revisions.
        db.execute("BEGIN")
        try:
            return _snapshot(db, product_id, context, content_type, include_price, selected_fields)
        finally:
            db.execute("ROLLBACK")


def current_basis(db, snapshot):
    return _snapshot(db, snapshot["product_id"], snapshot["context"], snapshot["content_type"],
                     snapshot["include_price"], snapshot["selection"])


def _check_operator(operator, reason):
    if not operator.strip() or not reason.strip():
        raise BusinessError("请填写操作人和确认依据或修改原因。")


def _change(db, product_id, field, context, old_id, new_id, operator, reason):
    db.execute("""INSERT INTO change_events(product_id,field,context,old_fact_id,new_fact_id,operator,reason,created_at)
               VALUES(?,?,?,?,?,?,?,?)""", (product_id, field, context, old_id, new_id, operator, reason, now()))
    if old_id:
        db.execute("""UPDATE content_revisions SET state='stale' WHERE id IN
                   (SELECT content_revision_id FROM content_dependencies WHERE fact_revision_id=?)
                   AND state!='archived'""", (old_id,))


def confirm_fact(repo, product_id, observation_id, expected_old_id, operator, reason):
    _check_operator(operator, reason)
    with repo.connect(write=True) as db:
        candidate = db.execute("SELECT * FROM observations WHERE id=? AND product_id=?", (observation_id, product_id)).fetchone()
        if not candidate or candidate["state"] != "pending" or candidate["normalized"] is None:
            raise BusinessError("候选不可确认或已被处理，请刷新。", "concurrent_change")
        if candidate["effective_from"] and candidate["effective_from"] > datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat():
            raise BusinessError("未来资料暂留候选区，适用日期到达后再人工确认。")
        field, context = candidate["field"], candidate["context"]
        current = db.execute("SELECT * FROM fact_revisions WHERE product_id=? AND field=? AND context=? AND state='current'",
                             (product_id, field, context)).fetchone()
        old_id = current["id"] if current else None
        if old_id != expected_old_id:
            raise BusinessError("当前修订已变化，请刷新后重新核对。", "concurrent_change")
        unresolved = db.execute("""SELECT 1 FROM observations WHERE product_id=? AND field=? AND context=?
                                AND state='pending' AND normalized!=? LIMIT 1""",
                                (product_id, field, context, candidate["normalized"])).fetchone()
        if unresolved:
            raise BusinessError("仍有不同值的候选，请先排除误录或补充依据，不能直接确认。", "unresolved_conflict")
        if current and current["value"] == candidate["normalized"]:
            new_id = old_id
        else:
            if old_id:
                db.execute("UPDATE fact_revisions SET state='superseded' WHERE id=?", (old_id,))
            new_id = db.execute("""INSERT INTO fact_revisions(product_id,field,context,value,source_observation_id,
                state,supersedes_id,operator,reason,confirmed_at) VALUES(?,?,?,?,?,'current',?,?,?,?)""",
                (product_id, field, context, candidate["normalized"], observation_id, old_id, operator.strip(), reason.strip(), now())).lastrowid
            _change(db, product_id, field, context, old_id, new_id, operator.strip(), reason.strip())
        equal_rows = db.execute("""SELECT id FROM observations WHERE product_id=? AND field=? AND context=?
            AND state='pending' AND normalized=?""", (product_id, field, context, candidate["normalized"])).fetchall()
        for row in equal_rows:
            db.execute("UPDATE observations SET state='adopted',operator=?,reason=?,handled_at=? WHERE id=?",
                       (operator.strip(), reason.strip(), now(), row[0]))
            db.execute("INSERT INTO observation_actions(observation_id,action,operator,reason,created_at) VALUES(?,?,?,?,?)",
                       (row[0], "confirm", operator.strip(), reason.strip(), now()))
        return new_id


def withdraw_fact(repo, product_id, field, context, expected_old_id, operator, reason):
    _check_operator(operator, reason)
    with repo.connect(write=True) as db:
        row = db.execute("SELECT * FROM fact_revisions WHERE product_id=? AND field=? AND context=? AND state='current'",
                         (product_id, field, context)).fetchone()
        if not row or row["id"] != expected_old_id:
            raise BusinessError("当前修订已变化，请刷新后重试。", "concurrent_change")
        db.execute("UPDATE fact_revisions SET state='withdrawn' WHERE id=?", (row["id"],))
        _change(db, product_id, field, context, row["id"], None, operator.strip(), reason.strip())
