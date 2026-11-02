from services.local_food_catalog import categories, search_foods
from config import ROOT
from streamlit.testing.v1 import AppTest


def test_guizhou_catalog_is_chinese_and_searchable():
    foods = search_foods()
    assert len(foods) >= 20
    assert all(item['name'] and item['region'] and item['kind'] for item in foods)
    assert any(item['name'] == '刺梨汁' for item in search_foods(keyword='刺梨'))
    assert any(item['name'] == '红酸汤底料' for item in search_foods(keyword='黔东南'))


def test_category_filter_never_mixes_unrelated_items():
    assert '贵州饮品' in categories()
    drinks = search_foods('贵州饮品')
    assert drinks
    assert all(item['category'] == '贵州饮品' for item in drinks)
    assert not search_foods('贵州饮品', '羊肉粉')


def test_food_card_opens_separate_detail_and_returns(tmp_path, monkeypatch):
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR', str(tmp_path))
    monkeypatch.delenv('QIANPIN_DB_PATH', raising=False)
    monkeypatch.setattr('views.food_facts_view.cached_chinese_food', lambda name: [
        {'title': name, 'extract': '在线中文简介',
         'url': 'https://zh.wikipedia.org/wiki/example', 'image': ''}
    ])
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20).run()
    app.button(key='local_food:刺梨汁').click().run()
    assert not app.exception
    assert app.button(key='local_food_back')
    assert any('在线中文简介' in item.value for item in app.markdown)
    assert not any(button.key and button.key.startswith('local_food:') for button in app.button)
    app.button(key='local_food_back').click().run()
    assert not app.exception
    assert app.button(key='local_food:刺梨汁')
