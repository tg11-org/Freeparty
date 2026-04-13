from django.core.cache import cache
from django.db import connections
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.core.pagination import paginate_queryset
from apps.social.models import Bookmark, Like, Repost
from apps.timelines.services import home_timeline, public_timeline


@require_http_methods(["GET"])
def home_view(request: HttpRequest) -> HttpResponse:
	active_tab = request.GET.get("tab", "all").strip().lower()
	if active_tab not in {"all", "media"}:
		active_tab = "all"

	if request.user.is_authenticated and hasattr(request.user, "actor"):
		posts_qs = home_timeline(request.user.actor, limit=None)
		actor = request.user.actor
	else:
		posts_qs = public_timeline(limit=None)
		liked_ids = set()
		reposted_ids = set()

	if active_tab == "media":
		posts_qs = posts_qs.filter(
			attachments__attachment_type__in=["image", "video"],
			attachments__moderation_state="normal",
		).distinct()

	page_obj = paginate_queryset(request, posts_qs, per_page=20, page_param="page")
	posts = page_obj.object_list
	if request.user.is_authenticated and hasattr(request.user, "actor"):
		actor = request.user.actor
		liked_ids = set(Like.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
		reposted_ids = set(Repost.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
		bookmarked_ids = set(Bookmark.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
	else:
		bookmarked_ids = set()
	return render(request, "core/home.html", {
		"posts": posts,
		"page_obj": page_obj,
		"liked_ids": liked_ids,
		"reposted_ids": reposted_ids,
		"bookmarked_ids": bookmarked_ids,
		"active_tab": active_tab,
		"query_string": f"tab={active_tab}" if active_tab != "all" else "",
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


@require_http_methods(["GET"])
def health_status_view(request: HttpRequest) -> HttpResponse:
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

	overall = "ok" if all(checks.values()) else "degraded"
	return render(request, "core/health_status.html", {"checks": checks, "overall": overall})


@require_http_methods(["GET"])
def me_redirect_view(request: HttpRequest) -> HttpResponse:
	if request.user.is_authenticated and hasattr(request.user, "actor"):
		return redirect("actors:detail", handle=request.user.actor.handle)
	return redirect("accounts:login")
