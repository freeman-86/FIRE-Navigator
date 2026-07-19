import unittest

from core.domain.tax_config import SocialInsuranceRules, TaxConfig
from core.domain.user import Prefecture
from core.domain.value_objects import Money, Rate
from core.simulation.tax.income_tax import (
    calculate_employment_income_deduction,
    calculate_income_tax,
    calculate_taxable_income,
)
from core.simulation.tax.resident_tax import calculate_resident_tax
from core.simulation.tax.social_insurance import calculate_social_insurance
from core.simulation.tax.tax_engine import calculate_tax
from repositories.config_repository import load_tax_rules


class IncomeTaxTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = load_tax_rules().income_tax

    def test_employment_income_deduction_middle_bracket(self) -> None:
        # 3,600,001~6,600,000円: 収入金額×20%+440,000円
        deduction = calculate_employment_income_deduction(Money.of(6_000_000), self.rules)
        self.assertEqual(deduction, Money.of(1_640_000))

    def test_employment_income_deduction_lower_flat_bracket(self) -> None:
        deduction = calculate_employment_income_deduction(Money.of(1_000_000), self.rules)
        self.assertEqual(deduction, Money.of(550_000))

    def test_employment_income_deduction_upper_cap(self) -> None:
        deduction = calculate_employment_income_deduction(Money.of(20_000_000), self.rules)
        self.assertEqual(deduction, Money.of(1_950_000))

    def test_taxable_income_subtracts_basic_and_employment_deduction(self) -> None:
        # 6,000,000 - (給与所得控除1,640,000 + 基礎控除480,000) = 3,880,000
        taxable_income = calculate_taxable_income(
            Money.of(6_000_000), Money.zero(), self.rules, is_65_or_older=False, apply_spouse_deduction=False
        )
        self.assertEqual(taxable_income, Money.of(3_880_000))

    def test_taxable_income_with_spouse_deduction(self) -> None:
        taxable_income = calculate_taxable_income(
            Money.of(6_000_000), Money.zero(), self.rules, is_65_or_older=False, apply_spouse_deduction=True
        )
        self.assertEqual(taxable_income, Money.of(3_500_000))

    def test_taxable_income_never_negative(self) -> None:
        taxable_income = calculate_taxable_income(
            Money.of(500_000), Money.zero(), self.rules, is_65_or_older=False, apply_spouse_deduction=False
        )
        self.assertEqual(taxable_income, Money.zero())

    def test_pension_income_uses_pension_deduction_table_not_employment_table(self) -> None:
        # 公的年金等収入3,000,000円(65歳未満): 控除は3,000,000×25%+275,000=1,025,000
        # (給与所得控除の場合は3,000,000×30%+80,000=980,000で異なる値になる)
        taxable_income = calculate_taxable_income(
            Money.zero(), Money.of(3_000_000), self.rules, is_65_or_older=False, apply_spouse_deduction=False
        )
        # 3,000,000 - 1,025,000(公的年金等控除) - 480,000(基礎控除) = 1,495,000
        self.assertEqual(taxable_income, Money.of(1_495_000))

    def test_pension_deduction_is_more_generous_at_65_or_older(self) -> None:
        # 65歳以上は同じ収入でも控除額が大きい(最低保障110万円 vs 65歳未満の60万円)ため、
        # 課税所得(under_65)の方が大きくなる
        under_65 = calculate_taxable_income(
            Money.zero(), Money.of(2_000_000), self.rules, is_65_or_older=False, apply_spouse_deduction=False
        )
        over_65 = calculate_taxable_income(
            Money.zero(), Money.of(2_000_000), self.rules, is_65_or_older=True, apply_spouse_deduction=False
        )
        self.assertGreater(under_65, over_65)

    def test_progressive_income_tax_matches_hand_calculation(self) -> None:
        # 3,880,000円 -> 1,950,000*5% + (3,300,000-1,950,000)*10% + (3,880,000-3,300,000)*20%
        # = 97,500 + 135,000 + 116,000 = 348,500
        tax = calculate_income_tax(Money.of(3_880_000), self.rules)
        self.assertEqual(tax, Money.of(348_500))

    def test_progressive_income_tax_within_first_bracket_only(self) -> None:
        tax = calculate_income_tax(Money.of(1_000_000), self.rules)
        self.assertEqual(tax, Money.of(50_000))

    def test_progressive_income_tax_zero_for_zero_income(self) -> None:
        self.assertEqual(calculate_income_tax(Money.zero(), self.rules), Money.zero())


class ResidentTaxTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = load_tax_rules().resident_tax

    def test_flat_rate_plus_per_capita_levy(self) -> None:
        tax = calculate_resident_tax(Money.of(3_880_000), Money.of(6_000_000), self.rules)
        self.assertEqual(tax, Money.of(393_000))

    def test_per_capita_levy_still_applies_when_deductions_zero_out_taxable_income(self) -> None:
        # 収入はあるが控除の結果taxable_incomeが0になった場合、均等割(5,000円)のみ課税される
        tax = calculate_resident_tax(Money.zero(), Money.of(500_000), self.rules)
        self.assertEqual(tax, Money.of(5_000))

    def test_zero_when_no_income_at_all(self) -> None:
        self.assertEqual(calculate_resident_tax(Money.zero(), Money.zero(), self.rules), Money.zero())


class SocialInsuranceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = load_tax_rules().social_insurance

    def test_combined_rate_applied_to_gross_income(self) -> None:
        insurance = calculate_social_insurance(Money.of(6_000_000), self.rules)
        self.assertEqual(insurance, Money.of(885_000))

    def test_health_and_pension_insurance_are_capped_but_employment_insurance_is_not(self) -> None:
        rules = SocialInsuranceRules(
            health_insurance_rate=Rate.of("0.05"),
            pension_insurance_rate=Rate.of("0.0915"),
            employment_insurance_rate=Rate.of("0.006"),
            health_insurance_cap=Money.of(16_680_000),
            pension_insurance_cap=Money.of(7_800_000),
        )
        # 健康保険は上限16,680,000円、厚生年金は上限7,800,000円で頭打ちになる。雇用保険は上限なし。
        insurance = calculate_social_insurance(Money.of(20_000_000), rules)
        expected = (
            Money.of(16_680_000) * Rate.of("0.05")
            + Money.of(7_800_000) * Rate.of("0.0915")
            + Money.of(20_000_000) * Rate.of("0.006")
        )
        self.assertEqual(insurance, expected)

    def test_no_cap_configured_behaves_as_before(self) -> None:
        rules = SocialInsuranceRules(
            health_insurance_rate=Rate.of("0.05"),
            pension_insurance_rate=Rate.of("0.0915"),
            employment_insurance_rate=Rate.of("0.006"),
        )
        insurance = calculate_social_insurance(Money.of(20_000_000), rules)
        self.assertEqual(insurance, Money.of(20_000_000) * Rate.of("0.1475"))


class TaxEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = load_tax_rules()

    def test_calculate_tax_matches_component_calculations(self) -> None:
        tax_config = TaxConfig(residence=Prefecture.TOKYO, deduction_settings={"spouse_deduction": True})
        result = calculate_tax(Money.of(6_000_000), Money.zero(), tax_config, has_spouse=True, rules=self.rules)

        self.assertEqual(result.income_tax, Money.of(272_500))
        self.assertEqual(result.resident_tax, Money.of(355_000))
        self.assertEqual(result.social_insurance, Money.of(885_000))
        self.assertEqual(result.net_income, Money.of(4_487_500))

    def test_spouse_deduction_not_applied_without_flag(self) -> None:
        tax_config = TaxConfig(residence=Prefecture.TOKYO, deduction_settings={})
        result = calculate_tax(Money.of(6_000_000), Money.zero(), tax_config, has_spouse=True, rules=self.rules)

        self.assertEqual(result.income_tax, Money.of(348_500))

    def test_no_income_results_in_zero_tax_and_zero_net_income(self) -> None:
        tax_config = TaxConfig(residence=Prefecture.TOKYO)
        result = calculate_tax(Money.zero(), Money.zero(), tax_config, has_spouse=False, rules=self.rules)

        self.assertEqual(result.income_tax, Money.zero())
        self.assertEqual(result.resident_tax, Money.zero())
        self.assertEqual(result.social_insurance, Money.zero())
        self.assertEqual(result.net_income, Money.zero())

    def test_pension_income_is_taxed_but_excluded_from_social_insurance(self) -> None:
        tax_config = TaxConfig(residence=Prefecture.TOKYO)
        with_pension = calculate_tax(Money.zero(), Money.of(2_000_000), tax_config, has_spouse=False, rules=self.rules)
        without_pension = calculate_tax(Money.zero(), Money.zero(), tax_config, has_spouse=False, rules=self.rules)

        self.assertGreater(with_pension.income_tax, without_pension.income_tax)
        self.assertEqual(with_pension.social_insurance, Money.zero())
        self.assertEqual(with_pension.social_insurance, without_pension.social_insurance)


if __name__ == "__main__":
    unittest.main()
