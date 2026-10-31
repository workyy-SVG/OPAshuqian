import json
import pytest
import requests
from config import ModelConfig
from repository import BusinessError
from services.fact_service import build_snapshot
from services.content_service import template_result, generate_content
from services.llm_client import DeepSeekClient, ModelError
from tests.conftest import confirmed


class Response:
    def __init__(self, status=200, content="", finish="stop"):
        self.status_code = status
        self.content = content
        self.finish = finish
    def json(self):
        return {"choices": [{"finish_reason": self.finish, "message": {"content": self.content}}], "usage": {"total_tokens": 30}}


@pytest.mark.parametrize("response,code", [(Response(content=""), "empty_content"),
    (Response(content="oops"), "invalid_json"), (Response(content="{}", finish="length"), "truncated"),
    (Response(status=401), "http_401"), (Response(status=402), "http_402")])
def test_api_errors_are_recorded_without_success(repo, response, code):
    p = confirmed(repo)
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs)
        return response
    client = DeepSeekClient(ModelConfig(api_key="fake-test-key"), post, lambda _: None)
    with pytest.raises(ModelError) as err:
        generate_content(repo, p, "bad", mode="deepseek", client=client)
    assert err.value.code == code
    assert len(calls) == 1
    job = repo.one("SELECT * FROM generation_jobs")
    assert job["state"] == "failed" and job["error_code"] == code
    assert not repo.all("SELECT * FROM content_revisions")
    assert "fake-test-key" not in str(job)


def test_transient_retry_once_and_validate_ids(repo):
    p = confirmed(repo)
    snap = build_snapshot(repo, p)["snapshot"]
    good = template_result(snap)
    responses = iter([Response(status=429), Response(content=json.dumps(good))])
    requests_seen = []
    def post(*args, **kwargs):
        requests_seen.append(kwargs)
        return next(responses)
    client = DeepSeekClient(ModelConfig(api_key="test"), post, lambda _: None)
    cid = generate_content(repo, p, "retry", mode="deepseek", client=client)["content_id"]
    assert cid and len(requests_seen) == 2
    assert requests_seen[0]["json"]["thinking"] == {"type": "disabled"}
    assert repo.one("SELECT attempts FROM generation_jobs")["attempts"] == 2
    good["used_fact_ids"] = [999999]
    client = DeepSeekClient(ModelConfig(api_key="test"), lambda *a, **kw: Response(content=json.dumps(good)), lambda _: None)
    with pytest.raises(ModelError, match="快照以外"):
        client.generate_json(snap)


def test_network_has_two_attempts_only(repo):
    p = confirmed(repo)
    calls = []
    def post(*a, **kw):
        calls.append(1)
        raise requests.Timeout("not logged")
    client = DeepSeekClient(ModelConfig(api_key="test"), post, lambda _: None)
    with pytest.raises(ModelError):
        client.generate_json(build_snapshot(repo, p)["snapshot"])
    assert len(calls) == 2


def test_wrong_quantity_rejected(repo):
    p = confirmed(repo)
    snap = build_snapshot(repo, p)["snapshot"]
    result = template_result(snap)
    result["body"] = result["body"].replace("200 克", "250 克")
    client = DeepSeekClient(ModelConfig(api_key="test"), lambda *a, **kw: Response(content=json.dumps(result)), lambda _: None)
    with pytest.raises(ModelError) as err:
        client.generate_json(snap)
    assert err.value.code == "fact_mismatch"
