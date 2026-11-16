"""Metriques Prometheus : base des SLI (disponibilite et latence)."""
import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response

REQUESTS = Counter("http_requests_total", "Requetes HTTP", ["method", "route", "status"])
LATENCY = Histogram(
    "http_request_duration_seconds", "Latence des requetes HTTP", ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
INFLIGHT = Gauge("http_requests_in_progress", "Requetes en cours")
TICKETS_CREATED = Counter("helpdesk_tickets_created_total", "Tickets crees")
LOGIN_FAILURES = Counter("helpdesk_login_failures_total", "Echecs de connexion")
UPLOADS = Counter("helpdesk_attachments_uploaded_total", "Pieces jointes televersees")


def route_label(request: Request) -> str:
    route = request.scope.get("route")
    return route.path if route else "unmatched"


def observe(request: Request, status: int, started: float) -> None:
    route = route_label(request)
    if route == "/metrics":
        return
    REQUESTS.labels(request.method, route, str(status)).inc()
    LATENCY.labels(request.method, route).observe(time.perf_counter() - started)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
