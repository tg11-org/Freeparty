import uuid

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

