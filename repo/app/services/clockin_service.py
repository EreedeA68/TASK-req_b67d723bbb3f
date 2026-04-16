"""Clock-in validation service (simulated biometric pipeline)."""
import hashlib
import secrets
from datetime import datetime, timedelta

from flask import current_app

from app.db import db
from app.models.timepunch import TimePunch
from app.models.user import User
from app.services import audit_service


class ClockInError(Exception):
    """Error in clock-in operations."""


RATE_LIMIT_MAX = 3
RATE_LIMIT_WINDOW_MINUTES = 5


def _make_nonce() -> str:
    """Generate a cryptographically random nonce for anti-replay."""
    return secrets.token_hex(16)


def _canonical_hash(
    user_id: int,
    punch_type: str,
    device_id: str,
    face_match_score,
    brightness: float = 0.0,
    face_count: int = 0,
) -> str:
    """Hash the immutable punch payload for replay detection.

    Unlike the tamper-evident signature (which includes a random nonce),
    the canonical hash is deterministic for a given logical payload.  Two
    submissions with identical claims produce the same hash, so a DB
    look-up within the rate-limit window catches replays even when nonces
    differ.
    """
    payload = (
        f"{user_id}:{punch_type}:{device_id}"
        f":{face_match_score}:{brightness}:{face_count}"
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _make_signature(
    user_id: int,
    punch_type: str,
    device_id: str,
    nonce: str,
    face_match_score=0.0,
    brightness: float = 0.0,
    face_count: int = 0,
) -> str:
    """Tamper-evident signature from canonical punch payload + server secret.

    The signature is computed from the full punch payload content combined
    with a random nonce and the server secret.  The nonce makes each
    signature unique for tamper evidence, while the separate canonical_hash
    handles replay detection.
    """
    secret = current_app.config.get("SECRET_KEY", "")
    payload = (
        f"{user_id}:{punch_type}:{device_id}:{nonce}"
        f":{face_match_score}:{brightness}:{face_count}:{secret}"
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _check_rate_limit(user_id: int) -> bool:
    """Return True if the user has exceeded the rate limit."""
    cutoff = datetime.utcnow() - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)
    recent = TimePunch.query.filter(
        TimePunch.user_id == user_id,
        TimePunch.created_at >= cutoff,
    ).count()
    return recent >= RATE_LIMIT_MAX


def _check_replay(signature: str) -> bool:
    """Return True if this signature has already been used (anti-replay)."""
    return TimePunch.query.filter_by(signature=signature).first() is not None


def _check_canonical_replay(canonical: str) -> bool:
    """Return True if an identical logical payload was submitted recently.

    Checks within the rate-limit window so that legitimate punches at
    different times (e.g., next shift) are not blocked.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)
    return (
        TimePunch.query
        .filter(
            TimePunch.canonical_hash == canonical,
            TimePunch.created_at >= cutoff,
            TimePunch.success.is_(True),
        )
        .first()
    ) is not None


def _clamp(value: float, lo: float, hi: float) -> float:
    """Server-side clamping of client-reported values."""
    return max(lo, min(hi, value))


def _compute_face_match(face_image_hash: str | None, enrollment) -> float:
    """Compute face-match score server-side against enrollment reference.

    In a production deployment this would compare a captured image embedding
    against the enrollment template.  In the current offline implementation,
    we compare the SHA-256 hash of the submitted face artifact against the
    stored reference_hash.  An exact match yields 1.0; otherwise a
    similarity score is derived from the common prefix length (simulating
    a confidence metric from a real face-recognition engine).

    If no face_image_hash is submitted the function returns 0.0 so that
    the threshold check will reject the punch.
    """
    if not face_image_hash or not enrollment or not enrollment.reference_hash:
        return 0.0

    ref = enrollment.reference_hash
    submitted = face_image_hash

    if submitted == ref:
        return 1.0

    # Derive a degraded score from common prefix (simulated partial match).
    common = 0
    for a, b in zip(submitted, ref):
        if a == b:
            common += 1
        else:
            break
    return min(common / max(len(ref), 1), 0.99)


def validate_clock_in(
    *,
    user_id: int,
    face_match_score: float = 0.0,
    brightness: float = 0.0,
    face_count: int = 0,
    device_id: str,
    actor_id: int | None = None,
    punch_type: str = "clock_in",
    face_image_hash: str | None = None,
) -> TimePunch:
    """Run the server-side validation pipeline.

    When *face_image_hash* is provided the server computes the face-match
    score against the enrollment reference, overriding any client-supplied
    ``face_match_score``.  This is the intended production flow — the kiosk
    captures an image, hashes it, and submits the hash; the server performs
    the match computation.

    When *face_image_hash* is ``None`` the client-supplied score is used
    as a **fallback** (development/testing mode), clamped and bounds-checked.

    For clock_out punches, biometric checks are skipped — only device_id
    and rate limit are enforced.
    """
    if punch_type not in ("clock_in", "clock_out"):
        raise ClockInError("punch_type must be clock_in or clock_out")

    if user_id is None:
        raise ClockInError("user_id is required")
    if db.session.get(User, user_id) is None:
        raise ClockInError("user not found")

    if not device_id or not device_id.strip():
        raise ClockInError("device_id is required")

    now = datetime.utcnow()

    failures: list[str] = []

    # Rate limit check (first — if exceeded, reject without running other checks)
    if _check_rate_limit(user_id):
        failures.append("rate_limit_exceeded")
        # Early canonical hash for rate-limit record (uses raw inputs — it won't
        # be used for downstream replay checks because success=False).
        early_canonical = _canonical_hash(
            user_id, punch_type, device_id,
            face_match_score, brightness, face_count,
        )
        nonce = _make_nonce()
        early_sig = _make_signature(
            user_id, punch_type, device_id, nonce,
            face_match_score, brightness, face_count,
        )
        punch = _record(user_id, now, device_id, early_sig, False,
                        "rate_limit_exceeded", punch_type=punch_type,
                        canonical_hash=early_canonical)
        action_label = "clockin_failed" if punch_type == "clock_in" else "clockout_failed"
        audit_service.log(
            actor_id=actor_id,
            action=action_label,
            resource=f"user:{user_id}",
            metadata={"reason": "rate_limit_exceeded", "punch_type": punch_type},
        )
        return punch

    # For clock_out, skip biometric checks — only device_id + rate limit apply
    enrollment = None
    if punch_type == "clock_in":
        # Verify enrollment exists for this user
        from app.models.enrollment import Enrollment

        enrollment = Enrollment.query.filter_by(user_id=user_id, active=True).first()
        if enrollment is None:
            failures.append("no_active_enrollment")
        else:
            # Strict mode: require server-side artifact (no client-claim fallback).
            strict = current_app.config.get("CLOCKIN_STRICT", True)
            if strict and not face_image_hash:
                failures.append("artifact_required")

            # Device policy: device_id must match enrollment (if enrollment has one).
            if enrollment.device_id and enrollment.device_id != device_id:
                failures.append("device_not_enrolled")
                audit_service.log(
                    actor_id=actor_id,
                    action="clockin_device_mismatch",
                    resource=f"user:{user_id}",
                    metadata={
                        "submitted": device_id,
                        "enrolled": enrollment.device_id,
                    },
                )

            # Server-side face-match against enrollment reference.
            if face_image_hash:
                # Production path: compute match server-side from artifact.
                face_match_score = _compute_face_match(face_image_hash, enrollment)
            else:
                # Fallback/dev path: use client claim (clamped).
                face_match_score = _clamp(float(face_match_score or 0), 0.0, 1.0)

            brightness = _clamp(float(brightness or 0), 0.0, 1.0)
            face_count = int(face_count or 0)

            min_threshold = current_app.config.get("CLOCKIN_FACE_THRESHOLD", 0.85)
            min_brightness = current_app.config.get("CLOCKIN_MIN_BRIGHTNESS", 0.5)

            if face_match_score < min_threshold:
                failures.append("face_match_score_too_low")
            if brightness < min_brightness:
                failures.append("brightness_too_low")
            if face_count != 1:
                failures.append("invalid_face_count")

    # Canonical hash now uses server-verified values + artifact hash (if any),
    # so replay of the same artifact with varied client claims is detected.
    canonical_source_face = face_image_hash or f"claim:{face_match_score}"
    canonical = _canonical_hash(
        user_id, punch_type, device_id,
        canonical_source_face, brightness, face_count,
    )

    # Anti-replay: reject if identical logical payload succeeded recently.
    if _check_canonical_replay(canonical):
        raise ClockInError("duplicate submission detected")

    nonce = _make_nonce()
    signature = _make_signature(
        user_id, punch_type, device_id, nonce,
        canonical_source_face, brightness, face_count,
    )

    # Belt-and-suspenders: exact signature uniqueness (in case of collisions).
    if _check_replay(signature):
        raise ClockInError("duplicate submission detected")

    success = len(failures) == 0
    reason = "; ".join(failures) if failures else None
    punch = _record(user_id, now, device_id, signature, success, reason,
                    punch_type=punch_type, canonical_hash=canonical)

    if punch_type == "clock_in":
        action_label = "clockin_success" if success else "clockin_failed"
    else:
        action_label = "clockout_success" if success else "clockout_failed"

    audit_service.log(
        actor_id=actor_id,
        action=action_label,
        resource=f"user:{user_id}",
        metadata={
            "success": success,
            "reason": reason,
            "punch_type": punch_type,
            "verification_mode": "server_artifact" if face_image_hash else "client_claim",
        },
    )
    return punch


def _record(
    user_id: int,
    timestamp: datetime,
    device_id: str | None,
    signature: str,
    success: bool,
    reason: str | None,
    punch_type: str = "clock_in",
    canonical_hash: str | None = None,
) -> TimePunch:
    punch = TimePunch(
        user_id=user_id,
        punch_type=punch_type,
        timestamp=timestamp,
        device_fingerprint=device_id,
        success=success,
        reason=reason,
        signature=signature,
        canonical_hash=canonical_hash,
    )
    db.session.add(punch)
    db.session.commit()
    return punch
