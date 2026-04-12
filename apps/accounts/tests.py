from django.core.exceptions import ValidationError
from django.test import TestCase

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
