"""Avisos del bot. Telegram se agrega como otra implementación de `Notifier`."""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger("btcbot")


class Notifier(Protocol):
    def send(self, text: str) -> None: ...


class LogNotifier:
    """Escribe los avisos en el log (consola). Siempre activo."""

    def send(self, text: str) -> None:
        log.info("AVISO: %s", text.replace("\n", " | "))


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


class MemoryNotifier:
    """Guarda los avisos en una lista (tests)."""

    def __init__(self):
        self.messages: list[str] = []

    def send(self, text: str) -> None:
        self.messages.append(text)
