from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("actors/", include("apps.actors.urls")),
    path("profiles/", include("apps.profiles.urls")),
    path("posts/", include("apps.posts.urls")),
    path("social/", include("apps.social.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("moderation/", include("apps.moderation.urls")),
    path("api/v1/", include("config.api_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns()
