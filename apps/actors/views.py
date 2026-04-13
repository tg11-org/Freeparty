from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.actors.models import Actor
from apps.posts.models import Post
from apps.social.models import Block, Follow, Like, Repost


@require_http_methods(["GET"])
def actor_detail_view(request: HttpRequest, handle: str) -> HttpResponse:
	try:
		actor = Actor.objects.select_related("profile").get(handle=handle, state=Actor.ActorState.ACTIVE)
	except Actor.DoesNotExist as exc:
		raise Http404("Actor not found") from exc

	posts = Post.objects.filter(
		author=actor, deleted_at__isnull=True, moderation_state=Post.ModerationState.NORMAL
	).select_related("author", "author__profile").order_by("-created_at")[:20]

	follower_count = actor.follower_relations.filter(state=Follow.FollowState.ACCEPTED).count()
	following_count = actor.following_relations.filter(state=Follow.FollowState.ACCEPTED).count()
	show_follower_count = getattr(actor.profile, "show_follower_count", True)
	show_following_count = getattr(actor.profile, "show_following_count", True)

	is_following = False
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
			is_following = Follow.objects.filter(
				follower=my_actor, followee=actor, state=Follow.FollowState.ACCEPTED
			).exists()
			is_blocked_by_me = Block.objects.filter(blocker=my_actor, blocked=actor).exists()
			is_blocked_by_them = Block.objects.filter(blocker=actor, blocked=my_actor).exists()
		liked_ids = set(Like.objects.filter(actor=my_actor, post__in=posts).values_list("post_id", flat=True))
		reposted_ids = set(Repost.objects.filter(actor=my_actor, post__in=posts).values_list("post_id", flat=True))

	return render(request, "actors/detail.html", {
		"actor": actor,
		"posts": posts,
		"follower_count": follower_count,
		"following_count": following_count,
		"is_following": is_following,
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
	actors = []
	posts = []
	if query and len(query) >= 2:
		actors = Actor.objects.filter(
			handle__icontains=query, state=Actor.ActorState.ACTIVE
		).select_related("profile")[:20]
		posts = Post.objects.filter(
			content__icontains=query,
			visibility=Post.Visibility.PUBLIC,
			deleted_at__isnull=True,
			moderation_state=Post.ModerationState.NORMAL,
		).select_related("author", "author__profile").order_by("-created_at")[:20]
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
		"liked_ids": liked_ids,
		"reposted_ids": reposted_ids,
	})
