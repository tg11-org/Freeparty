from __future__ import annotations

from datetime import timedelta
import re
from time import perf_counter
from uuid import UUID

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.utils import timezone

from apps.actors.models import Actor
from apps.private_messages.forms import EncryptedMessageEnvelopeForm
from apps.private_messages.models import Conversation, ConversationParticipant, EncryptedMessageAttachment, EncryptedMessageEnvelope, UserIdentityKey
from apps.private_messages.security import compute_identicon_seed, compute_safety_fingerprint_hex, has_remote_key_changed
from apps.private_messages.services import (
    ensure_active_identity_key,
    get_conversation_queryset_for_actor,
    get_or_create_direct_conversation,
    is_private_messages_enabled,
    mark_conversation_read,
    populate_conversation_activity,
    publish_direct_message_event,
    serialize_encrypted_envelope,
    register_browser_identity_key,
    send_direct_encrypted_message,
    store_encrypted_attachments,
)
from apps.social.models import Block
from apps.core.pagination import paginate_queryset
from apps.core.services.interaction_observability import log_interaction_metric


def _serialize_envelope_cursor(message: EncryptedMessageEnvelope | None) -> str:
    if message is None:
        return ""
    return f"{message.created_at.isoformat()}|{message.id}"


def _parse_envelope_cursor(raw_cursor: str) -> tuple | None:
    raw_cursor = (raw_cursor or "").strip()
    if not raw_cursor or "|" not in raw_cursor:
        return None
    created_at_raw, envelope_id_raw = raw_cursor.split("|", 1)
    normalized_created_at = re.sub(r" (?=[0-9]{2}:[0-9]{2}$)", "+", created_at_raw)
    created_at = parse_datetime(normalized_created_at)
    if created_at is None:
        return None
    try:
        envelope_id = UUID(envelope_id_raw)
    except ValueError:
        return None
    return created_at, envelope_id


def _public_keys_for_conversation(*, actor, other_participants: list[Actor]) -> dict[str, str]:
    participant_ids = [actor.id, *(other.id for other in other_participants)]
    known_keys = UserIdentityKey.objects.filter(actor_id__in=participant_ids).order_by("-created_at")
    return {key.key_id: key.public_key for key in known_keys}


def _serialize_envelope_for_request(*, request: HttpRequest, envelope: EncryptedMessageEnvelope) -> dict:
    payload = serialize_encrypted_envelope(envelope)
    payload["attachments"] = [
        {
            **attachment_payload,
            "download_url": reverse(
                "private_messages:download-attachment",
                kwargs={"conversation_id": envelope.conversation_id, "attachment_id": attachment_payload["id"]},
            ),
        }
        for attachment_payload in payload.get("attachments", [])
    ]
    return payload


def _validate_uploaded_attachments(uploaded_attachments, attachment_manifest: list[dict]) -> None:
    max_files = max(1, int(getattr(settings, "PM_ATTACHMENT_MAX_FILES", 5)))
    max_bytes = max(1, int(getattr(settings, "PM_ATTACHMENT_MAX_BYTES", 100 * 1024 * 1024)))
    if len(uploaded_attachments) > max_files:
        raise ValidationError(f"You can attach up to {max_files} encrypted files per message.")
    for uploaded in uploaded_attachments:
        if (getattr(uploaded, "size", 0) or 0) > max_bytes:
            raise ValidationError(f"Encrypted attachment exceeds the {max_bytes // (1024 * 1024)} MB limit.")
    if len(uploaded_attachments) != len(attachment_manifest):
        raise ValidationError("Encrypted attachment uploads do not match the attachment manifest.")


def _build_conversation_detail_context(*, request: HttpRequest, actor, conversation, form: EncryptedMessageEnvelopeForm | None = None) -> dict:
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
        .select_related("sender", "sender__user")
        .prefetch_related("attachments")
        .order_by("created_at", "id")
    )
    local_identity_keys = list(
        UserIdentityKey.objects.filter(actor=actor).order_by("-created_at")[:5]
    )
    remote_identity_keys = []
    if len(other_participants) == 1:
        remote_identity_keys = list(
            UserIdentityKey.objects.filter(actor=other_participants[0]).order_by("-created_at")[:5]
        )
    public_keys_by_key_id = _public_keys_for_conversation(actor=actor, other_participants=other_participants)
    envelope_payloads = [_serialize_envelope_for_request(request=request, envelope=message) for message in envelopes]
    latest_envelope = envelopes[-1] if envelopes else None

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
        "acknowledged_remote_key_id": self_participant.acknowledged_remote_key_id if self_participant else "",
        "local_identity_keys": local_identity_keys,
        "remote_identity_keys": remote_identity_keys,
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
        "latest_updates_cursor": _serialize_envelope_cursor(latest_envelope),
        "websocket_enabled": bool(getattr(settings, "FEATURE_PM_WEBSOCKET_ENABLED", False)),
        "websocket_url": f"/ws/messages/{conversation.id}/",
        "attachment_max_files": max(1, int(getattr(settings, "PM_ATTACHMENT_MAX_FILES", 5))),
        "attachment_max_bytes": max(1, int(getattr(settings, "PM_ATTACHMENT_MAX_BYTES", 100 * 1024 * 1024))),
    }


@login_required
@require_GET
def share_to_dm_view(request: HttpRequest) -> HttpResponse:
    """Show a picker of existing DM conversations to share a post link into."""
    post_id = request.GET.get("post_id", "").strip()
    post_url = request.GET.get("post_url", "").strip()
    if not post_id and not post_url:
        return redirect("private_messages:list")

    actor = request.user.actor
    if not is_private_messages_enabled():
        messages.error(request, "Private messaging is not enabled yet.")
        return redirect("core:index")

    conversations = populate_conversation_activity(
        actor=actor,
        conversations=get_conversation_queryset_for_actor(actor=actor),
    )
    return render(request, "private_messages/share_picker.html", {
        "conversations": conversations,
        "post_id": post_id,
        "post_url": post_url,
    })


@login_required
@require_GET
def conversation_list_view(request: HttpRequest) -> HttpResponse:
    actor = request.user.actor
    if not is_private_messages_enabled():
        return render(request, "private_messages/list.html", {"pm_enabled": False, "conversations": []})

    filter_type = request.GET.get("filter", "all").strip().lower()
    if filter_type not in {"all", "unread"}:
        filter_type = "all"

    conversations = populate_conversation_activity(
        actor=actor,
        conversations=get_conversation_queryset_for_actor(actor=actor),
    )
    if filter_type == "unread":
        conversations = [conversation for conversation in conversations if conversation.unread_message_count > 0]

    page_obj = paginate_queryset(request, conversations, per_page=20, page_param="page")
    conversations = list(page_obj.object_list)
    return render(
        request,
        "private_messages/list.html",
        {
            "pm_enabled": True,
            "conversations": conversations,
            "conversations_query_string": "filter=unread" if filter_type == "unread" else "",
            "page_obj": page_obj,
            "filter_type": filter_type,
            "viewer": actor,
            "viewer_has_active_key": UserIdentityKey.objects.filter(actor=actor, is_active=True).exists(),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
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
    redirect_url = f"/messages/{conversation.id}/"
    share_post = request.GET.get("share_post") or request.POST.get("share_post")
    if share_post:
        redirect_url += f"?share_post={share_post}"
    return redirect(redirect_url)


@login_required
@require_GET
def conversation_detail_view(request: HttpRequest, conversation_id: str) -> HttpResponse:
    actor = request.user.actor
    if not is_private_messages_enabled():
        messages.error(request, "Private messaging is not enabled yet.")
        return redirect("private_messages:list")

    conversation = get_object_or_404(
        Conversation.objects.prefetch_related("participants__actor", "participants__actor__profile", "messages__attachments"),
        id=conversation_id,
        participants__actor=actor,
    )
    mark_conversation_read(conversation=conversation, actor=actor)
    context = _build_conversation_detail_context(request=request, actor=actor, conversation=conversation)
    context["share_post_id"] = request.GET.get("share_post", "")
    return render(request, "private_messages/detail.html", context)


@login_required
@require_POST
def send_encrypted_message_view(request: HttpRequest, conversation_id: str) -> HttpResponse:
    actor = request.user.actor
    expects_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    if not is_private_messages_enabled():
        messages.error(request, "Private messaging is not enabled yet.")
        if expects_json:
            return JsonResponse({"ok": False, "error": "Private messaging is not enabled yet."}, status=400)
        return redirect("private_messages:list")

    conversation = get_object_or_404(
        Conversation.objects.prefetch_related("participants__actor", "participants__actor__profile", "messages__attachments"),
        id=conversation_id,
        participants__actor=actor,
    )

    # Phase 7.1: Rate limit message sends to prevent abuse
    message_rate_limit_messages = max(1, int(getattr(settings, "PM_MESSAGE_RATE_LIMIT_MESSAGES", 100)))
    message_rate_limit_window_seconds = max(1, int(getattr(settings, "PM_MESSAGE_RATE_LIMIT_WINDOW_SECONDS", 60)))

    recent_message_count = EncryptedMessageEnvelope.objects.filter(
        conversation=conversation,
        sender=actor,
        created_at__gte=timezone.now() - timedelta(seconds=message_rate_limit_window_seconds),
    ).count()

    if recent_message_count >= message_rate_limit_messages:
        messages.error(
            request,
            f"You have sent {recent_message_count} messages in the current safety window. "
            f"Please wait before sending more messages to this conversation."
        )
        if expects_json:
            return JsonResponse({"ok": False, "error": "Rate limit reached. Please wait before sending again."}, status=429)
        return redirect("private_messages:detail", conversation_id=conversation.id)

    form = EncryptedMessageEnvelopeForm(request.POST, request.FILES)
    if form.is_valid():
        uploaded_attachments = request.FILES.getlist("encrypted_attachments")
        try:
            _validate_uploaded_attachments(uploaded_attachments, form.cleaned_data["attachment_manifest"])
            with transaction.atomic():
                envelope = send_direct_encrypted_message(
                    conversation=conversation,
                    sender=actor,
                    ciphertext=form.cleaned_data["ciphertext"],
                    message_nonce=form.cleaned_data["message_nonce"],
                    client_message_id=form.cleaned_data["client_message_id"],
                    publish_event=False,
                )
                store_encrypted_attachments(
                    envelope=envelope,
                    uploaded_files=uploaded_attachments,
                    attachment_manifest=form.cleaned_data["attachment_manifest"],
                )
                publish_direct_message_event(envelope)
        except ValidationError as exc:
            form.add_error(None, exc.message)
        else:
            messages.success(request, "Encrypted message stored.")
            if expects_json:
                return JsonResponse({"ok": True})
            return redirect("private_messages:detail", conversation_id=conversation.id)

    if expects_json:
        error_list = []
        for errors in form.errors.values():
            error_list.extend(errors)
        return JsonResponse({"ok": False, "error": error_list[0] if error_list else "Unable to store encrypted message."}, status=400)
    return render(request, "private_messages/detail.html", _build_conversation_detail_context(request=request, actor=actor, conversation=conversation, form=form))


@login_required
@require_GET
def download_encrypted_attachment_view(request: HttpRequest, conversation_id: str, attachment_id: str) -> HttpResponse:
    actor = request.user.actor
    if not is_private_messages_enabled():
        raise Http404()

    attachment = get_object_or_404(
        EncryptedMessageAttachment.objects.select_related("envelope", "envelope__conversation"),
        id=attachment_id,
        envelope__conversation_id=conversation_id,
        envelope__conversation__participants__actor=actor,
    )
    response = FileResponse(attachment.encrypted_file.open("rb"), as_attachment=True, filename=f"{attachment.client_attachment_id}.bin")
    response["Content-Type"] = "application/octet-stream"
    response["Cache-Control"] = "private, no-store"
    return response


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

    # Phase 7.1: Rate limit acknowledgments to prevent spamming
    ack_cooldown_seconds = max(1, int(getattr(settings, "PM_KEY_ACK_COOLDOWN_SECONDS", 10)))
    if self_participant.acknowledged_remote_key_at:
        elapsed = timezone.now() - self_participant.acknowledged_remote_key_at
        if elapsed < timedelta(seconds=ack_cooldown_seconds):
            remaining = ack_cooldown_seconds - int(elapsed.total_seconds())
            messages.error(request, f"Please wait {remaining} seconds before acknowledging again.")
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

    # Phase 7.1: Rate limit key registration per actor
    key_registration_limit = max(1, int(getattr(settings, "PM_KEY_REGISTRATION_LIMIT", 5)))
    key_registration_window_seconds = max(1, int(getattr(settings, "PM_KEY_REGISTRATION_WINDOW_SECONDS", 86400)))
    recent_keys = UserIdentityKey.objects.filter(
        actor=actor,
        created_at__gte=timezone.now() - timedelta(seconds=key_registration_window_seconds),
    ).count()

    if recent_keys >= key_registration_limit:
        return JsonResponse(
            {"ok": False, "error": "You have registered too many keys in the current safety window. Please try again later."},
            status=429,
        )

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
    started_at = perf_counter()
    actor = request.user.actor
    if not is_private_messages_enabled():
        log_interaction_metric(
            name="dm_conversation_updates",
            success=False,
            duration_ms=(perf_counter() - started_at) * 1000,
            status_code=400,
            actor_id=str(actor.id),
            target_id=str(conversation_id),
            detail="feature_disabled",
        )
        return JsonResponse({"ok": False, "error": "Private messaging is not enabled."}, status=400)

    conversation = get_object_or_404(
        Conversation.objects.prefetch_related("participants__actor"),
        id=conversation_id,
        participants__actor=actor,
    )
    cursor = (request.GET.get("cursor") or "").strip()
    after = (request.GET.get("after") or "").strip()
    envelopes_qs = EncryptedMessageEnvelope.objects.filter(conversation=conversation).select_related("sender").prefetch_related("attachments").order_by("created_at", "id")
    parsed_cursor = _parse_envelope_cursor(cursor)
    if cursor and parsed_cursor is None:
        log_interaction_metric(
            name="dm_conversation_updates",
            success=False,
            duration_ms=(perf_counter() - started_at) * 1000,
            status_code=400,
            actor_id=str(actor.id),
            target_id=str(conversation.id),
            detail="invalid_cursor",
        )
        return JsonResponse({"ok": False, "error": "Invalid cursor."}, status=400)
    if parsed_cursor is not None:
        created_at, envelope_id = parsed_cursor
        envelopes_qs = envelopes_qs.filter(
            models.Q(created_at__gt=created_at)
            | models.Q(created_at=created_at, id__gt=envelope_id)
        )
    elif after:
        normalized_after = re.sub(r" (?=[0-9]{2}:[0-9]{2}$)", "+", after)
        after_dt = parse_datetime(normalized_after)
        if after_dt is None:
            log_interaction_metric(
                name="dm_conversation_updates",
                success=False,
                duration_ms=(perf_counter() - started_at) * 1000,
                status_code=400,
                actor_id=str(actor.id),
                target_id=str(conversation.id),
                detail="invalid_after_marker",
            )
            return JsonResponse({"ok": False, "error": "Invalid after marker."}, status=400)
        earliest_at_marker = (
            EncryptedMessageEnvelope.objects.filter(conversation=conversation, created_at=after_dt)
            .order_by("created_at", "id")
            .first()
        )
        if earliest_at_marker is not None:
            envelopes_qs = envelopes_qs.filter(
                models.Q(created_at__gt=after_dt)
                | models.Q(created_at=after_dt, id__gt=earliest_at_marker.id)
            )
        else:
            envelopes_qs = envelopes_qs.filter(created_at__gt=after_dt)

    limit = 100
    envelopes = list(envelopes_qs[: limit + 1])
    has_more = len(envelopes) > limit
    if has_more:
        envelopes = envelopes[:limit]
    latest_incoming = next((message for message in reversed(envelopes) if message.recipient_actor_id == actor.id), None)
    if latest_incoming is not None:
        mark_conversation_read(conversation=conversation, actor=actor, read_through=latest_incoming.created_at)
    envelope_payloads = [_serialize_envelope_for_request(request=request, envelope=message) for message in envelopes]
    other_participants = [participant.actor for participant in conversation.participants.all() if participant.actor_id != actor.id]
    latest_known = envelopes[-1] if envelopes else conversation.messages.order_by("created_at", "id").last()
    log_interaction_metric(
        name="dm_conversation_updates",
        success=True,
        duration_ms=(perf_counter() - started_at) * 1000,
        status_code=200,
        actor_id=str(actor.id),
        target_id=str(conversation.id),
        detail=f"envelopes={len(envelopes)} has_more={has_more}",
    )
    return JsonResponse(
        {
            "ok": True,
            "envelopes": envelope_payloads,
            "public_keys_by_key_id": _public_keys_for_conversation(actor=actor, other_participants=other_participants),
            "next_cursor": _serialize_envelope_cursor(latest_known),
            "poll_interval_ms": 5000,
            "has_more": has_more,
        }
    )