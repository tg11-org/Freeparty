from django.http import HttpResponse
from django.core import mail
from django.core.checks import run_checks
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from unittest.mock import patch

from apps.accounts.models import User
from apps.core.models import AsyncTaskExecution, AsyncTaskFailure
from apps.core.services.email_observability import log_smtp_delivery_event
from apps.notifications.models import Notification
from apps.posts.models import LinkPreview, Post
from apps.private_messages.models import ConversationParticipant
from apps.private_messages.services import create_direct_conversation, store_encrypted_message
from apps.core.templatetags.mention_tags import linkify_mentions

from apps.core.middleware import RequestObservabilityMiddleware
from apps.core.services.task_observability import observe_celery_task
from apps.posts.tasks import unfurl_post_link


class MentionAndHashtagLinkifyTests(SimpleTestCase):
    def test_linkify_mentions_and_hashtags(self):
        rendered = linkify_mentions("Hey @alice check #test")
        self.assertIn('href="/actors/alice/"', rendered)
        self.assertIn('href="/actors/search/?q=%23test"', rendered)

    def test_linkify_multiple_chained_hashtags(self):
        rendered = linkify_mentions("#foo#bar and #woo #hoo")
        self.assertIn('href="/actors/search/?q=%23foo"', rendered)
        self.assertIn('href="/actors/search/?q=%23bar"', rendered)
        self.assertIn('href="/actors/search/?q=%23woo"', rendered)
        self.assertIn('href="/actors/search/?q=%23hoo"', rendered)

    def test_linkify_http_url(self):
        rendered = linkify_mentions("Read https://example.com/path?q=1")
        self.assertIn('href="https://example.com/path?q=1"', rendered)
        self.assertIn('target="_blank"', rendered)
        self.assertIn('>https://example.com/path?q=1</a>', rendered)

    def test_linkify_www_url_adds_https_href(self):
        rendered = linkify_mentions("Visit www.example.com now")
        self.assertIn('href="https://www.example.com"', rendered)
        self.assertIn('>www.example.com</a>', rendered)

    def test_linkify_bare_domain_adds_https_href(self):
        rendered = linkify_mentions("Check tg11.org/news")
        self.assertIn('href="https://tg11.org/news"', rendered)
        self.assertIn('>tg11.org/news</a>', rendered)

    def test_linkify_url_excludes_trailing_punctuation(self):
        rendered = linkify_mentions("Visit https://example.com/test).")
        self.assertIn('href="https://example.com/test"', rendered)
        self.assertIn('</a>).', rendered)

    def test_email_domain_is_not_linkified(self):
        rendered = linkify_mentions("Email hello@tg11.org for support")
        self.assertNotIn('href="https://tg11.org"', rendered)
        self.assertIn('hello@tg11.org', rendered)

    def test_linkify_escapes_html_outside_links(self):
        rendered = linkify_mentions('<script>alert(1)</script> https://example.com')
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', rendered)
        self.assertIn('href="https://example.com"', rendered)
        self.assertNotIn('<script>', rendered)


class ProductionConfigGuardrailChecksTests(SimpleTestCase):
    @override_settings(
        DEBUG=True,
        SECRET_KEY="change-me",
        ALLOWED_HOSTS=["localhost", "127.0.0.1"],
        CSRF_TRUSTED_ORIGINS=[],
        SITE_DOMAIN="localhost",
    )
    def test_production_checks_fail_for_unsafe_defaults(self):
        with patch.dict("os.environ", {"DJANGO_SETTINGS_MODULE": "config.settings.production"}):
            errors = run_checks(tags=["security"], include_deployment_checks=True)

        error_ids = {error.id for error in errors}
        self.assertIn("core.E001", error_ids)
        self.assertIn("core.E002", error_ids)
        self.assertIn("core.E003", error_ids)
        self.assertIn("core.E004", error_ids)
        self.assertIn("core.E006", error_ids)

    @override_settings(
        DEBUG=False,
        SECRET_KEY="A2z5x9m1Q8p4r7t0V3k6n2d9L5b8w1Y4",
        ALLOWED_HOSTS=["freeparty.tg11.org"],
        CSRF_TRUSTED_ORIGINS=["https://freeparty.tg11.org"],
        SITE_DOMAIN="freeparty.tg11.org",
    )
    def test_production_checks_pass_for_safe_configuration(self):
        with patch.dict("os.environ", {"DJANGO_SETTINGS_MODULE": "config.settings.production"}):
            errors = run_checks(tags=["security"], include_deployment_checks=True)

        guardrail_errors = [error for error in errors if error.id and error.id.startswith("core.E")]
        self.assertEqual(guardrail_errors, [])


class RequestObservabilityMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_generates_request_id_header_when_missing(self):
        request = self.factory.get("/health/live/")
        middleware = RequestObservabilityMiddleware(lambda _: HttpResponse("ok"))

        response = middleware(request)

        self.assertIn("X-Request-ID", response)
        self.assertTrue(response["X-Request-ID"])

    def test_preserves_incoming_request_id_header(self):
        request = self.factory.get("/health/live/", HTTP_X_REQUEST_ID="abc-123")
        middleware = RequestObservabilityMiddleware(lambda _: HttpResponse("ok"))

        response = middleware(request)

        self.assertEqual(response["X-Request-ID"], "abc-123")

    @override_settings(REQUEST_SLOW_MS=0)
    def test_logs_warning_for_slow_request_threshold(self):
        request = self.factory.get("/health/live/")
        middleware = RequestObservabilityMiddleware(lambda _: HttpResponse("ok"))

        with self.assertLogs("apps.core.middleware", level="WARNING") as logs:
            middleware(request)

        self.assertTrue(any("slow_request" in message for message in logs.output))

    def test_logs_request_complete_with_correlation_fields(self):
        request = self.factory.get("/health/live/", HTTP_X_REQUEST_ID="trace-123")
        middleware = RequestObservabilityMiddleware(lambda _: HttpResponse("ok", status=204))

        with self.assertLogs("apps.core.middleware", level="INFO") as logs:
            middleware(request)

        joined = "\n".join(logs.output)
        self.assertIn("request_complete", joined)
        self.assertIn("method=GET", joined)
        self.assertIn("path=/health/live/", joined)
        self.assertIn("status=204", joined)
        self.assertIn("request_id=trace-123", joined)

    def test_logs_request_error_with_correlation_fields(self):
        request = self.factory.get("/explode/", HTTP_X_REQUEST_ID="err-123")

        def _raise_error(_):
            raise RuntimeError("boom")

        middleware = RequestObservabilityMiddleware(_raise_error)
        with self.assertLogs("apps.core.middleware", level="ERROR") as logs:
            with self.assertRaises(RuntimeError):
                middleware(request)

        joined = "\n".join(logs.output)
        self.assertIn("request_error", joined)
        self.assertIn("method=GET", joined)
        self.assertIn("path=/explode/", joined)
        self.assertIn("request_id=err-123", joined)


class SecurityHeadersMiddlewareTests(TestCase):
    @override_settings(
        CSP_ENFORCE_ENABLED=True,
        CSP_ENFORCE_POLICY="default-src 'self'; object-src 'none'",
        CSP_REPORT_ONLY_ENABLED=True,
        CSP_REPORT_ONLY_POLICY="default-src 'self'",
        SECURE_REFERRER_POLICY="strict-origin-when-cross-origin",
    )
    def test_sets_enforced_csp_and_skips_report_only_when_enforced(self):
        response = self.client.get("/health/live/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertEqual(response["Content-Security-Policy"], "default-src 'self'; object-src 'none'")
        self.assertNotIn("Content-Security-Policy-Report-Only", response)

    @override_settings(
        CSP_REPORT_ONLY_ENABLED=True,
        CSP_REPORT_ONLY_POLICY="default-src 'self'",
        SECURE_REFERRER_POLICY="strict-origin-when-cross-origin",
    )
    def test_sets_referrer_and_csp_report_only_headers(self):
        response = self.client.get("/health/live/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertEqual(response["Content-Security-Policy-Report-Only"], "default-src 'self'")

    @override_settings(
        CSP_REPORT_ONLY_ENABLED=False,
        CSP_REPORT_ONLY_POLICY="default-src 'self'",
        SECURE_REFERRER_POLICY="strict-origin-when-cross-origin",
    )
    def test_does_not_set_csp_report_only_when_disabled(self):
        response = self.client.get("/health/live/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertNotIn("Content-Security-Policy-Report-Only", response)


class TaskObservabilityTests(SimpleTestCase):
    class _Request:
        def __init__(self, task_id: str):
            self.id = task_id

    class _Task:
        def __init__(self, name: str, task_id: str):
            self.name = name
            self.request = TaskObservabilityTests._Request(task_id)

    def test_observe_celery_task_logs_start_and_success(self):
        task = self._Task("apps.notifications.tasks.process_notification_fanout", "task-123")

        with self.assertLogs("apps.core.services.task_observability", level="INFO") as logs:
            with observe_celery_task(task, correlation_id="req-123"):
                pass

        joined = "\n".join(logs.output)
        self.assertIn("task_start", joined)
        self.assertIn("task_success", joined)
        self.assertIn("task_id=task-123", joined)
        self.assertIn("correlation_id=req-123", joined)

    def test_observe_celery_task_logs_failure(self):
        task = self._Task("apps.federation.tasks.execute_federation_delivery", "task-999")

        with self.assertLogs("apps.core.services.task_observability", level="ERROR") as logs:
            with self.assertRaises(ValueError):
                with observe_celery_task(task, correlation_id="req-999"):
                    raise ValueError("fail")

        joined = "\n".join(logs.output)
        self.assertIn("task_failure", joined)
        self.assertIn("task_id=task-999", joined)
        self.assertIn("correlation_id=req-999", joined)

    def test_smtp_delivery_event_logs_structured_fields(self):
        with self.assertLogs("apps.core.services.email_observability", level="INFO") as logs:
            log_smtp_delivery_event(
                event="retry_scheduled",
                task_name="apps.accounts.tasks.send_verification_email",
                task_id="task-smtp-1",
                correlation_id="req-smtp-1",
                recipient_count=1,
                attempt=2,
                max_retries=5,
                will_retry=True,
                error="SMTPServerDisconnected",
            )
        joined = "\n".join(logs.output)
        self.assertIn("smtp_delivery", joined)
        self.assertIn("event=retry_scheduled", joined)
        self.assertIn("will_retry=True", joined)


class RootPathAndHealthStatusTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="rootpaths@example.com", username="rootpaths", password="secret123")
        self.user.mark_email_verified()

    def test_health_status_page_available(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Service Status")

    def test_health_status_redirects_without_trailing_slash(self):
        response = self.client.get("/health")
        self.assertIn(response.status_code, (301, 302))

    def test_me_redirects_for_anonymous_and_authenticated(self):
        anon = self.client.get("/me/")
        self.assertEqual(anon.status_code, 302)
        self.assertIn("/accounts/login/", anon.headers["Location"])

        self.client.force_login(self.user)
        authed = self.client.get("/me/")
        self.assertEqual(authed.status_code, 302)
        self.assertIn(f"/actors/{self.user.actor.handle}/", authed.headers["Location"])

    def test_app_index_routes_are_available(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/actors/").status_code, 200)
        self.assertEqual(self.client.get("/accounts/").status_code, 200)
        self.assertEqual(self.client.get("/profiles/").status_code, 200)
        self.assertEqual(self.client.get("/social/").status_code, 302)

    def test_static_info_pages_are_available(self):
        for path in ["/about/", "/terms/", "/privacy/", "/guidelines/", "/faq/", "/support/"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, msg=f"Expected 200 for {path}")

    def test_support_form_generates_prefilled_mailto_link(self):
        response = self.client.post(
            "/support/",
            {
                "support_type": "bug",
                "subject_summary": "Cannot send DMs",
                "username": "tester123",
                "email": "tester@example.com",
                "message": "Steps: open convo, send button disabled unexpectedly.",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "mailto:support%40tg11.org", html=False)


class EmailDiagnosticsViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(email="diag@example.com", username="diaguser", password="secret123")
        self.user.mark_email_verified()

    def test_requires_login(self):
        response = self.client.get("/support/email-test/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.headers["Location"])

    def test_requires_staff_or_superuser(self):
        self.client.force_login(self.user)
        response = self.client.get("/support/email-test/")
        self.assertEqual(response.status_code, 403)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@tg11.org",
        EMAIL_HOST="mail.tg11.org",
        EMAIL_PORT=587,
        EMAIL_USE_TLS=True,
        EMAIL_HOST_USER="noreply@tg11.org",
        MAIL_SERVER_HOST="mail.tg11.org",
        MAIL_SERVER_IPV4="45.79.221.81",
        MAIL_SERVER_IPV6="[2600:3c02::2000:81ff:fe85:4b9a]",
    )
    def test_send_attempt_produces_logs_and_queues_mail(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.client.force_login(self.user)
        response = self.client.post(
            "/support/email-test/",
            {
                "subject": "SMTP diagnostics",
                "message": "Testing outbound email diagnostics.",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Run Result: SUCCESS")
        self.assertContains(response, "Endpoint Results")
        self.assertContains(response, "mail.tg11.org")
        self.assertContains(response, "45.79.221.81")
        self.assertContains(response, "2600:3c02::2000:81ff:fe85:4b9a")
        self.assertContains(response, "Email send call returned")
        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(mail.outbox[0].to, ["gage@tg11.org", "skittlesallday12@icloud.com"])


class DeadLetterReplayCommandTests(TestCase):
    @patch("apps.core.management.commands.dead_letter_inspect.current_app")
    def test_replay_failure_requeues_task(self, mocked_current_app):
        from django.core.management import call_command

        task = mocked_current_app.tasks.get.return_value
        failure = AsyncTaskFailure.objects.create(
            task_name="apps.posts.tasks.unfurl_post_link",
            correlation_id="corr-replay-1",
            is_terminal=True,
            terminal_reason="max_retries_exceeded",
            error_message="boom",
            payload={"post_id": "post-1", "args": ["post-1"], "kwargs": {"correlation_id": "corr-replay-1"}},
        )

        call_command("dead_letter_inspect", replay=str(failure.id), operator="phase8-ops", note="safe retry")

        task.apply_async.assert_called_once_with(args=["post-1"], kwargs={"correlation_id": "corr-replay-1"})
        failure.refresh_from_db()
        self.assertEqual(failure.terminal_reason, "manual_replay")
        self.assertEqual(failure.payload["replay_count"], 1)
        self.assertEqual(failure.payload["last_replayed_by"], "phase8-ops")
        self.assertEqual(failure.payload["last_replay_note"], "safe retry")

    def test_replay_requires_operator_attribution(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        failure = AsyncTaskFailure.objects.create(
            task_name="apps.posts.tasks.unfurl_post_link",
            correlation_id="corr-replay-missing-operator",
            is_terminal=True,
            terminal_reason="max_retries_exceeded",
            error_message="boom",
            payload={"post_id": "post-1", "args": ["post-1"]},
        )

        with self.assertRaises(CommandError):
            call_command("dead_letter_inspect", replay=str(failure.id))

    @override_settings(DEAD_LETTER_REPLAY_COOLDOWN_SECONDS=3600)
    @patch("apps.core.management.commands.dead_letter_inspect.current_app")
    def test_replay_respects_cooldown_window(self, mocked_current_app):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        AsyncTaskFailure.objects.create(
            task_name="apps.posts.tasks.unfurl_post_link",
            correlation_id="corr-replay-cooldown",
            is_terminal=True,
            terminal_reason="manual_replay",
            error_message="boom",
            payload={
                "post_id": "post-1",
                "args": ["post-1"],
                "last_replay_at": timezone.now().isoformat(),
                "replay_count": 1,
            },
        )

        failure = AsyncTaskFailure.objects.get(correlation_id="corr-replay-cooldown")
        with self.assertRaises(CommandError):
            call_command("dead_letter_inspect", replay=str(failure.id), operator="phase8-ops")
        mocked_current_app.tasks.get.return_value.apply_async.assert_not_called()


@override_settings(FEATURE_LINK_UNFURL_ENABLED=True)
class LinkUnfurlReliabilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="unfurl-core@example.com", username="unfurlcore", password="secret123")
        self.user.mark_email_verified()
        with patch("apps.posts.tasks.unfurl_post_link.delay"):
            self.post = Post.objects.create(
                author=self.user.actor,
                canonical_uri="https://example.com/posts/unfurl-core-test",
                content="Look https://example.com/demo now",
            )

    @patch("apps.posts.tasks._fetch_unfurl")
    def test_unfurl_task_records_reliable_execution(self, mocked_fetch_unfurl):
        mocked_fetch_unfurl.return_value = {
            "title": "Example",
            "description": "Desc",
            "thumbnail_url": "",
            "site_name": "Example",
            "embed_html": "",
        }

        unfurl_post_link.run(str(self.post.id), correlation_id="corr-unfurl-1")

        self.assertTrue(LinkPreview.objects.filter(post=self.post).exists())
        execution = AsyncTaskExecution.objects.get(
            task_name="apps.posts.tasks.unfurl_post_link",
            idempotency_key=f"link_unfurl:{self.post.id}",
        )
        self.assertEqual(execution.status, AsyncTaskExecution.Status.SUCCEEDED)

    @patch("apps.posts.tasks._fetch_unfurl")
    def test_unfurl_task_is_idempotent_under_reliability_wrapper(self, mocked_fetch_unfurl):
        mocked_fetch_unfurl.return_value = {
            "title": "Example",
            "description": "Desc",
            "thumbnail_url": "",
            "site_name": "Example",
            "embed_html": "",
        }

        unfurl_post_link.run(str(self.post.id), correlation_id="corr-unfurl-2")
        unfurl_post_link.run(str(self.post.id), correlation_id="corr-unfurl-2")

        self.assertEqual(LinkPreview.objects.filter(post=self.post).count(), 1)
        execution = AsyncTaskExecution.objects.get(
            task_name="apps.posts.tasks.unfurl_post_link",
            idempotency_key=f"link_unfurl:{self.post.id}",
        )
        self.assertEqual(execution.status, AsyncTaskExecution.Status.SUCCEEDED)
        self.assertEqual(execution.attempt_count, 1)


@override_settings(FEATURE_PM_E2E_ENABLED=True)
class InboxViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.alice = User.objects.create_user(email="alice-inbox@example.com", username="aliceinbox", password="secret123")
        self.bob = User.objects.create_user(email="bob-inbox@example.com", username="bobinbox", password="secret123")
        self.alice.mark_email_verified()
        self.bob.mark_email_verified()

    def test_inbox_view_surfaces_dm_and_notification_previews(self):
        Notification.objects.create(
            recipient=self.alice.actor,
            source_actor=self.bob.actor,
            notification_type=Notification.NotificationType.MENTION,
            payload={"summary": "Bob mentioned you in a post"},
        )
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        store_encrypted_message(
            conversation=conversation,
            sender=self.bob.actor,
            recipient_actor=self.alice.actor,
            ciphertext="cipher-inbox",
            message_nonce="nonce-inbox",
            sender_key_id="bob-key-1",
            recipient_key_id="alice-key-1",
            client_message_id="client-inbox-1",
        )

        self.client.force_login(self.alice)
        response = self.client.get("/inbox/?filter=unread")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["unread_notification_count"], 1)
        self.assertEqual(response.context["unread_message_count"], 1)
        self.assertContains(response, "Bob mentioned you in a post")
        self.assertContains(response, f"/messages/{conversation.id}/")

    def test_nav_context_exposes_combined_unread_counts(self):
        Notification.objects.create(
            recipient=self.alice.actor,
            source_actor=self.bob.actor,
            notification_type=Notification.NotificationType.SYSTEM,
        )
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        store_encrypted_message(
            conversation=conversation,
            sender=self.bob.actor,
            recipient_actor=self.alice.actor,
            ciphertext="cipher-nav",
            message_nonce="nonce-nav",
            sender_key_id="bob-key-nav",
            recipient_key_id="alice-key-nav",
            client_message_id="client-nav-1",
        )

        self.client.force_login(self.alice)
        response = self.client.get("/notifications/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["nav_unread_notification_count"], 1)
        self.assertEqual(response.context["nav_unread_message_count"], 1)
        self.assertEqual(response.context["nav_unread_inbox_count"], 2)

    def test_inbox_activity_feed_combines_message_and_notification_items(self):
        notification = Notification.objects.create(
            recipient=self.alice.actor,
            source_actor=self.bob.actor,
            notification_type=Notification.NotificationType.REPLY,
            payload={"summary": "Bob replied to your post"},
        )
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        envelope = store_encrypted_message(
            conversation=conversation,
            sender=self.bob.actor,
            recipient_actor=self.alice.actor,
            ciphertext="cipher-feed",
            message_nonce="nonce-feed",
            sender_key_id="bob-feed-key",
            recipient_key_id="alice-feed-key",
            client_message_id="client-feed-1",
        )
        Notification.objects.filter(id=notification.id).update(created_at=envelope.created_at - timezone.timedelta(minutes=1))

        self.client.force_login(self.alice)
        response = self.client.get("/inbox/?mode=activity")

        self.assertEqual(response.status_code, 200)
        items = response.context["activity_items"]
        self.assertGreaterEqual(len(items), 2)
        kinds = {item["kind"] for item in items}
        self.assertIn("message", kinds)
        self.assertIn("notification", kinds)
        self.assertContains(response, f"/messages/{conversation.id}/")

    def test_inbox_activity_feed_paginates_high_volume(self):
        for idx in range(26):
            Notification.objects.create(
                recipient=self.alice.actor,
                source_actor=self.bob.actor,
                notification_type=Notification.NotificationType.SYSTEM,
                payload={"summary": f"System event {idx}"},
            )

        self.client.force_login(self.alice)
        response = self.client.get("/inbox/?mode=activity&section=notifications")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["activity_items"]), 20)
        self.assertTrue(response.context["activity_page_obj"].has_next())

    def test_inbox_activity_feed_unread_filter_hides_read_items(self):
        read_notification = Notification.objects.create(
            recipient=self.alice.actor,
            source_actor=self.bob.actor,
            notification_type=Notification.NotificationType.LIKE,
            payload={"summary": "Read like"},
            read_at=timezone.now(),
        )
        unread_notification = Notification.objects.create(
            recipient=self.alice.actor,
            source_actor=self.bob.actor,
            notification_type=Notification.NotificationType.MENTION,
            payload={"summary": "Unread mention"},
        )
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        envelope = store_encrypted_message(
            conversation=conversation,
            sender=self.bob.actor,
            recipient_actor=self.alice.actor,
            ciphertext="cipher-unread-filter",
            message_nonce="nonce-unread-filter",
            sender_key_id="bob-unread-filter-key",
            recipient_key_id="alice-unread-filter-key",
            client_message_id="client-unread-filter-1",
        )
        participant = ConversationParticipant.objects.get(conversation=conversation, actor=self.alice.actor)
        participant.last_read_at = envelope.created_at
        participant.save(update_fields=["last_read_at", "updated_at"])

        self.client.force_login(self.alice)
        response = self.client.get("/inbox/?mode=activity&filter=unread")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, unread_notification.payload["summary"])
        self.assertNotContains(response, read_notification.payload["summary"])
        self.assertNotContains(response, f"/messages/{conversation.id}/")

    def test_inbox_activity_feed_renders_notification_context_preview(self):
        notification = Notification.objects.create(
            recipient=self.alice.actor,
            source_actor=self.bob.actor,
            notification_type=Notification.NotificationType.MENTION,
            payload={"summary": "Bob mentioned you in a post"},
        )
        post = notification.source_post
        if post is None:
            from apps.posts.models import Post

            post = Post.objects.create(
                author=self.bob.actor,
                canonical_uri="https://example.com/posts/inbox-preview-1",
                content="This is a long preview line from Bob that should show up inside the inbox activity card.",
            )
            notification.source_post = post
            notification.save(update_fields=["source_post"])

        self.client.force_login(self.alice)
        response = self.client.get("/inbox/?mode=activity&section=notifications")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "From @bobinbox")
        self.assertContains(response, "Post preview:")
        self.assertContains(response, "Open related post")

    def test_inbox_activity_feed_renders_latest_sender_context_for_messages(self):
        conversation = create_direct_conversation(
            created_by=self.alice.actor,
            participant_a=self.alice.actor,
            participant_b=self.bob.actor,
        )
        store_encrypted_message(
            conversation=conversation,
            sender=self.bob.actor,
            recipient_actor=self.alice.actor,
            ciphertext="cipher-preview-message",
            message_nonce="nonce-preview-message",
            sender_key_id="bob-preview-key",
            recipient_key_id="alice-preview-key",
            client_message_id="client-preview-message-1",
        )

        self.client.force_login(self.alice)
        response = self.client.get("/inbox/?mode=activity&section=messages")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Latest envelope from @bobinbox")

    def test_inbox_activity_feed_uses_type_specific_phrase_without_payload_summary(self):
        Notification.objects.create(
            recipient=self.alice.actor,
            source_actor=self.bob.actor,
            notification_type=Notification.NotificationType.LIKE,
            payload={},
        )

        self.client.force_login(self.alice)
        response = self.client.get("/inbox/?mode=activity&section=notifications")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "@bobinbox liked your post")

    def test_inbox_activity_feed_uses_system_phrase_without_actor(self):
        Notification.objects.create(
            recipient=self.alice.actor,
            notification_type=Notification.NotificationType.SYSTEM,
            payload={},
        )

        self.client.force_login(self.alice)
        response = self.client.get("/inbox/?mode=activity&section=notifications")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "System update")
