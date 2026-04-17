import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.accounts.models import User
from apps.moderation.models import Report

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Report)
def auto_assign_critical_reports(sender, instance: Report, created: bool, **kwargs):
	if not created:
		return
	if instance.severity != Report.Severity.CRITICAL:
		return
	if instance.assigned_to_id:
		return

	on_call = User.objects.filter(is_staff=True).order_by("created_at", "id").first()
	if on_call is None:
		logger.warning("incident_escalation severity=critical report_id=%s outcome=no_staff_available", instance.id)
		return

	instance.assigned_to = on_call
	instance.first_assigned_at = timezone.now()
	instance.save(update_fields=["assigned_to", "first_assigned_at", "updated_at"])
	logger.warning(
		"incident_escalation severity=critical report_id=%s assigned_to=%s target_actor_id=%s target_post_id=%s",
		instance.id,
		on_call.id,
		instance.target_actor_id or "",
		instance.target_post_id or "",
	)