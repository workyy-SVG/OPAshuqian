"""Bounded, atomic snapshots of successful public catalogue pages only."""
import hashlib
import json
import time
import uuid
import re
from pathlib import Path

FRESH_SECONDS = 3600
MAX_AGE_SECONDS = 7 * 86400


def snapshot_path(folder: Path, tag: str, page: int) -> Path:
    key = hashlib.sha256(f'v1:{tag}:{page}'.encode()).hexdigest()
    return folder / f'{key}.json'


def read_snapshot(folder: Path | None, tag: str, page: int) -> dict | None:
    if folder is None:
        return None
    try:
        path = snapshot_path(folder, tag, page)
        if path.stat().st_size > 2 * 1024 * 1024:
            return None
        data = json.loads(path.read_text(encoding='utf-8'))
        age = time.time() - data['saved_at']
        result = data['result']
        if (not 0 <= age <= MAX_AGE_SECONDS or data['tag'] != tag or result['page'] != page
                or not isinstance(result['products'], list) or len(result['products']) > 12
                or any(not isinstance(p, dict) or not re.fullmatch(r'[0-9]{8,14}', str(p.get('code', '')))
                       for p in result['products'])
                or not isinstance(result['has_next'], bool)):
            return None
        return {**result, 'saved_at': data['saved_at'], 'cached': True, 'stale': age > FRESH_SECONDS}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def write_snapshot(folder: Path | None, tag: str, result: dict) -> None:
    if folder is None:
        return
    temporary = None
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = snapshot_path(folder, tag, result['page'])
        temporary = folder / f'.{uuid.uuid4().hex}.tmp'
        temporary.write_text(json.dumps({'tag': tag, 'saved_at': result['saved_at'], 'result': result},
                                        ensure_ascii=False), encoding='utf-8')
        temporary.replace(path)
        snapshots = [p for p in folder.glob('*.json') if re.fullmatch(r'[a-f0-9]{64}\.json', p.name)]
        for old in sorted(snapshots, key=lambda p: p.stat().st_mtime, reverse=True)[128:]:
            old.unlink(missing_ok=True)
    except OSError:
        # A full/read-only disk must not hide a valid upstream response.
        pass
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
