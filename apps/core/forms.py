from django import forms


class SupportRequestForm(forms.Form):
    SUPPORT_TYPE_ACCOUNT = "account"
    SUPPORT_TYPE_SAFETY = "safety"
    SUPPORT_TYPE_BUG = "bug"
    SUPPORT_TYPE_BILLING = "billing"
    SUPPORT_TYPE_GENERAL = "general"

    SUPPORT_TYPE_CHOICES = [
        (SUPPORT_TYPE_ACCOUNT, "Account access / login"),
        (SUPPORT_TYPE_SAFETY, "Safety or abuse report"),
        (SUPPORT_TYPE_BUG, "Bug report"),
        (SUPPORT_TYPE_BILLING, "Billing / business"),
        (SUPPORT_TYPE_GENERAL, "General question"),
    ]

    support_type = forms.ChoiceField(choices=SUPPORT_TYPE_CHOICES)
    subject_summary = forms.CharField(max_length=120)
    username = forms.CharField(max_length=100, required=False)
    email = forms.EmailField()
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 6}))

    def support_type_label(self) -> str:
        return dict(self.SUPPORT_TYPE_CHOICES).get(self.cleaned_data["support_type"], "General question")
