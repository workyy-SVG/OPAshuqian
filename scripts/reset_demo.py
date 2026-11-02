"""Create a fresh synthetic sandbox without deleting or replacing existing data."""
import argparse
import uuid
from pathlib import Path
from config import Settings
from repository import Repository
from services.demo_service import seed_demo


def reset_demo(destination: Path) -> Repository:
    destination.mkdir(parents=True, exist_ok=False)
    repo = Repository(Settings(destination.resolve(), destination.resolve() / 'qianpin.sqlite3'))
    repo.initialize()
    seed_demo(repo)
    return repo


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='创建统一拟制样例库；保留已有数据，不清除模型额度。')
    parser.add_argument('--out-dir', type=Path, default=Settings.from_env().runtime_dir / ('demo-reset-' + uuid.uuid4().hex))
    args = parser.parse_args()
    created = reset_demo(args.out_dir)
    print(f'拟制样例已准备：{created.settings.runtime_dir}')
    print('启动时将 QIANPIN_RUNTIME_DIR 设置为上述目录；不要同时设置旧的 QIANPIN_DB_PATH。')
