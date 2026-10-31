from repository import Repository
from config import Settings
from scripts.backup_db import backup_db
from scripts.restore_check import restore_check
from tests.conftest import confirmed
from tests.test_content import ready


def test_backup_restore_and_export(repo, tmp_path):
    p = confirmed(repo)
    cid = ready(repo, p)
    backup = backup_db(repo)
    result = restore_check(backup, tmp_path / "restored.sqlite3")
    assert result["integrity"] == "ok"
    assert result["counts"]["content_dependencies"] == 3
    assert result["counts"]["review_records"] == 2
    from services.content_service import export_content
    restored = Repository(Settings(tmp_path, tmp_path / "restored.sqlite3"))
    assert "12.00 元" in export_content(restored, cid, "恢复测试员")["text"]
