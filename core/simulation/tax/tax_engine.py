from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

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


def calculate_tax(
    employment_income: Money,
    pension_income: Money,
    tax_config: TaxConfig,
    has_spouse: bool,
    rules: TaxRules,
    additional_deduction: Money = Money.zero(),
    is_65_or_older: bool = False,
    prior_year_employment_income: Optional[Money] = None,
    prior_year_pension_income: Optional[Money] = None,
) -> TaxCalculationResult:
    """employment_income(給与等)とpension_income(公的年金等)を、それぞれの控除を適用してから
    合算して課税所得を計算する。is_65_or_olderは公的年金等控除の速算表選択に使う（その年12月31日
    現在の年齢で判定するのが実際の制度）。社会保険料は年金受給者には課さないため、
    employment_incomeのみを対象に計算する。

    住民税(resident_tax)は「前年の所得」に基づいて課税される実際の制度を反映し、
    prior_year_employment_income/prior_year_pension_income（省略時はemployment_income/
    pension_incomeそのもの＝シミュレーション最初の年や、この区別を追跡しない呼び出し元向けの
    フォールバック）から計算した課税所得を使う。所得税・社会保険料は制度通り当年の所得に
    基づいたままにする。

    控除の前提（配偶者控除の有無・65歳以上判定・additional_deduction＝iDeCo拠出額等）は
    厳密には前年時点のものと異なりうるが、当年と同じ値を流用する近似とする（年ごとに個別
    追跡するコストに対して得られる精度向上が小さいため）。
    """

    total_income = employment_income + pension_income
    apply_spouse_deduction = has_spouse and bool(tax_config.deduction_settings.get("spouse_deduction", False))
    taxable_income = calculate_taxable_income(
        employment_income, pension_income, rules.income_tax, is_65_or_older, apply_spouse_deduction, additional_deduction
    )

    prior_employment_income = (
        prior_year_employment_income if prior_year_employment_income is not None else employment_income
    )
    prior_pension_income = prior_year_pension_income if prior_year_pension_income is not None else pension_income
    prior_year_total_income = prior_employment_income + prior_pension_income
    prior_year_taxable_income = calculate_taxable_income(
        prior_employment_income,
        prior_pension_income,
        rules.income_tax,
        is_65_or_older,
        apply_spouse_deduction,
        additional_deduction,
    )

    income_tax = calculate_income_tax(taxable_income, rules.income_tax)
    resident_tax = calculate_resident_tax(prior_year_taxable_income, prior_year_total_income, rules.resident_tax)
    social_insurance = calculate_social_insurance(employment_income, rules.social_insurance)

    total_tax = income_tax + resident_tax + social_insurance
    net_income = total_income - total_tax

    return TaxCalculationResult(
        income_tax=income_tax,
        resident_tax=resident_tax,
        social_insurance=social_insurance,
        net_income=net_income,
    )
