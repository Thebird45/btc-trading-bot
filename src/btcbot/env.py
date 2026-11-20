"""Carga mínima de variables desde un archivo .env (sin dependencias).

No sobrescribe variables que ya existan en el entorno, así Docker o systemd
pueden definirlas directamente.
"""

from __future__ import annotations

import os
from pathlib import Path

from btcbot.config import ROOT


def load_dotenv(path: Path | str = ROOT / ".env") -> None:
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
