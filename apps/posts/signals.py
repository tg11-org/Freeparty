from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.posts.hashtags import sync_post_hashtags
from apps.posts.models import Post


@receiver(post_save, sender=Post)
def sync_hashtag_index(sender, instance, created, update_fields=None, **kwargs):
    """Maintain indexed hashtag mappings whenever post content is created/updated."""
    if not created and update_fields is not None and "content" not in update_fields:
        return
    sync_post_hashtags(instance)


@receiver(post_save, sender=Post)
def trigger_link_unfurl(sender, instance, created, **kwargs):
    """Queue link unfurl task when a new post is created and the flag is on."""
    if not created:
        return
    if not getattr(settings, "FEATURE_LINK_UNFURL_ENABLED", False):
        return
    # Avoid circular import — import at call time
    from apps.posts.tasks import unfurl_post_link

    unfurl_post_link.delay(str(instance.id))
