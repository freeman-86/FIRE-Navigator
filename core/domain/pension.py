from __future__ import annotations

from dataclasses import dataclass

from core.domain.value_objects import Money, Rate


@dataclass
class ClaimTiming:
    """年金の受給開始年齢。繰上げ/繰下げによる増減率は年齢だけから自動的に決まる
    （pension_engine.calculate_pension_income()がage vs PensionRules.standard_claim_ageで判定する）
    ため、種別（早期/標準/繰下げ）を別途保持する必要はない。"""

    age: int


@dataclass
class PensionEntitlement:
    estimate_annual: Money


@dataclass
class Pension:
    national_pension: PensionEntitlement
    employee_pension: PensionEntitlement
    claim_timing: ClaimTiming


@dataclass
class PensionRules:
    """繰上げ/繰下げ受給による増減率テーブル（pension.yaml由来）。"""

    standard_claim_age: int
    earliest_claim_age: int
    latest_claim_age: int
    early_reduction_rate_per_month: Rate
    deferred_increase_rate_per_month: Rate
