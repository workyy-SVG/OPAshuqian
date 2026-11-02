import csv
import hashlib
import io
import json
import re
import uuid
from typing import Any
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from config import BRAND_CODE, FIELDS, MAX_UPLOAD_BYTES, MAX_IMPORT_ROWS
from repository import BusinessError, now
from services.unit_service import normalize_weight
from repository import Repository

COLUMNS = ["sku", "product_version", "field_key", "raw_value", "context_key",
           "source_label", "source_locator", "effective_from"]
WIDE_FIELDS = {'商品名称':'product_name','净含量':'net_weight_g','零售价格':'price_cent',
               '配料':'ingredients_text','使用方法':'usage_text','储存说明':'storage_text'}


def normalize_value(field: str, raw: str) -> str:
    value = raw.strip()
    if not value:
        raise BusinessError("值不能为空。")
    if len(value) > 10000:
        raise BusinessError("单项资料不能超过 10000 字符。")
    if field not in FIELDS:
        raise BusinessError("无法识别的字段名。")
    if field == "net_weight_g":
        try:
            return normalize_weight(value)
        except ValueError as exc:
            raise BusinessError(str(exc)) from exc
    if field == "price_cent":
        match = re.fullmatch(r"(?:¥|￥)?\s*(\d+(?:\.\d{1,2})?)\s*元?", value)
        if not match:
            raise BusinessError("价格按元填写，最多两位小数，例如 12.00 或 12元。")
        cents = Decimal(match[1]) * 100
        if cents > 100000000000:
            raise BusinessError("价格超出允许范围。")
        return str(int(cents))
    return " ".join(value.split())


def normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for row in rows:
        item = dict(row)
        problems = []
        for key in COLUMNS:
            item.setdefault(key, "")
            if item[key] is None:
                item[key] = ""
        for key in ("sku", "product_version", "field_key", "context_key", "source_label", "source_locator", "effective_from"):
            item[key] = item[key].strip()
        if not item["sku"] or not item["product_version"]:
            problems.append("SKU 和产品版本不能为空")
        if max(len(item["sku"]), len(item["product_version"])) > 80:
            problems.append("SKU 或版本超过 80 字符")
        if not item["source_label"]:
            problems.append("来源说明不能为空")
        if item["field_key"] == "price_cent":
            if not item["context_key"] or item["context_key"] == "general":
                problems.append("价格必须填写明确渠道，例如 retail")
        elif item["context_key"] not in ("", "general"):
            problems.append("非价格字段的适用范围必须为 general")
        else:
            item["context_key"] = "general"
        if item["effective_from"]:
            try:
                date.fromisoformat(item["effective_from"])
            except ValueError:
                problems.append("适用日期必须是 YYYY-MM-DD")
        try:
            item["normalized"] = normalize_value(item["field_key"], item["raw_value"])
        except (BusinessError, InvalidOperation) as exc:
            item["normalized"] = None
            problems.append(str(exc))
        item["error"] = "；".join(problems)
        item["fingerprint"] = hashlib.sha256(json.dumps(
            [item[k] for k in COLUMNS], ensure_ascii=False).encode()).hexdigest()
        results.append(item)
    return results


def preview_import(file_bytes: bytes, encoding: str = "utf-8-sig") -> dict[str, Any]:
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise BusinessError("文件超过 5MB 上限。", "file_size")
    if encoding not in ("utf-8-sig", "gb18030"):
        raise BusinessError("不支持的编码。")
    try:
        stream = io.TextIOWrapper(io.BytesIO(file_bytes), encoding=encoding, newline='')
        reader = csv.DictReader(stream, strict=True)
        headers = reader.fieldnames or []
        errors = []
        long_format = set(COLUMNS).issubset(headers)
        wide_format = {'SKU','产品版本','来源说明'}.issubset(headers) and any(h in headers for h in WIDE_FIELDS)
        if not long_format and not wide_format:
            errors.append("表头应使用标准长表，或包含SKU、产品版本、来源说明及至少一个中文资料列")
        if len(set(headers)) != len(headers):
            errors.append("表头存在重复列")
        rows: list[dict[str, Any]] = []
        if not errors:
            for row in reader:
                if len(rows) >= MAX_IMPORT_ROWS:
                    raise BusinessError(f'文件超过{MAX_IMPORT_ROWS}条记录，请分批导入。', 'row_limit')
                if None in row:
                    errors.append(f"第 {reader.line_num} 行的列数超过表头")
                    continue
                row["row_no"] = reader.line_num
                if long_format:
                    rows.append(row)
                else:
                    for label, field in WIDE_FIELDS.items():
                        raw = (row.get(label) or '').strip()
                        if raw:
                            rows.append({'sku':row.get('SKU',''),'product_version':row.get('产品版本','V1'),
                                'field_key':field,'raw_value':raw,
                                'context_key':'retail' if field=='price_cent' else 'general',
                                'source_label':row.get('来源说明',''),'source_locator':row.get('来源位置',''),
                                'effective_from':row.get('适用日期',''),'row_no':len(rows)+2})
            if not rows:
                errors.append("CSV 没有数据行")
    except UnicodeDecodeError as exc:
        raise BusinessError("无法按所选编码读取。请明确选择 GB18030 后重新预览。", "encoding") from exc
    except csv.Error as exc:
        raise BusinessError("CSV 格式错误，请检查引号、分隔符或超长字段。", "csv_format") from exc
    finally:
        if 'stream' in locals():
            stream.close()
    return {"sha256": hashlib.sha256(file_bytes).hexdigest(), "file_bytes": file_bytes,
            "encoding": encoding, "headers": headers, "errors": errors,
            "rows": normalize_rows(rows) if not errors else []}


def commit_import(repo: Repository, preview: dict[str, Any], original_name: str = "资料.csv") -> dict[str, Any]:
    # Re-parse original bytes rather than trusting editable preview objects.
    checked = preview_import(preview["file_bytes"], preview["encoding"])
    if checked["errors"]:
        raise BusinessError("；".join(checked["errors"]))
    digest = checked["sha256"]
    folder = repo.settings.runtime_dir / "sources"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{digest}.csv"
    with repo.connect(write=True) as db:
        existing = db.execute("SELECT id FROM sources WHERE sha256=?", (digest,)).fetchone()
        if existing:
            return {"source_id": existing[0], "reused": True, **_counts(db, existing[0])}
        path.write_bytes(checked["file_bytes"])
        source_id = db.execute("INSERT INTO sources(sha256,original_name,stored_path,encoding,created_at) VALUES(?,?,?,?,?)",
            (digest, Path(original_name.replace("\\", "/")).name, str(path.relative_to(repo.settings.runtime_dir)), checked["encoding"], now())).lastrowid
        for item in checked["rows"]:
            product_id = None
            state = "error" if item["error"] else "pending"
            if not item["error"]:
                db.execute("INSERT OR IGNORE INTO product_versions(brand_code,sku,version) VALUES(?,?,?)",
                           (BRAND_CODE, item["sku"], item["product_version"]))
                product_id = db.execute("SELECT id FROM product_versions WHERE brand_code=? AND sku=? AND version=?",
                    (BRAND_CODE, item["sku"], item["product_version"])).fetchone()[0]
                if db.execute("SELECT 1 FROM observations WHERE fingerprint=? AND state NOT IN ('error','duplicate')",
                              (item["fingerprint"],)).fetchone():
                    state = "duplicate"
            db.execute("""INSERT INTO observations(source_id,row_no,product_id,field,context,raw,normalized,state,
                source_label,source_locator,effective_from,fingerprint,error) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (source_id, item["row_no"], product_id, item["field_key"], item["context_key"], item["raw_value"],
                 item["normalized"], state, item["source_label"], item["source_locator"], item["effective_from"],
                 item["fingerprint"], item["error"]))
        return {"source_id": source_id, "reused": False, **_counts(db, source_id)}


def _counts(db, source_id):
    counts = {r[0]: r[1] for r in db.execute("SELECT state,COUNT(*) FROM observations WHERE source_id=? GROUP BY state", (source_id,))}
    products = [dict(r) for r in db.execute("""SELECT p.id,p.sku,p.version,
        SUM(o.state IN ('pending','adopted','duplicate')) AS candidate_count
        FROM observations o JOIN product_versions p ON p.id=o.product_id
        WHERE o.source_id=? AND o.product_id IS NOT NULL GROUP BY p.id,p.sku,p.version ORDER BY p.sku,p.version""", (source_id,))]
    return {"candidates": counts.get("pending", 0) + counts.get("adopted", 0),
            "duplicates": counts.get("duplicate", 0), "errors": counts.get("error", 0),
            "pending": counts.get("pending", 0), "products": products,
            "product_ids": [p['id'] for p in products]}


def create_basic_product(repo: Repository, name: str, weight: str, source: str,
                         sku: str = '', version: str = 'V1') -> dict[str, Any]:
    sku = sku.strip() or ('QP-' + uuid.uuid4().hex[:8].upper())
    if not name.strip() or not weight.strip() or not source.strip():
        raise BusinessError('请填写商品名称、净含量和资料来源。')
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, COLUMNS)
    writer.writeheader()
    locator = '新建商品向导 ' + uuid.uuid4().hex
    for field, raw in (('product_name', name), ('net_weight_g', weight)):
        writer.writerow(dict(sku=sku, product_version=version, field_key=field, raw_value=raw,
                             context_key='general', source_label=source, source_locator=locator,
                             effective_from=''))
    result = commit_import(repo, preview_import(output.getvalue().encode('utf-8-sig')), '新建商品向导.csv')
    if not result['product_ids']:
        raise BusinessError('商品资料未能保存。')
    return {**result, 'product_id': result['product_ids'][0], 'sku': sku}


def add_manual_batch(repo: Repository, product_id: int, values: dict[str, str], source: str,
                     reason: str, operator: str, price_context: str = 'retail') -> dict[str, Any]:
    product = repo.one('SELECT * FROM product_versions WHERE id=?', (product_id,))
    if not product or not source.strip() or not reason.strip() or not operator.strip():
        raise BusinessError('请填写资料来源、补录原因和操作人。')
    provided = [(field, raw.strip()) for field, raw in values.items() if raw.strip()]
    if not provided:
        raise BusinessError('请至少填写一项产品资料。')
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, COLUMNS); writer.writeheader()
    locator = '基础资料补录 ' + uuid.uuid4().hex
    for field, raw in provided:
        writer.writerow(dict(sku=product['sku'],product_version=product['version'],field_key=field,
            raw_value=raw,context_key=price_context if field=='price_cent' else 'general',
            source_label=source,source_locator=locator,effective_from=''))
    result = commit_import(repo, preview_import(output.getvalue().encode('utf-8-sig')), '基础资料补录.csv')
    with repo.connect(write=True) as db:
        for row in db.execute('SELECT id FROM observations WHERE source_id=?', (result['source_id'],)):
            db.execute('INSERT INTO observation_actions(observation_id,action,operator,reason,created_at) VALUES(?,?,?,?,?)',
                       (row[0], 'manual', operator.strip(), reason.strip(), now()))
    return result


def add_manual(repo: Repository, product_id: int, field: str, raw: str, context: str, source_label: str, reason: str, operator: str, effective_from: str = "") -> int:
    product = repo.one("SELECT * FROM product_versions WHERE id=?", (product_id,))
    if not product:
        raise BusinessError("产品不存在。")
    if not reason.strip() or not operator.strip():
        raise BusinessError("请填写操作人和补录原因。")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, COLUMNS)
    writer.writeheader()
    writer.writerow(dict(sku=product["sku"], product_version=product["version"], field_key=field,
                         raw_value=raw, context_key=context, source_label=source_label,
                         source_locator="手动补录 " + uuid.uuid4().hex, effective_from=effective_from))
    preview = preview_import(output.getvalue().encode("utf-8-sig"))
    if preview["rows"][0]["error"]:
        raise BusinessError(preview["rows"][0]["error"])
    result = commit_import(repo, preview, "手动补录.csv")
    with repo.connect(write=True) as db:
        obs_id = db.execute("SELECT id FROM observations WHERE source_id=?", (result["source_id"],)).fetchone()[0]
        db.execute("INSERT INTO observation_actions(observation_id,action,operator,reason,created_at) VALUES(?,?,?,?,?)",
                   (obs_id, "manual", operator.strip(), reason.strip(), now()))
    return obs_id
