from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from django.shortcuts import render


def custom_404(request, exception=None):
    return render(request, "404.html", status=404)


handler404 = "config.urls.custom_404"

def trigger_error(request):
    division_by_zero = 1 / 0

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
    urlpatterns += [path("sentry-debug/", trigger_error)]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns()
