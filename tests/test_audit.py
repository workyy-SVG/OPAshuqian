import json
from services.audit_service import audit_event
from tests.conftest import confirmed
from tests.test_content import ready


def test_event_allowlist_excludes_keys_and_source_text(tmp_path):
    audit_event(tmp_path, 'test', 'failed', operator='secret-operator', api_key='secret-key', body='private-body',
                error_code='http_401', request_id='request_001', duration_ms=12)
    path = tmp_path / 'logs/events.jsonl'
    text = path.read_text(encoding='utf-8')
    assert 'secret-key' not in text and 'private-body' not in text and 'secret-operator' not in text
    record = json.loads(text)
    assert record['error_code'] == 'http_401' and record['actor_hash']


def test_business_events_and_rollbacks_have_codes(repo):
    import pytest
    from services.fact_service import confirm_fact
    from repository import BusinessError
    p = confirmed(repo)
    ready(repo, p)
    with pytest.raises(BusinessError):
        confirm_fact(repo, p, -1, None, '甲', 'secret-raw-evidence')
    text = (repo.settings.runtime_dir / 'logs/events.jsonl').read_text(encoding='utf-8')
    records = [json.loads(line) for line in text.splitlines()]
    assert any(r['event'] == 'fact.confirm' and r['result'] == 'failed' for r in records)
    assert any(r['event'] == 'transaction' and r['result'] == 'rolled_back' for r in records)
    assert any(r['event'] == 'content.approve' for r in records)
    assert 'secret-raw-evidence' not in text
