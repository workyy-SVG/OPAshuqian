"""Password verification, bounded login attempts and revocable server sessions."""
from dataclasses import dataclass
import hashlib
import hmac
import secrets
import threading
import time


def password_hash(password: str, iterations: int = 600000) -> str:
    if len(password) < 12:
        raise ValueError('口令至少12个字符。')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), iterations).hex()
    return f'pbkdf2_sha256${iterations}${salt}${digest}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        kind, rounds, salt, expected = encoded.split('$')
        count = int(rounds)
        if kind != 'pbkdf2_sha256' or not 300000 <= count <= 2000000 or len(salt) != 32 or len(expected) != 64 or len(password) > 1024:
            return False
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), count).hex()
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class AccessConfig:
    required: bool = False
    username: str = ''
    password_hash: str = ''
    session_seconds: int = 1800

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(f'{self.username}:{self.password_hash}:{self.session_seconds}'.encode()).hexdigest()

    @property
    def configured(self) -> bool:
        parts = self.password_hash.split('$')
        try:
            return bool(self.username.strip() and 60 <= self.session_seconds <= 86400 and len(parts) == 4
                        and parts[0] == 'pbkdf2_sha256' and 300000 <= int(parts[1]) <= 2000000
                        and len(bytes.fromhex(parts[2])) == 16 and len(bytes.fromhex(parts[3])) == 32)
        except ValueError:
            return False


class AccessRegistry:
    def __init__(self, clock=None):
        self.clock = clock or time.monotonic
        self.lock = threading.RLock()
        self.failures: dict[str, list[float]] = {}
        self.sessions: dict[str, tuple[str, str, float]] = {}

    def _prune(self) -> None:
        now = self.clock()
        self.failures = {key: [t for t in values if t > now - 300] for key, values in self.failures.items() if any(t > now - 300 for t in values)}
        self.sessions = {key: entry for key, entry in self.sessions.items() if entry[2] > now}

    def login(self, username: str, password: str, config: AccessConfig, peer: str = 'shared') -> str | None:
        with self.lock:
            self._prune()
            # Account-wide bucket also prevents bypassing the limit with new cookies/IPs.
            key = config.fingerprint
            if not config.configured or len(self.failures.get(key, [])) >= 5:
                return None
            good_password = verify_password(password, config.password_hash)
            if not good_password or not hmac.compare_digest(username.encode(), config.username.encode()):
                self.failures.setdefault(key, []).append(self.clock())
                return None
            self.failures.pop(key, None)
            token = secrets.token_urlsafe(32)
            self.sessions[token] = (config.username, config.fingerprint, self.clock() + config.session_seconds)
            return token

    def validate(self, token: str, config: AccessConfig) -> str | None:
        with self.lock:
            self._prune()
            entry = self.sessions.get(token)
            return entry[0] if entry and entry[1] == config.fingerprint else None

    def revoke(self, token: str) -> None:
        with self.lock:
            self.sessions.pop(token, None)
