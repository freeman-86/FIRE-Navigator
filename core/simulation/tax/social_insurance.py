from __future__ import annotations

from typing import Optional

from core.domain.tax_config import SocialInsuranceRules
from core.domain.value_objects import Money


def calculate_social_insurance(gross_income: Money, rules: SocialInsuranceRules) -> Money:
    """健康保険・厚生年金・雇用保険の合算料率を年収に掛けるMVP簡略化（標準報酬月額の等級表そのものは
    非対応）。健康保険・厚生年金は標準報酬月額に上限があるため、rulesに上限が設定されていれば
    その金額を超える収入には保険料をかけない（雇用保険には上限がないため常に全額に対して計算する）。
    """

    income = gross_income if not gross_income.is_negative else Money.zero()
    health_insurance = rules.health_insurance_rate.apply_to(_capped(income, rules.health_insurance_cap))
    pension_insurance = rules.pension_insurance_rate.apply_to(_capped(income, rules.pension_insurance_cap))
    employment_insurance = rules.employment_insurance_rate.apply_to(income)
    return health_insurance + pension_insurance + employment_insurance


def _capped(income: Money, cap: Optional[Money]) -> Money:
    if cap is not None and income > cap:
        return cap
    return income
