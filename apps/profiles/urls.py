from django.urls import path

from apps.profiles.views import edit_profile_view

app_name = "profiles"

urlpatterns = [
    path("me/edit/", edit_profile_view, name="edit"),
]
