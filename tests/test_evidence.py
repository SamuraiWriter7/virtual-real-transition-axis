"""Evidence verification tests for VRTA v0.2.

Python 3.11+.
Standard library only.

Tests cover:
- Evidence structure and digest validation
- Trusted-source registration checks
- Accepted-event binding
- Receipt registration and integrity
- Real-operation authorization
- Legacy verification bypass rejection
- Authority generation invalidation
- Fail-closed verification behavior

This suite tests application-level behavior.
It does not establish production security guarantees.
"""

import copy
import unittest
from dataclasses import replace

from axis import (
    AuthorityError,
    Mode,
    Role,
    TransitionAxisV2,
)

from evidence import (
    EvidenceBindingError,
    EvidenceConflictError,
    EvidenceRecord,
    EvidenceValidationError,
    EvidenceVerificationError,
    EvidenceVerifier,
    UntrustedSourceError,
    build_evidence,
    calculate_payload_digest,
)


class TestEvidenceVerification(unittest.TestCase):
    """Independent evidence verification tests."""

    def setUp(self):
        self.admin = object()

        self.axis = TransitionAxisV2(
            virtual_limit=3,
            trusted_sources=frozenset(
                {"sensor-alpha"}
            ),
            element_bindings={},
            administrator=self.admin,
        )

        self.virtual = self.axis.issue_token(
            "virtual-1",
            Role.VIRTUAL,
        )

        self.real = self.axis.issue_token(
            "real-1",
            Role.REAL,
        )

        self.axis.receive_virtual(
            self.virtual,
            {"event_id": "event-001"},
        )

    def make_evidence(
        self,
        evidence_id="evidence-001",
        event_id="event-001",
        source_id="sensor-alpha",
        payload=None,
    ):
        if payload is None:
            payload = {
                "event_type": "simulated_anomaly",
                "severity": "medium",
            }

        return build_evidence(
            evidence_id=evidence_id,
            event_id=event_id,
            source_id=source_id,
            payload=payload,
        )

    # --------------------------------------------------------
    # 01. Deterministic payload digest
    # --------------------------------------------------------

    def test_01_digest_is_deterministic(self):
        first = {
            "a": 1,
            "b": {
                "x": True,
                "y": [1, 2, 3],
            },
        }

        second = {
            "b": {
                "y": [1, 2, 3],
                "x": True,
            },
            "a": 1,
        }

        self.assertEqual(
            calculate_payload_digest(first),
            calculate_payload_digest(second),
        )

        self.assertEqual(
            len(calculate_payload_digest(first)),
            64,
        )

    # --------------------------------------------------------
    # 02. Non-JSON payload rejection
    # --------------------------------------------------------

    def test_02_invalid_payload_rejected(self):
        with self.assertRaises(
            EvidenceValidationError
        ):
            build_evidence(
                evidence_id="evidence-invalid",
                event_id="event-001",
                source_id="sensor-alpha",
                payload={"invalid": {1, 2, 3}},
            )

        with self.assertRaises(
            EvidenceValidationError
        ):
            calculate_payload_digest(
                {"value": float("nan")}
            )

    # --------------------------------------------------------
    # 03. Valid evidence and receipt issuance
    # --------------------------------------------------------

    def test_03_valid_evidence_verified(self):
        evidence = self.make_evidence()

        receipt = self.axis.verify_evidence(
            evidence
        )

        self.assertEqual(
            receipt.evidence_id,
            "evidence-001",
        )

        self.assertEqual(
            receipt.event_id,
            "event-001",
        )

        self.assertEqual(
            receipt.payload_digest,
            evidence["payload_digest"],
        )

        self.assertEqual(
            receipt.status,
            "verified",
        )

        self.assertEqual(
            receipt.generation,
            self.axis.generation,
        )

        self.assertTrue(
            receipt.receipt_id.startswith("receipt-")
        )

    # --------------------------------------------------------
    # 04. Missing evidence fields
    # --------------------------------------------------------

    def test_04_missing_fields_rejected(self):
        evidence = self.make_evidence()

        for field in list(evidence):
            with self.subTest(field=field):
                invalid = dict(evidence)
                del invalid[field]

                with self.assertRaises(
                    EvidenceValidationError
                ):
                    self.axis.verify_evidence(
                        invalid
                    )

    # --------------------------------------------------------
    # 05. Invalid identifiers
    # --------------------------------------------------------

    def test_05_invalid_identifiers_rejected(self):
        for field in (
            "evidence_id",
            "event_id",
            "source_id",
        ):
            for value in ("", None, 123):
                with self.subTest(
                    field=field,
                    value=value,
                ):
                    evidence = self.make_evidence()
                    evidence[field] = value

                    with self.assertRaises(
                        EvidenceValidationError
                    ):
                        self.axis.verify_evidence(
                            evidence
                        )

    # --------------------------------------------------------
    # 06. Unknown source rejection
    # --------------------------------------------------------

    def test_06_untrusted_source_rejected(self):
        evidence = self.make_evidence(
            source_id="unknown-sensor"
        )

        with self.assertRaises(
            UntrustedSourceError
        ):
            self.axis.verify_evidence(
                evidence
            )

    # --------------------------------------------------------
    # 07. Payload tampering rejection
    # --------------------------------------------------------

    def test_07_modified_payload_rejected(self):
        evidence = self.make_evidence()

        evidence["payload"]["severity"] = "critical"

        with self.assertRaises(
            EvidenceValidationError
        ):
            self.axis.verify_evidence(
                evidence
            )

    # --------------------------------------------------------
    # 08. Invalid digest format
    # --------------------------------------------------------

    def test_08_invalid_digest_format_rejected(self):
        invalid_digests = [
            "",
            "abc",
            "0" * 63,
            "G" * 64,
            "Z" * 64,
            None,
            123,
        ]

        for digest in invalid_digests:
            with self.subTest(digest=digest):
                evidence = self.make_evidence()
                evidence["payload_digest"] = digest

                with self.assertRaises(
                    EvidenceValidationError
                ):
                    self.axis.verify_evidence(
                        evidence
                    )

    # --------------------------------------------------------
    # 09. Unknown event rejection
    # --------------------------------------------------------

    def test_09_unknown_event_rejected(self):
        evidence = self.make_evidence(
            event_id="event-unknown"
        )

        with self.assertRaises(
            EvidenceBindingError
        ):
            self.axis.verify_evidence(
                evidence
            )

    # --------------------------------------------------------
    # 10. Duplicate evidence identifier
    # --------------------------------------------------------

    def test_10_duplicate_evidence_rejected(self):
        evidence = self.make_evidence()

        self.axis.verify_evidence(
            evidence
        )

        with self.assertRaises(
            EvidenceConflictError
        ):
            self.axis.verify_evidence(
                evidence
            )

    # --------------------------------------------------------
    # 11. Conflicting evidence identifier
    # --------------------------------------------------------

    def test_11_conflicting_evidence_rejected(self):
        first = self.make_evidence()

        self.axis.verify_evidence(
            first
        )

        second = self.make_evidence(
            payload={
                "event_type": "different_event",
                "severity": "low",
            }
        )

        with self.assertRaises(
            EvidenceConflictError
        ):
            self.axis.verify_evidence(
                second
            )

    # --------------------------------------------------------
    # 12. Verified real operation
    # --------------------------------------------------------

    def test_12_verified_real_operation_allowed(self):
        receipt = self.axis.verify_evidence(
            self.make_evidence()
        )

        for operation in (
            "analyze",
            "record",
            "propose",
        ):
            with self.subTest(operation=operation):
                result = (
                    self.axis.execute_real_verified(
                        self.real,
                        operation,
                        receipt_id=receipt.receipt_id,
                        evidence_id=receipt.evidence_id,
                        event_id=receipt.event_id,
                    )
                )

                self.assertTrue(result)

    # --------------------------------------------------------
    # 13. Unknown receipt rejection
    # --------------------------------------------------------

    def test_13_unknown_receipt_rejected(self):
        with self.assertRaises(
            AuthorityError
        ):
            self.axis.execute_real_verified(
                self.real,
                "analyze",
                receipt_id="receipt-forged",
            )

    # --------------------------------------------------------
    # 14. Receipt binding mismatch
    # --------------------------------------------------------

    def test_14_receipt_binding_mismatch(self):
        receipt = self.axis.verify_evidence(
            self.make_evidence()
        )

        with self.assertRaises(
            AuthorityError
        ):
            self.axis.execute_real_verified(
                self.real,
                "analyze",
                receipt_id=receipt.receipt_id,
                evidence_id="different-evidence",
            )

        with self.assertRaises(
            AuthorityError
        ):
            self.axis.execute_real_verified(
                self.real,
                "analyze",
                receipt_id=receipt.receipt_id,
                event_id="different-event",
            )

    # --------------------------------------------------------
    # 15. Forged receipt object rejection
    # --------------------------------------------------------

    def test_15_forged_receipt_rejected(self):
        receipt = self.axis.verify_evidence(
            self.make_evidence()
        )

        forged = replace(
            receipt,
            receipt_id="receipt-attacker",
        )

        with self.assertRaises(
            AuthorityError
        ):
            self.axis.execute_real_verified(
                self.real,
                "analyze",
                receipt_id=forged.receipt_id,
            )

        self.assertTrue(
            self.axis.execute_real_verified(
                self.real,
                "analyze",
                receipt_id=receipt.receipt_id,
            )
        )

    # --------------------------------------------------------
    # 16. Virtual-to-real escalation rejection
    # --------------------------------------------------------

    def test_16_virtual_cannot_execute_real(self):
        receipt = self.axis.verify_evidence(
            self.make_evidence()
        )

        with self.assertRaises(
            AuthorityError
        ):
            self.axis.execute_real_verified(
                self.virtual,
                "analyze",
                receipt_id=receipt.receipt_id,
            )

    # --------------------------------------------------------
    # 17. Forbidden real operation rejection
    # --------------------------------------------------------

    def test_17_forbidden_real_operation(self):
        receipt = self.axis.verify_evidence(
            self.make_evidence()
        )

        for operation in (
            "delete",
            "deploy",
            "execute",
            "modify_policy",
        ):
            with self.subTest(operation=operation):
                with self.assertRaises(
                    AuthorityError
                ):
                    self.axis.execute_real_verified(
                        self.real,
                        operation,
                        receipt_id=receipt.receipt_id,
                    )

    # --------------------------------------------------------
    # 18. Legacy verified=True bypass rejection
    # --------------------------------------------------------

    def test_18_legacy_verification_bypass_denied(self):
        with self.assertRaises(
            AuthorityError
        ):
            self.axis.execute_real(
                self.real,
                "analyze",
                verified=True,
            )

        with self.assertRaises(
            AuthorityError
        ):
            self.axis.execute_real(
                self.real,
                "record",
                verified=False,
            )

    # --------------------------------------------------------
    # 19. Receipt invalidation after neutralization
    # --------------------------------------------------------

    def test_19_stale_receipt_rejected(self):
        receipt = self.axis.verify_evidence(
            self.make_evidence()
        )

        self.axis.neutralize(
            "simulated emergency"
        )

        self.assertEqual(
            self.axis.mode,
            Mode.ZERO_NEUTRAL,
        )

        recovered = self.axis.recover(
            safety_verified=True,
            human_approved=True,
        )

        self.assertTrue(recovered)

        new_real = self.axis.issue_token(
            "real-2",
            Role.REAL,
        )

        with self.assertRaises(
            AuthorityError
        ):
            self.axis.execute_real_verified(
                new_real,
                "analyze",
                receipt_id=receipt.receipt_id,
            )

    # --------------------------------------------------------
    # 20. Verification blocked in neutral mode
    # --------------------------------------------------------

    def test_20_verification_blocked_when_neutral(self):
        self.axis.neutralize(
            "verification shutdown"
        )

        with self.assertRaises(
            AuthorityError
        ):
            self.axis.verify_evidence(
                self.make_evidence()
            )

    # --------------------------------------------------------
    # 21. Snapshot isolation of verified payload
    # --------------------------------------------------------

    def test_21_evidence_snapshot_is_preserved(self):
        evidence = self.make_evidence()

        original = copy.deepcopy(
            evidence
        )

        receipt = self.axis.verify_evidence(
            evidence
        )

        evidence["payload"]["severity"] = "critical"

        stored = self.axis._evidence_records[
            receipt.evidence_id
        ]

        self.assertEqual(
            stored.payload,
            original["payload"],
        )

        self.assertEqual(
            stored.payload_digest,
            original["payload_digest"],
        )

    # --------------------------------------------------------
    # 22. Internal receipt alteration detection
    # --------------------------------------------------------

    def test_22_altered_registered_receipt_rejected(self):
        receipt = self.axis.verify_evidence(
            self.make_evidence()
        )

        altered = replace(
            receipt,
            payload_digest="0" * 64,
        )

        # Deliberate internal-state mutation for testing.
        # This is not a supported public API.
        self.axis._receipts[
            receipt.receipt_id
        ] = altered

        with self.assertRaises(
            AuthorityError
        ):
            self.axis.execute_real_verified(
                self.real,
                "analyze",
                receipt_id=receipt.receipt_id,
            )

    # --------------------------------------------------------
    # 23. Event window reset invalidates event binding
    # --------------------------------------------------------

    def test_23_event_window_reset(self):
        self.axis.reset_virtual_load()

        with self.assertRaises(
            EvidenceBindingError
        ):
            self.axis.verify_evidence(
                self.make_evidence()
            )

    # --------------------------------------------------------
    # 24. Verifier callback failure is fail-closed
    # --------------------------------------------------------

    def test_24_verifier_failure_does_not_issue_receipt(self):
        def failing_event_lookup(event_id):
            raise RuntimeError(
                "simulated verifier failure"
            )

        verifier = EvidenceVerifier(
            verifier_id="test-verifier",
            trusted_sources=frozenset(
                {"sensor-alpha"}
            ),
            event_lookup=failing_event_lookup,
            evidence_lookup=lambda evidence_id: None,
        )

        with self.assertRaises(
            EvidenceVerificationError
        ):
            verifier.verify(
                self.make_evidence(),
                generation=0,
            )

    # --------------------------------------------------------
    # 25. Audit consistency after rejected verification
    # --------------------------------------------------------

    def test_25_rejection_is_audited(self):
        evidence = self.make_evidence(
            source_id="unregistered-source"
        )

        with self.assertRaises(
            UntrustedSourceError
        ):
            self.axis.verify_evidence(
                evidence
            )

        actions = [
            record["action"]
            for record in self.axis.audit.records
        ]

        self.assertIn(
            "evidence_verification_denied",
            actions,
        )

        self.assertTrue(
            self.axis.audit.verify()
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
