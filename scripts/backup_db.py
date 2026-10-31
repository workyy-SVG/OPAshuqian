"""Use SQLite's online backup API, rather than copying live WAL files."""
import argparse
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from repository import Repository, BusinessError


def backup_db(repo, destination=None):
    if not repo.settings.db_path.is_file():
        raise BusinessError("数据库尚不存在，请先初始化。")
    destination = Path(destination) if destination else repo.settings.runtime_dir / "backups" / (
        datetime.now(timezone.utc).strftime("qianpin-%Y%m%dT%H%M%S-") + uuid.uuid4().hex[:8] + ".sqlite3")
    if destination.exists():
        raise BusinessError("备份目标已存在，请使用新文件名。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    target = sqlite3.connect(destination)
    try:
        with repo.connect() as source:
            source.backup(target)
        if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise BusinessError("备份完整性检查未通过。")
    finally:
        target.close()
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="备份 SQLite 数据库；原始资料需同时保留 runtime/sources。")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    print(backup_db(Repository(), args.out))
