from datetime import timedelta
import logging

from django.conf import settings
from django.utils import timezone
from django.db.models import Count, Q

from apps.moderation.models import TrustSignal, SecurityAuditEvent, Report, ModerationAction
from apps.posts.models import Post
from apps.social.models import Like, Repost, Follow

logger = logging.getLogger(__name__)


class TrustSignalService:
	"""
	Computes trust signals and adaptive throttling recommendations for actors.
	Evaluates account age, email verification, moderation history, and action velocity.
	"""

	# Configuration thresholds
	MINIMUM_ACCOUNT_AGE_DAYS_FOR_TRUST = 7
	EMAIL_VERIFICATION_TRUST_BONUS = 25
	RECENT_REPORT_PENALTY_PER_REPORT = 10
	RECENT_ACTION_PENALTY_PER_ACTION = 15
	VELOCITY_THRESHOLD_POSTS_PER_HOUR = 5
	VELOCITY_THRESHOLD_FOLLOWS_PER_HOUR = 10
	VELOCITY_THRESHOLD_LIKES_PER_HOUR = 20
	VELOCITY_THRESHOLD_REPOSTS_PER_HOUR = 10

	@staticmethod
	def compute_trust_signal(actor):
		"""
		Compute or update trust signal for an actor.
		Returns the TrustSignal instance.
		"""
		signal, created = TrustSignal.objects.get_or_create(actor=actor)

		# Account age
		account_age = timezone.now() - actor.user.created_at
		signal.account_age_days = account_age.days

		# Email verification
		signal.email_verified = actor.user.email_verified if hasattr(actor.user, "email_verified") else False
		if signal.email_verified:
			# Find verification date from audit events if available
			verify_event = SecurityAuditEvent.objects.filter(
				user=actor.user,
				event_type=SecurityAuditEvent.EventType.EMAIL_VERIFICATION,
			).order_by("-created_at").first()
			signal.email_verified_at = verify_event.created_at if verify_event else actor.user.created_at

		# Moderation signals (last 30 days)
		thirty_days_ago = timezone.now() - timedelta(days=30)
		signal.recent_reports_count = Report.objects.filter(
			target_actor=actor,
			created_at__gte=thirty_days_ago,
		).count()
		signal.recent_actions_count = ModerationAction.objects.filter(
			actor_target=actor,
			created_at__gte=thirty_days_ago,
		).count()

		# Velocity signals (last hour)
		one_hour_ago = timezone.now() - timedelta(hours=1)
		signal.posts_last_hour = Post.objects.filter(
			author=actor,
			created_at__gte=one_hour_ago,
		).count()
		signal.likes_last_hour = Like.objects.filter(
			actor=actor,
			created_at__gte=one_hour_ago,
		).count()
		signal.reposts_last_hour = Repost.objects.filter(
			actor=actor,
			created_at__gte=one_hour_ago,
		).count()
		signal.follows_last_hour = Follow.objects.filter(
			follower=actor,
			created_at__gte=one_hour_ago,
		).count()

		# Compute trust score (0-100)
		score = 50  # baseline
		
		# Account age bonus
		if signal.account_age_days >= TrustSignalService.MINIMUM_ACCOUNT_AGE_DAYS_FOR_TRUST:
			age_bonus = min(20, signal.account_age_days // 3)
			score += age_bonus
		else:
			score -= 15  # penalty for very new accounts

		# Email verification bonus
		if signal.email_verified:
			score += TrustSignalService.EMAIL_VERIFICATION_TRUST_BONUS
		else:
			score -= 10

		# Moderation penalty
		score -= signal.recent_reports_count * TrustSignalService.RECENT_REPORT_PENALTY_PER_REPORT
		score -= signal.recent_actions_count * TrustSignalService.RECENT_ACTION_PENALTY_PER_ACTION

		# Velocity penalty
		if signal.posts_last_hour >= TrustSignalService.VELOCITY_THRESHOLD_POSTS_PER_HOUR:
			score -= 20
		if signal.follows_last_hour >= TrustSignalService.VELOCITY_THRESHOLD_FOLLOWS_PER_HOUR:
			score -= 15
		if signal.likes_last_hour >= TrustSignalService.VELOCITY_THRESHOLD_LIKES_PER_HOUR:
			score -= 10
		if signal.reposts_last_hour >= TrustSignalService.VELOCITY_THRESHOLD_REPOSTS_PER_HOUR:
			score -= 15

		# Clamp to 0-100
		signal.trust_score = max(0, min(100, score))

		# Determine throttling policy
		signal.is_throttled = signal.trust_score < 30
		if signal.is_throttled:
			if signal.recent_actions_count > 2:
				signal.throttle_reason = "recent_moderation_actions"
				signal.throttled_until = timezone.now() + timedelta(days=7)
			elif signal.recent_reports_count > 3:
				signal.throttle_reason = "recent_reports"
				signal.throttled_until = timezone.now() + timedelta(days=3)
			elif signal.posts_last_hour >= TrustSignalService.VELOCITY_THRESHOLD_POSTS_PER_HOUR:
				signal.throttle_reason = "posting_velocity"
				signal.throttled_until = timezone.now() + timedelta(hours=1)
			else:
				signal.throttle_reason = "low_trust_score"
				signal.throttled_until = timezone.now() + timedelta(hours=6)

		signal.save()
		logger.info(
			"trust_signal_computed actor=%s score=%d is_throttled=%s reason=%s",
			actor.handle,
			signal.trust_score,
			signal.is_throttled,
			signal.throttle_reason,
		)
		return signal

	@staticmethod
	def get_trust_signal(actor):
		"""Fetch or create trust signal for an actor."""
		try:
			return actor.trust_signal
		except TrustSignal.DoesNotExist:
			return TrustSignalService.compute_trust_signal(actor)

	@staticmethod
	def should_throttle(actor):
		"""
		Check if an actor should be throttled based on trust signals.
		Returns (should_throttle: bool, reason: str, until: datetime | None)
		"""
		signal = TrustSignalService.get_trust_signal(actor)

		# Check if throttle window has expired
		if signal.is_throttled and signal.throttled_until:
			if timezone.now() >= signal.throttled_until:
				signal.is_throttled = False
				signal.throttle_reason = ""
				signal.throttled_until = None
				signal.save(update_fields=["is_throttled", "throttle_reason", "throttled_until"])
				return False, "", None

		return signal.is_throttled, signal.throttle_reason, signal.throttled_until


class ActionVelocityTracker:
	"""
	Tracks rapid sequences of actions to detect abuse patterns (burst posting, follow spam, etc.).
	"""

	@staticmethod
	def record_post(actor):
		"""Record a post action for velocity tracking."""
		signal = TrustSignalService.get_trust_signal(actor)
		signal.posts_last_hour = Post.objects.filter(
			author=actor,
			created_at__gte=timezone.now() - timedelta(hours=1),
		).count()
		signal.save(update_fields=["posts_last_hour"])

	@staticmethod
	def record_follow(actor):
		"""Record a follow action for velocity tracking."""
		signal = TrustSignalService.get_trust_signal(actor)
		signal.follows_last_hour = Follow.objects.filter(
			follower=actor,
			created_at__gte=timezone.now() - timedelta(hours=1),
		).count()
		signal.save(update_fields=["follows_last_hour"])

	@staticmethod
	def record_like(actor):
		"""Record a like action for velocity tracking."""
		signal = TrustSignalService.get_trust_signal(actor)
		signal.likes_last_hour = Like.objects.filter(
			actor=actor,
			created_at__gte=timezone.now() - timedelta(hours=1),
		).count()
		signal.save(update_fields=["likes_last_hour"])

	@staticmethod
	def record_repost(actor):
		"""Record a repost action for velocity tracking."""
		signal = TrustSignalService.get_trust_signal(actor)
		signal.reposts_last_hour = Repost.objects.filter(
			actor=actor,
			created_at__gte=timezone.now() - timedelta(hours=1),
		).count()
		signal.save(update_fields=["reposts_last_hour"])

	@staticmethod
	def is_velocity_anomaly(actor, action_type: str) -> bool:
		"""
		Check if this action would exceed velocity thresholds.
		action_type: 'post', 'follow', 'like', 'repost'
		"""
		signal = TrustSignalService.get_trust_signal(actor)

		if action_type == "post":
			return signal.posts_last_hour >= TrustSignalService.VELOCITY_THRESHOLD_POSTS_PER_HOUR
		elif action_type == "follow":
			return signal.follows_last_hour >= TrustSignalService.VELOCITY_THRESHOLD_FOLLOWS_PER_HOUR
		elif action_type == "like":
			return signal.likes_last_hour >= TrustSignalService.VELOCITY_THRESHOLD_LIKES_PER_HOUR
		elif action_type == "repost":
			return signal.reposts_last_hour >= TrustSignalService.VELOCITY_THRESHOLD_REPOSTS_PER_HOUR
		return False


class SecurityAuditService:
	"""Records security-sensitive events for compliance and forensic investigation."""

	@staticmethod
	def log_event(user, event_type: str, ip_address: str = None, user_agent: str = None, details: dict = None):
		"""
		Log a security audit event.

		Args:
			user: User instance
			event_type: One of SecurityAuditEvent.EventType choices
			ip_address: Optional client IP
			user_agent: Optional HTTP user agent
			details: Optional dict of additional contextual data
		"""
		event = SecurityAuditEvent.objects.create(
			user=user,
			event_type=event_type,
			ip_address=ip_address,
			user_agent=user_agent,
			details=details or {},
		)
		logger.info(
			"security_audit_event event_type=%s user=%s ip=%s",
			event_type,
			user.email,
			ip_address,
		)
		return event

	@staticmethod
	def log_login_success(user, ip_address: str = None, user_agent: str = None):
		"""Log a successful login."""
		return SecurityAuditService.log_event(
			user,
			SecurityAuditEvent.EventType.LOGIN_SUCCESS,
			ip_address=ip_address,
			user_agent=user_agent,
		)

	@staticmethod
	def log_login_failure(user, ip_address: str = None, user_agent: str = None, reason: str = None):
		"""Log a failed login attempt."""
		details = {"reason": reason} if reason else {}
		return SecurityAuditService.log_event(
			user,
			SecurityAuditEvent.EventType.LOGIN_FAILURE,
			ip_address=ip_address,
			user_agent=user_agent,
			details=details,
		)

	@staticmethod
	def log_password_reset_request(user, ip_address: str = None, user_agent: str = None):
		"""Log a password reset request."""
		return SecurityAuditService.log_event(
			user,
			SecurityAuditEvent.EventType.PASSWORD_RESET_REQUEST,
			ip_address=ip_address,
			user_agent=user_agent,
		)

	@staticmethod
	def log_password_reset_complete(user, ip_address: str = None, user_agent: str = None):
		"""Log a password reset completion."""
		return SecurityAuditService.log_event(
			user,
			SecurityAuditEvent.EventType.PASSWORD_RESET_COMPLETE,
			ip_address=ip_address,
			user_agent=user_agent,
		)

	@staticmethod
	def log_email_verification(user, ip_address: str = None, user_agent: str = None):
		"""Log an email verification event."""
		return SecurityAuditService.log_event(
			user,
			SecurityAuditEvent.EventType.EMAIL_VERIFICATION,
			ip_address=ip_address,
			user_agent=user_agent,
		)

	@staticmethod
	def log_email_changed(user, old_email: str = None, ip_address: str = None, user_agent: str = None):
		"""Log an email change event."""
		details = {"old_email": old_email} if old_email else {}
		return SecurityAuditService.log_event(
			user,
			SecurityAuditEvent.EventType.EMAIL_CHANGED,
			ip_address=ip_address,
			user_agent=user_agent,
			details=details,
		)

	@staticmethod
	def log_moderator_action(moderator_user, target_user, action_type: str, ip_address: str = None, user_agent: str = None):
		"""Log when a moderator takes action on a user."""
		details = {"action_type": action_type, "target_user_id": str(target_user.id)}
		return SecurityAuditService.log_event(
			moderator_user,
			SecurityAuditEvent.EventType.MODERATION_ACTION_CREATE,
			ip_address=ip_address,
			user_agent=user_agent,
			details=details,
		)
