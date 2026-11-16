"""VRTA v0.4 acceptance tests. Faults are local and deterministic."""

import unittest
from dataclasses import replace
from unittest.mock import patch

from role_rotation import (
    DomainRole,
    RoleRotation,
    RotationDenied,
    RotationFailed,
    RotationRequest,
)


class TestRoleRotation(unittest.TestCase):
    def setUp(self):
        self.admin = object()
        self.records = []
        self.roles = RoleRotation(
            administrator=self.admin,
            audit_ready=lambda: True,
            append_audit=lambda action, details: self.records.append(action),
        )
        self.old = self.roles.assign(
            administrator=self.admin, role=DomainRole.REAL,
            token_id="real-1", generation=0,
        )
        self.request = RotationRequest(
            "r1", DomainRole.REAL, "real-1", "real-2", "Scheduled handover",
        )

    def accepts(self, credential):
        return self.roles.accepts(credential, role=DomainRole.REAL, generation=0)

    def rotate(self, request=None, generation=0):
        return self.roles.rotate(
            request or self.request, administrator=self.admin, generation=generation,
        )

    def test_neither_credential_is_accepted_during_cutover(self):
        # Capture only a test-local reference. The public API returns it at commit.
        from role_rotation import DomainCredential

        staged = DomainCredential("real-2", DomainRole.REAL, 0)
        checks = []

        def append(action, details):
            if action == "rotation_completion":
                checks.append((self.accepts(self.old), self.accepts(staged)))

        with patch("role_rotation.DomainCredential", return_value=staged):
            with patch.object(self.roles, "_append_audit", side_effect=append):
                new = self.rotate()
        self.assertEqual(checks, [(False, False)])
        self.assertIs(new, staged)
        self.assertTrue(self.accepts(new))
        self.assertFalse(self.accepts(self.old))

    def test_stale_binding_is_rejected_in_preflight(self):
        with self.assertRaises(RotationDenied):
            self.rotate(generation=1)
        self.assertTrue(self.accepts(self.old))
        self.assertEqual(self.records, [])

    def test_rotation_id_cannot_be_reused(self):
        current = self.rotate()
        with self.assertRaises(RotationDenied):
            self.rotate(replace(self.request, expected_current_id="real-2", new_id="real-3"))
        self.assertTrue(self.accepts(current))


class TestTransitionAxisV4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Keep the standalone tests runnable without the v0.3 source files.
        import axis
        import evidence
        import feedback
        import five_elements

        cls.api = axis
        cls.load = feedback.LoadObservation
        cls.evidence = evidence
        cls.elements = five_elements

    def setUp(self):
        self.admin = object()
        self.axis = self.api.TransitionAxisV4(
            virtual_limit=3,
            trusted_sources=frozenset({"sensor-alpha"}),
            element_bindings={"water-1": self.elements.Element.WATER},
            administrator=self.admin,
        )
        self.virtual = self.issue("virtual-1", self.api.Role.VIRTUAL)
        self.real = self.issue("real-1", self.api.Role.REAL)
        self.request = RotationRequest(
            "r1", DomainRole.REAL, "real-1", "real-2", "Scheduled handover",
        )

    def issue(self, token_id, role):
        return self.axis.issue_token(token_id, role, administrator=self.admin)

    def rotate(self, request=None):
        return self.axis.rotate_role(request or self.request, administrator=self.admin)

    def recover(self, safety=True, approval=True):
        return self.axis.recover(
            administrator=self.admin, safety_verified=safety, human_approved=approval,
        )

    def intake(self, token, event_id):
        return self.axis.receive_virtual(token, {"event_id": event_id})

    def receipt(self, virtual, suffix):
        event_id = f"event-{suffix}"
        self.assertEqual(self.intake(virtual, event_id), "accepted")
        return self.axis.verify_evidence(self.evidence.build_evidence(
            evidence_id=f"evidence-{suffix}", event_id=event_id,
            source_id="sensor-alpha", payload={"sample": suffix},
        )).receipt_id

    def execute(self, token, receipt, operation="analyze"):
        return self.axis.execute_real_verified(token, operation, receipt_id=receipt)

    def suspend_analysis(self):
        token = self.axis.issue_element_token("water-1", administrator=self.admin)
        self.axis.request_restriction(token, {
            "request_id": "restriction-1", "source_element": "water",
            "target_element": "fire", "action": "suspend_analysis",
            "reason": "Simulated audit finding",
        })
        return token

    def test_normal_real_handover_preserves_generation_and_evidence(self):
        receipt = self.receipt(self.virtual, "original")
        generation = self.axis.generation
        new = self.rotate()
        with self.assertRaises(self.api.AuthorityError):
            self.execute(self.real, receipt)
        self.assertTrue(self.execute(new, receipt))
        with self.assertRaises(self.api.AuthorityError):
            self.execute(new, "unknown-receipt")
        self.assertEqual(self.intake(self.virtual, "other-role"), "accepted")
        self.assertEqual(self.axis.generation, generation)
        self.assertTrue(self.axis.verify_audit())

    def test_normal_virtual_handover_preserves_real_role(self):
        generation = self.axis.generation
        new = self.rotate(RotationRequest(
            "virtual-r1", DomainRole.VIRTUAL, "virtual-1", "virtual-2", "Handover",
        ))
        with self.assertRaises(self.api.AuthorityError):
            self.intake(self.virtual, "old-holder")
        self.assertTrue(self.execute(self.real, self.receipt(new, "new-holder")))
        self.assertEqual(self.axis.generation, generation)

    def test_preflight_denials_leave_authority_unchanged(self):
        cases = (
            ("wrong admin", self.request, object()),
            ("unknown old ID", replace(self.request, expected_current_id="missing"), self.admin),
            ("wrong role", replace(self.request, role=DomainRole.VIRTUAL), self.admin),
            ("reused new ID", replace(self.request, new_id="virtual-1"), self.admin),
        )
        receipt = self.receipt(self.virtual, "preflight")
        for label, request, admin in cases:
            with self.subTest(label=label):
                with self.assertRaises(self.api.AuthorityError):
                    self.axis.rotate_role(request, administrator=admin)
                self.assertEqual(self.axis.mode, self.api.Mode.NORMAL)
                self.assertEqual(self.axis.generation, 0)
                self.assertTrue(self.execute(self.real, receipt))

        with patch.object(self.axis._core.audit, "append", side_effect=OSError("offline")):
            with self.assertRaises(self.api.AuthorityError):
                self.rotate()
        self.assertEqual(self.axis.mode, self.api.Mode.NORMAL)
        self.assertEqual(self.axis.generation, 0)
        self.assertTrue(self.execute(self.real, receipt))

    def test_assignment_cannot_bypass_rotation(self):
        with self.assertRaises(self.api.AuthorityError):
            self.axis.issue_token("real-2", self.api.Role.REAL)
        with self.assertRaises(self.api.AuthorityError):
            self.issue("real-2", self.api.Role.REAL)
        with self.assertRaises(self.api.AuthorityError):
            self.axis.execute_real(self.real, "analyze", verified=True)

    def test_neutralization_blocks_rotation_and_assignment(self):
        self.axis.neutralize("Maintenance", administrator=self.admin)
        generation = self.axis.generation
        with self.assertRaises(self.api.AuthorityError):
            self.rotate()
        with self.assertRaises(self.api.AuthorityError):
            self.issue("real-3", self.api.Role.REAL)
        self.assertEqual(self.axis.generation, generation)
        self.assertEqual(self.axis.mode, self.api.Mode.ZERO_NEUTRAL)

    def test_revocation_failure_requires_audited_explicit_recovery(self):
        old_receipt = self.receipt(self.virtual, "before")
        old_element = self.suspend_analysis()
        log = self.axis._core.audit
        original_append = log.append
        offline = False

        def append(action, details):
            if offline:
                raise OSError("audit is offline")
            original_append(action, details)

        def fail_after_revocation():
            nonlocal offline
            offline = True
            raise OSError("handover interrupted")

        with patch.object(log, "append", side_effect=append):
            with patch.object(self.axis._rotation, "_after_revocation", fail_after_revocation):
                with self.assertRaises(RotationFailed):
                    self.rotate()
            self.assertEqual(self.axis.mode, self.api.Mode.ZERO_NEUTRAL)
            self.assertEqual(self.axis.generation, 1)
            self.assertFalse(self.recover())

        for window in range(1, 5):
            self.axis.observe_load(self.load(window, 0.0, 0.0))
            self.assertEqual(self.axis.mode, self.api.Mode.ZERO_NEUTRAL)
        with self.assertRaises(self.api.AuthorityError):
            self.axis.recover(safety_verified=True, human_approved=True)
        self.assertFalse(self.recover(safety=False))
        self.assertFalse(self.recover(approval=False))

        def deny_reconciliation(action, details):
            if action == "rotation_reconciled":
                raise OSError("reconciliation unavailable")
            original_append(action, details)

        with patch.object(log, "append", side_effect=deny_reconciliation):
            self.assertFalse(self.recover())
        self.assertEqual(self.axis.mode, self.api.Mode.ZERO_NEUTRAL)
        self.assertTrue(self.recover())
        self.assertIn("rotation_reconciled", [r["action"] for r in self.axis.audit_records])
        with self.assertRaises(self.api.AuthorityError):
            self.issue("real-2", self.api.Role.REAL)
        new_real = self.issue("real-3", self.api.Role.REAL)
        new_virtual = self.issue("virtual-2", self.api.Role.VIRTUAL)
        new_receipt = self.receipt(new_virtual, "after")
        with self.assertRaises(self.api.AuthorityError):
            self.intake(self.virtual, "stale-holder")
        with self.assertRaises(self.api.AuthorityError):
            self.execute(self.real, new_receipt, "record")
        with self.assertRaises(self.api.AuthorityError):
            self.execute(new_real, old_receipt, "record")
        with self.assertRaises(self.api.AuthorityError):
            self.axis.request_restriction(old_element, {
                "request_id": "restriction-2", "source_element": "water",
                "target_element": "fire", "action": "suspend_analysis", "reason": "Test",
            })
        self.assertTrue(self.axis.restriction_active(
            self.elements.RestrictionAction.SUSPEND_ANALYSIS,
        ))
        with self.assertRaises(self.api.AuthorityError):
            self.execute(new_real, new_receipt)
        self.assertTrue(self.execute(new_real, new_receipt, "record"))
        self.assertTrue(self.axis.verify_audit())

    def test_completion_append_before_and_after_write(self):
        from role_rotation import DomainCredential

        for after_write in (False, True):
            with self.subTest(after_write=after_write):
                self.setUp()
                receipt = self.receipt(self.virtual, "audit")
                log = self.axis._core.audit
                original_append = log.append
                staged = DomainCredential("real-2", DomainRole.REAL, 0)

                def append(action, details):
                    if action != "rotation_completion" or after_write:
                        original_append(action, details)
                    if action == "rotation_completion":
                        raise OSError("completion not confirmed")

                with patch("role_rotation.DomainCredential", return_value=staged):
                    with patch.object(log, "append", side_effect=append):
                        with self.assertRaises(RotationFailed):
                            self.rotate()
                actions = [record["action"] for record in self.axis.audit_records]
                self.assertEqual("rotation_completion" in actions, after_write)
                self.assertIn("rotation_failed", actions)
                self.assertEqual(self.axis.mode, self.api.Mode.ZERO_NEUTRAL)
                self.assertEqual(self.axis.generation, 1)
                for token in (self.real, staged):
                    with self.assertRaises(self.api.AuthorityError):
                        self.execute(token, receipt, "record")

    def test_active_analysis_restriction_survives_real_handover(self):
        receipt = self.receipt(self.virtual, "restricted")
        self.suspend_analysis()
        new = self.rotate()
        with self.assertRaises(self.api.AuthorityError):
            self.execute(new, receipt)
        self.assertTrue(self.execute(new, receipt, "record"))

    def test_feedback_recovery_preserves_event_limit_degradation(self):
        for index in range(3):
            self.assertEqual(self.intake(self.virtual, str(index)), "accepted")
        self.assertEqual(self.intake(self.virtual, "overflow"), "backpressure")
        self.axis.observe_load(self.load(1, 0.9, 0.1))
        self.assertCountEqual(
            self.axis.degradation_causes, ("virtual_event_limit", "feedback_overload"),
        )
        for window in range(2, 5):
            self.axis.observe_load(self.load(window, 0.2, 0.2))
        self.assertEqual(self.axis.degradation_causes, ("virtual_event_limit",))
        self.assertEqual(self.axis.mode, self.api.Mode.DEGRADED)
        self.assertEqual(self.intake(self.virtual, "still-full"), "backpressure")

    def test_event_window_reset_preserves_feedback_degradation(self):
        for index in range(4):
            self.intake(self.virtual, str(index))
        self.axis.observe_load(self.load(1, 0.9, 0.1))
        self.axis.reset_virtual_load(administrator=self.admin)
        self.assertEqual(self.axis.degradation_causes, ("feedback_overload",))
        self.assertEqual(self.axis.mode, self.api.Mode.DEGRADED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
