from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.domain.value_objects import EventCondition


class MilestoneType(str, Enum):
    RETIREMENT = "retirement"
    FINANCIAL_INDEPENDENCE = "financial_independence"


@dataclass
class Milestone:
    milestone_id: str
    milestone_type: MilestoneType
    trigger: EventCondition
    parameters: dict[str, Any] = field(default_factory=dict)
