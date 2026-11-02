"""One unit vocabulary for import normalization and generated/manual text."""
import re
from decimal import Decimal

WEIGHT_FACTORS = {'mg': Decimal('.001'), '毫克': Decimal('.001'), 'g': Decimal(1), '克': Decimal(1),
                  'kg': Decimal(1000), '千克': Decimal(1000), '公斤': Decimal(1000), '斤': Decimal(500), '两': Decimal(50)}
WEIGHT_UNITS = r'mg|kg|毫克|千克|公斤|g|克|斤|两'
WEIGHT_PATTERN = re.compile(rf'(?<![\w.])(-?\d+(?:\.\d+)?)\s*({WEIGHT_UNITS})(?![a-zA-Z])', re.I)
# Chinese prose has no spaces between words, so the left boundary must allow Han characters.
QUANTITY_PATTERN = re.compile(rf'(?<![a-zA-Z\d.])(-?\d+(?:\.\d+)?)\s*({WEIGHT_UNITS}|元)(?![a-zA-Z])', re.I)


def grams(number: str, unit: str) -> Decimal:
    return Decimal(number) * WEIGHT_FACTORS[unit.lower()]


def normalize_weight(raw: str) -> str:
    match = re.fullmatch(rf'(\d+(?:\.\d+)?)\s*({WEIGHT_UNITS})?', raw.strip(), re.I)
    if not match:
        raise ValueError('净含量请填写正数及克、千克、毫克、斤或两等明确重量单位。')
    result = grams(match[1], match[2] or 'g')
    if result <= 0 or result > 1000000000:
        raise ValueError('净含量必须大于0，且在合理范围内。')
    return format(result.normalize(), 'f')
