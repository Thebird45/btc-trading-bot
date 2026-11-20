"""Autenticación de la web: hash de contraseña, sesión firmada y límite de intentos.

Solo usa la librería estándar:
- Contraseña: PBKDF2-SHA256 con sal aleatoria. En el servidor solo se guarda el hash.
- Sesión: cookie "expiración.firma" firmada con HMAC-SHA256 y un secreto del servidor.
- Fuerza bruta: tras `max_failures` intentos fallidos desde una IP, se bloquea
  esa IP durante `lockout_seconds`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time

ITERATIONS = 600_000


def hash_password(password: str, iterations: int = ITERATIONS) -> str:
    if len(password) < 10:
        raise ValueError("La contraseña debe tener al menos 10 caracteres")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    b64 = base64.urlsafe_b64encode
    return f"pbkdf2_sha256:{iterations}:{b64(salt).decode()}:{b64(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = stored.split(":")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64)
        expected = base64.urlsafe_b64decode(digest_b64)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


class SessionSigner:
    def __init__(self, secret: str, max_age_seconds: int):
        if len(secret) < 32:
            raise ValueError("WEB_SESSION_SECRET debe tener al menos 32 caracteres")
        self._key = secret.encode()
        self.max_age = max_age_seconds

    def _sign(self, payload: str) -> str:
        return hmac.new(self._key, payload.encode(), hashlib.sha256).hexdigest()

    def issue(self, now: float | None = None) -> str:
        expires = int((now or time.time()) + self.max_age)
        payload = f"{expires}.{secrets.token_hex(8)}"
        return f"{payload}.{self._sign(payload)}"

    def valid(self, token: str | None, now: float | None = None) -> bool:
        if not token or token.count(".") != 2:
            return False
        expires, nonce, signature = token.split(".")
        if not hmac.compare_digest(signature, self._sign(f"{expires}.{nonce}")):
            return False
        try:
            return int(expires) > (now or time.time())
        except ValueError:
            return False


class LoginLimiter:
    def __init__(self, max_failures: int = 5, lockout_seconds: int = 900):
        self.max_failures = max_failures
        self.lockout_seconds = lockout_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, ip: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(ip, []) if now - t < self.lockout_seconds]
        self._failures[ip] = recent
        return recent

    def blocked(self, ip: str, now: float | None = None) -> bool:
        with self._lock:
            return len(self._recent(ip, now or time.time())) >= self.max_failures

    def fail(self, ip: str, now: float | None = None) -> None:
        with self._lock:
            now = now or time.time()
            self._recent(ip, now).append(now)

    def reset(self, ip: str) -> None:
        with self._lock:
            self._failures.pop(ip, None)
