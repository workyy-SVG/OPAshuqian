"""Rotated JSON events with strict field allowlisting and no free-form payloads."""
from functools import wraps
import hashlib
import inspect
import json
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import re
import threading
import time
import uuid

_lock = threading.Lock()
_loggers: dict[str, logging.Logger] = {}


def audit_event(runtime_dir: Path, event: str, result: str, **fields) -> None:
    safe = {'event': event, 'result': result, 'timestamp': time.time()}
    for key in ('request_id', 'error_code'):
        value = fields.get(key)
        if isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}', value):
            safe[key] = value
    for key in ('duration_ms', 'job_id', 'content_id', 'fact_id', 'attempts', 'status_code'):
        value = fields.get(key)
        if type(value) in (int, float):
            safe[key] = value
    if fields.get('operator'):
        safe['actor_hash'] = hashlib.sha256(str(fields['operator']).encode()).hexdigest()[:20]
    try:
        folder = runtime_dir / 'logs'
        folder.mkdir(parents=True, exist_ok=True)
        name = str(folder.resolve())
        with _lock:
            logger = _loggers.get(name)
            if logger is None:
                logger = logging.getLogger('qianpin.audit.' + hashlib.sha256(name.encode()).hexdigest())
                logger.setLevel(logging.INFO)
                logger.propagate = False
                handler = TimedRotatingFileHandler(folder / 'events.jsonl', when='midnight', backupCount=14, encoding='utf-8', utc=True)
                handler.setFormatter(logging.Formatter('%(message)s'))
                logger.addHandler(handler)
                _loggers[name] = logger
            try:
                logger.info(json.dumps(safe, ensure_ascii=True))
            finally:
                # Avoid holding open files for short-lived/temporary databases on Windows.
                for item in logger.handlers:
                    item.close()
    except OSError:
        # Logs are supplementary; database audit records remain authoritative.
        logging.getLogger('qianpin').warning('audit_log_unavailable')


def audited(event: str):
    def decorate(function):
        signature = inspect.signature(function)
        @wraps(function)
        def run(*args, **kwargs):
            arguments = signature.bind(*args, **kwargs).arguments
            repo = arguments['repo']
            start = time.monotonic()
            fields = {'request_id': uuid.uuid4().hex, 'operator': arguments.get('operator')}
            try:
                result = function(*args, **kwargs)
            except Exception as exc:
                audit_event(repo.settings.runtime_dir, event, 'failed', **fields,
                            error_code=getattr(exc, 'code', 'internal_error'), duration_ms=round((time.monotonic()-start)*1000, 2))
                raise
            audit_event(repo.settings.runtime_dir, event, 'succeeded', **fields,
                        duration_ms=round((time.monotonic()-start)*1000, 2))
            return result
        return run
    return decorate
