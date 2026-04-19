from django import forms

from apps.posts.models import Attachment
from apps.posts.models import Post


class PostForm(forms.ModelForm):
    attachment = forms.FileField(required=False, help_text="Image or video · max 25 MB · jpg/png/gif/webp/mp4/webm/mov")
    attachment_alt_text = forms.CharField(required=False, max_length=500, help_text="Describe the media for screen readers (recommended).")
    attachment_caption = forms.CharField(required=False, max_length=500, help_text="Optional caption shown below the media.")

    class Meta:
        model = Post
        fields = ["content", "spoiler_text", "visibility", "local_only", "is_nsfw", "is_16plus", "is_18plus"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["local_only"].label = "Local only"
        self.fields["is_nsfw"].label = "NSFW"
        self.fields["is_16plus"].label = "16+"
        self.fields["is_18plus"].label = "18+"

    def clean_attachment(self):
        upload = self.cleaned_data.get("attachment")
        if not upload:
            return upload

        content_type = getattr(upload, "content_type", "") or ""
        allowed = {"image/", "video/"}
        if not any(content_type.startswith(prefix) for prefix in allowed):
            raise forms.ValidationError("Only image and video uploads are supported.")

        if upload.size > 25 * 1024 * 1024:
            raise forms.ValidationError("Attachment is too large (max 25 MB).")

        return upload

    def clean_attachment_alt_text(self):
        return (self.cleaned_data.get("attachment_alt_text") or "").strip()

    def clean_attachment_caption(self):
        return (self.cleaned_data.get("attachment_caption") or "").strip()

    def clean_content(self):
        return (self.cleaned_data.get("content") or "").strip()

    def clean(self):
        cleaned = super().clean()
        content = (cleaned.get("content") or "").strip()
        attachment = cleaned.get("attachment")
        if cleaned.get("is_16plus") and cleaned.get("is_18plus"):
            raise forms.ValidationError("Choose either 16+ or 18+ for a post, not both.")
        if not content and not attachment:
            raise forms.ValidationError("Add text or attach media before publishing.")
        cleaned["content"] = content
        return cleaned
