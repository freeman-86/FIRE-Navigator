import unittest

from core.domain.pension import ClaimTiming, ClaimTimingType, Pension, PensionEntitlement, PensionRules
from core.domain.value_objects import Money, Rate
from core.simulation.pension.pension_engine import calculate_pension_income


def _pension(claim_age: int, timing_type: ClaimTimingType = ClaimTimingType.STANDARD) -> Pension:
    return Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.of(780_000)),
        employee_pension=PensionEntitlement(estimate_annual=Money.of(1_200_000)),
        claim_timing=ClaimTiming(timing_type=timing_type, age=claim_age),
    )


def _rules() -> PensionRules:
    return PensionRules(
        standard_claim_age=65,
        earliest_claim_age=60,
        latest_claim_age=75,
        early_reduction_rate_per_month=Rate.of("0.004"),
        deferred_increase_rate_per_month=Rate.of("0.007"),
    )


class CalculatePensionIncomeTest(unittest.TestCase):
    def test_zero_before_claim_age(self) -> None:
        income = calculate_pension_income(64, _pension(65), _rules())
        self.assertEqual(income, Money.zero())

    def test_standard_claim_age_no_adjustment(self) -> None:
        income = calculate_pension_income(65, _pension(65), _rules())
        self.assertEqual(income, Money.of(1_980_000))

    def test_early_claim_reduces_income(self) -> None:
        # 60歳受給: 標準65歳より60ヶ月早い -> 60x0.4%=24%減額 -> 1,980,000x0.76=1,504,800
        income = calculate_pension_income(60, _pension(60, ClaimTimingType.EARLY), _rules())
        self.assertEqual(income, Money.of(1_504_800))

    def test_deferred_claim_increases_income(self) -> None:
        # 75歳受給: 標準65歳より120ヶ月遅い -> 120x0.7%=84%増額 -> 1,980,000x1.84=3,643,200
        income = calculate_pension_income(75, _pension(75, ClaimTimingType.DEFERRED), _rules())
        self.assertEqual(income, Money.of(3_643_200))

    def test_adjustment_stays_fixed_after_claim_age_passes(self) -> None:
        pension = _pension(60, ClaimTimingType.EARLY)
        rules = _rules()
        income_at_60 = calculate_pension_income(60, pension, rules)
        income_at_70 = calculate_pension_income(70, pension, rules)
        self.assertEqual(income_at_60, income_at_70)


if __name__ == "__main__":
    unittest.main()
