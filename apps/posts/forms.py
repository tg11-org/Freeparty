from django import forms

from apps.posts.models import Post


class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ["content", "spoiler_text", "visibility", "local_only"]
