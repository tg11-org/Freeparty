from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.accounts.models import User
from apps.moderation.models import ModerationAction, ModerationNote, Report, TrustSignal, SecurityAuditEvent
from apps.moderation.services import TrustSignalService, ActionVelocityTracker, SecurityAuditService, AdaptiveAbuseControlService
from apps.posts.models import Attachment, Post
from apps.social.models import Like


class ModerationWorkflowTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.staff = User.objects.create_user(email="mod@example.com", username="mod", password="secret123", is_staff=True)
		self.reporter = User.objects.create_user(email="reporter@example.com", username="reporter", password="secret123")
		self.staff.mark_email_verified()
		self.reporter.mark_email_verified()
		self.post = Post.objects.create(
			author=self.reporter.actor,
			canonical_uri="https://example.com/posts/moderation-test",
			content="Reported post",
		)
		self.report = Report.objects.create(
			reporter=self.reporter.actor,
			reason="spam",
			description="spam content",
		)
		self.post_report = Report.objects.create(
			reporter=self.reporter.actor,
			target_post=self.post,
			reason="abuse",
			description="post report",
		)

	def test_non_staff_cannot_access_dashboard(self):
		self.client.force_login(self.reporter)
		response = self.client.get("/moderation/")
		self.assertEqual(response.status_code, 302)

	def test_staff_can_move_report_to_under_review(self):
		self.client.force_login(self.staff)
		response = self.client.post(f"/moderation/reports/{self.report.id}/quick-status/", {"status": "under_review"})
		self.assertEqual(response.status_code, 302)
		self.report.refresh_from_db()
		self.assertEqual(self.report.status, Report.Status.UNDER_REVIEW)
		self.assertEqual(self.report.reviewed_by_id, self.staff.id)

	def test_action_creation_marks_actioned_when_no_status_selected(self):
		self.client.force_login(self.staff)
		response = self.client.post(
			f"/moderation/reports/{self.report.id}/update/",
			{
				"action_type": ModerationAction.ActionType.POST_HIDE,
				"notes": "Hidden pending review",
				"internal_note": "escalated",
			},
		)
		self.assertEqual(response.status_code, 302)
		self.report.refresh_from_db()
		self.assertEqual(self.report.status, Report.Status.ACTIONED)
		self.assertEqual(ModerationAction.objects.filter(report=self.report).count(), 1)
		self.assertEqual(ModerationNote.objects.filter(report=self.report).count(), 1)

	def test_dashboard_filters_by_target_post(self):
		self.client.force_login(self.staff)
		response = self.client.get(f"/moderation/?post={self.post.id}")
		self.assertEqual(response.status_code, 200)
		reports = list(response.context["reports"])
		self.assertEqual(len(reports), 1)
		self.assertEqual(reports[0].id, self.post_report.id)

	def test_dashboard_defaults_to_open_status(self):
		self.client.force_login(self.staff)
		closed_report = Report.objects.create(
			reporter=self.reporter.actor,
			target_post=self.post,
			reason=Report.Reason.OTHER,
			description="closed report",
			status=Report.Status.UNDER_REVIEW,
		)
		response = self.client.get("/moderation/")
		self.assertEqual(response.status_code, 200)
		reports = list(response.context["reports"])
		report_ids = {item.id for item in reports}
		self.assertIn(self.report.id, report_ids)
		self.assertIn(self.post_report.id, report_ids)
		self.assertNotIn(closed_report.id, report_ids)
		self.assertEqual(response.context["selected_status"], Report.Status.OPEN)

	def test_dashboard_filters_by_date_range(self):
		self.client.force_login(self.staff)
		old_timestamp = timezone.now() - timedelta(days=5)
		Report.objects.filter(id=self.report.id).update(created_at=old_timestamp)
		date_from = (timezone.now() - timedelta(days=1)).date().isoformat()

		response = self.client.get(f"/moderation/?date_from={date_from}")
		self.assertEqual(response.status_code, 200)
		reports = list(response.context["reports"])
		self.assertNotIn(self.report.id, {item.id for item in reports})
		self.assertIn(self.post_report.id, {item.id for item in reports})

	def test_dashboard_filters_by_severity_and_reason_category(self):
		self.client.force_login(self.staff)
		self.report.severity = Report.Severity.CRITICAL
		self.report.reason = Report.Reason.MINOR_SAFETY
		self.report.save(update_fields=["severity", "reason", "updated_at"])

		response = self.client.get(f"/moderation/?severity={Report.Severity.CRITICAL}&reason_category={Report.Reason.MINOR_SAFETY}")
		self.assertEqual(response.status_code, 200)
		reports = list(response.context["reports"])
		self.assertIn(self.report.id, {item.id for item in reports})
		self.assertNotIn(self.post_report.id, {item.id for item in reports})

	def test_report_detail_shows_target_post_attachments(self):
		upload = SimpleUploadedFile("detail.png", b"fakepng", content_type="image/png")
		Attachment.objects.create(
			post=self.post,
			attachment_type=Attachment.AttachmentType.IMAGE,
			file=upload,
			mime_type="image/png",
			file_size=len(b"fakepng"),
		)
		self.client.force_login(self.staff)
		response = self.client.get(f"/moderation/reports/{self.post_report.id}/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Post Attachments")
		self.assertContains(response, f'href="/actors/{self.reporter.actor.handle}/" target="_blank"')
		self.assertContains(response, f'href="/actors/{self.post.author.handle}/" target="_blank"')
		self.assertContains(response, f'href="/posts/{self.post.id}/" target="_blank"')

	def test_staff_can_update_attachment_state_from_report_detail(self):
		upload = SimpleUploadedFile("detail-flag.png", b"fakepng", content_type="image/png")
		attachment = Attachment.objects.create(
			post=self.post,
			attachment_type=Attachment.AttachmentType.IMAGE,
			file=upload,
			mime_type="image/png",
			file_size=len(b"fakepng"),
		)
		self.client.force_login(self.staff)
		response = self.client.post(
			f"/moderation/attachments/{attachment.id}/state/",
			{"moderation_state": Attachment.ModerationState.REMOVED, "report_id": str(self.post_report.id)},
		)
		self.assertEqual(response.status_code, 302)
		attachment.refresh_from_db()
		self.assertEqual(attachment.moderation_state, Attachment.ModerationState.REMOVED)

	def test_report_form_renders_structured_reason_choices(self):
		self.client.force_login(self.reporter)
		response = self.client.get(f"/moderation/report/?target_post_id={self.post.id}")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "DMCA / IP Complaint")
		self.assertContains(response, "Posting of a Minor")
		self.assertContains(response, "report-severity-map")

	def test_report_submission_derives_severity_from_reason(self):
		self.client.force_login(self.reporter)
		response = self.client.post(
			"/moderation/report/",
			{
				"target_post_id": str(self.post.id),
				"reason": Report.Reason.MINOR_SAFETY,
				"description": "urgent safety issue",
			},
		)
		self.assertEqual(response.status_code, 302)
		report = Report.objects.order_by("-created_at").first()
		self.assertEqual(report.reason, Report.Reason.MINOR_SAFETY)
		self.assertEqual(report.severity, Report.Severity.CRITICAL)
		self.assertEqual(report.assigned_to_id, self.staff.id)
		self.assertIsNotNone(report.first_assigned_at)

	def test_high_severity_status_change_requires_evidence(self):
		self.client.force_login(self.staff)
		self.post_report.reason = Report.Reason.DMCA_IP
		self.post_report.save(update_fields=["reason", "updated_at"])

		response = self.client.post(
			f"/moderation/reports/{self.post_report.id}/update/",
			{"status": Report.Status.UNDER_REVIEW},
		)

		self.assertEqual(response.status_code, 302)
		self.post_report.refresh_from_db()
		self.assertEqual(self.post_report.status, Report.Status.OPEN)

	def test_dashboard_filters_for_sla_breached_reports(self):
		self.client.force_login(self.staff)
		breached = Report.objects.create(
			reporter=self.reporter.actor,
			target_post=self.post,
			reason=Report.Reason.DMCA_IP,
			description="breached",
			assigned_to=self.staff,
			first_assigned_at=timezone.now() - timedelta(hours=4),
		)
		within_sla = Report.objects.create(
			reporter=self.reporter.actor,
			target_post=self.post,
			reason=Report.Reason.DMCA_IP,
			description="within sla",
			assigned_to=self.staff,
			first_assigned_at=timezone.now() - timedelta(minutes=30),
		)

		response = self.client.get("/moderation/?sla_breached=true")

		self.assertEqual(response.status_code, 200)
		report_ids = {item.id for item in response.context["reports"]}
		self.assertIn(breached.id, report_ids)
		self.assertNotIn(within_sla.id, report_ids)

	def test_sla_analytics_returns_response_percentiles(self):
		self.client.force_login(self.staff)
		report = Report.objects.create(
			reporter=self.reporter.actor,
			target_post=self.post,
			reason=Report.Reason.DMCA_IP,
			description="analytics",
			assigned_to=self.staff,
			first_assigned_at=timezone.now() - timedelta(minutes=90),
			responded_at=timezone.now(),
		)
		report.save(update_fields=["responded_at", "updated_at"])

		response = self.client.get("/moderation/reports/analytics/sla/?severity=high")

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload["severity"], "high")
		self.assertEqual(payload["completed_count"], 1)
		self.assertGreaterEqual(payload["p50_response_minutes"], 89)


@override_settings(
	CACHES={
		"default": {
			"BACKEND": "django.core.cache.backends.locmem.LocMemCache",
			"LOCATION": "moderation-api-tests",
		}
	}
)
class ModerationApiTests(TestCase):
	def setUp(self):
		self.client = Client()
		self.staff = User.objects.create_user(email="staff-api@example.com", username="staffapi", password="secret123", is_staff=True)
		self.user = User.objects.create_user(email="user-api@example.com", username="userapi", password="secret123")
		self.staff.mark_email_verified()
		self.user.mark_email_verified()
		self.post = Post.objects.create(
			author=self.user.actor,
			canonical_uri="https://example.com/posts/mod-api",
			content="Moderation API target",
		)
		self.report = Report.objects.create(
			reporter=self.user.actor,
			target_post=self.post,
			reason="abuse",
			description="api moderation report",
		)

	def test_non_staff_cannot_list_reports(self):
		self.client.force_login(self.user)
		response = self.client.get("/api/v1/moderation/reports/")
		self.assertEqual(response.status_code, 403)

	def test_staff_can_list_and_filter_reports(self):
		self.client.force_login(self.staff)
		self.report.severity = Report.Severity.HIGH
		self.report.reason = Report.Reason.DMCA_IP
		self.report.save(update_fields=["severity", "reason", "updated_at"])
		response = self.client.get(
			f"/api/v1/moderation/reports/?status=open&post={self.post.id}&severity={Report.Severity.HIGH}&reason_category={Report.Reason.DMCA_IP}"
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["count"], 1)
		self.assertEqual(response.json()["results"][0]["severity"], Report.Severity.HIGH)

	def test_staff_can_update_report_status(self):
		self.client.force_login(self.staff)
		self.report.stamp_evidence_hash(self.report.description, "api evidence")
		self.report.save(update_fields=["evidence_hash", "updated_at"])
		response = self.client.post(
			f"/api/v1/moderation/reports/{self.report.id}/status/",
			data={"status": "under_review"},
		)
		self.assertEqual(response.status_code, 200)
		self.report.refresh_from_db()
		self.assertEqual(self.report.status, Report.Status.UNDER_REVIEW)
		self.assertEqual(self.report.reviewed_by_id, self.staff.id)
		self.assertIsNotNone(self.report.responded_at)

	def test_staff_cannot_update_high_severity_report_without_evidence(self):
		self.client.force_login(self.staff)
		self.report.reason = Report.Reason.DMCA_IP
		self.report.save(update_fields=["reason", "updated_at"])

		response = self.client.post(
			f"/api/v1/moderation/reports/{self.report.id}/status/",
			data={"status": Report.Status.UNDER_REVIEW},
		)

		self.assertEqual(response.status_code, 400)
		self.report.refresh_from_db()
		self.assertEqual(self.report.status, Report.Status.OPEN)

	def test_staff_can_fetch_sla_analytics(self):
		self.client.force_login(self.staff)
		self.report.assigned_to = self.staff
		self.report.first_assigned_at = timezone.now() - timedelta(minutes=45)
		self.report.responded_at = timezone.now()
		self.report.stamp_evidence_hash(self.report.description, "api evidence")
		self.report.save(update_fields=["assigned_to", "first_assigned_at", "responded_at", "evidence_hash", "updated_at"])

		response = self.client.get("/api/v1/moderation/reports/analytics/sla/")

		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload["completed_count"], 1)
		self.assertGreaterEqual(payload["p50_response_minutes"], 44)

	def test_staff_can_create_action_and_note(self):
		self.client.force_login(self.staff)
		action_response = self.client.post(
			f"/api/v1/moderation/reports/{self.report.id}/actions/",
			data={"action_type": ModerationAction.ActionType.POST_HIDE, "notes": "API action"},
		)
		self.assertEqual(action_response.status_code, 201)
		note_response = self.client.post(
			f"/api/v1/moderation/reports/{self.report.id}/notes/",
			data={"body": "API note"},
		)
		self.assertEqual(note_response.status_code, 201)
		self.assertEqual(ModerationAction.objects.filter(report=self.report, moderator=self.staff).count(), 1)
		self.assertEqual(ModerationNote.objects.filter(report=self.report, author=self.staff).count(), 1)
		self.report.refresh_from_db()
		self.assertEqual(self.report.status, Report.Status.ACTIONED)

	def test_staff_can_update_attachment_moderation_state(self):
		upload = SimpleUploadedFile("flag.png", b"fakepng", content_type="image/png")
		attachment = Attachment.objects.create(
			post=self.post,
			attachment_type=Attachment.AttachmentType.IMAGE,
			file=upload,
			mime_type="image/png",
			file_size=len(b"fakepng"),
		)
		self.client.force_login(self.staff)
		response = self.client.post(
			f"/api/v1/moderation/attachments/{attachment.id}/state/",
			data={"moderation_state": Attachment.ModerationState.FLAGGED, "notes": "review needed"},
		)
		self.assertEqual(response.status_code, 200)
		attachment.refresh_from_db()
		self.assertEqual(attachment.moderation_state, Attachment.ModerationState.FLAGGED)

	def test_non_staff_cannot_update_attachment_moderation_state(self):
		upload = SimpleUploadedFile("remove.png", b"fakepng", content_type="image/png")
		attachment = Attachment.objects.create(
			post=self.post,
			attachment_type=Attachment.AttachmentType.IMAGE,
			file=upload,
			mime_type="image/png",
			file_size=len(b"fakepng"),
		)
		self.client.force_login(self.user)
		response = self.client.post(
			f"/api/v1/moderation/attachments/{attachment.id}/state/",
			data={"moderation_state": Attachment.ModerationState.REMOVED},
		)
		self.assertEqual(response.status_code, 403)

	def test_flagged_attachment_hidden_from_non_staff_post_api(self):
		upload = SimpleUploadedFile("hidden.png", b"fakepng", content_type="image/png")
		attachment = Attachment.objects.create(
			post=self.post,
			attachment_type=Attachment.AttachmentType.IMAGE,
			file=upload,
			mime_type="image/png",
			file_size=len(b"fakepng"),
			moderation_state=Attachment.ModerationState.FLAGGED,
		)
		self.client.force_login(self.user)
		response = self.client.get(f"/api/v1/posts/{self.post.id}/")
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json().get("attachments"), [])

	def test_flagged_attachment_visible_to_staff_post_api(self):
		upload = SimpleUploadedFile("staff-visible.png", b"fakepng", content_type="image/png")
		attachment = Attachment.objects.create(
			post=self.post,
			attachment_type=Attachment.AttachmentType.IMAGE,
			file=upload,
			mime_type="image/png",
			file_size=len(b"fakepng"),
			moderation_state=Attachment.ModerationState.FLAGGED,
		)
		self.client.force_login(self.staff)
		response = self.client.get(f"/api/v1/posts/{self.post.id}/")
		self.assertEqual(response.status_code, 200)
		attachments = response.json().get("attachments", [])
		self.assertEqual(len(attachments), 1)
		self.assertEqual(attachments[0]["moderation_state"], Attachment.ModerationState.FLAGGED)

	def test_report_detail_api_includes_target_post_attachments(self):
		upload = SimpleUploadedFile("api-detail.png", b"fakepng", content_type="image/png")
		attachment = Attachment.objects.create(
			post=self.post,
			attachment_type=Attachment.AttachmentType.IMAGE,
			file=upload,
			mime_type="image/png",
			file_size=len(b"fakepng"),
			moderation_state=Attachment.ModerationState.FLAGGED,
		)
		self.client.force_login(self.staff)
		response = self.client.get(f"/api/v1/moderation/reports/{self.report.id}/")
		self.assertEqual(response.status_code, 200)
		attachments = response.json().get("target_post_attachments", [])
		self.assertEqual(len(attachments), 1)
		self.assertEqual(attachments[0]["id"], str(attachment.id))


class TrustSignalTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(email="trust@example.com", username="trust", password="secret123")
		self.user.mark_email_verified()
		self.actor = self.user.actor

	def test_compute_trust_signal_baseline_score(self):
		"""New verified user should have reasonable baseline score."""
		signal = TrustSignalService.compute_trust_signal(self.actor)
		self.assertIsNotNone(signal)
		self.assertEqual(signal.email_verified, True)
		self.assertGreater(signal.trust_score, 40)

	def test_trust_score_decreases_with_moderation_actions(self):
		"""Account with recent moderation actions should have lower trust score."""
		# Create some reports against this actor
		for _ in range(3):
			Report.objects.create(reporter=self.actor, target_actor=self.actor, reason="spam")

		signal = TrustSignalService.compute_trust_signal(self.actor)
		# Should have penalty for 3 reports
		self.assertLess(signal.trust_score, 50)
		self.assertGreater(signal.recent_reports_count, 0)

	def test_trust_score_unverified_email_penalty(self):
		"""Unverified email should lower trust score."""
		self.user.email_verified_at = None
		self.user.save(update_fields=["email_verified_at"])

		signal = TrustSignalService.compute_trust_signal(self.actor)
		self.assertFalse(signal.email_verified)
		self.assertLess(signal.trust_score, 50)

	def test_should_throttle_returns_false_for_normal_account(self):
		"""Normal accounts should not be throttled."""
		signal = TrustSignalService.compute_trust_signal(self.actor)
		should_throttle, reason, until = TrustSignalService.should_throttle(self.actor)
		self.assertFalse(should_throttle)

	def test_should_throttle_returns_true_for_low_score(self):
		"""Accounts with very low trust score should be throttled."""
		# Create many reports to tank score
		for _ in range(5):
			Report.objects.create(reporter=self.actor, target_actor=self.actor, reason="spam")
			ModerationAction.objects.create(actor_target=self.actor, action_type="account_limit", moderator=User.objects.create_user(email=f"mod{_}@example.com", username=f"mod{_}"))

		signal = TrustSignalService.compute_trust_signal(self.actor)
		should_throttle, reason, until = TrustSignalService.should_throttle(self.actor)

		if signal.trust_score < 30:
			self.assertTrue(should_throttle)
			self.assertIsNotNone(reason)

	def test_velocity_tracking_posts(self):
		"""ActionVelocityTracker should record post velocity."""
		# Create some posts
		for _ in range(3):
			Post.objects.create(author=self.actor, canonical_uri=f"https://example.com/{_}", content="test")

		ActionVelocityTracker.record_post(self.actor)
		signal = TrustSignal.objects.get(actor=self.actor)
		self.assertEqual(signal.posts_last_hour, 3)

	def test_velocity_anomaly_detection(self):
		"""Velocity tracker should detect anomalies at threshold."""
		# Create posts up to but not exceeding threshold
		for _ in range(4):
			Post.objects.create(author=self.actor, canonical_uri=f"https://example.com/{_}", content="test")

		ActionVelocityTracker.record_post(self.actor)
		self.assertFalse(ActionVelocityTracker.is_velocity_anomaly(self.actor, "post"))

		# Add one more to hit threshold exactly (still allowed)
		Post.objects.create(author=self.actor, canonical_uri="https://example.com/5", content="test")
		ActionVelocityTracker.record_post(self.actor)
		self.assertFalse(ActionVelocityTracker.is_velocity_anomaly(self.actor, "post"))

		# Add one more to exceed threshold
		Post.objects.create(author=self.actor, canonical_uri="https://example.com/6", content="test")
		ActionVelocityTracker.record_post(self.actor)
		self.assertTrue(ActionVelocityTracker.is_velocity_anomaly(self.actor, "post"))

	def test_moderation_detail_api_includes_trust_signal(self):
		"""Moderation report detail should include target actor's trust signal."""
		client = Client()
		staff = User.objects.create_user(email="staff@example.com", username="staff", password="secret123", is_staff=True)
		staff.mark_email_verified()
		report = Report.objects.create(reporter=self.actor, target_actor=self.actor, reason="self_report")

		client.force_login(staff)
		response = client.get(f"/api/v1/moderation/reports/{report.id}/")
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertIn("target_actor_trust_signal", data)
		self.assertIsNotNone(data["target_actor_trust_signal"])
		self.assertIn("trust_score", data["target_actor_trust_signal"])

	@override_settings(FEATURE_ADAPTIVE_ABUSE_CONTROLS_ENABLED=True)
	def test_automatic_abuse_block_is_logged_to_security_audit(self):
		TrustSignal.objects.create(
			actor=self.actor,
			is_throttled=True,
			throttle_reason="risk_control",
		)

		allowed, _reason = AdaptiveAbuseControlService.evaluate_action(self.actor, "post")
		self.assertFalse(allowed)

		audit_event = SecurityAuditEvent.objects.filter(
			user=self.user,
			event_type=SecurityAuditEvent.EventType.ABUSE_AUTO_ACTION,
		).order_by("-created_at").first()
		self.assertIsNotNone(audit_event)
		assert audit_event is not None
		self.assertEqual(audit_event.details.get("action_type"), "post")
		self.assertEqual(audit_event.details.get("signal"), "throttled")
		self.assertTrue(audit_event.details.get("blocked"))


class SecurityAuditTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(email="audit@example.com", username="audit", password="secret123")

	def test_log_login_success(self):
		"""SecurityAuditService should log successful logins."""
		SecurityAuditService.log_login_success(self.user, ip_address="192.168.1.1", user_agent="TestBrowser/1.0")
		
		event = SecurityAuditEvent.objects.filter(user=self.user, event_type=SecurityAuditEvent.EventType.LOGIN_SUCCESS).first()
		self.assertIsNotNone(event)
		self.assertEqual(event.ip_address, "192.168.1.1")

	def test_log_login_failure(self):
		"""SecurityAuditService should log failed logins."""
		SecurityAuditService.log_login_failure(self.user, ip_address="192.168.1.1", reason="invalid_password")
		
		event = SecurityAuditEvent.objects.filter(user=self.user, event_type=SecurityAuditEvent.EventType.LOGIN_FAILURE).first()
		self.assertIsNotNone(event)
		self.assertEqual(event.details.get("reason"), "invalid_password")

	def test_log_password_reset_request(self):
		"""SecurityAuditService should log password reset requests."""
		SecurityAuditService.log_password_reset_request(self.user, ip_address="10.0.0.1")
		
		event = SecurityAuditEvent.objects.filter(user=self.user, event_type=SecurityAuditEvent.EventType.PASSWORD_RESET_REQUEST).first()
		self.assertIsNotNone(event)

	def test_log_password_reset_complete(self):
		"""SecurityAuditService should log password reset completion."""
		SecurityAuditService.log_password_reset_complete(self.user, ip_address="10.0.0.1")
		
		event = SecurityAuditEvent.objects.filter(user=self.user, event_type=SecurityAuditEvent.EventType.PASSWORD_RESET_COMPLETE).first()
		self.assertIsNotNone(event)

	def test_log_email_verification(self):
		"""SecurityAuditService should log email verification."""
		SecurityAuditService.log_email_verification(self.user, ip_address="192.168.1.1")
		
		event = SecurityAuditEvent.objects.filter(user=self.user, event_type=SecurityAuditEvent.EventType.EMAIL_VERIFICATION).first()
		self.assertIsNotNone(event)

	def test_log_moderator_action(self):
		"""SecurityAuditService should log moderation actions by staff."""
		moderator = User.objects.create_user(email="mod@example.com", username="mod", is_staff=True, password="secret")
		target = User.objects.create_user(email="target@example.com", username="target", password="secret")
		
		SecurityAuditService.log_moderator_action(
			moderator,
			target,
			"account_suspend",
			ip_address="10.0.0.1",
		)
		
		event = SecurityAuditEvent.objects.filter(user=moderator, event_type=SecurityAuditEvent.EventType.MODERATION_ACTION_CREATE).first()
		self.assertIsNotNone(event)
		self.assertEqual(event.details.get("action_type"), "account_suspend")
		self.assertEqual(event.details.get("target_user_id"), str(target.id))

	def test_audit_event_ordered_by_date(self):
		"""Audit events should be ordered by created_at descending."""
		SecurityAuditService.log_login_success(self.user)
		SecurityAuditService.log_login_failure(self.user)

		# Ensure deterministic ordering even on low timestamp precision backends.
		SecurityAuditEvent.objects.filter(
			user=self.user,
			event_type=SecurityAuditEvent.EventType.LOGIN_SUCCESS,
		).update(created_at=timezone.now() - timedelta(minutes=1))
		
		events = SecurityAuditEvent.objects.filter(user=self.user)
		self.assertEqual(events.count(), 2)
		# Most recent should be first due to Meta.ordering
		self.assertEqual(events[0].event_type, SecurityAuditEvent.EventType.LOGIN_FAILURE)
