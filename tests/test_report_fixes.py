from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
import uuid

import pytest
from streamlit.testing.v1 import AppTest

from config import ROOT, Settings, ModelConfig
from repository import Repository, BusinessError
from services.demo_service import demo_settings, quota_settings
from services.quota_service import reserve_request, session_quota_status, quota_status, CHINA_TIME
from services.text_check_service import expression_findings, text_issues
from services.content_service import generate_content, template_result
from services.fact_service import build_snapshot
from services.llm_client import DeepSeekClient
from scripts.reset_demo import reset_demo
from tests.conftest import confirmed
from tests.test_llm import Response


def test_session_requests_atomic_and_provider_shared(repo):
    def request(i):
        try:
            reserve_request(repo, ('deepseek', 'qwen')[i % 2], session_id='one-session')
            return True
        except BusinessError as exc:
            assert exc.code == 'session_quota_exceeded'
            return False
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert sum(pool.map(request, range(12))) == 3
    assert sum(v['used'] for v in quota_status(repo).values()) == 3
    assert session_quota_status(repo, 'one-session')['remaining'] == 0
    reserve_request(repo, 'qwen', session_id='other-session')
    assert session_quota_status(repo, 'other-session')['used'] == 1


def test_session_rollover_and_global_failure_rollback(repo):
    day = datetime(2026, 11, 1, 23, 59, tzinfo=CHINA_TIME)
    for _ in range(3):
        reserve_request(repo, 'deepseek', clock=lambda: day, session_id='session')
    reserve_request(repo, 'deepseek', clock=lambda: day + timedelta(minutes=2), session_id='session')
    assert session_quota_status(repo, 'session', clock=lambda: day)['used'] == 3
    assert session_quota_status(repo, 'session', clock=lambda: day + timedelta(minutes=2))['used'] == 1
    with pytest.raises(BusinessError, match='额度'):
        reserve_request(repo, 'deepseek', limit=3, clock=lambda: day, session_id='new')
    assert session_quota_status(repo, 'new', clock=lambda: day)['used'] == 0


def test_retry_cannot_exceed_session_limit(repo):
    p = confirmed(repo)
    reserve_request(repo, 'deepseek', session_id='limited')
    reserve_request(repo, 'qwen', session_id='limited')
    calls = []
    def post(*args, **kwargs):
        calls.append(1)
        return Response(status=429)
    client = DeepSeekClient(ModelConfig(api_key='test'), post, lambda _: None)
    with pytest.raises(BusinessError) as exc:
        generate_content(repo, p, 'retry-session', mode='deepseek', client=client, session_id='limited')
    assert exc.value.code == 'session_quota_exceeded'
    assert len(calls) == 1
    assert repo.one('SELECT state FROM generation_jobs')['state'] == 'failed'
    assert repo.one('SELECT attempts FROM generation_jobs')['attempts'] == 1
    assert session_quota_status(repo, 'limited')['used'] == 3


def test_public_live_switch_and_missing_quota_fail_closed(repo, monkeypatch):
    p = confirmed(repo)
    monkeypatch.setenv('QIANPIN_PUBLIC_DEMO', 'true')
    with pytest.raises(BusinessError) as exc:
        generate_content(repo, p, 'disabled', mode='qwen')
    assert exc.value.code == 'live_models_disabled'
    monkeypatch.setenv('QIANPIN_LIVE_MODELS_ENABLED', 'true')
    with pytest.raises(BusinessError) as exc:
        generate_content(repo, p, 'no-session', mode='qwen')
    assert exc.value.code == 'missing_session_quota'
    assert not repo.all('SELECT * FROM generation_jobs')


def test_public_business_databases_share_only_quota_ledger(repo, tmp_path, monkeypatch):
    monkeypatch.setenv('QIANPIN_PUBLIC_DEMO', 'true')
    monkeypatch.setenv('QIANPIN_LIVE_MODELS_ENABLED', 'true')
    for number in range(2):
        root = tmp_path / f'business-{number}'
        business = Repository(Settings(root, root / 'qianpin.sqlite3'))
        business.initialize()
        product = confirmed(business)
        result = template_result(build_snapshot(business, product)['snapshot'])
        client = DeepSeekClient(ModelConfig(api_key='fake-test-only'),
                                lambda *a, **kw: Response(content=json.dumps(result)), lambda _: None)
        args = dict(mode='deepseek', client=client, quota_repo=repo, session_id=f'session-{number}')
        first = generate_content(business, product, 'idempotent', **args)
        again = generate_content(business, product, 'idempotent', **args)
        assert first['content_id'] == again['content_id'] and again['reused']
        assert quota_status(business)['deepseek']['used'] == 0
        assert session_quota_status(repo, f'session-{number}')['used'] == 1
    assert quota_status(repo)['deepseek']['used'] == 2


def test_demo_settings_and_safe_reset(tmp_path):
    base = Settings(tmp_path, tmp_path / 'business.sqlite3')
    original = Repository(base)
    original.initialize()
    original.add_product('PRIVATE', 'V1')
    sid = uuid.uuid4().hex
    a = demo_settings(base, sid, uuid.uuid4().hex)
    b = demo_settings(base, uuid.uuid4().hex, uuid.uuid4().hex)
    first = reset_demo(a.runtime_dir)
    second = reset_demo(b.runtime_dir)
    first.add_product('ONLY-A', 'V1')
    assert 'ONLY-A' not in {p['sku'] for p in second.products()}
    assert original.products()[0]['sku'] == 'PRIVATE'
    with pytest.raises(FileExistsError):
        reset_demo(a.runtime_dir)
    with pytest.raises(ValueError):
        demo_settings(base, '../escape', sid)
    assert quota_settings(base).db_path not in (a.db_path, b.db_path)


def test_public_two_ui_sessions_and_reset_preserve_quota(tmp_path, monkeypatch):
    monkeypatch.setenv('QIANPIN_PUBLIC_DEMO', 'true')
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR', str(tmp_path))
    monkeypatch.delenv('QIANPIN_DB_PATH', raising=False)
    a = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20).run()
    b = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20).run()
    assert not a.exception and not b.exception
    sid = a.session_state['model_session_id']
    assert sid != b.session_state['model_session_id']
    old_workspace = a.session_state['demo_workspace_id']
    cfg = quota_settings(Settings(tmp_path, tmp_path / 'unused.sqlite3'))
    ledger = Repository(cfg)
    reserve_request(ledger, 'deepseek', session_id=sid)
    a.checkbox(key='confirm_demo_reset').check().run()
    a.button(key='reset_demo').click().run()
    assert not a.exception
    assert a.session_state['model_session_id'] == sid
    assert a.session_state['demo_workspace_id'] != old_workspace
    assert session_quota_status(ledger, sid)['used'] == 1
    assert b.session_state['demo_workspace_id'] != a.session_state['demo_workspace_id']
    assert not (tmp_path / 'qianpin.sqlite3').exists()


def test_expression_hints_do_not_replace_factual_gate(repo):
    p = confirmed(repo)
    snap = build_snapshot(repo, p)['snapshot']
    result = template_result(snap)
    body = result['body'] + '精选原料，香辣醇厚，增强免疫力，品质最好。'
    issues = expression_findings(result['title'], body, snap)
    assert {'精选', '醇厚', '增强免疫力', '最好'} <= {
        body[i['start']:i['end']] for i in issues if i['section'] == 'body'}
    assert not text_issues(result['title'], body, snap)
    snap['facts'].append({'field': 'ingredients_text', 'value': '精选原料，品质最好'})
    messages = [f['message'] for f in expression_findings(result['title'], body, snap)]
    assert not any('“精选”' in m for m in messages)
    assert any('“最好”' in m for m in messages)
