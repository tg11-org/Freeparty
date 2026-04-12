from django.core.cache import cache
from django.db import connections
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def api_live_view(request):
    return Response({"status": "ok", "service": "freeparty", "check": "live"})


@api_view(["GET"])
@permission_classes([AllowAny])
def api_ready_view(request):
    checks = {"database": False, "cache": False}

    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = True
    except Exception:
        checks["database"] = False

    try:
        cache.set("api_healthcheck", "ok", timeout=5)
        checks["cache"] = cache.get("api_healthcheck") == "ok"
    except Exception:
        checks["cache"] = False

    is_ready = all(checks.values())
    return Response(
        {
            "status": "ok" if is_ready else "degraded",
            "service": "freeparty",
            "check": "ready",
            "checks": checks,
        },
        status=200 if is_ready else 503,
    )
