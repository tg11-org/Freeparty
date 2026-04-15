from __future__ import annotations

import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone

from apps.actors.models import Actor
from apps.private_messages.forms import EncryptedMessageEnvelopeForm
from apps.private_messages.models import Conversation, ConversationParticipant, EncryptedMessageEnvelope, UserIdentityKey
from apps.private_messages.security import compute_identicon_seed, compute_safety_fingerprint_hex, has_remote_key_changed
from apps.private_messages.services import (
    ensure_active_identity_key,
    get_or_create_direct_conversation,
    is_private_messages_enabled,
    register_browser_identity_key,
    send_direct_encrypted_message,
)
from apps.social.models import Block


def _serialize_envelope(message: EncryptedMessageEnvelope) -> dict:
    return {
        "id": str(message.id),
        "sender_id": str(message.sender_id or ""),
        "sender_handle": message.sender.handle if message.sender else "unknown",
        "ciphertext": message.ciphertext,
        "message_nonce": message.message_nonce,
        "sender_key_id": message.sender_key_id,
        "recipient_key_id": message.recipient_key_id,
        "created_at": message.created_at.isoformat(),
    }


def _public_keys_for_conversation(*, actor, other_participants: list[Actor]) -> dict[str, str]:
    participant_ids = [actor.id, *(other.id for other in other_participants)]
    known_keys = UserIdentityKey.objects.filter(actor_id__in=participant_ids).order_by("-created_at")
    return {key.key_id: key.public_key for key in known_keys}


def _build_conversation_detail_context(*, actor, conversation, form: EncryptedMessageEnvelopeForm | None = None) -> dict:
    participant_records = list(conversation.participants.all())
    self_participant = next((participant for participant in participant_records if participant.actor_id == actor.id), None)
    other_participants = [participant.actor for participant in participant_records if participant.actor_id != actor.id]
    local_key = UserIdentityKey.objects.filter(actor=actor, is_active=True).order_by("-created_at").first()
    remote_key = None
    if len(other_participants) == 1:
        remote_key = UserIdentityKey.objects.filter(actor=other_participants[0], is_active=True).order_by("-created_at").first()

    safety_fingerprint = None
    identicon_seed = None
    can_send_encrypted = local_key is not None and remote_key is not None and len(other_participants) == 1
    send_block_reason = ""
    key_change_warning = ""
    key_change_acknowledged = True
    if local_key and remote_key:
        safety_fingerprint = compute_safety_fingerprint_hex(local_key.fingerprint_hex, remote_key.fingerprint_hex)
        identicon_seed = compute_identicon_seed(local_key.fingerprint_hex, remote_key.fingerprint_hex)
        if self_participant is not None:
            key_change_acknowledged = not has_remote_key_changed(
                acknowledged_remote_key_id=self_participant.acknowledged_remote_key_id,
                remote_key_id=remote_key.key_id,
            )
            if not key_change_acknowledged:
                key_change_warning = f"@{other_participants[0].handle} has a new active safety key. Verify the fingerprint before trusting new messages."
    elif len(other_participants) != 1:
        send_block_reason = "Encrypted compose is currently limited to one-to-one conversations."
    else:
        send_block_reason = "Both participants need active identity keys before encrypted send is available."

    envelopes = list(
        EncryptedMessageEnvelope.objects.filter(conversation=conversation)
        .select_related("sender")
        .order_by("created_at")
    )
    public_keys_by_key_id = _public_keys_for_conversation(actor=actor, other_participants=other_participants)
    envelope_payloads = [_serialize_envelope(message) for message in envelopes]

    return {
        "conversation": conversation,
        "viewer": actor,
        "other_participants": other_participants,
        "envelopes": envelopes,
        "safety_fingerprint": safety_fingerprint,
        "identicon_seed": identicon_seed,
        "message_form": form or EncryptedMessageEnvelopeForm(),
        "can_send_encrypted": can_send_encrypted,
        "send_block_reason": send_block_reason,
        "local_has_active_key": local_key is not None,
        "remote_has_active_key": remote_key is not None,
        "remote_handle": other_participants[0].handle if len(other_participants) == 1 else "",
        "key_change_warning": key_change_warning,
        "key_change_acknowledged": key_change_acknowledged,
        "current_remote_key_id": remote_key.key_id if remote_key else "",
        "show_ciphertext_preview": bool(
            getattr(settings, "FEATURE_PM_DEV_CIPHERTEXT_PREVIEW", False)
            and getattr(settings, "DEBUG", False)
        ),
        "local_active_key_id": local_key.key_id if local_key else "",
        "local_active_key_algorithm": local_key.algorithm if local_key else "",
        "remote_active_key_id": remote_key.key_id if remote_key else "",
        "remote_active_key_algorithm": remote_key.algorithm if remote_key else "",
        "remote_public_key": remote_key.public_key if remote_key else "",
        "envelope_payloads": envelope_payloads,
        "public_keys_by_key_id": public_keys_by_key_id,
        "updates_url": f"/messages/{conversation.id}/updates/",
    }


@login_required
@require_GET
def conversation_list_view(request: HttpRequest) -> HttpResponse:
    actor = request.user.actor
    if not is_private_messages_enabled():
        return render(request, "private_messages/list.html", {"pm_enabled": False, "conversations": []})

    conversations = (
        Conversation.objects.filter(participants__actor=actor)
        .prefetch_related("participants__actor", "participants__actor__profile")
        .distinct()
        .order_by("-updated_at")
    )
    return render(
        request,
        "private_messages/list.html",
        {
            "pm_enabled": True,
            "conversations": conversations,
            "viewer": actor,
            "viewer_has_active_key": UserIdentityKey.objects.filter(actor=actor, is_active=True).exists(),
        },
    )


@login_required
@require_POST
def start_direct_conversation_view(request: HttpRequest, handle: str) -> HttpResponse:
    if not is_private_messages_enabled():
        messages.error(request, "Private messaging is not enabled yet.")
        return redirect("actors:detail", handle=handle)

    actor = request.user.actor
    target = get_object_or_404(Actor, handle=handle, state=Actor.ActorState.ACTIVE)
    if actor.id == target.id:
        messages.error(request, "You cannot start a DM with yourself.")
        return redirect("actors:detail", handle=handle)
    if Block.objects.filter(blocker=actor, blocked=target).exists() or Block.objects.filter(blocker=target, blocked=actor).exists():
        messages.error(request, "You cannot start a DM with this account.")
        return redirect("actors:detail", handle=handle)

    conversation, created = get_or_create_direct_conversation(
        created_by=actor,
        participant_a=actor,
        participant_b=target,
    )
    messages.success(request, f"DM {'started' if created else 'opened'} with @{target.handle}.")
    return redirect("private_messages:detail", conversation_id=conversation.id)


@login_required
@require_GET
def conversation_detail_view(request: HttpRequest, conversation_id: str) -> HttpResponse:
    actor = request.user.actor
    if not is_private_messages_enabled():
        messages.error(request, "Private messaging is not enabled yet.")
        return redirect("private_messages:list")

    conversation = get_object_or_404(
        Conversation.objects.prefetch_related("participants__actor", "participants__actor__profile", "messages"),
        id=conversation_id,
        participants__actor=actor,
    )
    return render(request, "private_messages/detail.html", _build_conversation_detail_context(actor=actor, conversation=conversation))


@login_required
@require_POST
def send_encrypted_message_view(request: HttpRequest, conversation_id: str) -> HttpResponse:
    actor = request.user.actor
    if not is_private_messages_enabled():
        messages.error(request, "Private messaging is not enabled yet.")
        return redirect("private_messages:list")

    conversation = get_object_or_404(
        Conversation.objects.prefetch_related("participants__actor", "participants__actor__profile", "messages"),
        id=conversation_id,
        participants__actor=actor,
    )
    form = EncryptedMessageEnvelopeForm(request.POST)
    if form.is_valid():
        try:
            send_direct_encrypted_message(
                conversation=conversation,
                sender=actor,
                ciphertext=form.cleaned_data["ciphertext"],
                message_nonce=form.cleaned_data["message_nonce"],
                client_message_id=form.cleaned_data["client_message_id"],
            )
        except ValidationError as exc:
            form.add_error(None, exc.message)
        else:
            messages.success(request, "Encrypted message envelope stored.")
            return redirect("private_messages:detail", conversation_id=conversation.id)

    return render(request, "private_messages/detail.html", _build_conversation_detail_context(actor=actor, conversation=conversation, form=form))


@login_required
@require_POST
def acknowledge_remote_key_view(request: HttpRequest, conversation_id: str) -> HttpResponse:
    actor = request.user.actor
    if not is_private_messages_enabled():
        messages.error(request, "Private messaging is not enabled yet.")
        return redirect("private_messages:list")

    conversation = get_object_or_404(Conversation.objects.prefetch_related("participants__actor"), id=conversation_id, participants__actor=actor)
    self_participant = get_object_or_404(ConversationParticipant, conversation=conversation, actor=actor)
    other_participants = [participant.actor for participant in conversation.participants.all() if participant.actor_id != actor.id]
    if len(other_participants) != 1:
        messages.error(request, "Key acknowledgment is currently limited to direct conversations.")
        return redirect("private_messages:detail", conversation_id=conversation.id)

    remote_key = UserIdentityKey.objects.filter(actor=other_participants[0], is_active=True).order_by("-created_at").first()
    if remote_key is None:
        messages.error(request, "No active remote key is available to acknowledge.")
        return redirect("private_messages:detail", conversation_id=conversation.id)

    self_participant.acknowledged_remote_key_id = remote_key.key_id
    self_participant.acknowledged_remote_key_at = timezone.now()
    self_participant.save(update_fields=["acknowledged_remote_key_id", "acknowledged_remote_key_at", "updated_at"])
    messages.success(request, f"Acknowledged safety key {remote_key.key_id} for @{other_participants[0].handle}.")
    return redirect("private_messages:detail", conversation_id=conversation.id)


@login_required
@require_POST
def bootstrap_identity_key_view(request: HttpRequest) -> HttpResponse:
    actor = request.user.actor
    if not is_private_messages_enabled():
        messages.error(request, "Private messaging is not enabled yet.")
        return redirect("private_messages:list")

    rotate = request.POST.get("rotate") == "1"
    key, created = ensure_active_identity_key(actor=actor, rotate=rotate)
    if created:
        messages.success(request, f"Active identity key is now available: {key.key_id}")
    else:
        messages.info(request, f"You already have an active identity key: {key.key_id}")

    next_url = request.POST.get("next", "").strip()
    if next_url:
        return redirect(next_url)
    return redirect("private_messages:list")


@login_required
@require_POST
def register_identity_key_view(request: HttpRequest) -> HttpResponse:
    actor = request.user.actor
    if not is_private_messages_enabled():
        return JsonResponse({"ok": False, "error": "Private messaging is not enabled."}, status=400)

    key_id = request.POST.get("key_id", "").strip()
    public_key = request.POST.get("public_key", "").strip()
    fingerprint_hex = request.POST.get("fingerprint_hex", "").strip().lower()
    if not key_id or not public_key or not re.fullmatch(r"[0-9a-f]{64}", fingerprint_hex):
        return JsonResponse(
            {
                "ok": False,
                "error": "Invalid identity key payload. Expected key_id, public_key, fingerprint_hex.",
            },
            status=400,
        )

    try:
        key, created = register_browser_identity_key(
            actor=actor,
            key_id=key_id,
            public_key=public_key,
            fingerprint_hex=fingerprint_hex,
        )
    except ValidationError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "created": created,
            "key_id": key.key_id,
            "fingerprint_hex": key.fingerprint_hex,
        }
    )


@login_required
@require_GET
def conversation_updates_view(request: HttpRequest, conversation_id: str) -> HttpResponse:
    actor = request.user.actor
    if not is_private_messages_enabled():
        return JsonResponse({"ok": False, "error": "Private messaging is not enabled."}, status=400)

    conversation = get_object_or_404(
        Conversation.objects.prefetch_related("participants__actor"),
        id=conversation_id,
        participants__actor=actor,
    )
    after = (request.GET.get("after") or "").strip()
    envelopes_qs = EncryptedMessageEnvelope.objects.filter(conversation=conversation).select_related("sender").order_by("created_at")
    if after:
        envelopes_qs = envelopes_qs.filter(created_at__gt=after)

    envelope_payloads = [_serialize_envelope(message) for message in envelopes_qs[:100]]
    other_participants = [participant.actor for participant in conversation.participants.all() if participant.actor_id != actor.id]
    return JsonResponse(
        {
            "ok": True,
            "envelopes": envelope_payloads,
            "public_keys_by_key_id": _public_keys_for_conversation(actor=actor, other_participants=other_participants),
        }
    )