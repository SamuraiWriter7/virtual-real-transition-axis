"""Five-Element Authority Matrix for VRTA v0.2.

Python 3.11+.
Standard library only.

This module defines deterministic cross-element
restriction rules for the Virtual-Real Transition Axis.

It validates requests but does not authenticate callers,
modify privileges, or execute real-domain operations.

Final authorization and state changes belong to the
independent TransitionAxis controller.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class FiveElementError(Exception):
    """Base exception for five-element validation errors."""


class RestrictionValidationError(FiveElementError):
    """A restriction request is structurally invalid."""


class RestrictionDeniedError(FiveElementError):
    """A restriction relation or action is not permitted."""


class Element(str, Enum):
    """Functional authority roles."""

    WOOD = "wood"
    FIRE = "fire"
    EARTH = "earth"
    METAL = "metal"
    WATER = "water"


class RestrictionAction(str, Enum):
    """Permitted cross-element action types."""

    REQUEST_REVIEW = "request_review"
    FLAG_INCONSISTENCY = "flag_inconsistency"
    SUSPEND_ANALYSIS = "suspend_analysis"
    REQUEST_AUTHORITY_REVIEW = "request_authority_review"
    RESTRICT_INTAKE = "restrict_intake"


# Explicit allowlist.
#
# These relations are architecture-specific restrictions,
# not universal claims about classical five-element theory.
#
# A permitted relation authorizes only the corresponding
# request type. It does not authenticate the requester or
# automatically grant permission to mutate target state.

ALLOWED_RELATIONS: dict[
    tuple[Element, Element],
    RestrictionAction,
] = {
    (
        Element.WOOD,
        Element.EARTH,
    ): RestrictionAction.REQUEST_REVIEW,

    (
        Element.EARTH,
        Element.WATER,
    ): RestrictionAction.FLAG_INCONSISTENCY,

    (
        Element.WATER,
        Element.FIRE,
    ): RestrictionAction.SUSPEND_ANALYSIS,

    (
        Element.FIRE,
        Element.METAL,
    ): RestrictionAction.REQUEST_AUTHORITY_REVIEW,

    (
        Element.METAL,
        Element.WOOD,
    ): RestrictionAction.RESTRICT_INTAKE,
}


# Advisory actions record requests without directly
# changing target privileges.
ADVISORY_ACTIONS = frozenset(
    {
        RestrictionAction.REQUEST_REVIEW,
        RestrictionAction.FLAG_INCONSISTENCY,
        RestrictionAction.REQUEST_AUTHORITY_REVIEW,
    }
)


# Restrictive actions may activate a bounded prohibition
# only after the independent axis authorizes the request.
RESTRICTIVE_ACTIONS = frozenset(
    {
        RestrictionAction.SUSPEND_ANALYSIS,
        RestrictionAction.RESTRICT_INTAKE,
    }
)


def _required_string(value: Any, field: str) -> str:
    """Validate a non-empty string."""
    if not isinstance(value, str) or not value.strip():
        raise RestrictionValidationError(
            f"{field} must be a non-empty string"
        )

    return value


def _parse_element(value: Any, field: str) -> Element:
    """Parse a functional element name."""
    if isinstance(value, Element):
        return value

    if not isinstance(value, str):
        raise RestrictionValidationError(
            f"{field} must be a valid element"
        )

    try:
        return Element(value)
    except ValueError as exc:
        raise RestrictionValidationError(
            f"unknown element: {value}"
        ) from exc


def _parse_action(value: Any) -> RestrictionAction:
    """Parse a supported restriction action."""
    if isinstance(value, RestrictionAction):
        return value

    if not isinstance(value, str):
        raise RestrictionValidationError(
            "action must be a valid restriction action"
        )

    try:
        return RestrictionAction(value)
    except ValueError as exc:
        raise RestrictionValidationError(
            f"unknown restriction action: {value}"
        ) from exc


@dataclass(frozen=True)
class RestrictionRequest:
    """Immutable representation of a restriction request."""

    request_id: str
    source_element: Element
    target_element: Element
    action: RestrictionAction
    reason: str

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> RestrictionRequest:
        """Parse and validate a restriction request."""
        if not isinstance(value, Mapping):
            raise RestrictionValidationError(
                "restriction request must be an object"
            )

        required = {
            "request_id",
            "source_element",
            "target_element",
            "action",
            "reason",
        }

        missing = required - set(value)

        if missing:
            raise RestrictionValidationError(
                f"missing fields: {sorted(missing)}"
            )

        return cls(
            request_id=_required_string(
                value["request_id"],
                "request_id",
            ),
            source_element=_parse_element(
                value["source_element"],
                "source_element",
            ),
            target_element=_parse_element(
                value["target_element"],
                "target_element",
            ),
            action=_parse_action(
                value["action"]
            ),
            reason=_required_string(
                value["reason"],
                "reason",
            ),
        )

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-compatible representation."""
        return {
            "request_id": self.request_id,
            "source_element": self.source_element.value,
            "target_element": self.target_element.value,
            "action": self.action.value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RestrictionDecision:
    """Validated matrix decision without authority effects."""

    request_id: str
    source_element: Element
    target_element: Element
    action: RestrictionAction
    restrictive: bool
    permitted: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "source_element": self.source_element.value,
            "target_element": self.target_element.value,
            "action": self.action.value,
            "restrictive": self.restrictive,
            "permitted": self.permitted,
        }


class FiveElementMatrix:
    """Deterministic validation of five-element restrictions."""

    @staticmethod
    def allowed_action(
        source: Element,
        target: Element,
    ) -> RestrictionAction | None:
        """Return the sole permitted action for a relation."""
        return ALLOWED_RELATIONS.get((source, target))

    @staticmethod
    def validate(
        value: Mapping[str, Any] | RestrictionRequest,
    ) -> RestrictionDecision:
        """Validate a request against the explicit allowlist.

        No side effects are performed.
        """
        if isinstance(value, RestrictionRequest):
            # Reparse to enforce expected field types.
            request = RestrictionRequest.from_mapping(
                value.to_dict()
            )
        else:
            request = RestrictionRequest.from_mapping(value)

        expected_action = ALLOWED_RELATIONS.get(
            (
                request.source_element,
                request.target_element,
            )
        )

        if expected_action is None:
            raise RestrictionDeniedError(
                "source-target relation is not permitted"
            )

        if request.action != expected_action:
            raise RestrictionDeniedError(
                "action is not permitted for this relation"
            )

        return RestrictionDecision(
            request_id=request.request_id,
            source_element=request.source_element,
            target_element=request.target_element,
            action=request.action,
            restrictive=(
                request.action in RESTRICTIVE_ACTIONS
            ),
            permitted=True,
        )

    @staticmethod
    def is_advisory(action: RestrictionAction) -> bool:
        return action in ADVISORY_ACTIONS

    @staticmethod
    def is_restrictive(action: RestrictionAction) -> bool:
        return action in RESTRICTIVE_ACTIONS

    @staticmethod
    def relations() -> tuple[
        tuple[Element, Element, RestrictionAction],
        ...
    ]:
        """Return an immutable snapshot of allowed relations."""
        return tuple(
            (
                source,
                target,
                action,
            )
            for (source, target), action
            in ALLOWED_RELATIONS.items()
        )


def build_restriction_request(
    *,
    request_id: str,
    source_element: Element | str,
    target_element: Element | str,
    action: RestrictionAction | str,
    reason: str,
) -> dict[str, str]:
    """Create a normalized request for tests and examples.

    This helper does not authorize the requester.
    """
    request = RestrictionRequest.from_mapping(
        {
            "request_id": request_id,
            "source_element": source_element,
            "target_element": target_element,
            "action": action,
            "reason": reason,
        }
    )

    return request.to_dict()
