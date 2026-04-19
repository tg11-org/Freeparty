from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0008_profile_minor_age_settings_and_guardian_management"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="guardian_locks_account_protection",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="guardian_locks_basic_profile",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="profile",
            name="guardian_locks_visibility_settings",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="parentalcontrolchangerequest",
            name="proposed_bio",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="parentalcontrolchangerequest",
            name="proposed_location",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="parentalcontrolchangerequest",
            name="proposed_website_url",
            field=models.URLField(blank=True),
        ),
    ]
