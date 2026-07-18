from __future__ import annotations

from typing import Optional

from core.domain.portfolio_rules import AccountRules
from core.domain.value_objects import Money


def remaining_annual_room(rules: AccountRules, contributed_this_year: Money) -> Optional[Money]:
    if rules.annual_limit is None:
        return None
    remaining = rules.annual_limit - contributed_this_year
    return remaining if not remaining.is_negative else Money.zero()


def remaining_lifetime_room(rules: AccountRules, lifetime_contributed: Money) -> Optional[Money]:
    if rules.lifetime_limit is None:
        return None
    remaining = rules.lifetime_limit - lifetime_contributed
    return remaining if not remaining.is_negative else Money.zero()


def cap_contribution(
    desired: Money,
    rules: AccountRules,
    contributed_this_year: Money,
    lifetime_contributed: Money,
) -> Money:
    """annual_limit/lifetime_limitの両方を守れる範囲まで、希望拠出額を切り詰める。"""

    capped = desired if not desired.is_negative else Money.zero()

    annual_room = remaining_annual_room(rules, contributed_this_year)
    if annual_room is not None and capped > annual_room:
        capped = annual_room

    lifetime_room = remaining_lifetime_room(rules, lifetime_contributed)
    if lifetime_room is not None and capped > lifetime_room:
        capped = lifetime_room

    return capped
