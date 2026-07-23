from __future__ import annotations

from dataclasses import dataclass

from core.domain.value_objects import Money, Rate


@dataclass
class Expense:
    expense_id: str
    category: str
    amount: Money
    growth_rate: Rate
