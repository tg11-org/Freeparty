from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("private_messages", "0002_conversationparticipant_remote_key_ack_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversationparticipant",
            name="last_read_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]