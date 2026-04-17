# Generated migration: Security hardening for Phase 7.1 PM key lifecycle
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("private_messages", "0005_keylifecycleauditlog_useridentitykey_compromised_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="compromised_at",
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text="Set when conversation is suspected compromised; invalidates prior messages",
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="compromise_reason",
            field=models.TextField(blank=True, help_text="Description of compromise incident"),
        ),
        migrations.AddField(
            model_name="useridentitykey",
            name="revoked_at",
            field=models.DateTimeField(null=True, blank=True, help_text="Set when key is revoked"),
        ),
        migrations.AddField(
            model_name="useridentitykey",
            name="revocation_reason",
            field=models.TextField(blank=True, help_text="Reason for key revocation"),
        ),
        migrations.AddField(
            model_name="useridentitykey",
            name="rotation_cooldown_until",
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text="Prevent spam: timestamp after which next rotation is allowed",
            ),
        ),
        migrations.AddField(
            model_name="useridentitykey",
            name="creation_source",
            field=models.CharField(
                max_length=32,
                default="bootstrap",
                choices=[
                    ("bootstrap", "Bootstrap"),
                    ("browser", "Browser"),
                    ("federation", "Federation"),
                ],
                help_text="Origin of key: bootstrap (dev), browser (prod), or federation",
            ),
        ),
        # Add index for revoked key detection
        migrations.AddIndex(
            model_name="useridentitykey",
            index=models.Index(fields=["actor", "revoked_at"], name="idx_useridentitykey_actor_revoked"),
        ),
        # Add index for conversation compromise detection
        migrations.AddIndex(
            model_name="conversation",
            index=models.Index(fields=["compromised_at"], name="idx_conversation_compromised"),
        ),
    ]
