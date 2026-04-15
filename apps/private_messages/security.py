from __future__ import annotations

import hashlib


def _normalize_fingerprint(value: str) -> str:
    return "".join((value or "").lower().split())


def canonical_safety_fingerprint_input(local_fingerprint: str, remote_fingerprint: str) -> str:
    """Build an order-invariant canonical input for pairwise safety verification."""

    normalized = sorted([
        _normalize_fingerprint(local_fingerprint),
        _normalize_fingerprint(remote_fingerprint),
    ])
    return "|".join(normalized)


def compute_safety_fingerprint_hex(local_fingerprint: str, remote_fingerprint: str) -> str:
    """Return deterministic 64-char hex safety fingerprint for two participants."""

    canonical = canonical_safety_fingerprint_input(local_fingerprint, remote_fingerprint)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_identicon_seed(local_fingerprint: str, remote_fingerprint: str) -> str:
    """Return deterministic seed contract for visual fingerprint generation."""

    return compute_safety_fingerprint_hex(local_fingerprint, remote_fingerprint)[:32]


def has_remote_key_changed(*, acknowledged_remote_key_id: str, remote_key_id: str) -> bool:
    """Return whether the participant has not yet acknowledged the current remote key id."""

    normalized_ack = (acknowledged_remote_key_id or "").strip()
    normalized_remote = (remote_key_id or "").strip()
    return bool(normalized_remote) and normalized_ack != normalized_remote
