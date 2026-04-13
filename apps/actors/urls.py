from django.urls import path

from apps.actors.views import actor_detail_view, search_view

app_name = "actors"

urlpatterns = [
	path("search/", search_view, name="search"),
	path("<str:handle>/", actor_detail_view, name="detail"),
]
