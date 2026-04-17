from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.services import VerificationService
from apps.accounts.tasks import _deliver_transactional_email, send_password_reset_email


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


class PasswordResetAsyncDeliveryTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(
			email="reset@example.com",
			username="resetuser",
			password="secret123",
		)

	@override_settings(
		CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
		RATELIMIT_USE_CACHE="default",
	)
	@patch("apps.accounts.forms.send_password_reset_email.delay")
	def test_password_reset_request_enqueues_transactional_task(self, mock_delay):
		response = self.client.post(
			reverse("accounts:password-reset"),
			{"email": self.user.email},
		)

		self.assertRedirects(response, reverse("accounts:password-reset-done"))
		self.assertEqual(mock_delay.call_count, 1)
		kwargs = mock_delay.call_args.kwargs
		self.assertEqual(kwargs["recipient_email"], self.user.email)
		self.assertEqual(kwargs["from_email"], settings.DEFAULT_FROM_EMAIL)
		self.assertIn("password-reset/", kwargs["message"])


class TransactionalEmailTaskTests(TestCase):
	def test_password_reset_email_task_uses_retry_backoff_defaults(self):
		self.assertEqual(send_password_reset_email.autoretry_for, (Exception,))
		self.assertEqual(send_password_reset_email.retry_backoff, True)
		self.assertEqual(send_password_reset_email.retry_backoff_max, 300)
		self.assertEqual(send_password_reset_email.retry_jitter, True)

	@override_settings(DEFAULT_FROM_EMAIL="noreply+tests@freeparty.local")
	@patch("apps.accounts.tasks.send_mail")
	def test_delivery_helper_uses_default_sender_metadata(self, mock_send_mail):
		task = SimpleNamespace(
			name="apps.accounts.tasks.send_system_email",
			max_retries=5,
			request=SimpleNamespace(retries=0, id="task-1"),
		)

		_deliver_transactional_email(
			task=task,
			subject="System email",
			message="Body",
			recipient_list=["user@example.com"],
		)

		mock_send_mail.assert_called_once()
		self.assertEqual(mock_send_mail.call_args.kwargs["from_email"], "noreply+tests@freeparty.local")

	@patch("apps.accounts.tasks.send_mail", side_effect=TimeoutError("smtp timeout"))
	def test_delivery_helper_logs_retry_scheduled_on_transient_failure(self, _mock_send_mail):
		task = SimpleNamespace(
			name="apps.accounts.tasks.send_system_email",
			max_retries=5,
			request=SimpleNamespace(retries=0, id="task-2"),
		)

		with self.assertLogs("apps.core.services.email_observability", level="INFO") as logs:
			with self.assertRaises(TimeoutError):
				_deliver_transactional_email(
					task=task,
					subject="System email",
					message="Body",
					recipient_list=["user@example.com"],
				)

		joined = "\n".join(logs.output)
		self.assertIn("event=failure", joined)
		self.assertIn("event=retry_scheduled", joined)
		self.assertIn("will_retry=True", joined)
