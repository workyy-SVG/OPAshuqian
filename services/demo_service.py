"""Opt-in public sandboxes; business databases never contain shared quota state."""
import os
import re
from config import Settings


def public_demo() -> bool:
    return os.environ.get('QIANPIN_PUBLIC_DEMO', '').lower() == 'true'


def live_models_enabled() -> bool:
    return os.environ.get('QIANPIN_LIVE_MODELS_ENABLED', 'false' if public_demo() else 'true').lower() == 'true'


def demo_settings(base: Settings, session_id: str, workspace_id: str) -> Settings:
    for value in (session_id, workspace_id):
        if not re.fullmatch(r'[a-f0-9]{32}', value):
            raise ValueError('无效的演示会话编号。')
    root = base.runtime_dir / 'demo-sessions' / session_id / workspace_id
    return Settings(root, root / 'qianpin.sqlite3')


def quota_settings(base: Settings) -> Settings:
    root = base.runtime_dir / 'model-quotas'
    return Settings(root, root / 'quota.sqlite3')


def seed_demo(repo) -> None:
    from config import ROOT
    from services.import_service import commit_import, preview_import
    commit_import(repo, preview_import((ROOT / 'samples/products.csv').read_bytes()), '拟制演示样例.csv')
