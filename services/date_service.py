from datetime import datetime
from zoneinfo import ZoneInfo


def today_iso() -> str:
    return datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
