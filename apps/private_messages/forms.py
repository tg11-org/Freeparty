from django import forms
import json


class EncryptedMessageEnvelopeForm(forms.Form):
    ciphertext = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), required=False)
    message_nonce = forms.CharField(max_length=255, required=False)
    client_message_id = forms.CharField(max_length=128, required=False)
    attachment_manifest = forms.CharField(widget=forms.HiddenInput(), required=False)

    def clean_ciphertext(self):
        return (self.cleaned_data.get("ciphertext") or "").strip()

    def clean_message_nonce(self):
        return (self.cleaned_data.get("message_nonce") or "").strip()

    def clean_client_message_id(self):
        return (self.cleaned_data.get("client_message_id") or "").strip()

    def clean_attachment_manifest(self):
        raw = (self.cleaned_data.get("attachment_manifest") or "").strip()
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Attachment manifest is invalid.") from exc
        if not isinstance(data, list):
            raise forms.ValidationError("Attachment manifest must be a list.")
        normalized = []
        for item in data:
            if not isinstance(item, dict):
                raise forms.ValidationError("Attachment manifest entries must be objects.")
            client_attachment_id = (item.get("client_attachment_id") or "").strip()
            encrypted_size = item.get("encrypted_size")
            if not client_attachment_id:
                raise forms.ValidationError("Attachment manifest is missing required fields.")
            normalized.append(
                {
                    "client_attachment_id": client_attachment_id,
                    "encrypted_size": encrypted_size,
                }
            )
        return normalized

    def clean(self):
        cleaned = super().clean()
        ciphertext = cleaned.get("ciphertext") or ""
        nonce = cleaned.get("message_nonce") or ""
        manifest = cleaned.get("attachment_manifest") or []
        if not ciphertext:
            raise forms.ValidationError("Encrypted payload is required.")
        if not nonce:
            raise forms.ValidationError("Message nonce is required.")
        if manifest and len(manifest) > 5:
            raise forms.ValidationError("No more than 5 encrypted attachments can be sent at once.")
        return cleaned
