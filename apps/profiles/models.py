import uuid

from django.db import models

from apps.core.models import TimeStampedModel


def avatar_upload_to(instance: "Profile", filename: str) -> str:
	return f"avatars/{instance.actor_id}/{filename}"


def header_upload_to(instance: "Profile", filename: str) -> str:
	return f"headers/{instance.actor_id}/{filename}"


class Profile(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	actor = models.OneToOneField("actors.Actor", on_delete=models.CASCADE, related_name="profile")
	bio = models.TextField(blank=True)
	avatar = models.ImageField(upload_to=avatar_upload_to, blank=True)
	header = models.ImageField(upload_to=header_upload_to, blank=True)
	website_url = models.URLField(blank=True)
	location = models.CharField(max_length=255, blank=True)

	def __str__(self) -> str:
		return f"Profile<{self.actor.handle}>"

