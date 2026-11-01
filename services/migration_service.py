"""Versioned, atomic migrations with a pre-upgrade online backup."""
import hashlib
import sqlite3
import uuid
import re
from pathlib import Path
from config import ROOT

LATEST_SCHEMA_VERSION = 3


def execute_sql(db: sqlite3.Connection, text: str) -> None:
    pending = ''
    for line in text.splitlines(keepends=True):
        pending += line
        if sqlite3.complete_statement(pending):
            db.execute(pending)
            pending = ''
    if pending.strip():
        raise ValueError('迁移SQL不完整。')


def validate_baseline(db: sqlite3.Connection, baseline: str) -> None:
    expected = sqlite3.connect(':memory:')
    try:
        expected.executescript(baseline)
        tables = expected.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        for (table,) in tables:
            required = {r[1]: tuple(r[1:]) for r in expected.execute(f'PRAGMA table_info("{table}")')}
            actual = {r[1]: tuple(r[1:]) for r in db.execute(f'PRAGMA table_info("{table}")')}
            if any(actual.get(name) != definition for name, definition in required.items()):
                raise ValueError(f'旧库结构不符合基线：{table}。请先恢复备份或人工检查。')
            def unique_indexes(connection):
                result = set()
                for index in connection.execute(f'PRAGMA index_list("{table}")'):
                    if index[2]:
                        name = index[1].replace('"', '""')
                        columns = tuple(r[2] for r in connection.execute(f'PRAGMA index_info("{name}")'))
                        sql = connection.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name=?",(index[1],)).fetchone()[0] or ''
                        match = re.search(r'\bWHERE\b(.*)', sql, re.I | re.S)
                        predicate = re.sub(r'\s+', '', match[1]).lower() if match else ''
                        result.add((columns, bool(index[4]), predicate))
                return result
            if not unique_indexes(expected) <= unique_indexes(db):
                raise ValueError(f'旧库唯一约束不符合基线：{table}。')
            required_foreign = {tuple(r[2:]) for r in expected.execute(f'PRAGMA foreign_key_list("{table}")')}
            actual_foreign = {tuple(r[2:]) for r in db.execute(f'PRAGMA foreign_key_list("{table}")')}
            if not required_foreign <= actual_foreign:
                raise ValueError(f'旧库外键不符合基线：{table}。')
    finally:
        expected.close()


def migrate(db: sqlite3.Connection, db_path: Path, runtime_dir: Path, migrations_dir: Path | None = None) -> None:
    directory = migrations_dir or ROOT / 'migrations'
    baseline = (ROOT / 'schema.sql').read_text(encoding='utf-8')
    baseline_hash = hashlib.sha256(baseline.encode()).hexdigest()
    files = {int(p.name.split('_', 1)[0]): p for p in directory.glob('[0-9][0-9][0-9]_*.sql')}
    if len(files) != len(list(directory.glob('[0-9][0-9][0-9]_*.sql'))):
        raise ValueError('迁移文件的版本号重复。')
    if sorted(files) != list(range(2, LATEST_SCHEMA_VERSION + 1)):
        raise ValueError('迁移文件版本必须连续。')
    db.execute('BEGIN IMMEDIATE')
    try:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version > LATEST_SCHEMA_VERSION:
            raise ValueError('数据库版本比程序新，请更新程序，不要降级覆盖。')
        has_data = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()
        if version < LATEST_SCHEMA_VERSION and has_data:
            backup_dir = runtime_dir / 'backups'
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / f'pre-migration-v{version}-{uuid.uuid4().hex}.sqlite3'
            source = sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True)
            target = sqlite3.connect(backup)
            try:
                source.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('迁移前备份校验失败。')
            finally:
                target.close()
                source.close()
        if version == 0:
            if has_data:
                validate_baseline(db, baseline)
            else:
                execute_sql(db, baseline)
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY,name TEXT NOT NULL,checksum TEXT NOT NULL,applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        if version == 0:
            db.execute('INSERT INTO schema_migrations(version,name,checksum) VALUES(1,?,?)', ('schema.sql', baseline_hash))
            db.execute('PRAGMA user_version=1')
            version = 1
        for record in db.execute('SELECT version,checksum FROM schema_migrations'):
            number, checksum = record
            if number != 1 and number not in files:
                raise ValueError('迁移历史含未知版本。')
            expected = baseline_hash if number == 1 else hashlib.sha256(files[number].read_bytes()).hexdigest()
            if checksum != expected:
                raise ValueError('已应用迁移文件发生变化，请使用原文件或新增迁移。')
        applied = [r[0] for r in db.execute('SELECT version FROM schema_migrations ORDER BY version')]
        if applied != list(range(1, version + 1)):
            raise ValueError('数据库版本与迁移历史不一致，请检查备份。')
        for number in range(version + 1, LATEST_SCHEMA_VERSION + 1):
            path = files[number]
            execute_sql(db, path.read_text(encoding='utf-8'))
            db.execute('INSERT INTO schema_migrations(version,name,checksum) VALUES(?,?,?)',
                       (number, path.name, hashlib.sha256(path.read_bytes()).hexdigest()))
            db.execute(f'PRAGMA user_version={number}')
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('迁移后的外键检查失败。')
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK')
        raise
