"""Unit tests for Virtual-Real Transition Axis v0.1.

15 deterministic tests.
Python 3.11+.
No external dependencies.
"""

import unittest

from axis import (
    AuditLog,
    AuthorityError,
    Mode,
    Role,
    Token,
    TransitionAxis,
    ValidationError,
)


class TestTransitionAxis(unittest.TestCase):
    """Behavioral tests for the independent transition axis."""

    def setUp(self):
        self.axis = TransitionAxis(virtual_limit=3)
        self.virtual = self.axis.issue_token(
            "virtual-1", Role.VIRTUAL
        )
        self.real = self.axis.issue_token(
            "real-1", Role.REAL
        )

    # ---------------------------------------------------------
    # 01. Initialization and hard policy
    # ---------------------------------------------------------

    def test_01_initial_state_and_policy(self):
        self.assertEqual(self.axis.mode, Mode.NORMAL)
        self.assertEqual(self.axis.virtual_load, 0)
        self.assertEqual(self.axis.generation, 0)

        self.assertIn(
            "virtual_cannot_execute_real",
            TransitionAxis.HARD_POLICY,
        )
        self.assertIn(
            "unverified_evidence_cannot_execute",
            TransitionAxis.HARD_POLICY,
        )
        self.assertIn(
            "stale_authority_is_rejected",
            TransitionAxis.HARD_POLICY,
        )
        self.assertIn(
            "human_approval_required_for_recovery",
            TransitionAxis.HARD_POLICY,
        )

    # ---------------------------------------------------------
    # 02. Invalid configuration
    # ---------------------------------------------------------

    def test_02_invalid_virtual_limit(self):
        with self.assertRaises(ValueError):
            TransitionAxis(virtual_limit=0)

        with self.assertRaises(ValueError):
            TransitionAxis(virtual_limit=-1)

    # ---------------------------------------------------------
    # 03. Token issuance validation
    # ---------------------------------------------------------

    def test_03_token_issuance_validation(self):
        self.assertEqual(self.virtual.role, Role.VIRTUAL)
        self.assertEqual(self.real.role, Role.REAL)

        with self.assertRaises(ValidationError):
            self.axis.issue_token("", Role.VIRTUAL)

        with self.assertRaises(AuthorityError):
            self.axis.issue_token(
                "virtual-1", Role.VIRTUAL
            )

    # ---------------------------------------------------------
    # 04. Virtual events within limit
    # ---------------------------------------------------------

    def test_04_virtual_events_accepted(self):
        for number in range(1, 4):
            result = self.axis.receive_virtual(
                self.virtual,
                {"event_id": f"event-{number}"},
            )
            self.assertEqual(result, "accepted")

        self.assertEqual(self.axis.virtual_load, 3)
        self.assertEqual(self.axis.mode, Mode.NORMAL)

    # ---------------------------------------------------------
    # 05. Backpressure and degraded mode
    # ---------------------------------------------------------

    def test_05_virtual_backpressure(self):
        for number in range(1, 4):
            self.axis.receive_virtual(
                self.virtual,
                {"event_id": f"event-{number}"},
            )

        result = self.axis.receive_virtual(
            self.virtual,
            {"event_id": "event-4"},
        )

        self.assertEqual(result, "backpressure")
        self.assertEqual(self.axis.virtual_load, 3)
        self.assertEqual(self.axis.mode, Mode.DEGRADED)

    # ---------------------------------------------------------
    # 06. Invalid virtual evidence
    # ---------------------------------------------------------

    def test_06_invalid_virtual_event_rejected(self):
        invalid_events = [
            None,
            [],
            {},
            {"event_id": ""},
            {"event_id": 123},
        ]

        for event in invalid_events:
            with self.subTest(event=event):
                with self.assertRaises(ValidationError):
                    self.axis.receive_virtual(
                        self.virtual, event
                    )

        self.assertEqual(self.axis.virtual_load, 0)

    # ---------------------------------------------------------
    # 07. Virtual-to-real privilege escalation
    # ---------------------------------------------------------

    def test_07_virtual_cannot_execute_real(self):
        with self.assertRaises(AuthorityError):
            self.axis.execute_real(
                self.virtual,
                "analyze",
                verified=True,
            )

    # ---------------------------------------------------------
    # 08. Unverified real operation
    # ---------------------------------------------------------

    def test_08_unverified_real_operation_rejected(self):
        with self.assertRaises(AuthorityError):
            self.axis.execute_real(
                self.real,
                "analyze",
                verified=False,
            )

    # ---------------------------------------------------------
    # 09. Allowed real operations
    # ---------------------------------------------------------

    def test_09_verified_real_operations_allowed(self):
        for operation in ("analyze", "record", "propose"):
            with self.subTest(operation=operation):
                result = self.axis.execute_real(
                    self.real,
                    operation,
                    verified=True,
                )
                self.assertTrue(result)

    # ---------------------------------------------------------
    # 10. Forbidden real operations
    # ---------------------------------------------------------

    def test_10_forbidden_real_operation_rejected(self):
        forbidden_operations = [
            "delete",
            "deploy",
            "execute",
            "modify_policy",
        ]

        for operation in forbidden_operations:
            with self.subTest(operation=operation):
                with self.assertRaises(AuthorityError):
                    self.axis.execute_real(
                        self.real,
                        operation,
                        verified=True,
                    )

    # ---------------------------------------------------------
    # 11. Hard policy cannot be modified
    # ---------------------------------------------------------

    def test_11_hard_policy_modification_rejected(self):
        original_policy = TransitionAxis.HARD_POLICY

        with self.assertRaises(AuthorityError):
            self.axis.update_hard_policy(
                self.virtual,
                {"virtual_can_execute_real"},
            )

        with self.assertRaises(AuthorityError):
            self.axis.update_hard_policy(
                self.real,
                set(),
            )

        self.assertEqual(
            TransitionAxis.HARD_POLICY,
            original_policy,
        )

    # ---------------------------------------------------------
    # 12. Emergency neutralization
    # ---------------------------------------------------------

    def test_12_neutralization_blocks_operations(self):
        self.axis.neutralize("simulated emergency")

        self.assertEqual(
            self.axis.mode,
            Mode.ZERO_NEUTRAL,
        )
        self.assertEqual(self.axis.virtual_load, 0)
        self.assertEqual(self.axis.generation, 1)

        with self.assertRaises(AuthorityError):
            self.axis.receive_virtual(
                self.virtual,
                {"event_id": "blocked-event"},
            )

        with self.assertRaises(AuthorityError):
            self.axis.execute_real(
                self.real,
                "analyze",
                verified=True,
            )

        with self.assertRaises(AuthorityError):
            self.axis.issue_token(
                "new-token",
                Role.REAL,
            )

        with self.assertRaises(AuthorityError):
            self.axis.reset_virtual_load()

    # ---------------------------------------------------------
    # 13. Stale authority after recovery
    # ---------------------------------------------------------

    def test_13_stale_token_rejected_after_recovery(self):
        old_virtual = self.virtual
        old_real = self.real

        self.axis.neutralize("authority rotation")

        recovered = self.axis.recover(
            safety_verified=True,
            human_approved=True,
        )

        self.assertTrue(recovered)
        self.assertEqual(self.axis.mode, Mode.NORMAL)

        with self.assertRaises(AuthorityError):
            self.axis.receive_virtual(
                old_virtual,
                {"event_id": "stale-event"},
            )

        with self.assertRaises(AuthorityError):
            self.axis.execute_real(
                old_real,
                "analyze",
                verified=True,
            )

        new_virtual = self.axis.issue_token(
            "virtual-2",
            Role.VIRTUAL,
        )

        result = self.axis.receive_virtual(
            new_virtual,
            {"event_id": "fresh-event"},
        )

        self.assertEqual(result, "accepted")

    # ---------------------------------------------------------
    # 14. Recovery requires verification and approval
    # ---------------------------------------------------------

    def test_14_recovery_requires_both_conditions(self):
        self.axis.neutralize("recovery test")

        denied_cases = [
            (False, False),
            (False, True),
            (True, False),
        ]

        for safety_verified, human_approved in denied_cases:
            with self.subTest(
                safety_verified=safety_verified,
                human_approved=human_approved,
            ):
                result = self.axis.recover(
                    safety_verified=safety_verified,
                    human_approved=human_approved,
                )

                self.assertFalse(result)
                self.assertEqual(
                    self.axis.mode,
                    Mode.ZERO_NEUTRAL,
                )

        result = self.axis.recover(
            safety_verified=True,
            human_approved=True,
        )

        self.assertTrue(result)
        self.assertEqual(self.axis.mode, Mode.NORMAL)

        # Recovery is not repeated in normal mode.
        self.assertFalse(
            self.axis.recover(
                safety_verified=True,
                human_approved=True,
            )
        )

    # ---------------------------------------------------------
    # 15. Audit chain verification and tamper detection
    # ---------------------------------------------------------

    def test_15_audit_chain_integrity(self):
        audit = AuditLog()

        audit.append("event_one", {"value": 1})
        audit.append("event_two", {"value": 2})
        audit.append("event_three", {"value": 3})

        self.assertEqual(len(audit.records), 3)
        self.assertTrue(audit.verify())

        # Simulated in-memory tampering.
        audit.records[1]["details"]["value"] = 999

        self.assertFalse(audit.verify())

        # The axis audit is valid before tampering.
        self.assertTrue(self.axis.audit.verify())


if __name__ == "__main__":
    unittest.main(verbosity=2)
