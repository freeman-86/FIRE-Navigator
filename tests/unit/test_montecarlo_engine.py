import unittest
from datetime import date

from core.domain.account import Account, AccountType, OwnerType
from core.domain.asset import Asset, AssetClass
from core.domain.holding import Holding
from core.domain.income import Income
from core.domain.pension import ClaimTiming, ClaimTimingType, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.tax_config import TaxConfig
from core.domain.user import Prefecture, User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from core.simulation.montecarlo.distribution import distributions_from_historical_dataset
from core.simulation.montecarlo.correlation_matrix import compute_correlation_matrix
from core.simulation.montecarlo.montecarlo_engine import run_montecarlo
from tests.market_data_test_fixtures import small_dataset
from tests.pension_test_fixtures import zero_pension_rules
from tests.portfolio_test_fixtures import empty_portfolio_rules, no_allocation_contribution_strategy
from tests.tax_test_fixtures import zero_tax_rules


def _plan() -> Plan:
    user = User(birth_date=date(1990, 4, 1), residence=Prefecture.TOKYO)
    pension = Pension(
        national_pension=PensionEntitlement(estimate_annual=Money.zero()),
        employee_pension=PensionEntitlement(estimate_annual=Money.zero()),
        claim_timing=ClaimTiming(timing_type=ClaimTimingType.STANDARD, age=65),
    )
    income = Income(
        income_id="income_001",
        source="salary",
        amount=Money.of(5_000_000),
        growth_rate=Rate.zero(),
        start_condition=EventCondition.plan_start(),
    )
    return Plan(
        plan_id="plan_test",
        name="テストプラン",
        user=user,
        start_condition=StartCondition(StartConditionType.FIXED_DATE, fixed_date=date(2026, 1, 1)),
        assumptions=Assumptions(inflation_rate=Rate.zero(), investment_growth_rate=Rate.from_percent(5)),
        accounts=[Account(account_id="acc_001", account_type=AccountType.TAXABLE, owner=OwnerType.SELF)],
        tax_config=TaxConfig(residence=Prefecture.TOKYO),
        pension=pension,
        withdrawal_strategy=WithdrawalStrategy(order=[AccountType.CASH]),
        contribution_strategy=no_allocation_contribution_strategy(),
        incomes=[income],
    )


def _portfolios() -> dict[str, Portfolio]:
    asset = Asset(asset_class=AssetClass.DOMESTIC_EQUITY, expected_return=Rate.from_percent(5), volatility=Rate.from_percent(15))
    holding = Holding(asset=asset, quantity=1, cost_basis=Money.of(1_000_000))
    return {"acc_001": Portfolio(holdings=[holding])}


class RunMontecarloTest(unittest.TestCase):
    def test_same_seed_is_fully_reproducible(self) -> None:
        dataset = small_dataset()
        distributions = distributions_from_historical_dataset(dataset)
        correlation_matrix = compute_correlation_matrix(dataset)

        result_a = run_montecarlo(
            _plan(), _portfolios(), zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules(),
            distributions, correlation_matrix, trials=20, seed=123,
        )
        result_b = run_montecarlo(
            _plan(), _portfolios(), zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules(),
            distributions, correlation_matrix, trials=20, seed=123,
        )

        self.assertEqual(result_a.success_rate, result_b.success_rate)
        self.assertEqual(result_a.percentile_networth_by_year, result_b.percentile_networth_by_year)

    def test_returns_statistics_for_all_trials(self) -> None:
        dataset = small_dataset()
        distributions = distributions_from_historical_dataset(dataset)
        correlation_matrix = compute_correlation_matrix(dataset)

        result = run_montecarlo(
            _plan(), _portfolios(), zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules(),
            distributions, correlation_matrix, trials=15, seed=1,
        )

        self.assertEqual(result.trials, 15)
        self.assertGreaterEqual(result.success_rate, 0.0)
        self.assertLessEqual(result.success_rate, 1.0)
        self.assertIn(2026, result.percentile_networth_by_year)


if __name__ == "__main__":
    unittest.main()
