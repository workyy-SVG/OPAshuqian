import json

import pytest
import requests
from streamlit.testing.v1 import AppTest

from config import ROOT
from repository import BusinessError
from services import food_facts_service as food
from services.fact_service import confirm_fact


def product(**values):
    return dict(code='3017620422003', product_name='公开食品测试', quantity='200 g',
                ingredients_text='测试配料', **values)


class Response:
    def __init__(self, payload=None, status=200):
        self.status_code = status
        self.body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def iter_content(self, size):
        yield self.body


@pytest.fixture(autouse=True)
def reset_limits():
    for calls in food._calls.values():
        calls.clear()


def test_lookup_transport_and_name_search(monkeypatch):
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response({'product': product()} if '/product/' in url else {'products': [product()]})
    monkeypatch.setattr(food.requests, 'get', get)
    assert food.lookup('3017620422003')[0]['code'] == '3017620422003'
    assert food.lookup('测试', 'name')
    assert calls[0][0] == food.BASE + '/api/v3/product/3017620422003'
    assert calls[0][1]['allow_redirects'] is False
    assert calls[0][1]['headers']['User-Agent'] == food.USER_AGENT
    assert calls[1][1]['params']['page_size'] == '5'


@pytest.mark.parametrize('status,code', [(429,'food_rate_limit'), (503,'food_unavailable'), (302,'food_unavailable')])
def test_http_errors_do_not_import(monkeypatch, status, code):
    monkeypatch.setattr(food.requests, 'get', lambda *a, **k: Response(status=status))
    with pytest.raises(BusinessError) as exc:
        food.lookup('3017620422003')
    assert exc.value.code == code


def test_not_found_invalid_input_network_and_bad_json(monkeypatch):
    monkeypatch.setattr(food.requests, 'get', lambda *a, **k: Response(status=404))
    assert food.lookup('3017620422003') == []
    for query, kind in [('http://example.com', 'barcode'), ('x', 'name'), ('abc', 'other')]:
        with pytest.raises(BusinessError):
            food.lookup(query, kind)
    def fail(*args, **kwargs):
        raise requests.Timeout()
    monkeypatch.setattr(food.requests, 'get', fail)
    with pytest.raises(BusinessError, match='超时'):
        food.lookup('3017620422003')
    monkeypatch.setattr(food.requests, 'get', lambda *a, **k: Response(['wrong schema']))
    with pytest.raises(BusinessError, match='格式异常'):
        food.lookup('3017620422003')
    response = Response()
    response.body = b'not json'
    monkeypatch.setattr(food.requests, 'get', lambda *a, **k: response)
    with pytest.raises(BusinessError):
        food.lookup('3017620422003')


def test_response_bound_and_local_rate_limit(monkeypatch):
    response = Response()
    response.body = b' ' * (2*1024*1024+1)
    monkeypatch.setattr(food.requests, 'get', lambda *a, **k: response)
    with pytest.raises(BusinessError, match='过大'):
        food.lookup('3017620422003')
    monkeypatch.setattr(food.requests, 'get', lambda *a, **k: Response({'product': product()}))
    for _ in range(11):
        food.lookup('3017620422003')
    with pytest.raises(BusinessError, match='频率'):
        food.lookup('3017620422003')


def test_preview_preserves_leading_zeros_and_skips_volume():
    p = product()
    p['quantity'] = '200 ml'
    rows = food.candidate_preview(p, '0001', 'V1')['rows']
    assert all(r['sku'] == '0001' for r in rows)
    assert {r['field_key'] for r in rows} == {'product_name', 'ingredients_text'}
    p['quantity'] = '6 x 50 g'
    assert len(food.candidate_preview(p, '0001', 'V1')['rows']) == 2
    with pytest.raises(BusinessError):
        food.candidate_preview({'code': '12345678'}, '0001', 'V1')
    p['quantity'] = '400 g e'
    assert next(r for r in food.candidate_preview(p,'0001','V1')['rows'] if r['field_key']=='net_weight_g')['normalized'] == '400'


def test_import_is_pending_idempotent_and_preserves_snapshot(repo):
    p = product(nutriments={'sugars_100g': 3})
    preview = food.candidate_preview(p, '0001', 'V1')
    assert not repo.products()
    result = food.import_product(repo, p, '0001', 'V1')
    assert result['candidates'] == 3
    assert food.import_product(repo, p, '0001', 'V1')['reused']
    assert not repo.all('SELECT * FROM fact_revisions')
    source = repo.settings.runtime_dir / 'sources' / f'off-{food.snapshot_id(p)}.json'
    assert json.loads(source.read_bytes())['product']['nutriments']['sugars_100g'] == 3
    rows = repo.all('SELECT * FROM observations')
    assert all(r['state'] == 'pending' for r in rows)
    assert all(food.snapshot_id(p) in r['source_locator'] for r in rows)
    for row in rows:
        confirm_fact(repo, row['product_id'], row['id'], None, '测试员', '已核对包装')
    assert len(repo.all('SELECT * FROM fact_revisions')) == 3
    assert {r['field_key'] for r in preview['rows']} == {'product_name','net_weight_g','ingredients_text'}
    from tests.test_content import ready
    from services.content_service import export_content
    # Price is optional for this demonstration and must never be invented by OFF.
    cid = ready(repo, rows[0]['product_id'], include_price=False)
    assert '公开食品测试' in export_content(repo, cid, '测试员')['text']


def test_ui_search_to_candidate_import(tmp_path, monkeypatch):
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR', str(tmp_path))
    monkeypatch.delenv('QIANPIN_DB_PATH', raising=False)
    monkeypatch.setattr(food.requests, 'get', lambda *a, **k: Response({'product': product()}))
    from views.food_facts_view import cached_lookup
    cached_lookup.clear()
    app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=20).run()
    assert not app.exception
    app.radio(key='food_search_kind').set_value('barcode').run()
    next(x for x in app.text_input if x.label == '条码或名称').set_value('3017620422003')
    next(b for b in app.button if b.label == '查询公开商品资料').click().run()
    assert not app.exception
    app.button(key='search_preview').click().run()
    next(b for b in app.button if b.label == '导入为待确认候选').click().run()
    assert any('先核对商品' in w.value for w in app.warning)
    next(c for c in app.checkbox if c.label.startswith('已核对商品')).check()
    next(b for b in app.button if b.label == '导入为待确认候选').click().run()
    assert not app.exception
    assert any('OFF-3017620422003' in str(s.options) for s in app.selectbox)
