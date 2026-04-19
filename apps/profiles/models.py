from datetime import date
import uuid
from calendar import monthrange

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


def avatar_upload_to(instance: "Profile", filename: str) -> str:
	return f"avatars/{instance.actor_id}/{filename}"


def header_upload_to(instance: "Profile", filename: str) -> str:
	return f"headers/{instance.actor_id}/{filename}"


class Profile(TimeStampedModel):
	class MinorBirthdatePrecision(models.TextChoices):
		AGE_RANGE = "age_range", "Age range"
		AGE_YEARS = "age_years", "Age"
		MONTH_YEAR = "month_year", "MM/YYYY"
		FULL_DATE = "full_date", "DD/MM/YYYY"

	class MinorAgeRange(models.TextChoices):
		UNDER_13 = "under_13", "Under 13"
		BETWEEN_13_AND_15 = "13_15", "13-15"
		BETWEEN_16_AND_17 = "16_17", "16-17"

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
	minor_birthdate_precision = models.CharField(max_length=24, choices=MinorBirthdatePrecision.choices, blank=True)
	minor_age_range = models.CharField(max_length=24, choices=MinorAgeRange.choices, blank=True)
	minor_age_years = models.PositiveSmallIntegerField(null=True, blank=True)
	minor_age_recorded_at = models.DateTimeField(null=True, blank=True)
	minor_birth_year = models.PositiveSmallIntegerField(null=True, blank=True)
	minor_birth_month = models.PositiveSmallIntegerField(null=True, blank=True)
	minor_birth_day = models.PositiveSmallIntegerField(null=True, blank=True)
	guardian_allows_nsfw_underage = models.BooleanField(default=False)
	guardian_allows_16plus_underage = models.BooleanField(default=False)

	@property
	def guardian_email_verified(self) -> bool:
		return bool(self.guardian_email and self.guardian_email_verified_at)

	def get_effective_minor_age_years(self) -> int | None:
		if not self.is_minor_account:
			return None

		now = timezone.localdate()
		if self.minor_birthdate_precision == self.MinorBirthdatePrecision.AGE_RANGE:
			if self.minor_age_range == self.MinorAgeRange.UNDER_13:
				return 12
			if self.minor_age_range == self.MinorAgeRange.BETWEEN_13_AND_15:
				return 15
			if self.minor_age_range == self.MinorAgeRange.BETWEEN_16_AND_17:
				return 17
			return None

		if self.minor_birthdate_precision == self.MinorBirthdatePrecision.AGE_YEARS:
			if self.minor_age_years is None or self.minor_age_recorded_at is None:
				return None
			days_elapsed = max(0, (timezone.now() - self.minor_age_recorded_at).days)
			return self.minor_age_years + (days_elapsed // 365)

		if self.minor_birthdate_precision == self.MinorBirthdatePrecision.MONTH_YEAR:
			if not self.minor_birth_year or not self.minor_birth_month:
				return None
			last_day = monthrange(self.minor_birth_year, self.minor_birth_month)[1]
			birthdate = date(self.minor_birth_year, self.minor_birth_month, last_day)
		elif self.minor_birthdate_precision == self.MinorBirthdatePrecision.FULL_DATE:
			if not self.minor_birth_year or not self.minor_birth_month or not self.minor_birth_day:
				return None
			birthdate = date(self.minor_birth_year, self.minor_birth_month, self.minor_birth_day)
		else:
			return None

		age = now.year - birthdate.year - ((now.month, now.day) < (birthdate.month, birthdate.day))
		return max(age, 0)

	def allows_16plus_content(self) -> bool:
		if not self.is_minor_account:
			return True
		age = self.get_effective_minor_age_years()
		if age is not None and age >= 16:
			return True
		return bool(self.guardian_allows_16plus_underage)

	def allows_18plus_content(self) -> bool:
		if not self.is_minor_account:
			return True
		age = self.get_effective_minor_age_years()
		return bool(age is not None and age >= 18)

	def allows_nsfw_content(self) -> bool:
		if not self.is_minor_account:
			return True
		age = self.get_effective_minor_age_years()
		if age is not None and age >= 18:
			return True
		return bool(self.guardian_allows_nsfw_underage)

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


class GuardianManagementAccessToken(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	profile = models.ForeignKey("profiles.Profile", on_delete=models.CASCADE, related_name="guardian_management_tokens")
	guardian_email = models.EmailField()
	token = models.CharField(max_length=255, unique=True)
	expires_at = models.DateTimeField()

	class Meta:
		indexes = [models.Index(fields=["token"]), models.Index(fields=["expires_at"])]

	@property
	def is_expired(self) -> bool:
		return timezone.now() > self.expires_at

	@property
	def is_usable(self) -> bool:
		return not self.is_expired


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

