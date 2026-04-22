from django.urls import path

from apps.social.views import (
	approve_follow_request_view,
	bookmark_toggle_view,
	bookmarks_view,
	block_view,
	dislike_toggle_view,
	follow_view,
	follow_requests_view,
	like_toggle_view,
	my_blocked_view,
	my_followers_view,
	my_following_view,
	my_social_hub_view,
	my_muted_view,
	my_reports_view,
	reject_follow_request_view,
	report_actor_view,
	repost_toggle_view,
	social_index_view,
	unblock_view,
	unfollow_view,
)

app_name = "social"

urlpatterns = [
	path("", social_index_view, name="index"),
	path("follow/<str:handle>/", follow_view, name="follow"),
	path("unfollow/<str:handle>/", unfollow_view, name="unfollow"),
	path("block/<str:handle>/", block_view, name="block"),
	path("unblock/<str:handle>/", unblock_view, name="unblock"),
	path("like/<uuid:post_id>/", like_toggle_view, name="like-toggle"),
	path("dislike/<uuid:post_id>/", dislike_toggle_view, name="dislike-toggle"),
	path("repost/<uuid:post_id>/", repost_toggle_view, name="repost-toggle"),
	path("bookmark/<uuid:post_id>/", bookmark_toggle_view, name="bookmark-toggle"),
	path("bookmarks/", bookmarks_view, name="bookmarks"),
	path("report-actor/<str:handle>/", report_actor_view, name="report-actor"),
	path("follow-requests/", follow_requests_view, name="follow-requests"),
	path("follow-requests/<uuid:follow_id>/approve/", approve_follow_request_view, name="approve-follow-request"),
	path("follow-requests/<uuid:follow_id>/reject/", reject_follow_request_view, name="reject-follow-request"),
	path("my/", my_social_hub_view, name="my-index"),
	path("my/following/", my_following_view, name="my-following"),
	path("my/followers/", my_followers_view, name="my-followers"),
	path("my/blocked/", my_blocked_view, name="my-blocked"),
	path("my/muted/", my_muted_view, name="my-muted"),
	path("my/reports/", my_reports_view, name="my-reports"),
]
