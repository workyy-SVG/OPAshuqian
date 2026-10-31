from datetime import datetime, timezone
import json
import pytest
from config import ModelConfig
from services.llm_client import DeepSeekClient, ModelError
from services.retry_service import RetryPolicy
from services.prompt_service import load_prompt, PROMPT_VERSION
from services.fact_service import build_snapshot
from services.content_service import template_result, generate_content
from tests.conftest import confirmed
from tests.test_llm import Response


def test_retry_after_and_bounded_exponential_delays():
    policy = RetryPolicy(max_attempts=3)
    assert policy.delay(1, rng=lambda a,b:0) == 1
    assert policy.delay(2, rng=lambda a,b:0) == 2
    assert policy.delay(1, '3') == 3
    assert policy.delay(1, '100') is None
    assert policy.delay(1, 'Thu, 01 Jan 2026 00:00:05 GMT', now=datetime(2026,1,1,tzinfo=timezone.utc)) == 5
    assert policy.delay(1, 'invalid', rng=lambda a,b:0) == 1
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=10)


def test_retry_respects_server_and_never_retries_permanent_or_excess_wait(repo):
    p = confirmed(repo)
    calls, delays = [], []
    first = Response(status=429)
    first.headers = {'Retry-After': '3'}
    result = template_result(build_snapshot(repo,p)['snapshot'])
    responses = iter([first, Response(content=json.dumps(result))])
    def post(*a, **kw):
        calls.append(1)
        return next(responses)
    client = DeepSeekClient(ModelConfig(api_key='fake'), post, delays.append)
    assert generate_content(repo,p,'bounded',mode='deepseek',client=client)['content_id']
    assert delays == [3] and len(calls) == 2
    first.headers = {'Retry-After': '120'}
    client = DeepSeekClient(ModelConfig(api_key='fake'), lambda *a,**kw:first, delays.append)
    with pytest.raises(ModelError) as error:
        client.generate_json(build_snapshot(repo,p)['snapshot'])
    assert error.value.attempts == 1 and delays == [3]


def test_prompt_versions_are_validated_and_recorded(repo):
    assert 'json' in load_prompt('qianpin-v1')
    assert 'json' in load_prompt(PROMPT_VERSION)
    with pytest.raises(ValueError, match='未知'):
        load_prompt('../secret')
    p = confirmed(repo)
    generate_content(repo,p,'prompt-version')
    assert repo.one('SELECT prompt_version FROM generation_jobs')['prompt_version'] == PROMPT_VERSION


def test_invalid_prompt_prevents_network_request(repo):
    p = confirmed(repo)
    client = DeepSeekClient(ModelConfig(api_key='fake'), lambda *a,**kw:pytest.fail('unexpected network'))
    with pytest.raises(ModelError) as error:
        client.generate_json(build_snapshot(repo,p)['snapshot'], '../unknown')
    assert error.value.code == 'invalid_prompt'
