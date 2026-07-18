from __future__ import annotations

from decimal import Decimal

from core.domain.pension import Pension, PensionRules
from core.domain.value_objects import Money


def calculate_pension_income(age: int, pension: Pension, rules: PensionRules) -> Money:
    """claim_timing.age到達後の年金収入。繰上げ/繰下げによる増減率は受給開始時点で固定され、
    その後の年齢が進んでも再計算されない（実際の制度と同様）。
    """

    if age < pension.claim_timing.age:
        return Money.zero()

    base = pension.national_pension.estimate_annual + pension.employee_pension.estimate_annual
    months_from_standard = (pension.claim_timing.age - rules.standard_claim_age) * 12

    if months_from_standard < 0:
        adjustment = Decimal(1) - rules.early_reduction_rate_per_month.value * Decimal(abs(months_from_standard))
    elif months_from_standard > 0:
        adjustment = Decimal(1) + rules.deferred_increase_rate_per_month.value * Decimal(months_from_standard)
    else:
        adjustment = Decimal(1)

    return base * adjustment
