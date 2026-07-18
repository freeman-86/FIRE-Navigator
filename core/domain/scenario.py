from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from core.domain.milestone import Milestone, MilestoneType
from core.domain.plan import Plan
from core.domain.value_objects import EventCondition

SUPPORTED_OVERRIDE_KEYS = ("retirement_age",)


@dataclass
class Scenario:
    """Planに対する差分（overrides）を表す独立したAggregate。plan_id参照のみでPlan本体は持たない。"""

    scenario_id: str
    plan_id: str
    name: str
    overrides: dict[str, Any] = field(default_factory=dict)


def apply_scenario(base_plan: Plan, scenario: Scenario) -> Plan:
    """overridesを適用したbase_planの複製を返す。base_plan自体は変更しない。

    現時点でサポートするoverrideキーはretirement_ageのみ（YAGNI）。
    """

    if scenario.plan_id != base_plan.plan_id:
        raise ValueError(
            f"scenario.plan_id({scenario.plan_id}) が base_plan.plan_id({base_plan.plan_id}) と一致しません"
        )

    unknown_keys = set(scenario.overrides) - set(SUPPORTED_OVERRIDE_KEYS)
    if unknown_keys:
        raise ValueError(f"サポートしていないoverrideキーです: {sorted(unknown_keys)}")

    milestones = list(base_plan.milestones)
    if "retirement_age" in scenario.overrides:
        age = scenario.overrides["retirement_age"]
        milestones = [m for m in milestones if m.milestone_type != MilestoneType.RETIREMENT]
        milestones.append(
            Milestone(
                milestone_id=f"milestone_retirement_{scenario.scenario_id}",
                milestone_type=MilestoneType.RETIREMENT,
                trigger=EventCondition.at_age(age),
            )
        )

    return replace(base_plan, plan_id=f"{base_plan.plan_id}__{scenario.scenario_id}", milestones=milestones)
