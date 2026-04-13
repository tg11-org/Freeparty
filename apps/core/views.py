from django.core.cache import cache
from django.db import connections
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.social.models import Like, Repost
from apps.timelines.services import home_timeline, public_timeline


@require_http_methods(["GET"])
def home_view(request: HttpRequest) -> HttpResponse:
	if request.user.is_authenticated and hasattr(request.user, "actor"):
		posts = home_timeline(request.user.actor.id)
		actor = request.user.actor
		liked_ids = set(Like.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
		reposted_ids = set(Repost.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
	else:
		posts = public_timeline()
		liked_ids = set()
		reposted_ids = set()
	return render(request, "core/home.html", {
		"posts": posts,
		"liked_ids": liked_ids,
		"reposted_ids": reposted_ids,
	})


@require_http_methods(["GET"])
def health_live_view(request: HttpRequest) -> JsonResponse:
	return JsonResponse({"status": "ok", "service": "freeparty", "check": "live"}, status=200)


@require_http_methods(["GET"])
def health_ready_view(request: HttpRequest) -> JsonResponse:
	checks = {"database": False, "cache": False}

	try:
		with connections["default"].cursor() as cursor:
			cursor.execute("SELECT 1")
		checks["database"] = True
	except Exception:
		checks["database"] = False

	try:
		cache.set("healthcheck", "ok", timeout=5)
		checks["cache"] = cache.get("healthcheck") == "ok"
	except Exception:
		checks["cache"] = False

	is_ready = all(checks.values())
	return JsonResponse(
		{"status": "ok" if is_ready else "degraded", "service": "freeparty", "check": "ready", "checks": checks},
		status=200 if is_ready else 503,
	)
