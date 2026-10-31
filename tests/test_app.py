from config import ROOT
from streamlit.testing.v1 import AppTest
from tests.conftest import confirmed
from tests.test_content import ready


def test_empty_app_and_sample_import(tmp_path, monkeypatch):
    monkeypatch.setenv("QIANPIN_RUNTIME_DIR", str(tmp_path))
    monkeypatch.delenv("QIANPIN_DB_PATH", raising=False)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert not app.exception
    app.button(key="import_sample").click().run()
    assert not app.exception
    assert app.selectbox(key="selected_product").value is not None
    for page in ("数据核对", "内容工作台", "变更追踪", "产品资料"):
        app.radio(key="navigation").set_value(page).run()
        assert not app.exception, page


def test_ui_generate_submit_and_review(repo, monkeypatch):
    monkeypatch.setenv("QIANPIN_RUNTIME_DIR", str(repo.settings.runtime_dir))
    monkeypatch.setenv("QIANPIN_DB_PATH", str(repo.settings.db_path))
    p = confirmed(repo)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    app.text_input(key="operator").set_value("界面测试员").run()
    app.radio(key="navigation").set_value("内容工作台").run()
    app.button(key="generate_draft").click().run()
    assert not app.exception
    row = repo.one("SELECT * FROM content_revisions")
    assert row["state"] == "draft"
    app.button(key=f"submit:{row['id']}").click().run()
    assert not app.exception
    assert repo.one("SELECT state FROM content_revisions")["state"] == "review"
    checkbox = next(w for w in app.checkbox if "已逐句核对" in w.label)
    checkbox.check()
    reason = next(w for w in app.text_input if w.label == "审核说明")
    reason.set_value("逐句核对完成")
    next(w for w in app.button if w.label == "审核通过").click().run()
    assert not app.exception
    assert repo.one("SELECT state FROM content_revisions")["state"] == "ready"
