from core.domain.pension import PensionRules
from core.domain.value_objects import Rate


def zero_pension_rules() -> PensionRules:
    """繰上げ/繰下げの増減率をゼロにしたテスト用フィクスチャ。年金額はestimate_annual側で0にするのが基本だが、
    yaml読込に依存せずrun_projection()を呼べるようにするための最小限のダミー値。
    """

    return PensionRules(
        standard_claim_age=65,
        earliest_claim_age=60,
        latest_claim_age=75,
        early_reduction_rate_per_month=Rate.zero(),
        deferred_increase_rate_per_month=Rate.zero(),
    )
