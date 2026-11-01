import pytest
from streamlit.testing.v1 import AppTest
from config import ROOT
from services.experience_service import overview
from services.import_service import preview_import, commit_import
from views.components import STATE_LABELS, COLORS, badge_html


def test_overview_tracks_confirmed_data_without_adopting(repo):
    assert overview(repo, None)['steps'] == [False]*4
    commit_import(repo, preview_import((ROOT/'samples/products.csv').read_bytes()))
    p = repo.products()[0]['id']
    data = overview(repo, p)
    assert data['confirmed'] == 0 and data['pending'] > 0
    assert data['steps'] == [True, False, False, False]
    assert not repo.all('SELECT * FROM fact_revisions')


def test_badge_escapes_untrusted_labels():
    assert '<img' not in badge_html('<img src=x onerror=alert(1)>')
    assert '&lt;img' in badge_html('<img>')
    assert all(label and symbol and tone in COLORS for symbol,label,tone in STATE_LABELS.values())


@pytest.mark.parametrize('fg,bg', list(COLORS.values()))
def test_status_text_contrast(fg, bg):
    def luminance(color):
        channels = [int(color[i:i+2],16)/255 for i in (1,3,5)]
        linear = [c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in channels]
        return sum(a*b for a,b in zip(linear,(.2126,.7152,.0722)))
    a,b = sorted((luminance(fg),luminance(bg)))
    assert (b+.05)/(a+.05) >= 4.5


def test_sample_import_is_explicit_and_never_confirms(tmp_path, monkeypatch):
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR', str(tmp_path))
    monkeypatch.delenv('QIANPIN_DB_PATH', raising=False)
    app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=20).run()
    assert not any((b.key or '').startswith('welcome_') for b in app.button)
    app.button(key='import_sample').click().run()
    app.button(key='step:数据核对').click().run()
    assert not app.exception
    assert app.radio(key='navigation').value == '数据核对'
    from repository import Repository
    from config import Settings
    repo = Repository(Settings(tmp_path,tmp_path/'qianpin.sqlite3'))
    assert repo.products() and not repo.all('SELECT * FROM fact_revisions')


def test_candidate_card_requires_explicit_exclusion_acknowledgement(tmp_path, monkeypatch):
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR', str(tmp_path))
    monkeypatch.delenv('QIANPIN_DB_PATH', raising=False)
    app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=20).run()
    app.button(key='import_sample').click().run()
    app.button(key='step:数据核对').click().run()
    app.text_input(key='operator').set_value('体验测试员').run()
    from repository import Repository
    from config import Settings
    repo = Repository(Settings(tmp_path,tmp_path/'qianpin.sqlite3'))
    selected = app.selectbox(key='selected_product').value
    bad = repo.one("SELECT * FROM observations WHERE product_id=? AND normalized='250'", (selected,))
    app.button(key=f'exclude-card:{bad["id"]}').click().run()
    next(t for t in app.text_input if t.label=='核对依据 / 处理原因').set_value('包装为200g，250g为拟制误录')
    next(b for b in app.button if b.label=='保存本次处理').click().run()
    assert not app.exception
    assert repo.one('SELECT state FROM observations WHERE id=?',(bad['id'],))['state']=='pending'
    assert any('勾选排除确认' in w.value for w in app.warning)
    next(c for c in app.checkbox if c.label.startswith('确认排除此项')).check()
    next(b for b in app.button if b.label=='保存本次处理').click().run()
    assert not app.exception
    assert repo.one('SELECT state FROM observations WHERE id=?',(bad['id'],))['state']=='excluded'
    assert not repo.all('SELECT * FROM fact_revisions')


def test_impact_timeline_and_dependency_scope(repo, monkeypatch):
    from tests.conftest import confirmed
    from tests.test_content import ready
    from services.import_service import add_manual
    from services.fact_service import confirm_fact
    from services import query_service as queries
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR', str(repo.settings.runtime_dir))
    monkeypatch.setenv('QIANPIN_DB_PATH', str(repo.settings.db_path))
    p = confirmed(repo)
    cid = ready(repo,p)
    old = repo.one("SELECT * FROM fact_revisions WHERE field='price_cent' AND state='current'")
    assert queries.dependent_content_count(repo, old['id']) == 1
    obs = add_manual(repo,p,'price_cent','14.00','retail','拟制新价目表','调价','体验测试员')
    confirm_fact(repo,p,obs,old['id'],'体验测试员','已核对新价')
    app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=20).run()
    app.radio(key='navigation').set_value('变更追踪').run()
    assert not app.exception
    assert any('12.00 元 → 14.00 元' in m.value for m in app.markdown)
    assert any('撤回将影响' in w.value for w in app.warning)
    assert repo.one('SELECT state FROM content_revisions WHERE id=?',(cid,))['state']=='stale'
