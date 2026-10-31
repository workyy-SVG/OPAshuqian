import hashlib
import json
import uuid
from decimal import Decimal
from repository import BusinessError, now
from services.fact_service import _snapshot, canonical, current_basis, snapshot_hash
from services.llm_client import PROMPT_VERSION, ModelError, validate_result


def template_result(snapshot):
    values = {f["field"]: f["value"] for f in snapshot["facts"]}
    name = values["product_name"]
    pieces = [f"{name}，净含量 {values['net_weight_g']} 克。"]
    if "price_cent" in values:
        pieces.append(f"{snapshot['context']} 渠道价格 {Decimal(values['price_cent']) / 100:.2f} 元。")
    for field, label in (("ingredients_text", "配料"), ("usage_text", "使用方法"), ("storage_text", "储存说明")):
        if field in values:
            pieces.append(f"{label}：{values[field]}。")
    if snapshot["content_type"] == "social_post":
        pieces.insert(0, "今天分享一款小铺产品。")
    return {"title": name + ("商品介绍" if snapshot["content_type"] == "product_intro" else "分享"),
            "body": "\n".join(pieces), "used_fact_ids": [f["fact_revision_id"] for f in snapshot["facts"]], "missing_fields": []}


def create_generation(repo, product_id, request_key, context="retail", content_type="product_intro", include_price=True,
                      mode="template", model_name="template", selected_fields=None):
    if mode not in ("template", "deepseek") or not request_key.strip():
        raise BusinessError("生成模式或请求编号无效。")
    with repo.connect(write=True) as db:
        existing = db.execute("SELECT * FROM generation_jobs WHERE request_key=?", (request_key,)).fetchone()
        if existing:
            old_snapshot = json.loads(existing["snapshot_json"])
            expected_model = "template" if mode == "template" else model_name
            if ((existing["product_id"], existing["context"], existing["content_type"]) != (product_id, context, content_type)
                    or old_snapshot["include_price"] != include_price or existing["model"] != expected_model):
                raise BusinessError("请求编号已用于其他生成范围。", "request_key_conflict")
            return {"job": dict(existing), "created": False}
        basis = _snapshot(db, product_id, context, content_type, include_price, selected_fields)
        if basis["missing"]:
            raise BusinessError("请先确认必需资料并处理所选字段的冲突：" + "、".join(basis["missing"]), "incomplete_facts")
        job_id = db.execute("""INSERT INTO generation_jobs(request_key,product_id,snapshot_hash,snapshot_json,content_type,
            context,state,model,prompt_version,created_at) VALUES(?,?,?,?,?,?,'running',?,?,?)""",
            (request_key, product_id, basis["snapshot_hash"], canonical(basis["snapshot"]), content_type, context,
             "template" if mode == "template" else model_name, PROMPT_VERSION, now())).lastrowid
        return {"job": dict(db.execute("SELECT * FROM generation_jobs WHERE id=?", (job_id,)).fetchone()), "created": True}


def _insert_content(db, snapshot, result, state, mode, job_id=None, logical_id=None, reason="生成草稿"):
    logical_id = logical_id or uuid.uuid4().hex
    revision = db.execute("SELECT COALESCE(MAX(revision),0)+1 FROM content_revisions WHERE logical_id=?", (logical_id,)).fetchone()[0]
    content_id = db.execute("""INSERT INTO content_revisions(logical_id,revision,product_id,content_type,context,title,body,
        snapshot_json,snapshot_hash,state,mode,job_id,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (logical_id, revision, snapshot["product_id"], snapshot["content_type"], snapshot["context"], result["title"].strip(),
         result["body"].strip(), canonical(snapshot), snapshot_hash(snapshot), state, mode, job_id, reason, now())).lastrowid
    db.executemany("INSERT INTO content_dependencies(content_revision_id,fact_revision_id) VALUES(?,?)",
                   [(content_id, f["fact_revision_id"]) for f in snapshot["facts"]])
    return content_id


def save_draft(repo, job_id, result, mode, attempts=0, usage=None, logical_id=None):
    with repo.connect(write=True) as db:
        job = db.execute("SELECT * FROM generation_jobs WHERE id=?", (job_id,)).fetchone()
        if not job or job["state"] != "running":
            raise BusinessError("生成任务已结束或不存在，不能重复保存。")
        snapshot = json.loads(job["snapshot_json"])
        validate_result(result, snapshot)
        if logical_id:
            prior = db.execute("SELECT * FROM content_revisions WHERE logical_id=? ORDER BY revision DESC LIMIT 1", (logical_id,)).fetchone()
            if not prior or (prior["product_id"], prior["context"], prior["content_type"]) != (job["product_id"], job["context"], job["content_type"]):
                raise BusinessError("新修订与原内容的产品、渠道或类型不一致。")
        current = current_basis(db, snapshot)
        state = "stale" if current["missing"] or current["snapshot_hash"] != job["snapshot_hash"] else "draft"
        content_id = _insert_content(db, snapshot, result, state, mode, job_id, logical_id)
        db.execute("UPDATE generation_jobs SET state='succeeded',attempts=?,usage_json=?,finished_at=? WHERE id=?",
                   (attempts, json.dumps(usage or {}), now(), job_id))
        return content_id


def generate_content(repo, product_id, request_key, context="retail", content_type="product_intro", include_price=True,
                     mode="template", client=None, selected_fields=None, logical_id=None):
    created = create_generation(repo, product_id, request_key, context, content_type, include_price, mode,
                                client.config.name if client else "template", selected_fields)
    job = created["job"]
    if not created["created"]:
        existing = repo.one("SELECT id FROM content_revisions WHERE job_id=?", (job["id"],))
        return {"job_id": job["id"], "content_id": existing["id"] if existing else None, "reused": True, "state": job["state"]}
    try:
        snapshot = json.loads(job["snapshot_json"])
        if mode == "template":
            output = {"result": template_result(snapshot), "attempts": 0, "usage": {}}
        elif client:
            output = client.generate_json(snapshot, PROMPT_VERSION)
        else:
            raise ModelError("请先配置模型。", "missing_api_key", 0)
        content_id = save_draft(repo, job["id"], output["result"], mode, output["attempts"], output["usage"], logical_id)
        return {"job_id": job["id"], "content_id": content_id, "reused": False, "state": "succeeded"}
    except Exception as exc:
        with repo.connect(write=True) as db:
            db.execute("UPDATE generation_jobs SET state='failed',attempts=?,error_code=?,finished_at=? WHERE id=? AND state='running'",
                       (getattr(exc, "attempts", 0), getattr(exc, "code", "internal_error"), now(), job["id"]))
        if isinstance(exc, BusinessError):
            raise
        raise BusinessError("任务失败，错误已按任务编号记录。请检查配置或稍后手动重试。", "generation_failed") from exc


def _content(db, content_id):
    row = db.execute("SELECT * FROM content_revisions WHERE id=?", (content_id,)).fetchone()
    if not row:
        raise BusinessError("内容修订不存在。")
    return row


def _assert_current(db, row):
    current = current_basis(db, json.loads(row["snapshot_json"]))
    if current["missing"] or current["snapshot_hash"] != row["snapshot_hash"]:
        raise BusinessError("依据已变化或存在冲突，请生成新修订并重新审核。", "stale_basis")


def edit_content(repo, content_id, title, body, operator, reason, rebind=False):
    if not title.strip() or not body.strip() or not operator.strip() or not reason.strip():
        raise BusinessError("标题、正文、操作人和修改原因不能为空。")
    if len(title) > 200 or len(body) > 10000:
        raise BusinessError("标题或正文过长。")
    with repo.connect(write=True) as db:
        old = _content(db, content_id)
        snapshot = json.loads(old["snapshot_json"])
        if rebind:
            basis = current_basis(db, snapshot)
            if basis["missing"]:
                raise BusinessError("当前依据不完整或存在冲突，不能重绑。")
            snapshot = basis["snapshot"]
        basis = current_basis(db, snapshot)
        state = "stale" if basis["missing"] or basis["snapshot_hash"] != snapshot_hash(snapshot) else "draft"
        new_id = _insert_content(db, snapshot, {"title": title, "body": body}, state, "manual", logical_id=old["logical_id"], reason=reason.strip())
        db.execute("INSERT INTO review_records(content_id,operator,decision,basis_hash,reason,created_at) VALUES(?,?,?,?,?,?)",
                   (new_id, operator.strip(), "edited", snapshot_hash(snapshot), reason.strip(), now()))
        return new_id


def submit_for_review(repo, content_id, operator):
    if not operator.strip():
        raise BusinessError("请填写操作人。")
    with repo.connect(write=True) as db:
        row = _content(db, content_id)
        if row["state"] != "draft":
            raise BusinessError("只有草稿可提交审核。")
        _assert_current(db, row)
        db.execute("UPDATE content_revisions SET state='review' WHERE id=?", (content_id,))
        db.execute("INSERT INTO review_records(content_id,operator,decision,basis_hash,reason,created_at) VALUES(?,?,?,?,?,?)",
                   (content_id, operator.strip(), "submitted", row["snapshot_hash"], "提交人工逐句核对", now()))


def approve_content(repo, content_id, operator, basis_hash, reason):
    if not operator.strip() or not reason.strip():
        raise BusinessError("请填写审核人和审核说明。")
    with repo.connect(write=True) as db:
        row = _content(db, content_id)
        if row["state"] != "review":
            raise BusinessError("只有待审核内容可通过审核。")
        if basis_hash != row["snapshot_hash"]:
            raise BusinessError("页面审核依据不一致，请刷新。", "concurrent_change")
        _assert_current(db, row)
        db.execute("UPDATE content_revisions SET state='ready' WHERE id=?", (content_id,))
        db.execute("INSERT INTO review_records(content_id,operator,decision,basis_hash,reason,created_at) VALUES(?,?,?,?,?,?)",
                   (content_id, operator.strip(), "approved", basis_hash, reason.strip(), now()))


def export_content(repo, content_id, operator):
    if not operator.strip():
        raise BusinessError("请填写导出操作人。")
    with repo.connect(write=True) as db:
        row = _content(db, content_id)
        if row["state"] != "ready":
            raise BusinessError("仅已审核且依据有效的内容可以导出。")
        _assert_current(db, row)
        review = db.execute("SELECT * FROM review_records WHERE content_id=? AND decision='approved' ORDER BY id DESC LIMIT 1", (content_id,)).fetchone()
        if not review or review["basis_hash"] != row["snapshot_hash"]:
            raise BusinessError("缺少有效审核记录，不能导出。")
        snapshot = json.loads(row["snapshot_json"])
        text = (f"{row['title']}\n\n{row['body']}\n\n---\n"
                f"产品：{snapshot['brand_code']} / {snapshot['sku']} / {snapshot['product_version']}\n"
                f"渠道：{row['context']} | 内容修订：{row['logical_id']} / R{row['revision']}\n"
                f"生成时间：{row['created_at']} | 模式：{row['mode']}\n"
                f"审核人：{review['operator']} | 审核时间：{review['created_at']}\n"
                "已导出或已发布内容如有变更，需经营者自行替换。\n")
        folder = repo.settings.runtime_dir / "exports"
        folder.mkdir(parents=True, exist_ok=True)
        filename = f"{content_id}-R{row['revision']}-{uuid.uuid4().hex[:8]}.txt"
        path = folder / filename
        path.write_text(text, encoding="utf-8")
        db.execute("INSERT INTO export_records(content_id,operator,basis_hash,body_hash,stored_path,created_at) VALUES(?,?,?,?,?,?)",
                   (content_id, operator.strip(), row["snapshot_hash"], hashlib.sha256(text.encode()).hexdigest(), str(path.relative_to(repo.settings.runtime_dir)), now()))
        return {"text": text, "filename": filename, "path": str(path)}
