import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import metrics
from .config import get_settings
from .db import get_engine
from .logging_conf import request_id_var, setup_logging
from .routes_auth import router as auth_router
from .routes_tickets import router as tickets_router

settings = get_settings()
setup_logging(settings.log_level)
log = logging.getLogger("app")

app = FastAPI(title="Helpdesk API", version=settings.app_version)


@app.middleware("http")
async def observability(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request_id_var.set(rid)
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = rid
        response.headers["X-App-Version"] = settings.app_version
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    except Exception:
        log.exception("erreur non gérée")
        return JSONResponse({"detail": "Erreur interne"}, status_code=500)
    finally:
        metrics.observe(request, status, started)
        if request.url.path not in ("/health", "/ready", "/metrics"):
            log.info("requete", extra={"fields": {
                "method": request.method, "path": request.url.path, "status": status,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1)}})


@app.get("/health", include_in_schema=False)
def health():
    """Liveness : le process répond."""
    return {"status": "ok", "version": settings.app_version}


@app.get("/ready", include_in_schema=False)
def ready():
    """Readiness : la base répond, sinon K8s retire le pod du Service."""
    try:
        with get_engine().connect() as c:
            c.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "db_unavailable"}, status_code=503)
    return {"status": "ready"}


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics():
    return metrics.metrics_response()


app.include_router(auth_router)
app.include_router(tickets_router)
