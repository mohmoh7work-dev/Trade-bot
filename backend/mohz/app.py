"""The mohz bot web API (and, in production, the built frontend).

    uvicorn mohz.app:app --host 127.0.0.1 --port 8000      # from backend/

Run the supervisor next to it (python -m mohz.supervisor): it starts and stops the bots.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from . import __version__, redact
from .config import get_config
from .db import init_db
from .probe import ProbePool

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                                "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
                                "form-action 'self'"),
}


def create_app():
    redact.install()
    cfg = get_config()

    @asynccontextmanager
    async def lifespan(app):
        init_db()
        app.state.probes = ProbePool(cfg.probe_slots)
        yield

    app = FastAPI(title="mohz bot", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None,
                  openapi_url=None)

    @app.middleware("http")
    async def headers(request: Request, call_next):
        resp = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            resp.headers.setdefault(k, v)
        if request.url.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        if cfg.cookie_secure:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp

    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, exc: RequestValidationError):
        # One readable line, and never the submitted values (they can hold passwords).
        errs = exc.errors()
        first = errs[0] if errs else {}
        field = ".".join(str(x) for x in first.get("loc", ())[1:]) or "request"
        msg = str(first.get("msg", "invalid")).replace("Value error, ", "")
        return JSONResponse({"detail": "%s: %s" % (field.replace("_", " "), msg)}, status_code=422)

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__}

    from .api import accounts, auth_routes, me, payments, stream
    for r in (auth_routes.router, me.router, accounts.router, payments.router, stream.router):
        app.include_router(r)

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def api_404(rest: str):
        return JSONResponse({"detail": "Not found."}, status_code=404)

    dist = cfg.frontend_dist
    if dist.exists():
        index = dist / "index.html"

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            f = (dist / path).resolve()
            if path and f.is_file() and dist in f.parents:
                headers = {"Cache-Control": "public, max-age=31536000, immutable"} if path.startswith("assets/") \
                    else {"Cache-Control": "no-cache"}
                return FileResponse(f, headers=headers)
            return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
