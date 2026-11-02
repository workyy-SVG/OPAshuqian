import pytest
from services.import_service import normalize_value
from services.text_check_service import text_findings, text_issues
from services.content_service import template_result
from services.fact_service import build_snapshot
from services.llm_client import validate_result, ModelError
from tests.conftest import confirmed


@pytest.mark.parametrize('raw,expected', [('250mg','.25'), ('250毫克','.25'), ('2斤','1000'), ('4两','200'), ('0.2KG','200')])
def test_shared_unit_normalization(raw, expected):
    from decimal import Decimal
    assert Decimal(normalize_value('net_weight_g', raw)) == Decimal(expected)


def test_unit_checks_and_sentence_locations(repo):
    p = confirmed(repo)
    snapshot = build_snapshot(repo, p)['snapshot']
    assert not text_issues('拟制辣椒酱', '净含量4两，价格12元。', snapshot)
    findings = text_findings('拟制辣椒酱', '欢迎了解。净含量250毫克。售价12元。', snapshot)
    assert findings[0]['sentence'] == '净含量250毫克。'
    assert len(findings) == 1
    assert text_issues('拟制辣椒酱', '净含量250mg，价格12元。', snapshot)
    assert text_issues('拟制辣椒酱', '净含量200grams，价格12元。', snapshot)
    result = template_result(snapshot)
    result['body'] = '净含量4两，价格12元。'
    assert validate_result(result, snapshot)
    result['body'] = '净含量250mg，价格12元。'
    with pytest.raises(ModelError):
        validate_result(result, snapshot)
