from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0012_profile_show_follower_list_show_following_list"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="theme_custom_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="profile",
            name="theme_custom_bg",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="profile",
            name="theme_custom_bg_gradient",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="profile",
            name="theme_custom_surface",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="profile",
            name="theme_custom_surface2",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="profile",
            name="theme_custom_text",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="profile",
            name="theme_custom_text2",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="profile",
            name="theme_custom_accent",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="profile",
            name="theme_custom_accent_alt",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="profile",
            name="theme_custom_danger",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="profile",
            name="theme_custom_border",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="profile",
            name="theme_custom_focus",
            field=models.CharField(blank=True, max_length=32),
        ),
    ]
