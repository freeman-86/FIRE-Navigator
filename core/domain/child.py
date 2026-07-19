from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from core.domain.value_objects import AgeAt


@dataclass
class Child:
    child_id: str
    birth_date: date

    def age_at(self, reference_date: date) -> AgeAt:
        return AgeAt(self.birth_date, reference_date)
