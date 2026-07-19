from __future__ import annotations

from core.domain.tax_config import EmploymentIncomeDeductionBracket, IncomeTaxRules
from core.domain.value_objects import Money


def calculate_employment_income_deduction(gross_income: Money, rules: IncomeTaxRules) -> Money:
    """給与所得控除。区分ごとに base_amount + 収入金額×rate（rate=0の区分は base_amount を固定額として使う）。"""

    return _apply_deduction_brackets(gross_income, rules.employment_income_deduction_brackets)


def calculate_pension_income_deduction(pension_income: Money, is_65_or_older: bool, rules: IncomeTaxRules) -> Money:
    """公的年金等控除。年齢（その年12月31日現在、is_65_or_older）で使う速算表が異なる。"""

    brackets = (
        rules.pension_deduction_brackets_65_or_older if is_65_or_older else rules.pension_deduction_brackets_under_65
    )
    return _apply_deduction_brackets(pension_income, brackets)


def _apply_deduction_brackets(income: Money, brackets: list[EmploymentIncomeDeductionBracket]) -> Money:
    income = income if not income.is_negative else Money.zero()
    for bracket in brackets:
        if bracket.upper_bound is None or income <= bracket.upper_bound:
            if bracket.rate.value == 0:
                return bracket.base_amount
            return bracket.rate.apply_to(income) + bracket.base_amount
    raise ValueError("控除テーブルに該当する区分が見つかりません")


def calculate_taxable_income(
    employment_income: Money,
    pension_income: Money,
    rules: IncomeTaxRules,
    is_65_or_older: bool,
    apply_spouse_deduction: bool,
    additional_deduction: Money = Money.zero(),
) -> Money:
    """給与所得（収入-給与所得控除）と雑所得(公的年金等、収入-公的年金等控除)をそれぞれ算出して
    合算し、そこから基礎控除等（所得控除）を差し引く（実際の制度と同様、所得の種類ごとに
    控除してから合算する）。additional_deductionは、iDeCo/企業型DC拠出額等の
    小規模企業共済等掛金控除に相当する。
    """

    employment_deduction = calculate_employment_income_deduction(employment_income, rules)
    employment_income_amount = employment_income - employment_deduction
    if employment_income_amount.is_negative:
        employment_income_amount = Money.zero()

    pension_deduction = calculate_pension_income_deduction(pension_income, is_65_or_older, rules)
    pension_income_amount = pension_income - pension_deduction
    if pension_income_amount.is_negative:
        pension_income_amount = Money.zero()

    total_income = employment_income_amount + pension_income_amount
    total_deduction = rules.basic_deduction + additional_deduction
    if apply_spouse_deduction:
        total_deduction = total_deduction + rules.spouse_deduction

    taxable_income = total_income - total_deduction
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
