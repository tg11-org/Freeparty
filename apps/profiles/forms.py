from django import forms
from django.utils import timezone
from calendar import monthrange

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
            "show_follower_list",
            "show_following_list",
            "is_private_account",
            "auto_reveal_spoilers",
            "is_minor_account",
            "parental_controls_enabled",
            "guardian_email",
        ]
        help_texts = {
            "show_follower_count": "Disable to hide your follower count from other people.",
            "show_following_count": "Disable to hide how many accounts you follow.",
            "show_follower_list": "Disable to prevent others from seeing the list of who follows you.",
            "show_following_list": "Disable to prevent others from seeing the list of who you follow.",
            "is_private_account": "If enabled, only approved followers can view your profile and posts.",
            "auto_reveal_spoilers": "If enabled, spoiler and NSFW content gates open by default.",
            "is_minor_account": "Enable if this account is used by a minor and requires extra privacy protections.",
            "parental_controls_enabled": "Lock sensitive privacy/content settings behind guardian email consent.",
            "guardian_email": "Secondary parent/guardian email used to verify and approve protected settings changes.",
        }


class GuardianMinorSettingsForm(forms.Form):
    minor_birthdate_precision = forms.ChoiceField(
        choices=Profile.MinorBirthdatePrecision.choices,
        label="How should the child's age be stored?",
    )
    minor_age_range = forms.ChoiceField(
        choices=[("", "Choose a range")] + list(Profile.MinorAgeRange.choices),
        required=False,
        label="Age range",
    )
    minor_age_years = forms.IntegerField(required=False, min_value=0, max_value=17, label="Age")
    minor_birth_month = forms.IntegerField(required=False, min_value=1, max_value=12, label="Birth month")
    minor_birth_year = forms.IntegerField(required=False, min_value=1900, max_value=2100, label="Birth year")
    minor_birth_day = forms.IntegerField(required=False, min_value=1, max_value=31, label="Birth day")
    guardian_allows_nsfw_underage = forms.BooleanField(required=False, label="Allow NSFW for this minor")
    guardian_allows_16plus_underage = forms.BooleanField(required=False, label="Allow 16+ posts for this minor")
    guardian_locks_basic_profile = forms.BooleanField(required=False, label="Lock bio, website, and location")
    guardian_locks_visibility_settings = forms.BooleanField(required=False, label="Lock privacy and visibility toggles")
    guardian_locks_account_protection = forms.BooleanField(required=False, label="Lock minor mode and parental control toggles")
    guardian_restrict_dms_to_teens = forms.BooleanField(required=False, label="Allow DMs only with teen accounts")

    def __init__(self, *args, profile: Profile | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in [
            "guardian_allows_nsfw_underage",
            "guardian_allows_16plus_underage",
            "guardian_locks_basic_profile",
            "guardian_locks_visibility_settings",
            "guardian_locks_account_protection",
            "guardian_restrict_dms_to_teens",
        ]:
            self.fields[field_name].widget.attrs["class"] = "toggle-input"
        self.profile = profile
        if profile is not None:
            self.initial.setdefault("minor_birthdate_precision", profile.minor_birthdate_precision)
            self.initial.setdefault("minor_age_range", profile.minor_age_range)
            self.initial.setdefault("minor_age_years", profile.minor_age_years)
            self.initial.setdefault("minor_birth_month", profile.minor_birth_month)
            self.initial.setdefault("minor_birth_year", profile.minor_birth_year)
            self.initial.setdefault("minor_birth_day", profile.minor_birth_day)
            self.initial.setdefault("guardian_allows_nsfw_underage", profile.guardian_allows_nsfw_underage)
            self.initial.setdefault("guardian_allows_16plus_underage", profile.guardian_allows_16plus_underage)
            self.initial.setdefault("guardian_locks_basic_profile", profile.guardian_locks_basic_profile)
            self.initial.setdefault("guardian_locks_visibility_settings", profile.guardian_locks_visibility_settings)
            self.initial.setdefault("guardian_locks_account_protection", profile.guardian_locks_account_protection)
            self.initial.setdefault("guardian_restrict_dms_to_teens", profile.guardian_restrict_dms_to_teens)

    def clean(self):
        cleaned = super().clean()
        precision = cleaned.get("minor_birthdate_precision")
        if precision == Profile.MinorBirthdatePrecision.AGE_RANGE and not cleaned.get("minor_age_range"):
            self.add_error("minor_age_range", "Choose an age range.")
        if precision == Profile.MinorBirthdatePrecision.AGE_YEARS and cleaned.get("minor_age_years") is None:
            self.add_error("minor_age_years", "Enter the child's age.")
        if precision == Profile.MinorBirthdatePrecision.MONTH_YEAR:
            if cleaned.get("minor_birth_month") is None:
                self.add_error("minor_birth_month", "Enter a birth month.")
            if cleaned.get("minor_birth_year") is None:
                self.add_error("minor_birth_year", "Enter a birth year.")
            elif cleaned.get("minor_birth_month") is not None:
                try:
                    monthrange(cleaned["minor_birth_year"], cleaned["minor_birth_month"])
                except ValueError:
                    self.add_error("minor_birth_month", "Enter a valid month and year.")
        if precision == Profile.MinorBirthdatePrecision.FULL_DATE:
            if cleaned.get("minor_birth_day") is None:
                self.add_error("minor_birth_day", "Enter a birth day.")
            if cleaned.get("minor_birth_month") is None:
                self.add_error("minor_birth_month", "Enter a birth month.")
            if cleaned.get("minor_birth_year") is None:
                self.add_error("minor_birth_year", "Enter a birth year.")
            elif cleaned.get("minor_birth_day") is not None and cleaned.get("minor_birth_month") is not None:
                try:
                    last_day = monthrange(cleaned["minor_birth_year"], cleaned["minor_birth_month"])[1]
                except ValueError:
                    self.add_error("minor_birth_month", "Enter a valid month and year.")
                else:
                    if cleaned["minor_birth_day"] > last_day:
                        self.add_error("minor_birth_day", "That day is not valid for the selected month and year.")
        return cleaned

    def apply(self, profile: Profile) -> Profile:
        profile.minor_birthdate_precision = self.cleaned_data["minor_birthdate_precision"]
        profile.minor_age_range = self.cleaned_data.get("minor_age_range") or ""
        profile.minor_age_years = self.cleaned_data.get("minor_age_years")
        profile.minor_birth_month = self.cleaned_data.get("minor_birth_month")
        profile.minor_birth_year = self.cleaned_data.get("minor_birth_year")
        profile.minor_birth_day = self.cleaned_data.get("minor_birth_day")
        profile.guardian_allows_nsfw_underage = bool(self.cleaned_data.get("guardian_allows_nsfw_underage"))
        profile.guardian_allows_16plus_underage = bool(self.cleaned_data.get("guardian_allows_16plus_underage"))
        profile.guardian_locks_basic_profile = bool(self.cleaned_data.get("guardian_locks_basic_profile"))
        profile.guardian_locks_visibility_settings = bool(self.cleaned_data.get("guardian_locks_visibility_settings"))
        profile.guardian_locks_account_protection = bool(self.cleaned_data.get("guardian_locks_account_protection"))
        profile.guardian_restrict_dms_to_teens = bool(self.cleaned_data.get("guardian_restrict_dms_to_teens"))
        if profile.minor_birthdate_precision == Profile.MinorBirthdatePrecision.AGE_YEARS:
            profile.minor_age_recorded_at = timezone.now()
        else:
            profile.minor_age_recorded_at = None
        if profile.minor_birthdate_precision != Profile.MinorBirthdatePrecision.AGE_RANGE:
            profile.minor_age_range = ""
        if profile.minor_birthdate_precision != Profile.MinorBirthdatePrecision.AGE_YEARS:
            profile.minor_age_years = None
        if profile.minor_birthdate_precision not in {Profile.MinorBirthdatePrecision.MONTH_YEAR, Profile.MinorBirthdatePrecision.FULL_DATE}:
            profile.minor_birth_month = None
            profile.minor_birth_year = None
        if profile.minor_birthdate_precision != Profile.MinorBirthdatePrecision.FULL_DATE:
            profile.minor_birth_day = None
        return profile


class ProfileLinkForm(forms.ModelForm):
    class Meta:
        model = ProfileLink
        fields = ["title", "url", "display_order", "is_active"]
        help_texts = {
            "display_order": "Lower numbers appear first.",
            "is_active": "Disable to hide this link from your public links page.",
        }
