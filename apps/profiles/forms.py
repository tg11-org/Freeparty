from django import forms

from apps.profiles.models import Profile, ProfileLink


class ProfileForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in [
            "show_follower_count",
            "show_following_count",
            "is_private_account",
            "auto_reveal_spoilers",
            "is_minor_account",
            "parental_controls_enabled",
        ]:
            field = self.fields.get(field_name)
            if field is not None:
                field.widget.attrs["class"] = "toggle-input"

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
            "is_minor_account",
            "parental_controls_enabled",
            "guardian_email",
        ]
        help_texts = {
            "show_follower_count": "Disable to hide your follower count from other people.",
            "show_following_count": "Disable to hide how many accounts you follow.",
            "is_private_account": "If enabled, only approved followers can view your profile and posts.",
            "auto_reveal_spoilers": "If enabled, spoiler and NSFW content gates open by default.",
            "is_minor_account": "Enable if this account is used by a minor and requires extra privacy protections.",
            "parental_controls_enabled": "Lock sensitive privacy/content settings behind guardian email consent.",
            "guardian_email": "Secondary parent/guardian email used to verify and approve protected settings changes.",
        }


class ProfileLinkForm(forms.ModelForm):
    class Meta:
        model = ProfileLink
        fields = ["title", "url", "display_order", "is_active"]
        help_texts = {
            "display_order": "Lower numbers appear first.",
            "is_active": "Disable to hide this link from your public links page.",
        }
