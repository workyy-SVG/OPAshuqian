import sqlite3
import pytest
from config import ROOT
from repository import Repository, BusinessError
from services.migration_service import migrate


def test_fresh_and_repeated_initialization(repo):
    with repo.connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2
        assert db.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0] == 2
    repo.add_product('old', 'V1')
    repo.initialize()
    assert len(repo.products()) == 1
    assert not list((repo.settings.runtime_dir / 'backups').glob('*'))


def test_legacy_database_migrates_without_losing_rows(tmp_path):
    from config import Settings
    path = tmp_path / 'legacy.sqlite3'
    db = sqlite3.connect(path)
    db.executescript((ROOT / 'schema.sql').read_text(encoding='utf-8'))
    db.execute("INSERT INTO product_versions(brand_code,sku,version) VALUES('DEMO','001','V1')")
    db.commit()
    db.close()
    repo = Repository(Settings(tmp_path, path))
    repo.initialize()
    assert repo.products()[0]['sku'] == '001'
    backups = list((tmp_path / 'backups').glob('pre-migration*.sqlite3'))
    assert len(backups) == 1
    backup = sqlite3.connect(backups[0])
    try:
        assert backup.execute('PRAGMA user_version').fetchone()[0] == 0
        assert backup.execute('SELECT COUNT(*) FROM product_versions').fetchone()[0] == 1
    finally:
        backup.close()


def test_failed_increment_rolls_back_entire_upgrade(repo, tmp_path):
    with repo.connect() as db:
        db.execute('DROP INDEX ix_content_product')
        db.execute('DROP INDEX ix_content_logical_latest')
        db.execute('DROP INDEX ix_events_product')
        db.execute('DROP INDEX ix_jobs_product')
        db.execute('DELETE FROM schema_migrations WHERE version=2')
        db.execute('PRAGMA user_version=1')
        migrations = tmp_path / 'migrations'
        migrations.mkdir()
        (migrations / '002_broken.sql').write_text('CREATE TABLE must_rollback(id INTEGER);\nINSERT INTO no_such_table VALUES(1);\n', encoding='utf-8')
        with pytest.raises(sqlite3.OperationalError):
            migrate(db, repo.settings.db_path, repo.settings.runtime_dir, migrations)
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='must_rollback'").fetchone()


def test_future_and_incompatible_schema_fail_closed(repo):
    with repo.connect() as db:
        db.execute('PRAGMA user_version=999')
    with pytest.raises(BusinessError, match='版本'):
        repo.initialize()
