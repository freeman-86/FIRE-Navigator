from __future__ import annotations

from core.domain.tax_config import IncomeTaxRules
from core.domain.value_objects import Money


def calculate_employment_income_deduction(gross_income: Money, rules: IncomeTaxRules) -> Money:
    """給与所得控除。区分ごとに base_amount + 収入金額×rate（rate=0の区分は base_amount を固定額として使う）。"""

    income = gross_income if not gross_income.is_negative else Money.zero()
    for bracket in rules.employment_income_deduction_brackets:
        if bracket.upper_bound is None or income <= bracket.upper_bound:
            if bracket.rate.value == 0:
                return bracket.base_amount
            return bracket.rate.apply_to(income) + bracket.base_amount
    raise ValueError("給与所得控除テーブルに該当する区分が見つかりません")


def calculate_taxable_income(
    gross_income: Money,
    rules: IncomeTaxRules,
    apply_spouse_deduction: bool,
    additional_deduction: Money = Money.zero(),
) -> Money:
    """additional_deductionは、iDeCo/企業型DC拠出額等の小規模企業共済等掛金控除に相当する。"""

    employment_deduction = calculate_employment_income_deduction(gross_income, rules)
    total_deduction = employment_deduction + rules.basic_deduction + additional_deduction
    if apply_spouse_deduction:
        total_deduction = total_deduction + rules.spouse_deduction

    taxable_income = gross_income - total_deduction
    return taxable_income if not taxable_income.is_negative else Money.zero()


def calculate_income_tax(taxable_income: Money, rules: IncomeTaxRules) -> Money:
    """累進課税。各ブラケットの幅に該当税率を掛けて積み上げる（速算表の控除額方式と数学的に等価）。"""

    income = taxable_income if not taxable_income.is_negative else Money.zero()

    tax = Money.zero()
    lower_bound = Money.zero()
    for bracket in rules.brackets:
        upper_bound = bracket.upper_bound
        bracket_top = income if upper_bound is None or upper_bound > income else upper_bound

        bracket_income = bracket_top - lower_bound
        if bracket_income.is_negative:
            bracket_income = Money.zero()
        tax = tax + bracket.rate.apply_to(bracket_income)

        if upper_bound is None or income <= upper_bound:
            break
        lower_bound = upper_bound

    return tax
