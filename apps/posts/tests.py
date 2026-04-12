from django.test import Client, TestCase

from apps.accounts.models import User
from apps.core.services.uris import post_uri
from apps.posts.models import Post


class PostTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(email="poster@example.com", username="poster", password="secret123")
		self.user.mark_email_verified()

	def test_post_creation(self):
		actor = self.user.actor
		post = Post.objects.create(
			author=actor,
			content="Hello world",
			canonical_uri=post_uri("temp"),
		)
		post.canonical_uri = post_uri(post.id)
		post.save(update_fields=["canonical_uri", "updated_at"])
		self.assertEqual(Post.objects.count(), 1)
		self.assertEqual(post.author, actor)

	def test_public_posts_view(self):
		Post.objects.create(
			author=self.user.actor,
			content="Public message",
			canonical_uri=post_uri("public-1"),
		)
		response = Client().get("/posts/public/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Public message")
