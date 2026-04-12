from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.core.services.uris import post_uri
from apps.posts.forms import PostForm
from apps.posts.models import Post
from apps.timelines.services import public_timeline


@ratelimit(key="user_or_ip", rate="20/h", block=True)
@login_required
@require_http_methods(["GET", "POST"])
def create_post_view(request: HttpRequest) -> HttpResponse:
	if settings.EMAIL_VERIFICATION_REQUIRED and not request.user.email_verified:
		messages.error(request, "You must verify your email before posting.")
		return redirect("home")

	actor = getattr(request.user, "actor", None)
	if actor is None:
		messages.error(request, "No actor profile linked to this account.")
		return redirect("home")

	form = PostForm(request.POST or None)
	if request.method == "POST" and form.is_valid():
		post = form.save(commit=False)
		post.author = actor
		post.canonical_uri = post_uri(post.id)
		post.save()
		messages.success(request, "Post published.")
		return redirect("home")

	return render(request, "posts/create_post.html", {"form": form})


@require_http_methods(["GET"])
def public_posts_view(request: HttpRequest) -> HttpResponse:
	return render(request, "posts/public_list.html", {"posts": public_timeline()})

