from django.urls import path

from apps.actors.views import actor_detail_view, actor_followers_view, actor_following_view, search_view

app_name = "actors"

urlpatterns = [
	path("", search_view, name="index"),
	path("search/", search_view, name="search"),
	path("<str:handle>/", actor_detail_view, name="detail"),
	path("<str:handle>/followers/", actor_followers_view, name="followers"),
	path("<str:handle>/following/", actor_following_view, name="following"),
]
