"""Five-Element Authority Matrix tests for VRTA v0.2.

Python 3.11+.
Standard library only.

Tests cover:
- Five-element role definitions
- Allowed and forbidden restriction relations
- Element authority binding
- Restriction activation and enforcement
- Administrative restriction release
- Zero-neutralization
- Authority generation invalidation
- Restriction persistence after recovery
- Audit-chain integrity

This is behavioral validation, not a production
security certification.
"""

import unittest

from axis import (
    AuthorityError,
    Mode,
    Role,
    TransitionAxisV2,
    ValidationError,
)

from evidence import build_evidence

from five_elements import (
    ADVISORY_ACTIONS,
    ALLOWED_RELATIONS,
    RESTRICTIVE_ACTIONS,
    Element,
    FiveElementMatrix,
    RestrictionAction,
    RestrictionDeniedError,
    RestrictionRequest,
    RestrictionValidationError,
    build_restriction_request,
)


class TestFiveElementMatrix(unittest.TestCase):
    """Tests for the independent restriction matrix."""

    def setUp(self):
        self.matrix = FiveElementMatrix()

    def make_request(
        self,
        source="wood",
        target="earth",
        action="request_review",
        request_id="req-001",
        reason="Simulated control review",
    ):
        return {
            "request_id": request_id,
            "source_element": source,
            "target_element": target,
            "action": action,
            "reason": reason,
        }

    # --------------------------------------------------------
    # 01. Five functional elements
    # --------------------------------------------------------

    def test_01_five_elements_defined(self):
        self.assertEqual(
            set(Element),
            {
                Element.WOOD,
                Element.FIRE,
                Element.EARTH,
                Element.METAL,
                Element.WATER,
            },
        )

        self.assertEqual(len(Element), 5)

    # --------------------------------------------------------
    # 02. Five allowed relations
    # --------------------------------------------------------

    def test_02_allowed_relations(self):
        expected = {
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

        self.assertEqual(
            ALLOWED_RELATIONS,
            expected,
        )

        self.assertEqual(len(ALLOWED_RELATIONS), 5)

    # --------------------------------------------------------
    # 03. Every permitted relation
    # --------------------------------------------------------

    def test_03_all_permitted_relations_pass(self):
        for index, (
            relation,
            action,
        ) in enumerate(
            ALLOWED_RELATIONS.items(),
            start=1,
        ):
            source, target = relation

            with self.subTest(
                source=source,
                target=target,
            ):
                request = self.make_request(
                    source=source.value,
                    target=target.value,
                    action=action.value,
                    request_id=f"allowed-{index}",
                )

                decision = self.matrix.validate(
                    request
                )

                self.assertTrue(
                    decision.permitted
                )

                self.assertEqual(
                    decision.action,
                    action,
                )

    # --------------------------------------------------------
    # 04. Forbidden relationships
    # --------------------------------------------------------

    def test_04_forbidden_relations_rejected(self):
        forbidden = [
            ("wood", "fire", "request_review"),
            ("fire", "water", "suspend_analysis"),
            ("earth", "metal", "flag_inconsistency"),
            ("metal", "fire", "restrict_intake"),
            ("water", "wood", "suspend_analysis"),
        ]

        for source, target, action in forbidden:
            with self.subTest(
                source=source,
                target=target,
            ):
                with self.assertRaises(
                    RestrictionDeniedError
                ):
                    self.matrix.validate(
                        self.make_request(
                            source=source,
                            target=target,
                            action=action,
                        )
                    )

    # --------------------------------------------------------
    # 05. Wrong action for valid relation
    # --------------------------------------------------------

    def test_05_wrong_action_rejected(self):
        request = self.make_request(
            source="wood",
            target="earth",
            action="restrict_intake",
        )

        with self.assertRaises(
            RestrictionDeniedError
        ):
            self.matrix.validate(request)

    # --------------------------------------------------------
    # 06. Unknown element
    # --------------------------------------------------------

    def test_06_unknown_element_rejected(self):
        for field in (
            "source_element",
            "target_element",
        ):
            request = self.make_request()
            request[field] = "unknown"

            with self.subTest(field=field):
                with self.assertRaises(
                    RestrictionValidationError
                ):
                    self.matrix.validate(request)

    # --------------------------------------------------------
    # 07. Unknown restriction action
    # --------------------------------------------------------

    def test_07_unknown_action_rejected(self):
        request = self.make_request(
            action="grant_unrestricted_access"
        )

        with self.assertRaises(
            RestrictionValidationError
        ):
            self.matrix.validate(request)

    # --------------------------------------------------------
    # 08. Missing fields
    # --------------------------------------------------------

    def test_08_missing_fields_rejected(self):
        required = (
            "request_id",
            "source_element",
            "target_element",
            "action",
            "reason",
        )

        for field in required:
            request = self.make_request()
            del request[field]

            with self.subTest(field=field):
                with self.assertRaises(
                    RestrictionValidationError
                ):
                    self.matrix.validate(request)

    # --------------------------------------------------------
    # 09. Empty identifiers and reasons
    # --------------------------------------------------------

    def test_09_empty_strings_rejected(self):
        for field in (
            "request_id",
            "reason",
        ):
            request = self.make_request()
            request[field] = " "

            with self.subTest(field=field):
                with self.assertRaises(
                    RestrictionValidationError
                ):
                    self.matrix.validate(request)

    # --------------------------------------------------------
    # 10. Advisory and restrictive categories
    # --------------------------------------------------------

    def test_10_action_categories(self):
        self.assertEqual(len(ADVISORY_ACTIONS), 3)
        self.assertEqual(len(RESTRICTIVE_ACTIONS), 2)

        self.assertTrue(
            ADVISORY_ACTIONS.isdisjoint(
                RESTRICTIVE_ACTIONS
            )
        )

        for action in ADVISORY_ACTIONS:
            self.assertTrue(
                self.matrix.is_advisory(action)
            )
            self.assertFalse(
                self.matrix.is_restrictive(action)
            )

        for action in RESTRICTIVE_ACTIONS:
            self.assertTrue(
                self.matrix.is_restrictive(action)
            )

    # --------------------------------------------------------
    # 11. Request normalization
    # --------------------------------------------------------

    def test_11_request_serialization(self):
        request = build_restriction_request(
            request_id="req-normalized",
            source_element=Element.WOOD,
            target_element=Element.EARTH,
            action=RestrictionAction.REQUEST_REVIEW,
            reason="Test normalization",
        )

        parsed = RestrictionRequest.from_mapping(
            request
        )

        self.assertEqual(
            parsed.source_element,
            Element.WOOD,
        )

        self.assertEqual(
            parsed.action,
            RestrictionAction.REQUEST_REVIEW,
        )

        self.assertEqual(
            parsed.to_dict(),
            request,
        )


class TestFiveElementAxisIntegration(unittest.TestCase):
    """Tests for restriction enforcement by TransitionAxisV2."""

    def setUp(self):
        self.admin = object()

        self.bindings = {
            "wood-1": Element.WOOD,
            "earth-1": Element.EARTH,
            "water-1": Element.WATER,
            "fire-1": Element.FIRE,
            "metal-1": Element.METAL,
            "water-2": Element.WATER,
            "metal-2": Element.METAL,
        }

        self.axis = TransitionAxisV2(
            virtual_limit=3,
            trusted_sources=frozenset(
                {"sensor-alpha"}
            ),
            element_bindings=self.bindings,
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

        self.element_tokens = {
            element: self.axis.issue_element_token(
                token_id
            )
            for element, token_id in [
                (Element.WOOD, "wood-1"),
                (Element.EARTH, "earth-1"),
                (Element.WATER, "water-1"),
                (Element.FIRE, "fire-1"),
                (Element.METAL, "metal-1"),
            ]
        }

    def make_request(
        self,
        source,
        target,
        action,
        request_id="req-001",
        reason="Simulated restriction",
    ):
        return build_restriction_request(
            request_id=request_id,
            source_element=source,
            target_element=target,
            action=action,
            reason=reason,
        )

    def create_verified_receipt(self):
        self.axis.receive_virtual(
            self.virtual,
            {"event_id": "event-001"},
        )

        evidence = build_evidence(
            evidence_id="evidence-001",
            event_id="event-001",
            source_id="sensor-alpha",
            payload={
                "event_type": "simulated_anomaly",
            },
        )

        return self.axis.verify_evidence(
            evidence
        )

    def activate_analysis_suspension(self):
        request = self.make_request(
            "water",
            "fire",
            "suspend_analysis",
            request_id="suspend-001",
        )

        return self.axis.request_restriction(
            self.element_tokens[Element.WATER],
            request,
        )

    def activate_intake_restriction(self):
        request = self.make_request(
            "metal",
            "wood",
            "restrict_intake",
            request_id="intake-001",
        )

        return self.axis.request_restriction(
            self.element_tokens[Element.METAL],
            request,
        )

    # --------------------------------------------------------
    # 12. Element token binding
    # --------------------------------------------------------

    def test_12_element_authority_binding(self):
        for element, token in self.element_tokens.items():
            with self.subTest(element=element):
                self.assertEqual(
                    token.element,
                    element,
                )

                self.assertEqual(
                    token.generation,
                    self.axis.generation,
                )

    # --------------------------------------------------------
    # 13. Unregistered element identity
    # --------------------------------------------------------

    def test_13_unregistered_element_denied(self):
        with self.assertRaises(
            AuthorityError
        ):
            self.axis.issue_element_token(
                "unknown-element"
            )

    # --------------------------------------------------------
    # 14. Duplicate element token
    # --------------------------------------------------------

    def test_14_duplicate_element_token_denied(self):
        with self.assertRaises(
            AuthorityError
        ):
            self.axis.issue_element_token(
                "wood-1"
            )

    # --------------------------------------------------------
    # 15. Forged source-element claim
    # --------------------------------------------------------

    def test_15_forged_source_claim_denied(self):
        request = self.make_request(
            "metal",
            "wood",
            "restrict_intake",
        )

        with self.assertRaises(
            AuthorityError
        ):
            self.axis.request_restriction(
                self.element_tokens[Element.WOOD],
                request,
            )

        self.assertFalse(
            self.axis.restriction_active(
                RestrictionAction.RESTRICT_INTAKE
            )
        )

    # --------------------------------------------------------
    # 16. Invalid relation through axis
    # --------------------------------------------------------

    def test_16_invalid_relation_denied(self):
        request = self.make_request(
            "wood",
            "fire",
            "request_review",
        )

        with self.assertRaises(
            RestrictionDeniedError
        ):
            self.axis.request_restriction(
                self.element_tokens[Element.WOOD],
                request,
            )

    # --------------------------------------------------------
    # 17. Advisory action has no restrictive effect
    # --------------------------------------------------------

    def test_17_advisory_action_no_enforcement(self):
        request = self.make_request(
            "wood",
            "earth",
            "request_review",
        )

        decision = self.axis.request_restriction(
            self.element_tokens[Element.WOOD],
            request,
        )

        self.assertTrue(decision.permitted)
        self.assertFalse(decision.restrictive)

        self.assertEqual(
            len(self.axis._active_restrictions),
            0,
        )

    # --------------------------------------------------------
    # 18. Analysis suspension activation
    # --------------------------------------------------------

    def test_18_analysis_suspension_activated(self):
        decision = self.activate_analysis_suspension()

        self.assertTrue(decision.permitted)
        self.assertTrue(decision.restrictive)

        self.assertTrue(
            self.axis.restriction_active(
                RestrictionAction.SUSPEND_ANALYSIS
            )
        )

    # --------------------------------------------------------
    # 19. Suspended analysis is denied
    # --------------------------------------------------------

    def test_19_suspended_analysis_denied(self):
        receipt = self.create_verified_receipt()

        self.activate_analysis_suspension()

        with self.assertRaises(
            AuthorityError
        ):
            self.axis.execute_real_verified(
                self.real,
                "analyze",
                receipt_id=receipt.receipt_id,
            )

        # Other allowlisted operations remain available.
        self.assertTrue(
            self.axis.execute_real_verified(
                self.real,
                "record",
                receipt_id=receipt.receipt_id,
            )
        )

    # --------------------------------------------------------
    # 20. Intake restriction activation
    # --------------------------------------------------------

    def test_20_intake_restriction_activated(self):
        self.activate_intake_restriction()

        self.assertTrue(
            self.axis.restriction_active(
                RestrictionAction.RESTRICT_INTAKE
            )
        )

        with self.assertRaises(
            AuthorityError
        ):
            self.axis.receive_virtual(
                self.virtual,
                {"event_id": "blocked-event"},
            )

        self.assertEqual(
            self.axis.virtual_load,
            0,
        )

    # --------------------------------------------------------
    # 21. Duplicate restriction request ID
    # --------------------------------------------------------

    def test_21_duplicate_request_rejected(self):
        request = self.make_request(
            "wood",
            "earth",
            "request_review",
            request_id="duplicate-001",
        )

        self.axis.request_restriction(
            self.element_tokens[Element.WOOD],
            request,
        )

        with self.assertRaises(
            AuthorityError
        ):
            self.axis.request_restriction(
                self.element_tokens[Element.WOOD],
                request,
            )

    # --------------------------------------------------------
    # 22. Unauthorized release
    # --------------------------------------------------------

    def test_22_unauthorized_release_denied(self):
        self.activate_analysis_suspension()

        with self.assertRaises(
            AuthorityError
        ):
            self.axis.release_restriction(
                administrator=object(),
                action=RestrictionAction.SUSPEND_ANALYSIS,
            )

        self.assertTrue(
            self.axis.restriction_active(
                RestrictionAction.SUSPEND_ANALYSIS
            )
        )

    # --------------------------------------------------------
    # 23. Administrative release
    # --------------------------------------------------------

    def test_23_administrative_release(self):
        receipt = self.create_verified_receipt()

        self.activate_analysis_suspension()

        released = self.axis.release_restriction(
            administrator=self.admin,
            action=RestrictionAction.SUSPEND_ANALYSIS,
        )

        self.assertTrue(released)

        self.assertFalse(
            self.axis.restriction_active(
                RestrictionAction.SUSPEND_ANALYSIS
            )
        )

        self.assertTrue(
            self.axis.execute_real_verified(
                self.real,
                "analyze",
                receipt_id=receipt.receipt_id,
            )
        )

    # --------------------------------------------------------
    # 24. Neutral mode blocks restriction release
    # --------------------------------------------------------

    def test_24_release_blocked_in_neutral_mode(self):
        self.activate_analysis_suspension()

        self.axis.neutralize(
            "simulated emergency"
        )

        with self.assertRaises(
            AuthorityError
        ):
            self.axis.release_restriction(
                administrator=self.admin,
                action=RestrictionAction.SUSPEND_ANALYSIS,
            )

    # --------------------------------------------------------
    # 25. Restrictions persist after recovery
    # --------------------------------------------------------

    def test_25_restriction_persists_after_recovery(self):
        self.activate_analysis_suspension()
        self.activate_intake_restriction()

        self.axis.neutralize(
            "simulated emergency"
        )

        recovered = self.axis.recover(
            safety_verified=True,
            human_approved=True,
        )

        self.assertTrue(recovered)
        self.assertEqual(
            self.axis.mode,
            Mode.NORMAL,
        )

        self.assertTrue(
            self.axis.restriction_active(
                RestrictionAction.SUSPEND_ANALYSIS
            )
        )

        self.assertTrue(
            self.axis.restriction_active(
                RestrictionAction.RESTRICT_INTAKE
            )
        )

    # --------------------------------------------------------
    # 26. Old element authority is invalidated
    # --------------------------------------------------------

    def test_26_stale_element_token_rejected(self):
        old_water = self.element_tokens[
            Element.WATER
        ]

        self.axis.neutralize(
            "authority generation rotation"
        )

        self.axis.recover(
            safety_verified=True,
            human_approved=True,
        )

        request = self.make_request(
            "water",
            "fire",
            "suspend_analysis",
            request_id="stale-001",
        )

        with self.assertRaises(
            AuthorityError
        ):
            self.axis.request_restriction(
                old_water,
                request,
            )

        new_water = self.axis.issue_element_token(
            "water-2"
        )

        decision = self.axis.request_restriction(
            new_water,
            request,
        )

        self.assertTrue(decision.permitted)

    # --------------------------------------------------------
    # 27. No element tokens issued during neutralization
    # --------------------------------------------------------

    def test_27_element_issuance_blocked_in_neutral(self):
        self.axis.neutralize(
            "emergency shutdown"
        )

        with self.assertRaises(
            AuthorityError
        ):
            self.axis.issue_element_token(
                "water-2"
            )

    # --------------------------------------------------------
    # 28. Recovery does not release restrictions
    # --------------------------------------------------------

    def test_28_recovery_does_not_auto_release(self):
        self.activate_intake_restriction()

        self.axis.neutralize(
            "emergency"
        )

        self.assertFalse(
            self.axis.recover(
                safety_verified=True,
                human_approved=False,
            )
        )

        self.assertTrue(
            self.axis.restriction_active(
                RestrictionAction.RESTRICT_INTAKE
            )
        )

        self.assertTrue(
            self.axis.recover(
                safety_verified=True,
                human_approved=True,
            )
        )

        new_virtual = self.axis.issue_token(
            "virtual-2",
            Role.VIRTUAL,
        )

        with self.assertRaises(
            AuthorityError
        ):
            self.axis.receive_virtual(
                new_virtual,
                {"event_id": "new-event"},
            )

    # --------------------------------------------------------
    # 29. Restriction decision is audited
    # --------------------------------------------------------

    def test_29_restriction_decision_audited(self):
        self.activate_analysis_suspension()

        actions = [
            record["action"]
            for record in self.axis.audit.records
        ]

        self.assertIn(
            "restriction_activated",
            actions,
        )

        self.assertTrue(
            self.axis.audit.verify()
        )

    # --------------------------------------------------------
    # 30. Rejected restriction is audited
    # --------------------------------------------------------

    def test_30_rejected_restriction_audited(self):
        request = self.make_request(
            "wood",
            "fire",
            "request_review",
        )

        with self.assertRaises(
            RestrictionDeniedError
        ):
            self.axis.request_restriction(
                self.element_tokens[Element.WOOD],
                request,
            )

        actions = [
            record["action"]
            for record in self.axis.audit.records
        ]

        self.assertIn(
            "restriction_denied",
            actions,
        )

        self.assertTrue(
            self.axis.audit.verify()
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
