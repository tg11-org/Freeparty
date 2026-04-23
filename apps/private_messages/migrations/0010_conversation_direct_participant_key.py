# Generated manually for direct conversation de-duplication hardening.

from django.db import migrations, models
from django.db.models import Q


def populate_direct_participant_keys(apps, schema_editor):
    Conversation = apps.get_model("private_messages", "Conversation")
    ConversationParticipant = apps.get_model("private_messages", "ConversationParticipant")

    seen_keys = set()
    direct_conversations = Conversation.objects.filter(conversation_type="direct").only("id")
    for conversation in direct_conversations.iterator():
        actor_ids = list(
            ConversationParticipant.objects.filter(conversation_id=conversation.id)
            .order_by("actor_id")
            .values_list("actor_id", flat=True)
        )
        if len(actor_ids) != 2:
            continue
        key = ":".join(str(actor_id) for actor_id in actor_ids)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        Conversation.objects.filter(id=conversation.id).update(direct_participant_key=key)


class Migration(migrations.Migration):

    dependencies = [
        ("private_messages", "0009_rename_private_mes_envelop_f4c77a_idx_private_mes_envelop_1ccaca_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="direct_participant_key",
            field=models.CharField(blank=True, db_index=True, max_length=80),
        ),
        migrations.RunPython(populate_direct_participant_keys, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="conversation",
            constraint=models.UniqueConstraint(
                fields=("direct_participant_key",),
                condition=~Q(direct_participant_key=""),
                name="uniq_direct_conversation_participant_key",
            ),
        ),
    ]
