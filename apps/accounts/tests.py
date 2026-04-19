from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccountActionToken, User
from apps.accounts.services import AccountLifecycleService, VerificationService
from apps.accounts.tasks import _deliver_transactional_email, send_password_reset_email
from apps.core.models import AsyncTaskExecution


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

	@patch("apps.accounts.tasks.send_mail")
	def test_password_reset_task_records_reliable_execution(self, mock_send_mail):
		send_password_reset_email.run(
			subject="Reset",
			message="Body",
			recipient_email="user@example.com",
			correlation_id="corr-reset-1",
		)
		mock_send_mail.assert_called_once()
		execution = AsyncTaskExecution.objects.filter(task_name=send_password_reset_email.name).first()
		self.assertIsNotNone(execution)
		assert execution is not None
		self.assertEqual(execution.status, AsyncTaskExecution.Status.SUCCEEDED)

	@patch("apps.accounts.tasks.send_mail")
	def test_password_reset_task_is_idempotent_for_same_payload(self, mock_send_mail):
		payload = {
			"subject": "Reset",
			"message": "Body",
			"recipient_email": "user@example.com",
			"correlation_id": "corr-reset-2",
		}
		send_password_reset_email.run(**payload)
		send_password_reset_email.run(**payload)

		self.assertEqual(mock_send_mail.call_count, 1)
		execution = AsyncTaskExecution.objects.get(task_name=send_password_reset_email.name)
		self.assertEqual(execution.status, AsyncTaskExecution.Status.SUCCEEDED)
		self.assertEqual(execution.attempt_count, 1)


class SignupLegalConsentTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.signup_url = reverse("accounts:signup")

	def test_signup_requires_terms_and_guidelines_checkboxes(self):
		response = self.client.post(
			self.signup_url,
			{
				"email": "consent1@example.com",
				"username": "consent1",
				"display_name": "Consent User",
				"password1": "secret12345",
				"password2": "secret12345",
			},
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "You must accept the Terms of Service.")
		self.assertContains(response, "You must accept the Community Guidelines.")
		self.assertFalse(User.objects.filter(email="consent1@example.com").exists())

	@override_settings(LEGAL_TOS_VERSION="1.2", LEGAL_GUIDELINES_VERSION="1.3")
	def test_signup_persists_legal_acceptance_timestamps_and_versions(self):
		response = self.client.post(
			self.signup_url,
			{
				"email": "consent2@example.com",
				"username": "consent2",
				"display_name": "Consent User 2",
				"password1": "secret12345",
				"password2": "secret12345",
				"accept_tos": "on",
				"accept_guidelines": "on",
			},
		)
		self.assertEqual(response.status_code, 302)
		user = User.objects.get(email="consent2@example.com")
		self.assertIsNotNone(user.tos_accepted_at)
		self.assertIsNotNone(user.guidelines_accepted_at)
		assert user.tos_accepted_at is not None
		assert user.guidelines_accepted_at is not None
		self.assertLessEqual(user.tos_accepted_at, timezone.now())
		self.assertLessEqual(user.guidelines_accepted_at, timezone.now())
		self.assertEqual(user.tos_version_accepted, "1.2")
		self.assertEqual(user.guidelines_version_accepted, "1.3")


class AccountLifecycleFlowTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.user = User.objects.create_user(email="life@example.com", username="lifeuser", password="secret123")
		self.user.mark_email_verified()

	def test_deactivation_flow_sets_retention_and_sends_recovery_email(self):
		self.client.force_login(self.user)
		response = self.client.post(
			reverse("accounts:manage"),
			{"action": "deactivate", "confirm_deactivate": "on"},
		)
		self.assertEqual(response.status_code, 302)
		self.user.refresh_from_db()
		self.assertFalse(self.user.is_active)
		self.assertIsNotNone(self.user.deactivated_at)
		self.assertIsNotNone(self.user.deactivation_recovery_deadline_at)
		self.assertEqual(len(mail.outbox), 1)
		self.assertIn("reactivation", mail.outbox[0].subject.lower())

	def test_deletion_request_flow_sets_schedule_and_sends_cancel_email(self):
		self.client.force_login(self.user)
		response = self.client.post(
			reverse("accounts:manage"),
			{"action": "delete", "confirm_delete": "on"},
		)
		self.assertEqual(response.status_code, 302)
		self.user.refresh_from_db()
		self.assertFalse(self.user.is_active)
		self.assertIsNotNone(self.user.deletion_requested_at)
		self.assertIsNotNone(self.user.deletion_scheduled_for_at)
		self.assertEqual(len(mail.outbox), 1)
		self.assertIn("deletion", mail.outbox[0].subject.lower())

	def test_reactivate_and_cancel_delete_links_restore_account(self):
		self.user.request_account_deletion(retention_days=30)
		token = AccountLifecycleService.create_action_token(
			user=self.user,
			action=AccountActionToken.ActionType.CANCEL_DELETION,
			ttl_hours=24,
		)
		response = self.client.get(reverse("accounts:cancel-account-deletion", kwargs={"token": token}))
		self.assertEqual(response.status_code, 302)
		self.user.refresh_from_db()
		self.assertTrue(self.user.is_active)
		self.assertIsNone(self.user.deletion_requested_at)

		self.user.deactivate_account(retention_days=365)
		token2 = AccountLifecycleService.create_action_token(
			user=self.user,
			action=AccountActionToken.ActionType.REACTIVATE,
			ttl_hours=24,
		)
		response2 = self.client.get(reverse("accounts:reactivate-account", kwargs={"token": token2}))
		self.assertEqual(response2.status_code, 302)
		self.user.refresh_from_db()
		self.assertTrue(self.user.is_active)
		self.assertIsNone(self.user.deactivated_at)
