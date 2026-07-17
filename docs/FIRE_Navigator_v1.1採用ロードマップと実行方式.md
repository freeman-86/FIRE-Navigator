# FIRE Navigator v1.1採用ロードマップ ＆ 実行方式メモ

位置づけ: 「システムアーキテクチャ設計書」（v1.0＋思想追記）と「システムアーキテクチャ設計書 v1.1（改訂版）」の両方を正式仕様として維持したまま、**どのv1.1項目をいつ採用するか**、および**Excelとエンジンをどう連携させるか**を確定するための実務メモ。既存のMVP定義・Sprintロードマップ・アーキテクチャ設計は変更しない。

---

## 1. v1.1採用ロードマップ（Sprint紐づけ）

v1.1改訂書の9項目について、それぞれ「いつ採用するか」を明示する。判断基準は一貫して**YAGNI**：今のSprintで実際に価値を発揮する見込みが立った時点で採用し、見込みが立たないものはMVP期間中は採用しない。

| v1.1項目 | 採用Sprint | 理由 |
|---|---|---|
| **③ Repository interfaces/implementations分離** | **Sprint1〜2から採用** | コストが低く、最初にPlan Repositoryを作る段階でこの形にしておく方が、後から分離するより手戻りが少ない。 |
| **⑤ Output JSONの拡張（summary/metrics/tables/charts/diagnostics）** | **Sprint4から段階的に採用** | ネットワースグラフが動く（MVPの核が一周する）Sprint4の時点でOutput JSONの型を先に決めておくと、以後のSprintで追加するデータが自然にこの型へ乗る。ただし全フィールドを最初から埋める必要はなく、実際に使うデータが揃ったSprintごとに値を追加していけばよい。 |
| **⑥ Monte Carlo Engineの内部詳細化** | **Sprint9（モンテカルロ導入時）** | 元のSprintロードマップ通りSprint9で新規実装するので、最初から詳細構成（Return Generator等）で作ってよい。既存コードの作り直しが発生しない。 |
| **⑦ Historical Engineの内部詳細化** | **Sprint9（同上）** | 同上。 |
| **④ Reporting Engineの細分化（5 Builder）** | **Sprint9〜10** | Sprint4時点では単一のnetworth_reportで十分機能する。シナリオ比較（Sprint7）・モンテカルロ（Sprint9）でレポートの種類が増えた段階でBuilderへ分割すると、「本当に必要になってから分割する」形になり過剰設計を避けられる。 |
| **① Simulation Engineの再設計（domains/framework/shared構成）** | **MVP期間（Sprint1〜10）では採用しない**。将来、8つ目のドメイン（教育費・不動産等）を追加する具体的な必要が出た時点（Sprint11以降）で着手 | MVPで扱うドメインはtax/pension/portfolio/withdrawal/loan/montecarlo/historicalの7つ程度であり、v1.0のフラット構成で十分に見通せる。30ドメイン規模を見据えた抽象化を今行うのはYAGNIに反する。 |
| **② Aggregateの見直し（Plan/Portfolio/Scenario分割）** | **Sprint7（シナリオ比較機能に着手するタイミング）** | Scenario Aggregateの独立は、まさにSprint7の「シナリオ比較」機能で初めて価値を発揮する。それまでは v1.0通りPlanを単一集約として扱う。 |
| **⑧ Event Architecture** | **Sprint7から段階的に導入**。Milestone判定に必要な最小限（ConditionalEventの考え方）のみSprint7で採用し、RecurringEvent/OneTimeEventの本格的な型階層・Event Queue・優先順位テーブルは、実際に住宅購入等のOneTimeEventを扱う必要が出るSprint8以降、または将来ドメイン追加時に導入する | 合意の通り。Sprint1〜6は素朴な実装（Milestoneは単純なif判定、Income/Expenseの開始・終了条件も単純な条件判定）のまま進め、Sprint1〜6の基盤構築の負荷を上げない。 |
| **⑨ 設計レビューの更新** | **常時（各Sprint終了時の振り返りに反映）** | レビュー内容はコードではなく認識の記録なので、Sprintごとの実態に合わせて更新していけばよい。特定のSprintに紐づける必要はない。 |

### 1.1 結果として、Sprint1〜6は「v1.0のシンプルな構成」で進む

上表の通り、Sprint1〜6では①②④⑥⑦⑧の重い部分をいずれも採用しない。実質的にSprint1〜6は元の「システムアーキテクチャ設計書」（v1.0＋思想追記）のディレクトリ構成・クラス構成のままで進めてよい。v1.1の内容を意識する必要があるのはSprint7以降であり、それまでは**2つの設計書を同時に見比べながら実装する必要はない**。

### 1.2 Sprint7が「切り替えポイント」になる

Sprint7で③Aggregate分割と⑧Event Architectureの最小限を同時に導入する。この時点で初めてv1.1の設計書を開き、以下の作業を行う。

1. `core/domain/plan.py` からPortfolio関連の参照をID参照へ変更（Plan Aggregate / Portfolio Aggregateの分離）
2. `core/domain/scenario.py` を独立したAggregateとして整理
3. `core/domain/milestone.py` をConditionalEventの考え方に沿って整理（型階層は最小限、Event Queueの本格実装はまだ行わない）

この3点のみをSprint7のタスクに追加し、他のv1.1項目（①④⑥⑦）には触れない。

---

## 2. Excel起動方式の検討

### 2.1 前提の見直し

これまでの設計書は「Excelのボタンから直接Pythonを起動する」という前提を暗黙に置いていたが、これはSprint1の成立を左右する技術的な不確定要素であり、かつ**VBAマクロ経由でPythonを呼ぶ方式は、マクロ有効化の警告・セキュリティ設定・環境依存（PCごとのPythonパス設定等）の問題を抱えやすい**。今回、「Excel内からの起動にはこだわらない」という方針に転換したため、より安全でシンプルな方式を検討する。

### 2.2 選択肢の比較

| 方式 | 概要 | メリット | デメリット |
|---|---|---|---|
| **A. 外部スクリプト手動実行（推奨）** | Excelを保存した状態で、ダブルクリック起動できる簡易ランチャー（`.bat`/`.command`等）を実行する。ランチャーが`scripts/run_sample_simulation.py`（ディレクトリ構成に既存）を呼び出し、Excel Adapterが入力Excelを読込→計算→出力Excel（またはレポートシートを更新した同ファイル）を書込→自動で開く、という流れ。 | ・マクロを一切使わないためセキュリティ警告が出ない<br/>・VBA⇔Python連携特有の環境依存問題（パス設定、DLL等）が発生しない<br/>・「Excelを閉じてからPythonがファイルを書き換える」ため、ファイルロックの心配がない<br/>・実装が最も単純で、Sprint1のI/O疎通の延長線上でそのまま作れる | ・ユーザーが「Excelを保存→ランチャー実行→結果ファイルを開き直す」という一手間を意識する必要がある（ただし自分専用ツールなので許容範囲） |
| B. xlwings等のCOM連携ライブラリ | Excelのボタン等からPythonを直接呼び出す。Excelを開いたまま結果が反映される。 | ・Excel上のボタンクリックで完結し、体験としては滑らか | ・xlwingsのインストール・Excelアドイン設定など、環境構築の手間が増える<br/>・ExcelとPythonが同時に同じファイルを触る形になり、ファイルロック・保存タイミングの考慮が必要<br/>・「Excelはビジネスロジックを持たない」という設計思想とは独立の話だが、Excel側の設定（アドイン有効化等）への依存が増える |
| C. VBAマクロからShell実行 | VBAの`Shell`関数でPythonスクリプトを起動する。 | ・Excel上で完結する見た目にはなる | ・マクロ有効化が必須になりセキュリティ警告が出る<br/>・PCごとのPythonパス差異をVBA側で吸収する必要があり、環境依存が最も強い<br/>・当初の懸念そのもの |
| D. ファイル監視（watchdog等）による自動実行 | Excel保存を検知し、バックグラウンドプロセスが自動で計算・書き戻しを行う。 | ・保存するだけで結果が更新される体験 | ・常駐プロセスが必要になり、「シンプルで安全」という今回の要件からは外れる<br/>・自分専用ツールの初期段階でここまでの自動化は過剰 |

### 2.3 結論・推奨方式

**A. 外部スクリプト手動実行方式を採用する。**

- Excel Adapterが担う役割（Excel⇔JSON変換、Excel読み書き）は、これまでの設計書の記述から一切変更しない。変わるのは「誰が・どうやってそのAdapterを呼び出すか」という起動のきっかけだけである。
- 具体的には、ディレクトリ構成の`scripts/run_sample_simulation.py`を「サンプル実行スクリプト」から「実運用のエントリーポイント」として使う想定に位置づけ直す（新しいファイルを増やす必要はない。既存のscripts/配下の役割をそのまま使う）。
- OS別に、ダブルクリックで`python scripts/run_sample_simulation.py`相当を実行するだけの簡易ランチャー（Windowsなら`.bat`、Macなら`.command`）を1つ用意すれば足りる。これはコードではなく数行の起動用ファイルであり、Sprint1の「Excel⇄Python間I/O疎通」の完成と同時に用意できる。
- **Excelはこの方式でも変わらず「View」であり続ける**。Excelを閉じている間にPythonがファイルを読み書きするため、ExcelとPythonが同じファイルへ同時にアクセスする心配がなく、これまでの設計思想（Excel=View、Python Engine=Source of Truth）とも自然に整合する。

### 2.4 Sprint1タスクへの反映

Sprint1の「やること」に、以下を追加する（既存のSprint1の範囲・終了条件自体は変更しない。手段を具体化するだけ）。

- 簡易ランチャー（`.bat`または`.command`）を1つ作成し、`scripts/run_sample_simulation.py`相当を起動できるようにする
- 「Excelを保存 → ランチャーを実行 → 結果が反映された状態でExcelが開く（または開き直すよう促す）」という一連の流れを、Sprint1の「動くもの」の定義に含める

---

## 3. まとめ

- v1.1の重い部分（Simulation Engine再設計・Aggregate分割・Reporting Engine細分化・Event Architecture）はSprint1〜6では使わず、v1.0のシンプルな構成のまま進める。
- Sprint7を「v1.1への切り替えポイント」とし、Aggregate分割とEvent Architectureの最小限をこのタイミングでまとめて導入する。
- Monte Carlo/Historical Engineの詳細化、Output JSON拡張、Repository分離は、それぞれ元から予定されていたSprint（4, 9）でそのまま採用してよい。
- Excel起動は、マクロやCOM連携に頼らず、**外部スクリプトの手動実行**というもっともシンプルで環境依存の少ない方式を採用する。Excel Adapter自体の設計は変更しない。
