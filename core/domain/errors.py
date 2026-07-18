from __future__ import annotations


class FireNavigatorError(Exception):
    """全てのカスタム例外の共通基底。「どのフィールドで」「何が」問題かをfield_pathとして構造化して持つ
    （設計書11章 エラーハンドリング。Explainabilityの一部）。
    """

    def __init__(self, message: str, field_path: str):
        super().__init__(f"{field_path}: {message}")
        self.message = message
        self.field_path = field_path


class StructuralInputError(FireNavigatorError):
    """入力ミス（型不一致・書式崩れ・必須項目不足）。Sheets Adapter層で検出する。"""


class SchemaValidationError(FireNavigatorError):
    """スキーマ検証エラー（必須項目不足・型エラー）。JSON Adapter層で検出する想定。"""


class SemanticValidationError(FireNavigatorError):
    """意味的エラー（例：退職年齢が現在年齢より若い）。Validation Service層で検出する。"""


class ConfigInconsistencyError(FireNavigatorError):
    """税制設定矛盾等、config参照の不整合。Validation Service + 各Engineで検出する。"""


class SimulationExecutionError(FireNavigatorError):
    """シミュレーション実行時エラー。"""
