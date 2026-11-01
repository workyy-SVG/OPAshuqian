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


def test_first_visit_guide_loads_sample_but_never_confirms(tmp_path, monkeypatch):
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR', str(tmp_path))
    monkeypatch.delenv('QIANPIN_DB_PATH', raising=False)
    app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=20).run()
    app.button(key='welcome_import').click().run()
    assert not app.exception
    assert app.radio(key='navigation').value == '数据核对'
    from repository import Repository
    from config import Settings
    repo = Repository(Settings(tmp_path,tmp_path/'qianpin.sqlite3'))
    assert repo.products() and not repo.all('SELECT * FROM fact_revisions')
