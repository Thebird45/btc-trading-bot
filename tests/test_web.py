import pandas as pd
import pytest
from conftest import make_candles
from fastapi.testclient import TestClient
from test_paper import after_close, make_trader

from btcbot.web.app import COOKIE, WebSettings, create_app
from btcbot.web.auth import LoginLimiter, SessionSigner, hash_password, verify_password
from btcbot.web.dashboard import build_dashboard

PASSWORD = "una-clave-larga-123"
SECRET = "x" * 40


@pytest.fixture(scope="module")
def pw_hash():
    return hash_password(PASSWORD, iterations=1000)  # rápido para tests


@pytest.fixture
def populated(tmp_path):
    candles = make_candles("2023-01-01", 900, seed=42)
    trader, store, _ = make_trader(tmp_path, candles)
    for i in range(300, len(candles)):
        trader.tick(after_close(candles, i))
    return trader.cfg, store.path


def client_for(cfg, db_path, pw_hash):
    app = create_app(cfg, WebSettings(pw_hash, SECRET), db_path=db_path)
    return TestClient(app, follow_redirects=False)


def login(client, password=PASSWORD):
    return client.post("/login", data={"password": password})


# --- auth -------------------------------------------------------------------------

def test_password_hash_roundtrip():
    h = hash_password(PASSWORD, iterations=1000)
    assert "$" not in h  # Docker Compose interpreta '$' en .env
    assert verify_password(PASSWORD, h)
    assert not verify_password("otra-clave-123", h)
    assert not verify_password(PASSWORD, "basura")


def test_short_password_rejected():
    with pytest.raises(ValueError):
        hash_password("corta")


def test_session_signer():
    s = SessionSigner(SECRET, 3600)
    token = s.issue(now=1000)
    assert s.valid(token, now=2000)
    assert not s.valid(token, now=5000)  # expirada
    expires, nonce, sig = token.split(".")
    assert not s.valid(f"{int(expires) + 99999}.{nonce}.{sig}", now=2000)  # manipulada
    assert not SessionSigner("y" * 40, 3600).valid(token, now=2000)  # otro secreto
    assert not s.valid(None) and not s.valid("abc")


def test_limiter_blocks_after_failures():
    lim = LoginLimiter(max_failures=3, lockout_seconds=60)
    for _ in range(3):
        lim.fail("1.2.3.4", now=100)
    assert lim.blocked("1.2.3.4", now=110)
    assert not lim.blocked("5.6.7.8", now=110)
    assert not lim.blocked("1.2.3.4", now=200)  # pasó el bloqueo


# --- app ------------------------------------------------------------------------------

def test_requires_login(populated, pw_hash):
    c = client_for(*populated, pw_hash)
    assert c.get("/").status_code == 303
    assert c.get("/").headers["location"] == "/login"
    assert c.get("/api/dashboard").status_code == 401
    assert c.get("/static/app.js").status_code == 303
    assert c.get("/login").status_code == 200


def test_wrong_password(populated, pw_hash):
    c = client_for(*populated, pw_hash)
    r = login(c, "no-es-la-clave")
    assert r.headers["location"] == "/login?error=1"
    assert COOKIE not in r.cookies


def test_lockout_after_five_failures(populated, pw_hash):
    c = client_for(*populated, pw_hash)
    for _ in range(5):
        login(c, "mala-clave-000")
    # Ni siquiera la contraseña correcta entra durante el bloqueo
    assert login(c).headers["location"] == "/login?error=bloqueado"


def test_login_and_dashboard(populated, pw_hash):
    c = client_for(*populated, pw_hash)
    r = login(c)
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    c.cookies.set(COOKIE, r.cookies[COOKIE])
    assert c.get("/").status_code == 200
    d = c.get("/api/dashboard").json()
    assert d["ready"] is True
    assert d["account"]["equity"] > 0
    assert len(d["equity"]) > 10 and {"t", "equity", "bh"} <= set(d["equity"][0])
    assert d["metrics"]["trades"] == len(d["trades"]) or len(d["trades"]) == 50
    assert d["status"]["paused"] is False


def test_logout_clears_cookie(populated, pw_hash):
    c = client_for(*populated, pw_hash)
    r = c.post("/logout")
    assert r.headers["location"] == "/login"
    assert 'btcbot_session=""' in r.headers["set-cookie"] or "Max-Age=0" in r.headers["set-cookie"]


def test_security_headers(populated, pw_hash):
    c = client_for(*populated, pw_hash)
    h = c.get("/login").headers
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert "script-src 'self';" in h["content-security-policy"]
    assert h["x-frame-options"] == "DENY"


def test_no_docs_endpoints(populated, pw_hash):
    c = client_for(*populated, pw_hash)
    login(c)
    for path in ("/docs", "/openapi.json", "/redoc"):
        assert c.get(path).status_code in (303, 404)


def test_app_requires_password_hash(populated):
    with pytest.raises(ValueError):
        create_app(populated[0], WebSettings("", SECRET), db_path=populated[1])


# --- datos del panel ---------------------------------------------------------------------

def test_dashboard_without_db(tmp_path, populated):
    d = build_dashboard(populated[0], tmp_path / "no-existe.db")
    assert d["ready"] is False


def test_dashboard_json_has_no_nan(populated):
    import json

    d = build_dashboard(*populated)
    text = json.dumps(d, allow_nan=False)  # falla si queda algún NaN
    assert "NaN" not in text


def test_dashboard_alive_flag(populated):
    cfg, db = populated
    d = build_dashboard(cfg, db, now=pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=10))
    assert d["status"]["alive"] is False


# --- mercado en vivo -------------------------------------------------------------------

def fake_binance(calls, fail=False):
    import httpx

    def handler(request):
        calls.append(request.url.path)
        if fail:
            raise httpx.ConnectError("sin red")
        if request.url.path.endswith("/ticker/24hr"):
            return httpx.Response(200, json={"lastPrice": "60000.5", "priceChangePercent": "-2.5",
                                             "highPrice": "61000", "lowPrice": "59000"})
        n = int(request.url.params["limit"])
        t0 = 1_700_000_000_000
        rows = [[t0 + i * 14_400_000, "100", "101", "99", str(100 + i * 0.1), "1",
                 t0 + (i + 1) * 14_400_000 - 1, "100", 5, "0.5", "50", "0"] for i in range(n)]
        return httpx.Response(200, json=rows)

    return httpx.Client(base_url="https://test", transport=httpx.MockTransport(handler))


def test_market_feed_snapshot_and_cache(populated):
    from btcbot.web.market import SHOW, MarketFeed

    calls, now = [], [0.0]
    feed = MarketFeed(populated[0], client=fake_binance(calls), clock=lambda: now[0])
    m = feed.snapshot()
    assert m["ok"] and m["price"] == 60000.5 and m["change_24h"] == -0.025
    assert len(m["candles"]["t"]) == SHOW and m["candles"]["regime"][-1] is not None
    feed.snapshot()
    assert len(calls) == 2  # segunda llamada sale de la caché
    now[0] = 100
    feed.snapshot()
    assert len(calls) == 4  # caché vencida


def test_market_feed_offline(populated):
    from btcbot.web.market import MarketFeed

    m = MarketFeed(populated[0], client=fake_binance([], fail=True)).snapshot()
    assert m["ok"] is False and "Binance" in m["error"]


def test_market_endpoint_requires_login(populated, pw_hash):
    from btcbot.web.market import MarketFeed

    app = create_app(populated[0], WebSettings(pw_hash, SECRET), db_path=populated[1],
                     market=MarketFeed(populated[0], client=fake_binance([])))
    c = TestClient(app, follow_redirects=False)
    assert c.get("/api/market").status_code == 401
    c.cookies.set(COOKIE, login(c).cookies[COOKIE])
    assert c.get("/api/market").json()["ok"] is True


# --- salud ------------------------------------------------------------------------------

def test_health_is_public_and_ok_when_bot_alive(populated, pw_hash):
    from btcbot.live.store import PaperStore

    cfg, db = populated
    PaperStore(db).set("last_tick", pd.Timestamp.now(tz="UTC").isoformat())
    c = client_for(cfg, db, pw_hash)
    r = c.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_health_fails_when_bot_silent(populated):
    from btcbot.live.store import PaperStore
    from btcbot.web.health import check_health

    cfg, db = populated
    old = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=1)
    PaperStore(db).set("last_tick", old.isoformat())
    assert check_health(cfg, db) == (False, "el bot no responde")


def test_health_without_db(populated, tmp_path):
    from btcbot.web.health import check_health

    assert check_health(populated[0], tmp_path / "nada.db") == (False, "sin base de datos")


def test_health_reports_stale_data(populated):
    from btcbot.live.store import PaperStore
    from btcbot.web.health import check_health

    cfg, db = populated
    store = PaperStore(db)
    store.set("last_tick", pd.Timestamp.now(tz="UTC").isoformat())
    store.set("stale", True)
    assert check_health(cfg, db) == (False, "datos atrasados")
