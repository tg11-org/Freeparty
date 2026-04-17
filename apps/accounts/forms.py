from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.template import loader

from apps.accounts.tasks import send_password_reset_email

User = get_user_model()


class SignUpForm(forms.ModelForm):
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ["email", "username", "display_name"]

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("password1") != cleaned_data.get("password2"):
            raise forms.ValidationError("Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = user.email.lower()
        user.username = user.username.lower()
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class AsyncPasswordResetForm(PasswordResetForm):
    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        subject = loader.render_to_string(subject_template_name, context)
        subject = "".join(subject.splitlines())
        body = loader.render_to_string(email_template_name, context)
        html_message = None
        if html_email_template_name:
            html_message = loader.render_to_string(html_email_template_name, context)
        resolved_from_email = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", None)

        send_password_reset_email.delay(
            subject=subject,
            message=body,
            recipient_email=to_email,
            from_email=resolved_from_email,
            html_message=html_message,
        )
