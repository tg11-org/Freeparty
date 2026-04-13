from django.http import HttpResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.accounts.models import User

from apps.core.middleware import RequestObservabilityMiddleware
from apps.core.services.task_observability import observe_celery_task


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
