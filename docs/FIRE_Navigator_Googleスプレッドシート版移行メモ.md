# FIRE Navigator Googleスプレッドシート版 移行メモ

位置づけ: 「システムアーキテクチャ設計書」で定めたExcel Adapterを、Google Sheets Adapterへ置き換える決定を反映する。**Domain Layer・Simulation Engine・JSONスキーマ・レイヤー構成・依存方向は無改修**。変更が及ぶのはAdapter Layerとその周辺（ディレクトリ名・使用ライブラリ・起動方式の細部）のみである。これはまさに「Engine First」「Excel（UI）はViewの一つに過ぎない」という設計思想が実際に効いた例と言える。

---

## 1. 変更の範囲

| レイヤー | 変更の有無 |
|---|---|
| UI Layer | 変更あり（Excel → Googleスプレッドシート） |
| **Adapter Layer** | **変更あり**（`adapters/excel/` → `adapters/sheets/`。実装のみ差し替え） |
| Application Layer | 変更なし |
| Domain Layer | 変更なし |
| Simulation Engine | 変更なし |
| Infrastructure Layer | 変更なし |
| Input/Output JSONスキーマ | 変更なし |

---

## 2. ディレクトリ構成への反映

「システムアーキテクチャ設計書」2章の`adapters/excel/`を、`adapters/sheets/`に置き換える。ファイル単位の役割は1対1で対応させる。

```
adapters/
├── sheets/                       # 旧 adapters/excel/ に相当
│   ├── __init__.py
│   ├── sheets_input_adapter.py    # 旧 excel_input_adapter.py：Sheets → Input JSON
│   ├── sheets_output_adapter.py   # 旧 excel_output_adapter.py：Output JSON → Sheets
│   ├── sheet_mapping.py           # 変更なし（シート名/セル ⇔ JSONフィールドの対応表という役割は同じ）
│   └── sheets_error_writer.py     # 旧 excel_error_writer.py：エラーをシート上へ書き戻す
└── json/                          # 変更なし
```

7章「Excelアダプタ設計」の内容（設計原則・変換フロー・エラーの扱い）はそのまま「Google Sheets Adapter設計」として読み替えればよい。責務・変換の考え方（View⇔共通JSON形式の変換のみを担い、ビジネスルールは持たない）は一切変わらない。

---

## 3. 技術的な変更点

### 3.1 使用ライブラリ

| 項目 | Excel版 | スプレッドシート版 |
|---|---|---|
| 読み書きライブラリ | `openpyxl` | `gspread`（Google Sheets APIのPythonラッパー） |
| 認証 | 不要 | 必要（サービスアカウント認証） |

### 3.2 認証の設計

- Google Cloud Platform上でサービスアカウントを作成し、認証情報（JSONキーファイル）を発行する。
- 対象のGoogleスプレッドシートを、そのサービスアカウントのメールアドレスに対して編集権限で共有する。
- 認証キーファイルは**リポジトリに含めない**。`config/`とは別に、`secrets/`のようなgit管理外のフォルダに置くか、環境変数経由でパスを指定する。

**`.gitignore`への追加（必須）**:
```
secrets/
*.json  # ただし config/配下の.jsonは除外対象から明示的に外す運用に注意（誤って全JSON除外しないよう、secrets/配下のみを対象にするパターンを推奨）
credentials/
```

実務的には「認証キー専用のフォルダ名（例：`secrets/gsheets_credentials.json`）を`.gitignore`にピンポイントで指定する」方式が、誤って必要なファイルまで除外するリスクが低く安全である。

### 3.3 sheet_mapping.py の扱い

Excel版では「シート名・セル位置（または名前付き範囲）」で対応表を作っていたが、スプレッドシート版でも考え方は同じ。Google Sheetsも「シート名＋セル範囲（A1形式）」でアクセスできるため、対応表の構造（シート名／セル範囲／JSONフィールドパス／型変換ルール）はそのまま流用できる。名前付き範囲もGoogleスプレッドシートでサポートされているため、Excelと同様の設計が可能。

---

## 4. 起動方式への影響（プラスの変化）

前回決めた「外部スクリプト手動実行方式」は、スプレッドシート版でもそのまま使える。むしろ以下の点でシンプルになる。

- **ファイルロックの心配が完全になくなる**：Excelはローカルファイルを開いている間は他プロセスからの書き込みが競合しうるが、Google Sheets APIはクラウド上のシートに対してAPI経由でアクセスするため、「Excelを閉じてから実行する」という手順を意識する必要がなくなる。
- **OS依存が減る**：ローカルファイルパスの解決（Windows/Mac別のランチャー）は引き続き必要だが、対象ファイルの入出力先がクラウドになるため、複数の端末（PCとスマホ等）から同じシートを確認できる。
- 一方で、**実行のたびにネットワーク接続が必須**になる（Excel版はオフラインでも動いた）。自宅のPCで完結する使い方であれば問題にならないが、この点は認識しておく。

---

## 5. Sprint1タスクへの反映

「Sprint1実行タスクリスト」の3章（Excel⇄Python最小疎通の実装）を以下のように読み替える。他の章（0. 開発環境／1. GitHubリポジトリ／2. ランチャー方式／4. テスト基盤／5. 完了チェックリスト）は構成として変更なし。

- [ ] `gspread`と`google-auth`を`requirements.txt`に追加
- [ ] Google Cloud Platformでサービスアカウントを作成し、認証キーJSONを発行する
- [ ] 動作確認用のGoogleスプレッドシートを1つ作成し、サービスアカウントに編集権限を付与する
- [ ] 認証キーの保存場所（`secrets/`等）を決め、`.gitignore`に確実に追加する
- [ ] `adapters/sheets/sheets_input_adapter.py` の最小版を実装：指定セルの値を読み込む関数
- [ ] `scripts/run_sample_simulation.py` を拡張：読み込んだ値を2倍にする（Sprint1時点ではダミー処理でよい、Excel版の方針と同じ）
- [ ] `adapters/sheets/sheets_output_adapter.py` の最小版を実装：計算結果を指定セルへ書き込む関数
- [ ] ランチャーを実行し、「スプレッドシートの値を変更 → ランチャー実行 → スプレッドシートの別セルに2倍の値が反映される」ことを確認する

Sprint1の終了条件自体（「入力の値を変更して実行すると、Pythonが読み込み・加工し、結果を書き戻す」）は変わらない。対象がローカルのExcelファイルからクラウド上のスプレッドシートに変わるだけである。

---

## 6. まとめ

- 変更が及ぶのはAdapter Layer（`adapters/excel/` → `adapters/sheets/`）のみで、Domain・Simulation Engine・JSONスキーマ・レイヤー構成はすべて無改修。
- 新たに認証キー管理という注意点が1つ増えるが、`.gitignore`で確実に除外すれば問題ない。
- 起動方式（外部スクリプト手動実行）はそのまま使え、むしろファイルロックの懸念がなくなる分シンプルになる。
- Sprint1のタスクは「Excel」を「スプレッドシート」に読み替えるだけで、タスクの粒度・順序は変わらない。
