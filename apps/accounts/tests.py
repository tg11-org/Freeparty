from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.services import VerificationService


class UserModelTests(TestCase):
	def test_user_creation_normalizes_identity(self):
		user = User.objects.create_user(email="TeSt@Example.com", username="MyName", password="secret123")
		self.assertEqual(user.email, "TeSt@example.com".lower())
		self.assertEqual(user.username, "myname")

	def test_username_validation(self):
		user = User(email="valid@example.com", username="Invalid-Name")
		with self.assertRaises(ValidationError):
			user.full_clean()

	def test_email_verification_flow(self):
		user = User.objects.create_user(email="verify@example.com", username="verifyuser", password="secret123")
		token = VerificationService.create_token(user)
		verified_user = VerificationService.verify_token(token)
		self.assertIsNotNone(verified_user)
		assert verified_user is not None
		self.assertTrue(verified_user.email_verified)


class LogoutViewTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(
			email="logout@example.com",
			username="logoutuser",
			password="secret123"
		)
		self.logout_url = reverse("accounts:logout")
		self.home_url = reverse("home")

	def test_logout_redirects_to_home(self):
		"""Test that logout view redirects to home page"""
		self.client.login(username="logoutuser", password="secret123")
		response = self.client.post(self.logout_url)
		self.assertRedirects(response, self.home_url)
