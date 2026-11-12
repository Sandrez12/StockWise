"""Límite de intentos fallidos de login, en memoria y sin dependencias.

Cuenta los fallos por combinación (IP, correo) en una ventana deslizante. Tras
MAX_ATTEMPTS fallos dentro de la ventana, el par queda bloqueado hasta que el
fallo más antiguo salga de ella.

Limitación: el estado vive en el proceso. No se comparte entre varias instancias
ni sobrevive a un reinicio; para eso haría falta un almacén externo (p. ej. Redis).
"""

import threading
import time
from collections import deque
from collections.abc import Callable

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60
MAX_TRACKED_KEYS = 10_000  # tope de memoria ante un flujo de correos distintos


class LoginRateLimiter:
    def __init__(
        self,
        max_attempts: int = MAX_ATTEMPTS,
        window_seconds: float = WINDOW_SECONDS,
        max_keys: int = MAX_TRACKED_KEYS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_attempts = max_attempts
        self.window = window_seconds
        self.max_keys = max_keys
        self._clock = clock
        self._failures: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(ip: str, email: str) -> tuple[str, str]:
        return (ip, email.strip().lower())

    def _prune(self, key: tuple[str, str], now: float) -> deque[float] | None:
        attempts = self._failures.get(key)
        if attempts is None:
            return None
        while attempts and now - attempts[0] >= self.window:
            attempts.popleft()
        if not attempts:
            del self._failures[key]
            return None
        return attempts

    def retry_after(self, ip: str, email: str) -> int:
        """Segundos hasta poder reintentar; 0 si el par no está bloqueado."""
        key = self._key(ip, email)
        with self._lock:
            now = self._clock()
            attempts = self._prune(key, now)
            if attempts is None or len(attempts) < self.max_attempts:
                return 0
            return max(1, int(attempts[0] + self.window - now) + 1)

    def register_failure(self, ip: str, email: str) -> None:
        key = self._key(ip, email)
        with self._lock:
            now = self._clock()
            if key not in self._failures and len(self._failures) >= self.max_keys:
                self._evict(now)
            attempts = self._prune(key, now)
            if attempts is None:
                attempts = self._failures.setdefault(key, deque())
            attempts.append(now)
            # No hace falta guardar más fallos de los que bloquean.
            while len(attempts) > self.max_attempts:
                attempts.popleft()

    def reset(self, ip: str, email: str) -> None:
        with self._lock:
            self._failures.pop(self._key(ip, email), None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()

    def _evict(self, now: float) -> None:
        for key in list(self._failures):
            self._prune(key, now)
        if len(self._failures) >= self.max_keys:
            # Sigue lleno de claves vigentes: se descarta la más antigua.
            oldest = min(self._failures, key=lambda k: self._failures[k][-1])
            del self._failures[oldest]


login_limiter = LoginRateLimiter()
