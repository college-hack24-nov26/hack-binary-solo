"""App factory. Serves the API under /api and the built React app (web/dist) from the same origin, so tablets on the hospital
LAN need nothing but this one server. Run one worker only (see api/deps.py): scripts/run_server.py."""
from pathlib import Path

from fastapi import FastAPI, Request
from starlette.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse

from intake import offline
from intake.models import load_graph
from intake.redflags import load_rules

from .deps import CSRF_HEADER, CSRF_VALUE, SessionStore, make_authenticator
from .events import Broker, HelpRequests
from .identity_provider import default_provider
from .kiosk_identity import IdentitySessions, RateLimiter
from .routers import audit, auth, demo, doctor, dosing, identity, kiosk, ocr, patients, staff, staff_patients, system
from .sessions import Registry

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
SPA_PREFIXES = ("kiosk", "staff", "doctor", "gallery")


def create_app(dist: Path | None = None) -> FastAPI:
    offline.install_if_strict()            # OFFLINE_STRICT=1: any non-loopback connect raises and is logged
    from ocr.config import load_settings
    settings = load_settings()

    app = FastAPI(title="MediKiosk OPD API", version="1.0", openapi_url="/api/openapi.json", docs_url="/api/docs", redoc_url=None)
    app.state.sessions = SessionStore(settings.auth_idle_s)
    app.state.authenticator = make_authenticator()
    app.state.registry = Registry(load_graph(), load_rules())
    app.state.events = Broker()
    app.state.help = HelpRequests()
    app.state.results = dosing.ResultCache()
    app.state.identity_sessions = IdentitySessions()
    app.state.rate = RateLimiter()
    app.state.provider = default_provider()

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        """Every mutating API call must carry X-Requested-With: medikiosk. A cross-site form cannot set that header."""
        if request.method in MUTATING and request.url.path.startswith("/api/") \
                and request.headers.get(CSRF_HEADER, "").lower() != CSRF_VALUE:
            return JSONResponse({"detail": "Missing X-Requested-With header."}, status_code=403)
        resp = await call_next(request)
        if request.url.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        return resp

    app.add_middleware(GZipMiddleware, minimum_size=1000)   # LAN tablets: smaller JS and fonts. SSE (text/event-stream) is never compressed.

    for r in (system, auth, kiosk, identity, patients, staff, staff_patients, doctor, ocr, dosing, audit, demo):
        app.include_router(r.router)

    web = dist or DIST

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/") or path == "api":
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if not (web / "index.html").exists():
            return JSONResponse({"detail": "The web app is not built. Run: npm --prefix web run build"}, status_code=503)
        f = (web / path).resolve()
        if path and f.is_file() and web.resolve() in f.parents:
            headers = {"Cache-Control": "public, max-age=31536000, immutable"} if path.startswith("assets/") else {}
            return FileResponse(f, headers=headers)
        if path == "" or path.split("/")[0] in SPA_PREFIXES:
            return FileResponse(web / "index.html", headers={"Cache-Control": "no-cache"})
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    return app
