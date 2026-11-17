"""VRTA v0.5 tests for the local checkpoint store, not the axis."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import checkpoint
from checkpoint import (
    CheckpointConflict,
    CheckpointIncompatible,
    CheckpointInvalid,
    CheckpointMissing,
    CheckpointStore,
    CheckpointUnavailable,
    CheckpointWriteError,
    PendingOperation,
)

STORE_ID = "test-axis"
INTAKE = "restrict_intake"
ANALYSIS = "suspend_analysis"


class TestCheckpointStore(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "checkpoint.json"
        self.store = self.open_store()

    def open_store(self):
        return CheckpointStore(self.path, store_id=STORE_ID)

    def provision(self, *restrictions):
        return self.store.provision(restrictions=frozenset(restrictions))

    def write_fixture(self, body, *, rehash=True):
        envelope = json.loads(self.path.read_bytes())
        envelope["body"] = body
        if rehash:
            raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("ascii")
            envelope["sha256"] = hashlib.sha256(raw).hexdigest()
        self.path.write_text(json.dumps(envelope), encoding="utf-8")

    def test_missing_checkpoint_does_not_provision_or_fall_back(self):
        self.provision(INTAKE)
        backup = self.path.with_suffix(".bak")
        self.path.rename(backup)
        with self.assertRaises(CheckpointMissing):
            self.store.load()
        self.assertFalse(self.path.exists())
        self.assertTrue(backup.exists())

    def test_provision_keeps_an_existing_checkpoint(self):
        original = self.provision(INTAKE)
        with self.assertRaises(CheckpointWriteError):
            self.provision()
        self.assertEqual(original.revision, 0)
        self.assertEqual(original.phase, "clean")
        self.assertEqual(self.open_store().load(), original)

    def test_confirmed_operations_update_phase_revision_and_restrictions(self):
        current = self.provision(INTAKE)
        cases = (
            ("rotate_role", "real", {INTAKE}),
            ("activate_restriction", ANALYSIS, {INTAKE, ANALYSIS}),
            ("release_restriction", INTAKE, {ANALYSIS}),
        )
        for index, (kind, target, expected) in enumerate(cases, 1):
            with self.subTest(kind=kind):
                request = PendingOperation(f"op-{index}", kind, target)
                pending = self.store.begin(current, request)
                self.assertEqual(pending.phase, "pending")
                self.assertEqual(pending.pending, request)
                self.assertEqual(pending.restrictions, current.restrictions)
                self.assertEqual(pending.revision, current.revision + 1)
                self.assertEqual(self.open_store().load(), pending)
                current = self.store.commit(pending)
                self.assertEqual(current.phase, "clean")
                self.assertIsNone(current.pending)
                self.assertEqual(current.revision, pending.revision + 1)
                self.assertEqual(current.restrictions, frozenset(expected))
                self.assertEqual(self.open_store().load(), current)

    def test_corrupt_or_inconsistent_checkpoint_is_rejected(self):
        self.provision(INTAKE)
        original = self.path.read_bytes()
        body = json.loads(original)["body"]
        cases = (
            ({"restrictions": []}, False),
            ({"restrictions": [INTAKE, INTAKE]}, True),
            ({"restrictions": ["unknown"]}, True),
            ({"phase": "pending"}, True),
            ({"revision": False}, True),
        )
        for changes, rehash in cases:
            with self.subTest(changes=changes):
                self.path.write_bytes(original)
                self.write_fixture({**body, **changes}, rehash=rehash)
                with self.assertRaises(CheckpointInvalid):
                    self.store.load()
        for raw in (b"{", b'{"body": {}, "body": {}, "sha256": ""}'):
            with self.subTest(raw=raw):
                self.path.write_bytes(raw)
                with self.assertRaises(CheckpointInvalid):
                    self.store.load()

    def test_wrong_store_and_unsupported_schema_are_rejected(self):
        self.provision(INTAKE)
        original = self.path.read_bytes()
        body = json.loads(original)["body"]
        for changes in ({"store_id": "other-axis"}, {"schema_version": 999}):
            with self.subTest(changes=changes):
                self.path.write_bytes(original)
                self.write_fixture({**body, **changes})
                with self.assertRaises(CheckpointIncompatible):
                    self.store.load()
                with self.assertRaises(CheckpointIncompatible):
                    self.store.rebuild(
                        restrictions=frozenset({INTAKE}), audit_ref="review",
                        revision_floor=0,
                    )

    def test_read_failure_is_not_treated_as_missing(self):
        self.provision(INTAKE)
        with patch.object(Path, "read_bytes", side_effect=PermissionError("test")):
            with self.assertRaises(CheckpointUnavailable):
                self.store.load()

    def test_same_revision_with_different_contents_is_rejected(self):
        initial = self.provision(INTAKE)
        alter = replace(initial, restrictions=frozenset())
        with self.assertRaises(CheckpointConflict):
            self.store.begin(alter, PendingOperation("r1", "rotate_role", "real"))
        self.assertEqual(self.store.load(), initial)

    def test_failed_pending_replacement_leaves_clean_checkpoint(self):
        initial = self.provision(INTAKE)
        request = PendingOperation("r1", "rotate_role", "real")
        with patch("checkpoint.os.replace", side_effect=OSError("before replace")):
            with self.assertRaises(CheckpointWriteError):
                self.store.begin(initial, request)
        self.assertEqual(self.open_store().load(), initial)

    def test_unconfirmed_pending_write_is_visible_but_not_returned_as_success(self):
        initial = self.provision(INTAKE)
        request = PendingOperation("r1", "rotate_role", "real")
        with patch.object(
            self.store, "load",
            side_effect=[initial, CheckpointUnavailable("readback failed")],
        ):
            with self.assertRaises(CheckpointWriteError):
                self.store.begin(initial, request)
        pending = self.open_store().load()
        self.assertEqual(pending.pending, request)
        self.assertEqual(pending.phase, "pending")
        self.assertEqual(pending.restrictions, initial.restrictions)

    def test_failed_final_write_differs_from_unconfirmed_final_write(self):
        initial = self.provision(INTAKE)
        pending = self.store.begin(
            initial, PendingOperation("r1", "release_restriction", INTAKE),
        )
        with patch("checkpoint.os.replace", side_effect=OSError("before replace")):
            with self.assertRaises(CheckpointWriteError):
                self.store.commit(pending)
        self.assertEqual(self.open_store().load(), pending)

        with patch.object(
            self.store, "load",
            side_effect=[pending, CheckpointUnavailable("readback failed")],
        ):
            with self.assertRaises(CheckpointWriteError):
                self.store.commit(pending)
        observed = self.open_store().load()
        self.assertEqual(observed.phase, "clean")
        self.assertEqual(observed.restrictions, frozenset())
        self.assertEqual(observed.revision, pending.revision + 1)

    def test_reconciliation_keeps_restrictions_and_abandons_handover(self):
        current = self.provision(INTAKE)
        cases = (
            ("activate_restriction", ANALYSIS, {INTAKE, ANALYSIS}),
            ("release_restriction", INTAKE, {INTAKE, ANALYSIS}),
            ("rotate_role", "real", {INTAKE, ANALYSIS}),
        )
        for index, (kind, target, expected) in enumerate(cases, 1):
            with self.subTest(kind=kind):
                pending = self.store.begin(
                    current, PendingOperation(f"op-{index}", kind, target),
                )
                current = self.open_store().reconcile(
                    pending, audit_ref=f"reconciled-{index}",
                )
                self.assertEqual(current.phase, "clean")
                self.assertIsNone(current.pending)
                self.assertEqual(current.restrictions, frozenset(expected))
                self.assertEqual(current.reconciliation_ref, f"reconciled-{index}")
                self.assertEqual(self.store.load(), current)

    def test_reconciliation_requires_nonblank_audit_reference(self):
        pending = self.store.begin(
            self.provision(), PendingOperation("r1", "rotate_role", "real"),
        )
        with self.assertRaises(CheckpointInvalid):
            self.store.reconcile(pending, audit_ref=" ")
        self.assertEqual(self.store.load(), pending)

    def test_reviewed_rebuild_of_missing_or_corrupt_baseline(self):
        restrictions = frozenset({ANALYSIS})
        first = self.store.rebuild(
            restrictions=restrictions, audit_ref="review-1", revision_floor=4,
        )
        self.assertEqual((first.phase, first.revision), ("clean", 5))
        self.assertEqual(first.restrictions, restrictions)
        with self.assertRaises(CheckpointConflict):
            self.store.rebuild(
                restrictions=frozenset(), audit_ref="review-2", revision_floor=5,
            )
        self.path.write_bytes(b"not JSON")
        second = self.store.rebuild(
            restrictions=restrictions, audit_ref="review-3", revision_floor=5,
        )
        self.assertEqual(second.revision, 6)
        self.assertEqual(second.reconciliation_ref, "review-3")
        self.assertEqual(self.open_store().load(), second)

    def test_pending_survives_child_exit_without_cleanup(self):
        initial = self.provision(INTAKE)
        child = """
import os
import sys
from checkpoint import CheckpointStore, PendingOperation

store = CheckpointStore(sys.argv[1], store_id=sys.argv[2])
store.begin(store.load(), PendingOperation("child-r1", "rotate_role", "real"))
os._exit(73)
"""
        result = subprocess.run(
            [sys.executable, "-c", child, str(self.path), STORE_ID],
            cwd=Path(checkpoint.__file__).resolve().parent,
            capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 73, result.stderr)
        pending = self.open_store().load()
        self.assertEqual(pending.phase, "pending")
        self.assertEqual(pending.pending, PendingOperation("child-r1", "rotate_role", "real"))
        self.assertEqual(pending.revision, initial.revision + 1)
        self.assertEqual(pending.restrictions, initial.restrictions)


if __name__ == "__main__":
    unittest.main()
