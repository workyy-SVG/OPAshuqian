"""Shared factual checks with sentence locations; no semantic truth claims."""
import re
from decimal import Decimal
from repository import BusinessError
from services.unit_service import QUANTITY_PATTERN, grams


def expression_findings(title: str, body: str, snapshot: dict) -> list[dict]:
    """Review hints, separate from hard factual gates; a lexicon is not a legal review."""
    source = '\n'.join(str(f['value']) for f in snapshot['facts'])
    categories = {
        '主观描述': ('精选', '醇厚', '香辣', '鲜美', '顶级', '优质', '天然', '健康', '纯正'),
        '功效表达': ('降血糖', '降血压', '增强免疫力', '治疗', '治愈', '减肥', '养胃'),
        '绝对化表达': ('最好', '最佳', '第一', '百分百', '100%', '零风险', '绝对'),
    }
    findings = []
    for section, text in (('title', title), ('body', body)):
        for category, words in categories.items():
            for word in words:
                if category == '主观描述' and word in source:
                    continue
                for match in re.finditer(re.escape(word), text):
                    findings.append({'section': section, 'start': match.start(), 'end': match.end(),
                                     'sentence': _sentence(text, match.start(), match.end()),
                                     'message': f'请人工核对{category}“{word}”：' +
                                     ('当前确认快照未提供该表述。' if word not in source else '来源包含该词，仍需审核表达是否适用。')})
    return findings


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
