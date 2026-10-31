import pytest
from config import ROOT
from repository import BusinessError
from services.import_service import normalize_value, preview_import, commit_import


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
