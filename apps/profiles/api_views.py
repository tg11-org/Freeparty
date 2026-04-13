from rest_framework import generics, permissions

from apps.profiles.models import Profile
from apps.profiles.serializers import ProfilePrivacySerializer


class MyProfilePrivacyAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfilePrivacySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        profile, _ = Profile.objects.get_or_create(actor=self.request.user.actor)
        return profile
