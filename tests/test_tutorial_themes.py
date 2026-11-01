import pytest
from streamlit.testing.v1 import AppTest
from config import ROOT
from views.themes import THEMES, theme_css
from views.tutorial_view import LESSONS


@pytest.mark.parametrize('theme', list(THEMES))
def test_themes_and_tutorial_keep_data_unchanged(repo, monkeypatch, theme):
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR',str(repo.settings.runtime_dir))
    monkeypatch.setenv('QIANPIN_DB_PATH',str(repo.settings.db_path))
    app = AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    app.radio(key='navigation').set_value('使用教程').run()
    app.selectbox(key='background_style').set_value(theme).run()
    for topic in LESSONS:
        app.selectbox(key='tutorial_topic').set_value(topic).run()
        assert not app.exception
        assert any('完成标志' in s.value for s in app.success)
    assert not repo.products()
    assert not repo.all('SELECT * FROM fact_revisions')
    app.button(key='tutorial:practice:变更追踪').click().run()
    assert app.radio(key='navigation').value == '变更追踪'
    assert app.selectbox(key='background_style').value == theme


def test_theme_style_is_from_whitelisted_palette():
    assert theme_css('</style><script>bad</script>') == theme_css('山野青绿')
