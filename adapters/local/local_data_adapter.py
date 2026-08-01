"""ローカルのdata/plan.jsonを入出力先とするアダプタ。

adapters/sheets/sheets_input_adapter.pyが持っているフィールドごとの検証・デフォルト値ロジック
（成長率未入力→インフレ率、取得原価未入力→残高、年金見込額未入力→0円・受給開始年齢未入力→65歳等）を
踏襲しつつ、読み書き先をGoogle SheetsからローカルのJSONファイルに置き換える。

Sheetsアダプタと違い、単発支出/経常支出は`kind`（"recurring"|"one_time"）で明示的に区別する
（1つのシートを単発フラグ列で振り分けていたSheets版と異なり、JSON側は行の形自体を分けられるため）。
これにより、Sheets版で必要だった「使われない列に値が入っている」警告（collect_input_warnings）は
不要になる。該当kindで使えない項目が入っている場合は警告ではなくSchemaValidationErrorとして
拒否する（このJSONを作るのはWebフォームのみのため、不正な形が生まれるのはファイルの手編集時だけであり、
黙って無視するより早期に落とす方が分かりやすい）。

同様に、childrenを教育費バンドの行から都度組み立てる（同じchild_idの行でbirth_dateの食い違いを
チェックする）Sheets版の方式ではなく、childrenを独立したトップレベルの配列として持つ
（教育費バンドはchild_idで参照する）。
"""
from __future__ import annotations

import json
import os
from datetime import date
from decimal import InvalidOperation
from pathlib import Path
from typing import Optional, Union

from core.domain.account import Account, AccountType
from core.domain.allocation import AllocationPolicy, AllocationTarget
from core.domain.asset import Asset, AssetClass
from core.domain.child import Child
from core.domain.contribution_strategy import ContributionStrategy
from core.domain.education_expense import EducationExpenseBand
from core.domain.errors import SchemaValidationError
from core.domain.expense import Expense
from core.domain.holding import Holding
from core.domain.income import Income
from core.domain.one_time_expense import OneTimeExpense
from core.domain.pension import ClaimTiming, Pension, PensionEntitlement
from core.domain.plan import DEFAULT_LIFE_EXPECTANCY_AGE, Assumptions, Plan, StartCondition, StartConditionType
from core.domain.portfolio import Portfolio
from core.domain.tax_config import TaxConfig
from core.domain.user import User
from core.domain.value_objects import EventCondition, Money, Rate
from core.domain.withdrawal_strategy import WithdrawalStrategy
from repositories.asset_class_repository import load_asset_class_registry, load_asset_class_risk_order

DEFAULT_PLAN_FILE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "plan.json"

SCHEMA_VERSION = 1

EXPENSE_KIND_RECURRING = "recurring"
EXPENSE_KIND_ONE_TIME = "one_time"
_EXPENSE_KINDS = (EXPENSE_KIND_RECURRING, EXPENSE_KIND_ONE_TIME)

_RECURRING_ALLOWED_KEYS = {"expense_id", "category", "kind", "amount", "growth_rate", "start_condition", "end_condition"}
_ONE_TIME_ALLOWED_KEYS = {"expense_id", "category", "kind", "amount", "trigger"}

_CONDITION_TYPES = ("plan_start", "age", "date")


# --- 入力ミス検出用の共通ヘルパー（core/domain/errors.pyのSchemaValidationErrorを使う） -------------


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _require(data: dict, key: str, field_path: str) -> object:
    value = data.get(key)
    if _is_blank(value):
        raise SchemaValidationError(f"必須項目が未入力です（キー: {key}）", field_path)
    return value


def _parse_money(value: object, field_path: str) -> Money:
    try:
        return Money.of(value)
    except (InvalidOperation, ValueError, TypeError) as e:
        raise SchemaValidationError(f"金額として解釈できない値です: {value!r}", field_path) from e


def _parse_money_or_zero(value: object, field_path: str) -> Money:
    return Money.zero() if _is_blank(value) else _parse_money(value, field_path)


def _parse_rate(value: object, field_path: str) -> Rate:
    try:
        return Rate.of(value)
    except (InvalidOperation, ValueError, TypeError) as e:
        raise SchemaValidationError(f"割合として解釈できない値です: {value!r}", field_path) from e


def _parse_growth_rate(value: object, field_path: str, default_growth_rate: Rate) -> Rate:
    """成長率。未入力（null/空文字）の行はプラン設定のインフレ率を既定値として使う。"""

    return default_growth_rate if _is_blank(value) else _parse_rate(value, field_path)


def _parse_int(value: object, field_path: str) -> int:
    try:
        return int(value)
    except (ValueError, TypeError) as e:
        raise SchemaValidationError(f"整数として解釈できない値です: {value!r}", field_path) from e


def _parse_date_field(value: object, field_path: str) -> date:
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as e:
        raise SchemaValidationError(f"日付(YYYY-MM-DD形式)として解釈できない値です: {value!r}", field_path) from e


def _parse_enum(enum_cls, value: object, field_path: str):
    try:
        return enum_cls(value)
    except ValueError as e:
        allowed = ", ".join(member.value for member in enum_cls)
        raise SchemaValidationError(f"未知の値です: {value!r}（有効な値: {allowed}）", field_path) from e


def _parse_asset_class(value: object, field_path: str, asset_class_registry: dict[AssetClass, str]) -> AssetClass:
    code = str(value).strip()
    if code not in asset_class_registry:
        allowed = ", ".join(asset_class_registry.keys())
        raise SchemaValidationError(f"未知の資産クラスです: {code!r}（有効な値: {allowed}）", field_path)
    return code


def _build_event_condition(value: Optional[dict], field_path: str) -> Optional[EventCondition]:
    if value is None:
        return None
    if not isinstance(value, dict) or "type" not in value:
        raise SchemaValidationError(f"条件の形式が不正です: {value!r}", field_path)
    condition_type = value["type"]
    if condition_type == "plan_start":
        return EventCondition.plan_start()
    if condition_type == "age":
        return EventCondition.at_age(_parse_int(_require(value, "age", f"{field_path}.age"), f"{field_path}.age"))
    if condition_type == "date":
        raw = _require(value, "date", f"{field_path}.date")
        return EventCondition.at_date(_parse_date_field(raw, f"{field_path}.date"))
    allowed = ", ".join(_CONDITION_TYPES)
    raise SchemaValidationError(f"未知の条件タイプです: {condition_type!r}（有効な値: {allowed}）", field_path)


def _reject_unexpected_keys(row: dict, prefix: str, allowed: set[str]) -> None:
    unexpected = sorted(set(row.keys()) - allowed)
    if unexpected:
        raise SchemaValidationError(f"このkindでは使用できない項目です: {', '.join(unexpected)}", prefix)


# --- セクションごとのビルダー（Plan集約） -------------------------------------------------------


def _build_user(data: dict) -> User:
    """配偶者(user.spouse)は任意入力。フォームは常に{birth_date: ...}の形で送ってくるが、
    他の任意項目（成長率・拠出額等）と同じく空欄（null/空文字）は「配偶者なし」として扱う
    （オブジェクトごとnullにする方式にすると、フォーム側でチェックボックスの出し分けが
    必要になり複雑になるため）。
    """

    user_data = data.get("user") or {}
    spouse_data = user_data.get("spouse") or {}
    spouse_birth_date = spouse_data.get("birth_date")
    spouse = (
        None
        if _is_blank(spouse_birth_date)
        else User(birth_date=_parse_date_field(spouse_birth_date, "user.spouse.birth_date"))
    )
    return User(
        birth_date=_parse_date_field(_require(user_data, "birth_date", "user.birth_date"), "user.birth_date"),
        spouse=spouse,
    )


def _build_assumptions(data: dict) -> Assumptions:
    assumptions_data = data.get("assumptions") or {}
    return Assumptions(
        inflation_rate=_parse_rate(
            _require(assumptions_data, "inflation_rate", "assumptions.inflation_rate"),
            "assumptions.inflation_rate",
        )
    )


def _check_no_duplicate_account_ids(data: dict) -> None:
    """account_idの重複を検出する。

    Portfolio Aggregate（build_portfolios_from_local_file）はaccount_idをキーにした
    dictとして組み立てるため、複数行が同じaccount_idを持つと後の行が前の行を無言で
    上書きしてしまい、その口座の残高がシミュレーション全体から丸ごと消える
    （現在の純資産等の表示が実際より少なくなる、というだけでなく、取り崩し・成長計算
    からも完全に抜け落ちる）。事故を未然に防ぐため、構造的な入力エラーとして早期に拒否する。
    """

    first_seen_index: dict[str, int] = {}
    for index, row in enumerate(data.get("accounts") or []):
        account_id = row.get("account_id")
        if _is_blank(account_id):
            continue  # 未入力は_require側で別途エラーになるためここでは対象外
        account_id = str(account_id)
        if account_id in first_seen_index:
            raise SchemaValidationError(
                f"口座IDが{first_seen_index[account_id]}行目と重複しています: {account_id!r}"
                "（口座IDは一意である必要があります。重複したまま実行すると、後の行が前の行を"
                "上書きしてその口座の残高がシミュレーションから消えます）",
                f"accounts[{index}].account_id",
            )
        first_seen_index[account_id] = index


def _build_accounts(data: dict) -> list[Account]:
    _check_no_duplicate_account_ids(data)
    accounts = []
    for index, row in enumerate(data.get("accounts") or []):
        prefix = f"accounts[{index}]"
        account_id = str(_require(row, "account_id", f"{prefix}.account_id"))
        monthly_contribution_raw = row.get("monthly_contribution")
        accounts.append(
            Account(
                account_id=account_id,
                account_type=_parse_enum(
                    AccountType, _require(row, "account_type", f"{prefix}.account_type"), f"{prefix}.account_type"
                ),
                monthly_contribution=(
                    None if _is_blank(monthly_contribution_raw)
                    else _parse_money(monthly_contribution_raw, f"{prefix}.monthly_contribution")
                ),
            )
        )
    return accounts


def build_portfolios_from_local_file(
    data: dict, asset_class_registry: Optional[dict[AssetClass, str]] = None
) -> dict[str, Portfolio]:
    """Portfolio Aggregate（account_idで参照される独立集約）をaccounts配列から組み立てる。

    asset_class_registryは資産クラス識別子の妥当性検証に使う（省略時はconfig/asset_classes.yamlを
    読み込む）。
    """

    if asset_class_registry is None:
        asset_class_registry = load_asset_class_registry()

    _check_no_duplicate_account_ids(data)
    portfolios: dict[str, Portfolio] = {}
    for index, row in enumerate(data.get("accounts") or []):
        prefix = f"accounts[{index}]"
        account_id = str(_require(row, "account_id", f"{prefix}.account_id"))
        asset = Asset(
            asset_class=_parse_asset_class(
                _require(row, "asset_class", f"{prefix}.asset_class"), f"{prefix}.asset_class", asset_class_registry
            ),
            expected_return=_parse_rate(
                _require(row, "expected_return", f"{prefix}.expected_return"), f"{prefix}.expected_return"
            ),
        )
        current_value = _parse_money_or_zero(row.get("current_value"), f"{prefix}.current_value")
        cost_basis_raw = row.get("cost_basis")
        # 取得原価が未入力の場合は残高と同額とみなす（開始時点の含み益ゼロという後方互換のデフォルト）
        cost_basis = current_value if _is_blank(cost_basis_raw) else _parse_money(cost_basis_raw, f"{prefix}.cost_basis")
        holding = Holding(asset=asset, quantity=1, current_value=current_value, cost_basis=cost_basis)
        portfolios[account_id] = Portfolio(holdings=[holding])
    return portfolios


def _build_allocation_policy(
    data: dict,
    asset_class_registry: Optional[dict[AssetClass, str]] = None,
    asset_class_risk_order: Optional[list[AssetClass]] = None,
) -> Optional[AllocationPolicy]:
    """年齢別の目標配分比率（プラン全体で1つ、口座横断）をallocation_policyセクションから組み立てる。

    allocation_policyキーが存在しない（null）場合はNoneを返す（資産配分比率の可変対応・月次
    リバランスはオプション機能）。
    """

    allocation_data = data.get("allocation_policy")
    if allocation_data is None:
        return None

    if asset_class_registry is None:
        asset_class_registry = load_asset_class_registry()
    if asset_class_risk_order is None:
        asset_class_risk_order = load_asset_class_risk_order()

    targets = []
    for index, row in enumerate(allocation_data.get("targets") or []):
        prefix = f"allocation_policy.targets[{index}]"
        age = _parse_int(_require(row, "age", f"{prefix}.age"), f"{prefix}.age")
        weights_raw = _require(row, "weights", f"{prefix}.weights")
        for asset_class_code in weights_raw:
            _parse_asset_class(asset_class_code, f"{prefix}.weights", asset_class_registry)

        # weightsのキー順は、config/asset_classes.yamlのrisk_rank順（リスクが高い資産クラスが
        # 先）に正規化する（入力JSONのキー順そのままだと、手編集やフォーム再保存のたびに
        # 順序が変わりうる）。core/simulation/withdrawal/withdrawal_engine.pyのオーバーウェイト
        # 優先売却はtarget_weightsの辞書順で資産クラスを走査するため、複数の資産クラスが同時に
        # オーバーウェイトな場合、この順序がどちらを先に取り崩すかを決める
        # （リスクが高い資産クラスの含み益を先に確定させる、という方針）。
        weights: dict[AssetClass, Rate] = {}
        for asset_class_code in asset_class_risk_order:
            if asset_class_code in weights_raw:
                weights[asset_class_code] = _parse_rate(
                    weights_raw[asset_class_code], f"{prefix}.weights.{asset_class_code}"
                )
        targets.append(AllocationTarget(age=age, weights=weights))
    targets.sort(key=lambda target: target.age)
    return AllocationPolicy(targets=targets)


def _build_children_and_education_expenses(data: dict) -> tuple[list[Child], list[EducationExpenseBand]]:
    """子供の一覧と年齢帯別の教育費をchildren/education_expensesセクションから組み立てる。

    Sheets版と異なりchildrenは独立したトップレベル配列で持つため、education_expenses側の行が
    参照するchild_idがchildrenに存在するかだけを検証する（Sheets版のような「同じchild_idの行で
    birth_dateが食い違う」チェックは、そもそも1箇所にしかbirth_dateがないため不要）。
    """

    children = []
    for index, row in enumerate(data.get("children") or []):
        prefix = f"children[{index}]"
        children.append(
            Child(
                child_id=str(_require(row, "child_id", f"{prefix}.child_id")),
                birth_date=_parse_date_field(
                    _require(row, "birth_date", f"{prefix}.birth_date"), f"{prefix}.birth_date"
                ),
            )
        )
    child_ids = {child.child_id for child in children}

    bands = []
    for index, row in enumerate(data.get("education_expenses") or []):
        prefix = f"education_expenses[{index}]"
        child_id = str(_require(row, "child_id", f"{prefix}.child_id"))
        if child_id not in child_ids:
            raise SchemaValidationError(f"childrenに存在しないchild_idです: {child_id!r}", f"{prefix}.child_id")
        start_condition = _build_event_condition(row.get("start_condition"), f"{prefix}.start_condition")
        if start_condition is None:
            raise SchemaValidationError("start_conditionが必須です", f"{prefix}.start_condition")
        end_condition = _build_event_condition(row.get("end_condition"), f"{prefix}.end_condition")
        if end_condition is None:
            raise SchemaValidationError("end_conditionが必須です", f"{prefix}.end_condition")
        bands.append(
            EducationExpenseBand(
                band_id=str(_require(row, "band_id", f"{prefix}.band_id")),
                child_id=child_id,
                category=str(_require(row, "category", f"{prefix}.category")),
                start_condition=start_condition,
                end_condition=end_condition,
                monthly_amount=_parse_money_or_zero(row.get("monthly_amount"), f"{prefix}.monthly_amount"),
            )
        )
    return children, bands


def _build_incomes(data: dict, default_growth_rate: Rate) -> list[Income]:
    """収入一覧をincomesセクションから組み立てる。

    成長率が未入力の行は、プラン設定のインフレ率(default_growth_rate)を既定値として使う。
    """

    incomes = []
    for index, row in enumerate(data.get("incomes") or []):
        prefix = f"incomes[{index}]"
        start_condition = _build_event_condition(row.get("start_condition"), f"{prefix}.start_condition")
        if start_condition is None:
            raise SchemaValidationError("start_conditionが必須です", f"{prefix}.start_condition")
        end_condition = _build_event_condition(row.get("end_condition"), f"{prefix}.end_condition")
        incomes.append(
            Income(
                income_id=str(_require(row, "income_id", f"{prefix}.income_id")),
                source=str(_require(row, "source", f"{prefix}.source")),
                amount=_parse_money_or_zero(row.get("amount"), f"{prefix}.amount"),
                growth_rate=_parse_growth_rate(row.get("growth_rate"), f"{prefix}.growth_rate", default_growth_rate),
                start_condition=start_condition,
                end_condition=end_condition,
            )
        )
    return incomes


def _build_expenses(data: dict, default_growth_rate: Rate) -> tuple[list[Expense], list[OneTimeExpense]]:
    """経常支出と単発支出をexpensesセクションから組み立てる。

    各行のkind（"recurring"|"one_time"）で振り分ける。経常支出の成長率が未入力の行は、
    プラン設定のインフレ率(default_growth_rate)を既定値として使う。
    """

    expenses = []
    one_time_expenses = []
    for index, row in enumerate(data.get("expenses") or []):
        prefix = f"expenses[{index}]"
        expense_id = str(_require(row, "expense_id", f"{prefix}.expense_id"))
        category = str(_require(row, "category", f"{prefix}.category"))
        kind = _require(row, "kind", f"{prefix}.kind")
        if kind not in _EXPENSE_KINDS:
            raise SchemaValidationError(
                f"未知のkindです: {kind!r}（有効な値: {', '.join(_EXPENSE_KINDS)}）", f"{prefix}.kind"
            )

        if kind == EXPENSE_KIND_ONE_TIME:
            _reject_unexpected_keys(row, prefix, _ONE_TIME_ALLOWED_KEYS)
            amount = _parse_money_or_zero(row.get("amount"), f"{prefix}.amount")
            trigger = _build_event_condition(row.get("trigger"), f"{prefix}.trigger")
            if trigger is None:
                raise SchemaValidationError("triggerが必須です（kind=one_timeの行）", f"{prefix}.trigger")
            one_time_expenses.append(
                OneTimeExpense(expense_id=expense_id, category=category, amount=amount, trigger=trigger)
            )
        else:
            _reject_unexpected_keys(row, prefix, _RECURRING_ALLOWED_KEYS)
            amount = _parse_money_or_zero(row.get("amount"), f"{prefix}.amount")
            growth_rate = _parse_growth_rate(row.get("growth_rate"), f"{prefix}.growth_rate", default_growth_rate)
            start_condition = _build_event_condition(row.get("start_condition"), f"{prefix}.start_condition")
            end_condition = _build_event_condition(row.get("end_condition"), f"{prefix}.end_condition")
            expenses.append(
                Expense(
                    expense_id=expense_id,
                    category=category,
                    amount=amount,
                    growth_rate=growth_rate,
                    start_condition=start_condition,
                    end_condition=end_condition,
                )
            )
    return expenses, one_time_expenses


def _default_tax_config() -> TaxConfig:
    # spouse_deduction はここでは常に有効にしておき、実際に適用されるかどうかは
    # tax_engine.calculate_tax()内のhas_spouse（plan.user.spouseの有無）の方だけで
    # 決まるようにする（deduction_settingsという別スイッチをユーザー入力に露出させない）。
    return TaxConfig(deduction_settings={"spouse_deduction": True})


def _build_pension(data: dict) -> Pension:
    """pensionセクションからPensionを組み立てる。すべて任意入力。

    未入力の項目は年金見込額ゼロ・標準65歳受給という後方互換のデフォルトを使う。
    """

    pension_data = data.get("pension") or {}
    national_raw = pension_data.get("national_pension_estimate_annual")
    employee_raw = pension_data.get("employee_pension_estimate_annual")
    claim_age_raw = pension_data.get("claim_age")

    national_amount = (
        Money.zero() if _is_blank(national_raw)
        else _parse_money(national_raw, "pension.national_pension_estimate_annual")
    )
    employee_amount = (
        Money.zero() if _is_blank(employee_raw)
        else _parse_money(employee_raw, "pension.employee_pension_estimate_annual")
    )
    claim_age = 65 if _is_blank(claim_age_raw) else _parse_int(claim_age_raw, "pension.claim_age")

    return Pension(
        national_pension=PensionEntitlement(estimate_annual=national_amount),
        employee_pension=PensionEntitlement(estimate_annual=employee_amount),
        claim_timing=ClaimTiming(age=claim_age),
    )


def _build_life_expectancy_age(data: dict) -> int:
    """想定寿命（任意入力）を読み込む。未入力ならDEFAULT_LIFE_EXPECTANCY_AGE(100歳)。"""

    raw = data.get("life_expectancy_age")
    return DEFAULT_LIFE_EXPECTANCY_AGE if _is_blank(raw) else _parse_int(raw, "life_expectancy_age")


def read_target_ending_networth(data: dict) -> Money:
    """目標資産（想定寿命時点、任意入力）を読み込む。未入力なら0円。

    ダッシュボードの逆算機能でのみ使う値のため、Plan集約には含めない。
    """

    raw = data.get("target_ending_networth")
    return Money.zero() if _is_blank(raw) else _parse_money(raw, "target_ending_networth")


def _default_withdrawal_strategy() -> WithdrawalStrategy:
    return WithdrawalStrategy(
        order=[
            AccountType.CASH,
            AccountType.TAXABLE,
            AccountType.NISA_GROWTH,
            AccountType.NISA_TSUMITATE,
            AccountType.ZAIKEI,
            AccountType.IDECO,
            AccountType.COMPANY_DC,
        ]
    )


def _default_contribution_strategy() -> ContributionStrategy:
    return ContributionStrategy(
        order=[
            AccountType.CASH,
            AccountType.NISA_GROWTH,
            AccountType.NISA_TSUMITATE,
            AccountType.IDECO,
            AccountType.COMPANY_DC,
            AccountType.ZAIKEI,
            AccountType.TAXABLE,
        ],
        emergency_fund_target=Money.of(1_000_000),
    )


def build_plan_from_local_file(data: dict) -> Plan:
    user = _build_user(data)
    assumptions = _build_assumptions(data)
    expenses, one_time_expenses = _build_expenses(data, assumptions.inflation_rate)
    children, education_expenses = _build_children_and_education_expenses(data)

    return Plan(
        plan_id=str(_require(data, "plan_id", "plan_id")),
        name=str(_require(data, "name", "name")),
        user=user,
        start_condition=StartCondition(StartConditionType.TODAY),
        assumptions=assumptions,
        accounts=_build_accounts(data),
        tax_config=_default_tax_config(),
        pension=_build_pension(data),
        withdrawal_strategy=_default_withdrawal_strategy(),
        contribution_strategy=_default_contribution_strategy(),
        incomes=_build_incomes(data, assumptions.inflation_rate),
        expenses=expenses,
        allocation_policy=_build_allocation_policy(data),
        children=children,
        education_expenses=education_expenses,
        one_time_expenses=one_time_expenses,
        life_expectancy_age=_build_life_expectancy_age(data),
    )


# --- ファイルI/O ---------------------------------------------------------------------------------


def load_raw(path: Union[str, Path] = DEFAULT_PLAN_FILE_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_plan(path: Union[str, Path] = DEFAULT_PLAN_FILE_PATH) -> Plan:
    return build_plan_from_local_file(load_raw(path))


def load_portfolios(path: Union[str, Path] = DEFAULT_PLAN_FILE_PATH) -> dict[str, Portfolio]:
    return build_portfolios_from_local_file(load_raw(path))


def load_target_ending_networth(path: Union[str, Path] = DEFAULT_PLAN_FILE_PATH) -> Money:
    return read_target_ending_networth(load_raw(path))


def save_plan(data: dict, path: Union[str, Path] = DEFAULT_PLAN_FILE_PATH) -> None:
    """dataを検証してからpathへ保存する。

    壊れた入力でplan.jsonを上書きしないよう、書き込み前に必ずbuild_plan_from_local_file()と
    build_portfolios_from_local_file()の両方の検証を通す（前者だけだとasset_class/expected_return等、
    Portfolio側だけの項目の検証漏れが起こるため）。

    クラッシュ・ディスクフル等でファイルが空になったり壊れたりしないよう、一時ファイルに
    書き込んでからos.replace()で置き換える（アトミックな書き込み）。
    """

    build_plan_from_local_file(data)
    build_portfolios_from_local_file(data)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp_path, path)
