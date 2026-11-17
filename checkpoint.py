"""Local checkpoint storage for VRTA v0.5.

Python 3.11+, standard library only. One trusted writer on a local filesystem.
The axis owns authorization, auditing, serialization, and neutral mode.
This module does not provide power-loss durability or tamper resistance.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

SCHEMA_VERSION = 1
ROLES = frozenset({"virtual", "real"})
RESTRICTIONS = frozenset({"restrict_intake", "suspend_analysis"})


class CheckpointError(Exception):
    """Base error for checkpoint operations."""


class CheckpointMissing(CheckpointError):
    """The configured checkpoint is missing."""


class CheckpointInvalid(CheckpointError):
    """The record is malformed or fails its integrity checks."""


class CheckpointIncompatible(CheckpointError):
    """The schema version or store identity does not match."""


class CheckpointUnavailable(CheckpointError):
    """The checkpoint could not be read."""


class CheckpointConflict(CheckpointError):
    """The confirmed record differs from the expected state."""


class CheckpointWriteError(CheckpointError):
    """The intended write could not be confirmed."""


def _nonblank(value: object) -> bool:
    return type(value) is str and bool(value.strip())


@dataclass(frozen=True, slots=True)
class PendingOperation:
    operation_id: str
    kind: str
    target: str

    def __post_init__(self) -> None:
        if not all(_nonblank(v) for v in (self.operation_id, self.kind, self.target)):
            raise CheckpointInvalid("operation fields must be nonblank strings")
        if self.kind == "rotate_role":
            allowed = ROLES
        elif self.kind in ("activate_restriction", "release_restriction"):
            allowed = RESTRICTIONS
        else:
            raise CheckpointInvalid("unknown operation kind")
        if self.target not in allowed:
            raise CheckpointInvalid("invalid operation target")


@dataclass(frozen=True, slots=True)
class Checkpoint:
    store_id: str
    revision: int
    restrictions: frozenset[str]
    pending: PendingOperation | None = None
    reconciliation_ref: str | None = None

    def __post_init__(self) -> None:
        if not _nonblank(self.store_id):
            raise CheckpointInvalid("store identity must be a nonblank string")
        if type(self.revision) is not int or self.revision < 0:
            raise CheckpointInvalid("revision must be a non-negative integer")
        if (
            type(self.restrictions) is not frozenset
            or any(type(value) is not str for value in self.restrictions)
            or not self.restrictions <= RESTRICTIONS
        ):
            raise CheckpointInvalid("invalid restriction set")
        if self.reconciliation_ref is not None and not _nonblank(self.reconciliation_ref):
            raise CheckpointInvalid("invalid reconciliation reference")
        if self.pending is not None:
            if type(self.pending) is not PendingOperation:
                raise CheckpointInvalid("invalid pending operation")
            if (
                self.pending.kind == "release_restriction"
                and self.pending.target not in self.restrictions
            ):
                raise CheckpointInvalid("pending release targets an inactive restriction")

    @property
    def phase(self) -> str:
        return "pending" if self.pending is not None else "clean"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CheckpointInvalid("duplicate JSON field")
        result[key] = value
    return result


def _require_keys(value: Any, keys: set[str]) -> None:
    if type(value) is not dict or set(value) != keys:
        raise CheckpointInvalid("unexpected checkpoint fields")


class CheckpointStore:
    """Read and replace checkpoints under the caller's single-writer contract."""

    def __init__(self, path: str | Path, *, store_id: str) -> None:
        if not _nonblank(store_id):
            raise CheckpointInvalid("store identity must be a nonblank string")
        self.path = Path(path)
        self.store_id = store_id

    def load(self) -> Checkpoint:
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError as exc:
            raise CheckpointMissing("checkpoint not found") from exc
        except OSError as exc:
            raise CheckpointUnavailable("checkpoint could not be read") from exc

        try:
            envelope = json.loads(raw, object_pairs_hook=_unique_keys)
            _require_keys(envelope, {"body", "sha256"})
            body = envelope["body"]
            _require_keys(body, {
                "schema_version", "store_id", "revision", "restrictions",
                "phase", "pending", "reconciliation_ref",
            })
            if envelope["sha256"] != hashlib.sha256(_json_bytes(body)).hexdigest():
                raise CheckpointInvalid("checkpoint checksum mismatch")
            if (
                type(body["schema_version"]) is not int
                or body["schema_version"] != SCHEMA_VERSION
            ):
                raise CheckpointIncompatible("unsupported checkpoint version")
            if body["store_id"] != self.store_id:
                raise CheckpointIncompatible("checkpoint belongs to another store")

            items = body["restrictions"]
            if type(items) is not list or any(type(item) is not str for item in items):
                raise CheckpointInvalid("restrictions must be a list of strings")
            restrictions = frozenset(items)
            if len(items) != len(restrictions):
                raise CheckpointInvalid("duplicate restriction")

            operation = body["pending"]
            if operation is not None:
                _require_keys(operation, {"operation_id", "kind", "target"})
                operation = PendingOperation(**operation)
            record = Checkpoint(
                self.store_id, body["revision"], restrictions,
                operation, body["reconciliation_ref"],
            )
            if record.phase != body["phase"]:
                raise CheckpointInvalid("phase does not match the pending operation")
            return record
        except (ValueError, RecursionError) as exc:
            raise CheckpointInvalid("checkpoint could not be decoded") from exc

    def _publish(self, record: Checkpoint, *, create_only: bool = False) -> Checkpoint:
        pending = record.pending
        body = {
            "schema_version": SCHEMA_VERSION,
            "store_id": record.store_id,
            "revision": record.revision,
            "restrictions": sorted(record.restrictions),
            "phase": record.phase,
            "pending": None if pending is None else {
                "operation_id": pending.operation_id,
                "kind": pending.kind,
                "target": pending.target,
            },
            "reconciliation_ref": record.reconciliation_ref,
        }
        data = _json_bytes({
            "body": body,
            "sha256": hashlib.sha256(_json_bytes(body)).hexdigest(),
        }) + b"\n"

        temporary = None
        try:
            with NamedTemporaryFile(dir=self.path.parent, delete=False) as out:
                temporary = Path(out.name)
                out.write(data)
            if create_only:
                # Publish without replacing an existing store.
                os.link(temporary, self.path)
            else:
                os.replace(temporary, self.path)
            confirmed = self.load()
            if confirmed != record:
                raise CheckpointWriteError("checkpoint readback differs from the write")
            return confirmed
        except CheckpointWriteError:
            raise
        except (OSError, CheckpointError) as exc:
            raise CheckpointWriteError("checkpoint publication was not confirmed") from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass  # A leftover temporary file is not a checkpoint.

    def provision(self, *, restrictions: frozenset[str]) -> Checkpoint:
        """Create a new store explicitly. Never called as a load fallback."""
        return self._publish(
            Checkpoint(self.store_id, 0, restrictions), create_only=True,
        )

    def _require_current(self, expected: Checkpoint, *, phase: str) -> None:
        if expected.phase != phase or self.load() != expected:
            raise CheckpointConflict("checkpoint phase or revision changed")

    def begin(self, expected: Checkpoint, operation: PendingOperation) -> Checkpoint:
        """Return only after the pending operation has been read back."""
        if type(operation) is not PendingOperation:
            raise CheckpointInvalid("a pending operation is required")
        self._require_current(expected, phase="clean")
        return self._publish(Checkpoint(
            self.store_id, expected.revision + 1, expected.restrictions,
            operation, expected.reconciliation_ref,
        ))

    def _finish(
        self, expected: Checkpoint, *, reconciliation_ref: str | None,
    ) -> Checkpoint:
        self._require_current(expected, phase="pending")
        operation = expected.pending
        if operation is None:
            raise CheckpointConflict("no pending operation")
        restrictions = expected.restrictions
        if operation.kind == "activate_restriction":
            restrictions = restrictions | {operation.target}
        elif operation.kind == "release_restriction" and reconciliation_ref is None:
            restrictions = restrictions - {operation.target}
        return self._publish(Checkpoint(
            self.store_id, expected.revision + 1, restrictions,
            reconciliation_ref=reconciliation_ref or expected.reconciliation_ref,
        ))

    def commit(self, expected: Checkpoint) -> Checkpoint:
        """Confirm completion of a successfully processed operation."""
        return self._finish(expected, reconciliation_ref=None)

    def reconcile(self, expected: Checkpoint, *, audit_ref: str) -> Checkpoint:
        """Resolve a pending operation after the axis confirms its audit entry."""
        if not _nonblank(audit_ref):
            raise CheckpointInvalid("confirmed reconciliation reference required")
        return self._finish(expected, reconciliation_ref=audit_ref)

    def rebuild(
        self, *, restrictions: frozenset[str], audit_ref: str, revision_floor: int,
    ) -> Checkpoint:
        """Write a reviewed baseline after a confirmed administrative audit entry.

        The caller supplies the independently reviewed restriction set and its
        last known revision (-1 if none is known). A valid, incompatible, or
        inaccessible checkpoint is not overwritten by this path.
        """
        if not _nonblank(audit_ref) or type(revision_floor) is not int or revision_floor < -1:
            raise CheckpointInvalid("audit reference and a valid revision floor required")
        record = Checkpoint(
            self.store_id, revision_floor + 1, restrictions,
            reconciliation_ref=audit_ref,
        )
        try:
            self.load()
        except CheckpointMissing:
            return self._publish(record, create_only=True)
        except CheckpointInvalid:
            return self._publish(record)
        raise CheckpointConflict("a valid checkpoint already exists")
