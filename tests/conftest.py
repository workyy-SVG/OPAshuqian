import pytest
from config import Settings
from repository import Repository
from services.import_service import add_manual
from services.fact_service import confirm_fact


@pytest.fixture
def repo(tmp_path):
    result = Repository(Settings(tmp_path, tmp_path / "test.sqlite3"))
    result.initialize()
    return result


def confirmed(repo, sku="P001", version="V1", price="12.00", context="retail"):
    product = repo.add_product(sku, version)
    for field, raw, scope in (("product_name", "拟制辣椒酱", "general"), ("net_weight_g", "200g", "general"), ("price_cent", price, context)):
        obs = add_manual(repo, product, field, raw, scope, "拟制测试依据", "测试补录", "测试员")
        confirm_fact(repo, product, obs, None, "测试员", "已核对拟制来源")
    return product
