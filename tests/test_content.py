import json
import pytest
from repository import BusinessError, Repository
from services.content_service import (generate_content, edit_content, submit_for_review, approve_content, export_content)
from tests.conftest import confirmed


def ready(repo, product, **kwargs):
    result = generate_content(repo, product, "request-" + str(len(repo.all("SELECT * FROM generation_jobs"))), **kwargs)
    content_id = result["content_id"]
    submit_for_review(repo, content_id, "审核员")
    row = repo.one("SELECT * FROM content_revisions WHERE id=?", (content_id,))
    approve_content(repo, content_id, "审核员", row["snapshot_hash"], "逐句核对确认资料")
    return content_id


def test_review_export_edit_and_restart(repo):
    product = confirmed(repo)
    cid = ready(repo, product)
    output = export_content(repo, cid, "甲")
    assert "12.00 元" in output["text"]
    content = repo.one("SELECT * FROM content_revisions WHERE id=?", (cid,))
    new_id = edit_content(repo, cid, content["title"], content["body"] + "\n欢迎了解。", "甲", "调整表达")
    new = repo.one("SELECT * FROM content_revisions WHERE id=?", (new_id,))
    assert new["revision"] == 2 and new["state"] == "draft"
    assert repo.one("SELECT state FROM content_revisions WHERE id=?", (cid,))["state"] == "ready"
    with pytest.raises(BusinessError):
        export_content(repo, new_id, "甲")
    restarted = Repository(repo.settings)
    restarted.initialize()
    assert export_content(restarted, cid, "甲")["text"] == output["text"]
    assert len(repo.all("SELECT * FROM export_records")) == 2


def test_request_is_idempotent(repo):
    p = confirmed(repo)
    a = generate_content(repo, p, "same-request")
    b = generate_content(repo, p, "same-request")
    assert b["reused"] and a["content_id"] == b["content_id"]
    assert len(repo.all("SELECT * FROM generation_jobs")) == 1


def test_running_job_is_not_automatically_retried(repo):
    from services.content_service import create_generation
    p = confirmed(repo)
    job = create_generation(repo, p, "interrupted")
    result = generate_content(repo, p, "interrupted")
    assert not result["content_id"] and result["state"] == "running"
    assert len(repo.all("SELECT * FROM generation_jobs")) == 1


def test_all_input_facts_are_dependencies(repo):
    p = confirmed(repo)
    cid = generate_content(repo, p, "r")["content_id"]
    row = repo.one("SELECT * FROM content_revisions WHERE id=?", (cid,))
    ids = {f["fact_revision_id"] for f in json.loads(row["snapshot_json"])["facts"]}
    assert {r["fact_revision_id"] for r in repo.all("SELECT * FROM content_dependencies WHERE content_revision_id=?", (cid,))} == ids
