"""A reproducible fictitious scenario, separate from the user's runtime DB."""
import argparse
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from config import ROOT, Settings
from repository import Repository, BusinessError
from services.import_service import preview_import, commit_import, add_manual
from services.quality_service import exclude_observation
from services.fact_service import confirm_fact
from services.content_service import generate_content, submit_for_review, approve_content, export_content
from services.impact_service import list_impacts
from scripts.backup_db import backup_db
from scripts.restore_check import restore_check


def run_demo(folder):
    folder = Path(folder).resolve()
    if folder.exists():
        raise BusinessError("演示目录已存在，请选新目录以保留原数据。")
    repo = Repository(Settings(folder, folder / "qianpin.sqlite3"))
    repo.initialize()
    imported = commit_import(repo, preview_import((ROOT / "samples/products.csv").read_bytes()), "拟制演示样例.csv")
    product = repo.one("SELECT * FROM product_versions WHERE sku='P001' AND version='V1'")
    conflict = repo.one("SELECT id FROM observations WHERE product_id=? AND field='net_weight_g' AND normalized='250'", (product["id"],))
    exclude_observation(repo, conflict["id"], "拟制演示脚本", "仅演示：假设经营者核对包装后确认200g，排除250g误录")
    for candidate in repo.all("SELECT * FROM observations WHERE state='pending' ORDER BY id"):
        if repo.one("SELECT state FROM observations WHERE id=?", (candidate["id"],))["state"] != "pending":
            continue
        confirm_fact(repo, candidate["product_id"], candidate["id"], None, "拟制演示脚本", "拟制场景预设确认，非真实用户核验")
    def make_ready(pid, kind="product_intro", logical_id=None):
        cid = generate_content(repo, pid, uuid.uuid4().hex, content_type=kind, logical_id=logical_id)["content_id"]
        submit_for_review(repo, cid, "拟制演示脚本")
        content = repo.one("SELECT * FROM content_revisions WHERE id=?", (cid,))
        approve_content(repo, cid, "拟制演示脚本", content["snapshot_hash"], "拟制流程验证，实际使用必须人工逐句审核")
        export_content(repo, cid, "拟制演示脚本")
        return content
    originals = [make_ready(product["id"], kind) for kind in ("product_intro", "social_post")]
    other = repo.one("SELECT id FROM product_versions WHERE sku='P002'")["id"]
    unaffected = make_ready(other)
    old_price = repo.one("SELECT id FROM fact_revisions WHERE product_id=? AND field='price_cent' AND context='retail' AND state='current'", (product["id"],))["id"]
    obs = add_manual(repo, product["id"], "price_cent", "14.00", "retail", "拟制调价单", "演示调价", "拟制演示脚本")
    confirm_fact(repo, product["id"], obs, old_price, "拟制演示脚本", "演示：同渠道由12元调为14元")
    impacts = list_impacts(repo, product["id"])
    assert {r["id"] for r in impacts} == {r["id"] for r in originals}
    assert repo.one("SELECT state FROM content_revisions WHERE id=?", (unaffected["id"],))["state"] == "ready"
    replacements = [make_ready(product["id"], row["content_type"], row["logical_id"])["id"] for row in originals]
    backup = backup_db(repo)
    restored = restore_check(backup, folder / "restored-check.sqlite3")
    report = {"data_kind": "全部拟制；模板模式；不构成真实模型或用户效果验证", "import": imported,
              "old_content_ids": [r["id"] for r in originals], "impacted_content_ids": [r["id"] for r in impacts],
              "new_content_ids": replacements, "unaffected_other_sku": unaffected["id"],
              "restore": restored, "runtime_dir": str(folder)}
    (folder / "demo-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=ROOT / "runtime" / ("demo-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")))
    args = parser.parse_args()
    print(json.dumps(run_demo(args.out_dir), ensure_ascii=False, indent=2))
