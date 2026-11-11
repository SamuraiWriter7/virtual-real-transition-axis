"""Independent Evidence Verification for VRTA v0.2.

Python 3.11+.
Standard library only.

This module provides deterministic evidence validation and
verification receipt creation.

It does not authenticate external source identities, provide
cryptographic signatures, or authorize real-domain operations.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from uuid import uuid4


class EvidenceError(Exception):
    """Base exception for evidence verification failures."""


class EvidenceValidationError(EvidenceError):
    """Evidence structure or content is invalid."""


class UntrustedSourceError(EvidenceError):
    """Evidence source is not registered as trusted."""


class EvidenceConflictError(EvidenceError):
    """An evidence identifier conflicts with an existing record."""


class EvidenceBindingError(EvidenceError):
    """Evidence does not match its registered event."""


class EvidenceVerificationError(EvidenceError):
    """The evidence verification procedure failed."""


def canonical_json(value: Any) -> bytes:
    """Serialize JSON-compatible data deterministically.

    This implements the VRTA v0.2 reference encoding.
    It is not a universal cross-language canonical JSON standard.
    """
    try:
        serialized = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise EvidenceValidationError(
            "payload must be valid JSON-compatible data"
        ) from exc

    return serialized.encode("utf-8")


def calculate_payload_digest(payload: Any) -> str:
    """Return lowercase SHA-256 of canonical JSON payload."""
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceValidationError(
            f"{field} must be a non-empty string"
        )
    return value


def _validate_digest(value: Any) -> str:
    if not isinstance(value, str):
        raise EvidenceValidationError(
            "payload_digest must be a string"
        )

    if len(value) != 64 or any(
        character not in "0123456789abcdef"
        for character in value
    ):
        raise EvidenceValidationError(
            "payload_digest must be lowercase SHA-256 hex"
        )

    return value


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    event_id: str
    source_id: str
    payload: Any
    payload_digest: str

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> EvidenceRecord:
        """Parse a strict evidence record."""
        if not isinstance(value, Mapping):
            raise EvidenceValidationError(
                "evidence must be an object"
            )

        required = {
            "evidence_id",
            "event_id",
            "source_id",
            "payload",
            "payload_digest",
        }

        missing = required - set(value)
        if missing:
            raise EvidenceValidationError(
                f"missing fields: {sorted(missing)}"
            )

        return cls(
            evidence_id=_nonempty_string(
                value["evidence_id"], "evidence_id"
            ),
            event_id=_nonempty_string(
                value["event_id"], "event_id"
            ),
            source_id=_nonempty_string(
                value["source_id"], "source_id"
            ),
            payload=value["payload"],
            payload_digest=_validate_digest(
                value["payload_digest"]
            ),
        )


@dataclass(frozen=True)
class VerificationReceipt:
    receipt_id: str
    evidence_id: str
    event_id: str
    payload_digest: str
    verifier_id: str
    generation: int
    status: str = "verified"

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "evidence_id": self.evidence_id,
            "event_id": self.event_id,
            "payload_digest": self.payload_digest,
            "verifier_id": self.verifier_id,
            "generation": self.generation,
            "status": self.status,
        }


class EvidenceVerifier:
    """Deterministic verifier for locally registered evidence.

    The controller supplies read-only callbacks describing its
    authoritative event and evidence state.

    The verifier owns no real-operation permissions.
    """

    def __init__(
        self,
        *,
        verifier_id: str,
        trusted_sources: frozenset[str],
        event_lookup: Callable[[str], bool],
        evidence_lookup: Callable[
            [str], EvidenceRecord | None
        ],
    ) -> None:
        self.verifier_id = _nonempty_string(
            verifier_id, "verifier_id"
        )

        if not isinstance(trusted_sources, frozenset):
            raise EvidenceValidationError(
                "trusted_sources must be a frozenset"
            )

        for source in trusted_sources:
            _nonempty_string(source, "trusted source")

        if not callable(event_lookup):
            raise EvidenceValidationError(
                "event_lookup must be callable"
            )

        if not callable(evidence_lookup):
            raise EvidenceValidationError(
                "evidence_lookup must be callable"
            )

        self._trusted_sources = trusted_sources
        self._event_lookup = event_lookup
        self._evidence_lookup = evidence_lookup

    @property
    def trusted_sources(self) -> frozenset[str]:
        """Expose an immutable snapshot of trusted source IDs."""
        return self._trusted_sources

    def verify(
        self,
        value: Mapping[str, Any] | EvidenceRecord,
        *,
        generation: int,
    ) -> tuple[EvidenceRecord, VerificationReceipt]:
        """Validate evidence and return a local verification receipt.

        Receipt registration and final authorization are performed
        by the independent axis, not by this module.
        """
        if not isinstance(generation, int) or isinstance(
            generation, bool
        ) or generation < 0:
            raise EvidenceValidationError(
                "generation must be a non-negative integer"
            )

        if isinstance(value, EvidenceRecord):
            # Revalidate rather than trusting an existing instance.
            record = EvidenceRecord.from_mapping(
                {
                    "evidence_id": value.evidence_id,
                    "event_id": value.event_id,
                    "source_id": value.source_id,
                    "payload": value.payload,
                    "payload_digest": value.payload_digest,
                }
            )
        else:
            record = EvidenceRecord.from_mapping(value)

        if record.source_id not in self._trusted_sources:
            raise UntrustedSourceError(
                "evidence source is not registered"
            )

        calculated_digest = calculate_payload_digest(
            record.payload
        )

        if not hmac.compare_digest(
            calculated_digest,
            record.payload_digest,
        ):
            raise EvidenceValidationError(
                "payload digest mismatch"
            )

        try:
            event_accepted = self._event_lookup(
                record.event_id
            )
        except Exception as exc:
            raise EvidenceVerificationError(
                "event lookup failed"
            ) from exc

        if event_accepted is not True:
            raise EvidenceBindingError(
                "event is not registered as accepted"
            )

        try:
            existing = self._evidence_lookup(
                record.evidence_id
            )
        except Exception as exc:
            raise EvidenceVerificationError(
                "evidence lookup failed"
            ) from exc

        if existing is not None:
            raise EvidenceConflictError(
                "evidence_id has already been registered"
            )

        receipt = VerificationReceipt(
            receipt_id=f"receipt-{uuid4().hex}",
            evidence_id=record.evidence_id,
            event_id=record.event_id,
            payload_digest=record.payload_digest,
            verifier_id=self.verifier_id,
            generation=generation,
        )

        return record, receipt


def build_evidence(
    *,
    evidence_id: str,
    event_id: str,
    source_id: str,
    payload: Any,
) -> dict[str, Any]:
    """Build evidence with a matching digest for local tests.

    This helper does not verify source authenticity.
    """
    return {
        "evidence_id": _nonempty_string(
            evidence_id, "evidence_id"
        ),
        "event_id": _nonempty_string(
            event_id, "event_id"
        ),
        "source_id": _nonempty_string(
            source_id, "source_id"
        ),
        "payload": payload,
        "payload_digest": calculate_payload_digest(
            payload
        ),
    }
