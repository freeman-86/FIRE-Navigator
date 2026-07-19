from __future__ import annotations

from core.domain.tax_config import ResidentTaxRules
from core.domain.value_objects import Money


def calculate_resident_tax(taxable_income: Money, total_income: Money, rules: ResidentTaxRules) -> Money:
    """所得割(flat_rate) + 均等割(per_capita_levy)。

    均等割は、収入が全くない場合(total_income=0)は非課税とするが、収入はあるが各種控除の結果
    taxable_incomeが0になった場合は課税する（実際の制度と同様）。所得割はtaxable_incomeが
    0の場合はかからない。実際の均等割の非課税限度額（自治体・扶養人数により異なる）を厳密に
    再現するものではないMVP簡略化で、収入の有無のみで判定する。
    """

    if total_income.is_negative or total_income == Money.zero():
        return Money.zero()

    has_taxable_income = not (taxable_income.is_negative or taxable_income == Money.zero())
    flat_portion = rules.flat_rate.apply_to(taxable_income) if has_taxable_income else Money.zero()
    return flat_portion + rules.per_capita_levy
