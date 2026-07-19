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
    """pension_deduction_brackets_*は公的年金等控除の速算表（65歳未満/65歳以上で表が異なる）。
    「その年12月31日現在の年齢」で表を選ぶのが実際の制度（is_65_or_olderの判定基準）。
    公的年金等以外の所得が1,000万円を超える場合の控除縮小には対応しない（MVP簡略化）。
    """

    brackets: list[IncomeTaxBracket]
    employment_income_deduction_brackets: list[EmploymentIncomeDeductionBracket]
    pension_deduction_brackets_under_65: list[EmploymentIncomeDeductionBracket]
    pension_deduction_brackets_65_or_older: list[EmploymentIncomeDeductionBracket]
    basic_deduction: Money
    spouse_deduction: Money


@dataclass
class ResidentTaxRules:
    flat_rate: Rate
    per_capita_levy: Money


@dataclass
class SocialInsuranceRules:
    """健康保険・厚生年金保険は標準報酬月額に上限があるため、年収換算の上限
    (health_insurance_cap/pension_insurance_cap)を超える部分には保険料がかからない。
    雇用保険には上限がないため対応するcapフィールドはない。上限を指定しない場合(None)は
    従来通り上限なしで計算する。
    """

    health_insurance_rate: Rate
    pension_insurance_rate: Rate
    employment_insurance_rate: Rate
    health_insurance_cap: Optional[Money] = None
    pension_insurance_cap: Optional[Money] = None


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
