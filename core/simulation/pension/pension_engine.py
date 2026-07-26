from __future__ import annotations

from decimal import Decimal

from core.domain.pension import Pension, PensionRules
from core.domain.value_objects import Money, Rate


def calculate_pension_income(
    age: int,
    pension: Pension,
    rules: PensionRules,
    inflation_rate: Rate,
    estimate_reference_age: int,
) -> Money:
    """claim_timing.age到達後の年金収入。

    入力_プラン設定の国民年金見込額・厚生年金見込額は「見積もり時点（estimate_reference_age。
    通常はプラン開始時点の年齢）での見込み額」として扱う。実際の受給開始（claim_timing.age）まで
    年数が残っている場合、その年数分をinflation_rateで複利計算し、受給開始時点の基準額を求める
    （例: 現在35歳・受給開始65歳なら30年分複利。plan開始時点で既に受給開始年齢以降の場合は
    複利計算なし＝見込み額をそのまま基準額とする）。

    繰上げ/繰下げによる増減率（実際の制度と同様、受給開始時点で固定され、その後再計算されない）は、
    この受給開始時点の基準額に対して掛ける（インフレ調整の後、繰上げ/繰下げ調整の順）。

    受給開始後は、生活費等の他の項目と同様に年金額自体も毎年inflation_rateで増え続ける
    （据え置きだと他項目との間に不自然なギャップが生まれるため）。
    """

    if age < pension.claim_timing.age:
        return Money.zero()

    estimate = pension.national_pension.estimate_annual + pension.employee_pension.estimate_annual
    years_until_claim = max(pension.claim_timing.age - estimate_reference_age, 0)
    base_at_claim = _compound(estimate, inflation_rate, years_until_claim)

    months_from_standard = (pension.claim_timing.age - rules.standard_claim_age) * 12

    if months_from_standard < 0:
        adjustment = Decimal(1) - rules.early_reduction_rate_per_month.value * Decimal(abs(months_from_standard))
    elif months_from_standard > 0:
        adjustment = Decimal(1) + rules.deferred_increase_rate_per_month.value * Decimal(months_from_standard)
    else:
        adjustment = Decimal(1)

    amount_at_claim = base_at_claim * adjustment

    years_since_claim = age - pension.claim_timing.age
    return _compound(amount_at_claim, inflation_rate, years_since_claim)


def _compound(money: Money, rate: Rate, years: int) -> Money:
    factor = (Decimal(1) + rate.value) ** years
    return money * factor
