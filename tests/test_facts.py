import pytest
from repository import BusinessError
from services.fact_service import build_snapshot, confirm_fact
from services.import_service import add_manual
from tests.conftest import confirmed


def test_identity_context_and_concurrency(repo):
    p = confirmed(repo)
    p2 = confirmed(repo, "P002")
    v2 = confirmed(repo, "P001", "V2")
    a = build_snapshot(repo, p)
    assert not a["missing"]
    assert a["snapshot_hash"] != build_snapshot(repo, p2)["snapshot_hash"]
    assert a["snapshot_hash"] != build_snapshot(repo, v2)["snapshot_hash"]
    obs = add_manual(repo, p, "price_cent", "10.00", "wholesale", "批发表", "新增渠道", "甲")
    confirm_fact(repo, p, obs, None, "甲", "渠道单独确认")
    assert next(f for f in build_snapshot(repo, p, "wholesale")["snapshot"]["facts"] if f["field"] == "price_cent")["value"] == "1000"
    old = next(f for f in a["snapshot"]["facts"] if f["field"] == "price_cent")["fact_revision_id"]
    obs = add_manual(repo, p, "price_cent", "14.00", "retail", "新价单", "调价", "甲")
    with pytest.raises(BusinessError) as error:
        confirm_fact(repo, p, obs, None, "甲", "调价")
    assert error.value.code == "concurrent_change"
    new = confirm_fact(repo, p, obs, old, "甲", "核对新价单")
    assert repo.one("SELECT state FROM fact_revisions WHERE id=?", (old,))["state"] == "superseded"
    assert new != old
    assert build_snapshot(repo, p)["snapshot_hash"] != a["snapshot_hash"]


def test_same_value_does_not_create_revision(repo):
    p = confirmed(repo)
    old = repo.one("SELECT id FROM fact_revisions WHERE field='net_weight_g'")["id"]
    obs = add_manual(repo, p, "net_weight_g", "0.2kg", "general", "新证据", "核对", "甲")
    assert confirm_fact(repo, p, obs, old, "甲", "等价单位") == old
    assert len(repo.all("SELECT * FROM fact_revisions")) == 3
