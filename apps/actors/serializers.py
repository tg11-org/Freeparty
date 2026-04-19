from rest_framework import serializers

from apps.actors.models import Actor


class ActorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Actor
        fields = [
            "id",
            "handle",
            "canonical_uri",
            "actor_type",
            "state",
            "is_verified",
            "verified_at",
            "verified_label",
            "handle_locked",
            "remote_domain",
            "created_at",
        ]
