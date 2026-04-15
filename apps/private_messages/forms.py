from django import forms


class EncryptedMessageEnvelopeForm(forms.Form):
    ciphertext = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), min_length=1)
    message_nonce = forms.CharField(max_length=255)
    client_message_id = forms.CharField(max_length=128, required=False)

    def clean_ciphertext(self):
        return (self.cleaned_data.get("ciphertext") or "").strip()

    def clean_message_nonce(self):
        return (self.cleaned_data.get("message_nonce") or "").strip()

    def clean_client_message_id(self):
        return (self.cleaned_data.get("client_message_id") or "").strip()
