from django.urls import path

from apps.social.views import follow_view, unfollow_view

app_name = "social"

urlpatterns = [
    path("follow/<str:handle>/", follow_view, name="follow"),
    path("unfollow/<str:handle>/", unfollow_view, name="unfollow"),
]
