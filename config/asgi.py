"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

django_asgi_app = get_asgi_application()

# Import websocket routes only after Django app setup to avoid AppRegistryNotReady
# errors from model imports during ASGI startup.
from apps.notifications.routing import websocket_urlpatterns as notification_websocket_urlpatterns
from apps.private_messages.routing import websocket_urlpatterns as private_message_websocket_urlpatterns

application = ProtocolTypeRouter(
	{
		"http": django_asgi_app,
		"websocket": AuthMiddlewareStack(URLRouter(notification_websocket_urlpatterns + private_message_websocket_urlpatterns)),
	}
)
