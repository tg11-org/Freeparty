import re

from django.conf import settings
from django.db import models
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.actors.models import Actor
from apps.core.pagination import paginate_queryset
from apps.core.permissions import can_view_actor
from apps.posts.hashtags import extract_hashtags
from apps.posts.models import Post
from apps.social.models import Block, Bookmark, Dislike, Follow, Like, Repost
from apps.private_messages.services import get_parental_dm_restriction_error


@require_http_methods(["GET"])
def actor_detail_view(request: HttpRequest, handle: str) -> HttpResponse:
	try:
		actor = Actor.objects.select_related("profile").get(handle=handle, state=Actor.ActorState.ACTIVE)
	except Actor.DoesNotExist as exc:
		raise Http404("Actor not found") from exc
	viewer = request.user.actor if request.user.is_authenticated and hasattr(request.user, "actor") else None
	blocked_context = {
		"is_blocked_by_me": False,
		"is_blocked_by_them": False,
	}
	if viewer is not None and viewer.id != actor.id:
		blocked_context["is_blocked_by_me"] = Block.objects.filter(blocker=viewer, blocked=actor).exists()
		blocked_context["is_blocked_by_them"] = Block.objects.filter(blocker=actor, blocked=viewer).exists()
		if blocked_context["is_blocked_by_me"] or blocked_context["is_blocked_by_them"]:
			return render(request, "actors/blocked.html", {"actor": actor, **blocked_context})
	if not can_view_actor(viewer, actor):
		if getattr(actor.profile, "is_private_account", False):
			return render(request, "actors/blocked.html", {"actor": actor, **blocked_context})
		raise Http404("Actor not found")

	active_filter = request.GET.get("filter", "posts")
	if active_filter not in ("posts", "reposts", "media", "links"):
		active_filter = "posts"

	repost_posts = None
	if active_filter == "reposts":
		repost_ids = Repost.objects.filter(actor=actor).order_by("-created_at").values_list("post_id", flat=True)
		posts_qs = Post.objects.filter(
			id__in=repost_ids, deleted_at__isnull=True, moderation_state=Post.ModerationState.NORMAL
		).select_related("author", "author__profile", "link_preview").order_by("-created_at")
	elif active_filter == "media":
		posts_qs = Post.objects.filter(
			author=actor, deleted_at__isnull=True, moderation_state=Post.ModerationState.NORMAL,
			attachments__isnull=False,
		).distinct().select_related("author", "author__profile", "link_preview").order_by("-created_at")
	elif active_filter == "links":
		posts_qs = Post.objects.filter(
			author=actor, deleted_at__isnull=True, moderation_state=Post.ModerationState.NORMAL,
			link_preview__isnull=False,
		).select_related("author", "author__profile", "link_preview").order_by("-created_at")
	else:
		posts_qs = Post.objects.filter(
			author=actor, deleted_at__isnull=True, moderation_state=Post.ModerationState.NORMAL
		).select_related("author", "author__profile", "link_preview").order_by("-created_at")

	page_obj = paginate_queryset(request, posts_qs, per_page=20, page_param="page")
	posts = page_obj.object_list

	follower_count = actor.follower_relations.filter(state=Follow.FollowState.ACCEPTED).count()
	following_count = actor.following_relations.filter(state=Follow.FollowState.ACCEPTED).count()
	show_follower_count = getattr(actor.profile, "show_follower_count", True)
	show_following_count = getattr(actor.profile, "show_following_count", True)

	is_following = False
	is_follow_pending = False
	is_blocked_by_me = False
	is_blocked_by_them = False
	liked_ids = set()
	disliked_ids = set()
	reposted_ids = set()
	bookmarked_ids = set()

	if request.user.is_authenticated and hasattr(request.user, "actor"):
		my_actor = request.user.actor
		if my_actor.id == actor.id:
			show_follower_count = True
			show_following_count = True
		if my_actor.id != actor.id:
			relation = Follow.objects.filter(
				follower=my_actor,
				followee=actor,
			).first()
			is_following = bool(relation and relation.state == Follow.FollowState.ACCEPTED)
			is_follow_pending = bool(relation and relation.state == Follow.FollowState.PENDING)
			is_blocked_by_me = blocked_context["is_blocked_by_me"]
			is_blocked_by_them = blocked_context["is_blocked_by_them"]
		liked_ids = set(Like.objects.filter(actor=my_actor, post__in=posts).values_list("post_id", flat=True))
		disliked_ids = set(Dislike.objects.filter(actor=my_actor, post__in=posts).values_list("post_id", flat=True))
		reposted_ids = set(Repost.objects.filter(actor=my_actor, post__in=posts).values_list("post_id", flat=True))
		bookmarked_ids = set(Bookmark.objects.filter(actor=my_actor, post__in=posts).values_list("post_id", flat=True))

	dm_restriction_reason = ""
	if request.user.is_authenticated and hasattr(request.user, "actor") and request.user.actor.id != actor.id:
		dm_restriction_reason = get_parental_dm_restriction_error(actor=request.user.actor, target_actor=actor) or ""
	can_start_dm = bool(request.user.is_authenticated and hasattr(request.user, "actor") and request.user.actor.id != actor.id and not dm_restriction_reason)

	return render(request, "actors/detail.html", {
		"actor": actor,
		"posts": posts,
		"page_obj": page_obj,
		"active_filter": active_filter,
		"filter_tabs": [("posts", "Posts"), ("reposts", "Reposts"), ("media", "Images & Video"), ("links", "Links")],
		"query_string": f"filter={active_filter}" if active_filter != "posts" else "",
		"follower_count": follower_count,
		"following_count": following_count,
		"is_following": is_following,
		"is_follow_pending": is_follow_pending,
		"is_blocked_by_me": is_blocked_by_me,
		"is_blocked_by_them": is_blocked_by_them,
		"show_follower_count": show_follower_count,
		"show_following_count": show_following_count,
		"liked_ids": liked_ids,
		"disliked_ids": disliked_ids,
		"reposted_ids": reposted_ids,
		"bookmarked_ids": bookmarked_ids,
		"can_start_dm": can_start_dm,
		"dm_restriction_reason": dm_restriction_reason,
	})


@require_http_methods(["GET"])
def search_view(request: HttpRequest) -> HttpResponse:
	query = request.GET.get("q", "").strip()
	hashtag_terms = extract_hashtags(query)
	viewer = request.user.actor if request.user.is_authenticated and hasattr(request.user, "actor") else None
	actors = []
	posts = []
	if query and len(query) >= 2:
		followed_ids = []
		if viewer is not None:
			followed_ids = Follow.objects.filter(
				follower=viewer,
				state=Follow.FollowState.ACCEPTED,
			).values_list("followee_id", flat=True)
		actors_qs = Actor.objects.filter(
			handle__icontains=query, state=Actor.ActorState.ACTIVE
		).select_related("profile")
		if viewer is None:
			actors_qs = actors_qs.filter(profile__is_private_account=False)
		else:
			actors_qs = actors_qs.filter(
				models.Q(profile__is_private_account=False) | models.Q(id__in=followed_ids) | models.Q(id=viewer.id)
			)
		if viewer is not None:
			blocked_by_me = Block.objects.filter(blocker=viewer).values_list("blocked_id", flat=True)
			blocked_me = Block.objects.filter(blocked=viewer).values_list("blocker_id", flat=True)
			actors_qs = actors_qs.exclude(id__in=blocked_by_me).exclude(id__in=blocked_me)
		posts_qs = Post.objects.filter(
			visibility=Post.Visibility.PUBLIC,
			deleted_at__isnull=True,
			moderation_state=Post.ModerationState.NORMAL,
		).select_related("author", "author__profile", "link_preview").order_by("-created_at")
		if hashtag_terms:
			if getattr(settings, "FEATURE_INDEXED_HASHTAG_SEARCH_ENABLED", True):
				for tag in hashtag_terms:
					posts_qs = posts_qs.filter(post_hashtags__hashtag__tag=tag)
				posts_qs = posts_qs.distinct()
			else:
				for tag in hashtag_terms:
					posts_qs = posts_qs.filter(content__iregex=rf"#{re.escape(tag)}(?![A-Za-z0-9_])")
		else:
			posts_qs = posts_qs.filter(content__icontains=query)
		if viewer is None:
			posts_qs = posts_qs.filter(author__profile__is_private_account=False)
		else:
			posts_qs = posts_qs.filter(
				models.Q(author__profile__is_private_account=False)
				| models.Q(author_id__in=followed_ids)
				| models.Q(author_id=viewer.id)
			)
		if viewer is not None:
			blocked_by_me = Block.objects.filter(blocker=viewer).values_list("blocked_id", flat=True)
			blocked_me = Block.objects.filter(blocked=viewer).values_list("blocker_id", flat=True)
			posts_qs = posts_qs.exclude(author_id__in=blocked_by_me).exclude(author_id__in=blocked_me)
		actors_page_obj = paginate_queryset(request, actors_qs, per_page=12, page_param="people_page")
		posts_page_obj = paginate_queryset(request, posts_qs, per_page=10, page_param="posts_page")
		actors = actors_page_obj.object_list
		posts = posts_page_obj.object_list
	else:
		actors_page_obj = None
		posts_page_obj = None
	liked_ids: set = set()
	disliked_ids: set = set()
	reposted_ids: set = set()
	bookmarked_ids: set = set()
	if request.user.is_authenticated and posts:
		from apps.social.models import Bookmark, Dislike, Like, Repost
		post_ids = [p.id for p in posts]
		liked_ids = set(Like.objects.filter(actor=request.user.actor, post_id__in=post_ids).values_list("post_id", flat=True))
		disliked_ids = set(Dislike.objects.filter(actor=request.user.actor, post_id__in=post_ids).values_list("post_id", flat=True))
		reposted_ids = set(Repost.objects.filter(actor=request.user.actor, post_id__in=post_ids).values_list("post_id", flat=True))
		bookmarked_ids = set(Bookmark.objects.filter(actor=request.user.actor, post_id__in=post_ids).values_list("post_id", flat=True))
	return render(request, "actors/search.html", {
		"query": query,
		"actor_results": actors,
		"post_results": posts,
		"actors_page_obj": actors_page_obj,
		"posts_page_obj": posts_page_obj,
		"liked_ids": liked_ids,
		"disliked_ids": disliked_ids,
		"reposted_ids": reposted_ids,
		"bookmarked_ids": bookmarked_ids,
		"query_string": f"q={query}",
	})


@require_http_methods(["GET"])
def actor_followers_view(request: HttpRequest, handle: str) -> HttpResponse:
	try:
		actor = Actor.objects.select_related("profile").get(handle=handle, state=Actor.ActorState.ACTIVE)
	except Actor.DoesNotExist as exc:
		raise Http404("Actor not found") from exc
	viewer = request.user.actor if request.user.is_authenticated and hasattr(request.user, "actor") else None
	if not can_view_actor(viewer, actor):
		raise Http404("Actor not found")
	is_own = viewer is not None and viewer.id == actor.id
	show_list = getattr(actor.profile, "show_follower_list", True) or is_own
	if not show_list:
		raise Http404("Follower list is private")
	qs = (
		Follow.objects.filter(followee=actor, state=Follow.FollowState.ACCEPTED)
		.select_related("follower", "follower__profile")
		.order_by("-created_at")
	)
	page_obj = paginate_queryset(request, qs, per_page=30, page_param="page")
	return render(request, "actors/follower_list.html", {
		"actor": actor,
		"page_obj": page_obj,
		"relations": page_obj.object_list,
		"list_type": "followers",
	})


@require_http_methods(["GET"])
def actor_following_view(request: HttpRequest, handle: str) -> HttpResponse:
	try:
		actor = Actor.objects.select_related("profile").get(handle=handle, state=Actor.ActorState.ACTIVE)
	except Actor.DoesNotExist as exc:
		raise Http404("Actor not found") from exc
	viewer = request.user.actor if request.user.is_authenticated and hasattr(request.user, "actor") else None
	if not can_view_actor(viewer, actor):
		raise Http404("Actor not found")
	is_own = viewer is not None and viewer.id == actor.id
	show_list = getattr(actor.profile, "show_following_list", True) or is_own
	if not show_list:
		raise Http404("Following list is private")
	qs = (
		Follow.objects.filter(follower=actor, state=Follow.FollowState.ACCEPTED)
		.select_related("followee", "followee__profile")
		.order_by("-created_at")
	)
	page_obj = paginate_queryset(request, qs, per_page=30, page_param="page")
	return render(request, "actors/follower_list.html", {
		"actor": actor,
		"page_obj": page_obj,
		"relations": page_obj.object_list,
		"list_type": "following",
	})
