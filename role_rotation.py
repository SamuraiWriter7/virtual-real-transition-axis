"""Internal domain credential handover for VRTA v0.4 (Python 3.11+).

The axis owns mode, generation, and recovery. It must serialize all commands,
supply its own generation, and neutralize on RotationFailed before returning.
This module is not a public role API or a process isolation boundary.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class DomainRole(str, Enum):
    VIRTUAL = "virtual"
    REAL = "real"


class RotationDenied(Exception):
    """The request was rejected before cutover."""


class RotationFailed(Exception):
    """Cutover failed and all local domain bindings are blocked."""


@dataclass(frozen=True, slots=True, eq=False)
class DomainCredential:
    token_id: str
    role: DomainRole
    generation: int


@dataclass(frozen=True, slots=True)
class RotationRequest:
    rotation_id: str
    role: DomainRole
    expected_current_id: str
    new_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class FailedRotation:
    rotation_id: str
    generation: int
    failure_logged: bool


class RoleRotation:
    """Manage one local credential per role under the axis's command scope.

    Audit calls must return normally only on confirmed writes. They and the
    test hook must not dispatch axis commands or mutate axis state.
    """

    def __init__(
        self,
        *,
        administrator: object,
        audit_ready: Callable[[], bool],
        append_audit: Callable[[str, dict], None],
    ) -> None:
        if administrator is None:
            raise ValueError("administrator capability is required")
        self._administrator = administrator
        self._audit_ready = audit_ready
        self._append_audit = append_audit
        self._current: dict[DomainRole, DomainCredential] = {}
        self._used_ids: set[str] = set()
        self._used_rotations: set[str] = set()
        self._busy = False
        self._gate: DomainRole | None = None
        self._failure: FailedRotation | None = None

    @property
    def failure(self) -> FailedRotation | None:
        return self._failure

    def _admin(self, administrator: object) -> None:
        if administrator is not self._administrator or self._busy:
            raise RotationDenied("administrator required and axis must be idle")

    @staticmethod
    def _validate_text(*values: str) -> None:
        if any(type(value) is not str or not value.strip() for value in values):
            raise RotationDenied("IDs and reason must be nonblank strings")

    def accepts(
        self, credential: object, *, role: DomainRole, generation: int
    ) -> bool:
        """Check identity and current binding. The axis still checks its mode."""
        current = self._current.get(role)
        return (
            self._failure is None
            and self._gate != role
            and current is not None
            and credential is current
            and current.generation == generation
        )

    def assign(
        self, *, administrator: object, role: DomainRole, token_id: str,
        generation: int,
    ) -> DomainCredential:
        """Fill a vacancy. The axis must reject assignment while neutral."""
        self._admin(administrator)
        self._validate_text(token_id)
        if self._failure is not None or not isinstance(role, DomainRole):
            raise RotationDenied("assignment unavailable")
        current = self._current.get(role)
        if (current is not None and current.generation == generation
                or token_id in self._used_ids):
            raise RotationDenied("role occupied or credential ID already used")
        credential = DomainCredential(token_id, role, generation)
        self._used_ids.add(token_id)
        self._current[role] = credential
        return credential

    def rotate(
        self, request: RotationRequest, *, administrator: object,
        generation: int,
    ) -> DomainCredential:
        """Run one handover. The axis must reject rotation while neutral."""
        self._admin(administrator)
        if self._failure is not None or type(request) is not RotationRequest:
            raise RotationDenied("rotation unavailable")
        self._validate_text(
            request.rotation_id, request.expected_current_id,
            request.new_id, request.reason,
        )
        role = request.role
        if not isinstance(role, DomainRole):
            raise RotationDenied("invalid domain role")
        old = self._current.get(role)
        if (
            old is None
            or old.generation != generation
            or old.token_id != request.expected_current_id
            or request.new_id in self._used_ids
            or request.rotation_id in self._used_rotations
        ):
            raise RotationDenied("current binding mismatch or ID already used")

        details = {
            "rotation_id": request.rotation_id, "role": role.value,
            "old_id": old.token_id, "new_id": request.new_id,
            "generation": generation,
        }
        self._busy = True
        try:
            try:
                ready = self._audit_ready()
            except Exception as exc:
                raise RotationDenied("audit unavailable") from exc
            if ready is not True:
                raise RotationDenied("audit unavailable")

            self._gate = role
            try:
                self._used_rotations.add(request.rotation_id)
                self._used_ids.add(request.new_id)
                self._append_audit(
                    "rotation_started",
                    {**details, "phase": "cutover", "outcome": "started"},
                )
                del self._current[role]
                self._after_revocation()
                new = DomainCredential(request.new_id, role, generation)
                self._append_audit(
                    "rotation_completion",
                    {**details, "phase": "completion", "outcome": "commit_ready"},
                )
                self._current[role] = new
                return new
            except Exception as exc:
                self._current.clear()
                self._failure = FailedRotation(request.rotation_id, generation, False)
                try:
                    self._append_audit(
                        "rotation_failed",
                        {**details, "phase": "cutover", "outcome": type(exc).__name__},
                    )
                except Exception:
                    pass  # Axis must reconcile the missing confirmation at recovery.
                else:
                    self._failure = FailedRotation(request.rotation_id, generation, True)
                raise RotationFailed("handover did not commit") from exc
            finally:
                self._gate = None
        finally:
            self._busy = False

    def finish_axis_recovery(
        self, *, administrator: object, generation: int
    ) -> None:
        """Reset the local latch only after the axis confirms audited recovery."""
        self._admin(administrator)
        if self._failure is None or generation <= self._failure.generation:
            raise RotationDenied("failed handover and newer generation required")
        self._failure = None

    def _after_revocation(self) -> None:
        """Private no-op checkpoint for deterministic test fixtures."""
