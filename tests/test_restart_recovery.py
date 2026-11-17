"""Integration tests for VRTA v0.5 restart and checkpoint ordering."""

import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import UUID

from axis import (
    AuthorityError,
    DomainRole,
    Element,
    LoadObservation,
    Mode,
    RestrictionAction,
    Role,
    RotationRequest,
    TransitionAxisV5,
)
from checkpoint import (
    CheckpointStore,
    CheckpointUnavailable,
    CheckpointWriteError,
    PendingOperation,
)
from evidence import build_evidence

ANALYSIS = RestrictionAction.SUSPEND_ANALYSIS
CUTOVER_EXIT = 73
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHILD_RUNNER = """
import runpy
import sys
from pathlib import Path

probe = runpy.run_path(sys.argv[1])[sys.argv[2]]
probe(Path(sys.argv[3]))
"""


def make_axis(path, administrator):
    return TransitionAxisV5(
        checkpoint=CheckpointStore(path, store_id="restart-test"),
        administrator=administrator,
        trusted_sources=frozenset({"sensor"}),
        element_bindings={"water": Element.WATER},
    )


def approve(axis, administrator, context=None, *, safety=True, human=True):
    return axis.recover(
        administrator=administrator,
        context=axis.recovery_context() if context is None else context,
        safety_verified=safety,
        human_approved=human,
    )


def suspend_analysis(axis, token):
    return axis.request_restriction(token, {
        "request_id": "suspend-1",
        "source_element": "water",
        "target_element": "fire",
        "action": ANALYSIS.value,
        "reason": "Recorded by the test fixture",
    })


def verify_sample(axis, token):
    axis.receive_virtual(token, {"event_id": "event"})
    evidence = build_evidence(
        evidence_id="evidence", event_id="event", source_id="sensor",
        payload={"sample": True},
    )
    return axis.verify_evidence(evidence).receipt_id


def crash_after_revocation(path):
    import os

    admin = object()
    axis = make_axis(path, admin)
    if not approve(axis, admin):
        raise AssertionError("child could not leave initial neutral mode")
    old = axis.issue_token("r1", Role.REAL, administrator=admin)

    def stop():
        pending = axis._store.load().pending
        if pending is None or pending.operation_id != "rot1":
            raise AssertionError("pending was not confirmed before revocation")
        if axis._axis._rotation.accepts(
            old, role=DomainRole.REAL, generation=axis.generation,
        ):
            raise AssertionError("outgoing credential was still valid")
        os._exit(CUTOVER_EXIT)  # No normal cleanup or exception handlers.

    axis._axis._rotation._after_revocation = stop
    axis.rotate_role(
        RotationRequest("rot1", DomainRole.REAL, "r1", "r2", "fixture"),
        administrator=admin,
    )
    raise AssertionError("cutover stop hook did not run")


def inspect_interrupted_restart(path):
    admin = object()
    axis = make_axis(path, admin)
    pending = axis.checkpoint.pending
    if axis.mode != Mode.ZERO_NEUTRAL or pending is None or pending.operation_id != "rot1":
        raise AssertionError("fresh process did not start neutral with the pending rotation")
    if approve(axis, admin) or axis._axis._rotation._current:
        raise AssertionError("fresh process resumed the interrupted rotation")


class TestRestartRecovery(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "checkpoint.json"
        self.admin = object()
        self.axis = make_axis(self.path, self.admin)
        self.store = self.axis._store
        self.rotation = RotationRequest("rot1", DomainRole.REAL, "r1", "r2", "fixture")

    def ready(self, restrictions=frozenset()):
        self.axis.provision_checkpoint(administrator=self.admin, restrictions=restrictions)
        self.assertTrue(approve(self.axis, self.admin))

    def issue(self, token_id="r1", role=Role.REAL):
        return self.axis.issue_token(token_id, role, administrator=self.admin)

    def run_child(self, probe, expected):
        child = subprocess.run(
            [sys.executable, "-c", CHILD_RUNNER, str(Path(__file__).resolve()),
             probe, str(self.path)],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(child.returncode, expected, child.stdout + child.stderr)

    def test_restart_preserves_restrictions_but_rejects_old_authority(self):
        self.axis.provision_checkpoint(
            administrator=self.admin, restrictions=frozenset({ANALYSIS.value}),
        )
        prior_context = self.axis.recovery_context()
        self.assertTrue(approve(self.axis, self.admin, prior_context))
        old_real = self.issue()
        old_virtual = self.issue("v1", Role.VIRTUAL)
        old_element = self.axis.issue_element_token("water", administrator=self.admin)

        # Deliberately reuse the local receipt identifier in the new startup.
        with patch("evidence.uuid4", return_value=UUID(int=1)):
            old_receipt = verify_sample(self.axis, old_virtual)
            reboot = make_axis(self.path, self.admin)
            current_context = reboot.recovery_context()
            self.assertNotEqual(current_context.startup_id, prior_context.startup_id)
            self.assertEqual(current_context.revision, prior_context.revision)
            self.assertEqual(current_context.generation, prior_context.generation)
            self.assertEqual(reboot.mode, Mode.ZERO_NEUTRAL)
            self.assertTrue(reboot.restriction_active(ANALYSIS))
            self.assertFalse(approve(reboot, self.admin, prior_context))
            self.assertTrue(approve(reboot, self.admin, current_context))
            new_real = reboot.issue_token("r1", Role.REAL, administrator=self.admin)
            new_virtual = reboot.issue_token("v1", Role.VIRTUAL, administrator=self.admin)
            reboot.issue_element_token("water", administrator=self.admin)
            with self.assertRaises(AuthorityError):
                reboot.receive_virtual(old_virtual, {"event_id": "old"})
            with self.assertRaises(AuthorityError):
                suspend_analysis(reboot, old_element)
            new_receipt = verify_sample(reboot, new_virtual)

        self.assertEqual(old_receipt.partition(":")[2], new_receipt.partition(":")[2])
        for credential, reference, operation in (
            (old_real, new_receipt, "record"),
            (new_real, old_receipt, "record"),
            (new_real, new_receipt, "analyze"),
        ):
            with self.subTest(operation=operation, reference=reference):
                with self.assertRaises(AuthorityError):
                    reboot.execute_real_verified(credential, operation, receipt_id=reference)
        self.assertTrue(reboot.execute_real_verified(new_real, "record", receipt_id=new_receipt))

    def test_pending_is_confirmed_before_revocation(self):
        self.ready()
        old = self.issue()
        generation = self.axis.generation

        def at_cutover():
            record = self.store.load()
            self.assertEqual(record.phase, "pending")
            self.assertEqual(record.pending.operation_id, "rot1")
            self.assertFalse(self.axis._axis._rotation.accepts(
                old, role=DomainRole.REAL, generation=generation,
            ))
            with self.assertRaises(AuthorityError):
                self.axis.issue_token("r3", Role.REAL, administrator=self.admin)

        with patch.object(self.axis._axis._rotation, "_after_revocation", side_effect=at_cutover) as hook:
            new = self.axis.rotate_role(self.rotation, administrator=self.admin)
            hook.assert_called_once_with()
        self.assertEqual(new.token_id, "r2")
        self.assertEqual(self.store.load().phase, "clean")
        self.assertEqual(self.axis.generation, generation)

    def test_invalid_handover_does_not_open_a_transaction(self):
        self.ready()
        self.issue()
        prior = self.store.load()
        invalid = replace(self.rotation, expected_current_id="wrong")
        with patch.object(self.store, "begin", wraps=self.store.begin) as begin:
            with self.assertRaises(AuthorityError):
                self.axis.rotate_role(invalid, administrator=self.admin)
            begin.assert_not_called()
        self.assertEqual(self.store.load(), prior)

    def test_pending_write_failure_before_replace_does_not_begin_changes(self):
        self.ready()
        old = self.issue()
        water = self.axis.issue_element_token("water", administrator=self.admin)
        prior = self.store.load()
        with patch("checkpoint.os.replace", side_effect=OSError("before replace")):
            with patch.object(self.axis._axis._rotation, "_after_revocation") as hook:
                with self.assertRaises(CheckpointWriteError):
                    self.axis.rotate_role(self.rotation, administrator=self.admin)
                hook.assert_not_called()
            with self.assertRaises(CheckpointWriteError):
                suspend_analysis(self.axis, water)
        self.assertEqual(self.axis.mode, Mode.NORMAL)
        self.assertEqual(self.store.load(), prior)
        self.assertFalse(self.axis.restriction_active(ANALYSIS))
        self.assertTrue(self.axis._axis._rotation.accepts(
            old, role=DomainRole.REAL, generation=self.axis.generation,
        ))

    def test_unconfirmed_pending_write_blocks_cutover(self):
        self.ready()
        self.issue()
        original_load = self.store.load

        def fail_pending_readback():
            record = original_load()
            if record.phase == "pending":
                raise CheckpointUnavailable("cannot confirm pending record")
            return record

        with patch.object(self.store, "load", side_effect=fail_pending_readback):
            with patch.object(self.axis._axis._rotation, "_after_revocation") as hook:
                with self.assertRaises(CheckpointWriteError):
                    self.axis.rotate_role(self.rotation, administrator=self.admin)
                hook.assert_not_called()
        self.assertEqual(self.axis.mode, Mode.ZERO_NEUTRAL)
        self.assertEqual(self.store.load().phase, "pending")
        self.assertFalse(approve(self.axis, self.admin))

    def fail_final_readback(self):
        original_load = self.store.load
        final_revision = original_load().revision + 2

        def load():
            record = original_load()
            if record.revision == final_revision:
                raise CheckpointUnavailable("cannot confirm final record")
            return record

        return patch.object(self.store, "load", side_effect=load)

    def test_unconfirmed_release_does_not_lift_the_live_restriction(self):
        self.ready(frozenset({ANALYSIS.value}))
        with self.fail_final_readback():
            with self.assertRaises(CheckpointWriteError):
                self.axis.release_restriction(administrator=self.admin, action=ANALYSIS)
        self.assertEqual(self.axis.mode, Mode.ZERO_NEUTRAL)
        self.assertTrue(self.axis.restriction_active(ANALYSIS))
        self.assertEqual(self.store.load().phase, "clean")
        self.assertFalse(approve(self.axis, self.admin))

    def test_unconfirmed_handover_does_not_return_the_replacement(self):
        self.ready()
        self.issue()
        with self.fail_final_readback():
            with self.assertRaises(CheckpointWriteError):
                self.axis.rotate_role(self.rotation, administrator=self.admin)
        self.assertEqual(self.axis.mode, Mode.ZERO_NEUTRAL)
        self.assertFalse(approve(self.axis, self.admin))
        reboot = make_axis(self.path, self.admin)
        self.assertEqual(reboot.mode, Mode.ZERO_NEUTRAL)
        self.assertTrue(approve(reboot, self.admin))
        self.assertFalse(reboot._axis._rotation._current)

    def test_checkpoint_revision_change_blocks_old_approval(self):
        initial = self.axis.provision_checkpoint(
            administrator=self.admin, restrictions=frozenset(),
        )
        context = self.axis.recovery_context()
        pending = self.store.begin(initial, PendingOperation("rot2", "rotate_role", "real"))
        self.store.commit(pending)
        self.assertFalse(approve(self.axis, self.admin, context))
        self.assertEqual(self.axis.mode, Mode.ZERO_NEUTRAL)

    def test_corrupt_checkpoint_requires_review_and_fresh_approval(self):
        self.assertEqual(self.axis.checkpoint_issue, "CheckpointMissing")
        self.assertFalse(approve(self.axis, self.admin))
        self.path.write_bytes(b"invalid")
        reboot = make_axis(self.path, self.admin)
        self.assertEqual(reboot.checkpoint_issue, "CheckpointInvalid")
        self.assertFalse(approve(reboot, self.admin))
        with self.assertRaises(AuthorityError):
            reboot.provision_checkpoint(administrator=self.admin, restrictions=frozenset())
        reviewed = reboot.rebuild_checkpoint(
            administrator=self.admin, restrictions=frozenset({ANALYSIS.value}),
            baseline_ref="reviewed records", reason="corruption",
        )
        self.assertIsNotNone(reviewed.reconciliation_ref)
        self.assertFalse(approve(reboot, self.admin, human=False))
        self.assertFalse(approve(reboot, self.admin, safety=False))
        with patch.object(reboot._core.audit, "append", side_effect=OSError("offline")):
            self.assertFalse(approve(reboot, self.admin))
        self.assertTrue(approve(reboot, self.admin))
        self.assertTrue(reboot.restriction_active(ANALYSIS))
        self.assertTrue(reboot.verify_audit())

    def test_interrupted_activation_and_release_reconcile_conservatively(self):
        self.axis.provision_checkpoint(administrator=self.admin, restrictions=frozenset())
        for kind in ("activate_restriction", "release_restriction"):
            with self.subTest(kind=kind):
                self.store.begin(
                    self.store.load(), PendingOperation(kind, kind, ANALYSIS.value),
                )
                reboot = make_axis(self.path, self.admin)
                self.assertFalse(approve(reboot, self.admin))
                resolved = reboot.reconcile_checkpoint(administrator=self.admin, reason=kind)
                self.assertEqual(resolved.restrictions, frozenset({ANALYSIS.value}))
                self.assertEqual(reboot.mode, Mode.ZERO_NEUTRAL)
                self.assertTrue(approve(reboot, self.admin))
                self.assertTrue(reboot.restriction_active(ANALYSIS))

    def test_process_exit_after_revocation_requires_reconciliation(self):
        self.axis.provision_checkpoint(
            administrator=self.admin, restrictions=frozenset({ANALYSIS.value}),
        )
        self.run_child("crash_after_revocation", CUTOVER_EXIT)
        self.run_child("inspect_interrupted_restart", 0)

        reboot = make_axis(self.path, self.admin)
        for window in range(3):
            reboot.observe_load(LoadObservation(window, 0.0, 0.0))
        self.assertEqual(reboot.mode, Mode.ZERO_NEUTRAL)
        with patch.object(reboot._core.audit, "append", side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                reboot.reconcile_checkpoint(administrator=self.admin, reason="interrupted")
        self.assertEqual(self.store.load().phase, "pending")
        reboot.reconcile_checkpoint(administrator=self.admin, reason="interrupted")
        self.assertEqual(reboot.mode, Mode.ZERO_NEUTRAL)
        self.assertTrue(approve(reboot, self.admin))
        self.assertTrue(reboot.restriction_active(ANALYSIS))
        self.assertFalse(reboot._axis._rotation._current)


if __name__ == "__main__":
    unittest.main(verbosity=2)
