from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.private_messages.services import is_private_message_websocket_enabled


class DirectMessageConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope["user"]
        if user.is_anonymous:
            await self.close(code=4401)
            return
        if not is_private_message_websocket_enabled():
            await self.close(code=4403)
            return

        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        actor = getattr(user, "actor", None)
        if actor is None:
            await self.close(code=4403)
            return

        from apps.private_messages.models import ConversationParticipant

        is_participant = await ConversationParticipant.objects.filter(
            conversation_id=self.conversation_id,
            actor_id=actor.id,
        ).aexists()
        if not is_participant:
            await self.close(code=4403)
            return

        self.group_name = f"dm_conversation_{self.conversation_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"ok": True, "type": "dm.socket.ready", "conversation_id": str(self.conversation_id)})

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def dm_envelope(self, event):
        await self.send_json(event.get("payload", {}))