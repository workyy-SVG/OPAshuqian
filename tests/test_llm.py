import json
import pytest
import requests
from config import ModelConfig, QwenConfig
from repository import BusinessError
from services.fact_service import build_snapshot
from services.content_service import template_result, generate_content
from services.llm_client import DeepSeekClient, QwenClient, ModelError
from services.quota_service import reserve_request, quota_status
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


def test_qwen_uses_official_endpoint_and_json_mode(repo):
    p = confirmed(repo)
    snap = build_snapshot(repo, p)["snapshot"]
    result = template_result(snap)
    requests_seen = []
    def post(*args, **kwargs):
        requests_seen.append((args, kwargs))
        return Response(content=json.dumps(result))
    client = QwenClient(QwenConfig(api_key="test-qwen-key"), post, lambda _: None)
    cid = generate_content(repo, p, "qwen", mode="qwen", client=client)["content_id"]
    assert cid
    args, kwargs = requests_seen[0]
    assert args[0] == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert kwargs["json"]["response_format"] == {"type": "json_object"}
    assert kwargs["json"]["enable_thinking"] is False
    assert "thinking" not in kwargs["json"]
    job = repo.one("SELECT model,state FROM generation_jobs")
    assert job["model"] == "qwen-plus" and job["state"] == "succeeded"


def test_daily_quota_is_separate_and_blocks_request_101(repo):
    for _ in range(100):
        reserve_request(repo, "deepseek")
    status = quota_status(repo)
    assert status["deepseek"]["used"] == 100 and status["deepseek"]["remaining"] == 0
    assert status["qwen"]["used"] == 0 and status["qwen"]["remaining"] == 100
    with pytest.raises(BusinessError) as err:
        reserve_request(repo, "deepseek")
    assert err.value.code == "daily_quota_exceeded"


def test_transient_retry_counts_each_outbound_request(repo):
    p = confirmed(repo)
    snap = build_snapshot(repo, p)["snapshot"]
    responses = iter([Response(status=429), Response(content=json.dumps(template_result(snap)))])
    client = DeepSeekClient(ModelConfig(api_key="test"), lambda *a, **kw: next(responses), lambda _: None)
    generate_content(repo, p, "two-counted-requests", mode="deepseek", client=client)
    assert quota_status(repo)["deepseek"]["used"] == 2
