from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from django_ratelimit.decorators import ratelimit

from apps.core.services.uris import post_uri
from apps.notifications.models import Notification
from apps.posts.forms import PostForm
from apps.posts.models import Comment, Post
from apps.social.models import Like, Repost
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
	posts = public_timeline()
	liked_ids = set()
	reposted_ids = set()
	if request.user.is_authenticated and hasattr(request.user, "actor"):
		actor = request.user.actor
		liked_ids = set(Like.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
		reposted_ids = set(Repost.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
	return render(request, "posts/public_list.html", {
		"posts": posts,
		"liked_ids": liked_ids,
		"reposted_ids": reposted_ids,
	})


@require_http_methods(["GET"])
def post_detail_view(request: HttpRequest, post_id: str) -> HttpResponse:
	post = get_object_or_404(Post, id=post_id, deleted_at__isnull=True, moderation_state=Post.ModerationState.NORMAL)
	comments = post.comments.filter(deleted_at__isnull=True).select_related("author", "author__profile")
	liked_ids = set()
	reposted_ids = set()
	if request.user.is_authenticated and hasattr(request.user, "actor"):
		actor = request.user.actor
		liked_ids = set(Like.objects.filter(actor=actor, post=post).values_list("post_id", flat=True))
		reposted_ids = set(Repost.objects.filter(actor=actor, post=post).values_list("post_id", flat=True))
	return render(request, "posts/detail.html", {
		"post": post,
		"comments": comments,
		"liked_ids": liked_ids,
		"reposted_ids": reposted_ids,
	})


@ratelimit(key="user_or_ip", rate="60/h", block=True)
@login_required
@require_POST
def add_comment_view(request: HttpRequest, post_id: str) -> HttpResponse:
	post = get_object_or_404(Post, id=post_id, deleted_at__isnull=True)
	actor = request.user.actor
	content = request.POST.get("content", "").strip()
	if not content:
		messages.error(request, "Comment cannot be empty.")
		return redirect("posts:detail", post_id=post_id)
	if len(content) > 2000:
		messages.error(request, "Comment is too long (max 2000 characters).")
		return redirect("posts:detail", post_id=post_id)
	Comment.objects.create(post=post, author=actor, content=content)
	Notification.objects.create(
		recipient=post.author,
		source_actor=actor,
		notification_type=Notification.NotificationType.MENTION,
		source_post=post,
	)
	messages.success(request, "Comment added.")
	return redirect("posts:detail", post_id=post_id)


@ratelimit(key="user_or_ip", rate="30/h", block=True)
@login_required
@require_http_methods(["GET", "POST"])
def edit_post_view(request: HttpRequest, post_id: str) -> HttpResponse:
	post = get_object_or_404(Post, id=post_id, deleted_at__isnull=True)
	if request.user.actor.id != post.author_id:
		messages.error(request, "You can only edit your own posts.")
		return redirect("posts:detail", post_id=post_id)

	form = PostForm(request.POST or None, instance=post)
	if request.method == "POST" and form.is_valid():
		form.save()
		messages.success(request, "Post updated.")
		return redirect("posts:detail", post_id=post_id)

	return render(request, "posts/edit_post.html", {"form": form, "post": post})


@ratelimit(key="user_or_ip", rate="60/h", block=True)
@login_required
@require_POST
def delete_post_view(request: HttpRequest, post_id: str) -> HttpResponse:
	post = get_object_or_404(Post, id=post_id, deleted_at__isnull=True)
	if request.user.actor.id != post.author_id:
		messages.error(request, "You can only delete your own posts.")
		return redirect("posts:detail", post_id=post_id)

	post.deleted_at = timezone.now()
	post.save(update_fields=["deleted_at", "updated_at"])
	messages.success(request, "Post deleted.")
	return redirect("home")


@ratelimit(key="user_or_ip", rate="60/h", block=True)
@login_required
@require_POST
def edit_comment_view(request: HttpRequest, comment_id: str) -> HttpResponse:
	comment = get_object_or_404(Comment.objects.select_related("post"), id=comment_id, deleted_at__isnull=True)
	if request.user.actor.id != comment.author_id:
		messages.error(request, "You can only edit your own comments.")
		return redirect("posts:detail", post_id=comment.post_id)

	content = request.POST.get("content", "").strip()
	if not content:
		messages.error(request, "Comment cannot be empty.")
		return redirect("posts:detail", post_id=comment.post_id)
	if len(content) > 2000:
		messages.error(request, "Comment is too long (max 2000 characters).")
		return redirect("posts:detail", post_id=comment.post_id)

	comment.content = content
	comment.save(update_fields=["content", "updated_at"])
	messages.success(request, "Comment updated.")
	return redirect("posts:detail", post_id=comment.post_id)


@ratelimit(key="user_or_ip", rate="60/h", block=True)
@login_required
@require_POST
def delete_comment_view(request: HttpRequest, comment_id: str) -> HttpResponse:
	comment = get_object_or_404(Comment.objects.select_related("post"), id=comment_id, deleted_at__isnull=True)
	if request.user.actor.id != comment.author_id:
		messages.error(request, "You can only delete your own comments.")
		return redirect("posts:detail", post_id=comment.post_id)

	comment.deleted_at = timezone.now()
	comment.save(update_fields=["deleted_at", "updated_at"])
	messages.success(request, "Comment deleted.")
	return redirect("posts:detail", post_id=comment.post_id)

