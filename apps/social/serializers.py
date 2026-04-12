from rest_framework import serializers

from apps.social.models import Follow


class FollowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Follow
        fields = ["id", "follower", "followee", "state", "created_at"]
        read_only_fields = ["id", "follower", "state", "created_at"]
