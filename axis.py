"""Virtual–Real Transition Axis v0.1.

A dependency-free reference prototype for virtual/real separation,
independent authority control, neutralization, recovery, and audit.

This is a behavioral model, not a production security boundary.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Mode(str, Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    ZERO_NEUTRAL = "zero_neutral"


class Role(str, Enum):
    VIRTUAL = "virtual"
    REAL = "real"


class AxisError(Exception):
    """Base exception for rejected axis operations."""


class AuthorityError(AxisError):
    """An operation is not authorized."""


class ValidationError(AxisError):
    """An event does not satisfy input requirements."""


@dataclass(frozen=True)
class Token:
    token_id: str
    role: Role
    generation: int


class AuditLog:
    """In-memory hash-chained audit records.

    The chain detects accidental modification within this process.
    It does not provide external tamper resistance.
    """

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def append(self, action: str, details: dict[str, Any]) -> None:
        previous_hash = (
            self.records[-1]["hash"] if self.records else "0" * 64
        )
        record = {
            "index": len(self.records),
            "action": action,
            "details": details,
            "previous_hash": previous_hash,
        }
        encoded = json.dumps(
            record, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        record["hash"] = hashlib.sha256(encoded).hexdigest()
        self.records.append(record)

    def verify(self) -> bool:
        previous_hash = "0" * 64

        for index, record in enumerate(self.records):
            if record.get("index") != index:
                return False
            if record.get("previous_hash") != previous_hash:
                return False

            payload = {
                "index": record.get("index"),
                "action": record.get("action"),
                "details": record.get("details"),
                "previous_hash": record.get("previous_hash"),
            }
            encoded = json.dumps(
                payload, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            expected = hashlib.sha256(encoded).hexdigest()

            if record.get("hash") != expected:
                return False

            previous_hash = expected

        return True


class TransitionAxis:
    """Independent deterministic control axis."""

    HARD_POLICY = frozenset(
        {
            "virtual_cannot_execute_real",
            "unverified_evidence_cannot_execute",
            "stale_authority_is_rejected",
            "human_approval_required_for_recovery",
        }
    )

    def __init__(self, virtual_limit: int = 3) -> None:
        if virtual_limit < 1:
            raise ValueError("virtual_limit must be positive")

        self.virtual_limit = virtual_limit
        self.virtual_load = 0
        self.mode = Mode.NORMAL
        self.generation = 0
        self.tokens: dict[str, Token] = {}
        self.audit = AuditLog()
        self.audit.append(
            "axis_initialized",
            {"virtual_limit": virtual_limit},
        )

    def issue_token(self, token_id: str, role: Role) -> Token:
        if not token_id:
            raise ValidationError("token_id must not be empty")
        if token_id in self.tokens:
            raise AuthorityError("duplicate token identifier")
        if self.mode == Mode.ZERO_NEUTRAL:
            raise AuthorityError("token issuance disabled in neutral mode")

        token = Token(token_id, role, self.generation)
        self.tokens[token_id] = token
        self.audit.append(
            "token_issued",
            {"token_id": token_id, "role": role.value},
        )
        return token

    def _authorize(self, token: Token, required: Role) -> None:
        registered = self.tokens.get(token.token_id)

        if registered != token:
            raise AuthorityError("unknown or mismatched token")
        if token.generation != self.generation:
            raise AuthorityError("stale authority generation")
        if token.role != required:
            raise AuthorityError("role is not authorized")
        if self.mode == Mode.ZERO_NEUTRAL:
            raise AuthorityError("axis is neutralized")

    def receive_virtual(
        self, token: Token, event: dict[str, Any]
    ) -> str:
        self._authorize(token, Role.VIRTUAL)

        if not isinstance(event, dict):
            raise ValidationError("event must be an object")
        if not isinstance(event.get("event_id"), str):
            raise ValidationError("event_id must be a string")
        if not event["event_id"]:
            raise ValidationError("event_id must not be empty")

        if self.virtual_load >= self.virtual_limit:
            self.mode = Mode.DEGRADED
            self.audit.append(
                "virtual_backpressure",
                {"event_id": event["event_id"]},
            )
            return "backpressure"

        self.virtual_load += 1
        self.audit.append(
            "virtual_event_accepted",
            {"event_id": event["event_id"]},
        )
        return "accepted"

    def execute_real(
        self,
        token: Token,
        operation: str,
        *,
        verified: bool,
    ) -> bool:
        self._authorize(token, Role.REAL)

        allowed_operations = {"analyze", "record", "propose"}

        if operation not in allowed_operations:
            raise AuthorityError("real operation is not permitted")
        if not verified:
            raise AuthorityError("unverified evidence is rejected")

        self.audit.append(
            "real_operation",
            {"operation": operation},
        )
        return True

    def update_hard_policy(
        self, token: Token, new_policy: set[str]
    ) -> None:
        """All role-level policy changes are forbidden."""
        raise AuthorityError(
            "hard policy cannot be modified by role tokens"
        )

    def neutralize(self, reason: str) -> None:
        """Revoke existing generations and enter zero-neutral mode."""
        if not reason:
            raise ValidationError("neutralization requires a reason")

        self.generation += 1
        self.mode = Mode.ZERO_NEUTRAL
        self.virtual_load = 0
        self.audit.append(
            "axis_neutralized",
            {"reason": reason, "generation": self.generation},
        )

    def recover(
        self,
        *,
        safety_verified: bool,
        human_approved: bool,
    ) -> bool:
        if self.mode != Mode.ZERO_NEUTRAL:
            return False

        if not (safety_verified and human_approved):
            self.audit.append(
                "recovery_denied",
                {
                    "safety_verified": safety_verified,
                    "human_approved": human_approved,
                },
            )
            return False

        self.mode = Mode.NORMAL
        self.virtual_load = 0
        self.audit.append(
            "axis_recovered",
            {"generation": self.generation},
        )
        return True

    def reset_virtual_load(self) -> None:
        """Simulate a new observation window."""
        if self.mode == Mode.ZERO_NEUTRAL:
            raise AuthorityError("cannot reset while neutralized")

        self.virtual_load = 0
        self.mode = Mode.NORMAL
        self.audit.append("virtual_window_reset", {})


def main() -> None:
    axis = TransitionAxis(virtual_limit=3)
    virtual = axis.issue_token("virtual-1", Role.VIRTUAL)
    real = axis.issue_token("real-1", Role.REAL)

    for number in range(1, 5):
        result = axis.receive_virtual(
            virtual, {"event_id": f"event-{number}"}
        )
        print(f"virtual event {number}: {result}")

    print(f"mode: {axis.mode.value}")

    print(
        "real verified analysis:",
        axis.execute_real(real, "analyze", verified=True),
    )

    axis.neutralize("simulated emergency")
    print(f"neutral: {axis.mode.value}")

    print(
        "recovery check 1:",
        axis.recover(
            safety_verified=True,
            human_approved=False,
        ),
    )

    print(
        "recovery check 2 + approval:",
        axis.recover(
            safety_verified=True,
            human_approved=True,
        ),
    )

    print(f"mode: {axis.mode.value}")
    print(f"audit chain valid: {axis.audit.verify()}")
    print(f"records: {len(axis.audit.records)}")


if __name__ == "__main__":
    main()
