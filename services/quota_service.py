"""Atomic per-provider daily API request limits, reset on China Standard Time."""
from datetime import datetime
from zoneinfo import ZoneInfo

from repository import BusinessError, now

DAILY_API_LIMIT = 100
SESSION_API_LIMIT = 3
PROVIDERS = ("deepseek", "qwen")
CHINA_TIME = ZoneInfo("Asia/Shanghai")


def usage_date(clock=None):
    current = clock() if clock else datetime.now(CHINA_TIME)
    if current.tzinfo is None:
        current = current.replace(tzinfo=CHINA_TIME)
    return current.astimezone(CHINA_TIME).date().isoformat()


def reserve_request(repo, provider, limit=DAILY_API_LIMIT, clock=None, session_id=None):
    """Reserve one outbound request before sending it; safe across concurrent sessions."""
    if provider not in PROVIDERS:
        raise BusinessError("未知模型提供方。", "invalid_provider")
    day = usage_date(clock)
    with repo.connect(write=True) as db:
        if session_id:
            db.execute('INSERT OR IGNORE INTO model_session_usage VALUES(?,?,0)', (session_id, day))
            changed = db.execute('''UPDATE model_session_usage SET request_count=request_count+1
                WHERE session_id=? AND usage_date=? AND request_count<?''',
                (session_id, day, SESSION_API_LIMIT)).rowcount
            if changed != 1:
                raise BusinessError('本会话今天的3次真实模型请求已用完，请使用模板模式。', 'session_quota_exceeded')
        db.execute("""INSERT OR IGNORE INTO model_daily_usage(provider,usage_date,request_count,updated_at)
                      VALUES(?,?,0,?)""", (provider, day, now()))
        changed = db.execute("""UPDATE model_daily_usage
            SET request_count=request_count+1,updated_at=?
            WHERE provider=? AND usage_date=? AND request_count<?""",
            (now(), provider, day, limit)).rowcount
        if changed != 1:
            raise BusinessError(f"该模型今天的 {limit} 次 API 调用额度已用完，请明天再试。", "daily_quota_exceeded")
        count = db.execute("SELECT request_count FROM model_daily_usage WHERE provider=? AND usage_date=?",
                           (provider, day)).fetchone()[0]
    return {"provider": provider, "date": day, "used": count, "remaining": limit-count, "limit": limit}


def session_quota_status(repo, session_id, clock=None):
    day = usage_date(clock)
    row = repo.one('SELECT request_count FROM model_session_usage WHERE session_id=? AND usage_date=?', (session_id, day))
    used = row['request_count'] if row else 0
    return {'used': used, 'remaining': max(0, SESSION_API_LIMIT-used), 'limit': SESSION_API_LIMIT}


def quota_status(repo, limit=DAILY_API_LIMIT, clock=None):
    day = usage_date(clock)
    rows = {row["provider"]: row["request_count"] for row in repo.all(
        "SELECT provider,request_count FROM model_daily_usage WHERE usage_date=?", (day,))}
    return {provider: {"date": day, "used": rows.get(provider, 0),
                       "remaining": max(0, limit-rows.get(provider, 0)), "limit": limit}
            for provider in PROVIDERS}
