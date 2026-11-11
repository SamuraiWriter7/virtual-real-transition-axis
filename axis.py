"""Virtual-Real Transition Axis v0.2.

Python 3.11+.
Standard library only.

Includes:
- v0.1 legacy behavioral reference
- v0.2 independent evidence verification
- Five-element authority restrictions
- Authority generation invalidation
- Zero-neutralization and recovery
- In-memory hash-chained audit

This is an experimental reference implementation.
It is not a production security boundary.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from evidence import (
    EvidenceError,
    EvidenceRecord,
    EvidenceVerifier,
    VerificationReceipt,
    canonical_json,
)
from five_elements import (
    Element,
    FiveElementError,
    FiveElementMatrix,
    RestrictionAction,
    RestrictionDecision,
    RestrictionRequest,
)


# ============================================================
# 1. Operating modes and authority types
# ============================================================

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
    """Input or configuration is invalid."""


@dataclass(frozen=True)
class Token:
    token_id: str
    role: Role
    generation: int


@dataclass(frozen=True)
class ElementToken:
    token_id: str
    element: Element
    generation: int


# ============================================================
# 2. Hash-chained audit log
# ============================================================

class AuditLog:
    """In-memory SHA-256 hash-chained audit records.

    Detects modifications without recomputing the chain.
    Does not provide external tamper resistance.
    """

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def append(
        self,
        action: str,
        details: dict[str, Any],
    ) -> None:
        previous_hash = (
            self.records[-1]["hash"]
            if self.records
            else "0" * 64
        )

        record = {
            "index": len(self.records),
            "action": action,
            "details": details,
            "previous_hash": previous_hash,
        }

        encoded = json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        record["hash"] = hashlib.sha256(
            encoded
        ).hexdigest()

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

            try:
                encoded = json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            except (TypeError, ValueError):
                return False

            expected = hashlib.sha256(
                encoded
            ).hexdigest()

            if record.get("hash") != expected:
                return False

            previous_hash = expected

        return True


# ============================================================
# 3. v0.1 legacy reference implementation
# ============================================================

class TransitionAxis:
    """VRTA v0.1 compatibility reference.

    This class preserves the original simulation behavior.

    IMPORTANT:
    The caller-supplied verified flag is NOT secure.
    New v0.2 integrations must use TransitionAxisV2.
    """

    HARD_POLICY = frozenset(
        {
            "virtual_cannot_execute_real",
            "unverified_evidence_cannot_execute",
            "stale_authority_is_rejected",
            "human_approval_required_for_recovery",
        }
    )

    def __init__(
        self,
        virtual_limit: int = 3,
    ) -> None:
        if virtual_limit < 1:
            raise ValueError(
                "virtual_limit must be positive"
            )

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

    def issue_token(
        self,
        token_id: str,
        role: Role,
    ) -> Token:
        if not token_id:
            raise ValidationError(
                "token_id must not be empty"
            )

        if token_id in self.tokens:
            raise AuthorityError(
                "duplicate token identifier"
            )

        if self.mode == Mode.ZERO_NEUTRAL:
            raise AuthorityError(
                "token issuance disabled in neutral mode"
            )

        token = Token(
            token_id,
            role,
            self.generation,
        )

        self.tokens[token_id] = token

        self.audit.append(
            "token_issued",
            {
                "token_id": token_id,
                "role": role.value,
            },
        )

        return token

    def _authorize(
        self,
        token: Token,
        required: Role,
    ) -> None:
        registered = self.tokens.get(
            token.token_id
        )

        if registered != token:
            raise AuthorityError(
                "unknown or mismatched token"
            )

        if token.generation != self.generation:
            raise AuthorityError(
                "stale authority generation"
            )

        if token.role != required:
            raise AuthorityError(
                "role is not authorized"
            )

        if self.mode == Mode.ZERO_NEUTRAL:
            raise AuthorityError(
                "axis is neutralized"
            )

    def receive_virtual(
        self,
        token: Token,
        event: dict[str, Any],
    ) -> str:
        self._authorize(token, Role.VIRTUAL)

        if not isinstance(event, dict):
            raise ValidationError(
                "event must be an object"
            )

        if not isinstance(
            event.get("event_id"), str
        ):
            raise ValidationError(
                "event_id must be a string"
            )

        if not event["event_id"]:
            raise ValidationError(
                "event_id must not be empty"
            )

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
        """Legacy simulation only."""
        self._authorize(token, Role.REAL)

        allowed = {
            "analyze",
            "record",
            "propose",
        }

        if operation not in allowed:
            raise AuthorityError(
                "real operation is not permitted"
            )

        if not verified:
            raise AuthorityError(
                "unverified evidence is rejected"
            )

        self.audit.append(
            "real_operation",
            {"operation": operation},
        )

        return True

    def update_hard_policy(
        self,
        token: Token,
        new_policy: set[str],
    ) -> None:
        raise AuthorityError(
            "hard policy cannot be modified by role tokens"
        )

    def neutralize(self, reason: str) -> None:
        if not reason:
            raise ValidationError(
                "neutralization requires a reason"
            )

        self.generation += 1
        self.mode = Mode.ZERO_NEUTRAL
        self.virtual_load = 0

        self.audit.append(
            "axis_neutralized",
            {
                "reason": reason,
                "generation": self.generation,
            },
        )

    def recover(
        self,
        *,
        safety_verified: bool,
        human_approved: bool,
    ) -> bool:
        if self.mode != Mode.ZERO_NEUTRAL:
            return False

        if not (
            safety_verified and human_approved
        ):
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
        if self.mode == Mode.ZERO_NEUTRAL:
            raise AuthorityError(
                "cannot reset while neutralized"
            )

        self.virtual_load = 0
        self.mode = Mode.NORMAL

        self.audit.append(
            "virtual_window_reset",
            {},
        )


# ============================================================
# 4. v0.2 independent transition axis
# ============================================================

class TransitionAxisV2(TransitionAxis):
    """VRTA v0.2 reference controller.

    Evidence and authority decisions are coordinated
    by the axis.

    All trust boundaries remain application-level.
    """

    ALLOWED_REAL_OPERATIONS = frozenset(
        {"analyze", "record", "propose"}
    )

    def __init__(
        self,
        *,
        virtual_limit: int = 3,
        trusted_sources: frozenset[str],
        element_bindings: Mapping[str, Element],
        administrator: object,
    ) -> None:
        super().__init__(
            virtual_limit=virtual_limit
        )

        if administrator is None:
            raise ValidationError(
                "administrator capability is required"
            )

        self._administrator = administrator

        self._accepted_events: set[str] = set()

        self._evidence_records: dict[
            str, EvidenceRecord
        ] = {}

        self._receipts: dict[
            str, VerificationReceipt
        ] = {}

        self._configured_elements: dict[
            str, Element
        ] = {}

        self._element_tokens: dict[
            str, ElementToken
        ] = {}

        self._used_request_ids: set[str] = set()

        self._active_restrictions: set[
            RestrictionAction
        ] = set()

        for token_id, element in element_bindings.items():
            if (
                not isinstance(token_id, str)
                or not token_id.strip()
                or not isinstance(element, Element)
            ):
                raise ValidationError(
                    "invalid element binding"
                )

            self._configured_elements[
                token_id
            ] = element

        self._verifier = EvidenceVerifier(
            verifier_id="vrta-verifier-v0.2",
            trusted_sources=trusted_sources,
            event_lookup=self._event_accepted,
            evidence_lookup=self._lookup_evidence,
        )

        self.audit.append(
            "axis_v0.2_initialized",
            {
                "trusted_source_count": len(
                    trusted_sources
                ),
                "element_binding_count": len(
                    self._configured_elements
                ),
            },
        )

    # --------------------------------------------------------
    # Internal evidence lookups
    # --------------------------------------------------------

    def _event_accepted(
        self,
        event_id: str,
    ) -> bool:
        return event_id in self._accepted_events

    def _lookup_evidence(
        self,
        evidence_id: str,
    ) -> EvidenceRecord | None:
        return self._evidence_records.get(
            evidence_id
        )

    # --------------------------------------------------------
    # Role token issuance
    # --------------------------------------------------------

    def issue_token(
        self,
        token_id: str,
        role: Role,
    ) -> Token:
        if token_id in self._element_tokens:
            raise AuthorityError(
                "token identifier already used"
            )

        return super().issue_token(
            token_id,
            role,
        )

    def issue_element_token(
        self,
        token_id: str,
    ) -> ElementToken:
        """Issue only preconfigured element authority."""
        if self.mode == Mode.ZERO_NEUTRAL:
            raise AuthorityError(
                "element issuance blocked in neutral mode"
            )

        if token_id not in self._configured_elements:
            raise AuthorityError(
                "element identity is not configured"
            )

        if (
            token_id in self._element_tokens
            or token_id in self.tokens
        ):
            raise AuthorityError(
                "duplicate token identifier"
            )

        token = ElementToken(
            token_id=token_id,
            element=self._configured_elements[token_id],
            generation=self.generation,
        )

        self._element_tokens[token_id] = token

        self.audit.append(
            "element_token_issued",
            {
                "token_id": token_id,
                "element": token.element.value,
                "generation": self.generation,
            },
        )

        return token

    def _authorize_element(
        self,
        token: ElementToken,
    ) -> Element:
        if not isinstance(token, ElementToken):
            raise AuthorityError(
                "invalid element token type"
            )

        registered = self._element_tokens.get(
            token.token_id
        )

        if registered != token:
            raise AuthorityError(
                "unknown or mismatched element token"
            )

        if token.generation != self.generation:
            raise AuthorityError(
                "stale element authority"
            )

        if self.mode == Mode.ZERO_NEUTRAL:
            raise AuthorityError(
                "axis is neutralized"
            )

        return token.element

    # --------------------------------------------------------
    # Virtual event intake
    # --------------------------------------------------------

    def receive_virtual(
        self,
        token: Token,
        event: dict[str, Any],
    ) -> str:
        self._authorize(
            token,
            Role.VIRTUAL,
        )

        if not isinstance(event, dict):
            raise ValidationError(
                "event must be an object"
            )

        event_id = event.get("event_id")

        if (
            not isinstance(event_id, str)
            or not event_id
        ):
            raise ValidationError(
                "event_id must be a non-empty string"
            )

        if (
            RestrictionAction.RESTRICT_INTAKE
            in self._active_restrictions
        ):
            self.audit.append(
                "virtual_intake_denied",
                {
                    "event_id": event_id,
                    "reason": "active_restriction",
                },
            )

            raise AuthorityError(
                "virtual intake is restricted"
            )

        if event_id in self._accepted_events:
            self.audit.append(
                "virtual_event_denied",
                {
                    "event_id": event_id,
                    "reason": "duplicate_event",
                },
            )

            raise ValidationError(
                "duplicate event identifier"
            )

        result = super().receive_virtual(
            token,
            event,
        )

        if result == "accepted":
            self._accepted_events.add(
                event_id
            )

        return result

    # --------------------------------------------------------
    # Independent evidence verification
    # --------------------------------------------------------

    def verify_evidence(
        self,
        evidence: Mapping[str, Any] | EvidenceRecord,
    ) -> VerificationReceipt:
        """Verify evidence and register an internal receipt.

        The operation is coordinated synchronously by
        the axis; it is not distributed or thread-safe.
        """
        if self.mode == Mode.ZERO_NEUTRAL:
            raise AuthorityError(
                "verification blocked in neutral mode"
            )

        try:
            record, receipt = self._verifier.verify(
                evidence,
                generation=self.generation,
            )

            # Snapshot the payload to avoid retaining
            # a caller-owned mutable JSON object.
            snapshot_payload = json.loads(
                canonical_json(record.payload)
            )

            stored_record = EvidenceRecord(
                evidence_id=record.evidence_id,
                event_id=record.event_id,
                source_id=record.source_id,
                payload=snapshot_payload,
                payload_digest=record.payload_digest,
            )

            if (
                stored_record.evidence_id
                in self._evidence_records
            ):
                raise ValidationError(
                    "duplicate evidence identifier"
                )

            if receipt.receipt_id in self._receipts:
                raise ValidationError(
                    "duplicate receipt identifier"
                )

            self._evidence_records[
                stored_record.evidence_id
            ] = stored_record

            self._receipts[
                receipt.receipt_id
            ] = receipt

            self.audit.append(
                "evidence_verified",
                {
                    "evidence_id": record.evidence_id,
                    "event_id": record.event_id,
                    "receipt_id": receipt.receipt_id,
                    "generation": self.generation,
                },
            )

            return receipt

        except (EvidenceError, ValidationError) as exc:
            self.audit.append(
                "evidence_verification_denied",
                {
                    "reason": type(exc).__name__,
                    "generation": self.generation,
                },
            )

            raise

    def _validate_receipt(
        self,
        receipt_id: str,
    ) -> VerificationReceipt:
        if not isinstance(receipt_id, str):
            raise AuthorityError(
                "invalid receipt identifier"
            )

        receipt = self._receipts.get(
            receipt_id
        )

        if receipt is None:
            raise AuthorityError(
                "unknown verification receipt"
            )

        if receipt.generation != self.generation:
            raise AuthorityError(
                "stale verification receipt"
            )

        if receipt.status != "verified":
            raise AuthorityError(
                "receipt is not verified"
            )

        if receipt.verifier_id != (
            self._verifier.verifier_id
        ):
            raise AuthorityError(
                "unexpected verifier identity"
            )

        record = self._evidence_records.get(
            receipt.evidence_id
        )

        if record is None:
            raise AuthorityError(
                "receipt evidence not registered"
            )

        if (
            receipt.event_id != record.event_id
            or receipt.payload_digest
            != record.payload_digest
        ):
            raise AuthorityError(
                "receipt evidence binding mismatch"
            )

        if not self._event_accepted(
            receipt.event_id
        ):
            raise AuthorityError(
                "receipt event is not accepted"
            )

        return receipt

    # --------------------------------------------------------
    # Block legacy verification bypass
    # --------------------------------------------------------

    def execute_real(
        self,
        token: Token,
        operation: str,
        *,
        verified: bool,
    ) -> bool:
        """Never accept the v0.1 Boolean verification path."""
        self.audit.append(
            "legacy_operation_denied",
            {
                "operation": str(operation),
                "reason": "legacy_verification_disabled",
            },
        )

        raise AuthorityError(
            "v0.2 requires a registered evidence receipt"
        )

    # --------------------------------------------------------
    # Verified real operations
    # --------------------------------------------------------

    def execute_real_verified(
        self,
        token: Token,
        operation: str,
        *,
        receipt_id: str,
        evidence_id: str | None = None,
        event_id: str | None = None,
    ) -> bool:
        """Authorize a simulated operation using stored evidence."""
        try:
            self._authorize(
                token,
                Role.REAL,
            )

            if (
                operation
                not in self.ALLOWED_REAL_OPERATIONS
            ):
                raise AuthorityError(
                    "real operation is not permitted"
                )

            receipt = self._validate_receipt(
                receipt_id
            )

            if (
                evidence_id is not None
                and evidence_id != receipt.evidence_id
            ):
                raise AuthorityError(
                    "evidence identifier mismatch"
                )

            if (
                event_id is not None
                and event_id != receipt.event_id
            ):
                raise AuthorityError(
                    "event identifier mismatch"
                )

            if (
                operation == "analyze"
                and RestrictionAction.SUSPEND_ANALYSIS
                in self._active_restrictions
            ):
                raise AuthorityError(
                    "analysis is suspended"
                )

            self.audit.append(
                "real_operation_verified",
                {
                    "operation": operation,
                    "receipt_id": receipt_id,
                    "evidence_id": receipt.evidence_id,
                    "generation": self.generation,
                },
            )

            return True

        except (AuthorityError, AttributeError) as exc:
            self.audit.append(
                "real_operation_denied",
                {
                    "operation": str(operation),
                    "reason": type(exc).__name__,
                },
            )

            if isinstance(exc, AttributeError):
                raise AuthorityError(
                    "invalid role token"
                ) from exc

            raise

    # --------------------------------------------------------
    # Five-element authority requests
    # --------------------------------------------------------

    def request_restriction(
        self,
        token: ElementToken,
        request: (
            Mapping[str, Any] | RestrictionRequest
        ),
    ) -> RestrictionDecision:
        """Validate a request and apply bounded restrictions."""
        try:
            actual_element = self._authorize_element(
                token
            )

            parsed = (
                request
                if isinstance(request, RestrictionRequest)
                else RestrictionRequest.from_mapping(
                    request
                )
            )

            if parsed.source_element != actual_element:
                raise AuthorityError(
                    "source element does not match authority"
                )

            if parsed.request_id in self._used_request_ids:
                raise AuthorityError(
                    "duplicate restriction request"
                )

            decision = FiveElementMatrix.validate(
                parsed
            )

            self._used_request_ids.add(
                parsed.request_id
            )

            if decision.restrictive:
                self._active_restrictions.add(
                    decision.action
                )

                self.audit.append(
                    "restriction_activated",
                    {
                        "request_id": decision.request_id,
                        "action": decision.action.value,
                    },
                )

            else:
                self.audit.append(
                    "restriction_advisory_accepted",
                    {
                        "request_id": decision.request_id,
                        "action": decision.action.value,
                    },
                )

            return decision

        except (
            FiveElementError,
            AuthorityError,
        ) as exc:
            self.audit.append(
                "restriction_denied",
                {
                    "reason": type(exc).__name__,
                    "generation": self.generation,
                },
            )
            raise

    def restriction_active(
        self,
        action: RestrictionAction,
    ) -> bool:
        return action in self._active_restrictions

    # --------------------------------------------------------
    # Administrative restriction release
    # --------------------------------------------------------

    def release_restriction(
        self,
        *,
        administrator: object,
        action: RestrictionAction,
    ) -> bool:
        """Release a restriction through bootstrap authority.

        The administrator object is an in-process capability.
        It is not a cryptographically authenticated principal.
        """
        if administrator is not self._administrator:
            self.audit.append(
                "restriction_release_denied",
                {"reason": "unauthorized_administrator"},
            )

            raise AuthorityError(
                "administrator capability required"
            )

        if self.mode == Mode.ZERO_NEUTRAL:
            raise AuthorityError(
                "cannot release restriction in neutral mode"
            )

        if not isinstance(action, RestrictionAction):
            raise ValidationError(
                "invalid restriction action"
            )

        if action not in self._active_restrictions:
            return False

        self._active_restrictions.remove(
            action
        )

        self.audit.append(
            "restriction_released",
            {"action": action.value},
        )

        return True

    # --------------------------------------------------------
    # Neutralization and recovery
    # --------------------------------------------------------

    def neutralize(self, reason: str) -> None:
        super().neutralize(reason)

        # Old receipts remain recorded but cannot be
        # used under the new authority generation.
        self._accepted_events.clear()

        self.audit.append(
            "v0.2_generation_invalidated",
            {
                "generation": self.generation,
                "receipts_invalidated": True,
                "element_tokens_invalidated": True,
            },
        )

    def recover(
        self,
        *,
        safety_verified: bool,
        human_approved: bool,
    ) -> bool:
        result = super().recover(
            safety_verified=safety_verified,
            human_approved=human_approved,
        )

        if result:
            self.audit.append(
                "v0.2_recovery_completed",
                {
                    "generation": self.generation,
                    "restrictions_preserved": True,
                },
            )

        return result

    def reset_virtual_load(self) -> None:
        super().reset_virtual_load()

        # A reset starts a new simulated event window.
        # Previously accepted events are no longer
        # eligible for new verification.
        self._accepted_events.clear()

        self.audit.append(
            "v0.2_event_window_reset",
            {"generation": self.generation},
        )


# ============================================================
# 5. Legacy deterministic simulation
# ============================================================

def main() -> None:
    """Preserve the original v0.1 simulation output."""
    axis = TransitionAxis(
        virtual_limit=3
    )

    virtual = axis.issue_token(
        "virtual-1",
        Role.VIRTUAL,
    )

    real = axis.issue_token(
        "real-1",
        Role.REAL,
    )

    for number in range(1, 5):
        result = axis.receive_virtual(
            virtual,
            {"event_id": f"event-{number}"},
        )

        print(
            f"virtual event {number}: {result}"
        )

    print(
        f"mode: {axis.mode.value}"
    )

    print(
        "real verified analysis:",
        axis.execute_real(
            real,
            "analyze",
            verified=True,
        ),
    )

    axis.neutralize(
        "simulated emergency"
    )

    print(
        f"neutral: {axis.mode.value}"
    )

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

    print(
        f"mode: {axis.mode.value}"
    )

    print(
        f"audit chain valid: {axis.audit.verify()}"
    )

    print(
        f"records: {len(axis.audit.records)}"
    )


if __name__ == "__main__":
    main()
