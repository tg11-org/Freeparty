from django import forms

from apps.profiles.models import Profile


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            "bio",
            "avatar",
            "header",
            "website_url",
            "location",
            "show_follower_count",
            "show_following_count",
        ]
        help_texts = {
            "show_follower_count": "Disable to hide your follower count from other people.",
            "show_following_count": "Disable to hide how many accounts you follow.",
        }
