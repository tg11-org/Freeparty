from django.db import migrations, models
import django.db.models.deletion
import uuid

import apps.private_messages.models


class Migration(migrations.Migration):

    dependencies = [
        ("private_messages", "0007_security_hardening_phase_7_1"),
    ]

    operations = [
        migrations.CreateModel(
            name="EncryptedMessageAttachment",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("client_attachment_id", models.CharField(max_length=128)),
                ("encrypted_file", models.FileField(upload_to=apps.private_messages.models.encrypted_dm_attachment_upload_to)),
                ("encrypted_size", models.PositiveBigIntegerField(default=0)),
                ("envelope", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="private_messages.encryptedmessageenvelope")),
            ],
            options={
                "ordering": ["created_at", "id"],
                "indexes": [models.Index(fields=["envelope", "created_at"], name="private_mes_envelop_f4c77a_idx")],
            },
        ),
        migrations.AddConstraint(
            model_name="encryptedmessageattachment",
            constraint=models.UniqueConstraint(fields=("envelope", "client_attachment_id"), name="uniq_dm_attachment_client_id_per_envelope"),
        ),
    ]
