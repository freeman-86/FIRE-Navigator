import unittest

from core.domain.simulation_result import MilestoneOutcome, SimulationResult
from core.simulation.montecarlo.scenario_filter import (
    filter_by_milestone_achieved,
    filter_by_milestone_achieved_before_year,
)


def _trial(milestone_id: str, achieved: bool, achieved_year=None) -> SimulationResult:
    return SimulationResult(
        milestone_outcomes=[MilestoneOutcome(milestone_id=milestone_id, achieved=achieved, achieved_year=achieved_year)]
    )


class FilterByMilestoneAchievedTest(unittest.TestCase):
    def test_keeps_only_achieved_trials(self) -> None:
        trials = [_trial("m1", True), _trial("m1", False)]
        filtered = filter_by_milestone_achieved(trials, "m1", achieved=True)
        self.assertEqual(len(filtered), 1)

    def test_keeps_only_trials_achieved_before_year(self) -> None:
        trials = [
            _trial("m1", True, achieved_year=2050),
            _trial("m1", True, achieved_year=2060),
            _trial("m1", False),
        ]
        filtered = filter_by_milestone_achieved_before_year(trials, "m1", 2055)
        self.assertEqual(len(filtered), 1)


if __name__ == "__main__":
    unittest.main()
