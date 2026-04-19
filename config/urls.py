from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from django.shortcuts import render


def handler404(request, exception=None):
    return render(request, "404.html", status=404)


handler404 = handler404  # noqa: F811 — registers with Django's URL resolver

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("actors/", include("apps.actors.urls")),
    path("profiles/", include("apps.profiles.urls")),
    path("posts/", include("apps.posts.urls")),
    path("social/", include("apps.social.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("messages/", include("apps.private_messages.urls")),
    path("moderation/", include("apps.moderation.urls")),
    path("api/v1/", include("config.api_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns()
