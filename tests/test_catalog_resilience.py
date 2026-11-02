import json
import time
from unittest.mock import Mock

import pytest

from repository import BusinessError
from services import food_facts_service as food
from services.food_catalog_cache import snapshot_path, MAX_AGE_SECONDS
from tests.test_food_facts import Response, product
from streamlit.testing.v1 import AppTest
from config import ROOT


@pytest.fixture(autouse=True)
def limits(monkeypatch):
    for values in food._calls.values():
        values.clear()
    monkeypatch.setattr(food.time, 'sleep', lambda _: None)


def test_503_retries_once_then_returns_real_response(monkeypatch, tmp_path):
    get = Mock(side_effect=[Response(status=503), Response({'products': [product()], 'count': 1})])
    monkeypatch.setattr(food.requests, 'get', get)
    result = food.browse('水饮', '饮用水', cache_dir=tmp_path)
    assert get.call_count == 2
    assert len(food._calls['name']) == 2
    assert result['products'][0]['code'] == product()['code']
    assert not result['stale']
    assert get.call_args.kwargs['params']['categories_tags'] == 'en:waters'
    again = food.browse('水饮', '饮用水', cache_dir=tmp_path)
    assert again['cached'] and get.call_count == 2


def expire(folder, tag, page=1, seconds=7200):
    path = snapshot_path(folder, tag, page)
    saved = json.loads(path.read_text())
    saved['saved_at'] = time.time() - seconds
    path.write_text(json.dumps(saved))


def test_stale_cache_survives_service_restart_and_is_isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(food.requests, 'get', lambda *a, **k: Response({'products': [product()]}))
    first = food.browse('水饮', '饮用水', cache_dir=tmp_path)
    expire(tmp_path, 'en:waters')
    get = Mock(return_value=Response(status=503))
    monkeypatch.setattr(food.requests, 'get', get)
    restored = food.browse('水饮', '饮用水', cache_dir=tmp_path)
    assert restored['stale'] and restored['cached'] and '503' in restored['source_error']
    assert restored['products'] == first['products'] and get.call_count == 2
    # Neither another category nor another page may reuse the waters page.
    for category, subcategory, page in [('水饮', '果汁', 1), ('水饮', '饮用水', 2)]:
        with pytest.raises(BusinessError):
            food.browse(category, subcategory, page, cache_dir=tmp_path)
    assert not snapshot_path(tmp_path, 'en:fruit-juices', 1).exists()


def test_no_count_page_length_is_not_a_total(monkeypatch):
    monkeypatch.setattr(food.requests, 'get', lambda *a, **k: Response({'count': 12, 'products': [product()] * 12}))
    result = food.browse('水饮', '饮料与饮用水', 2)
    assert result['total'] is None and result['has_next']


@pytest.mark.parametrize('status', [403, 429, 302])
def test_no_retry_on_denial_redirect_or_rate_limit(monkeypatch, status):
    get = Mock(return_value=Response(status=status))
    monkeypatch.setattr(food.requests, 'get', get)
    with pytest.raises(BusinessError):
        food.browse('水饮', '饮用水')
    assert get.call_count == 1


def test_proxy_denial_is_not_retried_or_called_no_results(monkeypatch):
    get = Mock(side_effect=food.requests.exceptions.ProxyError('proxy denied connection'))
    monkeypatch.setattr(food.requests, 'get', get)
    with pytest.raises(BusinessError) as exc:
        food.browse('水饮', '饮用水')
    assert exc.value.code == 'food_proxy' and get.call_count == 1


def test_cache_expiration_and_corruption_are_not_results(monkeypatch, tmp_path):
    monkeypatch.setattr(food.requests, 'get', lambda *a, **k: Response({'products': [product()]}))
    food.browse('水饮', '饮用水', cache_dir=tmp_path)
    expire(tmp_path, 'en:waters', seconds=MAX_AGE_SECONDS + 1)
    get = Mock(return_value=Response(status=503))
    monkeypatch.setattr(food.requests, 'get', get)
    with pytest.raises(BusinessError):
        food.browse('水饮', '饮用水', cache_dir=tmp_path)
    snapshot_path(tmp_path, 'en:waters', 1).write_text('broken JSON')
    with pytest.raises(BusinessError):
        food.browse('水饮', '饮用水', cache_dir=tmp_path)


def test_stale_page_displays_time_and_can_still_be_previewed(repo, monkeypatch):
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR', str(repo.settings.runtime_dir))
    monkeypatch.setenv('QIANPIN_DB_PATH', str(repo.settings.db_path))
    result = {'products': [product()], 'page': 1, 'total': None, 'has_next': False,
              'cached': True, 'stale': True, 'saved_at': time.time() - 7200}
    monkeypatch.setattr('views.food_facts_view.cached_catalog', lambda *a: result)
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20).run()
    app.selectbox(key='catalog_category').set_value('水饮').run()
    app.button(key='catalog_load').click().run()
    assert not app.exception
    assert any('同一分类、同一页' in m.value for m in app.warning)
    assert any('北京时间' in m.value for m in app.caption)
    app.button(key='catalog_pick:0:3017620422003').click().run()
    assert app.session_state['food_preview_open'] and not repo.products()
