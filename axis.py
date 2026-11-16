"""Virtual-Real Transition Axis v0.3.

Python 3.11+.
Standard library only.

Versions:
- TransitionAxis: v0.1 legacy reference
- TransitionAxisV2: evidence and five-element control
- TransitionAxisV3: seesaw negative feedback integration

Experimental behavioral prototype.
Not a production security boundary.
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

from feedback import (
    FeedbackConfig,
    FeedbackController,
    FeedbackDecision,
    FeedbackError,
    FeedbackMode,
    FeedbackReason,
    LoadObservation,
)


# ============================================================
# 1. Basic types
# ============================================================

class Mode(str, Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    ZERO_NEUTRAL = "zero_neutral"


class Role(str, Enum):
    VIRTUAL = "virtual"
    REAL = "real"


class AxisError(Exception):
    """Base axis exception."""


class AuthorityError(AxisError):
    """Operation is not authorized."""


class ValidationError(AxisError):
    """Invalid input or configuration."""


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
# 2. Audit log
# ============================================================

class AuditLog:
    """In-memory SHA-256 hash-chained audit.

    This detects simple record modification.
    It does not protect against a process-level attacker.
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
# 3. v0.1 compatibility
# ============================================================

class TransitionAxis:
    """Original v0.1 behavioral reference.

    The verified Boolean is a simulation flag.
    Do not use this class for v0.2/v0.3 authorization.
    """

    HARD_POLICY = frozenset({
        "virtual_cannot_execute_real",
        "unverified_evidence_cannot_execute",
        "stale_authority_is_rejected",
        "human_approval_required_for_recovery",
    })

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
        if not isinstance(token, Token):
            raise AuthorityError(
                "invalid token type"
            )

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
        """Legacy v0.1 simulation only."""
        self._authorize(token, Role.REAL)

        if operation not in {
            "analyze",
            "record",
            "propose",
        }:
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
# 4. v0.2 evidence and five-element integration
# ============================================================

class TransitionAxisV2(TransitionAxis):
    """v0.2 independent evidence and authority controller."""

    ALLOWED_REAL_OPERATIONS = frozenset({
        "analyze",
        "record",
        "propose",
    })

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
            self._accepted_events.add(event_id)

        return result

    def verify_evidence(
        self,
        evidence: Mapping[str, Any] | EvidenceRecord,
    ) -> VerificationReceipt:
        if self.mode == Mode.ZERO_NEUTRAL:
            raise AuthorityError(
                "verification blocked in neutral mode"
            )

        try:
            record, receipt = self._verifier.verify(
                evidence,
                generation=self.generation,
            )

            snapshot_payload = json.loads(
                canonical_json(record.payload)
            )

            stored = EvidenceRecord(
                evidence_id=record.evidence_id,
                event_id=record.event_id,
                source_id=record.source_id,
                payload=snapshot_payload,
                payload_digest=record.payload_digest,
            )

            if stored.evidence_id in self._evidence_records:
                raise ValidationError(
                    "duplicate evidence identifier"
                )

            if receipt.receipt_id in self._receipts:
                raise ValidationError(
                    "duplicate receipt identifier"
                )

            self._evidence_records[
                stored.evidence_id
            ] = stored

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

        receipt = self._receipts.get(receipt_id)

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

        if receipt.verifier_id != self._verifier.verifier_id:
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
            or receipt.payload_digest != record.payload_digest
        ):
            raise AuthorityError(
                "receipt evidence binding mismatch"
            )

        if not self._event_accepted(receipt.event_id):
            raise AuthorityError(
                "receipt event is not accepted"
            )

        return receipt

    def execute_real(
        self,
        token: Token,
        operation: str,
        *,
        verified: bool,
    ) -> bool:
        """Block the v0.1 self-verification path."""
        self.audit.append(
            "legacy_operation_denied",
            {
                "operation": str(operation),
                "reason": "legacy_verification_disabled",
            },
        )

        raise AuthorityError(
            "v0.2+ requires a registered evidence receipt"
        )

    def execute_real_verified(
        self,
        token: Token,
        operation: str,
        *,
        receipt_id: str,
        evidence_id: str | None = None,
        event_id: str | None = None,
    ) -> bool:
        try:
            self._authorize(token, Role.REAL)

            if operation not in self.ALLOWED_REAL_OPERATIONS:
                raise AuthorityError(
                    "real operation is not permitted"
                )

            receipt = self._validate_receipt(receipt_id)

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

    def request_restriction(
        self,
        token: ElementToken,
        request: Mapping[str, Any] | RestrictionRequest,
    ) -> RestrictionDecision:
        try:
            actual_element = self._authorize_element(token)

            parsed = (
                request
                if isinstance(request, RestrictionRequest)
                else RestrictionRequest.from_mapping(request)
            )

            if parsed.source_element != actual_element:
                raise AuthorityError(
                    "source element does not match authority"
                )

            if parsed.request_id in self._used_request_ids:
                raise AuthorityError(
                    "duplicate restriction request"
                )

            decision = FiveElementMatrix.validate(parsed)

            self._used_request_ids.add(parsed.request_id)

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

        except (FiveElementError, AuthorityError) as exc:
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

    def release_restriction(
        self,
        *,
        administrator: object,
        action: RestrictionAction,
    ) -> bool:
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

        self._active_restrictions.remove(action)

        self.audit.append(
            "restriction_released",
            {"action": action.value},
        )

        return True

    def neutralize(self, reason: str) -> None:
        super().neutralize(reason)

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

        self._accepted_events.clear()

        self.audit.append(
            "v0.2_event_window_reset",
            {"generation": self.generation},
        )


# ============================================================
# 5. v0.3 seesaw feedback integration
# ============================================================

class TransitionAxisV3(TransitionAxisV2):
    """Independent axis with deterministic feedback control.

    The controller is used only through axis-owned evaluation.

    No public API accepts an arbitrary FeedbackDecision
    as authority to change the operating mode.

    The reference implementation assumes sequential access.
    """

    def __init__(
        self,
        *,
        virtual_limit: int = 3,
        trusted_sources: frozenset[str],
        element_bindings: Mapping[str, Element],
        administrator: object,
        feedback_config: FeedbackConfig | None = None,
    ) -> None:
        super().__init__(
            virtual_limit=virtual_limit,
            trusted_sources=trusted_sources,
            element_bindings=element_bindings,
            administrator=administrator,
        )

        self._feedback_controller = FeedbackController(
            feedback_config
        )

        # Independent degradation causes.
        self._feedback_degraded = False
        self._legacy_degraded = False

        self.audit.append(
            "axis_v0.3_initialized",
            {
                "degrade_threshold": (
                    self._feedback_controller
                    .config.degrade_threshold
                ),
                "recover_threshold": (
                    self._feedback_controller
                    .config.recover_threshold
                ),
                "stable_windows_required": (
                    self._feedback_controller
                    .config.stable_windows_required
                ),
            },
        )

    # --------------------------------------------------------
    # Read-only diagnostics
    # --------------------------------------------------------

    @property
    def feedback_history(
        self,
    ) -> tuple[LoadObservation, ...]:
        return self._feedback_controller.history

    @property
    def feedback_stable_count(self) -> int:
        return self._feedback_controller.stable_count

    @property
    def degradation_causes(self) -> tuple[str, ...]:
        causes = []

        if self._legacy_degraded:
            causes.append("virtual_event_limit")

        if self._feedback_degraded:
            causes.append("feedback_overload")

        return tuple(causes)

    def feedback_snapshot(self) -> dict[str, Any]:
        """Return diagnostic data without granting authority."""
        snapshot = self._feedback_controller.snapshot()

        return {
            "axis_mode": self.mode.value,
            "generation": self.generation,
            "degradation_causes": self.degradation_causes,
            "controller": snapshot,
        }

    # --------------------------------------------------------
    # Authoritative state synchronization
    # --------------------------------------------------------

    def _synchronize_mode(
        self,
        *,
        reason: str,
    ) -> None:
        """Recompute the mode from active degradation causes.

        Zero-neutral always has priority.
        """
        if self.mode == Mode.ZERO_NEUTRAL:
            return

        previous = self.mode

        if (
            self._feedback_degraded
            or self._legacy_degraded
        ):
            self.mode = Mode.DEGRADED
        else:
            self.mode = Mode.NORMAL

        if self.mode != previous:
            self.audit.append(
                "axis_mode_transition",
                {
                    "previous_mode": previous.value,
                    "new_mode": self.mode.value,
                    "reason": reason,
                    "causes": list(
                        self.degradation_causes
                    ),
                    "generation": self.generation,
                },
            )

    # --------------------------------------------------------
    # Legacy virtual-event degradation
    # --------------------------------------------------------

    def receive_virtual(
        self,
        token: Token,
        event: dict[str, Any],
    ) -> str:
        """Preserve event-count backpressure independently."""
        result = super().receive_virtual(
            token,
            event,
        )

        if result == "backpressure":
            self._legacy_degraded = True

            self.audit.append(
                "legacy_degradation_activated",
                {
                    "virtual_load": self.virtual_load,
                    "virtual_limit": self.virtual_limit,
                },
            )

        self._synchronize_mode(
            reason="virtual_event_intake"
        )

        return result

    def reset_virtual_load(self) -> None:
        """Clear only the legacy event-count degradation cause.

        Feedback degradation is intentionally preserved.
        """
        if self.mode == Mode.ZERO_NEUTRAL:
            raise AuthorityError(
                "cannot reset while neutralized"
            )

        # The v0.2 parent implementation also resets
        # accepted-event bindings.
        super().reset_virtual_load()

        self._legacy_degraded = False

        self._synchronize_mode(
            reason="legacy_window_reset"
        )

        self.audit.append(
            "legacy_degradation_cleared",
            {
                "feedback_degraded": (
                    self._feedback_degraded
                ),
                "generation": self.generation,
            },
        )

    # --------------------------------------------------------
    # Axis-owned feedback evaluation
    # --------------------------------------------------------

    def observe_load(
        self,
        observation: (
            Mapping[str, Any] | LoadObservation
        ),
    ) -> FeedbackDecision:
        """Observe load and apply bounded feedback decisions.

        The caller supplies an observation, not a mode decision.

        The independent axis uses its own controller to
        evaluate the observation and update only the
        feedback-related degradation cause.
        """
        previous_mode = self.mode

        # The controller evaluates its own active feedback
        # condition, not the combined axis degradation state.
        #
        # This separation prevents an unrelated legacy
        # degradation cause from being cleared by feedback.
        if self.mode == Mode.ZERO_NEUTRAL:
            feedback_mode = FeedbackMode.ZERO_NEUTRAL
        elif self._feedback_degraded:
            feedback_mode = FeedbackMode.DEGRADED
        else:
            feedback_mode = FeedbackMode.NORMAL

        try:
            decision = self._feedback_controller.evaluate(
                observation,
                current_mode=feedback_mode,
            )

        except FeedbackError as exc:
            self.audit.append(
                "feedback_observation_denied",
                {
                    "reason": type(exc).__name__,
                    "generation": self.generation,
                },
            )
            raise

        # Zero-neutral cannot be exited by feedback.
        if self.mode == Mode.ZERO_NEUTRAL:
            self.audit.append(
                "feedback_zero_neutral_hold",
                {
                    "window_id": decision.window_id,
                    "reason": decision.reason.value,
                },
            )
            return decision

        if decision.recommended_mode == FeedbackMode.DEGRADED:
            self._feedback_degraded = True

        elif decision.recommended_mode == FeedbackMode.NORMAL:
            self._feedback_degraded = False

        else:
            # Defensive check: never allow an unexpected
            # recommendation to cause a state transition.
            self.audit.append(
                "feedback_decision_denied",
                {
                    "window_id": decision.window_id,
                    "reason": "unexpected_mode",
                },
            )
            raise ValidationError(
                "unexpected feedback recommendation"
            )

        self._synchronize_mode(
            reason=decision.reason.value
        )

        # Always record the accepted observation and decision.
        self.audit.append(
            "feedback_decision",
            {
                "window_id": decision.window_id,
                "virtual_load": decision.virtual_load,
                "real_load": decision.real_load,
                "virtual_overloaded": (
                    decision.virtual_overloaded
                ),
                "real_overloaded": (
                    decision.real_overloaded
                ),
                "stable_count": decision.stable_count,
                "reason": decision.reason.value,
                "recommended_mode": (
                    decision.recommended_mode.value
                ),
                "previous_axis_mode": previous_mode.value,
                "final_axis_mode": self.mode.value,
                "remaining_causes": list(
                    self.degradation_causes
                ),
                "generation": self.generation,
            },
        )

        if decision.reason == FeedbackReason.RECOVERY_ELIGIBLE:
            self.audit.append(
                "feedback_recovery_evaluated",
                {
                    "window_id": decision.window_id,
                    "accepted": (
                        self.mode == Mode.NORMAL
                    ),
                    "remaining_causes": list(
                        self.degradation_causes
                    ),
                },
            )

        return decision

    # --------------------------------------------------------
    # Emergency neutralization
    # --------------------------------------------------------

    def neutralize(self, reason: str) -> None:
        """Apply emergency neutralization with highest priority."""
        super().neutralize(reason)

        # The emergency boundary supersedes both
        # feedback and legacy degradation.
        self._feedback_degraded = False
        self._legacy_degraded = False

        self._feedback_controller.reset()

        self.audit.append(
            "v0.3_feedback_neutralized",
            {
                "generation": self.generation,
                "feedback_history_reset": True,
                "five_element_restrictions_preserved": True,
            },
        )

    # --------------------------------------------------------
    # Controlled recovery
    # --------------------------------------------------------

    def recover(
        self,
        *,
        safety_verified: bool,
        human_approved: bool,
    ) -> bool:
        """Preserve independent recovery requirements.

        Feedback cannot invoke recovery implicitly.

        The two Boolean conditions remain v0.1/v0.2
        simulation flags, not authenticated approvals.
        """
        result = super().recover(
            safety_verified=safety_verified,
            human_approved=human_approved,
        )

        if result:
            self._feedback_degraded = False
            self._legacy_degraded = False

            self._feedback_controller.reset()

            self._synchronize_mode(
                reason="independent_recovery"
            )

            self.audit.append(
                "v0.3_recovery_synchronized",
                {
                    "generation": self.generation,
                    "mode": self.mode.value,
                    "restrictions_preserved": True,
                    "old_authority_invalidated": True,
                },
            )

        return result


# ============================================================
# 6. Legacy simulation
# ============================================================

def main() -> None:
    """Preserve the v0.1 deterministic simulation output."""

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


# VRTA v0.4 addition. Insert this block before the final __main__ guard
# in the existing v0.3 axis.py. Keep all earlier classes and main().
from copy import deepcopy
from functools import wraps
from threading import RLock

from role_rotation import (
    DomainCredential,
    DomainRole,
    RoleRotation,
    RotationDenied,
    RotationFailed,
    RotationRequest,
)


def _v4_command(method):
    """Serialize public commands and reject callback reentry."""
    @wraps(method)
    def run(self, *args, **kwargs):
        with self._command_lock:
            if self._in_command:
                raise AuthorityError("axis command already in progress")
            self._in_command = True
            try:
                return method(self, *args, **kwargs)
            finally:
                self._in_command = False
    return run


class _RotationCoreV4(TransitionAxisV3):
    """Private v0.3 engine with v0.4 credential checks."""

    def _authorize(self, credential: DomainCredential, required: Role) -> None:
        if self.mode == Mode.ZERO_NEUTRAL or not self._rotation.accepts(
            credential, role=DomainRole(required.value), generation=self.generation
        ):
            raise AuthorityError("no current credential for the required role")

    def _authorize_element(self, token: ElementToken) -> Element:
        if (
            not isinstance(token, ElementToken)
            or type(token.token_id) is not str
            or self._element_tokens.get(token.token_id) is not token
        ):
            raise AuthorityError("no registered element credential")
        return super()._authorize_element(token)


class TransitionAxisV4:
    """Experimental serialized facade. Older axis classes are separate APIs."""

    def __init__(
        self,
        *,
        trusted_sources: frozenset[str],
        element_bindings: Mapping[str, Element],
        administrator: object,
        virtual_limit: int = 3,
        feedback_config: FeedbackConfig | None = None,
    ) -> None:
        self._command_lock = RLock()
        self._in_command = False
        self._administrator = administrator
        self._core = _RotationCoreV4(
            trusted_sources=trusted_sources,
            element_bindings=element_bindings,
            administrator=administrator,
            virtual_limit=virtual_limit,
            feedback_config=feedback_config,
        )
        self._rotation = RoleRotation(
            administrator=administrator,
            audit_ready=self._probe_rotation_audit,
            append_audit=self._append_confirmed,
        )
        self._core._rotation = self._rotation
        self._neutral_audit_pending = False
        self._rotation_reconciled = False

    @property
    def mode(self) -> Mode:
        with self._command_lock:
            return self._core.mode

    @property
    def generation(self) -> int:
        with self._command_lock:
            return self._core.generation

    @property
    def degradation_causes(self) -> tuple[str, ...]:
        with self._command_lock:
            return self._core.degradation_causes

    @property
    def audit_records(self) -> tuple[dict, ...]:
        with self._command_lock:
            return tuple(deepcopy(self._core.audit.records))

    @_v4_command
    def verify_audit(self) -> bool:
        return self._core.audit.verify()

    def _require_admin(self, administrator: object) -> None:
        if administrator is not self._administrator:
            raise AuthorityError("administrator capability required")

    def _require_active(self) -> None:
        if self._core.mode == Mode.ZERO_NEUTRAL:
            raise AuthorityError("axis is neutralized")

    def _append_confirmed(self, action: str, details: dict) -> None:
        log = self._core.audit
        index = len(log.records)
        log.append(action, details)
        if (
            len(log.records) != index + 1
            or log.records[index].get("action") != action
            or log.records[index].get("details") != details
            or log.verify() is not True
        ):
            raise OSError("audit append not confirmed")

    def _probe_rotation_audit(self) -> bool:
        if self._core.audit.verify() is not True:
            return False
        self._append_confirmed(
            "rotation_audit_ready", {"generation": self._core.generation}
        )
        return True

    def _best_effort_audit(self, action: str, details: dict) -> bool:
        try:
            self._append_confirmed(action, details)
        except Exception:
            return False
        return True

    @_v4_command
    def issue_token(
        self, token_id: str, role: Role, *, administrator: object = None
    ) -> DomainCredential:
        self._require_admin(administrator)
        self._require_active()
        if type(token_id) is not str or not isinstance(role, Role):
            raise ValidationError("invalid credential ID or domain role")
        if token_id in self._core._element_tokens:
            raise AuthorityError("credential ID already used")
        try:
            return self._rotation.assign(
                administrator=administrator, role=DomainRole(role.value),
                token_id=token_id, generation=self._core.generation,
            )
        except RotationDenied as exc:
            raise AuthorityError(str(exc)) from exc

    @_v4_command
    def issue_element_token(
        self, token_id: str, *, administrator: object = None
    ) -> ElementToken:
        self._require_admin(administrator)
        self._require_active()
        if type(token_id) is not str:
            raise ValidationError("invalid element credential ID")
        if token_id in self._rotation._used_ids:
            raise AuthorityError("credential ID already used")
        return self._core.issue_element_token(token_id)

    @_v4_command
    def rotate_role(
        self, request: RotationRequest, *, administrator: object
    ) -> DomainCredential:
        try:
            self._require_admin(administrator)
            self._require_active()
            if (
                type(request) is RotationRequest
                and type(request.new_id) is str
                and request.new_id in self._core._element_tokens
            ):
                raise AuthorityError("credential ID already used")
            return self._rotation.rotate(
                request, administrator=administrator,
                generation=self._core.generation,
            )
        except RotationFailed:
            self._enter_neutral("rotation_failed")
            raise
        except (RotationDenied, AuthorityError) as exc:
            self._best_effort_audit(
                "rotation_denied",
                {"generation": self._core.generation, "reason": str(exc)},
            )
            if isinstance(exc, RotationDenied):
                raise AuthorityError(str(exc)) from exc
            raise

    def _enter_neutral(self, reason: str) -> None:
        # Safety state changes precede audit and do not call the legacy
        # neutralize() path, which can stop partway through on an audit error.
        core = self._core
        core.mode = Mode.ZERO_NEUTRAL
        core.generation += 1
        core.virtual_load = 0
        core._accepted_events.clear()
        core._legacy_degraded = False
        core._feedback_degraded = False
        core._feedback_controller.reset()
        self._rotation_reconciled = False
        self._neutral_audit_pending = not self._best_effort_audit(
            "axis_neutralized", {"generation": core.generation, "reason": reason}
        )

    @_v4_command
    def neutralize(self, reason: str, *, administrator: object) -> None:
        self._require_admin(administrator)
        if type(reason) is not str or not reason.strip():
            raise ValidationError("a nonblank neutralization reason is required")
        self._enter_neutral(reason)

    @_v4_command
    def recover(
        self, *, safety_verified: bool, human_approved: bool,
        administrator: object = None,
    ) -> bool:
        self._require_admin(administrator)
        core = self._core
        if core.mode != Mode.ZERO_NEUTRAL:
            return False
        if safety_verified is not True or human_approved is not True:
            self._best_effort_audit(
                "recovery_denied", {"generation": core.generation}
            )
            return False

        failure = self._rotation.failure
        try:
            if core.audit.verify() is not True:
                return False
            missing_rotation = failure is not None and not failure.failure_logged
            if self._neutral_audit_pending or (
                missing_rotation and not self._rotation_reconciled
            ):
                self._append_confirmed(
                    "rotation_reconciled" if failure else "neutralization_reconciled",
                    {
                        "rotation_id": failure.rotation_id if failure else None,
                        "failed_generation": failure.generation if failure else None,
                        "generation": core.generation,
                        "outcome": "not_committed" if failure else "neutralized",
                    },
                )
                self._neutral_audit_pending = False
                self._rotation_reconciled = failure is not None
            self._append_confirmed(
                "axis_recovery_approved", {"generation": core.generation}
            )
        except Exception:
            return False

        if failure is not None:
            self._rotation.finish_axis_recovery(
                administrator=administrator, generation=core.generation
            )
        core._feedback_controller.reset()
        core.mode = Mode.NORMAL
        return True

    @_v4_command
    def receive_virtual(
        self, token: DomainCredential, event: dict[str, Any]
    ) -> str:
        return self._core.receive_virtual(token, event)

    @_v4_command
    def verify_evidence(
        self, evidence: Mapping[str, Any] | EvidenceRecord
    ) -> VerificationReceipt:
        return self._core.verify_evidence(evidence)

    def execute_real(self, token: object, operation: str, *, verified: bool) -> bool:
        raise AuthorityError("a registered evidence receipt is required")

    @_v4_command
    def execute_real_verified(
        self, token: DomainCredential, operation: str, *, receipt_id: str,
        evidence_id: str | None = None, event_id: str | None = None,
    ) -> bool:
        if type(operation) is not str:
            raise ValidationError("operation must be a string")
        return self._core.execute_real_verified(
            token, operation, receipt_id=receipt_id,
            evidence_id=evidence_id, event_id=event_id,
        )

    @_v4_command
    def request_restriction(
        self, token: ElementToken, request: Mapping[str, Any] | RestrictionRequest
    ) -> RestrictionDecision:
        return self._core.request_restriction(token, request)

    @_v4_command
    def release_restriction(
        self, *, administrator: object, action: RestrictionAction
    ) -> bool:
        return self._core.release_restriction(administrator=administrator, action=action)

    @_v4_command
    def restriction_active(self, action: RestrictionAction) -> bool:
        return self._core.restriction_active(action)

    @_v4_command
    def observe_load(
        self, observation: Mapping[str, Any] | LoadObservation
    ) -> FeedbackDecision:
        return self._core.observe_load(observation)

    @_v4_command
    def feedback_snapshot(self) -> dict[str, Any]:
        return self._core.feedback_snapshot()

    @_v4_command
    def reset_virtual_load(self, *, administrator: object) -> None:
        self._require_admin(administrator)
        self._core.reset_virtual_load()


if __name__ == "__main__":
    main()
