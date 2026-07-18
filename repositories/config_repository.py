from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import yaml

from core.domain.account import AccountType
from core.domain.portfolio_rules import AccountRules, PortfolioRules
from core.domain.tax_config import (
    EmploymentIncomeDeductionBracket,
    IncomeTaxBracket,
    IncomeTaxRules,
    ResidentTaxRules,
    SocialInsuranceRules,
    TaxRules,
)
from core.domain.value_objects import Money, Rate

DEFAULT_TAX_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "tax_2026.yaml"
DEFAULT_PORTFOLIO_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "portfolio_2026.yaml"


def load_tax_rules(config_path: Union[str, Path] = DEFAULT_TAX_CONFIG_PATH) -> TaxRules:
    """tax.yamlを読み込み、core.domainの値オブジェクト(Money/Rate)に変換したTaxRulesを返す。

    yaml読込を行うのはこの関数のみ。core/simulation側はyamlを直接読まず、
    ここで変換済みのTaxRulesを受け取るだけにする（設計書3.2 依存方向の原則）。
    """

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    income_tax_raw = raw["income_tax"]

    brackets = [
        IncomeTaxBracket(upper_bound=_money_or_none(b["upper_bound"]), rate=Rate.of(b["rate"]))
        for b in income_tax_raw["brackets"]
    ]
    employment_income_deduction_brackets = [
        EmploymentIncomeDeductionBracket(
            upper_bound=_money_or_none(b["upper_bound"]),
            rate=Rate.of(b["rate"]),
            base_amount=Money.of(b["base_amount"]),
        )
        for b in income_tax_raw["employment_income_deduction"]
    ]
    income_tax_rules = IncomeTaxRules(
        brackets=brackets,
        employment_income_deduction_brackets=employment_income_deduction_brackets,
        basic_deduction=Money.of(income_tax_raw["basic_deduction"]),
        spouse_deduction=Money.of(income_tax_raw["spouse_deduction"]),
    )

    resident_tax_raw = raw["resident_tax"]
    resident_tax_rules = ResidentTaxRules(
        flat_rate=Rate.of(resident_tax_raw["flat_rate"]),
        per_capita_levy=Money.of(resident_tax_raw["per_capita_levy"]),
    )

    social_insurance_raw = raw["social_insurance"]
    social_insurance_rules = SocialInsuranceRules(
        health_insurance_rate=Rate.of(social_insurance_raw["health_insurance_rate"]),
        pension_insurance_rate=Rate.of(social_insurance_raw["pension_insurance_rate"]),
        employment_insurance_rate=Rate.of(social_insurance_raw["employment_insurance_rate"]),
    )

    return TaxRules(
        income_tax=income_tax_rules,
        resident_tax=resident_tax_rules,
        social_insurance=social_insurance_rules,
    )


def load_portfolio_rules(config_path: Union[str, Path] = DEFAULT_PORTFOLIO_CONFIG_PATH) -> PortfolioRules:
    """portfolio.yamlを読み込み、口座タイプ別の拠出上限・非課税判定をPortfolioRulesとして返す。"""

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    rules_by_account_type = {
        AccountType(account_type_key): AccountRules(
            annual_limit=_money_or_none(entry["annual_limit"]),
            lifetime_limit=_money_or_none(entry["lifetime_limit"]),
            tax_free=bool(entry["tax_free"]),
        )
        for account_type_key, entry in raw["account_types"].items()
    }

    return PortfolioRules(rules_by_account_type=rules_by_account_type)


def _money_or_none(value: Optional[float]) -> Optional[Money]:
    return Money.of(value) if value is not None else None
