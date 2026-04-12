from django.db import IntegrityError
from django.test import TestCase

from apps.accounts.models import User
from apps.social.models import Follow


class FollowTests(TestCase):
	def setUp(self):
		self.user_a = User.objects.create_user(email="a@example.com", username="usera", password="secret123")
		self.user_b = User.objects.create_user(email="b@example.com", username="userb", password="secret123")

	def test_follow_unique_constraint(self):
		Follow.objects.create(
			follower=self.user_a.actor,
			followee=self.user_b.actor,
			state=Follow.FollowState.ACCEPTED,
		)
		with self.assertRaises(IntegrityError):
			Follow.objects.create(
				follower=self.user_a.actor,
				followee=self.user_b.actor,
				state=Follow.FollowState.ACCEPTED,
			)

	def test_prevent_self_follow_constraint(self):
		with self.assertRaises(IntegrityError):
			Follow.objects.create(
				follower=self.user_a.actor,
				followee=self.user_a.actor,
				state=Follow.FollowState.ACCEPTED,
			)
