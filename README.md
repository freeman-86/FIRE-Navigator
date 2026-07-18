# FIRE Navigator

日本の税制・社会保険料・NISA/iDeCo等の制度を反映した、手取りベースの資産形成シミュレーションエンジン。
Googleスプレッドシートを入出力UI（View）として使い、計算のSource of TruthはPythonエンジン側に置く
（「Engine First」という設計思想。詳細は `docs/` 配下の設計書を参照）。

## 現在の状態

MVP定義とロードマップ（`docs/FIRE_Navigator_MVP定義とロードマップ.md`）のSprint1〜10がすべて完了しています。

- 決定論的な年次シミュレーション（税引後キャッシュフロー、NISA/iDeCo等の口座別配分、取り崩し、公的年金の繰上げ/繰下げ）
- マイルストーン到達判定・シナリオ比較・感応度分析
- モンテカルロシミュレーション・ヒストリカルバックテスト（過去データ）・実績vs計画の比較
- 回帰テスト（`tests/regression/`）で保護された計算ロジック

## セットアップ

### 前提

- Python 3.13
- Google Cloud Platformのサービスアカウント（Google Sheets API / Drive APIを有効化したもの）

### 手順

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

1. GCPでサービスアカウントを作成し、認証キー（JSON）を発行する。
2. 発行したキーを `secrets/gsheets_credentials.json` として保存する（`secrets/` は `.gitignore` 対象）。
3. 動作確認用のGoogleスプレッドシートを作成し、サービスアカウントのメールアドレスに編集権限を付与する。
4. スプレッドシート名を `FIRE-Navigator-test` にする（`adapters/sheets/sheet_mapping.py` の `SPREADSHEET_NAME` で変更可能）。

## 使い方

すべてのスクリプトはリポジトリルートから `PYTHONPATH=.` を付けて実行する。

```bash
# サンプルデータをテスト用スプレッドシートに投入する
PYTHONPATH=. python3 scripts/seed_test_spreadsheet.py
```

シミュレーションの実行例（Plan読込 → 計算 → 結果をスプレッドシートへ書き戻す）:

```python
from adapters.sheets.sheets_input_adapter import build_client, open_spreadsheet, load_plan, load_portfolios
from adapters.sheets.sheets_output_adapter import write_networth_table, write_networth_breakdown_chart
from core.simulation.projection.projection_engine import run_projection
from repositories.config_repository import load_tax_rules, load_portfolio_rules, load_pension_rules
from reports.chart_builder import build_networth_chart

plan = load_plan()
portfolios = load_portfolios()
result = run_projection(plan, portfolios, load_tax_rules(), load_portfolio_rules(), load_pension_rules())

spreadsheet = open_spreadsheet(build_client())
write_networth_table(spreadsheet, result)
write_networth_breakdown_chart(spreadsheet, build_networth_chart(plan, result))
```

シナリオ比較・感応度分析・モンテカルロ・ヒストリカルバックテスト・Progress比較も同様に、
`adapters/sheets/sheets_input_adapter.py` の `load_*` 関数と `core/simulation/` 配下の各Engineを
組み合わせて実行する。

### 入力シート一覧

| シート名 | 内容 | 必須 |
|---|---|---|
| `入力_プラン設定` | 基本設定（生年月日・居住地・前提条件） | ✓ |
| `入力_口座` | 口座一覧（NISA/iDeCo等） | ✓ |
| `入力_収入` | 収入 | ✓ |
| `入力_支出` | 支出 | ✓ |
| `入力_シナリオ` | シナリオ比較用（退職年齢違い等） | 任意 |
| `入力_実績` | 実績純資産（計画との比較用） | 任意 |

タブ名・列名（ヘッダー行）は日本語だが、`account_type`・`asset_class`等の値は内部識別子として
英語のまま扱う（`adapters/sheets/sheet_mapping.py` に集約）。NISA/iDeCoは制度の正式名称のため
英語表記を維持する。

入力に不備があると `StructuralInputError` が送出される（`core/domain/errors.py`）。
`adapters/sheets/sheets_error_writer.py` の `write_errors()` で `出力_エラー` シートへ
「どのフィールドで・何が」の形式で一覧を書き戻せる。

## テスト

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -p "test_*.py"
```

Google Sheets認証キー（`secrets/gsheets_credentials.json`）がない環境では、実スプレッドシートに
接続する `tests/integration/` のテストは自動的にスキップされる。

カバレッジ確認:

```bash
pip install coverage
PYTHONPATH=. python3 -m coverage run --source=core,repositories,reports,adapters -m unittest discover -s tests -p "test_*.py"
PYTHONPATH=. python3 -m coverage report -m
```

## プロジェクト構成

```
core/domain/         ドメインモデル（標準ライブラリ以外への依存を持たない）
core/simulation/      計算ロジック本体（projection/tax/portfolio/withdrawal/pension/montecarlo/historical）
core/services/        Application Layer（意味的な入力検証など）
repositories/         config/yamlの読込窓口
adapters/sheets/       Googleスプレッドシート ⇔ ドメインモデルの変換
reports/              SimulationResult等からグラフ・表用データを生成
config/               税制・年金・口座制度・過去市場データ（yaml）
tests/unit/           単体テスト
tests/integration/     Sheets Adapterの結合テスト（実スプレッドシート接続）
tests/regression/      固定シナリオでの回帰テスト（golden file比較）
docs/                 設計書・ロードマップ
```

設計思想・レイヤー構成の詳細は `docs/FIRE_Navigator_システムアーキテクチャ設計書.md`
（v1.1変更点は同名 `_v1.1.md`）を参照。

## 既知の制約

- `domestic_bond`・`global_bond` の過去リターン系列（`config/market_data/`）は実際の指数値を
  検証しきれておらず、一般的な資産クラスの特性に基づく参考値（詳細はファイル内コメント参照）。
- `inflation_rate`（`入力_プラン設定`）は現時点でシミュレーション結果に反映されない
  （Income/Expenseが個別の`growth_rate`を持つ設計のため）。
- 投資の含み益・実現益に対する課税、住宅ローン（`core/domain/loan.py`）は未実装（MVPスコープ外）。
- 「カスタムプロット」（MoSCoWのShould項目）は未着手。
