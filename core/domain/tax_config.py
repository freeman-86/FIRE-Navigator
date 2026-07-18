from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.domain.user import Prefecture


@dataclass
class TaxConfig:
    residence: Prefecture
    deduction_settings: dict[str, Any] = field(default_factory=dict)
    tax_year_config_ref: str = ""
