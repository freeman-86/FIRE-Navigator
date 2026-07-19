import unittest

from core.domain.allocation import AllocationPolicy, AllocationTarget
from core.domain.value_objects import Rate


class WeightsForAgeTest(unittest.TestCase):
    def test_returns_empty_dict_when_no_targets(self) -> None:
        policy = AllocationPolicy(targets=[])
        self.assertEqual(policy.weights_for_age(40), {})

    def test_returns_empty_dict_when_age_is_before_first_target(self) -> None:
        policy = AllocationPolicy(targets=[AllocationTarget(age=30, weights={"equity_sp500": Rate.of("1.0")})])
        self.assertEqual(policy.weights_for_age(25), {})

    def test_uses_step_function_of_nearest_target_at_or_below_age(self) -> None:
        policy = AllocationPolicy(
            targets=[
                AllocationTarget(
                    age=20, weights={"equity_sp500": Rate.of("0.8"), "bond_us_treasury": Rate.of("0.2")}
                ),
                AllocationTarget(
                    age=60, weights={"equity_sp500": Rate.of("0.4"), "bond_us_treasury": Rate.of("0.6")}
                ),
            ]
        )

        self.assertEqual(policy.weights_for_age(20)["equity_sp500"], Rate.of("0.8"))
        self.assertEqual(policy.weights_for_age(59)["equity_sp500"], Rate.of("0.8"))
        self.assertEqual(policy.weights_for_age(60)["equity_sp500"], Rate.of("0.4"))
        self.assertEqual(policy.weights_for_age(80)["equity_sp500"], Rate.of("0.4"))


if __name__ == "__main__":
    unittest.main()
