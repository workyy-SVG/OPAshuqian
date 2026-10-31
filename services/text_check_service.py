"""Shared factual checks with sentence locations; no semantic truth claims."""
import re
from decimal import Decimal
from repository import BusinessError
from services.unit_service import QUANTITY_PATTERN, grams


def _sentence(text: str, start: int, end: int) -> str:
    left = max((m.end() for m in re.finditer(r'[。！？\n]', text[:start])), default=0)
    right_match = re.search(r'[。！？\n]', text[end:])
    right = end + right_match.end() if right_match else len(text)
    return text[left:right].strip()


def text_findings(title: str, body: str, snapshot: dict) -> list[dict]:
    values = {f['field']: f['value'] for f in snapshot['facts']}
    findings = []
    has_weight = False
    def add(message, section, text, start=0, end=0):
        findings.append({'message': message, 'section': section, 'start': start, 'end': end,
                         'sentence': _sentence(text, start, end) if end else ''})
    if values.get('product_name', '') not in title + '\n' + body:
        add('请保留已确认的产品名称。', 'body', body)
    for section, text in [('title', title), ('body', body)]:
        quantities = [(m.start(), m.end(), m[1], m[2]) for m in QUANTITY_PATTERN.finditer(text)]
        quantities += [(m.start(), m.end(), m[1], '元') for m in re.finditer(r'[¥￥]\s*(-?\d+(?:\.\d+)?)', text)]
        for start, end, number, unit in quantities:
            if unit == '元':
                amount = Decimal(number)
                expected = Decimal(values['price_cent']) / 100 if 'price_cent' in values else None
                if expected is None:
                    add('本次依据未加入价格，请删除文案中的金额，或重新生成含价格的内容。', section, text, start, end)
                elif amount != expected:
                    add(f'文案金额 {number} 元与确认价格 {expected:.2f} 元不一致，请修改正文。', section, text, start, end)
            else:
                amount = grams(number, unit)
                expected = Decimal(values['net_weight_g'])
                has_weight = True
                if amount != expected:
                    add(f'文案净含量 {number}{unit} 与确认净含量 {expected} 克不一致，请修改正文。', section, text, start, end)
    if not has_weight:
        add('请明确写出已确认的净含量及单位，例如200克。', 'body', body)
    return findings


def text_issues(title: str, body: str, snapshot: dict) -> list[str]:
    return list(dict.fromkeys(f['message'] for f in text_findings(title, body, snapshot)))


def assert_text_matches(title: str, body: str, snapshot: dict) -> None:
    issues = text_issues(title, body, snapshot)
    if issues:
        raise BusinessError('；'.join(issues), 'body_fact_mismatch')
