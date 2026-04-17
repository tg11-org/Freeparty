from django.urls import re_path

from apps.private_messages.consumers import DirectMessageConsumer

websocket_urlpatterns = [
    re_path(r"ws/messages/(?P<conversation_id>[0-9a-f-]+)/$", DirectMessageConsumer.as_asgi()),
]