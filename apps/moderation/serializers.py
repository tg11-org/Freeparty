from rest_framework import serializers

from apps.moderation.models import ModerationAction, ModerationNote, Report, TrustSignal, SecurityAuditEvent
from apps.moderation.services import TrustSignalService
from apps.posts.models import Attachment


class ModerationActionSerializer(serializers.ModelSerializer):
    moderator_username = serializers.CharField(source="moderator.username", read_only=True)

    class Meta:
        model = ModerationAction
        fields = [
            "id",
            "action_type",
            "notes",
            "moderator",
            "moderator_username",
            "applied_at",
        ]
        read_only_fields = ["moderator", "moderator_username", "applied_at"]


class ModerationNoteSerializer(serializers.ModelSerializer):
    author_username = serializers.CharField(source="author.username", read_only=True)

    class Meta:
        model = ModerationNote
        fields = ["id", "body", "author", "author_username", "created_at"]
        read_only_fields = ["author", "author_username", "created_at"]


class TrustSignalSerializer(serializers.ModelSerializer):
    """Serializes trust signal data for staff visibility."""

    throttle_status = serializers.SerializerMethodField()

    def get_throttle_status(self, obj):
        if not obj.is_throttled:
            return None
        return {
            "reason": obj.throttle_reason,
            "until": obj.throttled_until,
        }

    class Meta:
        model = TrustSignal
        fields = [
            "account_age_days",
            "email_verified",
            "email_verified_at",
            "recent_reports_count",
            "recent_actions_count",
            "posts_last_hour",
            "follows_last_hour",
            "likes_last_hour",
            "reposts_last_hour",
            "trust_score",
            "is_throttled",
            "throttle_status",
            "last_computed_at",
        ]
        read_only_fields = [
            "account_age_days",
            "email_verified",
            "email_verified_at",
            "recent_reports_count",
            "recent_actions_count",
            "posts_last_hour",
            "follows_last_hour",
            "likes_last_hour",
            "reposts_last_hour",
            "trust_score",
            "is_throttled",
            "throttle_status",
            "last_computed_at",
        ]



class ReportListSerializer(serializers.ModelSerializer):
    reporter_handle = serializers.CharField(source="reporter.handle", read_only=True)

    class Meta:
        model = Report
        fields = [
            "id",
            "reason",
            "severity",
            "description",
            "status",
            "reporter",
            "reporter_handle",
            "target_actor",
            "target_post",
            "reviewed_at",
            "reviewed_by",
            "created_at",
        ]


class ReportDetailSerializer(ReportListSerializer):
    actions = ModerationActionSerializer(many=True, read_only=True)
    notes = ModerationNoteSerializer(many=True, read_only=True)
    target_actor_trust_signal = serializers.SerializerMethodField()
    target_post_attachments = serializers.SerializerMethodField()

    def get_target_actor_trust_signal(self, obj):
        """Include trust signal for the target actor to help staff make decisions."""
        if not obj.target_actor:
            return None
        signal = TrustSignalService.get_trust_signal(obj.target_actor)
        return TrustSignalSerializer(signal).data

    def get_target_post_attachments(self, obj):
        if not obj.target_post:
            return []
        attachments = obj.target_post.attachments.all().order_by("created_at")
        return [
            {
                "id": str(a.id),
                "attachment_type": a.attachment_type,
                "file": a.file.url if a.file else "",
                "mime_type": a.mime_type,
                "file_size": a.file_size,
                "processing_state": a.processing_state,
                "moderation_state": a.moderation_state,
                "alt_text": a.alt_text,
                "caption": a.caption,
            }
            for a in attachments
        ]

    class Meta(ReportListSerializer.Meta):
        fields = ReportListSerializer.Meta.fields + [
            "actions",
            "notes",
            "target_actor_trust_signal",
            "target_post_attachments",
        ]


class ReportStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Report.Status.choices)


class CreateModerationActionSerializer(serializers.Serializer):
    action_type = serializers.ChoiceField(choices=ModerationAction.ActionType.choices)
    notes = serializers.CharField(required=False, allow_blank=True)


class CreateModerationNoteSerializer(serializers.Serializer):
    body = serializers.CharField(min_length=1)
