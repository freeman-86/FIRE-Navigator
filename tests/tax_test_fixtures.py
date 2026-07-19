from core.domain.tax_config import (
    CapitalGainsTaxRules,
    EmploymentIncomeDeductionBracket,
    IncomeTaxRules,
    ResidentTaxRules,
    SocialInsuranceRules,
    TaxRules,
)
from core.domain.value_objects import Money, Rate


def zero_tax_rules() -> TaxRules:
    """税金の影響を排除して他のロジック(成長・余剰計算等)だけを検証したいテスト用のフィクスチャ。"""

    return TaxRules(
        income_tax=IncomeTaxRules(
            brackets=[],
            employment_income_deduction_brackets=[
                EmploymentIncomeDeductionBracket(upper_bound=None, rate=Rate.zero(), base_amount=Money.zero())
            ],
            pension_deduction_brackets_under_65=[
                EmploymentIncomeDeductionBracket(upper_bound=None, rate=Rate.zero(), base_amount=Money.zero())
            ],
            pension_deduction_brackets_65_or_older=[
                EmploymentIncomeDeductionBracket(upper_bound=None, rate=Rate.zero(), base_amount=Money.zero())
            ],
            basic_deduction=Money.zero(),
            spouse_deduction=Money.zero(),
        ),
        resident_tax=ResidentTaxRules(flat_rate=Rate.zero(), per_capita_levy=Money.zero()),
        social_insurance=SocialInsuranceRules(
            health_insurance_rate=Rate.zero(),
            pension_insurance_rate=Rate.zero(),
            employment_insurance_rate=Rate.zero(),
        ),
        capital_gains=CapitalGainsTaxRules(rate=Rate.zero()),
    )
