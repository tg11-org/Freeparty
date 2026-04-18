from rest_framework import serializers

from apps.profiles.models import Profile


class ProfilePrivacySerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["show_follower_count", "show_following_count", "is_private_account", "auto_reveal_spoilers"]
