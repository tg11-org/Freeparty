import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_user_deactivated_at_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="TOTPDevice",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("secret", models.CharField(max_length=64)),
                ("verified", models.BooleanField(default=False)),
                ("name", models.CharField(default="Authenticator app", max_length=64)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="totp_device",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["user"], name="accounts_tot_user_id_idx")],
            },
        ),
    ]
