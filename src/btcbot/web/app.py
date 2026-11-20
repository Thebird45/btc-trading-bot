"""Web de seguimiento del bot (solo lectura, con login).

Los controles (pausar/reanudar) se quedan en Telegram: aunque alguien entrara
a la web, no podría operar nada.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from btcbot.config import Config
from btcbot.web.auth import LoginLimiter, SessionSigner, verify_password
from btcbot.web.dashboard import build_dashboard

STATIC = Path(__file__).parent / "static"
COOKIE = "btcbot_session"

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; "
        "style-src 'self'; img-src 'self' data:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    ),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


@dataclass(frozen=True)
class WebSettings:
    password_hash: str
    session_secret: str
    session_hours: int = 72
    secure_cookies: bool = False
    trust_proxy: bool = False


def create_app(cfg: Config, settings: WebSettings, db_path: Path | None = None) -> FastAPI:
    if not settings.password_hash:
        raise ValueError("Falta WEB_PASSWORD_HASH (genéralo con: btcbot web hash-password)")
    db_path = db_path or cfg.paper.db_file()
    signer = SessionSigner(settings.session_secret, settings.session_hours * 3600)
    limiter = LoginLimiter()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def client_ip(request: Request) -> str:
        if settings.trust_proxy:
            forwarded = request.headers.get("x-forwarded-for", "")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "?"

    def logged_in(request: Request) -> bool:
        return signer.valid(request.cookies.get(COOKIE))

    @app.middleware("http")
    async def security(request: Request, call_next):
        public = request.url.path in ("/login", "/logout", "/manifest.webmanifest", "/icon.svg",
                                      "/static/style.css")
        if not public and not logged_in(request):
            if request.url.path.startswith("/api/"):
                response: Response = JSONResponse({"error": "no autenticado"}, status_code=401)
            else:
                response = RedirectResponse("/login", status_code=303)
        else:
            response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/login")
    def login_page():
        return FileResponse(STATIC / "login.html")

    @app.post("/login")
    def login(request: Request, password: str = Form(...)):
        ip = client_ip(request)
        if limiter.blocked(ip):
            return RedirectResponse("/login?error=bloqueado", status_code=303)
        if not verify_password(password, settings.password_hash):
            limiter.fail(ip)
            return RedirectResponse("/login?error=1", status_code=303)
        limiter.reset(ip)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(COOKIE, signer.issue(), max_age=signer.max_age, httponly=True,
                            secure=settings.secure_cookies, samesite="strict")
        return response

    @app.post("/logout")
    def logout():
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(COOKIE)
        return response

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/dashboard")
    def dashboard():
        return build_dashboard(cfg, db_path)

    @app.get("/manifest.webmanifest")
    def manifest():
        return FileResponse(STATIC / "manifest.webmanifest",
                            media_type="application/manifest+json")

    @app.get("/icon.svg")
    def icon():
        return FileResponse(STATIC / "icon.svg", media_type="image/svg+xml")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
