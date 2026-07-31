from __future__ import annotations

from dataclasses import dataclass, replace

from core.domain.pension import PensionRules
from core.domain.plan import Plan
from core.domain.portfolio import Portfolio
from core.domain.portfolio_rules import PortfolioRules
from core.domain.tax_config import TaxRules
from core.domain.value_objects import Money, Rate
from core.simulation.projection.projection_engine import run_projection

DEFAULT_EXPENSE_LEVEL_VARIATIONS: tuple[tuple[str, Rate], ...] = (
    ("-10%", Rate.from_percent(-10)),
    ("±0%", Rate.zero()),
    ("+10%", Rate.from_percent(10)),
)
DEFAULT_INFLATION_RATE_VARIATIONS: tuple[tuple[str, Rate], ...] = (
    ("-0.5%", Rate.from_percent(-0.5)),
    ("±0%", Rate.zero()),
    ("+0.5%", Rate.from_percent(0.5)),
)


@dataclass
class SensitivityResult:
    expense_level_labels: list[str]
    inflation_rate_labels: list[str]
    final_networth_grid: dict[tuple[str, str], Money]  # (expense_label, inflation_label) -> 最終年ネットワース


def run_sensitivity_analysis(
    plan: Plan,
    portfolios: dict[str, Portfolio],
    tax_rules: TaxRules,
    portfolio_rules: PortfolioRules,
    pension_rules: PensionRules,
    expense_level_variations: tuple[tuple[str, Rate], ...] = DEFAULT_EXPENSE_LEVEL_VARIATIONS,
    inflation_rate_variations: tuple[tuple[str, Rate], ...] = DEFAULT_INFLATION_RATE_VARIATIONS,
) -> SensitivityResult:
    """支出水準・インフレ率を複数パターン振って再計算し、各組み合わせの最終年ネットワースを
    グリッドとして返すバッチ処理。

    以前は「口座期待リターン±1%」という軸を持っていたが、同じダッシュボードにあるモンテカルロ/
    ヒストリカルの方がリターンの不確実性を遥かに高精度（分布）で表現できており、決定論的な3点評価は
    二重表現で情報価値が低いため廃止した。代わりに、モンテカルロでは表現できない
    「ユーザー自身が選べる意思決定」の軸として支出水準を採用する。expense_level_variationsは
    経常支出（Expense.amount）・単発支出（OneTimeExpense.amount）・教育費（EducationExpenseBand.
    monthly_amount）全てに一律で加える増減幅として適用する（収入には影響しない）。

    インフレ率側の軸には、成長率が未入力（空欄）だった収入・支出行が入力読込時に元のinflation_rateへ
    固定値として解決済みになっている（adapters/local/local_data_adapter._parse_growth_rate）ため、
    ここでplan.assumptions.inflation_rateを振っても反映されないという制約があった。growth_rateが
    元のinflation_rateと一致する行を「未入力だった行」とみなし、新しいinflation_rateへ付け替えることで
    対応する（_apply_inflation_delta。成長率を明示的に元のinflation_rateと同じ値へ設定していた行との
    区別はできないため、あくまで近似）。教育費・単発支出・年金収入は元々plan.assumptions.
    inflation_rateを毎回参照する設計のため、この付け替えなしでも正しく反映される。
    """

    expense_level_labels = [label for label, _delta in expense_level_variations]
    inflation_rate_labels = [label for label, _delta in inflation_rate_variations]

    final_networth_grid: dict[tuple[str, str], Money] = {}
    for expense_label, expense_delta in expense_level_variations:
        varied_plan_by_expense = _apply_expense_level_delta(plan, expense_delta)
        for inflation_label, inflation_delta in inflation_rate_variations:
            varied_plan = _apply_inflation_delta(varied_plan_by_expense, inflation_delta)
            result = run_projection(varied_plan, portfolios, tax_rules, portfolio_rules, pension_rules)
            final_networth = result.yearly_projections[-1].networth if result.yearly_projections else Money.zero()
            final_networth_grid[(expense_label, inflation_label)] = final_networth

    return SensitivityResult(
        expense_level_labels=expense_level_labels,
        inflation_rate_labels=inflation_rate_labels,
        final_networth_grid=final_networth_grid,
    )


def _apply_expense_level_delta(plan: Plan, expense_delta: Rate) -> Plan:
    """経常支出・単発支出・教育費の金額に一律でexpense_deltaを加えた（±n%した）Planの複製を返す
    （元のplanは変更しない。収入には影響しない）。"""

    expenses = [
        replace(expense, amount=expense.amount + expense_delta.apply_to(expense.amount)) for expense in plan.expenses
    ]
    one_time_expenses = [
        replace(expense, amount=expense.amount + expense_delta.apply_to(expense.amount))
        for expense in plan.one_time_expenses
    ]
    education_expenses = [
        replace(band, monthly_amount=band.monthly_amount + expense_delta.apply_to(band.monthly_amount))
        for band in plan.education_expenses
    ]
    return replace(plan, expenses=expenses, one_time_expenses=one_time_expenses, education_expenses=education_expenses)


def _apply_inflation_delta(plan: Plan, inflation_delta: Rate) -> Plan:
    original_inflation_rate = plan.assumptions.inflation_rate
    new_inflation_rate = original_inflation_rate + inflation_delta
    assumptions = replace(plan.assumptions, inflation_rate=new_inflation_rate)

    incomes = [
        replace(income, growth_rate=new_inflation_rate) if income.growth_rate == original_inflation_rate else income
        for income in plan.incomes
    ]
    expenses = [
        replace(expense, growth_rate=new_inflation_rate) if expense.growth_rate == original_inflation_rate else expense
        for expense in plan.expenses
    ]
    return replace(plan, assumptions=assumptions, incomes=incomes, expenses=expenses)
