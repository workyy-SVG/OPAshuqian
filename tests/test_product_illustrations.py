import pytest
from io import BytesIO
from streamlit.testing.v1 import AppTest
from PIL import Image
from config import ROOT
from services.product_illustration_service import illustration_kind, ILLUSTRATIONS
from services.food_facts_service import product_image_url
from tests.test_food_facts import product, Response


@pytest.mark.parametrize('name,kind', [
    ('纯牛奶', 'milk'), ('fresh milk', 'milk'), ('巧克力牛奶', 'milk'), ('chocolate milk', 'milk'),
    ('蔬菜胡萝卜', 'vegetables'), ('苹果', 'fruit'), ('苹果汁', 'juice'), ('番茄汁', 'juice'),
    ('牛奶巧克力', 'snacks'), ('milk chocolate', 'snacks'), ('牛奶饼干', 'snacks'),
    ('奶茶', 'tea'), ('milk tea', 'tea'), ('奶粉', 'powder'), ('番茄酱', 'condiments'),
    ('矿泉水', 'water'), ('草莓酸奶', 'yogurt'), ('奶酪', 'cheese'), ('可乐', 'soda'),
    ('牛肉', 'meat'), ('鲜鱼', 'fish'), ('鸡蛋', 'eggs'), ('鸡肉方便面', 'meals'),
])
def test_category_illustrations_distinguish_composite_foods(name, kind):
    assert illustration_kind({'product_name': name}) == kind


def test_uncertain_types_never_use_ingredients_or_browse_category():
    assert illustration_kind({'product_name': '不明食品', 'ingredients_text': '牛奶、胡萝卜'}) is None
    assert illustration_kind({'categories_tags': ['en:beverages']}) is None
    assert illustration_kind({'categories_tags': ['en:milks', 'en:vegetables']}) is None
    assert illustration_kind({'categories_tags': ['en:vegetables']}) == 'vegetables'
    assert illustration_kind({'product_name_zh': '牛奶', 'product_name': 'carrot'}) is None
    assert illustration_kind({'product_name': '牛奶', 'categories_tags': ['en:prepared-meals']}) == 'milk'


def test_barcode_binding_and_small_image_fallback():
    milk = 'https://images.openfoodfacts.org/images/products/611/126/696/2187/front_zh.1.400.jpg'
    vegetable = 'https://images.openfoodfacts.org/images/products/301/762/042/2003/front_en.1.400.jpg'
    assert product_image_url({'code': '6111266962187', 'image_front_url': vegetable,
                              'image_front_small_url': milk}) == milk
    assert product_image_url({'code': '12345678', 'image_front_url':
                              'https://images.openfoodfacts.org/images/products/12345678/front_en.1.jpg'})
    assert product_image_url({'code': '6111266962187', 'image_front_url': milk.replace('611/', '611%2f')}) is None


def test_sprite_contains_all_distinct_cells_and_release_asset():
    with Image.open(ROOT / 'static/product-illustrations.png') as sheet:
        assert sheet.width == sheet.height
    cells = {(col, row) for _, col, row in ILLUSTRATIONS.values()}
    assert cells == {(col, row) for col in range(4) for row in range(4)}


def test_real_image_priority_small_fallback_and_switching(monkeypatch):
    output = BytesIO()
    Image.new('RGB', (20, 20), 'blue').save(output, 'PNG')
    base = 'https://images.openfoodfacts.org/images/products/611/126/696/2187/'
    large, small = base + 'front_en.1.400.jpg', base + 'front_en.1.200.jpg'
    calls = []
    def photo(url):
        calls.append(url)
        return output.getvalue() if url == small else None
    monkeypatch.setattr('views.food_facts_view.cached_product_photo', photo)
    app = AppTest.from_string('''
import streamlit as st
from views.food_facts_view import product_photo
kind = st.radio('商品', ['milk', 'vegetables', 'missing'])
base = 'https://images.openfoodfacts.org/images/products/611/126/696/2187/'
if kind == 'milk':
    product_photo({'code': '6111266962187', 'product_name': '牛奶',
                   'image_front_url': base+'front_en.1.400.jpg',
                   'image_front_small_url': base+'front_en.1.200.jpg'})
elif kind == 'vegetables':
    product_photo({'code': '12345678', 'product_name': '胡萝卜',
                   'image_front_url': base+'front_en.1.200.jpg'})
else:
    product_photo({'code': '6111266962187', 'product_name': '牛奶'})
''').run()
    assert not app.exception and calls == [large, small]
    assert [c.value for c in app.caption] == ['商品包装图 · Open Food Facts']
    app.radio[0].set_value('vegetables').run()
    assert calls == [large, small]  # Another product's milk URL must never be downloaded.
    assert [c.value for c in app.caption] == ['蔬菜示意图 · 非实物包装，仅表示类别']
    app.radio[0].set_value('missing').run()
    assert [c.value for c in app.caption] == ['奶类饮品示意图 · 非实物包装，仅表示类别']


def test_switching_products_and_dialog_do_not_reuse_illustration(repo, monkeypatch):
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR', str(repo.settings.runtime_dir))
    monkeypatch.setenv('QIANPIN_DB_PATH', str(repo.settings.db_path))
    milk, carrot = product(), product()
    milk.update(product_name='牛奶', code='6111266962187')
    carrot.update(product_name='胡萝卜', code='12345678')
    monkeypatch.setattr('services.food_facts_service.requests.get', lambda *a, **kw: Response({'products': [milk, carrot]}))
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20).run()
    app.button(key='catalog_load').click().run()
    assert not app.exception
    captions = [c.value for c in app.caption]
    assert any('奶类饮品示意图' in c for c in captions)
    assert any('蔬菜示意图' in c for c in captions)
    app.button(key='catalog_pick:0:6111266962187').click().run()
    assert app.session_state['food_preview_product']['code'] == milk['code']
    app.button(key='close_food_preview').click().run()
    app.button(key='catalog_pick:1:12345678').click().run()
    assert not app.exception
    assert app.session_state['food_preview_product']['code'] == carrot['code']
    assert 'background-position:100.0% 0.0%' in '\n'.join(m.value for m in app.markdown)
