import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

	dependencies = [
		("accounts", "0004_totpdevice"),
	]

	operations = [
		migrations.CreateModel(
			name="RecoveryCode",
			fields=[
				("created_at", models.DateTimeField(auto_now_add=True)),
				("updated_at", models.DateTimeField(auto_now=True)),
				("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
				("code_hash", models.CharField(max_length=255)),
				("used_at", models.DateTimeField(blank=True, null=True)),
				(
					"user",
					models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="recovery_codes", to=settings.AUTH_USER_MODEL),
				),
			],
			options={
				"indexes": [models.Index(fields=["user", "used_at"], name="accounts_re_user_id_5933b8_idx")],
			},
		),
	]