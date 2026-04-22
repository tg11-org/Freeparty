import re
from calendar import monthrange

from django import forms
from django.utils import timezone

from apps.profiles.models import Profile, ProfileLink


class ProfileForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in [
            "show_follower_count",
            "show_following_count",
            "show_follower_list",
            "show_following_list",
            "is_private_account",
            "auto_reveal_spoilers",
            "is_minor_account",
            "parental_controls_enabled",
            "theme_custom_enabled",
        ]:
            field = self.fields.get(field_name)
            if field is not None:
                field.widget.attrs["class"] = "toggle-input"

        # Mark custom-theme hex fields so the template can attach compact color pickers.
        for field_name in self._HEX_FIELDS:
            field = self.fields.get(field_name)
            if field is not None:
                field.widget.attrs["data-theme-hex"] = "1"

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
            "theme_custom_enabled",
            "theme_custom_bg",
            "theme_custom_bg_gradient",
            "theme_custom_surface",
            "theme_custom_surface2",
            "theme_custom_text",
            "theme_custom_text2",
            "theme_custom_accent",
            "theme_custom_accent_alt",
            "theme_custom_danger",
            "theme_custom_border",
            "theme_custom_focus",
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
            "theme_custom_enabled": "Enable your own custom color palette and pick 'Custom' in the Theme selector.",
            "theme_custom_bg": "Hex color for the page background (example: #101820).",
            "theme_custom_bg_gradient": "Optional CSS gradient for page background (example: linear-gradient(135deg,#101820,#1f2937)).",
            "theme_custom_surface": "Hex color for cards and panels.",
            "theme_custom_surface2": "Hex color for secondary panels and buttons.",
            "theme_custom_text": "Hex color for main text.",
            "theme_custom_text2": "Hex color for muted/secondary text.",
            "theme_custom_accent": "Hex color for primary links/buttons.",
            "theme_custom_accent_alt": "Hex color for hover/alternate accents.",
            "theme_custom_danger": "Hex color for destructive actions and warnings.",
            "theme_custom_border": "Hex color for borders and separators.",
            "theme_custom_focus": "Hex color for keyboard focus outlines.",
        }


    _HEX_FIELDS = (
        "theme_custom_bg",
        "theme_custom_surface",
        "theme_custom_surface2",
        "theme_custom_text",
        "theme_custom_text2",
        "theme_custom_accent",
        "theme_custom_accent_alt",
        "theme_custom_danger",
        "theme_custom_border",
        "theme_custom_focus",
    )

    _HEX_PATTERN = re.compile(r"^#?[0-9a-fA-F]{3}([0-9a-fA-F]{3})?([0-9a-fA-F]{2})?$")

    # Allowlist: only printable ASCII printable chars permitted in gradient values,
    # excluding characters that are dangerous in HTML/CSS/JS contexts.
    _GRADIENT_SAFE = re.compile(r"^[a-zA-Z0-9 ,.()\-#%/]+$")

    def clean(self):
        cleaned = super().clean()

        # Normalize hex-like color entries (allow missing # and trailing semicolon).
        for field_name in self._HEX_FIELDS:
            raw_value = (cleaned.get(field_name) or "").strip().rstrip(";")
            if not raw_value:
                cleaned[field_name] = ""
                continue
            if not self._HEX_PATTERN.fullmatch(raw_value):
                self.add_error(field_name, "Enter a valid hex color, for example #1f2937.")
                continue
            cleaned[field_name] = raw_value if raw_value.startswith("#") else f"#{raw_value}"

        gradient_value = (cleaned.get("theme_custom_bg_gradient") or "").strip().rstrip(";")
        if gradient_value:
            # Reject any char outside a safe CSS gradient allowlist (blocks <, >, ", ', \, ;, etc.)
            if not self._GRADIENT_SAFE.fullmatch(gradient_value):
                self.add_error(
                    "theme_custom_bg_gradient",
                    "Gradient contains invalid characters. Only letters, digits, spaces, commas,"
                    " parentheses, hyphens, # and % are allowed.",
                )
            else:
                lowered = gradient_value.lower()
                if not (
                    lowered.startswith("linear-gradient(")
                    or lowered.startswith("radial-gradient(")
                    or lowered.startswith("conic-gradient(")
                ):
                    if self._HEX_PATTERN.fullmatch(gradient_value):
                        cleaned["theme_custom_bg_gradient"] = gradient_value if gradient_value.startswith("#") else f"#{gradient_value}"
                    else:
                        self.add_error("theme_custom_bg_gradient", "Use a CSS gradient like linear-gradient(...).")
                else:
                    cleaned["theme_custom_bg_gradient"] = gradient_value
        else:
            cleaned["theme_custom_bg_gradient"] = ""

        return cleaned


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
