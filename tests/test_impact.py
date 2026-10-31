import sqlite3
import pytest
from repository import BusinessError
from services.content_service import generate_content, edit_content, export_content, submit_for_review, template_result
from services.fact_service import confirm_fact, withdraw_fact
from services.import_service import add_manual
from services.impact_service import list_impacts
from tests.conftest import confirmed
from tests.test_content import ready


def change_price(repo, product, price="14.00"):
    old = repo.one("SELECT id FROM fact_revisions WHERE product_id=? AND field='price_cent' AND context='retail' AND state='current'", (product,))["id"]
    obs = add_manual(repo, product, "price_cent", price, "retail", "拟制新价单", "调价", "甲")
    return confirm_fact(repo, product, obs, old, "甲", "核对新价格")


def test_price_impact_identity_and_optional_scope(repo):
    p = confirmed(repo)
    p2 = confirmed(repo, "P002")
    v2 = confirmed(repo, "P001", "V2")
    a = ready(repo, p)
    b = ready(repo, p, content_type="social_post")
    without_price = ready(repo, p, include_price=False)
    other = ready(repo, p2)
    other_version = ready(repo, v2)
    change_price(repo, p)
    assert {r["id"] for r in list_impacts(repo, p)} == {a, b}
    for cid in (a, b):
        assert repo.one("SELECT state FROM content_revisions WHERE id=?", (cid,))["state"] == "stale"
        with pytest.raises(BusinessError):
            export_content(repo, cid, "甲")
    for cid in (without_price, other, other_version):
        assert repo.one("SELECT state FROM content_revisions WHERE id=?", (cid,))["state"] == "ready"
        export_content(repo, cid, "甲")


def test_unused_new_field_does_not_break_old_content(repo):
    p = confirmed(repo)
    cid = ready(repo, p)
    obs = add_manual(repo, p, "storage_text", "阴凉处保存", "general", "拟制包装", "补资料", "甲")
    confirm_fact(repo, p, obs, None, "甲", "核对")
    assert not list_impacts(repo, p)
    assert export_content(repo, cid, "甲")


def test_withdraw_required_blocks_rebinding_and_review(repo):
    p = confirmed(repo)
    cid = ready(repo, p)
    old = repo.one("SELECT * FROM fact_revisions WHERE product_id=? AND field='net_weight_g'", (p,))
    withdraw_fact(repo, p, old["field"], old["context"], old["id"], "甲", "发现错误")
    assert repo.one("SELECT state FROM content_revisions WHERE id=?", (cid,))["state"] == "stale"
    with pytest.raises(BusinessError):
        edit_content(repo, cid, "标题", "原文不变", "甲", "沿用", rebind=True)
    with pytest.raises(BusinessError):
        generate_content(repo, p, "blocked")


def test_generation_race_is_preserved_stale(repo):
    from config import ModelConfig
    p = confirmed(repo)
    class WaitingClient:
        config = ModelConfig(name="test-model")
        def generate_json(self, snapshot, prompt_version):
            change_price(repo, p)
            return {"result": template_result(snapshot), "attempts": 1, "usage": {}}
    cid = generate_content(repo, p, "race", mode="deepseek", client=WaitingClient())["content_id"]
    row = repo.one("SELECT * FROM content_revisions WHERE id=?", (cid,))
    assert row["state"] == "stale" and "12.00" in row["body"]
    with pytest.raises(BusinessError):
        submit_for_review(repo, cid, "甲")


def test_transaction_rollback_covers_fact_and_content(repo):
    p = confirmed(repo)
    cid = ready(repo, p)
    old = repo.one("SELECT * FROM fact_revisions WHERE field='price_cent'")
    obs = add_manual(repo, p, "price_cent", "14.00", "retail", "新价格", "调价", "甲")
    with repo.connect() as db:
        db.execute("CREATE TRIGGER fail_content BEFORE UPDATE OF state ON content_revisions BEGIN SELECT RAISE(ABORT,'injected'); END")
    before = len(repo.all("SELECT * FROM change_events"))
    with pytest.raises(sqlite3.IntegrityError):
        confirm_fact(repo, p, obs, old["id"], "甲", "模拟失败")
    assert repo.one("SELECT state FROM fact_revisions WHERE id=?", (old["id"],))["state"] == "current"
    assert repo.one("SELECT state FROM content_revisions WHERE id=?", (cid,))["state"] == "ready"
    assert len(repo.all("SELECT * FROM fact_revisions WHERE field='price_cent'")) == 1
    assert len(repo.all("SELECT * FROM change_events")) == before
    assert repo.one("SELECT state FROM observations WHERE id=?", (obs,))["state"] == "pending"


def test_reuse_body_rebinds_new_revision_and_requires_review(repo):
    p = confirmed(repo)
    cid = ready(repo, p)
    row = repo.one("SELECT * FROM content_revisions WHERE id=?", (cid,))
    change_price(repo, p)
    new_id = edit_content(repo, cid, row["title"], row["body"].replace("12.00", "14.00"), "甲", "调价后复查", rebind=True)
    new = repo.one("SELECT * FROM content_revisions WHERE id=?", (new_id,))
    assert new["state"] == "draft" and new["snapshot_hash"] != row["snapshot_hash"]
    assert repo.one("SELECT snapshot_hash FROM content_revisions WHERE id=?", (cid,))["snapshot_hash"] == row["snapshot_hash"]
