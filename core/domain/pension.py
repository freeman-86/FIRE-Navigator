from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.domain.value_objects import Money, Rate


class ClaimTimingType(str, Enum):
    EARLY = "early"
    STANDARD = "standard"
    DEFERRED = "deferred"


@dataclass
class ClaimTiming:
    timing_type: ClaimTimingType
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
