"""Cache (por processo) do cadastro de estúdios.

Toda requisição autenticada precisa do estúdio (ativo? horário de funcionamento?). Sem cache isso é uma consulta
extra ao banco central por requisição. O cache vale ``studio_cache_seconds`` e é invalidado quando o estúdio é
alterado neste processo; em outros processos a mudança (ex.: desativar um estúdio) vale em até esse tempo.
Só estúdios encontrados são guardados: um estúdio recém-criado aparece na hora.
"""

import threading
import time

from sqlalchemy import select

from app.core.config import settings
from app.db.engines import central_session
from app.models.central import Studio


class StudioCache:
    def __init__(self) -> None:
        self._items: dict[str, tuple[float, Studio]] = {}
        self._lock = threading.Lock()

    def get(self, slug: str) -> Studio | None:
        ttl = settings.studio_cache_seconds
        now = time.monotonic()
        if ttl > 0:
            hit = self._items.get(slug)
            if hit is not None and now - hit[0] < ttl:
                return hit[1]
        with central_session() as central:
            studio = central.scalar(select(Studio).where(Studio.slug == slug))
        if studio is not None and ttl > 0:
            with self._lock:
                self._items[slug] = (now, studio)
        return studio

    def invalidate(self, slug: str | None = None) -> None:
        with self._lock:
            if slug is None:
                self._items.clear()
            else:
                self._items.pop(slug, None)


studio_cache = StudioCache()
