from django.test import TestCase

from apps.accounts.models import User
from apps.core.models import AsyncTaskExecution
from apps.federation.models import FederationDelivery, Instance
from apps.federation.tasks import execute_federation_delivery


class FederationTaskReliabilityTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(email="federation-owner@example.com", username="federationowner", password="secret123")
		self.user.mark_email_verified()
		self.instance = Instance._default_manager.create(domain="remote.example")
		self.delivery = FederationDelivery.objects.create(
			target_instance=self.instance,
			actor=self.user.actor,
			object_uri="https://example.com/objects/1",
			activity_payload={"type": "Create"},
		)

	def test_execute_federation_delivery_marks_success_and_records_execution(self):
		execute_federation_delivery.run(str(self.delivery.id), correlation_id="corr-1")

		self.delivery.refresh_from_db()
		self.assertEqual(self.delivery.state, FederationDelivery.DeliveryState.SUCCESS)
		self.assertEqual(self.delivery.response_code, 202)

		execution = AsyncTaskExecution.objects.get(
			task_name="apps.federation.tasks.execute_federation_delivery",
			idempotency_key=f"federation_delivery:{self.delivery.id}",
		)
		self.assertEqual(execution.status, AsyncTaskExecution.Status.SUCCEEDED)
		self.assertEqual(execution.attempt_count, 1)

	def test_execute_federation_delivery_is_idempotent_after_success(self):
		execute_federation_delivery.run(str(self.delivery.id), correlation_id="corr-2")
		execute_federation_delivery.run(str(self.delivery.id), correlation_id="corr-2")

		execution = AsyncTaskExecution.objects.get(
			task_name="apps.federation.tasks.execute_federation_delivery",
			idempotency_key=f"federation_delivery:{self.delivery.id}",
		)
		self.assertEqual(execution.status, AsyncTaskExecution.Status.SUCCEEDED)
		self.assertEqual(execution.attempt_count, 1)
