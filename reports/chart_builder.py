from __future__ import annotations

from core.domain.plan import Plan
from core.domain.simulation_result import SimulationResult

NETWORTH_CHART_TYPE = "stacked_area"


def build_networth_chart(plan: Plan, simulation_result: SimulationResult) -> dict:
    """SimulationResultから、口座種別ごとに積み上げたネットワース推移のグラフ系列データを生成する。

    account_balancesのキー（account_id）をaccount_typeへ変換して集計する。
    Projection Engineが加算する「unallocated_surplus」（配分ルール未確定の余剰）は
    どの口座種別にも属さないため、そのまま独立した系列として扱う。
    v1.1システムアーキテクチャ設計書のOutput JSON `charts.networth_chart` 形式に準拠する。
    """

    account_type_by_id = {account.account_id: account.account_type.value for account in plan.accounts}

    x = [projection.year for projection in simulation_result.yearly_projections]

    series_names: list[str] = []
    yearly_group_totals: list[dict[str, int]] = []
    for projection in simulation_result.yearly_projections:
        group_totals: dict[str, int] = {}
        for account_id, balance in projection.account_balances.items():
            series_name = account_type_by_id.get(account_id, account_id)
            group_totals[series_name] = group_totals.get(series_name, 0) + int(balance.amount)
            if series_name not in series_names:
                series_names.append(series_name)
        yearly_group_totals.append(group_totals)

    series = [
        {
            "name": series_name,
            "values": [group_totals.get(series_name, 0) for group_totals in yearly_group_totals],
        }
        for series_name in series_names
    ]

    return {"type": NETWORTH_CHART_TYPE, "x": x, "series": series}
