from xml.etree import ElementTree as ET
import pytest
from streamlit.testing.v1 import AppTest
from config import ROOT
from views.workflow_charts import FLOWS,flow_svg
from views.tutorial_view import PROCEDURES


@pytest.mark.parametrize('topic',list(FLOWS))
def test_flowchart_decisions_have_labeled_return_paths(topic):
    svg=flow_svg(topic)
    root=ET.fromstring(svg)
    assert root.attrib['role']=='img'
    ns={'s':'http://www.w3.org/2000/svg'}
    assert len(root.findall('s:polygon',ns)) == sum(bool(n[2]) for n in FLOWS[topic])
    assert 'marker-end' in svg and 'stroke-dasharray' in svg
    assert len(FLOWS[topic])==len(PROCEDURES[topic])
    assert all(all(piece.strip() for piece in row) for row in PROCEDURES[topic])


def test_manual_has_no_demo_and_routes_to_correct_workspace(repo,monkeypatch):
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR',str(repo.settings.runtime_dir))
    monkeypatch.setenv('QIANPIN_DB_PATH',str(repo.settings.db_path))
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    assert not any((b.key or '').startswith(('welcome_','visual_','open_guide')) for b in app.button)
    app.radio(key='navigation').set_value('使用教程').run()
    for topic in FLOWS:
        app.selectbox(key='tutorial_topic').set_value(topic).run()
        assert not app.exception
        assert any('入口位置' in c.value for c in app.caption)
        assert not any((b.key or '').startswith('visual_') for b in app.button)
    assert not repo.products()
    app.button(key='tutorial:practice:变更追踪').click().run()
    assert app.radio(key='navigation').value=='变更追踪'


def test_workspace_order_and_review_tab_order(repo,monkeypatch):
    from tests.conftest import confirmed
    confirmed(repo)
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR',str(repo.settings.runtime_dir))
    monkeypatch.setenv('QIANPIN_DB_PATH',str(repo.settings.db_path))
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    assert app.radio(key='navigation').options==['01 · 产品资料','02 · 数据核对','03 · 内容工作台','04 · 变更追踪','帮助 · 使用教程']
    app.radio(key='navigation').set_value('数据核对').run()
    assert app.tabs[0].label=='① 待处理资料'
    app.radio(key='navigation').set_value('内容工作台').run()
    assert [t.label for t in app.tabs]==['① 生成内容','② 审核与导出']
