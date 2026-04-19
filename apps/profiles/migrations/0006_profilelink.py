from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0005_profile_auto_reveal_spoilers"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProfileLink",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=120)),
                ("url", models.URLField(max_length=2048)),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="links", to="profiles.profile")),
            ],
            options={
                "ordering": ["display_order", "created_at"],
            },
        ),
    ]
