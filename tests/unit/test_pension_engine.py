import unittest

from core.domain.pension import ClaimTiming, Pension, PensionEntitlement, PensionRules
from core.domain.value_objects import Money, Rate
from core.simulation.pension.pension_engine import calculate_pension_income


def _pension(claim_age: int) -> Pension:
    return Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.of(780_000)),
        employee_pension=PensionEntitlement(estimate_annual=Money.of(1_200_000)),
        claim_timing=ClaimTiming(age=claim_age),
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
        income = calculate_pension_income(64, _pension(65), _rules(), Rate.zero(), estimate_reference_age=35)
        self.assertEqual(income, Money.zero())

    def test_standard_claim_age_no_adjustment_when_no_inflation(self) -> None:
        income = calculate_pension_income(65, _pension(65), _rules(), Rate.zero(), estimate_reference_age=35)
        self.assertEqual(income, Money.of(1_980_000))

    def test_early_claim_reduces_income(self) -> None:
        # 60歳受給: 標準65歳より60ヶ月早い -> 60x0.4%=24%減額 -> 1,980,000x0.76=1,504,800
        income = calculate_pension_income(
            60, _pension(60), _rules(), Rate.zero(), estimate_reference_age=35
        )
        self.assertEqual(income, Money.of(1_504_800))

    def test_deferred_claim_increases_income(self) -> None:
        # 75歳受給: 標準65歳より120ヶ月遅い -> 120x0.7%=84%増額 -> 1,980,000x1.84=3,643,200
        income = calculate_pension_income(
            75, _pension(75), _rules(), Rate.zero(), estimate_reference_age=35
        )
        self.assertEqual(income, Money.of(3_643_200))

    def test_pre_claim_inflation_compounds_estimate_to_claim_age(self) -> None:
        # 現在35歳・受給開始65歳（標準・調整なし）・インフレ率2% -> 見込み額を30年複利。
        # 1,980,000 x 1.02^30 = 3,586,268.28... -> Money丸めで3,586,268
        income = calculate_pension_income(
            65, _pension(65), _rules(), Rate.of("0.02"), estimate_reference_age=35
        )
        expected = Money.of(round(1_980_000 * (1.02**30)))
        self.assertEqual(income, expected)

    def test_no_pre_claim_inflation_when_plan_starts_at_or_after_claim_age(self) -> None:
        # プラン開始時点で既に受給開始年齢に達している場合、見込み額をそのまま基準額とする
        # （将来に向けた複利計算はしない）。
        income = calculate_pension_income(
            65, _pension(65), _rules(), Rate.of("0.02"), estimate_reference_age=70
        )
        self.assertEqual(income, Money.of(1_980_000))

    def test_post_claim_inflation_grows_income_year_by_year(self) -> None:
        # 受給開始後もインフレ率で毎年増え続ける（据え置きにしない）。
        rules = _rules()
        pension = _pension(65)
        income_at_65 = calculate_pension_income(65, pension, rules, Rate.of("0.02"), estimate_reference_age=65)
        income_at_70 = calculate_pension_income(70, pension, rules, Rate.of("0.02"), estimate_reference_age=65)

        self.assertEqual(income_at_65, Money.of(1_980_000))
        self.assertGreater(income_at_70, income_at_65)
        expected_at_70 = Money.of(round(1_980_000 * (1.02**5)))
        self.assertEqual(income_at_70, expected_at_70)

    def test_early_reduction_adjustment_is_applied_to_inflation_adjusted_base_then_stays_fixed(self) -> None:
        # 繰上げ/繰下げの調整率は「インフレ調整済みの受給開始時点の基準額」に対して1回だけ掛かり、
        # 以降は据え置き（その上に受給開始後のインフレだけが毎年重なる）。
        rules = _rules()
        pension = _pension(60)
        inflation_rate = Rate.of("0.02")

        # 現在35歳、受給開始60歳 -> 25年複利 -> 24%減額
        base_at_claim = 1_980_000 * (1.02**25) * 0.76
        income_at_60 = calculate_pension_income(60, pension, rules, inflation_rate, estimate_reference_age=35)
        self.assertEqual(income_at_60, Money.of(round(base_at_claim)))

        income_at_65 = calculate_pension_income(65, pension, rules, inflation_rate, estimate_reference_age=35)
        expected_at_65 = Money.of(round(base_at_claim * (1.02**5)))
        self.assertEqual(income_at_65, expected_at_65)


if __name__ == "__main__":
    unittest.main()
