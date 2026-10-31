import pytest
from config import ROOT
from repository import BusinessError
from services.import_service import preview_import, commit_import
from services.quality_service import detect_issues, exclude_observation
from services.fact_service import confirm_fact, build_snapshot


def test_conflict_requires_explicit_exclusion(repo):
    commit_import(repo, preview_import((ROOT / "samples/products.csv").read_bytes()))
    product = repo.products()[0]["id"]
    issues = detect_issues(repo, product)
    assert len([i for i in issues if i["type"] == "conflict"]) == 1
    group = next(i for i in issues if i["type"] == "conflict")
    chosen = next(r for r in group["observations"] if r["normalized"] == "200")
    with pytest.raises(BusinessError, match="不同值"):
        confirm_fact(repo, product, chosen["id"], None, "甲", "核对包装")
    other = next(r for r in group["observations"] if r["normalized"] == "250")
    exclude_observation(repo, other["id"], "甲", "拟制错误记录")
    fact = confirm_fact(repo, product, chosen["id"], None, "甲", "拟制包装为200g")
    assert fact
    assert repo.one("SELECT COUNT(*) n FROM observations WHERE product_id=? AND field='net_weight_g' AND state='adopted'", (product,))["n"] == 2
    assert "product_name" in build_snapshot(repo, product)["missing"]


def test_reassignment_is_audited_and_future_candidates_stay_pending(repo):
    from services.import_service import add_manual
    from services.quality_service import reassign_observation
    p = repo.add_product("001", "V1")
    p2 = repo.add_product("002", "V1")
    obs = add_manual(repo, p, "net_weight_g", "200g", "general", "拟制包装", "补录", "甲")
    reassign_observation(repo, obs, p2, "甲", "确认属于002")
    assert repo.one("SELECT product_id FROM observations WHERE id=?", (obs,))["product_id"] == p2
    assert repo.one("SELECT * FROM observation_actions WHERE action='reassign'")["old_product_id"] == p
    future = add_manual(repo, p, "price_cent", "12.00", "retail", "未来价单", "暂存", "甲", "2099-01-01")
    with pytest.raises(BusinessError, match="未来资料"):
        confirm_fact(repo, p, future, None, "甲", "不能提前生效")
    assert repo.one("SELECT state FROM observations WHERE id=?", (future,))["state"] == "pending"
