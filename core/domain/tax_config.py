from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from core.domain.user import Prefecture
from core.domain.value_objects import Money, Rate


@dataclass
class TaxConfig:
    residence: Prefecture
    deduction_settings: dict[str, Any] = field(default_factory=dict)
    tax_year_config_ref: str = ""


@dataclass
class IncomeTaxBracket:
    upper_bound: Optional[Money]
    rate: Rate


@dataclass
class EmploymentIncomeDeductionBracket:
    upper_bound: Optional[Money]
    rate: Rate
    base_amount: Money


@dataclass
class IncomeTaxRules:
    brackets: list[IncomeTaxBracket]
    employment_income_deduction_brackets: list[EmploymentIncomeDeductionBracket]
    basic_deduction: Money
    spouse_deduction: Money


@dataclass
class ResidentTaxRules:
    flat_rate: Rate
    per_capita_levy: Money


@dataclass
class SocialInsuranceRules:
    health_insurance_rate: Rate
    pension_insurance_rate: Rate
    employment_insurance_rate: Rate


@dataclass
class CapitalGainsTaxRules:
    """課税口座(TAXABLE)からの取り崩し時、平均取得原価方式で算出した譲渡益に課税する税率。

    NISA等の非課税口座、iDeCo等その他口座の出口課税(退職所得控除等)は対象外
    （ギャップ分析5.2で確定した範囲）。
    """

    rate: Rate


@dataclass
class TaxRules:
    income_tax: IncomeTaxRules
    resident_tax: ResidentTaxRules
    social_insurance: SocialInsuranceRules
    capital_gains: CapitalGainsTaxRules
