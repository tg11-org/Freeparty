from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0011_add_rejected_at_to_change_request"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="show_follower_list",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="profile",
            name="show_following_list",
            field=models.BooleanField(default=True),
        ),
    ]
