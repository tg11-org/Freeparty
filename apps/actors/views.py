from django.db import models
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.actors.models import Actor
from apps.core.pagination import paginate_queryset
from apps.core.permissions import can_view_actor
from apps.posts.models import Post
from apps.social.models import Block, Follow, Like, Repost


@require_http_methods(["GET"])
def actor_detail_view(request: HttpRequest, handle: str) -> HttpResponse:
	try:
		actor = Actor.objects.select_related("profile").get(handle=handle, state=Actor.ActorState.ACTIVE)
	except Actor.DoesNotExist as exc:
		raise Http404("Actor not found") from exc
	viewer = request.user.actor if request.user.is_authenticated and hasattr(request.user, "actor") else None
	if not can_view_actor(viewer, actor):
		raise Http404("Actor not found")

	posts_qs = Post.objects.filter(
		author=actor, deleted_at__isnull=True, moderation_state=Post.ModerationState.NORMAL
	).select_related("author", "author__profile").order_by("-created_at")
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
	reposted_ids = set()

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
			is_blocked_by_me = Block.objects.filter(blocker=my_actor, blocked=actor).exists()
			is_blocked_by_them = Block.objects.filter(blocker=actor, blocked=my_actor).exists()
		liked_ids = set(Like.objects.filter(actor=my_actor, post__in=posts).values_list("post_id", flat=True))
		reposted_ids = set(Repost.objects.filter(actor=my_actor, post__in=posts).values_list("post_id", flat=True))

	return render(request, "actors/detail.html", {
		"actor": actor,
		"posts": posts,
		"page_obj": page_obj,
		"follower_count": follower_count,
		"following_count": following_count,
		"is_following": is_following,
		"is_follow_pending": is_follow_pending,
		"is_blocked_by_me": is_blocked_by_me,
		"is_blocked_by_them": is_blocked_by_them,
		"show_follower_count": show_follower_count,
		"show_following_count": show_following_count,
		"liked_ids": liked_ids,
		"reposted_ids": reposted_ids,
	})


@require_http_methods(["GET"])
def search_view(request: HttpRequest) -> HttpResponse:
	query = request.GET.get("q", "").strip()
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
			content__icontains=query,
			visibility=Post.Visibility.PUBLIC,
			deleted_at__isnull=True,
			moderation_state=Post.ModerationState.NORMAL,
		).select_related("author", "author__profile").order_by("-created_at")
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
	reposted_ids: set = set()
	if request.user.is_authenticated and posts:
		from apps.social.models import Like, Repost
		post_ids = [p.id for p in posts]
		liked_ids = set(Like.objects.filter(actor=request.user.actor, post_id__in=post_ids).values_list("post_id", flat=True))
		reposted_ids = set(Repost.objects.filter(actor=request.user.actor, post_id__in=post_ids).values_list("post_id", flat=True))
	return render(request, "actors/search.html", {
		"query": query,
		"actor_results": actors,
		"post_results": posts,
		"actors_page_obj": actors_page_obj,
		"posts_page_obj": posts_page_obj,
		"liked_ids": liked_ids,
		"reposted_ids": reposted_ids,
		"query_string": f"q={query}",
	})
