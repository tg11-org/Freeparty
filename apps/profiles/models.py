import uuid

from django.db import models
from django.utils import timezone

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
	is_minor_account = models.BooleanField(default=False)
	parental_controls_enabled = models.BooleanField(default=False)
	guardian_email = models.EmailField(blank=True)
	guardian_email_verified_at = models.DateTimeField(null=True, blank=True)

	@property
	def guardian_email_verified(self) -> bool:
		return bool(self.guardian_email and self.guardian_email_verified_at)

	def __str__(self) -> str:
		return f"Profile<{self.actor.handle}>"


class ProfileLink(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	profile = models.ForeignKey("profiles.Profile", on_delete=models.CASCADE, related_name="links")
	title = models.CharField(max_length=120)
	url = models.URLField(max_length=2048)
	display_order = models.PositiveIntegerField(default=0)
	is_active = models.BooleanField(default=True)

	class Meta:
		ordering = ["display_order", "created_at"]

	def __str__(self) -> str:
		return f"ProfileLink<{self.profile.actor.handle}:{self.title}>"


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


class GuardianEmailVerificationToken(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	profile = models.ForeignKey("profiles.Profile", on_delete=models.CASCADE, related_name="guardian_email_tokens")
	guardian_email = models.EmailField()
	token = models.CharField(max_length=255, unique=True)
	expires_at = models.DateTimeField()
	used_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		indexes = [models.Index(fields=["token"]), models.Index(fields=["expires_at"])]

	@property
	def is_expired(self) -> bool:
		return timezone.now() > self.expires_at

	@property
	def is_usable(self) -> bool:
		return self.used_at is None and not self.is_expired


class ParentalControlChangeRequest(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	profile = models.ForeignKey("profiles.Profile", on_delete=models.CASCADE, related_name="parental_change_requests")
	requested_by = models.ForeignKey(
		"accounts.User",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="parental_change_requests",
	)
	guardian_email = models.EmailField()
	token = models.CharField(max_length=255, unique=True)
	expires_at = models.DateTimeField()
	used_at = models.DateTimeField(null=True, blank=True)
	proposed_is_private_account = models.BooleanField(default=False)
	proposed_auto_reveal_spoilers = models.BooleanField(default=False)
	proposed_show_follower_count = models.BooleanField(default=True)
	proposed_show_following_count = models.BooleanField(default=True)
	proposed_is_minor_account = models.BooleanField(default=False)
	proposed_parental_controls_enabled = models.BooleanField(default=False)
	proposed_guardian_email = models.EmailField(blank=True)

	class Meta:
		indexes = [models.Index(fields=["token"]), models.Index(fields=["expires_at"])]

	@property
	def is_expired(self) -> bool:
		return timezone.now() > self.expires_at

	@property
	def is_usable(self) -> bool:
		return self.used_at is None and not self.is_expired

