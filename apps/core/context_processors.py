from apps.notifications.models import Notification
from apps.private_messages.services import get_unread_conversation_count, is_private_messages_enabled


def inbox_counts(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not hasattr(user, "actor"):
        return {
            "nav_unread_notification_count": 0,
            "nav_unread_message_count": 0,
            "nav_unread_inbox_count": 0,
        }

    actor = user.actor
    unread_notification_count = Notification.objects.filter(recipient=actor, read_at__isnull=True).count()
    unread_message_count = get_unread_conversation_count(actor=actor) if is_private_messages_enabled() else 0
    return {
        "nav_unread_notification_count": unread_notification_count,
        "nav_unread_message_count": unread_message_count,
        "nav_unread_inbox_count": unread_notification_count + unread_message_count,
    }


def custom_theme_settings(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not hasattr(user, "actor"):
        return {
            "custom_theme_available": False,
            "custom_theme": {},
        }

    profile = getattr(user.actor, "profile", None)
    if profile is None or not profile.theme_custom_enabled:
        return {
            "custom_theme_available": False,
            "custom_theme": {},
        }

    return {
        "custom_theme_available": True,
        "custom_theme": {
            "bg": profile.theme_custom_bg,
            "bg_gradient": profile.theme_custom_bg_gradient,
            "surface": profile.theme_custom_surface,
            "surface2": profile.theme_custom_surface2,
            "text": profile.theme_custom_text,
            "text2": profile.theme_custom_text2,
            "accent": profile.theme_custom_accent,
            "accent_alt": profile.theme_custom_accent_alt,
            "danger": profile.theme_custom_danger,
            "border": profile.theme_custom_border,
            "focus": profile.theme_custom_focus,
        },
    }