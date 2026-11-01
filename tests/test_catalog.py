import pytest
from streamlit.testing.v1 import AppTest
from config import ROOT
from repository import BusinessError
from services import food_facts_service as food
from tests.test_food_facts import Response, product


def test_catalog_category_filter_and_pagination(monkeypatch):
    calls=[]
    def get(url, **kwargs):
        calls.append((url,kwargs))
        return Response({'count':25,'products':[product()]})
    monkeypatch.setattr(food.requests,'get',get)
    for d in food._calls.values(): d.clear()
    first=food.browse('生鲜','果蔬',1)
    assert first['has_next'] and first['page']==1 and first['total']==25
    assert calls[0][1]['params']['categories_tags']=='en:fruits-and-vegetables'
    assert calls[0][1]['params']['page']=='1'
    assert calls[0][1]['params']['page_size']=='12'
    assert not food.browse('水饮','饮料与饮用水',3)['has_next']
    for args in [('熟食','不存在',1),('其他','果蔬',1),('生鲜','果蔬',0),('生鲜','果蔬',True)]:
        with pytest.raises(BusinessError): food.browse(*args)


def test_catalog_failure_and_unknown_totals(monkeypatch):
    for d in food._calls.values(): d.clear()
    monkeypatch.setattr(food.requests,'get',lambda *a,**kw:Response({'count':'not a count','products':[]}))
    result=food.browse('熟食','即食餐食')
    assert result['products']==[] and result['total'] is None and not result['has_next']
    monkeypatch.setattr(food.requests,'get',lambda *a,**kw:Response({'products':'wrong schema'}))
    with pytest.raises(BusinessError): food.browse('熟食','即食餐食')


def test_catalog_select_preview_import_and_change_category(repo,monkeypatch):
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR',str(repo.settings.runtime_dir))
    monkeypatch.setenv('QIANPIN_DB_PATH',str(repo.settings.db_path))
    from views.food_facts_view import cached_catalog
    cached_catalog.clear()
    calls=[]
    def get(url,**kwargs):
        calls.append(kwargs['params'])
        return Response({'count':30,'products':[product()]})
    monkeypatch.setattr(food.requests,'get',get)
    for d in food._calls.values(): d.clear()
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()
    app.button(key='welcome_close').click().run()
    assert calls==[]
    app.selectbox(key='catalog_category').set_value('水饮').run()
    app.button(key='catalog_load').click().run()
    assert not app.exception and calls[-1]['categories_tags']=='en:beverages'
    app.button(key='catalog_next').click().run()
    assert calls[-1]['page']=='2'
    app.button(key='catalog_pick:0:3017620422003').click().run()
    assert not repo.products()  # Selecting a catalogue item only previews it.
    next(c for c in app.checkbox if c.label.startswith('已核对商品身份')).check()
    next(b for b in app.button if b.label=='导入为待确认候选').click().run()
    assert not app.exception and repo.products()
    assert not repo.all('SELECT * FROM fact_revisions')
    app.selectbox(key='catalog_category').set_value('生鲜').run()
    assert not app.exception
    assert app.session_state['catalog_page']==1
    assert 'catalog_result' not in app.session_state
