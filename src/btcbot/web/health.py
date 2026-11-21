"""Chequeo de salud público para el monitoreo externo.

Solo responde "ok" o el motivo de la falla, sin datos de la cuenta: es la única
ruta de la web que no exige iniciar sesión.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from btcbot.config import Config
from btcbot.live.store import PaperStore


def check_health(cfg: Config, db_path: Path, now: pd.Timestamp | None = None) -> tuple[bool, str]:
    now = now or pd.Timestamp.now(tz="UTC")
    if not db_path.exists():
        return False, "sin base de datos"
    store = PaperStore(db_path)
    try:
        last_tick = store.get("last_tick")
        stale = bool(store.get("stale", False))
    finally:
        store.close()
    if not last_tick:
        return False, "el bot no ha arrancado"
    # El bot revisa cada poll_seconds; damos margen para reinicios y despliegues
    window = pd.Timedelta(seconds=max(10 * cfg.paper.poll_seconds, 600))
    if now - pd.Timestamp(last_tick) > window:
        return False, "el bot no responde"
    if stale:
        return False, "datos atrasados"
    return True, "ok"
