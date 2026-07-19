#!/bin/bash
# ダブルクリックで実行できるFIRE Navigatorのランチャー。
# 「スプレッドシートを読み込む→シミュレーション実行→結果を書き戻す」を一括で行う。

set -u

# このファイル自身の場所（=リポジトリルート）へ移動する。
# シンボリックリンク経由で開かれた場合も実体のパスを解決する。
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
REPO_ROOT="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
cd "$REPO_ROOT" || { echo "リポジトリのディレクトリに移動できませんでした: $REPO_ROOT"; read -n 1 -s -r -p "何かキーを押すと閉じます..."; exit 1; }

echo "作業ディレクトリ: $REPO_ROOT"
echo

if [ -f "$REPO_ROOT/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.venv/bin/activate"
  PYTHON_BIN="python3"
elif command -v python3 >/dev/null 2>&1; then
  echo "[注意] .venv が見つからなかったため、システムのpython3を使用します。"
  echo "       README.mdの「セットアップ」手順に従って仮想環境を作成することを推奨します。"
  echo
  PYTHON_BIN="python3"
else
  echo "[エラー] python3 が見つかりません。Python 3をインストールしてください。"
  read -n 1 -s -r -p "何かキーを押すと閉じます..."
  exit 1
fi

"$PYTHON_BIN" "$REPO_ROOT/scripts/run_full_simulation.py" "$@"
EXIT_CODE=$?

echo
if [ $EXIT_CODE -eq 0 ]; then
  echo "完了しました。このウィンドウは閉じても構いません。"
else
  echo "エラーが発生しました（終了コード: $EXIT_CODE）。上のログを確認してください。"
fi

read -n 1 -s -r -p "何かキーを押すと閉じます..."
echo
