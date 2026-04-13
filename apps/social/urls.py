from django.urls import path

from apps.social.views import (
	block_view,
	follow_view,
	like_toggle_view,
	report_actor_view,
	repost_toggle_view,
	unblock_view,
	unfollow_view,
)

app_name = "social"

urlpatterns = [
	path("follow/<str:handle>/", follow_view, name="follow"),
	path("unfollow/<str:handle>/", unfollow_view, name="unfollow"),
	path("block/<str:handle>/", block_view, name="block"),
	path("unblock/<str:handle>/", unblock_view, name="unblock"),
	path("like/<uuid:post_id>/", like_toggle_view, name="like-toggle"),
	path("repost/<uuid:post_id>/", repost_toggle_view, name="repost-toggle"),
	path("report-actor/<str:handle>/", report_actor_view, name="report-actor"),
]
