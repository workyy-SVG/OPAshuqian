"""Conservative category illustrations, never inferred from ingredients or the open tab."""
import re

# Row-major positions in the reviewed 4 x 4 illustration sheet.
ILLUSTRATIONS = {
    'milk': ('奶类饮品', 0, 0), 'yogurt': ('酸奶', 1, 0), 'cheese': ('奶酪', 2, 0),
    'vegetables': ('蔬菜', 3, 0), 'fruit': ('水果', 0, 1), 'water': ('饮用水', 1, 1),
    'juice': ('果汁', 2, 1), 'tea': ('茶饮', 3, 1), 'soda': ('碳酸饮料', 0, 2),
    'meat': ('肉类', 1, 2), 'fish': ('水产', 2, 2), 'eggs': ('蛋类', 3, 2),
    'snacks': ('零食', 0, 3), 'condiments': ('调味品', 1, 3), 'meals': ('餐食', 2, 3),
    'powder': ('粉状食品', 3, 3),
}

# Composite foods precede ingredients: milk chocolate is not milk; tomato juice is not vegetables.
NAME_RULES = [
    ('snacks', r'饼干|曲奇|巧克力(?!(?:味|风味)?(?:牛奶|酸奶|奶昔))|奶糖|薯片|蛋糕|糕点|面包|\bchocolate\b(?!\s+(?:milk|yogurt|yoghurt))|\b(biscuits?|cookies?|crackers?|chips|cakes?|bread)\b'),
    ('powder', r'奶粉|乳粉|蛋白粉|面粉|白糖|砂糖|\b(milk powder|protein powder|flour|sugar)\b'),
    ('meals', r'方便面|泡面|面条|米饭|炒饭|饺子|披萨|意面|\b(noodles?|pasta|pizza|dumplings?|ready meals?)\b'),
    ('condiments', r'酱|醋|调味|食用油|植物油|茶油|\b(sauce|ketchup|seasoning|condiment|vinegar)\b'),
    ('tea', r'奶茶|茶饮|冰茶|红茶|绿茶|乌龙茶|茶叶|\b(tea|matcha)\b'),
    ('juice', r'果汁|蔬菜汁|番茄汁|橙汁|苹果汁|\bjuice\b'),
    ('yogurt', r'酸奶|酸乳|\b(yogurt|yoghurt|yogourt)\b'),
    ('cheese', r'奶酪|芝士|干酪|\b(cheese|fromage)\b'),
    ('soda', r'汽水|可乐|碳酸饮料|\b(soda|cola|lemonade)\b'),
    ('milk', r'牛奶|纯奶|鲜奶|全脂奶|脱脂奶|豆奶|燕麦奶|椰奶|\b(milk|lait|milkshake)\b'),
    ('water', r'饮用水|矿泉水|纯净水|苏打水|气泡水|\b(water|eau)\b'),
    ('vegetables', r'蔬菜|白菜|生菜|菠菜|西兰花|胡萝卜|番茄|黄瓜|土豆|洋葱|芹菜|青椒|茄子|\b(vegetables?|carrots?|broccoli|spinach|lettuce|tomatoes|tomato|cucumber|onion|potato)\b'),
    ('fruit', r'水果|苹果|橙子|香蕉|草莓|葡萄|柠檬|\b(fruit|apple|orange|banana|strawberry|grapes?|lemon)\b'),
    ('fish', r'鱼|虾|蟹|水产|\b(fish|salmon|tuna|shrimp|seafood)\b'),
    ('meat', r'牛肉|猪肉|鸡肉|羊肉|肉排|\b(beef|pork|chicken|steak|lamb|meat)\b'),
    ('eggs', r'鸡蛋|鸭蛋|鹌鹑蛋|鲜蛋|\beggs?\b'),
]

TAG_RULES = {
    'en:milks': 'milk', 'en:plant-milks': 'milk', 'en:yogurts': 'yogurt', 'en:cheeses': 'cheese',
    'en:vegetables': 'vegetables', 'en:fruits': 'fruit', 'en:waters': 'water',
    'en:fruit-juices': 'juice', 'en:vegetable-juices': 'juice', 'en:iced-teas': 'tea', 'en:teas': 'tea',
    'en:sodas': 'soda', 'en:meats': 'meat', 'en:seafood': 'fish', 'en:eggs': 'eggs',
    'en:snacks': 'snacks', 'en:condiments': 'condiments', 'en:prepared-meals': 'meals',
    'en:milk-powders': 'powder',
}


def illustration_kind(product: dict) -> str | None:
    kinds = set()
    for key in ('product_name_zh', 'product_name'):
        name = product.get(key)
        if not isinstance(name, str):
            continue
        for kind, pattern in NAME_RULES:
            if re.search(pattern, name, re.IGNORECASE):
                kinds.add(kind)
                break
    # Contradictory names must not silently choose one illustration.
    if len(kinds) == 1:
        return next(iter(kinds))
    if kinds:
        return None
    tags = product.get('categories_tags')
    if isinstance(tags, list):
        tag_kinds = {TAG_RULES[t] for t in tags if isinstance(t, str) and t in TAG_RULES}
        if len(tag_kinds) == 1:
            return next(iter(tag_kinds))
    return None
