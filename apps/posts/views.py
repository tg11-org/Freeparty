from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from django_ratelimit.decorators import ratelimit

from apps.core.pagination import paginate_queryset
from apps.core.permissions import (
	can_comment_on_post,
	can_delete_comment,
	can_delete_post,
	can_edit_comment,
	can_edit_post,
	can_view_post,
)
from apps.core.services.uris import post_uri
from apps.notifications.models import Notification
from apps.notifications.services import create_notification_if_new, notify_mentions
from apps.posts.forms import PostForm
from apps.posts.models import Attachment, Comment, CommentEditHistory, Post, PostEditHistory
from apps.social.models import Bookmark, Like, Repost
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

	form = PostForm(request.POST or None, request.FILES or None)
	if request.method == "POST" and form.is_valid():
		post = form.save(commit=False)
		post.author = actor
		post.canonical_uri = post_uri(post.id)
		post.save()

		upload = form.cleaned_data.get("attachment")
		if upload:
			content_type = getattr(upload, "content_type", "") or "application/octet-stream"
			attachment_type = (
				Attachment.AttachmentType.IMAGE
				if content_type.startswith("image/")
				else Attachment.AttachmentType.VIDEO
			)
			Attachment.objects.create(
				post=post,
				attachment_type=attachment_type,
				file=upload,
				alt_text=form.cleaned_data.get("attachment_alt_text", ""),
				caption=form.cleaned_data.get("attachment_caption", ""),
				mime_type=content_type,
				file_size=getattr(upload, "size", 0),
			)
		messages.success(request, "Post published.")
		notify_mentions(content=post.content, source_actor=actor, source_post=post)
		return redirect("home")

	return render(request, "posts/create_post.html", {"form": form})


@require_http_methods(["GET"])
def public_posts_view(request: HttpRequest) -> HttpResponse:
	actor = request.user.actor if request.user.is_authenticated and hasattr(request.user, "actor") else None
	active_tab = request.GET.get("tab", "all").strip().lower()
	if active_tab not in {"all", "media"}:
		active_tab = "all"
	posts_qs = public_timeline(actor=actor, limit=None)
	if active_tab == "media":
		posts_qs = posts_qs.filter(
			attachments__attachment_type__in=["image", "video"],
			attachments__moderation_state="normal",
		).distinct()
	page_obj = paginate_queryset(request, posts_qs, per_page=20, page_param="page")
	posts = page_obj.object_list
	liked_ids = set()
	reposted_ids = set()
	bookmarked_ids = set()
	if request.user.is_authenticated and hasattr(request.user, "actor"):
		actor = request.user.actor
		liked_ids = set(Like.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
		reposted_ids = set(Repost.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
		bookmarked_ids = set(Bookmark.objects.filter(actor=actor, post__in=posts).values_list("post_id", flat=True))
	return render(request, "posts/public_list.html", {
		"posts": posts,
		"page_obj": page_obj,
		"liked_ids": liked_ids,
		"reposted_ids": reposted_ids,
		"bookmarked_ids": bookmarked_ids,
		"active_tab": active_tab,
		"query_string": f"tab={active_tab}" if active_tab != "all" else "",
	})


@require_http_methods(["GET"])
def post_detail_view(request: HttpRequest, post_id: str) -> HttpResponse:
	post = get_object_or_404(Post.objects.select_related("author"), id=post_id)
	actor = request.user.actor if request.user.is_authenticated and hasattr(request.user, "actor") else None
	if not can_view_post(actor, post):
		messages.error(request, "You do not have access to that post.")
		return redirect("home")
	comments = post.comments.filter(deleted_at__isnull=True).select_related("author", "author__profile")
	liked_ids = set()
	reposted_ids = set()
	bookmarked_ids = set()
	if actor is not None:
		liked_ids = set(Like.objects.filter(actor=actor, post=post).values_list("post_id", flat=True))
		reposted_ids = set(Repost.objects.filter(actor=actor, post=post).values_list("post_id", flat=True))
		bookmarked_ids = set(Bookmark.objects.filter(actor=actor, post=post).values_list("post_id", flat=True))
	return render(request, "posts/detail.html", {
		"post": post,
		"comments": comments,
		"liked_ids": liked_ids,
		"reposted_ids": reposted_ids,
		"bookmarked_ids": bookmarked_ids,
	})


@ratelimit(key="user_or_ip", rate="60/h", block=True)
@login_required
@require_POST
def add_comment_view(request: HttpRequest, post_id: str) -> HttpResponse:
	post = get_object_or_404(Post, id=post_id)
	actor = request.user.actor
	if not can_comment_on_post(actor, post):
		messages.error(request, "You cannot comment on that post.")
		return redirect("home")

	content = request.POST.get("content", "").strip()
	if not content:
		messages.error(request, "Comment cannot be empty.")
		return redirect("posts:detail", post_id=post_id)
	if len(content) > 2000:
		messages.error(request, "Comment is too long (max 2000 characters).")
		return redirect("posts:detail", post_id=post_id)
	Comment.objects.create(post=post, author=actor, content=content)
	if post.author != actor:
		create_notification_if_new(
			recipient=post.author,
			source_actor=actor,
			notification_type=Notification.NotificationType.REPLY,
			source_post=post,
		)
	notify_mentions(content=content, source_actor=actor, source_post=post)
	messages.success(request, "Comment added.")
	return redirect("posts:detail", post_id=post_id)


@ratelimit(key="user_or_ip", rate="30/h", block=True)
@login_required
@require_http_methods(["GET", "POST"])
def edit_post_view(request: HttpRequest, post_id: str) -> HttpResponse:
	post = get_object_or_404(Post, id=post_id)
	if not can_edit_post(request.user.actor, post):
		messages.error(request, "You can only edit your own posts.")
		return redirect("posts:detail", post_id=post_id)

	form = PostForm(request.POST or None, instance=post)
	if request.method == "POST" and form.is_valid():
		original_post = Post.objects.only("content", "spoiler_text", "visibility").get(id=post.id)
		previous_content = original_post.content
		previous_spoiler_text = original_post.spoiler_text
		previous_visibility = original_post.visibility
		changed_fields = set(form.changed_data)
		updated_post = form.save()
		if {"content", "spoiler_text", "visibility"}.intersection(changed_fields):
			PostEditHistory.objects.create(
				post=updated_post,
				editor=request.user,
				previous_content=previous_content,
				new_content=updated_post.content,
				previous_spoiler_text=previous_spoiler_text,
				new_spoiler_text=updated_post.spoiler_text,
				previous_visibility=previous_visibility,
				new_visibility=updated_post.visibility,
			)
		messages.success(request, "Post updated.")
		return redirect("posts:detail", post_id=post_id)

	return render(request, "posts/edit_post.html", {"form": form, "post": post})


@ratelimit(key="user_or_ip", rate="60/h", block=True)
@login_required
@require_POST
def delete_post_view(request: HttpRequest, post_id: str) -> HttpResponse:
	post = get_object_or_404(Post, id=post_id)
	if not can_delete_post(request.user.actor, post):
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
	comment = get_object_or_404(Comment.objects.select_related("post"), id=comment_id)
	if not can_edit_comment(request.user.actor, comment):
		messages.error(request, "You can only edit your own comments.")
		return redirect("posts:detail", post_id=comment.post_id)

	content = request.POST.get("content", "").strip()
	if not content:
		messages.error(request, "Comment cannot be empty.")
		return redirect("posts:detail", post_id=comment.post_id)
	if len(content) > 2000:
		messages.error(request, "Comment is too long (max 2000 characters).")
		return redirect("posts:detail", post_id=comment.post_id)

	previous_content = comment.content
	comment.content = content
	comment.is_edited = True
	comment.save(update_fields=["content", "is_edited", "updated_at"])
	if previous_content != content:
		CommentEditHistory.objects.create(
			comment=comment,
			editor=request.user,
			previous_content=previous_content,
			new_content=content,
		)
	messages.success(request, "Comment updated.")
	return redirect("posts:detail", post_id=comment.post_id)


@ratelimit(key="user_or_ip", rate="60/h", block=True)
@login_required
@require_POST
def delete_comment_view(request: HttpRequest, comment_id: str) -> HttpResponse:
	comment = get_object_or_404(Comment.objects.select_related("post"), id=comment_id)
	if not can_delete_comment(request.user.actor, comment):
		messages.error(request, "You can only delete your own comments.")
		return redirect("posts:detail", post_id=comment.post_id)

	comment.deleted_at = timezone.now()
	comment.save(update_fields=["deleted_at", "updated_at"])
	messages.success(request, "Comment deleted.")
	return redirect("posts:detail", post_id=comment.post_id)

