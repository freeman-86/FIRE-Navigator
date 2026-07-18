import unittest

from core.domain.tax_config import TaxConfig
from core.domain.user import Prefecture
from core.domain.value_objects import Money
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
        taxable_income = calculate_taxable_income(Money.of(6_000_000), self.rules, apply_spouse_deduction=False)
        self.assertEqual(taxable_income, Money.of(3_880_000))

    def test_taxable_income_with_spouse_deduction(self) -> None:
        taxable_income = calculate_taxable_income(Money.of(6_000_000), self.rules, apply_spouse_deduction=True)
        self.assertEqual(taxable_income, Money.of(3_500_000))

    def test_taxable_income_never_negative(self) -> None:
        taxable_income = calculate_taxable_income(Money.of(500_000), self.rules, apply_spouse_deduction=False)
        self.assertEqual(taxable_income, Money.zero())

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
        tax = calculate_resident_tax(Money.of(3_880_000), self.rules)
        self.assertEqual(tax, Money.of(393_000))

    def test_zero_when_no_taxable_income(self) -> None:
        self.assertEqual(calculate_resident_tax(Money.zero(), self.rules), Money.zero())


class SocialInsuranceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = load_tax_rules().social_insurance

    def test_combined_rate_applied_to_gross_income(self) -> None:
        insurance = calculate_social_insurance(Money.of(6_000_000), self.rules)
        self.assertEqual(insurance, Money.of(885_000))


class TaxEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = load_tax_rules()

    def test_calculate_tax_matches_component_calculations(self) -> None:
        tax_config = TaxConfig(residence=Prefecture.TOKYO, deduction_settings={"spouse_deduction": True})
        result = calculate_tax(Money.of(6_000_000), tax_config, has_spouse=True, rules=self.rules)

        self.assertEqual(result.income_tax, Money.of(272_500))
        self.assertEqual(result.resident_tax, Money.of(355_000))
        self.assertEqual(result.social_insurance, Money.of(885_000))
        self.assertEqual(result.net_income, Money.of(4_487_500))

    def test_spouse_deduction_not_applied_without_flag(self) -> None:
        tax_config = TaxConfig(residence=Prefecture.TOKYO, deduction_settings={})
        result = calculate_tax(Money.of(6_000_000), tax_config, has_spouse=True, rules=self.rules)

        self.assertEqual(result.income_tax, Money.of(348_500))

    def test_no_income_results_in_zero_tax_and_zero_net_income(self) -> None:
        tax_config = TaxConfig(residence=Prefecture.TOKYO)
        result = calculate_tax(Money.zero(), tax_config, has_spouse=False, rules=self.rules)

        self.assertEqual(result.income_tax, Money.zero())
        self.assertEqual(result.resident_tax, Money.zero())
        self.assertEqual(result.social_insurance, Money.zero())
        self.assertEqual(result.net_income, Money.zero())


if __name__ == "__main__":
    unittest.main()
