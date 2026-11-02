import pytest
from streamlit.testing.v1 import AppTest

from config import ROOT
from repository import BusinessError
from services.import_service import create_basic_product, add_manual_batch
from tests.conftest import confirmed


@pytest.mark.parametrize('create', [True, False])
def test_invalid_manual_weight_does_not_save_partial_product(repo, create):
    product = None if create else repo.add_product('existing', 'V1')
    with pytest.raises(BusinessError, match='重量|净含量|单位'):
        if create:
            create_basic_product(repo, '校验测试', '错误重量', '测试包装', 'invalid')
        else:
            add_manual_batch(repo, product, {'product_name': '校验测试', 'net_weight_g': '错误重量'},
                             '测试包装', '测试原因', '测试员')
    assert not repo.all('SELECT * FROM sources')
    assert not repo.all('SELECT * FROM observations')
    if create:
        assert not repo.products()


def app_for(repo, monkeypatch):
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR', str(repo.settings.runtime_dir))
    monkeypatch.setenv('QIANPIN_DB_PATH', str(repo.settings.db_path))
    return AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()


def test_manual_price_channel_appears_before_submitting(repo, monkeypatch):
    repo.add_product('manual', 'V1')
    app = app_for(repo, monkeypatch)
    next(s for s in app.selectbox if s.label == '字段').set_value('price_cent').run()
    assert not app.exception
    assert any(s.label == '价格渠道' for s in app.selectbox)


def test_generating_and_impact_review_open_review_tab(repo, monkeypatch):
    confirmed(repo)
    app = app_for(repo, monkeypatch)
    app.radio(key='navigation').set_value('内容工作台').run()
    app.button(key='generate_draft').click().run()
    assert not app.exception
    assert app.session_state['content_workspace_tab'] == '② 审核与导出'
    row = repo.one('SELECT * FROM content_revisions')
    assert app.selectbox(key='content_choice').value == row['id']
    # Follow the actual impact-page review button to the selected revision.
    from services.import_service import add_manual
    from services.fact_service import confirm_fact
    old = repo.one("SELECT id FROM fact_revisions WHERE field='price_cent' AND state='current'")
    obs = add_manual(repo, row['product_id'], 'price_cent', '14.00', 'retail', '新价表', '调价', '测试员')
    confirm_fact(repo, row['product_id'], obs, old['id'], '测试员', '已核对新价')
    app.radio(key='navigation').set_value('变更追踪').run()
    app.button(key=f"edit-impact:{row['id']}").click().run()
    assert not app.exception
    assert app.radio(key='navigation').value == '内容工作台'
    assert app.session_state['content_workspace_tab'] == '② 审核与导出'
    assert app.selectbox(key='content_choice').value == row['id']


def test_food_catalog_is_paginated_and_search_resets_page(repo, monkeypatch):
    app = app_for(repo, monkeypatch)
    cards = lambda: [b.key for b in app.button if (b.key or '').startswith('local_food:')]
    assert len(cards()) == 6
    first = set(cards())
    next(n for n in app.number_input if n.label == '食品列表页码').set_value(2).run()
    assert len(cards()) == 6 and not first.intersection(cards())
    app.text_input(key='local_food_keyword').set_value('刺梨汁').run()
    assert cards() == ['local_food:刺梨汁']
