from __future__ import annotations

from decimal import Decimal

from core.domain.asset import AssetClass
from core.domain.plan import Plan
from core.domain.portfolio import Portfolio


def compute_asset_class_weights(plan: Plan, portfolios: dict[str, Portfolio]) -> dict[AssetClass, Decimal]:
    """Planの口座構成から、資産クラスごとの残高比率を算出する。Monte Carlo/Historical Engineの
    双方が、資産クラスごとにサンプリング・実績再生したリターンを、このプラン固有の配分比率で
    加重平均し、Projection Engineが受け取れる単一の年次成長率へ変換する際に使う。
    """

    totals: dict[AssetClass, Decimal] = {}
    grand_total = Decimal(0)
    for account in plan.accounts:
        portfolio = portfolios.get(account.account_id)
        if portfolio is None:
            continue
        for holding in portfolio.holdings:
            amount = holding.cost_basis.amount
            totals[holding.asset.asset_class] = totals.get(holding.asset.asset_class, Decimal(0)) + amount
            grand_total += amount

    if grand_total == 0:
        return {}
    return {asset_class: total / grand_total for asset_class, total in totals.items()}
