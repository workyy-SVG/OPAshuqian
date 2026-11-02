import pytest
from config import ROOT
from repository import BusinessError
from services.import_service import normalize_value, preview_import, commit_import, add_manual_batch


def test_units_and_decimal():
    assert normalize_value("net_weight_g", "200g") == normalize_value("net_weight_g", "0.2kg") == "200"
    assert normalize_value("price_cent", "0.29元") == "29"
    for value in ("十二元", "12.001", "-1", "NaN"):
        with pytest.raises(BusinessError):
            normalize_value("price_cent", value)
    with pytest.raises(BusinessError):
        normalize_value("net_weight_g", "0g")


def test_import_idempotent_and_errors(repo):
    preview = preview_import((ROOT / "samples/products.csv").read_bytes())
    assert not preview["errors"]
    result = commit_import(repo, preview, "../../evil.csv")
    assert result["errors"] == 2
    assert result["duplicates"] == 1
    assert {p['sku'] for p in result['products']} == {'P001', 'P002'}
    assert result['product_ids'] == [p['id'] for p in result['products']]
    count = len(repo.all("SELECT * FROM observations"))
    assert commit_import(repo, preview)["reused"]
    assert len(repo.all("SELECT * FROM observations")) == count
    assert len(repo.products()) == 3
    assert repo.one("SELECT original_name FROM sources")["original_name"] == "evil.csv"
    assert repo.one("SELECT * FROM observations WHERE raw='0.2kg'")["normalized"] == "200"
    repo.initialize()
    assert len(repo.all("SELECT * FROM observations")) == count


def test_encoding_headers_and_preview_tamper(repo):
    with pytest.raises(BusinessError):
        preview_import("中文".encode("gb18030"))
    assert preview_import(b"sku,raw_value\n001,a")["errors"]
    preview = preview_import((ROOT / "samples/products.csv").read_bytes())
    preview["rows"][0]["normalized"] = "篡改"
    commit_import(repo, preview)
    assert repo.one("SELECT normalized FROM observations WHERE row_no=2")["normalized"] == "山野辣椒酱"


def test_streaming_row_limit_is_enforced(monkeypatch):
    import services.import_service as importer
    monkeypatch.setattr(importer,'MAX_IMPORT_ROWS',1)
    data=(ROOT/'samples/products.csv').read_bytes()
    with pytest.raises(BusinessError) as error:
        preview_import(data)
    assert error.value.code == 'row_limit'


def test_chinese_wide_template_and_manual_batch(repo):
    data = 'SKU,产品版本,商品名称,净含量,零售价格,来源说明\n001,V1,刺梨汁,200g,12.00,包装标签\n'.encode('utf-8-sig')
    preview = preview_import(data)
    assert not preview['errors'] and len(preview['rows']) == 3
    result = commit_import(repo, preview, '中文模板.csv')
    product_id = result['product_ids'][0]
    rows = repo.all('SELECT * FROM observations WHERE product_id=?', (product_id,))
    assert {r['field'] for r in rows} == {'product_name','net_weight_g','price_cent'}
    added = add_manual_batch(repo, product_id, {'product_name':'刺梨原浆','net_weight_g':'250g'}, '新包装', '包装更新', '测试员')
    assert added['candidates'] == 2
    assert len(repo.all('SELECT * FROM observation_actions')) == 2
