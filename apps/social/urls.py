from django.urls import path

from apps.social.views import (
	approve_follow_request_view,
	bookmark_toggle_view,
	bookmarks_view,
	block_view,
	follow_view,
	follow_requests_view,
	like_toggle_view,
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
	path("repost/<uuid:post_id>/", repost_toggle_view, name="repost-toggle"),
	path("bookmark/<uuid:post_id>/", bookmark_toggle_view, name="bookmark-toggle"),
	path("bookmarks/", bookmarks_view, name="bookmarks"),
	path("report-actor/<str:handle>/", report_actor_view, name="report-actor"),
	path("follow-requests/", follow_requests_view, name="follow-requests"),
	path("follow-requests/<uuid:follow_id>/approve/", approve_follow_request_view, name="approve-follow-request"),
	path("follow-requests/<uuid:follow_id>/reject/", reject_follow_request_view, name="reject-follow-request"),
]
