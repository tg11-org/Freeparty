from django.urls import path

from apps.profiles.views import (
    approve_parental_change_view,
    edit_profile_links_view,
    edit_profile_view,
    guardian_linked_minors_view,
    guardian_manage_linked_minor_view,
    guardian_manage_minor_view,
    public_profile_links_view,
    verify_guardian_email_view,
)

app_name = "profiles"

urlpatterns = [
    path("", edit_profile_view, name="index"),
    path("me/edit/", edit_profile_view, name="edit"),
    path("me/links/", edit_profile_links_view, name="links_edit"),
    path("guardian/verify/<str:token>/", verify_guardian_email_view, name="verify_guardian_email"),
    path("guardian/manage/<str:token>/", guardian_manage_minor_view, name="guardian_manage"),
    path("guardian/approve/<str:token>/", approve_parental_change_view, name="approve_parental_change"),
    path("guardian/minors/", guardian_linked_minors_view, name="guardian_minors"),
    path("guardian/minors/<uuid:profile_id>/", guardian_manage_linked_minor_view, name="guardian_manage_linked_minor"),
    path("<str:handle>/links/", public_profile_links_view, name="public_links"),
]
