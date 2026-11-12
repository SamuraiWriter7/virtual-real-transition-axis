"""Seesaw Negative Feedback Controller for VRTA v0.3.

Python 3.11+.
Standard library only.

Provides:
- Independent virtual and real load evaluation
- Sliding observation windows
- Hysteresis
- Consecutive stability confirmation
- Deterministic feedback recommendations
- Zero-neutral priority
- Invalid observation rejection

The controller does not:
- Modify the independent axis
- Grant or revoke authority
- Issue evidence receipts
- Release five-element restrictions
- Recover from zero-neutral mode

This is an experimental behavioral reference model.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


# ============================================================
# 1. Exceptions
# ============================================================

class FeedbackError(Exception):
    """Base exception for feedback failures."""


class FeedbackConfigurationError(FeedbackError):
    """Feedback configuration is invalid."""


class FeedbackObservationError(FeedbackError):
    """A load observation is invalid."""


class FeedbackStateError(FeedbackError):
    """An operating mode or state is invalid."""


# ============================================================
# 2. Operating modes and reason codes
# ============================================================

class FeedbackMode(str, Enum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    ZERO_NEUTRAL = "zero_neutral"


class FeedbackReason(str, Enum):
    NORMAL_STABLE = "normal_stable"
    VIRTUAL_OVERLOAD = "virtual_overload"
    REAL_OVERLOAD = "real_overload"
    SIMULTANEOUS_OVERLOAD = "simultaneous_overload"
    HYSTERESIS_HOLD = "hysteresis_hold"
    RECOVERY_PENDING = "recovery_pending"
    RECOVERY_ELIGIBLE = "recovery_eligible"
    ZERO_NEUTRAL_HOLD = "zero_neutral_hold"


# ============================================================
# 3. Validation helpers
# ============================================================

def _finite_number(
    value: Any,
    field: str,
) -> float:
    """Accept finite numeric values but reject Boolean values."""
    if isinstance(value, bool):
        raise FeedbackConfigurationError(
            f"{field} must not be Boolean"
        )

    if not isinstance(value, (int, float)):
        raise FeedbackConfigurationError(
            f"{field} must be numeric"
        )

    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise FeedbackConfigurationError(
            f"{field} cannot be converted to a finite float"
        ) from exc

    if not math.isfinite(result):
        raise FeedbackConfigurationError(
            f"{field} must be finite"
        )

    return result


def _positive_integer(
    value: Any,
    field: str,
    *,
    minimum: int = 1,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
    ):
        raise FeedbackConfigurationError(
            f"{field} must be an integer >= {minimum}"
        )

    return value


def _normalized_load(
    value: Any,
    field: str,
) -> float:
    """Validate a normalized load in the range [0.0, 1.0]."""
    try:
        result = _finite_number(value, field)
    except FeedbackConfigurationError as exc:
        raise FeedbackObservationError(
            str(exc)
        ) from exc

    if not 0.0 <= result <= 1.0:
        raise FeedbackObservationError(
            f"{field} must be between 0.0 and 1.0"
        )

    return result


def _parse_mode(
    value: FeedbackMode | str,
) -> FeedbackMode:
    if isinstance(value, FeedbackMode):
        return value

    if not isinstance(value, str):
        raise FeedbackStateError(
            "current_mode must be a valid operating mode"
        )

    try:
        return FeedbackMode(value)
    except ValueError as exc:
        raise FeedbackStateError(
            f"unknown operating mode: {value}"
        ) from exc


# ============================================================
# 4. Feedback configuration
# ============================================================

@dataclass(frozen=True)
class FeedbackConfig:
    """Immutable configuration for deterministic feedback."""

    degrade_threshold: float = 0.80
    recover_threshold: float = 0.40
    stable_windows_required: int = 3
    window_size: int = 3

    def __post_init__(self) -> None:
        degrade = _finite_number(
            self.degrade_threshold,
            "degrade_threshold",
        )

        recover = _finite_number(
            self.recover_threshold,
            "recover_threshold",
        )

        if not 0.0 <= recover < degrade <= 1.0:
            raise FeedbackConfigurationError(
                "thresholds must satisfy "
                "0.0 <= recover < degrade <= 1.0"
            )

        stable = _positive_integer(
            self.stable_windows_required,
            "stable_windows_required",
            minimum=2,
        )

        capacity = _positive_integer(
            self.window_size,
            "window_size",
        )

        object.__setattr__(
            self,
            "degrade_threshold",
            degrade,
        )

        object.__setattr__(
            self,
            "recover_threshold",
            recover,
        )

        object.__setattr__(
            self,
            "stable_windows_required",
            stable,
        )

        object.__setattr__(
            self,
            "window_size",
            capacity,
        )


# ============================================================
# 5. Load observation
# ============================================================

@dataclass(frozen=True)
class LoadObservation:
    """One ordered virtual-real load observation."""

    window_id: int
    virtual_load: float
    real_load: float

    def __post_init__(self) -> None:
        if (
            isinstance(self.window_id, bool)
            or not isinstance(self.window_id, int)
            or self.window_id < 0
        ):
            raise FeedbackObservationError(
                "window_id must be a non-negative integer"
            )

        virtual = _normalized_load(
            self.virtual_load,
            "virtual_load",
        )

        real = _normalized_load(
            self.real_load,
            "real_load",
        )

        object.__setattr__(
            self,
            "virtual_load",
            virtual,
        )

        object.__setattr__(
            self,
            "real_load",
            real,
        )

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
    ) -> LoadObservation:
        """Parse a load observation from an object."""
        if not isinstance(value, Mapping):
            raise FeedbackObservationError(
                "observation must be an object"
            )

        required = {
            "window_id",
            "virtual_load",
            "real_load",
        }

        missing = required - set(value)

        if missing:
            raise FeedbackObservationError(
                f"missing fields: {sorted(missing)}"
            )

        return cls(
            window_id=value["window_id"],
            virtual_load=value["virtual_load"],
            real_load=value["real_load"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "virtual_load": self.virtual_load,
            "real_load": self.real_load,
        }


# ============================================================
# 6. Feedback decision
# ============================================================

@dataclass(frozen=True)
class FeedbackDecision:
    """Immutable feedback recommendation.

    A decision is not an authorization token.

    The independent axis must validate the decision
    before applying any state transition.
    """

    window_id: int
    virtual_load: float
    real_load: float
    virtual_overloaded: bool
    real_overloaded: bool
    stable_count: int
    current_mode: FeedbackMode
    recommended_mode: FeedbackMode
    reason: FeedbackReason

    @property
    def transition_recommended(self) -> bool:
        return self.current_mode != self.recommended_mode

    @property
    def overloaded(self) -> bool:
        return (
            self.virtual_overloaded
            or self.real_overloaded
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_id": self.window_id,
            "virtual_load": self.virtual_load,
            "real_load": self.real_load,
            "virtual_overloaded": self.virtual_overloaded,
            "real_overloaded": self.real_overloaded,
            "stable_count": self.stable_count,
            "current_mode": self.current_mode.value,
            "recommended_mode": self.recommended_mode.value,
            "reason": self.reason.value,
            "transition_recommended": (
                self.transition_recommended
            ),
        }


# ============================================================
# 7. Independent feedback controller
# ============================================================

class FeedbackController:
    """Deterministic negative feedback recommendation engine.

    This controller owns observation history and stability
    counters, but never modifies the authoritative axis.

    The reference implementation assumes sequential calls.
    It is not thread-safe or suitable for untrusted callers.
    """

    def __init__(
        self,
        config: FeedbackConfig | None = None,
    ) -> None:
        if config is None:
            config = FeedbackConfig()

        if not isinstance(config, FeedbackConfig):
            raise FeedbackConfigurationError(
                "config must be a FeedbackConfig"
            )

        self.config = config

        self._history: deque[LoadObservation] = deque(
            maxlen=config.window_size
        )

        self._last_window_id: int | None = None
        self._stable_count = 0
        self._last_decision: FeedbackDecision | None = None

    # --------------------------------------------------------
    # Read-only diagnostics
    # --------------------------------------------------------

    @property
    def history(self) -> tuple[LoadObservation, ...]:
        """Return an immutable snapshot of retained windows."""
        return tuple(self._history)

    @property
    def stable_count(self) -> int:
        return self._stable_count

    @property
    def last_window_id(self) -> int | None:
        return self._last_window_id

    @property
    def last_decision(self) -> FeedbackDecision | None:
        return self._last_decision

    # --------------------------------------------------------
    # Observation validation
    # --------------------------------------------------------

    def _parse_observation(
        self,
        value: Mapping[str, Any] | LoadObservation,
    ) -> LoadObservation:
        if isinstance(value, LoadObservation):
            # Reconstruct to enforce validation.
            observation = LoadObservation.from_mapping(
                value.to_dict()
            )
        else:
            observation = LoadObservation.from_mapping(
                value
            )

        if self._last_window_id is not None:
            if observation.window_id <= self._last_window_id:
                raise FeedbackObservationError(
                    "window_id must increase strictly"
                )

        return observation

    # --------------------------------------------------------
    # Load evaluation
    # --------------------------------------------------------

    def _evaluate_overload(
        self,
        observation: LoadObservation,
    ) -> tuple[bool, bool]:
        virtual_overloaded = (
            observation.virtual_load
            >= self.config.degrade_threshold
        )

        real_overloaded = (
            observation.real_load
            >= self.config.degrade_threshold
        )

        return (
            virtual_overloaded,
            real_overloaded,
        )

    def _is_stable(
        self,
        observation: LoadObservation,
    ) -> bool:
        return (
            observation.virtual_load
            <= self.config.recover_threshold
            and observation.real_load
            <= self.config.recover_threshold
        )

    # --------------------------------------------------------
    # Decision evaluation
    # --------------------------------------------------------

    def evaluate(
        self,
        observation: (
            Mapping[str, Any] | LoadObservation
        ),
        *,
        current_mode: FeedbackMode | str,
    ) -> FeedbackDecision:
        """Evaluate one observation.

        Invalid inputs do not modify controller state.

        The returned recommendation is advisory.
        The independent axis owns final mode transitions.
        """

        # Validate all external inputs before changing state.
        parsed = self._parse_observation(
            observation
        )

        mode = _parse_mode(
            current_mode
        )

        virtual_overloaded, real_overloaded = (
            self._evaluate_overload(parsed)
        )

        overloaded = (
            virtual_overloaded
            or real_overloaded
        )

        stable = self._is_stable(
            parsed
        )

        # Calculate the next counter without committing it.
        next_stable_count = self._stable_count

        recommended = mode
        reason = FeedbackReason.HYSTERESIS_HOLD

        # ----------------------------------------------------
        # Zero-neutral is never exited through feedback.
        # ----------------------------------------------------

        if mode == FeedbackMode.ZERO_NEUTRAL:
            next_stable_count = 0

            recommended = FeedbackMode.ZERO_NEUTRAL
            reason = FeedbackReason.ZERO_NEUTRAL_HOLD

        # ----------------------------------------------------
        # Overload has priority over recovery progress.
        # ----------------------------------------------------

        elif overloaded:
            next_stable_count = 0

            recommended = FeedbackMode.DEGRADED

            if virtual_overloaded and real_overloaded:
                reason = (
                    FeedbackReason.SIMULTANEOUS_OVERLOAD
                )
            elif virtual_overloaded:
                reason = FeedbackReason.VIRTUAL_OVERLOAD
            else:
                reason = FeedbackReason.REAL_OVERLOAD

        # ----------------------------------------------------
        # Normal mode is retained without overload.
        # ----------------------------------------------------

        elif mode == FeedbackMode.NORMAL:
            next_stable_count = 0

            recommended = FeedbackMode.NORMAL
            reason = FeedbackReason.NORMAL_STABLE

        # ----------------------------------------------------
        # Degraded mode requires consecutive stable windows.
        # ----------------------------------------------------

        elif mode == FeedbackMode.DEGRADED:

            if stable:
                next_stable_count += 1

                if (
                    next_stable_count
                    >= self.config.stable_windows_required
                ):
                    recommended = FeedbackMode.NORMAL
                    reason = FeedbackReason.RECOVERY_ELIGIBLE

                    # A completed recovery cycle starts
                    # a new stability sequence.
                    next_stable_count = 0

                else:
                    recommended = FeedbackMode.DEGRADED
                    reason = FeedbackReason.RECOVERY_PENDING

            else:
                next_stable_count = 0
                recommended = FeedbackMode.DEGRADED
                reason = FeedbackReason.HYSTERESIS_HOLD

        # ----------------------------------------------------
        # Build immutable decision before committing history.
        # ----------------------------------------------------

        decision = FeedbackDecision(
            window_id=parsed.window_id,
            virtual_load=parsed.virtual_load,
            real_load=parsed.real_load,
            virtual_overloaded=virtual_overloaded,
            real_overloaded=real_overloaded,
            stable_count=next_stable_count,
            current_mode=mode,
            recommended_mode=recommended,
            reason=reason,
        )

        # Commit the accepted observation.
        self._history.append(parsed)
        self._last_window_id = parsed.window_id
        self._stable_count = next_stable_count
        self._last_decision = decision

        return decision

    # --------------------------------------------------------
    # Diagnostic snapshot
    # --------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return controller diagnostics without axis mutation."""
        return {
            "last_window_id": self._last_window_id,
            "stable_count": self._stable_count,
            "history_size": len(self._history),
            "window_capacity": self.config.window_size,
            "last_decision": (
                self._last_decision.to_dict()
                if self._last_decision is not None
                else None
            ),
        }

    # --------------------------------------------------------
    # Local reset
    # --------------------------------------------------------

    def reset(self) -> None:
        """Clear feedback observations and stability progress.

        This method must not be exposed to untrusted callers
        as an authorization or axis-recovery operation.

        Resetting feedback does not modify the axis mode,
        invalidate tokens, or release restrictions.
        """
        self._history.clear()
        self._last_window_id = None
        self._stable_count = 0
        self._last_decision = None


# ============================================================
# 8. Deterministic local demonstration
# ============================================================

def main() -> None:
    """Demonstrate degradation, hysteresis, and recovery."""

    controller = FeedbackController()

    mode = FeedbackMode.NORMAL

    samples = [
        (1, 0.30, 0.35),
        (2, 0.90, 0.30),
        (3, 0.60, 0.50),
        (4, 0.30, 0.35),
        (5, 0.28, 0.31),
        (6, 0.25, 0.29),
    ]

    print("VRTA v0.3 Feedback Simulation")
    print("=" * 35)

    for window_id, virtual_load, real_load in samples:
        observation = LoadObservation(
            window_id=window_id,
            virtual_load=virtual_load,
            real_load=real_load,
        )

        decision = controller.evaluate(
            observation,
            current_mode=mode,
        )

        print(
            f"window={window_id} "
            f"virtual={virtual_load:.2f} "
            f"real={real_load:.2f} "
            f"recommend={decision.recommended_mode.value} "
            f"reason={decision.reason.value}"
        )

        # Demonstration-only simulated axis acceptance.
        # In the integrated implementation, axis.py must
        # validate and apply the decision instead.
        mode = decision.recommended_mode

    print("=" * 35)
    print(f"final simulated mode: {mode.value}")
    print(f"retained windows: {len(controller.history)}")


if __name__ == "__main__":
    main()
