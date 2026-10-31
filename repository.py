"""SQLite access and transaction boundary shared by services."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from config import ROOT, Settings, BRAND_CODE


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class BusinessError(ValueError):
    def __init__(self, message, code="validation"):
        super().__init__(message)
        self.code = code


class Repository:
    def __init__(self, settings=None):
        self.settings = settings or Settings.from_env()

    @contextmanager
    def connect(self, write=False):
        self.settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.settings.db_path, isolation_level=None, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.execute("COMMIT")
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def initialize(self):
        self.settings.runtime_dir.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))

    def all(self, sql, params=()):
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, params).fetchall()]

    def one(self, sql, params=()):
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def products(self):
        return self.all("SELECT * FROM product_versions ORDER BY sku,version,id")

    def add_product(self, sku, version, brand_code=BRAND_CODE):
        if not sku.strip() or not version.strip():
            raise BusinessError("SKU 和产品版本不能为空。")
        if max(len(sku), len(version)) > 80:
            raise BusinessError("SKU 和产品版本最长 80 个字符。")
        with self.connect(write=True) as db:
            db.execute("INSERT OR IGNORE INTO product_versions(brand_code,sku,version) VALUES(?,?,?)",
                       (brand_code, sku.strip(), version.strip()))
            return db.execute("SELECT id FROM product_versions WHERE brand_code=? AND sku=? AND version=?",
                              (brand_code, sku.strip(), version.strip())).fetchone()[0]
