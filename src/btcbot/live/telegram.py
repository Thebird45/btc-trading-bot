"""Telegram: avisos y comandos.

Seguridad:
- Solo se aceptan comandos del chat configurado en TELEGRAM_CHAT_ID; los demás
  se ignoran.
- El token va en la URL de la API de Telegram. Por eso los errores se convierten
  en mensajes sin URL y se silencian los logs de httpx, para que el token nunca
  quede en logs, en la base de datos ni en la web.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import httpx

log = logging.getLogger("btcbot")
logging.getLogger("httpx").setLevel(logging.WARNING)  # sus logs INFO incluyen la URL con token

API = "https://api.telegram.org"
MAX_LEN = 4000  # Telegram corta en 4096 caracteres


class TelegramError(RuntimeError):
    """Error de Telegram sin datos sensibles (sin URL ni token)."""


class TelegramClient:
    def __init__(self, token: str, client: httpx.Client | None = None, timeout: float = 60):
        if not token:
            raise ValueError("Falta el token de Telegram")
        self._client = client or httpx.Client(base_url=f"{API}/bot{token}", timeout=timeout)

    def call(self, method: str, **params) -> dict | list:
        try:
            resp = self._client.post(f"/{method}", json=params)
        except httpx.HTTPError as exc:
            raise TelegramError(f"sin conexión con Telegram ({type(exc).__name__})") from None
        try:
            data = resp.json()
        except ValueError:
            raise TelegramError(f"Telegram respondió {resp.status_code}") from None
        if not data.get("ok"):
            raise TelegramError(f"Telegram rechazó {method}: {data.get('description', '?')}")
        return data["result"]

    def send_message(self, chat_id: str | int, text: str) -> None:
        for i in range(0, len(text), MAX_LEN):
            self.call("sendMessage", chat_id=chat_id, text=text[i:i + MAX_LEN],
                      disable_web_page_preview=True)

    def get_updates(self, offset: int | None, timeout: int = 50) -> list[dict]:
        params = {"timeout": timeout, "allowed_updates": ["message"]}
        if offset is not None:
            params["offset"] = offset
        return self.call("getUpdates", **params)


class TelegramNotifier:
    def __init__(self, client: TelegramClient, chat_id: str | int):
        self.client = client
        self.chat_id = chat_id

    def send(self, text: str) -> None:
        self.client.send_message(self.chat_id, text)


HELP = """🤖 Comandos del bot
/estado — capital, posición y lectura del mercado
/resumen — desempeño desde el inicio vs buy & hold
/operaciones — últimas operaciones cerradas
/pausar — interruptor de emergencia: no abre compras nuevas (ventas y stops siguen)
/reanudar — vuelve a operar normal
/ayuda — esta lista"""


class TelegramCommands:
    """Escucha comandos con long polling en un hilo aparte."""

    def __init__(self, client: TelegramClient, chat_id: str | int,
                 handlers: dict[str, Callable[[], str]]):
        self.client = client
        self.chat_id = str(chat_id)
        self.handlers = {"/ayuda": lambda: HELP, "/start": lambda: HELP, "/help": lambda: HELP,
                         **handlers}
        self.offset: int | None = None

    def handle_update(self, update: dict) -> str | None:
        """Procesa un update y devuelve la respuesta (o None si se ignora)."""
        msg = update.get("message") or {}
        chat = str((msg.get("chat") or {}).get("id", ""))
        text = (msg.get("text") or "").strip()
        if not text.startswith("/"):
            return None
        if chat != self.chat_id:
            log.warning("Comando ignorado de un chat no autorizado (%s)", chat)
            return None
        command = text.split()[0].split("@")[0].lower()
        handler = self.handlers.get(command)
        if handler is None:
            return f"No conozco {command}. Escribe /ayuda."
        try:
            return handler()
        except Exception as exc:
            log.exception("Falló el comando %s", command)
            return f"⚠️ Error al ejecutar {command}: {type(exc).__name__}"

    def poll_once(self, timeout: int = 50) -> int:
        updates = self.client.get_updates(self.offset, timeout=timeout)
        for update in updates:
            self.offset = update["update_id"] + 1
            reply = self.handle_update(update)
            if reply:
                self.client.send_message(self.chat_id, reply)
        return len(updates)

    def run(self, stop: threading.Event) -> None:
        # Los comandos enviados con el bot apagado se ejecutan al volver: un /pausar
        # de emergencia no debe perderse.
        while not stop.is_set():
            try:
                self.poll_once()
            except TelegramError as exc:
                log.warning("Telegram: %s", exc)
                stop.wait(10)
            except Exception:
                log.exception("Error inesperado escuchando Telegram")
                stop.wait(10)

    def start(self, stop: threading.Event) -> threading.Thread:
        thread = threading.Thread(target=self.run, args=(stop,), name="telegram", daemon=True)
        thread.start()
        return thread
