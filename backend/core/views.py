"""Healthcheck: usato dai container e dal reverse proxy."""

from __future__ import annotations

from django.db import connection
from django.http import HttpRequest, JsonResponse


def health(request: HttpRequest) -> JsonResponse:
    checks: dict[str, str] = {}
    ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = "ok"
    except Exception as exc:
        ok = False
        checks["database"] = f"errore: {exc.__class__.__name__}"
    return JsonResponse(
        {"status": "ok" if ok else "degraded", "checks": checks}, status=200 if ok else 503
    )
