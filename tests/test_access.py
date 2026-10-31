import pytest
from services.access_service import AccessConfig, AccessRegistry, password_hash, verify_password


@pytest.fixture
def access():
    return AccessConfig(True, 'reviewer', password_hash('fictitious-test-password'), 60)


def test_password_hash_validation(access):
    assert verify_password('fictitious-test-password', access.password_hash)
    assert not verify_password('wrong', access.password_hash)
    assert not verify_password('anything', 'pbkdf2_sha256$1$bad$bad')
    assert not AccessConfig(True, 'x', 'garbage').configured
    with pytest.raises(ValueError):
        password_hash('short')


def test_login_expiry_revoke_rotation_and_rate_limit(access):
    clock = [0.0]
    registry = AccessRegistry(lambda: clock[0])
    for _ in range(5):
        assert registry.login('reviewer', 'wrong', access) is None
    assert registry.login('reviewer', 'fictitious-test-password', access) is None
    clock[0] = 301
    token = registry.login('reviewer', 'fictitious-test-password', access)
    assert registry.validate(token, access) == 'reviewer'
    assert registry.validate(token, AccessConfig(True, 'changed', access.password_hash, 60)) is None
    registry.revoke(token)
    assert registry.validate(token, access) is None
    token = registry.login('reviewer', 'fictitious-test-password', access)
    clock[0] += 61
    assert registry.validate(token, access) is None


def test_protected_app_exposes_no_business_data_without_login(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from config import ROOT
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR', str(tmp_path))
    monkeypatch.setenv('QIANPIN_AUTH_REQUIRED', 'true')
    monkeypatch.delenv('QIANPIN_AUTH_USER', raising=False)
    monkeypatch.delenv('QIANPIN_AUTH_PASSWORD_HASH', raising=False)
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20).run()
    assert not app.exception
    assert len(app.error) == 1
    assert not app.radio
    assert not (tmp_path / 'qianpin.sqlite3').exists()


def test_protected_login_locks_actor_and_logout_revokes_download(tmp_path, monkeypatch, access):
    from streamlit.testing.v1 import AppTest
    from config import ROOT
    from views.access_view import access_registry
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR', str(tmp_path))
    monkeypatch.setenv('QIANPIN_AUTH_REQUIRED', 'true')
    monkeypatch.setenv('QIANPIN_AUTH_USER', access.username)
    monkeypatch.setenv('QIANPIN_AUTH_PASSWORD_HASH', access.password_hash)
    app = AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    assert not app.exception and not app.radio
    next(w for w in app.text_input if w.label=='用户名').set_value(access.username)
    next(w for w in app.text_input if w.label=='口令').set_value('fictitious-test-password')
    next(w for w in app.button if w.label=='登录').click().run()
    assert not app.exception and app.radio(key='navigation')
    assert not any(w.label=='操作人 / 审核人' for w in app.text_input)
    token=app.session_state['access_token']
    # The app default timeout is 1800, rather than the fixture's 60 seconds.
    config=AccessConfig(True,access.username,access.password_hash,1800)
    assert access_registry().validate(token,config)
    next(w for w in app.button if w.label=='退出登录').click().run()
    assert not app.radio and access_registry().validate(token,config) is None


def test_chinese_account_names_are_supported(access):
    config=AccessConfig(True,'经营者',access.password_hash,60)
    assert AccessRegistry().login('经营者','fictitious-test-password',config)
