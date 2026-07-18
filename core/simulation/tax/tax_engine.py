from __future__ import annotations

from dataclasses import dataclass

from core.domain.tax_config import TaxConfig, TaxRules
from core.domain.value_objects import Money
from core.simulation.tax.income_tax import calculate_income_tax, calculate_taxable_income
from core.simulation.tax.resident_tax import calculate_resident_tax
from core.simulation.tax.social_insurance import calculate_social_insurance


@dataclass
class TaxCalculationResult:
    income_tax: Money
    resident_tax: Money
    social_insurance: Money
    net_income: Money


def calculate_tax(gross_income: Money, tax_config: TaxConfig, has_spouse: bool, rules: TaxRules) -> TaxCalculationResult:
    apply_spouse_deduction = has_spouse and bool(tax_config.deduction_settings.get("spouse_deduction", False))
    taxable_income = calculate_taxable_income(gross_income, rules.income_tax, apply_spouse_deduction)

    income_tax = calculate_income_tax(taxable_income, rules.income_tax)
    resident_tax = calculate_resident_tax(taxable_income, rules.resident_tax)
    social_insurance = calculate_social_insurance(gross_income, rules.social_insurance)

    total_tax = income_tax + resident_tax + social_insurance
    net_income = gross_income - total_tax

    return TaxCalculationResult(
        income_tax=income_tax,
        resident_tax=resident_tax,
        social_insurance=social_insurance,
        net_income=net_income,
    )
