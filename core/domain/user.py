from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from core.domain.value_objects import AgeAt


@dataclass
class User:
    birth_date: date
    spouse: Optional["User"] = None

    def age_at(self, reference_date: date) -> AgeAt:
        return AgeAt(self.birth_date, reference_date)
