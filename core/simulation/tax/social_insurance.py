from __future__ import annotations

from core.domain.tax_config import SocialInsuranceRules
from core.domain.value_objects import Money


def calculate_social_insurance(gross_income: Money, rules: SocialInsuranceRules) -> Money:
    """健康保険・厚生年金・雇用保険の合算料率を年収に掛けるだけのMVP簡略化（標準報酬月額表・上限は非対応）。"""

    income = gross_income if not gross_income.is_negative else Money.zero()
    combined_rate = rules.health_insurance_rate + rules.pension_insurance_rate + rules.employment_insurance_rate
    return combined_rate.apply_to(income)
