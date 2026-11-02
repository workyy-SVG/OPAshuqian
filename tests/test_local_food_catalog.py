from services.local_food_catalog import categories, search_foods


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
