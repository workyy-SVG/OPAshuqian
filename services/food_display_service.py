"""Read-only Chinese reading aids and explicit source quantities, never confirmed facts."""
import re
from decimal import Decimal, InvalidOperation
from services.product_illustration_service import illustration_kind, ILLUSTRATIONS

UNITS = {'g': '克', 'kg': '千克', 'mg': '毫克', 'ml': '毫升', 'l': '升', 'cl': '厘升',
         '克': '克', '千克': '千克', '毫克': '毫克', '毫升': '毫升', '升': '升'}


def source_quantity(product: dict) -> str:
    raw = product.get('quantity')
    if isinstance(raw, str) and raw.strip().casefold() not in ('', 'n/a', 'none', 'unknown', '未提供', '不详'):
        return raw.strip()
    number, unit = product.get('product_quantity'), product.get('product_quantity_unit')
    if isinstance(number, bool) or not isinstance(unit, str) or unit.lower().strip() not in UNITS:
        return ''
    try:
        value = Decimal(str(number))
        if value.is_finite() and Decimal('0.000001') <= value <= 1_000_000_000:
            return f'{format(value.normalize(), "f")} {unit.lower().strip()}'
    except InvalidOperation:
        pass
    return ''


def quantity_display(product: dict) -> str:
    raw = source_quantity(product)
    if not raw:
        return '来源未提供规格（可在导入后补录）'
    return re.sub(r'(\d+(?:\.\d+)?)\s*(kg|mg|ml|cl|g|l)\b',
                  lambda m: f'{m[1]} {UNITS[m[2].lower()]}', raw, flags=re.I)


def name_display(product: dict) -> dict[str, str]:
    original = product.get('product_name') or product.get('product_name_zh') or '来源未提供商品名称'
    original = str(original)
    chinese = product.get('product_name_zh')
    if isinstance(chinese, str) and re.search(r'[\u4e00-\u9fff]', chinese):
        return {'original': original, 'chinese': chinese.strip(), 'label': '中文名（来源提供）'}
    if re.search(r'[\u4e00-\u9fff]', original):
        return {'original': original, 'chinese': original, 'label': '中文名（来源提供）'}
    generic = product.get('generic_name_zh')
    if isinstance(generic, str) and re.search(r'[\u4e00-\u9fff]', generic):
        return {'original': original, 'chinese': generic.strip(), 'label': '中文品类说明（来源提供，非完整商品名）'}
    name = original.casefold()
    tags = product.get('categories_tags')
    tags = tags if isinstance(tags, list) else []
    kind = illustration_kind(product)
    water = bool(re.search(r'\b(water|seltzer|eau|voda)\b|mineralwasser', name)) or kind == 'water'
    if water:
        mineral = bool(re.search(r'mineral', name))
        sparkling = bool(re.search(r'\b(sparkling|seltzer|carbonated|gazirana)\b', name)) or 'en:carbonated-waters' in tags
        if re.search(r'\b(non[- ]carbonated|still water)\b', name):
            sparkling = False
        base = ('气泡' if sparkling else '') + ('矿泉水' if mineral else '饮用水')
        if sparkling and not mineral:
            base = '气泡水'
    else:
        base = ILLUSTRATIONS[kind][0] if kind else ''
    # Only explain words actually present. Do not translate brands or invent missing claims.
    flavors = []
    for pattern, translated in [(r'\blime\b', '青柠'), (r'\bwatermelon\b', '西瓜'),
                                 (r'\blemon zest\b', '柠檬皮'), (r'\blemon(?:ade)?\b', '柠檬'),
                                 (r'\bstrawberr(?:y|ies)\b', '草莓'), (r'\borange\b', '橙子'),
                                 (r'\bapple\b', '苹果')]:
        if re.search(pattern, name):
            flavors.append(translated)
    if flavors and kind == 'fruit':
        explanation = '、'.join(flavors) + '（名称词语参考，具体商品类型请核对）'
    elif flavors and kind == 'juice':
        explanation = '、'.join(flavors) + '汁'
    elif flavors and kind not in ('vegetables', 'meat', 'fish', 'eggs'):
        explanation = '、'.join(flavors) + ('风味' + base if base else '风味；商品类型待核对')
    else:
        explanation = base
    if explanation:
        label = '中文参考说明（非官方译名，需核对）'
    else:
        explanation = '来源未提供中文名，暂无法可靠翻译，请结合原名与实物核对'
        label = '中文说明'
    return {'original': original, 'chinese': explanation, 'label': label}
