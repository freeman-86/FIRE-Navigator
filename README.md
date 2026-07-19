# FIRE Navigator

日本の税制・社会保険料・NISA/iDeCo等の制度を反映した、手取りベースの資産形成シミュレーションエンジン。
Googleスプレッドシートを入出力UI（View）として使い、計算のSource of TruthはPythonエンジン側に置く
（「Engine First」という設計思想。詳細は `docs/` 配下の設計書を参照）。

## 現在の状態

MVP定義とロードマップ（`docs/FIRE_Navigator_MVP定義とロードマップ.md`）のSprint1〜10に加え、
`docs/FIRE_Navigator_旧ドラフトとのギャップ分析_追加要件定義.md`で確定した追加要件
（資産クラスの拡張性・Master/ダッシュボード・Projection Engineの月次化・譲渡税/取得原価管理・
資産配分比率の可変対応/月次リバランス・教育費/大型一時支出）が完了しています。

- 決定論的シミュレーション（税引後キャッシュフロー、NISA/iDeCo等の口座別配分、取り崩し、公的年金の繰上げ/繰下げ）。
  内部的には**月次ループ**で計算し（Sprint12 月次化）、年末時点の集計を`yearly_projections`、
  月次明細を`monthly_projections`としてそれぞれ`SimulationResult`に保持する
- **譲渡税・取得原価管理**（Sprint13）: 課税口座（TAXABLE）からの取り崩し時、平均取得原価方式で
  実現益を算出し譲渡税(20.315%)を課税する。NISA等の非課税口座は対象外
- **資産配分比率の可変対応・月次リバランス**（Sprint13）: 年齢別の目標配分比率（`入力_配分方針`、
  任意）をプラン全体で1つ持ち、毎月ドリフトをチェックして新規拠出で優先的に埋め、
  埋めきれない分は非課税口座を優先して売却→再投資する。Monte Carlo/Historical Engineも
  この目標配分比率でその時点の資産クラス別リターンを加重合成する（固定比率で合成しない）
- **教育費・単発支出**（Sprint14）: 子供の年齢帯に応じた教育費（`入力_教育費`、任意）を毎月の
  支出に自動加算する。車・旅行・住宅購入等の単発支出は`入力_支出`に統合されており、単発フラグ列
  で区別する（該当行のみ指定した年月〈today/plan_start/age/date〉に全額を一括計上する）
- マイルストーン到達判定・シナリオ比較・感応度分析
- モンテカルロシミュレーション（月次相関考慮サンプリング）・ヒストリカルバックテスト（過去データ）・実績vs計画の比較
- Master的な要約入力ビュー（退職年齢・年金条件・目標資産）・ダッシュボード（逆算による追加可能額・資産枯渇年齢）
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

### 全部まとめて実行する（推奨）

「スプレッドシートを読み込む→シミュレーション実行（決定論的・シナリオ比較・感応度分析・
モンテカルロ・ヒストリカルバックテスト・Progress比較）→結果を書き戻す」を一括で行う。

**Finderからダブルクリックで実行する場合**: リポジトリ直下の `シミュレーション実行.command` を
ダブルクリックする。初回はmacOSのセキュリティ設定でブロックされることがあるため、その場合は
`シミュレーション実行.command` を右クリック→「開く」を選び、表示される確認ダイアログで
「開く」を選択する（一度許可すれば以降はダブルクリックで実行できる）。ターミナルが開いて
実行ログが表示され、完了後は何かキーを押すとウィンドウが閉じる。

**ターミナルから実行する場合**:

```bash
PYTHONPATH=. python3 scripts/run_full_simulation.py
```

モンテカルロ/ヒストリカルバックテストは計算に数十秒〜数分かかることがある。基本的な数値だけ
素早く確認したいときは省略できる:

```bash
PYTHONPATH=. python3 scripts/run_full_simulation.py --quick             # 両方省略して高速実行
PYTHONPATH=. python3 scripts/run_full_simulation.py --trials 1000       # モンテカルロの試行回数を指定（既定200）
PYTHONPATH=. python3 scripts/run_full_simulation.py --spreadsheet-name "自分のシート名"
```

入力に不備があると処理を中断し、`出力_エラー` シートに詳細を書き込む（`シミュレーション実行.command`
経由でもターミナル上にエラー内容が表示される）。

### 個別のスクリプト

すべてのスクリプトはリポジトリルートから `PYTHONPATH=.` を付けて実行する。

```bash
# サンプルデータをテスト用スプレッドシートに投入する
PYTHONPATH=. python3 scripts/seed_test_spreadsheet.py

# 入力シートの必須セルの色分け・プルダウン・「入力例」シートを設定する（初回セットアップ時、
# または入力シートの列構成を変更した後に実行する。既存の入力値は変更しない）
PYTHONPATH=. python3 scripts/setup_input_sheets.py
```

上記の一括実行スクリプトを使わず、特定の計算だけをPythonコードから個別に呼び出すこともできる
（Jupyter notebook等での動作確認や、独自のバッチ処理を書く場合を想定）。

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

ダッシュボード（今月使える金額の逆算・資産枯渇年齢）の実行例:

```python
from adapters.sheets.sheets_input_adapter import (
    build_client, open_spreadsheet, load_plan, load_portfolios, load_target_ending_networth,
)
from adapters.sheets.sheets_output_adapter import write_dashboard
from repositories.config_repository import load_tax_rules, load_portfolio_rules, load_pension_rules
from reports.dashboard_builder import build_dashboard

plan = load_plan()
portfolios = load_portfolios()
target = load_target_ending_networth()
dashboard = build_dashboard(plan, portfolios, load_tax_rules(), load_portfolio_rules(), load_pension_rules(), target)

write_dashboard(open_spreadsheet(build_client()), dashboard)
```

### 入力シート一覧

| シート名 | 内容 | 必須 |
|---|---|---|
| `入力_プラン設定` | 基本設定（生年月日・居住地・前提条件・退職年齢・年金条件・目標資産等） | ✓ |
| `入力_口座` | 口座一覧（NISA/iDeCo等） | ✓ |
| `入力_収入` | 収入 | ✓ |
| `入力_支出` | 経常支出・単発支出（車・旅行・住宅購入等）を単発フラグ列で区別して管理 | ✓ |
| `入力_シナリオ` | シナリオ比較用（退職年齢違い等） | 任意 |
| `入力_実績` | 実績純資産（計画との比較用） | 任意 |
| `入力_配分方針` | 年齢別の目標配分比率（資産クラス別、プラン全体で1つ、口座横断） | 任意 |
| `入力_教育費` | 子供の一覧（子供ID・生年月日）と年齢帯別の教育費（小学校・塾・中学・高校・大学等、月額） | 任意 |

`入力_プラン設定`は旧ドラフトのMasterシート（主要条件をまとめて素早く変更できる単一シート）の
方向性を踏襲し、退職年齢・年金見込額・年金受給タイミング・目標資産（想定寿命時点）も含めて
1シートに集約している（いずれも任意入力。未入力時は退職なし・年金見込額ゼロ・標準65歳受給という
後方互換のデフォルトになる）。他の`入力_*`シート（口座/収入/支出等の表形式シート）とは別に
複製の入力ビューは作らず、各項目の置き場所は常に1箇所に統一している。

タブ数を減らすため、`入力_支出`は旧`入力_大型支出`を、`入力_教育費`は旧`入力_子供`をそれぞれ
統合している。`入力_支出`は単発フラグ（TRUE/FALSE）列で行の意味が変わる: FALSE（既定）の行は
経常支出（`年間金額`・`成長率`・`柔軟支出フラグ`を使用）、TRUEの行は単発支出（`金額`と
`開始条件タイプ`/`開始条件値`を使用、`today`/`plan_start`/`age`/`date`のいずれかで発生年月を指定）
として扱う。`入力_教育費`は`生年月日`列を追加しており、同じ子供IDの行すべてに同じ生年月日を
繰り返し記入する（行間で値が食い違うとエラーになる）。

タブ名・列名（ヘッダー行）は日本語だが、`account_type`・`asset_class`等の値は内部識別子として
英語のまま扱う（`adapters/sheets/sheet_mapping.py` に集約）。NISA/iDeCoは制度の正式名称のため
英語表記を維持する。

入力に不備があると `StructuralInputError` が送出される（`core/domain/errors.py`）。
`adapters/sheets/sheets_error_writer.py` の `write_errors()` で `出力_エラー` シートへ
「どのフィールドで・何が」の形式で一覧を書き戻せる。

### 入力のしやすさ（書式設定・入力例）

`scripts/setup_input_sheets.py` を実行すると、各入力シートに以下を設定する
（`adapters/sheets/sheets_formatting.py`）。既存の入力値は一切変更しない。

- 実際に入力すべき必須セルに薄い黄色の背景色を付ける（`入力_プラン設定`はB列の該当行のみ）
- 口座タイプ・名義・資産クラス・開始/終了条件タイプ・居住都道府県・年金受給タイミング・
  柔軟支出フラグなど、選択肢が決まっている列にプルダウン（データの入力規則、`strict: true`）を
  設定し、無効な値を入力できないようにする
- 全入力シートの記入例（サンプル行）をまとめた `入力例` シートを作成する

`入力例`シートは既存の`入力_*`シートとは完全に別のシートに作られ、シミュレーションの
入力読み込み（`get_all_records()`）では一切参照されない。同じシートの余白列・余白行に
サンプルを置くと、ヘッダー行が他行の最大幅までパディングされて重複ヘッダー扱いになり、
次回の入力読み込みが壊れる可能性があるため、あえて別シートに分離している。

### ダッシュボード（出力_ダッシュボード）

旧ドラフトのDashboardシート（1画面で主要指標を把握できる要約ビュー）を踏襲した出力シート。
`reports/dashboard_builder.py` の `build_dashboard()` が以下を算出する。

- 今年/今月使える追加金額（`入力_プラン設定`の目標資産を下回らない範囲で生活費に上乗せできる金額を、
  既存の決定論的Projection Engineに対する二分探索で逆算する）
- 資産枯渇年齢（想定寿命までにnetworthが0以下になる最初の年齢）
- 目標資産との余裕（想定寿命時点の予測networth − 目標資産）

「今月使える金額」は現時点では年額を12等分した暫定値であり、Projection Engineの月次化後に
月次粒度の値へ置き換える予定（`docs/FIRE_Navigator_旧ドラフトとのギャップ分析_追加要件定義.md` 3.1）。

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
scripts/run_full_simulation.py  読込→計算→書き戻しを一括実行するスクリプト
scripts/setup_input_sheets.py   入力シートの必須セル色分け・プルダウン・入力例を設定するスクリプト
シミュレーション実行.command      ↑をダブルクリックで実行するためのランチャー
tests/unit/           単体テスト
tests/integration/     Sheets Adapterの結合テスト（実スプレッドシート接続）
tests/regression/      固定シナリオでの回帰テスト（golden file比較）
docs/                 設計書・ロードマップ
```

設計思想・レイヤー構成の詳細は `docs/FIRE_Navigator_システムアーキテクチャ設計書.md`
（v1.1変更点は同名 `_v1.1.md`）を参照。

## 既知の制約

- 資産クラスは`config/asset_classes.yaml`で管理しており、コード変更なしに追加できる
  （`repositories/asset_class_repository.py`）。ただしMonte Carlo/Historical Engineで
  使うには別途`config/market_data/`に過去リターン系列を追加する必要があり、未追加の資産クラス
  （例: `btc`）はこれらのEngineの加重平均リターン計算で実質0%リターン扱いになる
  （決定論的なProjection Engineはこの制約を受けない）。
- `config/market_data/historical_returns_2001_2024.yaml`の過去リターン系列（S&P500・米国長期国債）
  はAswath Damodaran教授（NYU Stern）の公開データセットに基づく実データ（詳細はファイル内コメント参照）。
- `inflation_rate`（`入力_プラン設定`）は現時点でシミュレーション結果に反映されない
  （Income/Expenseが個別の`growth_rate`を持つ設計のため）。
- 譲渡税は課税口座（TAXABLE）からの取り崩し・リバランス売却時のみ対象。iDeCo等その他口座の
  出口課税（退職所得控除等）、譲渡損失の損益通算・繰越控除は対象外（ギャップ分析5.2/6章で確定した
  簡易化）。住宅ローン（`core/domain/loan.py`）も未実装。
- 資産配分の目標比率（`入力_配分方針`）は口座ごとに1資産クラスのみを保有する前提（`入力_口座`の
  1行=1口座=1資産クラスという既存モデルに合わせた設計）。月次リバランスの再投資は各口座の
  拠出上限（年間/生涯枠）を尊重するが、通常の月次拠出フローとは別枠で判定する簡易化のため、
  両者を跨いだ年間枠の厳密な合算管理はしない（生涯枠は共有のlifetime_contributionsで正しく守られる）。
- Monte Carlo/Historical Engineの資産クラス別加重合成は、AllocationPolicy設定時はその時点の年齢の
  目標配分比率を使う。ただしサンプリング対象の資産クラス一覧はシミュレーション開始時点(age基準)の
  構成で決め打ちするため、途中の年齢で新しい資産クラスが初めて登場するケースは反映されない。
- 収入・支出の開始/終了条件（`Income`/`Expense`の`start_condition`/`end_condition`）は現時点では
  年単位でしか判定しない（月次化はProjection Engine内部の資産成長・キャッシュフロー計算のみ対応済みで、
  収支の発生タイミング自体の月精度化は今後の課題）。一方、`入力_支出`の単発フラグ=TRUEの行（単発支出）は
  `resolve_condition_month()`により発生月を正確に判定する（Sprint14）。
- 教育費（`入力_教育費`）・単発支出（`入力_支出`の単発フラグ=TRUEの行）には`inflation_rate`と
  同様に物価上昇率は適用されない（名目固定額のまま）。教育費バンドの年齢帯（開始年齢〜終了年齢を
  含む）は、子供の誕生月ではなく学年（4月1日時点の年齢）を基準に切り替わる（`_school_year_age()`）。
- 所得税・住民税・社会保険料は年1回の確定計算のみで、その結果を12等分して毎月のキャッシュフローに
  反映する（月ごとの累進課税の再計算はしない。日本の税制がそもそも年次確定であるため）。
- Historical Engineの月次バックテストは、実際の年次リターン実績値を`monthly_equivalent()`で月率換算し
  同じ年の12ヶ月に均等適用する近似（実際の月次指数データへの置き換えは将来課題）。
- Monte Carlo Engineは毎月新規に相関考慮サンプリングするため、月次化により1試行あたりの計算量が
  約12倍に増えている（trials=1000・想定寿命までの長期プランで実行に1分弱かかる場合がある）。
- 「カスタムプロット」（MoSCoWのShould項目）は未着手。
