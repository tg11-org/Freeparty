from django.urls import path

from apps.posts.views import (
	add_comment_view,
	create_post_view,
	delete_comment_view,
	delete_post_view,
	edit_comment_view,
	edit_post_view,
	post_detail_view,
	public_posts_view,
)

app_name = "posts"

urlpatterns = [
	path("new/", create_post_view, name="create"),
	path("public/", public_posts_view, name="public"),
	path("<uuid:post_id>/", post_detail_view, name="detail"),
	path("<uuid:post_id>/edit/", edit_post_view, name="edit"),
	path("<uuid:post_id>/delete/", delete_post_view, name="delete"),
	path("<uuid:post_id>/comment/", add_comment_view, name="add-comment"),
	path("comments/<uuid:comment_id>/edit/", edit_comment_view, name="edit-comment"),
	path("comments/<uuid:comment_id>/delete/", delete_comment_view, name="delete-comment"),
]
