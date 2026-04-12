from django.urls import path

from apps.posts.views import create_post_view, public_posts_view

app_name = "posts"

urlpatterns = [
    path("new/", create_post_view, name="create"),
    path("public/", public_posts_view, name="public"),
]
