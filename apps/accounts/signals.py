from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import User
from apps.actors.models import Actor
from apps.core.services.uris import actor_uri
from apps.profiles.models import Profile


@receiver(post_save, sender=User)
def create_local_actor_for_user(sender, instance: User, created: bool, **kwargs):
    if not created:
        return

    handle = instance.username
    actor = Actor.objects.create(
        user=instance,
        actor_type=Actor.ActorType.LOCAL,
        state=Actor.ActorState.ACTIVE,
        handle=handle,
        local_username=instance.username,
        canonical_uri=actor_uri(handle),
    )
    Profile.objects.create(actor=actor)
