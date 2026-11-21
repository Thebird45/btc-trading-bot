"""Avisos del bot. Telegram se agrega como otra implementación de `Notifier`."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

log = logging.getLogger("btcbot")


class Notifier(Protocol):
    def send(self, text: str) -> None: ...


class LogNotifier:
    """Escribe los avisos en el log (consola). Siempre activo."""

    def send(self, text: str) -> None:
        log.info("AVISO: %s", text.replace("\n", " | "))

    def send_file(self, path: Path, caption: str) -> None:
        log.info("ARCHIVO: %s (%d bytes)", path.name, path.stat().st_size)


class MultiNotifier:
    """Envía a varios destinos; si uno falla, los demás siguen."""

    def __init__(self, *notifiers: Notifier):
        self.notifiers = list(notifiers)

    def send(self, text: str) -> None:
        for n in self.notifiers:
            try:
                n.send(text)
            except Exception:  # un aviso fallido nunca debe tumbar el bot
                log.exception("Falló el envío de un aviso con %s", type(n).__name__)

    def send_file(self, path: Path, caption: str) -> None:
        for n in self.notifiers:
            if not hasattr(n, "send_file"):
                continue
            try:
                n.send_file(path, caption)
            except Exception:
                log.exception("Falló el envío de un archivo con %s", type(n).__name__)


class MemoryNotifier:
    """Guarda los avisos en una lista (tests)."""

    def __init__(self):
        self.messages: list[str] = []
        self.files: list[tuple[str, bytes, str]] = []

    def send(self, text: str) -> None:
        self.messages.append(text)

    def send_file(self, path: Path, caption: str) -> None:
        self.files.append((path.name, path.read_bytes(), caption))
