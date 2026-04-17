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