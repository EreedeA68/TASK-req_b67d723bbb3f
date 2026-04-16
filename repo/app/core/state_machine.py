"""Order state machine."""


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""


# Allowed transitions
TRANSITIONS = {
    "created": {"paid"},
    "paid": {"in_prep"},
    "in_prep": {"ready"},
    "ready": {"delivered"},
    "ready_for_pickup": {"delivered"},
    "delivered": {"reviewed"},
    "reviewed": set(),
    "cancelled": set(),
}

ORDERED_STATES = [
    "created", "paid", "in_prep", "ready",
    "ready_for_pickup", "delivered", "reviewed",
]

# States from which no further transition is allowed.
FINAL_STATES = frozenset({"reviewed", "cancelled"})


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, set())


def next_status(current: str) -> str:
    """Return the next status for advancement (raises if none)."""
    allowed = TRANSITIONS.get(current, set())
    if not allowed:
        raise InvalidTransitionError(
            f"No further transitions allowed from '{current}'"
        )
    # The state machine is strictly linear, so there should always be exactly one.
    return next(iter(allowed))


def validate_transition(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(
            f"Invalid transition: {current} -> {target}"
        )
