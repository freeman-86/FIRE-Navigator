#!/bin/bash
# ダブルクリックで実行できるFIRE Navigatorのランチャー。
# ローカルサーバーを起動し、ブラウザでダッシュボードを開く。

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

# venv内のpython3を「場所」で直接指定する（sourceでactivateしない）。
# activateスクリプトはvenv作成時のパスを内部に記録しているため、
# リポジトリフォルダを移動した後にsourceすると壊れて誤ったpython3
# （システム側）を掴んでしまうことがある。実行ファイルのパスを直接
# 指定すればフォルダを移動しても常に正しいvenvのpython3が使われる。
if [ -x "$REPO_ROOT/.venv/bin/python3" ]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python3"
elif [ -x "$REPO_ROOT/venv/bin/python3" ]; then
  PYTHON_BIN="$REPO_ROOT/venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
  echo "[注意] 仮想環境（.venv）が見つからなかったため、システムのpython3を使用します。"
  echo "       README.mdの「セットアップ」手順に従って仮想環境を作成することを推奨します。"
  echo
  PYTHON_BIN="python3"
else
  echo "[エラー] python3 が見つかりません。Python 3をインストールしてください。"
  read -n 1 -s -r -p "何かキーを押すと閉じます..."
  exit 1
fi

PORT=5001
echo "ローカルサーバーを起動しています（ポート ${PORT}）..."
"$PYTHON_BIN" "$REPO_ROOT/web/app.py" --port "$PORT" &
SERVER_PID=$!

# このウィンドウが閉じられた（キー入力・Cmd+W・Terminal終了等）場合に、
# バックグラウンドで起動したサーバーを道連れで確実に終了させる。
trap 'kill "$SERVER_PID" 2>/dev/null' EXIT INT TERM

# サーバーの起動を待ってからブラウザを開く（起動失敗の取りこぼしも軽くチェックする）。
STARTED=0
for _ in $(seq 1 30); do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    break
  fi
  if curl -s -o /dev/null "http://127.0.0.1:$PORT/"; then
    STARTED=1
    break
  fi
  sleep 0.5
done

if [ "$STARTED" -ne 1 ]; then
  echo "[エラー] サーバーの起動に失敗しました。上のログを確認してください。"
  read -n 1 -s -r -p "何かキーを押すと閉じます..."
  exit 1
fi

open "http://127.0.0.1:${PORT}/"

echo
echo "ブラウザでダッシュボードを開きました: http://127.0.0.1:${PORT}/"
echo "このウィンドウを開いたままにしてください（サーバーが動作中です）。"
read -n 1 -s -r -p "何かキーを押すとサーバーを停止して閉じます..."
echo
