from __future__ import annotations

from datetime import date

from core.domain.plan import Plan
from core.domain.simulation_result import MilestoneOutcome, YearlyProjection
from core.domain.value_objects import EventCondition, EventConditionType
from core.simulation.projection.event_conditions import resolve_condition_year


def evaluate_milestones(plan: Plan, yearly_projections: list[YearlyProjection]) -> list[MilestoneOutcome]:
    """各MilestoneのConditionalEvent(trigger)を年次シミュレーション結果に照らして到達判定する。

    age/date系の条件は計算期間内に該当年が含まれるかで判定する。
    networth_multiple_of_expense条件は年次ループの実績値（networth/total_expense）に対して動的に判定する。
    """

    if not yearly_projections:
        return []

    start_year = yearly_projections[0].year
    birth_date = plan.user.birth_date

    outcomes = []
    for milestone in plan.milestones:
        outcomes.append(_evaluate_trigger(milestone.milestone_id, milestone.trigger, yearly_projections, start_year, birth_date))
    return outcomes


def _evaluate_trigger(
    milestone_id: str,
    trigger: EventCondition,
    yearly_projections: list[YearlyProjection],
    start_year: int,
    birth_date: date,
) -> MilestoneOutcome:
    if trigger.condition_type == EventConditionType.NETWORTH_MULTIPLE_OF_EXPENSE:
        for projection in yearly_projections:
            threshold = projection.total_expense * trigger.multiple
            if projection.networth >= threshold:
                return MilestoneOutcome(milestone_id=milestone_id, achieved=True, achieved_year=projection.year)
        return MilestoneOutcome(milestone_id=milestone_id, achieved=False, achieved_year=None)

    target_year = resolve_condition_year(trigger, start_year, birth_date)
    projection_years = {projection.year for projection in yearly_projections}
    if target_year is not None and target_year in projection_years:
        return MilestoneOutcome(milestone_id=milestone_id, achieved=True, achieved_year=target_year)
    return MilestoneOutcome(milestone_id=milestone_id, achieved=False, achieved_year=None)
