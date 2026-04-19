from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0007_profile_guardian_email_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="guardian_allows_16plus_underage",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="profile",
            name="guardian_allows_nsfw_underage",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="profile",
            name="minor_age_range",
            field=models.CharField(blank=True, choices=[("under_13", "Under 13"), ("13_15", "13-15"), ("16_17", "16-17")], max_length=24),
        ),
        migrations.AddField(
            model_name="profile",
            name="minor_age_recorded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="minor_age_years",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="minor_birth_day",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="minor_birth_month",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="minor_birth_year",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="minor_birthdate_precision",
            field=models.CharField(blank=True, choices=[("age_range", "Age range"), ("age_years", "Age"), ("month_year", "MM/YYYY"), ("full_date", "DD/MM/YYYY")], max_length=24),
        ),
        migrations.CreateModel(
            name="GuardianManagementAccessToken",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("guardian_email", models.EmailField(max_length=254)),
                ("token", models.CharField(max_length=255, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="guardian_management_tokens", to="profiles.profile")),
            ],
            options={
                "indexes": [models.Index(fields=["token"], name="profiles_gua_token_5532bb_idx"), models.Index(fields=["expires_at"], name="profiles_gua_expire_5f13e5_idx")],
            },
        ),
    ]
