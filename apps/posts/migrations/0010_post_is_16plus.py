from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("posts", "0009_rename_posts_hasht_tag_8a3530_idx_posts_hasht_tag_7a6858_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="post",
            name="is_16plus",
            field=models.BooleanField(
                default=False,
                help_text="Mark as 16+ content (teen/adult themes under EEA-style age gating).",
            ),
        ),
    ]
