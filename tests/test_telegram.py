import json
import os

import httpx
import pytest

from btcbot.env import load_dotenv
from btcbot.live.telegram import TelegramClient, TelegramCommands, TelegramError

TOKEN = "123456:SECRET-TOKEN"


def client_with(handler):
    transport = httpx.MockTransport(handler)
    return TelegramClient(TOKEN, client=httpx.Client(
        base_url=f"https://api.telegram.org/bot{TOKEN}", transport=transport))


def recorder(result=True):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.path.rsplit("/", 1)[-1], json.loads(request.content)))
        return httpx.Response(200, json={"ok": True, "result": result})

    return calls, handler


def test_send_message():
    calls, handler = recorder()
    client_with(handler).send_message(42, "hola")
    assert calls == [("sendMessage", {"chat_id": 42, "text": "hola",
                                      "disable_web_page_preview": True})]


def test_long_message_is_split():
    calls, handler = recorder()
    client_with(handler).send_message(42, "x" * 9000)
    assert [len(c[1]["text"]) for c in calls] == [4000, 4000, 1000]


def test_errors_never_contain_token():
    def boom(request):
        raise httpx.ConnectError(f"falló {request.url}")

    with pytest.raises(TelegramError) as exc:
        client_with(boom).send_message(42, "hola")
    assert "SECRET" not in str(exc.value) and "123456" not in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__


def test_api_rejection_is_reported():
    def handler(request):
        return httpx.Response(400, json={"ok": False, "description": "chat not found"})

    with pytest.raises(TelegramError, match="chat not found"):
        client_with(handler).send_message(42, "hola")


def update(text, chat_id=42, update_id=1):
    return {"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": text}}


def commands(handlers=None):
    calls, handler = recorder()
    return TelegramCommands(client_with(handler), 42, handlers or {}), calls


def test_authorized_command_runs():
    cmds, _ = commands({"/estado": lambda: "todo bien"})
    assert cmds.handle_update(update("/estado")) == "todo bien"


def test_command_with_bot_suffix():
    cmds, _ = commands({"/pausar": lambda: "pausado"})
    assert cmds.handle_update(update("/pausar@MiBtcBot")) == "pausado"


def test_unauthorized_chat_is_ignored():
    executed = []
    cmds, _ = commands({"/pausar": lambda: executed.append(1) or "pausado"})
    assert cmds.handle_update(update("/pausar", chat_id=999)) is None
    assert executed == []


def test_non_command_and_unknown_command():
    cmds, _ = commands()
    assert cmds.handle_update(update("hola")) is None
    assert "No conozco /xyz" in cmds.handle_update(update("/xyz"))
    assert "/pausar" in cmds.handle_update(update("/ayuda"))


def test_handler_error_is_contained():
    cmds, _ = commands({"/estado": lambda: 1 / 0})
    assert "ZeroDivisionError" in cmds.handle_update(update("/estado"))


def test_poll_once_replies_and_advances_offset():
    sent = []

    def handler(request):
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content)
        if method == "getUpdates":
            return httpx.Response(200, json={"ok": True, "result": [
                update("/estado", update_id=7), update("/estado", chat_id=5, update_id=8)]})
        sent.append(body)
        return httpx.Response(200, json={"ok": True, "result": {}})

    cmds = TelegramCommands(client_with(handler), 42, {"/estado": lambda: "ok"})
    assert cmds.poll_once(timeout=0) == 2
    assert cmds.offset == 9
    assert [m["text"] for m in sent] == ["ok"]  # el chat 5 no recibe respuesta


def test_load_dotenv(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comentario\nBTC_TEST_A=uno\nBTC_TEST_B='dos'\nBTC_TEST_C=nuevo\n")
    monkeypatch.setenv("BTC_TEST_C", "existente")
    monkeypatch.delenv("BTC_TEST_A", raising=False)
    monkeypatch.delenv("BTC_TEST_B", raising=False)
    load_dotenv(env)
    assert os.environ["BTC_TEST_A"] == "uno"
    assert os.environ["BTC_TEST_B"] == "dos"
    assert os.environ["BTC_TEST_C"] == "existente"  # no sobrescribe
