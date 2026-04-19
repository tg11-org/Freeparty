from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0009_profile_guardian_lock_fields_and_change_request_profile_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="guardian_restrict_dms_to_teens",
            field=models.BooleanField(default=False),
        ),
    ]
