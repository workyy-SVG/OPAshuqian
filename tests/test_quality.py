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
