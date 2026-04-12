from django.urls import path

from apps.actors.views import actor_detail_view

app_name = "actors"

urlpatterns = [
    path("<str:handle>/", actor_detail_view, name="detail"),
]
