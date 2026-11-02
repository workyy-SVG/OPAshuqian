from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import os
import random


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter: float = .25

    def __post_init__(self) -> None:
        if not (1 <= self.max_attempts <= 5 and 0 <= self.base_delay <= self.max_delay <= 30 and 0 <= self.jitter <= 2):
            raise ValueError('重试参数超出允许范围。')

    @classmethod
    def from_env(cls):
        return cls(int(os.environ.get('QIANPIN_RETRY_ATTEMPTS', 2)),
                   float(os.environ.get('QIANPIN_RETRY_BASE_DELAY', 1)),
                   float(os.environ.get('QIANPIN_RETRY_MAX_DELAY', 30)))

    def delay(self, attempt: int, retry_after: str | None = None, rng=None, now=None) -> float | None:
        if retry_after:
            try:
                wait = float(retry_after)
            except ValueError:
                try:
                    wait = (parsedate_to_datetime(retry_after) - (now or datetime.now(timezone.utc))).total_seconds()
                except (ValueError, TypeError, OverflowError):
                    wait = -1
            if wait >= 0:
                # Do not retry earlier than the server requested.
                return wait if wait <= self.max_delay else None
        return min(self.max_delay, self.base_delay * 2 ** (attempt - 1) + (rng or random.uniform)(0, self.jitter))
