from copy import deepcopy
import pytest
from config import ROOT
from streamlit.testing.v1 import AppTest
from services.food_display_service import name_display, source_quantity, quantity_display
from services.food_facts_service import candidate_preview, product_image_urls
from services.product_illustration_service import illustration_kind
from tests.test_food_facts import product, Response


@pytest.mark.parametrize('name,words', [
    ('Naturell Mineralwasser', ['矿泉水']),
    ('Lime + Watermelon Sparkling Water Beverage', ['青柠', '西瓜', '气泡水']),
    ('Lemon & Lemon Zest Essenza', ['柠檬', '柠檬皮']),
    ('gazirana prirodna mineralna voda', ['气泡', '矿泉水']),
    ('Sparkling seltzer water', ['气泡水']),
    ('Kroger, vitamin enhanced water beverage, lemonade', ['柠檬', '饮用水']),
])
def test_screenshot_names_have_honest_chinese_reading_aids(name, words):
    shown = name_display({'product_name': name})
    assert shown['original'] == name and '非官方译名' in shown['label']
    assert all(word in shown['chinese'] for word in words)


def test_native_names_unknown_names_and_non_carbonated_water():
    shown = name_display({'product_name': 'Water', 'product_name_zh': '山泉饮用水'})
    assert shown['chinese'] == '山泉饮用水' and shown['label'] == '中文名（来源提供）'
    assert '无法可靠翻译' in name_display({'product_name': 'Unidentified Brand X'})['chinese']
    assert '气泡' not in name_display({'product_name': 'non-carbonated mineral water'})['chinese']
    assert illustration_kind({'product_name': 'vitamin enhanced water beverage, lemonade'}) == 'water'


@pytest.mark.parametrize('number,unit,expected', [(355, 'ml', '355 毫升'), ('0.5', 'l', '0.5 升'),
                                               (200, 'g', '200 克')])
def test_explicit_structured_quantity_fallback(number, unit, expected):
    assert quantity_display({'product_quantity': number, 'product_quantity_unit': unit}) == expected
    assert quantity_display({'quantity': '500ml', 'product_quantity': number,
                             'product_quantity_unit': unit}) == '500 毫升'


@pytest.mark.parametrize('record', [{}, {'product_quantity': 355}, {'serving_size': '355ml'},
                                   {'product_quantity': True, 'product_quantity_unit': 'ml'},
                                   {'product_quantity': 'NaN', 'product_quantity_unit': 'ml'},
                                   {'product_quantity': -2, 'product_quantity_unit': 'g'}])
def test_missing_specs_are_not_guessed_from_serving_sizes(record):
    assert source_quantity(record) == ''
    assert '来源未提供规格' in quantity_display(record)


def test_reading_aid_does_not_replace_candidate_source_name_or_invent_weight():
    record = product()
    record.update(product_name='Sparkling water', quantity='', product_quantity=355, product_quantity_unit='ml')
    before = deepcopy(record)
    name_display(record)
    preview = candidate_preview(record, 'OFF-TEST', 'V1')
    assert record == before
    assert next(r['raw_value'] for r in preview['rows'] if r['field_key'] == 'product_name') == 'Sparkling water'
    assert not any(r['field_key'] == 'net_weight_g' for r in preview['rows'])
    record['product_quantity_unit'] = 'g'
    assert any(r['field_key'] == 'net_weight_g' and r['normalized'] == '355'
               for r in candidate_preview(record, 'OFF-TEST', 'V1')['rows'])


def test_other_language_front_image_and_generic_front_still_bind_barcode():
    base = 'https://images.openfoodfacts.org/images/products/611/126/696/2187/'
    record = {'code': '6111266962187', 'selected_images': {'front': {'display': {'de': base + 'front_de.1.400.jpg'}}}}
    assert product_image_urls(record) == [base + 'front_de.1.400.jpg']
    record['image_url'] = base + 'front_en.1.400.jpg'
    assert base + 'front_en.1.400.jpg' in product_image_urls(record)
    assert not product_image_urls({'code': '12345678', 'selected_images': record['selected_images']})
    assert not product_image_urls({'code': '6111266962187', 'image_url': base + 'ingredients_en.1.400.jpg'})
    assert not product_image_urls({'code': '6111266962187', 'image_url': 'https://[bad'})


def test_card_and_dialog_have_chinese_high_contrast_notes(repo, monkeypatch):
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR', str(repo.settings.runtime_dir))
    monkeypatch.setenv('QIANPIN_DB_PATH', str(repo.settings.db_path))
    sample = product()
    sample.update(product_name='Naturell Mineralwasser', quantity='', product_quantity=500, product_quantity_unit='ml')
    monkeypatch.setattr('services.food_facts_service.requests.get', lambda *a, **kw: Response({'products': [sample]}))
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20).run()
    app.button(key='catalog_load').click().run()
    assert not app.exception
    notes = [m.value for m in app.markdown if 'qp-chinese-name' in m.value]
    assert notes and all('#123a63' in n and '矿泉水' in n for n in notes)
    assert any('规格：500 毫升' in m.value for m in app.markdown)
    app.button(key='catalog_pick:0:3017620422003').click().run()
    assert not app.exception and app.session_state['food_preview_open']
    assert len([m for m in app.markdown if 'qp-chinese-name' in m.value]) == 2


def test_explicit_detail_refresh_keeps_barcode_and_resets_acknowledgment(repo, monkeypatch):
    monkeypatch.setenv('QIANPIN_RUNTIME_DIR', str(repo.settings.runtime_dir))
    monkeypatch.setenv('QIANPIN_DB_PATH', str(repo.settings.db_path))
    original = product()
    original.update(product_name='Sparkling water', quantity='')
    detailed = {**original, 'product_quantity': 355, 'product_quantity_unit': 'ml'}
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return Response({'product': detailed} if '/api/v3/product/' in url else {'products': [original]})
    monkeypatch.setattr('services.food_facts_service.requests.get', get)
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20).run()
    app.button(key='catalog_load').click().run()
    app.button(key='catalog_pick:0:3017620422003').click().run()
    acknowledgment = next(c for c in app.checkbox if c.label.startswith('已核对商品身份'))
    acknowledgment.check().run()
    app.button(key='refresh_food_product').click().run()
    assert not app.exception and len(calls) == 2
    assert calls[-1].endswith('/api/v3/product/3017620422003')
    assert app.session_state['food_preview_product']['product_quantity'] == 355
    assert not next(c for c in app.checkbox if c.label.startswith('已核对商品身份')).value
    assert not repo.products()
