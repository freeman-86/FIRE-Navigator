from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Callable, Optional

from core.domain.asset import AssetClass
from core.domain.child import Child
from core.domain.education_expense import EducationExpenseBand
from core.domain.expense import Expense
from core.domain.income import Income
from core.domain.milestone import MilestoneType
from core.domain.one_time_expense import OneTimeExpense
from core.domain.pension import Pension, PensionRules
from core.domain.plan import DEFAULT_LIFE_EXPECTANCY_AGE, Plan, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.portfolio_rules import PortfolioRules
from core.domain.simulation_result import MonthlyProjection, SimulationResult, YearlyProjection
from core.domain.tax_config import TaxRules
from core.domain.value_objects import AgeAt, EventCondition, Money, Rate
from core.simulation.pension.pension_engine import calculate_pension_income
from core.simulation.portfolio.portfolio_engine import allocate_discretionary_surplus, plan_fixed_contributions
from core.simulation.projection.event_conditions import resolve_condition_month, resolve_condition_year
from core.simulation.projection.milestone_evaluation import evaluate_milestones
from core.simulation.tax.tax_engine import calculate_tax
from core.simulation.withdrawal.withdrawal_engine import withdraw_shortfall

DEFAULT_PROJECTION_YEARS = 30
UNALLOCATED_SURPLUS_KEY = "unallocated_surplus"
MONTHS_PER_YEAR = 12


@dataclass
class _YearAccumulator:
    """実際の西暦年ごとに月次実績を合算するための可変な集計バケット（YearlyProjection構築用）。

    フロー項目（収入・支出・税額等）はその年に属する月の値を合計する。ストック項目
    （口座残高・純資産・年齢）は月が進むたびに上書きし、最終的にその年最後の月（年末時点、
    または想定寿命等でシミュレーションが途中で終わる場合は最終月）のスナップショットになる。
    """

    gross_income: Money = field(default_factory=Money.zero)
    pension_income: Money = field(default_factory=Money.zero)
    income_tax: Money = field(default_factory=Money.zero)
    resident_tax: Money = field(default_factory=Money.zero)
    social_insurance: Money = field(default_factory=Money.zero)
    net_income: Money = field(default_factory=Money.zero)
    total_expense: Money = field(default_factory=Money.zero)
    net_cashflow: Money = field(default_factory=Money.zero)
    capital_gains_tax: Money = field(default_factory=Money.zero)
    age_self: int = 0
    account_balances: dict[str, Money] = field(default_factory=dict)
    networth: Money = field(default_factory=Money.zero)


def _build_yearly_projection(calendar_year: int, acc: _YearAccumulator) -> YearlyProjection:
    return YearlyProjection(
        year=calendar_year,
        age_self=acc.age_self,
        gross_income=acc.gross_income,
        pension_income=acc.pension_income,
        income_tax=acc.income_tax,
        resident_tax=acc.resident_tax,
        social_insurance=acc.social_insurance,
        net_income=acc.net_income,
        total_expense=acc.total_expense,
        net_cashflow=acc.net_cashflow,
        capital_gains_tax=acc.capital_gains_tax,
        account_balances=acc.account_balances,
        networth=acc.networth,
    )


def run_projection(
    plan: Plan,
    portfolios: dict[str, Portfolio],
    tax_rules: TaxRules,
    portfolio_rules: PortfolioRules,
    pension_rules: PensionRules,
    growth_rate_provider: Optional[Callable[[int], Rate]] = None,
) -> SimulationResult:
    """決定論的シミュレーション。内部的には月次ループで計算し（Sprint12 月次化）、
    実際の西暦年（1〜12月）ごとに集計したスナップショットをYearlyProjectionとして積み上げる。
    これによりmilestone評価・感応度分析・チャート・Monte Carlo/Historical Engine等の年次インターフェースは
    無改修で動作する。月次の明細はSimulationResult.monthly_projectionsに別途保持する。

    内部の年次ループ自体はプラン開始月（start_month）を起点とした12ヶ月区切り（例:
    TODAY開始・7月なら7月〜翌6月）のまま所得税・住民税・社会保険料等を計算するが（年次課税額の
    近似計算はこの区切りの方が実態に近いため）、YearlyProjectionへの集計は月次実績
    （MonthlyProjection）を実際の西暦年ごとに合算して作る。これにより出力_純資産推移の「西暦年」列と
    出力_月次詳細の同じ西暦年の月次合計が一致する（以前はプラン開始月起点の12ヶ月区切りをそのまま
    「西暦年」として表示していたため、start_monthが1月以外の場合は両シートの集計期間がずれ、
    金額が一致しなかった）。

    退職(RETIREMENT)マイルストーンがある場合、想定寿命(plan.life_expectancy_age。
    入力_プラン設定の想定寿命、未入力ならDEFAULT_LIFE_EXPECTANCY_AGE)まで
    退職後フェーズを含めて計算する。手取り収入(給与+年金)が生活費・確定拠出を上回る月は
    contribution_strategyの優先順位で口座へ自動配分し、下回る月（退職後の取り崩し局面等）は
    withdrawal_strategyの優先順位で口座残高を取り崩す。

    所得税・住民税・社会保険料は日本の税制がそもそも年次確定であるため、従来通り年1回のみ
    計算し、その結果を12等分して毎月のキャッシュフローに反映する（旧ドラフトのEngineと同様の
    簡略化）。収入・支出の開始/終了条件は現時点では年単位でのみ判定する（月単位への精緻化は
    将来課題）。

    portfolios/tax_rules/portfolio_rules/pension_rulesはApplication層相当の呼び出し元が
    用意して渡す。Simulation Engineはyaml等のI/Oを直接扱わない（設計書3.2 依存方向の原則）。

    growth_rate_provider: 月次オフセット(0始まり)を受け取りその月の資産成長率を返す関数。
    省略時はplan.assumptions.investment_growth_rate（年率固定値）をmonthly_equivalent()で
    月率に変換し、毎月同じ値を使う従来通りの決定論的計算になる。Monte Carlo Engineは毎月
    新規にサンプリングした相関考慮済みの月次リターンを、Historical Engineは実績の年次リターンを
    月率換算した値を返す関数をここに渡すことで、同じProjection Engineを反復実行する
    （設計書v1.1 ⑥⑦）。
    """

    start_year = resolve_start_year(plan)
    start_month = resolve_start_month(plan)
    end_year = _resolve_end_year(plan, start_year)
    birth_date = plan.user.birth_date
    has_spouse = plan.user.spouse is not None
    default_monthly_rate = plan.assumptions.investment_growth_rate.monthly_equivalent()
    per_account_monthly_rate = _monthly_rate_by_account_id(portfolios)
    one_time_expenses_by_month_offset = _one_time_expenses_by_month_offset(
        plan.one_time_expenses, start_year, start_month, birth_date
    )

    account_balances = {
        account.account_id: _initial_balance(portfolios.get(account.account_id)) for account in plan.accounts
    }
    # 取り崩し時の譲渡税計算（平均取得原価方式）に使う累計取得原価。入力_口座の取得原価列
    # （Holding.cost_basis）をそのまま初期値とするため、シミュレーション開始前からの含み益/含み損を
    # 正しく反映できる（取得原価が未入力の口座は残高と同額になり、含み益ゼロからのスタートになる）。
    cost_basis_balances = {
        account.account_id: _initial_cost_basis(portfolios.get(account.account_id)) for account in plan.accounts
    }
    lifetime_contributions = {account.account_id: Money.zero() for account in plan.accounts}
    surplus_reserve = Money.zero()
    asset_class_by_account_id = _asset_class_by_account_id(portfolios)
    # 月次詳細の資産クラス別取り崩し額列を、月をまたいで常に同じ列構成にするための資産クラス一覧
    # （出力_月次詳細の列がプランの口座構成に応じて動的に決まる。ソートは表示順を安定させるため）。
    all_asset_classes = sorted(set(asset_class_by_account_id.values()))

    monthly_projections: list[MonthlyProjection] = []
    calendar_year_accumulators: dict[int, _YearAccumulator] = {}
    for offset_year in range(end_year - start_year + 1):
        month_pairs_this_year = [
            calendar_year_month(start_year, start_month, offset_year * MONTHS_PER_YEAR + m)
            for m in range(MONTHS_PER_YEAR)
        ]
        gross_income_annual = _active_income_total(
            plan.incomes, month_pairs_this_year, start_year, start_month, birth_date, offset_year
        )
        pension_income_annual = _pension_income_for_year(birth_date, plan.pension, pension_rules, month_pairs_this_year)
        total_expense_annual = _active_expense_total(
            plan.expenses, month_pairs_this_year, start_year, start_month, birth_date, offset_year
        )

        fixed_plan = plan_fixed_contributions(plan.accounts, lifetime_contributions, portfolio_rules)
        year_end_calendar_year, year_end_calendar_month = month_pairs_this_year[-1]
        is_65_or_older = age_at(birth_date, year_end_calendar_year, year_end_calendar_month) >= 65
        tax_result = calculate_tax(
            gross_income_annual, pension_income_annual, plan.tax_config, has_spouse, tax_rules,
            fixed_plan.tax_deductible_amount, is_65_or_older,
        )

        monthly_gross_income = _divide_by_12(gross_income_annual)
        monthly_pension_income = _divide_by_12(pension_income_annual)
        monthly_net_income = _divide_by_12(tax_result.net_income)
        monthly_income_tax = _divide_by_12(tax_result.income_tax)
        monthly_resident_tax = _divide_by_12(tax_result.resident_tax)
        monthly_social_insurance = _divide_by_12(tax_result.social_insurance)
        monthly_recurring_expense = _divide_by_12(total_expense_annual)
        monthly_fixed_contributions = {
            account_id: _divide_by_12(amount) for account_id, amount in fixed_plan.contributions.items()
        }
        discretionary_contributed_this_year: dict[str, Money] = {}

        balances_snapshot: dict[str, Money] = {}
        networth = Money.zero()
        for month in range(1, MONTHS_PER_YEAR + 1):
            month_offset = offset_year * MONTHS_PER_YEAR + (month - 1)
            calendar_year, calendar_month = calendar_year_month(start_year, start_month, month_offset)
            age_this_month = age_at(birth_date, calendar_year, calendar_month)
            growth_rate = (
                growth_rate_provider(month_offset) if growth_rate_provider is not None else default_monthly_rate
            )

            one_time_expense_this_month = one_time_expenses_by_month_offset.get(month_offset, Money.zero())
            education_expense_this_month = _education_expense_monthly_total(
                plan.children, plan.education_expenses, calendar_year, calendar_month
            )
            monthly_expense = monthly_recurring_expense + one_time_expense_this_month + education_expense_this_month

            net_cashflow_month = monthly_net_income - monthly_expense
            discretionary_surplus_month = net_cashflow_month - _total(monthly_fixed_contributions)
            target_weights_this_month = (
                plan.allocation_policy.weights_for_age(age_this_month) if plan.allocation_policy is not None else {}
            )

            if discretionary_surplus_month.is_negative:
                withdrawal_outcome = withdraw_shortfall(
                    plan.accounts,
                    account_balances,
                    cost_basis_balances,
                    -discretionary_surplus_month,
                    plan.withdrawal_strategy,
                    portfolio_rules,
                    tax_rules.capital_gains,
                    age_this_month,
                    asset_class_by_account_id=asset_class_by_account_id,
                    target_weights=target_weights_this_month,
                )
                contributions_this_month = _merge(monthly_fixed_contributions, _negate(withdrawal_outcome.withdrawals))
                unallocated_delta = -withdrawal_outcome.remaining_shortfall
                capital_gains_tax_month = withdrawal_outcome.capital_gains_tax
                withdrawals_by_asset_class_month = {
                    asset_class: withdrawal_outcome.withdrawals_by_asset_class.get(asset_class, Money.zero())
                    for asset_class in all_asset_classes
                }
                cost_basis_balances = {
                    account_id: withdrawal_outcome.updated_cost_basis.get(account_id, Money.zero())
                    + monthly_fixed_contributions.get(account_id, Money.zero())
                    for account_id in account_balances
                }
            else:
                already_contributed_this_year = _merge(fixed_plan.contributions, discretionary_contributed_this_year)
                discretionary_contributions, unallocated_leftover = allocate_discretionary_surplus(
                    plan.accounts,
                    account_balances,
                    lifetime_contributions,
                    already_contributed_this_year,
                    discretionary_surplus_month,
                    plan.contribution_strategy,
                    portfolio_rules,
                    asset_class_by_account_id=asset_class_by_account_id,
                    target_weights=target_weights_this_month,
                )
                contributions_this_month = _merge(monthly_fixed_contributions, discretionary_contributions)
                unallocated_delta = unallocated_leftover
                capital_gains_tax_month = Money.zero()
                withdrawals_by_asset_class_month = {asset_class: Money.zero() for asset_class in all_asset_classes}
                discretionary_contributed_this_year = _merge(
                    discretionary_contributed_this_year, discretionary_contributions
                )
                cost_basis_balances = {
                    account_id: cost_basis_balances.get(account_id, Money.zero())
                    + contributions_this_month.get(account_id, Money.zero())
                    for account_id in account_balances
                }

            account_balances = {
                account_id: _floor_zero(
                    _grow(
                        balance,
                        growth_rate
                        if growth_rate_provider is not None
                        else per_account_monthly_rate.get(account_id, default_monthly_rate),
                    )
                    + contributions_this_month.get(account_id, Money.zero())
                )
                for account_id, balance in account_balances.items()
            }
            lifetime_contributions = {
                account_id: lifetime_contributions[account_id] + contributions_this_month.get(account_id, Money.zero())
                for account_id in lifetime_contributions
            }
            surplus_reserve = _grow(surplus_reserve, growth_rate) + unallocated_delta

            balances_snapshot = {**account_balances, UNALLOCATED_SURPLUS_KEY: surplus_reserve}
            networth = sum(balances_snapshot.values(), Money.zero())

            monthly_projections.append(
                MonthlyProjection(
                    year=calendar_year,
                    month=calendar_month,
                    age_self=age_this_month,
                    gross_income=monthly_gross_income,
                    pension_income=monthly_pension_income,
                    net_income=monthly_net_income,
                    total_expense=monthly_expense,
                    net_cashflow=net_cashflow_month,
                    capital_gains_tax=capital_gains_tax_month,
                    account_balances=dict(balances_snapshot),
                    networth=networth,
                    withdrawals_by_asset_class=dict(withdrawals_by_asset_class_month),
                )
            )

            # 出力_純資産推移の「西暦年」が出力_月次詳細の同じ西暦年の月次合計と一致するよう、
            # プラン開始月起点の12ヶ月区切り（この外側ループの単位）ではなく、実際の西暦年
            # （calendar_year）ごとに月次実績を合算してYearlyProjectionを作る。
            year_acc = calendar_year_accumulators.setdefault(calendar_year, _YearAccumulator())
            year_acc.gross_income += monthly_gross_income
            year_acc.pension_income += monthly_pension_income
            year_acc.income_tax += monthly_income_tax
            year_acc.resident_tax += monthly_resident_tax
            year_acc.social_insurance += monthly_social_insurance
            year_acc.net_income += monthly_net_income
            year_acc.total_expense += monthly_expense
            year_acc.net_cashflow += net_cashflow_month
            year_acc.capital_gains_tax += capital_gains_tax_month
            year_acc.age_self = age_this_month  # 月が進むたびに上書きされ、最終的にその年最後の月の年齢になる
            year_acc.account_balances = dict(balances_snapshot)  # 同様に、その年最後の月の残高スナップショットになる
            year_acc.networth = networth

    yearly_projections = [
        _build_yearly_projection(calendar_year, year_acc)
        for calendar_year, year_acc in sorted(calendar_year_accumulators.items())
    ]

    milestone_outcomes = evaluate_milestones(plan, yearly_projections)

    return SimulationResult(
        yearly_projections=yearly_projections,
        monthly_projections=monthly_projections,
        milestone_outcomes=milestone_outcomes,
    )


def _initial_balance(portfolio: Optional[Portfolio]) -> Money:
    if portfolio is None:
        return Money.zero()
    total = Money.zero()
    for holding in portfolio.holdings:
        total = total + holding.current_value
    return total


def _initial_cost_basis(portfolio: Optional[Portfolio]) -> Money:
    if portfolio is None:
        return Money.zero()
    total = Money.zero()
    for holding in portfolio.holdings:
        total = total + holding.cost_basis
    return total


def _asset_class_by_account_id(portfolios: dict[str, Portfolio]) -> dict[str, AssetClass]:
    """口座ごとの資産クラスを解決する（現状のSheets入力モデルは1口座=1資産クラスの前提。
    複数保有がある場合は先頭のholdingを代表として扱う）。AllocationPolicyによる
    ドリフト考慮の拠出配分・月次リバランスで、口座がどの資産クラスに属するかを引くのに使う。
    """

    result: dict[str, AssetClass] = {}
    for account_id, portfolio in portfolios.items():
        if portfolio.holdings:
            result[account_id] = portfolio.holdings[0].asset.asset_class
    return result


def _monthly_rate_by_account_id(portfolios: dict[str, Portfolio]) -> dict[str, Rate]:
    """口座ごとの月率換算した期待リターンを解決する（決定論的エンジン専用）。

    入力_口座の期待リターン(Asset.expected_return)を口座ごとの資産成長率として使う。
    Monte Carlo/Historical Engineはgrowth_rate_providerで全口座に一律の月次レートを渡す
    既存の設計のままとする（資産クラス別の過去実績分布をAllocationPolicyの資産クラス比率で
    加重合成した単一レートを使う設計であり、口座単位のexpected_returnは使わない）。
    """

    result: dict[str, Rate] = {}
    for account_id, portfolio in portfolios.items():
        if portfolio.holdings:
            result[account_id] = portfolio.holdings[0].asset.expected_return.monthly_equivalent()
    return result


def _divide_by_12(amount: Money) -> Money:
    return Money.of(amount.amount / MONTHS_PER_YEAR)


def _total(amounts: dict[str, Money]) -> Money:
    total = Money.zero()
    for amount in amounts.values():
        total = total + amount
    return total


def _merge(a: dict[str, Money], b: dict[str, Money]) -> dict[str, Money]:
    merged = dict(a)
    for account_id, amount in b.items():
        merged[account_id] = merged.get(account_id, Money.zero()) + amount
    return merged


def _negate(amounts: dict[str, Money]) -> dict[str, Money]:
    return {account_id: -amount for account_id, amount in amounts.items()}


def _grow(money: Money, rate: Rate) -> Money:
    return money + rate.apply_to(money)


def _floor_zero(money: Money) -> Money:
    # マイナス成長率下での取り崩し等、稀な端数ケースで口座残高が僅かに負になるのを防ぐ安全弁。
    return money if not money.is_negative else Money.zero()


def _grown_amount(amount: Money, growth_rate: Rate, offset: int) -> Money:
    factor = (Decimal(1) + growth_rate.value) ** offset
    return amount * factor


def resolve_start_year(plan: Plan) -> int:
    condition = plan.start_condition
    if condition.condition_type == StartConditionType.FIXED_DATE:
        return condition.fixed_date.year
    return date.today().year


def resolve_start_month(plan: Plan) -> int:
    condition = plan.start_condition
    if condition.condition_type == StartConditionType.FIXED_DATE:
        return condition.fixed_date.month
    return date.today().month


def calendar_year_month(start_year: int, start_month: int, month_offset: int) -> tuple[int, int]:
    """月次オフセット(0始まり)を実際の西暦年・月に変換する。

    YearlyProjection.yearは「プラン開始からN年目」という単純な連番（start_year+offset_year）の
    ままだが、MonthlyProjectionの年月はOneTimeExpense等の発生月と一致させる必要があるため、
    start_monthが1月以外（例: StartConditionType.TODAYで年の途中から始まるプラン）でも
    実際のカレンダー通りの年月になるようここで変換する。
    """

    total_months = (start_month - 1) + month_offset
    return start_year + total_months // MONTHS_PER_YEAR, total_months % MONTHS_PER_YEAR + 1


def _resolve_end_year(plan: Plan, start_year: int) -> int:
    retirement_year = _retirement_year(plan, start_year)
    if retirement_year is not None:
        life_expectancy_year = plan.user.birth_date.year + plan.life_expectancy_age
        return max(retirement_year, life_expectancy_year, start_year)
    return start_year + DEFAULT_PROJECTION_YEARS - 1


def _retirement_year(plan: Plan, start_year: int) -> Optional[int]:
    for milestone in plan.milestones:
        if milestone.milestone_type == MilestoneType.RETIREMENT:
            return resolve_condition_year(milestone.trigger, start_year, plan.user.birth_date)
    return None


def _is_active_in_month(
    start_condition: Optional[EventCondition],
    end_condition: Optional[EventCondition],
    calendar_year: int,
    calendar_month: int,
    start_year: int,
    start_month: int,
    birth_date: date,
) -> bool:
    # start_conditionはExpense（経常支出）では省略可能（Noneの場合は開始条件による制限なし＝
    # プラン開始時点から発生しているものとして扱う）。Incomeでは常に必須のためNoneにはならない。
    if start_condition is not None:
        start_resolved = resolve_condition_month(start_condition, start_year, start_month, birth_date)
        if start_resolved is not None and (calendar_year, calendar_month) < start_resolved:
            return False
    if end_condition is not None:
        end_resolved = resolve_condition_month(end_condition, start_year, start_month, birth_date)
        if end_resolved is not None and (calendar_year, calendar_month) >= end_resolved:
            return False
    return True


def _active_months_in_year(
    start_condition: Optional[EventCondition],
    end_condition: Optional[EventCondition],
    month_pairs: list[tuple[int, int]],
    start_year: int,
    start_month: int,
    birth_date: date,
) -> int:
    return sum(
        1
        for calendar_year, calendar_month in month_pairs
        if _is_active_in_month(
            start_condition, end_condition, calendar_year, calendar_month, start_year, start_month, birth_date
        )
    )


def _active_income_total(
    incomes: list[Income],
    month_pairs: list[tuple[int, int]],
    start_year: int,
    start_month: int,
    birth_date: date,
    offset: int,
) -> Money:
    """月精度で開始/終了条件を判定し、年間のうち条件を満たす月数分だけ按分した年間収入合計を返す
    （「西暦年」だけでの判定だと、年の途中で開始/終了する収入が最大11ヶ月分ずれるため）。
    """

    total = Money.zero()
    for income in incomes:
        active_months = _active_months_in_year(
            income.start_condition, income.end_condition, month_pairs, start_year, start_month, birth_date
        )
        if active_months == 0:
            continue
        full_year_amount = _grown_amount(income.amount, income.growth_rate, offset)
        if active_months >= MONTHS_PER_YEAR:
            total = total + full_year_amount
        else:
            total = total + full_year_amount * (Decimal(active_months) / Decimal(MONTHS_PER_YEAR))
    return total


def _active_expense_total(
    expenses: list[Expense],
    month_pairs: list[tuple[int, int]],
    start_year: int,
    start_month: int,
    birth_date: date,
    offset: int,
) -> Money:
    """月精度で開始/終了条件を判定し、年間のうち条件を満たす月数分だけ按分した年間経常支出合計を返す
    （_active_income_totalの支出版。start_condition/end_conditionはともに省略可能で、両方省略した
    行はこれまで通りプラン全期間で発生する扱いになる）。
    """

    total = Money.zero()
    for expense in expenses:
        active_months = _active_months_in_year(
            expense.start_condition, expense.end_condition, month_pairs, start_year, start_month, birth_date
        )
        if active_months == 0:
            continue
        full_year_amount = _grown_amount(expense.amount, expense.growth_rate, offset)
        if active_months >= MONTHS_PER_YEAR:
            total = total + full_year_amount
        else:
            total = total + full_year_amount * (Decimal(active_months) / Decimal(MONTHS_PER_YEAR))
    return total


def age_at(birth_date: date, calendar_year: int, calendar_month: int) -> int:
    """その月の1日時点での満年齢を返す（誕生日を考慮した正確な年齢）。

    配分方針の年齢帯判定・年齢表示（YearlyProjection/MonthlyProjection.age_self）に使う。
    「西暦年-生年」だけの単純計算だと誕生月を無視して最大1年近くずれるため、AgeAtで
    誕生日基準の年齢を毎月計算し直す。
    """

    reference_date = date(calendar_year, calendar_month, 1)
    if reference_date < birth_date:
        return 0
    return AgeAt(birth_date, reference_date).years


def _pension_eligible_months(birth_date: date, claim_age: int, month_pairs: list[tuple[int, int]]) -> int:
    """month_pairs（その年にループが実際に処理する(西暦年,月)の一覧）のうち、
    年金受給資格年齢(claim_age)に達している月数を返す（0〜12）。

    誕生日を迎えた月から資格を得ると仮定する簡略化（実際の支給開始月の厳密な制度計算は行わない）。
    「西暦年-生年」だけで判定すると、誕生日がまだ来ていない月も受給資格ありと誤判定してしまうため
    （最大11ヶ月分の年金を早く計上してしまう）、月ごとにAgeAtで正確な年齢を確認する。
    month_pairsは_calendar_year_month()で解決した実際のカレンダー年月を渡す必要がある
    （プランがTODAY開始で年度途中から始まる場合、ループの名目上のyearとは一致しないため）。
    """

    count = 0
    for calendar_year, calendar_month in month_pairs:
        reference_date = date(calendar_year, calendar_month, 1)
        if reference_date < birth_date:
            continue
        if AgeAt(birth_date, reference_date).years >= claim_age:
            count += 1
    return count


def _pension_income_for_year(
    birth_date: date, pension: Pension, pension_rules: PensionRules, month_pairs: list[tuple[int, int]]
) -> Money:
    """その年の年金収入を、受給資格を得た月数で按分して返す（受給資格を得る年の按分計算）。

    受給開始タイミングによる増減率(繰上げ/繰下げ)はcalculate_pension_income内で固定額として
    決まるため、まず満額(claim_timing.age時点の額)を求め、その年のうち資格がある月数分だけ
    按分する。年金は所得税・住民税と同様に年1回のみ確定する既存の設計を維持する。
    """

    eligible_months = _pension_eligible_months(birth_date, pension.claim_timing.age, month_pairs)
    if eligible_months == 0:
        return Money.zero()
    full_year_amount = calculate_pension_income(pension.claim_timing.age, pension, pension_rules)
    if eligible_months >= MONTHS_PER_YEAR:
        return full_year_amount
    return full_year_amount * (Decimal(eligible_months) / Decimal(MONTHS_PER_YEAR))


def _school_year_age(birth_date: date, calendar_year: int, calendar_month: int) -> Optional[int]:
    """その月が属する年度（4月始まり）の4月1日時点の年齢を返す（日本の学年の切り替わり基準）。

    1〜3月は前年度扱いとする（例: 2028年1月〜3月は2027年度、2028年4月〜12月は2028年度）。
    その年度の4月1日時点でまだ生まれていない場合はNoneを返す（該当年齢なし）。
    """

    school_year = calendar_year if calendar_month >= 4 else calendar_year - 1
    reference_date = date(school_year, 4, 1)
    if reference_date < birth_date:
        return None
    return AgeAt(birth_date, reference_date).years


def _education_expense_monthly_total(
    children: list[Child], bands: list[EducationExpenseBand], calendar_year: int, calendar_month: int
) -> Money:
    """その月が属する年度の4月1日時点の子供の年齢に基づき、教育費バンド（小学校・塾等）の
    月額合計を返す（ギャップ分析3.2）。年齢帯の切り替わりは誕生月ではなく学年（4月1日）を基準にする。
    物価上昇は考慮しない（既存のinflation_rate同様、現時点では未対応）。
    """

    age_by_child_id = {
        child.child_id: _school_year_age(child.birth_date, calendar_year, calendar_month) for child in children
    }
    total = Money.zero()
    for band in bands:
        age = age_by_child_id.get(band.child_id)
        if age is not None and band.applies_to_age(age):
            total = total + band.monthly_amount
    return total


def _one_time_expenses_by_month_offset(
    one_time_expenses: list[OneTimeExpense], start_year: int, start_month: int, birth_date: date
) -> dict[int, Money]:
    """車・旅行・住宅購入等の単発支出（ギャップ分析3.3）を、発生する月次オフセットごとに
    集計する。同じ月に複数の単発支出が重なる場合は合算する。
    """

    result: dict[int, Money] = {}
    for expense in one_time_expenses:
        resolved = resolve_condition_month(expense.trigger, start_year, start_month, birth_date)
        if resolved is None:
            continue
        target_year, target_month = resolved
        target_offset = (target_year - start_year) * MONTHS_PER_YEAR + (target_month - start_month)
        result[target_offset] = result.get(target_offset, Money.zero()) + expense.amount
    return result
