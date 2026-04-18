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
            "is_private_account",
            "auto_reveal_spoilers",
        ]
        help_texts = {
            "show_follower_count": "Disable to hide your follower count from other people.",
            "show_following_count": "Disable to hide how many accounts you follow.",
            "is_private_account": "If enabled, only approved followers can view your profile and posts.",
            "auto_reveal_spoilers": "If enabled, spoiler and NSFW content gates open by default.",
        }
