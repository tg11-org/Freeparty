from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.actors.models import Actor


@require_http_methods(["GET"])
def actor_detail_view(request: HttpRequest, handle: str) -> HttpResponse:
	try:
		actor = Actor.objects.select_related("profile").get(handle=handle, state=Actor.ActorState.ACTIVE)
	except Actor.DoesNotExist as exc:
		raise Http404("Actor not found") from exc
	return render(request, "actors/detail.html", {"actor": actor})
