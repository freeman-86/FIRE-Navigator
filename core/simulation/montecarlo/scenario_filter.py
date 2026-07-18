from __future__ import annotations

from core.domain.simulation_result import SimulationResult


def filter_by_milestone_achieved(
    trials: list[SimulationResult], milestone_id: str, achieved: bool = True
) -> list[SimulationResult]:
    """「マイルストーン到達がachievedの通りだった試行のみ」に絞り込む。"""

    return [
        trial
        for trial in trials
        if any(outcome.milestone_id == milestone_id and outcome.achieved == achieved for outcome in trial.milestone_outcomes)
    ]


def filter_by_milestone_achieved_before_year(trials: list[SimulationResult], milestone_id: str, year: int) -> list[SimulationResult]:
    """「マイルストーン到達がyear年より前だった試行のみ」に絞り込む。"""

    return [
        trial
        for trial in trials
        if any(
            outcome.milestone_id == milestone_id and outcome.achieved and outcome.achieved_year is not None and outcome.achieved_year < year
            for outcome in trial.milestone_outcomes
        )
    ]
