from django.urls import path

from apps.profiles.views import edit_profile_links_view, edit_profile_view, public_profile_links_view

app_name = "profiles"

urlpatterns = [
    path("", edit_profile_view, name="index"),
    path("me/edit/", edit_profile_view, name="edit"),
    path("me/links/", edit_profile_links_view, name="links_edit"),
    path("<str:handle>/links/", public_profile_links_view, name="public_links"),
]
