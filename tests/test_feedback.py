"""Unit tests for VRTA v0.3 feedback controller.

35 deterministic tests.
Python 3.11+.
Standard library only.

Covers configuration, observations, overload,
hysteresis, recovery, zero-neutral priority,
history, and controller boundaries.

These are behavioral tests, not production
control-system or security certification.
"""

import math
import unittest

from dataclasses import FrozenInstanceError

from feedback import (
    FeedbackConfig,
    FeedbackConfigurationError,
    FeedbackController,
    FeedbackDecision,
    FeedbackMode,
    FeedbackObservationError,
    FeedbackReason,
    FeedbackStateError,
    LoadObservation,
)


class TestFeedbackConfiguration(unittest.TestCase):
    """Configuration validation tests."""

    # 01
    def test_01_default_configuration(self):
        config = FeedbackConfig()

        self.assertEqual(config.degrade_threshold, 0.80)
        self.assertEqual(config.recover_threshold, 0.40)
        self.assertEqual(config.stable_windows_required, 3)
        self.assertEqual(config.window_size, 3)

    # 02
    def test_02_valid_custom_configuration(self):
        config = FeedbackConfig(
            degrade_threshold=0.90,
            recover_threshold=0.30,
            stable_windows_required=4,
            window_size=5,
        )

        self.assertEqual(config.degrade_threshold, 0.90)
        self.assertEqual(config.recover_threshold, 0.30)
        self.assertEqual(config.stable_windows_required, 4)
        self.assertEqual(config.window_size, 5)

    # 03
    def test_03_invalid_threshold_order(self):
        cases = [
            (0.30, 0.60),
            (0.50, 0.50),
            (0.00, 0.00),
        ]

        for degrade, recover in cases:
            with self.subTest(
                degrade=degrade,
                recover=recover,
            ):
                with self.assertRaises(
                    FeedbackConfigurationError
                ):
                    FeedbackConfig(
                        degrade_threshold=degrade,
                        recover_threshold=recover,
                    )

    # 04
    def test_04_out_of_range_thresholds(self):
        cases = [
            {"degrade_threshold": -0.1},
            {"degrade_threshold": 1.1},
            {"recover_threshold": -0.1},
            {"recover_threshold": 1.1},
        ]

        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(
                    FeedbackConfigurationError
                ):
                    FeedbackConfig(**kwargs)

    # 05
    def test_05_nonfinite_thresholds_rejected(self):
        values = [
            math.nan,
            math.inf,
            -math.inf,
        ]

        for value in values:
            for field in (
                "degrade_threshold",
                "recover_threshold",
            ):
                with self.subTest(
                    field=field,
                    value=value,
                ):
                    with self.assertRaises(
                        FeedbackConfigurationError
                    ):
                        FeedbackConfig(**{field: value})

    # 06
    def test_06_boolean_thresholds_rejected(self):
        for field in (
            "degrade_threshold",
            "recover_threshold",
        ):
            with self.subTest(field=field):
                with self.assertRaises(
                    FeedbackConfigurationError
                ):
                    FeedbackConfig(**{field: True})

    # 07
    def test_07_invalid_integer_configuration(self):
        cases = [
            {"stable_windows_required": 0},
            {"stable_windows_required": 1},
            {"stable_windows_required": -1},
            {"stable_windows_required": True},
            {"stable_windows_required": 2.5},
            {"window_size": 0},
            {"window_size": -1},
            {"window_size": False},
            {"window_size": 2.5},
        ]

        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(
                    FeedbackConfigurationError
                ):
                    FeedbackConfig(**kwargs)


class TestLoadObservations(unittest.TestCase):
    """Observation parsing and validation tests."""

    # 08
    def test_08_valid_observation(self):
        observation = LoadObservation(
            window_id=1,
            virtual_load=0.35,
            real_load=0.42,
        )

        self.assertEqual(observation.window_id, 1)
        self.assertEqual(observation.virtual_load, 0.35)
        self.assertEqual(observation.real_load, 0.42)

    # 09
    def test_09_boundary_load_values(self):
        for load in (0.0, 1.0):
            with self.subTest(load=load):
                observation = LoadObservation(
                    window_id=0,
                    virtual_load=load,
                    real_load=load,
                )

                self.assertEqual(
                    observation.virtual_load,
                    load,
                )

    # 10
    def test_10_invalid_load_values(self):
        values = [
            -0.1,
            1.1,
            None,
            "0.5",
            True,
            False,
            math.nan,
            math.inf,
            -math.inf,
        ]

        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(
                    FeedbackObservationError
                ):
                    LoadObservation(
                        window_id=1,
                        virtual_load=value,
                        real_load=0.3,
                    )

                with self.assertRaises(
                    FeedbackObservationError
                ):
                    LoadObservation(
                        window_id=1,
                        virtual_load=0.3,
                        real_load=value,
                    )

    # 11
    def test_11_invalid_window_identifier(self):
        values = [
            -1,
            1.5,
            "1",
            None,
            True,
            False,
        ]

        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(
                    FeedbackObservationError
                ):
                    LoadObservation(
                        window_id=value,
                        virtual_load=0.2,
                        real_load=0.3,
                    )

    # 12
    def test_12_missing_observation_fields(self):
        base = {
            "window_id": 1,
            "virtual_load": 0.2,
            "real_load": 0.3,
        }

        for field in base:
            with self.subTest(field=field):
                value = dict(base)
                del value[field]

                with self.assertRaises(
                    FeedbackObservationError
                ):
                    LoadObservation.from_mapping(value)

    # 13
    def test_13_duplicate_window_rejected(self):
        controller = FeedbackController()

        controller.evaluate(
            {
                "window_id": 1,
                "virtual_load": 0.2,
                "real_load": 0.3,
            },
            current_mode=FeedbackMode.NORMAL,
        )

        with self.assertRaises(
            FeedbackObservationError
        ):
            controller.evaluate(
                {
                    "window_id": 1,
                    "virtual_load": 0.3,
                    "real_load": 0.4,
                },
                current_mode=FeedbackMode.NORMAL,
            )

        self.assertEqual(len(controller.history), 1)

    # 14
    def test_14_out_of_order_window_rejected(self):
        controller = FeedbackController()

        controller.evaluate(
            {
                "window_id": 5,
                "virtual_load": 0.2,
                "real_load": 0.2,
            },
            current_mode="normal",
        )

        with self.assertRaises(
            FeedbackObservationError
        ):
            controller.evaluate(
                {
                    "window_id": 4,
                    "virtual_load": 0.2,
                    "real_load": 0.2,
                },
                current_mode="normal",
            )

        self.assertEqual(controller.last_window_id, 5)


class TestOverloadControl(unittest.TestCase):
    """Overload and degradation tests."""

    def setUp(self):
        self.controller = FeedbackController()

    def evaluate(
        self,
        window_id,
        virtual,
        real,
        mode=FeedbackMode.NORMAL,
    ):
        return self.controller.evaluate(
            LoadObservation(
                window_id=window_id,
                virtual_load=virtual,
                real_load=real,
            ),
            current_mode=mode,
        )

    # 15
    def test_15_normal_load_retains_normal(self):
        decision = self.evaluate(
            1, 0.30, 0.35
        )

        self.assertEqual(
            decision.recommended_mode,
            FeedbackMode.NORMAL,
        )
        self.assertEqual(
            decision.reason,
            FeedbackReason.NORMAL_STABLE,
        )
        self.assertFalse(decision.transition_recommended)

    # 16
    def test_16_virtual_overload(self):
        decision = self.evaluate(
            1, 0.90, 0.20
        )

        self.assertTrue(decision.virtual_overloaded)
        self.assertFalse(decision.real_overloaded)
        self.assertTrue(decision.overloaded)

        self.assertEqual(
            decision.reason,
            FeedbackReason.VIRTUAL_OVERLOAD,
        )
        self.assertEqual(
            decision.recommended_mode,
            FeedbackMode.DEGRADED,
        )

    # 17
    def test_17_real_overload(self):
        decision = self.evaluate(
            1, 0.20, 0.90
        )

        self.assertFalse(decision.virtual_overloaded)
        self.assertTrue(decision.real_overloaded)

        self.assertEqual(
            decision.reason,
            FeedbackReason.REAL_OVERLOAD,
        )

    # 18
    def test_18_simultaneous_overload(self):
        decision = self.evaluate(
            1, 0.95, 0.91
        )

        self.assertTrue(decision.virtual_overloaded)
        self.assertTrue(decision.real_overloaded)

        self.assertEqual(
            decision.reason,
            FeedbackReason.SIMULTANEOUS_OVERLOAD,
        )

    # 19
    def test_19_exact_degradation_threshold(self):
        for virtual, real in (
            (0.80, 0.20),
            (0.20, 0.80),
        ):
            controller = FeedbackController()

            decision = controller.evaluate(
                LoadObservation(
                    window_id=1,
                    virtual_load=virtual,
                    real_load=real,
                ),
                current_mode="normal",
            )

            self.assertEqual(
                decision.recommended_mode,
                FeedbackMode.DEGRADED,
            )

    # 20
    def test_20_average_cannot_hide_overload(self):
        decision = self.evaluate(
            1, 0.95, 0.05
        )

        self.assertEqual(
            (0.95 + 0.05) / 2,
            0.50,
        )

        self.assertTrue(decision.virtual_overloaded)
        self.assertEqual(
            decision.recommended_mode,
            FeedbackMode.DEGRADED,
        )


class TestHysteresisRecovery(unittest.TestCase):
    """Hysteresis and recovery stability tests."""

    def setUp(self):
        self.controller = FeedbackController()

    def evaluate(
        self,
        window_id,
        virtual,
        real,
        mode=FeedbackMode.DEGRADED,
    ):
        return self.controller.evaluate(
            {
                "window_id": window_id,
                "virtual_load": virtual,
                "real_load": real,
            },
            current_mode=mode,
        )

    # 21
    def test_21_hysteresis_holds_degraded(self):
        decision = self.evaluate(
            1, 0.60, 0.50
        )

        self.assertEqual(
            decision.recommended_mode,
            FeedbackMode.DEGRADED,
        )
        self.assertEqual(
            decision.reason,
            FeedbackReason.HYSTERESIS_HOLD,
        )
        self.assertEqual(decision.stable_count, 0)

    # 22
    def test_22_recovery_pending_first_window(self):
        decision = self.evaluate(
            1, 0.30, 0.35
        )

        self.assertEqual(
            decision.reason,
            FeedbackReason.RECOVERY_PENDING,
        )
        self.assertEqual(decision.stable_count, 1)
        self.assertEqual(
            decision.recommended_mode,
            FeedbackMode.DEGRADED,
        )

    # 23
    def test_23_recovery_requires_three_windows(self):
        first = self.evaluate(1, 0.30, 0.35)
        second = self.evaluate(2, 0.28, 0.31)
        third = self.evaluate(3, 0.25, 0.29)

        self.assertEqual(
            first.recommended_mode,
            FeedbackMode.DEGRADED,
        )
        self.assertEqual(
            second.recommended_mode,
            FeedbackMode.DEGRADED,
        )
        self.assertEqual(
            third.recommended_mode,
            FeedbackMode.NORMAL,
        )

        self.assertEqual(
            third.reason,
            FeedbackReason.RECOVERY_ELIGIBLE,
        )

        self.assertEqual(self.controller.stable_count, 0)

    # 24
    def test_24_exact_recovery_threshold(self):
        for window_id in range(1, 4):
            decision = self.evaluate(
                window_id,
                0.40,
                0.40,
            )

        self.assertEqual(
            decision.reason,
            FeedbackReason.RECOVERY_ELIGIBLE,
        )

    # 25
    def test_25_unstable_window_resets_progress(self):
        self.evaluate(1, 0.20, 0.25)
        self.evaluate(2, 0.30, 0.35)

        unstable = self.evaluate(
            3, 0.50, 0.30
        )

        self.assertEqual(unstable.stable_count, 0)
        self.assertEqual(
            unstable.reason,
            FeedbackReason.HYSTERESIS_HOLD,
        )

        restarted = self.evaluate(
            4, 0.20, 0.20
        )

        self.assertEqual(restarted.stable_count, 1)
        self.assertEqual(
            restarted.recommended_mode,
            FeedbackMode.DEGRADED,
        )

    # 26
    def test_26_overload_resets_stability(self):
        self.evaluate(1, 0.20, 0.20)
        self.evaluate(2, 0.30, 0.30)

        decision = self.evaluate(
            3, 0.95, 0.20
        )

        self.assertEqual(decision.stable_count, 0)
        self.assertEqual(
            decision.reason,
            FeedbackReason.VIRTUAL_OVERLOAD,
        )

    # 27
    def test_27_invalid_input_preserves_progress(self):
        self.evaluate(1, 0.20, 0.20)

        before = self.controller.snapshot()

        with self.assertRaises(
            FeedbackObservationError
        ):
            self.evaluate(2, -0.5, 0.20)

        after = self.controller.snapshot()

        self.assertEqual(before, after)

        decision = self.evaluate(
            2, 0.20, 0.20
        )

        self.assertEqual(decision.stable_count, 2)


class TestFeedbackBoundaries(unittest.TestCase):
    """Zero-neutral and authority-separation tests."""

    # 28
    def test_28_zero_neutral_never_auto_recovers(self):
        controller = FeedbackController()

        for window_id in range(1, 6):
            decision = controller.evaluate(
                LoadObservation(
                    window_id=window_id,
                    virtual_load=0.0,
                    real_load=0.0,
                ),
                current_mode=FeedbackMode.ZERO_NEUTRAL,
            )

            self.assertEqual(
                decision.recommended_mode,
                FeedbackMode.ZERO_NEUTRAL,
            )

            self.assertEqual(
                decision.reason,
                FeedbackReason.ZERO_NEUTRAL_HOLD,
            )

        self.assertEqual(controller.stable_count, 0)

    # 29
    def test_29_unknown_mode_rejected(self):
        controller = FeedbackController()

        with self.assertRaises(FeedbackStateError):
            controller.evaluate(
                {
                    "window_id": 1,
                    "virtual_load": 0.2,
                    "real_load": 0.2,
                },
                current_mode="unrestricted",
            )

        self.assertEqual(len(controller.history), 0)

    # 30
    def test_30_decision_is_immutable(self):
        controller = FeedbackController()

        decision = controller.evaluate(
            LoadObservation(1, 0.9, 0.2),
            current_mode="normal",
        )

        with self.assertRaises(
            FrozenInstanceError
        ):
            decision.recommended_mode = FeedbackMode.NORMAL

    # 31
    def test_31_controller_does_not_mutate_axis(self):
        class SimulatedAxis:
            def __init__(self):
                self.mode = "normal"
                self.generation = 7
                self.tokens = {"real-1": "existing"}

        axis = SimulatedAxis()
        controller = FeedbackController()

        decision = controller.evaluate(
            LoadObservation(1, 0.95, 0.20),
            current_mode=axis.mode,
        )

        self.assertEqual(
            decision.recommended_mode,
            FeedbackMode.DEGRADED,
        )

        # Recommendation has no direct authority effects.
        self.assertEqual(axis.mode, "normal")
        self.assertEqual(axis.generation, 7)
        self.assertEqual(
            axis.tokens,
            {"real-1": "existing"},
        )


class TestFeedbackHistory(unittest.TestCase):
    """History, diagnostics, and reset tests."""

    # 32
    def test_32_sliding_window_capacity(self):
        controller = FeedbackController(
            FeedbackConfig(window_size=3)
        )

        for window_id in range(1, 6):
            controller.evaluate(
                LoadObservation(
                    window_id,
                    0.2,
                    0.3,
                ),
                current_mode="normal",
            )

        self.assertEqual(len(controller.history), 3)
        self.assertEqual(
            [x.window_id for x in controller.history],
            [3, 4, 5],
        )

    # 33
    def test_33_snapshot_diagnostics(self):
        controller = FeedbackController()

        controller.evaluate(
            LoadObservation(1, 0.9, 0.2),
            current_mode="normal",
        )

        snapshot = controller.snapshot()

        self.assertEqual(snapshot["last_window_id"], 1)
        self.assertEqual(snapshot["history_size"], 1)
        self.assertEqual(snapshot["window_capacity"], 3)

        self.assertEqual(
            snapshot["last_decision"]["reason"],
            "virtual_overload",
        )

    # 34
    def test_34_reset_clears_controller_state(self):
        controller = FeedbackController()

        controller.evaluate(
            LoadObservation(1, 0.2, 0.2),
            current_mode="degraded",
        )

        controller.reset()

        self.assertEqual(controller.history, ())
        self.assertEqual(controller.stable_count, 0)
        self.assertIsNone(controller.last_window_id)
        self.assertIsNone(controller.last_decision)

        decision = controller.evaluate(
            LoadObservation(1, 0.9, 0.2),
            current_mode="normal",
        )

        self.assertEqual(
            decision.reason,
            FeedbackReason.VIRTUAL_OVERLOAD,
        )

    # 35
    def test_35_decision_serialization(self):
        controller = FeedbackController()

        decision = controller.evaluate(
            LoadObservation(1, 0.9, 0.3),
            current_mode="normal",
        )

        value = decision.to_dict()

        self.assertEqual(value["window_id"], 1)
        self.assertEqual(value["current_mode"], "normal")
        self.assertEqual(
            value["recommended_mode"],
            "degraded",
        )
        self.assertEqual(
            value["reason"],
            "virtual_overload",
        )
        self.assertTrue(
            value["transition_recommended"]
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
