from __future__ import annotations

from core.domain.simulation_result import SimulationResult
from core.simulation.projection.projection_engine import UNALLOCATED_SURPLUS_KEY


def is_successful(trial: SimulationResult) -> bool:
    """計画期間中、unallocated_surplus（資金枯渇シグナル。Sprint8のWithdrawal Engine参照）が
    一度もマイナスにならなければ「成功」と判定する。
    """

    return all(
        not projection.account_balances[UNALLOCATED_SURPLUS_KEY].is_negative
        for projection in trial.yearly_projections
    )
