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
	show_follower_count = models.BooleanField(default=True)
	show_following_count = models.BooleanField(default=True)
	is_private_account = models.BooleanField(default=False)
	auto_reveal_spoilers = models.BooleanField(default=False)

	def __str__(self) -> str:
		return f"Profile<{self.actor.handle}>"


class ProfileEditHistory(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	profile = models.ForeignKey("profiles.Profile", on_delete=models.CASCADE, related_name="edit_history")
	editor = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="edited_profiles_history")
	previous_bio = models.TextField(blank=True)
	new_bio = models.TextField(blank=True)
	previous_website_url = models.URLField(blank=True)
	new_website_url = models.URLField(blank=True)
	previous_location = models.CharField(max_length=255, blank=True)
	new_location = models.CharField(max_length=255, blank=True)

	class Meta:
		ordering = ["-created_at"]

