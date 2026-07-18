from __future__ import annotations

from core.domain.tax_config import ResidentTaxRules
from core.domain.value_objects import Money


def calculate_resident_tax(taxable_income: Money, rules: ResidentTaxRules) -> Money:
    """所得割(flat_rate) + 均等割(per_capita_levy)。taxable_incomeが0の場合は課税なしとするMVP簡略化。"""

    if taxable_income.is_negative or taxable_income == Money.zero():
        return Money.zero()
    return rules.flat_rate.apply_to(taxable_income) + rules.per_capita_levy
