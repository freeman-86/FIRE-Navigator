import unittest
from datetime import date

from core.domain.account import Account, AccountType, OwnerType
from core.domain.asset import Asset
from core.domain.holding import Holding
from core.domain.income import Income
from core.domain.pension import ClaimTiming, ClaimTimingType, Pension, PensionEntitlement
from core.domain.plan import Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.tax_config import TaxConfig
from core.domain.user import Prefecture, User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from core.simulation.historical.historical_engine import run_historical_backtest
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
    asset = Asset(asset_class="domestic_equity", expected_return=Rate.from_percent(5), volatility=Rate.from_percent(15))
    holding = Holding(asset=asset, quantity=1, cost_basis=Money.of(1_000_000))
    return {"acc_001": Portfolio(holdings=[holding])}


class RunHistoricalBacktestTest(unittest.TestCase):
    def test_runs_one_projection_per_window(self) -> None:
        dataset = small_dataset()  # 2001-2004年、window_length=2なら3窓（2001,2002,2003開始）

        statistics, results_by_window = run_historical_backtest(
            _plan(), _portfolios(), zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules(),
            dataset, window_length=2,
        )

        self.assertEqual(set(results_by_window.keys()), {2001, 2002, 2003})
        self.assertEqual(statistics.trials, 3)

    def test_different_windows_produce_different_networth_due_to_actual_returns(self) -> None:
        dataset = small_dataset()

        _statistics, results_by_window = run_historical_backtest(
            _plan(), _portfolios(), zero_tax_rules(), empty_portfolio_rules(), zero_pension_rules(),
            dataset, window_length=2,
        )

        # 窓ごとに実際に異なるリターン系列が適用されるため、初年度のnetworthが窓によって異なる
        first_year_networths = {
            window_start_year: result.yearly_projections[0].networth
            for window_start_year, result in results_by_window.items()
        }
        self.assertEqual(len(set(first_year_networths.values())), len(first_year_networths))


if __name__ == "__main__":
    unittest.main()
