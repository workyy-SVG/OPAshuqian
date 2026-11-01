from xml.etree import ElementTree as ET
import pytest
from streamlit.testing.v1 import AppTest
from config import ROOT
from views.visual_tutorial import SCENES,screen_svg


@pytest.mark.parametrize('topic',list(SCENES))
def test_each_screen_is_valid_labeled_svg(topic):
    images=[]
    for step in range(len(SCENES[topic])):
        svg=screen_svg(topic,step)
        root=ET.fromstring(svg)
        assert root.attrib['role']=='img' and '教学' in svg
        images.append(svg)
    assert len(set(images))==len(images)


def test_quality_walkthrough_requires_reason_and_keeps_business_data(repo,monkeypatch):
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR',str(repo.settings.runtime_dir))
    monkeypatch.setenv('QIANPIN_DB_PATH',str(repo.settings.db_path))
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    app.button(key='welcome_close').click().run()
    app.radio(key='navigation').set_value('使用教程').run()
    app.selectbox(key='tutorial_topic').set_value('数据核对').run()
    for _ in range(2): app.button(key='visual_action:数据核对').click().run()
    app.button(key='visual_action:数据核对').click().run()
    assert app.session_state['visual_step:数据核对']==2
    assert any('先填写依据' in w.value for w in app.warning)
    app.text_input(key='visual_reason:数据核对:2').set_value('包装为200g，250g为误录')
    app.button(key='visual_action:数据核对').click().run()
    assert app.session_state['visual_step:数据核对']==2
    assert any('先勾选' in w.value for w in app.warning)
    app.checkbox(key='visual_ack:数据核对:2').check()
    app.button(key='visual_action:数据核对').click().run()
    app.button(key='visual_action:数据核对').click().run()
    app.text_input(key='visual_reason:数据核对:4').set_value('已对照示例包装为200g')
    app.button(key='visual_action:数据核对').click().run()
    assert not app.exception and app.session_state['visual_step:数据核对']==5
    assert not repo.products() and not repo.all('SELECT * FROM fact_revisions')
    app.button(key='visual_reset:数据核对').click().run()
    assert app.session_state['visual_step:数据核对']==0


@pytest.mark.parametrize('topic',['产品资料','内容工作台','变更追踪'])
def test_other_visual_lessons_complete_without_business_changes(repo,monkeypatch,topic):
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR',str(repo.settings.runtime_dir))
    monkeypatch.setenv('QIANPIN_DB_PATH',str(repo.settings.db_path))
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    app.button(key='welcome_close').click().run()
    app.radio(key='navigation').set_value('使用教程').run()
    app.selectbox(key='tutorial_topic').set_value(topic).run()
    for step in range(len(SCENES[topic])-1):
        if topic=='内容工作台' and step==3:
            app.text_input(key='visual_reason:内容工作台:3').set_value('逐句核对示例资料一致')
            app.checkbox(key='visual_ack:内容工作台:3').check()
        app.button(key='visual_action:'+topic).click().run()
        assert not app.exception
    assert any('演示完成' in s.value for s in app.success)
    assert not repo.all('SELECT * FROM content_revisions')
    assert not repo.all('SELECT * FROM sources')
