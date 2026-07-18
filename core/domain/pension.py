from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.domain.value_objects import Money


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
