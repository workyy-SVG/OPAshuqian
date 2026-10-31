from config import ROOT
from streamlit.testing.v1 import AppTest
from repository import Repository
from services import query_service as queries
from tests.conftest import confirmed
from tests.test_content import ready


def test_app_initializes_once_and_product_list_invalidates(tmp_path, monkeypatch):
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR', str(tmp_path))
    monkeypatch.delenv('QIANPIN_DB_PATH', raising=False)
    calls = []
    initialize = Repository.initialize
    def record(self):
        calls.append(1)
        return initialize(self)
    monkeypatch.setattr(Repository, 'initialize', record)
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20).run()
    app.button(key='import_sample').click().run()
    app.button(key='step:数据核对').click().run()
    assert not app.exception and len(calls) == 1
    assert app.selectbox(key='selected_product').value is not None


def test_read_models_keep_identity_and_evidence(repo):
    p = confirmed(repo)
    cid = ready(repo,p)
    assert queries.products(repo)[0]['id'] == p
    assert 'retail' in queries.channels(repo,p)
    assert len(queries.current_facts(repo,p)) == 3
    assert queries.sources(repo)
    source_id = queries.sources(repo)[0]['id']
    assert queries.source_record(repo, source_id)
    assert queries.source_observations(repo, source_id)
    row = queries.content_history(repo,p,False)[0]
    assert row['id'] == cid and not queries.content_basis(repo,row)['missing']
    assert len(queries.content_evidence(repo,cid)) == 3
    assert queries.content_reviews(repo,cid)
    assert queries.generation_jobs(repo,p)
    assert queries.observation_actions(repo,p)
    assert queries.fact_history(repo,p) and queries.change_history(repo,p)
    assert queries.content_exports(repo,cid) == []


def test_views_have_no_sql_statements():
    import re
    assert not [p.name for p in (ROOT/'views').glob('*.py') if re.search(r'\b(SELECT|INSERT INTO|UPDATE .* SET|DELETE FROM)\b', p.read_text(encoding='utf-8'))]
