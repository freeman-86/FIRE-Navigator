import unittest

from adapters.local.local_data_adapter import _build_allocation_policy
from core.domain.errors import SchemaValidationError
from core.domain.value_objects import Rate

_REGISTRY = {"equity_sp500": "米国株式(S&P500)", "bond_us_treasury": "米国債"}


class BuildAllocationPolicyTest(unittest.TestCase):
    def test_missing_section_returns_none(self) -> None:
        self.assertIsNone(_build_allocation_policy({}))

    def test_explicit_null_returns_none(self) -> None:
        self.assertIsNone(_build_allocation_policy({"allocation_policy": None}))

    def test_groups_weights_by_age_and_sorts_targets(self) -> None:
        data = {
            "allocation_policy": {
                "targets": [
                    {"age": 60, "weights": {"equity_sp500": "0.4", "bond_us_treasury": "0.6"}},
                    {"age": 30, "weights": {"equity_sp500": "0.8", "bond_us_treasury": "0.2"}},
                ]
            }
        }

        policy = _build_allocation_policy(data, asset_class_registry=_REGISTRY)

        self.assertEqual([target.age for target in policy.targets], [30, 60])
        self.assertEqual(policy.targets[0].weights, {"equity_sp500": Rate.of("0.8"), "bond_us_treasury": Rate.of("0.2")})

    def test_unknown_asset_class_in_weights_raises_schema_validation_error(self) -> None:
        data = {"allocation_policy": {"targets": [{"age": 30, "weights": {"gold": "1.0"}}]}}

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_allocation_policy(data, asset_class_registry=_REGISTRY)
        self.assertEqual(ctx.exception.field_path, "allocation_policy.targets[0].weights")

    def test_missing_age_raises_schema_validation_error(self) -> None:
        data = {"allocation_policy": {"targets": [{"weights": {"equity_sp500": "1.0"}}]}}

        with self.assertRaises(SchemaValidationError) as ctx:
            _build_allocation_policy(data, asset_class_registry=_REGISTRY)
        self.assertEqual(ctx.exception.field_path, "allocation_policy.targets[0].age")


if __name__ == "__main__":
    unittest.main()
