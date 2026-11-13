"""Limite de tentativas de login que falharam.

Em memória e por processo: freia força bruta e dicionário contra uma instância, sem depender de Redis. Com várias
réplicas o limite efetivo é multiplicado pelo número delas; se isso virar problema, troque o armazenamento por um
compartilhado (a interface — ``check``/``hit``/``reset`` — não muda).

Só tentativas *falhas* contam, e a chave inclui o IP: assim um atacante não consegue travar a conta de outra
pessoa. Há dois limites: por IP + conta (``login_max_attempts``) e por IP no total (``login_max_attempts_per_ip``).
"""

import math
import threading
import time
from collections import deque

from fastapi import HTTPException, Request, status

from app.core.config import settings

_PRUNE_EVERY = 1000  # varre chaves antigas a cada N registros de falha


class FailureLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._writes = 0

    def _fresh(self, key: str, now: float, window: float) -> deque[float]:
        hits = self._hits.get(key)
        if hits is None:
            return deque()
        while hits and now - hits[0] >= window:
            hits.popleft()
        return hits

    def retry_after(self, key: str, limit: int, window: float) -> int:
        """Segundos até liberar, ou 0 se a chave ainda não atingiu o limite."""
        now = time.monotonic()
        with self._lock:
            hits = self._fresh(key, now, window)
            if len(hits) < limit:
                return 0
            return max(1, math.ceil(window - (now - hits[0])))

    def hit(self, key: str, window: float) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= window:
                hits.popleft()
            hits.append(now)
            self._writes += 1
            if self._writes % _PRUNE_EVERY == 0:
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= window]:
                    del self._hits[k]

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = FailureLimiter()


def client_ip(request: Request) -> str:
    # Atrás do Caddy, o uvicorn já troca request.client pelo X-Forwarded-For (FORWARDED_ALLOW_IPS).
    return request.client.host if request.client else "desconhecido"


class LoginAttempt:
    """Uso: ``attempt = LoginAttempt(request, "studio", account)`` → ``attempt.check()`` antes de validar a senha,
    ``attempt.failed()`` ao errar e ``attempt.succeeded()`` ao acertar."""

    def __init__(self, request: Request, scope: str, account: str) -> None:
        ip = client_ip(request)
        self.ip_key = f"{scope}:ip:{ip}"
        self.account_key = f"{scope}:acct:{ip}:{account.strip().lower()}"

    def check(self) -> None:
        window = settings.login_window_seconds
        wait = max(
            limiter.retry_after(self.account_key, settings.login_max_attempts, window),
            limiter.retry_after(self.ip_key, settings.login_max_attempts_per_ip, window),
        )
        if wait:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Muitas tentativas de login. Aguarde alguns minutos e tente novamente.",
                headers={"Retry-After": str(wait)},
            )

    def failed(self) -> None:
        window = settings.login_window_seconds
        limiter.hit(self.account_key, window)
        limiter.hit(self.ip_key, window)

    def succeeded(self) -> None:
        limiter.reset(self.account_key)
