"""実行履歴（軽量な結果サマリー）をdata/history.jsonへ保存・読み込みするアダプタ。

過去の実行結果と現在の結果を見比べられる「前回実行との比較」機能で使う。プランの入力
そのものは保存しない（あくまでKPI等の要約のみ、reports.output_builder.build_history_entry
が組み立てる）。data/plan.jsonと違い1件のオブジェクトではなく配列で、実行するたびに
末尾へ追記する。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Union

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_HISTORY_FILE_PATH = REPO_ROOT / "data" / "history.json"

# 際限なく肥大化しないよう、直近の実行だけを残す（軽量な比較用途のため、長期のアーカイブは
# 目的としない）。
MAX_HISTORY_ENTRIES = 50


def load_history(path: Union[str, Path] = DEFAULT_HISTORY_FILE_PATH) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def append_history_entry(entry: dict, path: Union[str, Path] = DEFAULT_HISTORY_FILE_PATH) -> None:
    """entryを履歴の末尾に追記する。MAX_HISTORY_ENTRIESを超えた古い履歴は先頭から削除する。

    data/plan.jsonのsave_plan()と同じく、一時ファイル経由のアトミックな書き込みにする
    （クラッシュ等で履歴ファイルが壊れないように）。
    """

    entries = load_history(path)
    entries.append(entry)
    if len(entries) > MAX_HISTORY_ENTRIES:
        entries = entries[-MAX_HISTORY_ENTRIES:]

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp_path, path)
