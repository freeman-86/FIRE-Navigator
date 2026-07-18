from __future__ import annotations

from datetime import date
from typing import Optional

from core.domain.errors import ConfigInconsistencyError, FireNavigatorError, SemanticValidationError
from core.domain.milestone import MilestoneType
from core.domain.pension import PensionRules
from core.domain.plan import Plan
from core.domain.value_objects import EventConditionType


def validate_plan(
    plan: Plan,
    pension_rules: Optional[PensionRules] = None,
    reference_date: Optional[date] = None,
) -> list[FireNavigatorError]:
    """値としては妥当だが意味的に矛盾しているケースを検出する（設計書11.1のSemanticValidationError
    ／ConfigInconsistencyError）。Sheets Adapter層のStructuralInputError（型不一致・必須項目欠落）
    とは別の検出層。見つかったエラーを一覧で返し、最初の1件で止めない。
    """

    reference_date = reference_date or date.today()
    errors: list[FireNavigatorError] = []

    errors.extend(_validate_retirement_age(plan, reference_date))
    errors.extend(_validate_spouse_birth_date(plan, reference_date))
    errors.extend(_validate_pension_claim_age(plan, pension_rules))
    errors.extend(_validate_milestone_multiples(plan))

    return errors


def _validate_retirement_age(plan: Plan, reference_date: date) -> list[FireNavigatorError]:
    current_age = plan.user.age_at(reference_date).years
    errors: list[FireNavigatorError] = []
    for milestone in plan.milestones:
        if milestone.milestone_type != MilestoneType.RETIREMENT:
            continue
        if milestone.trigger.condition_type != EventConditionType.AGE:
            continue
        if milestone.trigger.age < current_age:
            errors.append(
                SemanticValidationError(
                    f"退職年齢({milestone.trigger.age}歳)が現在の年齢({current_age}歳)より若く設定されています",
                    f"milestones[{milestone.milestone_id}].trigger.age",
                )
            )
    return errors


def _validate_spouse_birth_date(plan: Plan, reference_date: date) -> list[FireNavigatorError]:
    if plan.user.spouse is not None and plan.user.spouse.birth_date > reference_date:
        return [SemanticValidationError("配偶者の生年月日が未来の日付になっています", "user.spouse.birth_date")]
    return []


def _validate_pension_claim_age(plan: Plan, pension_rules: Optional[PensionRules]) -> list[FireNavigatorError]:
    if pension_rules is None:
        return []
    claim_age = plan.pension.claim_timing.age
    if pension_rules.earliest_claim_age <= claim_age <= pension_rules.latest_claim_age:
        return []
    return [
        ConfigInconsistencyError(
            f"年金受給開始年齢({claim_age}歳)が制度上の範囲"
            f"({pension_rules.earliest_claim_age}〜{pension_rules.latest_claim_age}歳)外です",
            "pension.claim_timing.age",
        )
    ]


def _validate_milestone_multiples(plan: Plan) -> list[FireNavigatorError]:
    errors: list[FireNavigatorError] = []
    for milestone in plan.milestones:
        trigger = milestone.trigger
        if trigger.condition_type != EventConditionType.NETWORTH_MULTIPLE_OF_EXPENSE:
            continue
        if trigger.multiple is not None and trigger.multiple <= 0:
            errors.append(
                SemanticValidationError(
                    f"networth_multiple_of_expenseのmultipleは正の値である必要があります(現在値: {trigger.multiple})",
                    f"milestones[{milestone.milestone_id}].trigger.multiple",
                )
            )
    return errors
