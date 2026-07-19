import unittest
from datetime import date
from decimal import Decimal

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
from core.domain.allocation import AllocationPolicy, AllocationTarget
from core.simulation.montecarlo.distribution import distributions_from_historical_dataset, to_monthly_distributions
from core.simulation.montecarlo.correlation_matrix import compute_correlation_matrix
from core.simulation.montecarlo.montecarlo_engine import build_weight_lookup, _make_growth_rate_provider, run_montecarlo
from core.simulation.montecarlo.random_seed import create_rng
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
    holding = Holding(asset=asset, quantity=1, current_value=Money.of(1_000_000), cost_basis=Money.of(1_000_000))
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

    def test_samples_a_fresh_return_every_month_not_once_per_year(self) -> None:
        # Sprint12 月次化: growth_rate_providerは月次オフセットで毎回呼び出され、
        # 同じ年の12ヶ月すべてに同一の値を使い回すことはない（サンプリングの分散が失われていないか確認）。
        dataset = small_dataset()
        distributions = distributions_from_historical_dataset(dataset)
        correlation_matrix = compute_correlation_matrix(dataset)
        asset_classes = list(distributions.keys())
        weights = {ac: Decimal("1") / len(asset_classes) for ac in asset_classes}

        provider = _make_growth_rate_provider(
            asset_classes, to_monthly_distributions(distributions), correlation_matrix, lambda offset: weights, create_rng(7)
        )
        monthly_rates = [provider(offset).value for offset in range(12)]

        self.assertEqual(len(set(monthly_rates)), 12)


class BuildWeightLookupTest(unittest.TestCase):
    def test_uses_allocation_policy_weights_and_switches_at_age_boundary(self) -> None:
        import dataclasses

        # _plan()はstart_year=2026年1月1日開始, birth_date=1990-04-01。誕生日考慮の年齢計算のため、
        # 4月を迎えるまでは前年の年齢のまま: offset0-2(2026年1〜3月)はage35、
        # offset3(2026年4月、36歳の誕生日)からage36、offset15(2027年4月、37歳の誕生日)からage37。
        plan = dataclasses.replace(
            _plan(),
            allocation_policy=AllocationPolicy(
                targets=[
                    AllocationTarget(age=36, weights={"domestic_equity": Rate.of("1.0")}),
                    AllocationTarget(age=37, weights={"domestic_bond": Rate.of("1.0")}),
                ]
            ),
        )

        weight_lookup = build_weight_lookup(plan, _portfolios())

        # offset0(2026年1月、age35): まだ適用対象の配分方針がない
        self.assertEqual(weight_lookup(0), {})
        # offset3-14(2026年4月〜2027年3月、age36): 株式100%
        self.assertEqual(weight_lookup(3).get("domestic_equity"), Decimal("1.0"))
        self.assertEqual(weight_lookup(14).get("domestic_equity"), Decimal("1.0"))
        # offset15(2027年4月、age37): 債券100%に切り替わる
        self.assertEqual(weight_lookup(15).get("domestic_bond"), Decimal("1.0"))
        self.assertNotIn("domestic_equity", weight_lookup(15))

    def test_falls_back_to_static_portfolio_weights_without_allocation_policy(self) -> None:
        weight_lookup = build_weight_lookup(_plan(), _portfolios())

        weights_at_0 = weight_lookup(0)
        weights_at_100 = weight_lookup(100)
        self.assertEqual(weights_at_0, weights_at_100)
        self.assertIn("domestic_equity", weights_at_0)


if __name__ == "__main__":
    unittest.main()
