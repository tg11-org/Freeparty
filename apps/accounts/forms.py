from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.template import loader
from django.utils import timezone

from apps.accounts.tasks import send_password_reset_email

User = get_user_model()


class SignUpForm(forms.ModelForm):
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)
    accept_tos = forms.BooleanField(required=True, error_messages={"required": "You must accept the Terms of Service."})
    accept_guidelines = forms.BooleanField(required=True, error_messages={"required": "You must accept the Community Guidelines."})

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
        now = timezone.now()
        user.tos_accepted_at = now
        user.guidelines_accepted_at = now
        user.tos_version_accepted = str(getattr(settings, "LEGAL_TOS_VERSION", "1.0"))
        user.guidelines_version_accepted = str(getattr(settings, "LEGAL_GUIDELINES_VERSION", "1.0"))
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


class AccountDeactivationForm(forms.Form):
    confirm_deactivate = forms.BooleanField(
        required=True,
        label="I understand this account will be deactivated and can be recovered within 12 months.",
        error_messages={"required": "Please confirm account deactivation."},
    )


class AccountDeletionRequestForm(forms.Form):
    confirm_delete = forms.BooleanField(
        required=True,
        label="I understand account deletion is scheduled for 30 days and can be cancelled before then.",
        error_messages={"required": "Please confirm account deletion request."},
    )
