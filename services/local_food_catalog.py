"""Curated Chinese food ideas for discovery, never treated as packaging facts."""
from typing import Any


FOODS: tuple[dict[str, str], ...] = (
    {'name': '贵州糟辣椒', 'category': '贵州调味', 'region': '贵州', 'kind': '辣椒调味品', 'note': '适合用于炒菜、蘸水和地方风味菜品。'},
    {'name': '贵州油辣椒', 'category': '贵州调味', 'region': '贵州', 'kind': '辣椒调味品', 'note': '常见佐餐调味方向，可进一步区分豆豉、鸡辣椒等口味。'},
    {'name': '红酸汤底料', 'category': '贵州调味', 'region': '黔东南', 'kind': '复合调味料', 'note': '适合酸汤火锅、酸汤鱼等菜品的产品方向。'},
    {'name': '独山盐酸菜', 'category': '贵州调味', 'region': '黔南·独山', 'kind': '腌制蔬菜', 'note': '可作为佐餐、炒制或地方风味配菜方向。'},
    {'name': '花溪牛肉粉', 'category': '贵州主食', 'region': '贵阳·花溪', 'kind': '米粉', 'note': '可做鲜食、半成品或冲泡型米粉产品。'},
    {'name': '遵义羊肉粉', 'category': '贵州主食', 'region': '遵义', 'kind': '米粉', 'note': '适合拆分为米粉、汤料和辣椒配料的组合产品。'},
    {'name': '水城羊肉粉', 'category': '贵州主食', 'region': '六盘水·水城', 'kind': '米粉', 'note': '贵州地方米粉方向，具体口味与包装信息需按实物记录。'},
    {'name': '肠旺面', 'category': '贵州主食', 'region': '贵阳', 'kind': '面食', 'note': '可探索鲜食套餐或方便型地方风味面食。'},
    {'name': '威宁荞酥', 'category': '贵州零食', 'region': '毕节·威宁', 'kind': '糕点', 'note': '苦荞风味糕点方向，适合礼盒或单份包装。'},
    {'name': '青岩玫瑰糖', 'category': '贵州零食', 'region': '贵阳·青岩', 'kind': '糖果', 'note': '玫瑰风味糖果方向，可用于地方特色伴手礼选品。'},
    {'name': '波波糖', 'category': '贵州零食', 'region': '贵州', 'kind': '糖果', 'note': '地方特色糖果方向，实际原料和过敏原以包装为准。'},
    {'name': '贵州豆腐干', 'category': '贵州零食', 'region': '贵州', 'kind': '豆制品', 'note': '可按香辣、卤香等口味继续细分。'},
    {'name': '刺梨汁', 'category': '贵州饮品', 'region': '贵州', 'kind': '果汁饮品', 'note': '贵州特色水果饮品方向，不在目录中预设营养或功效信息。'},
    {'name': '刺梨原浆', 'category': '贵州饮品', 'region': '贵州', 'kind': '果蔬制品', 'note': '适合做原浆、复合果汁等产品方向，浓度以具体包装为准。'},
    {'name': '贵州苦荞茶', 'category': '贵州饮品', 'region': '贵州', 'kind': '代用茶', 'note': '适合袋泡、罐装或礼盒产品方向。'},
    {'name': '贵州腊肉', 'category': '贵州肉制品', 'region': '贵州', 'kind': '腌腊肉制品', 'note': '地方腌腊风味方向，产地、保存方式和保质期须按包装核对。'},
    {'name': '贵州香肠', 'category': '贵州肉制品', 'region': '贵州', 'kind': '腌腊肉制品', 'note': '可按麻辣、广味等口味继续细分。'},
    {'name': '折耳根调味包', 'category': '贵州调味', 'region': '贵州', 'kind': '复合调味料', 'note': '适合蘸水、凉拌等风味方向，具体配方以产品为准。'},
    {'name': '酸汤火锅底料', 'category': '贵州调味', 'region': '贵州', 'kind': '火锅底料', 'note': '贵州酸汤风味产品方向，可继续区分红酸汤、白酸汤。'},
    {'name': '贵州辣子鸡调料', 'category': '贵州调味', 'region': '贵州', 'kind': '复合调味料', 'note': '地方菜调味产品方向，不预设具体品牌或配料。'},
    {'name': '桂林米粉', 'category': '中国主食', 'region': '广西', 'kind': '米粉', 'note': '中国地方米粉选品参考。'},
    {'name': '重庆小面', 'category': '中国主食', 'region': '重庆', 'kind': '面食', 'note': '可做鲜食或方便型地方风味面食。'},
    {'name': '云南鲜花饼', 'category': '中国零食', 'region': '云南', 'kind': '糕点', 'note': '地方糕点及伴手礼选品参考。'},
    {'name': '四川豆瓣酱', 'category': '中国调味', 'region': '四川', 'kind': '酱类调味品', 'note': '中式烹饪调味品选品参考。'},
)


def categories() -> list[str]:
    return ['全部', *dict.fromkeys(item['category'] for item in FOODS)]


def search_foods(category: str = '全部', keyword: str = '') -> list[dict[str, Any]]:
    term = keyword.strip().casefold()
    return [dict(item) for item in FOODS
            if (category == '全部' or item['category'] == category)
            and (not term or any(term in item[field].casefold()
                                 for field in ('name', 'category', 'region', 'kind', 'note')))]
