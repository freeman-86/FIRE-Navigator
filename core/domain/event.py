from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.domain.value_objects import EventCondition


@runtime_checkable
class ConditionalEvent(Protocol):
    """状態条件を満たした時に発生するEvent（v1.1 Event Architecture 8.2）の構造的型。

    Sprint7では型階層を最小限にとどめ、Milestone等の既存クラスのフィールドを
    変更せずに「trigger: EventConditionを持つ型はConditionalEventとして扱える」
    という構造的部分型のみを導入する。OneTimeEvent/RecurringEvent/Event Queue/
    優先順位テーブルの本格導入はSprint8以降。
    """

    trigger: EventCondition
