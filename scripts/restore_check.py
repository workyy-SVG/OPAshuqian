"""Restore to a new file and verify data. Never overwrites the running DB."""
import argparse
import sqlite3
from pathlib import Path
from repository import BusinessError


def restore_check(backup, destination):
    backup, destination = Path(backup).resolve(), Path(destination).resolve()
    if not backup.is_file() or destination.exists():
        raise BusinessError("备份不存在，或恢复目标已存在。请选择一个新路径。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(backup.as_uri() + "?mode=ro", uri=True)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
        integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_errors = target.execute("PRAGMA foreign_key_check").fetchall()
        if integrity != "ok" or foreign_errors:
            raise BusinessError("恢复后的数据库完整性或外键检查未通过。")
        counts = {name: target.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                  for name in ("product_versions", "sources", "observations", "fact_revisions", "content_revisions", "content_dependencies", "review_records")}
        return {"integrity": integrity, "counts": counts, "restored_path": str(destination)}
    finally:
        target.close()
        source.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("backup", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    import json
    print(json.dumps(restore_check(args.backup, args.destination), ensure_ascii=False, indent=2))
