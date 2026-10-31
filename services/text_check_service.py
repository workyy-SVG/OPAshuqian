"""Deterministic checks of explicit facts, shared by review and export."""
import re
from decimal import Decimal
from repository import BusinessError


def text_issues(title, body, snapshot):
    values = {f['field']: f['value'] for f in snapshot['facts']}
    text = title + '\n' + body
    issues = []
    if values.get('product_name', '') not in text:
        issues.append('请保留已确认的产品名称。')
    has_weight = False
    quantities = re.findall(r'(?<![\d.])(-?\d+(?:\.\d+)?)\s*(kg|千克|公斤|g|克|元)', text, re.I)
    quantities += [(n, '元') for n in re.findall(r'[¥￥]\s*(-?\d+(?:\.\d+)?)', text)]
    for number, unit in quantities:
        amount = Decimal(number)
        if unit == '元':
            expected = Decimal(values['price_cent']) / 100 if 'price_cent' in values else None
            if expected is None:
                issues.append('本次依据未加入价格，请删除文案中的金额，或重新生成含价格的内容。')
            elif amount != expected:
                issues.append(f'文案金额 {number} 元与确认价格 {expected:.2f} 元不一致，请修改正文。')
        else:
            amount *= 1000 if unit.lower() in ('kg', '千克', '公斤') else 1
            expected = Decimal(values['net_weight_g'])
            has_weight = True
            if amount != expected:
                issues.append(f'文案净含量 {number}{unit} 与确认净含量 {expected} 克不一致，请修改正文。')
    if not has_weight:
        issues.append('请明确写出已确认的净含量及单位，例如200克。')
    return list(dict.fromkeys(issues))


def assert_text_matches(title, body, snapshot):
    issues = text_issues(title, body, snapshot)
    if issues:
        raise BusinessError('；'.join(issues), 'body_fact_mismatch')
