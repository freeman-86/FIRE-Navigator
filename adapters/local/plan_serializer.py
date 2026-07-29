"""Plan集約（+Portfolio・目標資産）を、local_data_adapter.pyが読み込めるJSON辞書に変換する。

scripts/migrate_from_sheets.py（既存のGoogleスプレッドシートからの一回限りの移行）専用。
Webアプリのフォーム保存パス（POST /api/plan・/api/run）はブラウザ側で既にこの形のJSONを
組み立てて送ってくるため、このモジュールは経由しない。

Money→JSON整数(円未満なし)、Rate→JSON文字列（Decimalの桁を浮動小数点誤差なしに保つため。
float往復はこの移行が解消しようとしているのと同種の誤差混入バグを再導入しかねない）。
"""
from __future__ import annotations

from typing import Optional

from core.domain.plan import Plan
from core.domain.portfolio import Portfolio
from core.domain.value_objects import EventCondition, EventConditionType, Money, Rate

SCHEMA_VERSION = 1


def _money_to_json(money: Money) -> int:
    return int(money.amount)


def _optional_money_to_json(money: Optional[Money]) -> Optional[int]:
    return None if money is None else _money_to_json(money)


def _rate_to_json(rate: Rate) -> str:
    return str(rate.value)


def _condition_to_json(condition: Optional[EventCondition]) -> Optional[dict]:
    if condition is None:
        return None
    if condition.condition_type == EventConditionType.PLAN_START:
        return {"type": "plan_start"}
    if condition.condition_type == EventConditionType.AGE:
        return {"type": "age", "age": condition.age}
    if condition.condition_type == EventConditionType.DATE:
        return {"type": "date", "date": condition.date.isoformat()}
    # fixed_date/networth_multiple_of_expenseはSheetsアダプタの入力経路が存在せず、
    # 移行元のPlanに含まれることはないはずだが、念のため明示的に拒否する。
    raise ValueError(f"ローカルJSON形式は未対応の条件タイプです: {condition.condition_type}")


def _account_to_json(account, portfolios: dict[str, Portfolio]) -> dict:
    portfolio = portfolios.get(account.account_id)
    holding = portfolio.holdings[0] if portfolio and portfolio.holdings else None
    return {
        "account_id": account.account_id,
        "account_type": account.account_type.value,
        "monthly_contribution": _optional_money_to_json(account.monthly_contribution),
        "asset_class": holding.asset.asset_class if holding else None,
        "expected_return": _rate_to_json(holding.asset.expected_return) if holding else None,
        "current_value": _money_to_json(holding.current_value) if holding else 0,
        # 取得原価は、残高と同額（含み益ゼロ、Sheets版のデフォルト挙動）ならnullにして、
        # 読み込み側のデフォルト解決ロジックと対称にする。異なる場合のみ実際の値を書き出す。
        "cost_basis": (
            None
            if holding is None or holding.cost_basis == holding.current_value
            else _money_to_json(holding.cost_basis)
        ),
    }


def _income_to_json(income) -> dict:
    return {
        "income_id": income.income_id,
        "source": income.source,
        "amount": _money_to_json(income.amount),
        "growth_rate": _rate_to_json(income.growth_rate),
        "start_condition": _condition_to_json(income.start_condition),
        "end_condition": _condition_to_json(income.end_condition),
    }


def _recurring_expense_to_json(expense) -> dict:
    return {
        "expense_id": expense.expense_id,
        "category": expense.category,
        "kind": "recurring",
        "amount": _money_to_json(expense.amount),
        "growth_rate": _rate_to_json(expense.growth_rate),
        "start_condition": _condition_to_json(expense.start_condition),
        "end_condition": _condition_to_json(expense.end_condition),
    }


def _one_time_expense_to_json(one_time_expense) -> dict:
    return {
        "expense_id": one_time_expense.expense_id,
        "category": one_time_expense.category,
        "kind": "one_time",
        "amount": _money_to_json(one_time_expense.amount),
        "trigger": _condition_to_json(one_time_expense.trigger),
    }


def _allocation_policy_to_json(allocation_policy) -> Optional[dict]:
    if allocation_policy is None:
        return None
    return {
        "targets": [
            {
                "age": target.age,
                "weights": {
                    asset_class: _rate_to_json(rate) for asset_class, rate in target.weights.items()
                },
            }
            for target in allocation_policy.targets
        ]
    }


def to_json_dict(plan: Plan, portfolios: dict[str, Portfolio], target_ending_networth: Money) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan.plan_id,
        "name": plan.name,
        "user": {"birth_date": plan.user.birth_date.isoformat()},
        "assumptions": {"inflation_rate": _rate_to_json(plan.assumptions.inflation_rate)},
        "pension": {
            "national_pension_estimate_annual": _money_to_json(plan.pension.national_pension.estimate_annual),
            "employee_pension_estimate_annual": _money_to_json(plan.pension.employee_pension.estimate_annual),
            "claim_age": plan.pension.claim_timing.age,
        },
        "life_expectancy_age": plan.life_expectancy_age,
        "target_ending_networth": _money_to_json(target_ending_networth),
        "accounts": [_account_to_json(account, portfolios) for account in plan.accounts],
        "incomes": [_income_to_json(income) for income in plan.incomes],
        "expenses": (
            [_recurring_expense_to_json(expense) for expense in plan.expenses]
            + [_one_time_expense_to_json(one_time_expense) for one_time_expense in plan.one_time_expenses]
        ),
        "allocation_policy": _allocation_policy_to_json(plan.allocation_policy),
        "children": [
            {"child_id": child.child_id, "birth_date": child.birth_date.isoformat()} for child in plan.children
        ],
        "education_expenses": [
            {
                "band_id": band.band_id,
                "child_id": band.child_id,
                "category": band.category,
                "start_age": band.start_age,
                "end_age": band.end_age,
                "monthly_amount": _money_to_json(band.monthly_amount),
            }
            for band in plan.education_expenses
        ],
    }
