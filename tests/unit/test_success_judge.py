import unittest

from core.domain.simulation_result import SimulationResult, YearlyProjection
from core.domain.value_objects import Money
from core.simulation.montecarlo.success_judge import is_successful


def _projection(year: int, unallocated_surplus: int) -> YearlyProjection:
    return YearlyProjection(
        year=year,
        age_self=36,
        gross_income=Money.zero(),
        pension_income=Money.zero(),
        income_tax=Money.zero(),
        resident_tax=Money.zero(),
        social_insurance=Money.zero(),
        net_income=Money.zero(),
        total_expense=Money.zero(),
        net_cashflow=Money.zero(),
        account_balances={"unallocated_surplus": Money.of(unallocated_surplus)},
        networth=Money.zero(),
    )


class IsSuccessfulTest(unittest.TestCase):
    def test_success_when_never_negative(self) -> None:
        trial = SimulationResult(yearly_projections=[_projection(2026, 100), _projection(2027, 0)])
        self.assertTrue(is_successful(trial))

    def test_failure_when_negative_in_any_year(self) -> None:
        trial = SimulationResult(
            yearly_projections=[_projection(2026, 100), _projection(2027, -1), _projection(2028, 500)]
        )
        self.assertFalse(is_successful(trial))


if __name__ == "__main__":
    unittest.main()
