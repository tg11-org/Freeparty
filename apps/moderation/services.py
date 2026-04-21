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
	TRUST_SCORE_THROTTLE_THRESHOLD = 30
	VELOCITY_THRESHOLD_POSTS_PER_HOUR = 5
	VELOCITY_THRESHOLD_FOLLOWS_PER_HOUR = 10
	VELOCITY_THRESHOLD_LIKES_PER_HOUR = 20
	VELOCITY_THRESHOLD_REPOSTS_PER_HOUR = 10
	# Profile completeness bonuses
	PROFILE_AVATAR_TRUST_BONUS = 10
	PROFILE_BIO_TRUST_BONUS = 8
	HAS_POSTS_TRUST_BONUS = 5
	HAS_LIKED_TRUST_BONUS = 5
	HAS_FOLLOWERS_TRUST_BONUS = 10
	HAS_FOLLOWING_TRUST_BONUS = 5

	THROTTLE_RECENT_ACTIONS_COUNT_THRESHOLD = 3
	THROTTLE_RECENT_REPORTS_COUNT_THRESHOLD = 4
	THROTTLE_RECENT_ACTIONS_DAYS = 7
	THROTTLE_RECENT_REPORTS_DAYS = 3
	THROTTLE_POSTING_VELOCITY_HOURS = 1
	THROTTLE_LOW_TRUST_HOURS = 6

	@staticmethod
	def minimum_account_age_days_for_trust() -> int:
		return int(getattr(settings, "ABUSE_MINIMUM_ACCOUNT_AGE_DAYS_FOR_TRUST", TrustSignalService.MINIMUM_ACCOUNT_AGE_DAYS_FOR_TRUST))

	@staticmethod
	def email_verification_trust_bonus() -> int:
		return int(getattr(settings, "ABUSE_EMAIL_VERIFICATION_TRUST_BONUS", TrustSignalService.EMAIL_VERIFICATION_TRUST_BONUS))

	@staticmethod
	def recent_report_penalty_per_report() -> int:
		return int(getattr(settings, "ABUSE_RECENT_REPORT_PENALTY_PER_REPORT", TrustSignalService.RECENT_REPORT_PENALTY_PER_REPORT))

	@staticmethod
	def recent_action_penalty_per_action() -> int:
		return int(getattr(settings, "ABUSE_RECENT_ACTION_PENALTY_PER_ACTION", TrustSignalService.RECENT_ACTION_PENALTY_PER_ACTION))

	@staticmethod
	def trust_score_throttle_threshold() -> int:
		return int(getattr(settings, "ABUSE_TRUST_SCORE_THROTTLE_THRESHOLD", TrustSignalService.TRUST_SCORE_THROTTLE_THRESHOLD))

	@staticmethod
	def profile_avatar_trust_bonus() -> int:
		return int(getattr(settings, "ABUSE_PROFILE_AVATAR_TRUST_BONUS", TrustSignalService.PROFILE_AVATAR_TRUST_BONUS))

	@staticmethod
	def profile_bio_trust_bonus() -> int:
		return int(getattr(settings, "ABUSE_PROFILE_BIO_TRUST_BONUS", TrustSignalService.PROFILE_BIO_TRUST_BONUS))

	@staticmethod
	def has_posts_trust_bonus() -> int:
		return int(getattr(settings, "ABUSE_HAS_POSTS_TRUST_BONUS", TrustSignalService.HAS_POSTS_TRUST_BONUS))

	@staticmethod
	def has_liked_trust_bonus() -> int:
		return int(getattr(settings, "ABUSE_HAS_LIKED_TRUST_BONUS", TrustSignalService.HAS_LIKED_TRUST_BONUS))

	@staticmethod
	def has_followers_trust_bonus() -> int:
		return int(getattr(settings, "ABUSE_HAS_FOLLOWERS_TRUST_BONUS", TrustSignalService.HAS_FOLLOWERS_TRUST_BONUS))

	@staticmethod
	def has_following_trust_bonus() -> int:
		return int(getattr(settings, "ABUSE_HAS_FOLLOWING_TRUST_BONUS", TrustSignalService.HAS_FOLLOWING_TRUST_BONUS))

	@staticmethod
	def throttle_recent_actions_count_threshold() -> int:
		return int(getattr(settings, "ABUSE_THROTTLE_RECENT_ACTIONS_COUNT_THRESHOLD", TrustSignalService.THROTTLE_RECENT_ACTIONS_COUNT_THRESHOLD))

	@staticmethod
	def throttle_recent_reports_count_threshold() -> int:
		return int(getattr(settings, "ABUSE_THROTTLE_RECENT_REPORTS_COUNT_THRESHOLD", TrustSignalService.THROTTLE_RECENT_REPORTS_COUNT_THRESHOLD))

	@staticmethod
	def throttle_recent_actions_days() -> int:
		return int(getattr(settings, "ABUSE_THROTTLE_RECENT_ACTIONS_DAYS", TrustSignalService.THROTTLE_RECENT_ACTIONS_DAYS))

	@staticmethod
	def throttle_recent_reports_days() -> int:
		return int(getattr(settings, "ABUSE_THROTTLE_RECENT_REPORTS_DAYS", TrustSignalService.THROTTLE_RECENT_REPORTS_DAYS))

	@staticmethod
	def throttle_posting_velocity_hours() -> int:
		return int(getattr(settings, "ABUSE_THROTTLE_POSTING_VELOCITY_HOURS", TrustSignalService.THROTTLE_POSTING_VELOCITY_HOURS))

	@staticmethod
	def throttle_low_trust_hours() -> int:
		return int(getattr(settings, "ABUSE_THROTTLE_LOW_TRUST_HOURS", TrustSignalService.THROTTLE_LOW_TRUST_HOURS))

	@staticmethod
	def velocity_threshold_posts_per_hour() -> int:
		return int(getattr(settings, "ABUSE_THRESHOLD_POSTS_PER_HOUR", TrustSignalService.VELOCITY_THRESHOLD_POSTS_PER_HOUR))

	@staticmethod
	def velocity_threshold_follows_per_hour() -> int:
		return int(getattr(settings, "ABUSE_THRESHOLD_FOLLOWS_PER_HOUR", TrustSignalService.VELOCITY_THRESHOLD_FOLLOWS_PER_HOUR))

	@staticmethod
	def velocity_threshold_likes_per_hour() -> int:
		return int(getattr(settings, "ABUSE_THRESHOLD_LIKES_PER_HOUR", TrustSignalService.VELOCITY_THRESHOLD_LIKES_PER_HOUR))

	@staticmethod
	def velocity_threshold_reposts_per_hour() -> int:
		return int(getattr(settings, "ABUSE_THRESHOLD_REPOSTS_PER_HOUR", TrustSignalService.VELOCITY_THRESHOLD_REPOSTS_PER_HOUR))

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
		if signal.account_age_days >= TrustSignalService.minimum_account_age_days_for_trust():
			age_bonus = min(20, signal.account_age_days // 3)
			score += age_bonus
		else:
			score -= 15  # penalty for very new accounts

		# Email verification bonus
		if signal.email_verified:
			score += TrustSignalService.email_verification_trust_bonus()
		else:
			score -= 10

		# Profile completeness bonuses
		profile = getattr(actor, "profile", None)
		if profile:
			if getattr(profile, "avatar", None):
				score += TrustSignalService.profile_avatar_trust_bonus()
			if getattr(profile, "bio", "").strip():
				score += TrustSignalService.profile_bio_trust_bonus()
		if Post.objects.filter(author=actor, deleted_at__isnull=True).exists():
			score += TrustSignalService.has_posts_trust_bonus()
		if Like.objects.filter(actor=actor).exists():
			score += TrustSignalService.has_liked_trust_bonus()
		if Follow.objects.filter(followee=actor).exists():
			score += TrustSignalService.has_followers_trust_bonus()
		if Follow.objects.filter(follower=actor).exists():
			score += TrustSignalService.has_following_trust_bonus()

		# Moderation penalty
		score -= signal.recent_reports_count * TrustSignalService.recent_report_penalty_per_report()
		score -= signal.recent_actions_count * TrustSignalService.recent_action_penalty_per_action()

		# Velocity penalty
		if signal.posts_last_hour >= TrustSignalService.velocity_threshold_posts_per_hour():
			score -= 20
		if signal.follows_last_hour >= TrustSignalService.velocity_threshold_follows_per_hour():
			score -= 15
		if signal.likes_last_hour >= TrustSignalService.velocity_threshold_likes_per_hour():
			score -= 10
		if signal.reposts_last_hour >= TrustSignalService.velocity_threshold_reposts_per_hour():
			score -= 15

		# Clamp to 0-100
		signal.trust_score = max(0, min(100, score))

		# Determine throttling policy
		signal.is_throttled = signal.trust_score < TrustSignalService.trust_score_throttle_threshold()
		if signal.is_throttled:
			if signal.recent_actions_count >= TrustSignalService.throttle_recent_actions_count_threshold():
				signal.throttle_reason = "recent_moderation_actions"
				signal.throttled_until = timezone.now() + timedelta(days=TrustSignalService.throttle_recent_actions_days())
			elif signal.recent_reports_count >= TrustSignalService.throttle_recent_reports_count_threshold():
				signal.throttle_reason = "recent_reports"
				signal.throttled_until = timezone.now() + timedelta(days=TrustSignalService.throttle_recent_reports_days())
			elif signal.posts_last_hour >= TrustSignalService.velocity_threshold_posts_per_hour():
				signal.throttle_reason = "posting_velocity"
				signal.throttled_until = timezone.now() + timedelta(hours=TrustSignalService.throttle_posting_velocity_hours())
			else:
				signal.throttle_reason = "low_trust_score"
				signal.throttled_until = timezone.now() + timedelta(hours=TrustSignalService.throttle_low_trust_hours())

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
			return signal.posts_last_hour > TrustSignalService.velocity_threshold_posts_per_hour()
		elif action_type == "follow":
			return signal.follows_last_hour > TrustSignalService.velocity_threshold_follows_per_hour()
		elif action_type == "like":
			return signal.likes_last_hour > TrustSignalService.velocity_threshold_likes_per_hour()
		elif action_type == "repost":
			return signal.reposts_last_hour > TrustSignalService.velocity_threshold_reposts_per_hour()
		return False


class AdaptiveAbuseControlService:
	"""
	Runtime abuse controls that can block high-risk actions and surface queueable reports.
	"""

	REPORT_WINDOW_HOURS = 24
	REPORT_MARKER = "auto:adaptive_abuse"

	@staticmethod
	def is_enabled() -> bool:
		return getattr(settings, "FEATURE_ADAPTIVE_ABUSE_CONTROLS_ENABLED", False)

	@staticmethod
	def evaluate_action(actor, action_type: str):
		"""
		Returns (allowed: bool, reason: str).
		"""
		if not AdaptiveAbuseControlService.is_enabled():
			return True, ""

		is_throttled, throttle_reason, throttle_until = TrustSignalService.should_throttle(actor)
		if is_throttled:
			AdaptiveAbuseControlService._escalate_actor(
				actor,
				action_type=action_type,
				signal="throttled",
				detail=throttle_reason,
			)
			AdaptiveAbuseControlService._log_automatic_action(
				actor,
				action_type=action_type,
				signal="throttled",
				detail=throttle_reason or "risk_control",
				blocked=True,
			)
			until_text = throttle_until.isoformat() if throttle_until else "later"
			return False, f"Account action limit active ({throttle_reason or 'risk_control'}). Try again {until_text}."

		if ActionVelocityTracker.is_velocity_anomaly(actor, action_type):
			AdaptiveAbuseControlService._escalate_actor(
				actor,
				action_type=action_type,
				signal="velocity_anomaly",
				detail="burst_detected",
			)
			AdaptiveAbuseControlService._log_automatic_action(
				actor,
				action_type=action_type,
				signal="velocity_anomaly",
				detail="burst_detected",
				blocked=bool(getattr(settings, "ABUSE_VELOCITY_BLOCK_ENABLED", True)),
			)
			if getattr(settings, "ABUSE_VELOCITY_BLOCK_ENABLED", True):
				return False, "Action rate temporarily limited due to unusual activity."

		return True, ""

	@staticmethod
	def _escalate_actor(actor, *, action_type: str, signal: str, detail: str) -> None:
		window_start = timezone.now() - timedelta(hours=AdaptiveAbuseControlService.REPORT_WINDOW_HOURS)
		description = f"{AdaptiveAbuseControlService.REPORT_MARKER} action={action_type} signal={signal} detail={detail}"
		existing = Report.objects.filter(
			target_actor=actor,
			reason=Report.Reason.SPAM_SCAM,
			created_at__gte=window_start,
			description__icontains=AdaptiveAbuseControlService.REPORT_MARKER,
			status__in=[Report.Status.OPEN, Report.Status.UNDER_REVIEW],
		).exists()
		if existing:
			return

		Report.objects.create(
			reporter=actor,
			target_actor=actor,
			reason=Report.Reason.SPAM_SCAM,
			description=description,
		)

	@staticmethod
	def _log_automatic_action(actor, *, action_type: str, signal: str, detail: str, blocked: bool) -> None:
		signal_snapshot = TrustSignalService.get_trust_signal(actor)
		SecurityAuditService.log_event(
			actor.user,
			SecurityAuditEvent.EventType.ABUSE_AUTO_ACTION,
			details={
				"action_type": action_type,
				"signal": signal,
				"detail": detail,
				"blocked": blocked,
				"trust_score": signal_snapshot.trust_score,
				"posts_last_hour": signal_snapshot.posts_last_hour,
				"follows_last_hour": signal_snapshot.follows_last_hour,
				"likes_last_hour": signal_snapshot.likes_last_hour,
				"reposts_last_hour": signal_snapshot.reposts_last_hour,
			},
		)
 


class SecurityAuditService:
	"""Records security-sensitive events for compliance and forensic investigation."""

	@staticmethod
	def log_event(user, event_type: str, ip_address: str | None = None, user_agent: str | None = None, details: dict | None = None):
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
	def log_login_success(user, ip_address: str | None = None, user_agent: str | None = None):
		"""Log a successful login."""
		return SecurityAuditService.log_event(
			user,
			SecurityAuditEvent.EventType.LOGIN_SUCCESS,
			ip_address=ip_address,
			user_agent=user_agent,
		)

	@staticmethod
	def log_login_failure(user, ip_address: str | None = None, user_agent: str | None = None, reason: str | None = None):
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
	def log_password_reset_request(user, ip_address: str | None = None, user_agent: str | None = None):
		"""Log a password reset request."""
		return SecurityAuditService.log_event(
			user,
			SecurityAuditEvent.EventType.PASSWORD_RESET_REQUEST,
			ip_address=ip_address,
			user_agent=user_agent,
		)

	@staticmethod
	def log_password_reset_complete(user, ip_address: str | None = None, user_agent: str | None = None):
		"""Log a password reset completion."""
		return SecurityAuditService.log_event(
			user,
			SecurityAuditEvent.EventType.PASSWORD_RESET_COMPLETE,
			ip_address=ip_address,
			user_agent=user_agent,
		)

	@staticmethod
	def log_email_verification(user, ip_address: str | None = None, user_agent: str | None = None):
		"""Log an email verification event."""
		return SecurityAuditService.log_event(
			user,
			SecurityAuditEvent.EventType.EMAIL_VERIFICATION,
			ip_address=ip_address,
			user_agent=user_agent,
		)

	@staticmethod
	def log_email_changed(user, old_email: str | None = None, ip_address: str | None = None, user_agent: str | None = None):
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
	def log_moderator_action(moderator_user, target_user, action_type: str, ip_address: str | None = None, user_agent: str | None = None):
		"""Log when a moderator takes action on a user."""
		details = {"action_type": action_type, "target_user_id": str(target_user.id)}
		return SecurityAuditService.log_event(
			moderator_user,
			SecurityAuditEvent.EventType.MODERATION_ACTION_CREATE,
			ip_address=ip_address,
			user_agent=user_agent,
			details=details,
		)
