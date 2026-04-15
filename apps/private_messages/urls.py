from django.urls import path

from apps.private_messages.views import (
    acknowledge_remote_key_view,
    bootstrap_identity_key_view,
    conversation_detail_view,
    conversation_list_view,
    register_identity_key_view,
    send_encrypted_message_view,
    start_direct_conversation_view,
)

app_name = "private_messages"

urlpatterns = [
    path("", conversation_list_view, name="list"),
    path("keys/bootstrap/", bootstrap_identity_key_view, name="bootstrap-key"),
    path("keys/register/", register_identity_key_view, name="register-key"),
    path("start/<str:handle>/", start_direct_conversation_view, name="start-direct"),
    path("<uuid:conversation_id>/", conversation_detail_view, name="detail"),
    path("<uuid:conversation_id>/send/", send_encrypted_message_view, name="send"),
    path("<uuid:conversation_id>/acknowledge-key/", acknowledge_remote_key_view, name="acknowledge-key"),
]