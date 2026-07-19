from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import ClassVar, Optional, Union

Numeric = Union[int, float, str, Decimal]


def _to_decimal(value: Numeric) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@dataclass(frozen=True, slots=True)
class Money:
    """金額。Decimalで内部保持し、円未満の誤差混入を防ぐ。"""

    amount: Decimal
    currency: str = "JPY"

    def __post_init__(self) -> None:
        quantized = _to_decimal(self.amount).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        object.__setattr__(self, "amount", quantized)

    @classmethod
    def of(cls, amount: Numeric, currency: str = "JPY") -> "Money":
        return cls(_to_decimal(amount), currency)

    @classmethod
    def zero(cls, currency: str = "JPY") -> "Money":
        return cls(Decimal(0), currency)

    def _ensure_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError(f"通貨が一致しません: {self.currency} != {other.currency}")

    def __add__(self, other: "Money") -> "Money":
        self._ensure_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._ensure_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def __mul__(self, multiplier: Union["Rate", Numeric]) -> "Money":
        factor = multiplier.value if isinstance(multiplier, Rate) else _to_decimal(multiplier)
        return Money(self.amount * factor, self.currency)

    __rmul__ = __mul__

    def __lt__(self, other: "Money") -> bool:
        self._ensure_same_currency(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._ensure_same_currency(other)
        return self.amount <= other.amount

    def __gt__(self, other: "Money") -> bool:
        self._ensure_same_currency(other)
        return self.amount > other.amount

    def __ge__(self, other: "Money") -> bool:
        self._ensure_same_currency(other)
        return self.amount >= other.amount

    @property
    def is_negative(self) -> bool:
        return self.amount < 0

    def __str__(self) -> str:
        return f"{self.amount:,} {self.currency}"


@dataclass(frozen=True, slots=True)
class Rate:
    """割合。0.05のような生の小数を型として明示し、パーセント表記との変換ミスを防ぐ。"""

    value: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _to_decimal(self.value))

    @classmethod
    def of(cls, value: Numeric) -> "Rate":
        return cls(_to_decimal(value))

    @classmethod
    def from_percent(cls, percent: Numeric) -> "Rate":
        return cls(_to_decimal(percent) / Decimal(100))

    @classmethod
    def zero(cls) -> "Rate":
        return cls(Decimal(0))

    @property
    def percent(self) -> Decimal:
        return self.value * Decimal(100)

    def apply_to(self, money: Money) -> Money:
        return money * self

    def monthly_equivalent(self) -> "Rate":
        """年率としての自分自身と等価な複利になる月率を返す((1+r)^(1/12) - 1)。"""

        return Rate((Decimal(1) + self.value) ** (Decimal(1) / Decimal(12)) - Decimal(1))

    def __add__(self, other: "Rate") -> "Rate":
        return Rate(self.value + other.value)

    def __sub__(self, other: "Rate") -> "Rate":
        return Rate(self.value - other.value)

    def __neg__(self) -> "Rate":
        return Rate(-self.value)

    def __lt__(self, other: "Rate") -> bool:
        return self.value < other.value

    def __le__(self, other: "Rate") -> bool:
        return self.value <= other.value

    def __gt__(self, other: "Rate") -> bool:
        return self.value > other.value

    def __ge__(self, other: "Rate") -> bool:
        return self.value >= other.value

    def __str__(self) -> str:
        return f"{self.percent}%"


@dataclass(frozen=True, slots=True)
class AgeAt:
    """特定時点での年齢。生年月日からの年齢計算ロジックを一箇所に集約する。"""

    birth_date: date
    reference_date: date

    def __post_init__(self) -> None:
        if self.reference_date < self.birth_date:
            raise ValueError("reference_date は birth_date 以降である必要があります")

    @property
    def years(self) -> int:
        rd, bd = self.reference_date, self.birth_date
        years = rd.year - bd.year
        if (rd.month, rd.day) < (bd.month, bd.day):
            years -= 1
        return years

    @classmethod
    def today(cls, birth_date: date) -> "AgeAt":
        return cls(birth_date, date.today())


@dataclass(frozen=True, slots=True)
class FiscalYear:
    """年度（4月始まり）。暦年と会計年度のズレを吸収する。"""

    year: int

    START_MONTH: ClassVar[int] = 4

    @classmethod
    def from_date(cls, d: date) -> "FiscalYear":
        if d.month >= cls.START_MONTH:
            return cls(d.year)
        return cls(d.year - 1)

    @property
    def start_date(self) -> date:
        return date(self.year, self.START_MONTH, 1)

    @property
    def end_date(self) -> date:
        return date(self.year + 1, self.START_MONTH, 1) - date.resolution

    def contains(self, d: date) -> bool:
        return self.start_date <= d <= self.end_date

    def __str__(self) -> str:
        return f"FY{self.year}"


class EventConditionType(str, Enum):
    TODAY = "today"
    FIXED_DATE = "fixed_date"
    PLAN_START = "plan_start"
    AGE = "age"
    DATE = "date"
    NETWORTH_MULTIPLE_OF_EXPENSE = "networth_multiple_of_expense"


@dataclass(frozen=True, slots=True)
class EventCondition:
    """Milestone/Incomeの発生条件を統一的に表現する型。"""

    condition_type: EventConditionType
    age: Optional[int] = None
    date: Optional[date] = None
    multiple: Optional[float] = None

    def __post_init__(self) -> None:
        if self.condition_type == EventConditionType.AGE and self.age is None:
            raise ValueError("condition_type='age' には age が必須です")
        if self.condition_type in (EventConditionType.DATE, EventConditionType.FIXED_DATE) and self.date is None:
            raise ValueError(f"condition_type='{self.condition_type.value}' には date が必須です")
        if self.condition_type == EventConditionType.NETWORTH_MULTIPLE_OF_EXPENSE and self.multiple is None:
            raise ValueError("condition_type='networth_multiple_of_expense' には multiple が必須です")

    @classmethod
    def today(cls) -> "EventCondition":
        return cls(EventConditionType.TODAY)

    @classmethod
    def fixed_date(cls, d: date) -> "EventCondition":
        return cls(EventConditionType.FIXED_DATE, date=d)

    @classmethod
    def plan_start(cls) -> "EventCondition":
        return cls(EventConditionType.PLAN_START)

    @classmethod
    def at_age(cls, age: int) -> "EventCondition":
        return cls(EventConditionType.AGE, age=age)

    @classmethod
    def at_date(cls, d: date) -> "EventCondition":
        return cls(EventConditionType.DATE, date=d)

    @classmethod
    def networth_multiple_of_expense(cls, multiple: float) -> "EventCondition":
        return cls(EventConditionType.NETWORTH_MULTIPLE_OF_EXPENSE, multiple=multiple)
