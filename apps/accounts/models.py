import uuid
from datetime import timedelta

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel

USERNAME_VALIDATOR = RegexValidator(
	regex=r"^[a-z0-9_\.]{3,30}$",
	message="Username may contain lowercase letters, numbers, underscore, and dot.",
)


class UserManager(BaseUserManager):
	def create_user(self, email: str, username: str, password: str | None = None, **extra_fields):
		if not email:
			raise ValueError("Users must have an email address")
		if not username:
			raise ValueError("Users must have a username")

		email = self.normalize_email(email).lower()
		username = username.lower()
		user = self.model(email=email, username=username, **extra_fields)
		if password:
			user.set_password(password)
		else:
			user.set_unusable_password()
		user.save(using=self._db)
		return user

	def create_superuser(self, email: str, username: str, password: str, **extra_fields):
		extra_fields.setdefault("is_staff", True)
		extra_fields.setdefault("is_superuser", True)
		extra_fields.setdefault("is_active", True)
		if not extra_fields.get("is_staff"):
			raise ValueError("Superuser must have is_staff=True")
		if not extra_fields.get("is_superuser"):
			raise ValueError("Superuser must have is_superuser=True")
		return self.create_user(email=email, username=username, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
	class AccountState(models.TextChoices):
		ACTIVE = "active", "Active"
		PENDING_VERIFICATION = "pending_verification", "Pending Verification"
		LIMITED = "limited", "Limited"
		SUSPENDED = "suspended", "Suspended"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	email = models.EmailField(unique=True)
	username = models.CharField(max_length=30, unique=True, validators=[USERNAME_VALIDATOR])
	display_name = models.CharField(max_length=80, blank=True)

	is_active = models.BooleanField(default=True)
	is_staff = models.BooleanField(default=False)
	email_verified_at = models.DateTimeField(null=True, blank=True)
	state = models.CharField(max_length=32, choices=AccountState.choices, default=AccountState.PENDING_VERIFICATION)
	last_seen_at = models.DateTimeField(null=True, blank=True)
	tos_accepted_at = models.DateTimeField(null=True, blank=True)
	tos_version_accepted = models.CharField(max_length=32, blank=True)
	guidelines_accepted_at = models.DateTimeField(null=True, blank=True)
	guidelines_version_accepted = models.CharField(max_length=32, blank=True)
	deactivated_at = models.DateTimeField(null=True, blank=True)
	deactivation_recovery_deadline_at = models.DateTimeField(null=True, blank=True)
	deletion_requested_at = models.DateTimeField(null=True, blank=True)
	deletion_scheduled_for_at = models.DateTimeField(null=True, blank=True)

	objects = UserManager()

	USERNAME_FIELD = "email"
	REQUIRED_FIELDS = ["username"]

	class Meta:
		ordering = ["-created_at"]

	@property
	def email_verified(self) -> bool:
		return self.email_verified_at is not None

	def mark_email_verified(self) -> None:
		self.email_verified_at = timezone.now()
		if self.state == self.AccountState.PENDING_VERIFICATION:
			self.state = self.AccountState.ACTIVE
		self.save(update_fields=["email_verified_at", "state", "updated_at"])

	@property
	def is_deactivated(self) -> bool:
		return self.deactivated_at is not None and self.is_active is False

	@property
	def is_pending_deletion(self) -> bool:
		return self.deletion_requested_at is not None and self.deletion_scheduled_for_at is not None

	def deactivate_account(self, *, retention_days: int) -> None:
		now = timezone.now()
		self.is_active = False
		self.deactivated_at = now
		self.deactivation_recovery_deadline_at = now + timedelta(days=retention_days)
		self.save(
			update_fields=[
				"is_active",
				"deactivated_at",
				"deactivation_recovery_deadline_at",
				"updated_at",
			],
		)

	def request_account_deletion(self, *, retention_days: int) -> None:
		now = timezone.now()
		self.is_active = False
		self.deletion_requested_at = now
		self.deletion_scheduled_for_at = now + timedelta(days=retention_days)
		if self.deactivated_at is None:
			self.deactivated_at = now
		self.save(
			update_fields=[
				"is_active",
				"deactivated_at",
				"deletion_requested_at",
				"deletion_scheduled_for_at",
				"updated_at",
			],
		)

	def reactivate_account(self) -> None:
		self.is_active = True
		self.deactivated_at = None
		self.deactivation_recovery_deadline_at = None
		self.deletion_requested_at = None
		self.deletion_scheduled_for_at = None
		self.save(
			update_fields=[
				"is_active",
				"deactivated_at",
				"deactivation_recovery_deadline_at",
				"deletion_requested_at",
				"deletion_scheduled_for_at",
				"updated_at",
			],
		)

	def cancel_deletion_request(self) -> None:
		self.deletion_requested_at = None
		self.deletion_scheduled_for_at = None
		self.is_active = True
		self.save(update_fields=["deletion_requested_at", "deletion_scheduled_for_at", "is_active", "updated_at"])

	def __str__(self) -> str:
		return self.username


class EmailVerificationToken(TimeStampedModel):
	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="verification_tokens")
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


class AccountActionToken(TimeStampedModel):
	class ActionType(models.TextChoices):
		REACTIVATE = "reactivate", "Reactivate"
		CANCEL_DELETION = "cancel_deletion", "Cancel deletion"

	id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
	user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="account_action_tokens")
	action = models.CharField(max_length=32, choices=ActionType.choices)
	token = models.CharField(max_length=255, unique=True)
	expires_at = models.DateTimeField()
	used_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		indexes = [models.Index(fields=["token"]), models.Index(fields=["expires_at"]), models.Index(fields=["action"])]

	@property
	def is_expired(self) -> bool:
		return timezone.now() > self.expires_at

	@property
	def is_usable(self) -> bool:
		return self.used_at is None and not self.is_expired

