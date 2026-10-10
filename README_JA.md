<div align="center">

<img src="assets/logo.png" alt="fugue-docs logo" width="280">

# fugue-docs — フーガ・ドキュメント

[简体中文](README.md) | [English](README_EN.md) | **日本語**

> "The map IS the terrain. The terrain IS the map."

</div>

> コードは「機械相」、ドキュメントは「意味相」。両相は常に同型(isomorphic)でなければならない——一方の変化が他方に反映されない限り、タスクは未完了とみなす。

「GEB フラクタル・ドキュメント・プロトコル」を AI コーディングの日常的な作法に変えるツールキットです。三層フラクタル索引(L1 プロジェクト / L2 フォルダ / L3 ファイルヘッダ)+ 強制ループ更新 + 機械検証可能な同型性により、AI 支援開発時代のプロジェクト・エントロピー——コードは散らかり、ドキュメントは常に遅れる——に対抗します。

Claude Code、Codex、Devin はネイティブフックで自動保守できます。Codex と Devin には単独スキルとプロジェクト規則による接続もあります。同じプロトコルは Cursor、Windsurf、Cline、Copilot、Web チャットでも利用できます。各ツールの接続方法と任意のコミット検査は「あらゆるツール・モデルで使える」を参照してください。

## Codex ネイティブフック:自動保守と意味の補完

`geb_install_codex.py --hooks` で SessionStart、UserPromptSubmit、Pre/PostToolUse、Stop、SessionEnd、Interrupt、SubagentStart/SubagentStop の計九種類を配置します。Codex の標準の信頼確認を経て有効になると、日常の同期・検査・計量コマンドは不要です。開始時に索引を案内し、ツールイベントで当該会話の変更を記録、Stop で L3 と機械フィールドを同期して、新たな意味の欠落だけをモデルへ返して補完を続けます。子エージェントも自身の開始・終了イベントで同じ保守を行い、計量は子のログに独立して紐付けます。同じ欠落は内容が変わらない限り一度だけ通知し、未採用プロジェクトは自動初期化しません。

現在のインターフェース確認は Codex CLI `0.159.0-alpha.3` に基づきます。この版の `hooks` は stable で既定で有効、旧 `plugin_hooks` フラグは不要です。フックは Codex のホスト上で動くため、ホストから見えないリモートファイルは保守できません。Desktop とクラウドは個別に確認が必要です。[インストール](#インストール)と[フックの詳細](references/codex-hooks.md)にイベント、帰属の境界、参照ソースを記載しています。

## v2.7: Claude Code フックでモデルは意味だけを担当

最初の三群試験では、小さな変更に対して完全な Fugue フローが索引のみより非キャッシュ入力と出力の合計を 44%–82% 多く使いました。主な原因は、モデルがスキル文書を読み直し、計量・同期・検査スクリプトを自分で実行していたことです。v2.7 ではこれをプログラムに任せます。

- **モデル自身が書いたファイルだけ**:モデルが編集・書き込みツールを使う前に対象ファイルを記録し、シェルコマンドの前後で未コミット変更を比較して、そのコマンドが変えたコードファイルを記録します。checkout・pull・merge・stash pop などの git コマンドで入ったファイル、ユーザー自身の変更、同じリポジトリの別セッションが書いたファイルは含めません。コミット済み、元に戻ったもの、ターンの合間にユーザーが再び変更したものは記録から外します。セッション開始時はコンテキストに 1 行の案内だけを追加します。
- **各ターン終了**:このセッションが書き、まだ差分があり、未コミットのコードファイルだけを扱います。merge や rebase の途中は何も書き込みません。競合や構文エラーのあるファイル、UTF-8 以外のファイル、生成コード、プロジェクト外を指すシンボリックリンクは個別に飛ばし、一覧の既存の機械フィールドはそのまま残します。新規ファイルには L3 ヘッダーの骨格を入れ、依存と一覧は `geb_sync` が差分同期します。関数本体だけの変更は何も出力しません。新規ファイルの `[POS]`、一覧の役割、export 変更後の `[OUTPUT]`、新ディレクトリの位置付けといった意味の欠落だけを短い指示でモデルに渡し、内容が変わらない限り同じ欠落は一度しか伝えません。
- **計量**:Claude Code の会話記録からメッセージ単位で重複を除いて実使用量を集計し、Codex と互換の形式で `~/.claude/fugue/metrics` に記録します。会話記録の形式は公開インターフェースではないため、読めない場合はゼロではなく不明とします。
- **SKILL.md** 本文は約 4 割小さくなりました。フック導入後は通常のコーディングでスキルを呼ぶ必要がなく、フックを有効にしていない場合の手順は [references/manual-workflow.md](references/manual-workflow.md) に移しました。

プラグインマーケットからインストールするとフック(`hooks/hooks.json`)が有効になり、索引のないプロジェクトには干渉しません。`settings.json` に `geb_stop_hook.py` を手動登録していた場合は、Stop フックが二重に動かないよう削除してください。本リリースはまだ実モデルでの対照測定をしていないため、削減効果は今後の試験で確認が必要です。

## v2.5: タスク別レポートと計量診断

実測 token、経過時間、検証結果、対照状態をタスクごとに表示します。読み取り専用インデックスで Codex の分割ログを検出し、計量カバー率と欠測理由を示します。欠測はゼロではなく、品質確認済みの対照がなければ削減量は不明です。[計量説明](references/token-accounting.md) と [予算制限付き試験](evals/token-pilot.md) を参照してください。

[最初の三群試験](evals/TOKEN_PILOT_RESULTS.md) は、2 タスク・6 回の呼び出し後にソフト予算で停止し、5 回が検証を通過しました。有効な 2 組では、Fugue の非キャッシュ入力と出力の合計が索引のみより 44.2% と 82.0% 多くなりました。この限定的な自己ホスト試験から一般的な削減率や費用は結論できません。

## v2.4: Codex と使用量の記録

Python 3.9 以上が必要です。`geb_arch.py` は共有の依存解析からアーキテクチャ候補を生成し、ファイル単位の根拠と未解決の import を出力します。スコアはヒューリスティックであり、正解確率ではありません。同期時の非コード説明の保持、空ディレクトリと Unicode パスの処理を修正し、コミットフックはステージ済みスナップショットを検査します。

現在の手順は下記の[インストール](#インストール)と [Codex ガイド](references/codex.md)を参照してください。プロジェクト用スキルは `.agents/skills/fugue-docs`、個人用は `~/.agents/skills/fugue-docs` に配置します。既定ではスキルだけを配置し、明示的な `--hooks` でネイティブフックも登録します。

フック未使用時の `scripts/geb_metrics.py` は任意で、ユーザーが求め、ログを読めて台帳に書き込める場合のみ実行します。フック有効時は利用可能なテレメトリを自動記録します。既定の台帳は `${CODEX_HOME:-~/.codex}/fugue/metrics/` で、ログがなければ不明とし、開発を止めません。同じタスク・モデル・コミットで、品質を確認した独立した対照実験がない場合、削減量も不明のままです。負の差分も保持します。[計量説明](references/token-accounting.md) と [テスト](evals/README.md) を参照してください。CI は macOS/Linux、Python 3.9/3.14 で境界テストと自己検査を実行します。

## 出典とクレジット

本プロジェクトのプロトコルの原初のアイデア(L1/L2/L3 索引、自己言及更新、ループ)は **趙純想(chunxiang)** 氏の「GEB フラクタル・ドキュメント・システム・プロトコル」に由来し、その着想はダグラス・ホフスタッター『ゲーデル、エッシャー、バッハ』にあります。オリジナルの公式実装(CLI + Claude Code プラグイン + VSCode 拡張)は [Claudate/project-multilevel-index](https://github.com/Claudate/project-multilevel-index)(MIT)を参照してください。

fugue-docs は**独立した実装であり、独立した進化**です:オリジナルのコードは一切使用せず、スキル(方法論の注入)としてゼロから記述;プロトコル不変量の抽象化、機械フィールドのビュー化(geb_sync)、再帰フラクタル、規模弾力プロファイル、機械ファクト源などの設計は本リポジトリ独自のものです(進化の全過程はコミット履歴参照)。名前の「フーガ」は、プロトコル三大特性のひとつ「ポリフォニー(複調性)」へのオマージュです——コード・索引・ドキュメントの三声部が呼応し合い、フーガのように自己維持するプロジェクトを目指します。

## 主な機能

### 動作(自動適用、コマンド不要)

| 状況 | 動作 |
|------|------|
| 未知のプロジェクトに入る | 逆ループ:コードを読む前に L1 → L2 → L3 を読む |
| ドキュメント構造がない | スキャフォールドで骨格生成 + ボトムアップで意味を補完(実際にコードを読む。捏造禁止) |
| コードの追加・変更・削除 | 順ループ:L3 ヘッダ → L2 フォルダ索引 → L1 プロジェクト索引。更新完了までタスクは「完了」にならない |
| ドキュメントの陳腐化が疑われる | `geb_check.py` を実行し違反一覧を確認 |

### 6 つの設計原則

1. **同型性はスローガンではなく検証可能**:`geb_check.py` は二層で検査——**構造層**(デフォルト):L1 の存在、L2 カバレッジ、L3 タグの完全性、索引台帳と実ファイルの突合(欠落 + 幽霊エントリ);**意味ドリフト層**(`--strict`、保守的ヒューリスティクス):L1 が全トップレベル・コードディレクトリに言及しているか、各 L3 `[INPUT]` が実際の import に追随しているか。終了コード非 0 = 両相不一致、CI 対応。より深い意味の同期は AI ループの担当——明確な分業であり、検査の欠陥ではありません。CLAUDE.md は GEB プロトコル標識を含む場合のみ索引と認定され、「散文 CLAUDE.md による形だけの採用」という抜け穴を塞いでいます。本リポジトリ自身も CI で `--strict` 自己検査しています。
2. **ループはハード制約、モデルの善意に頼らない**:3 つのゲートを必要に応じて有効化——Claude Code / Codex の Stop フック(終了前)、git pre-commit フック(コミット前)、CI(マージ前)。
3. **機械相は全自動、知能が要るのは意味相だけ**:初期化時はスキャフォールドが骨格を静的生成(意味は `TODO` のまま);保守期は `geb_sync` が `[INPUT]` 行と台帳テーブルを**コードから再生成されるビュー**として扱う——派生データは手書き・照合ではなく再生成。ドリフトの半分が根本から消えます。機械は意味を理解したふりをしません。
4. **層数は複雑度に応じて伸縮——教条ではない**:プロトコルの不変量は「各意味境界に位置特定可能な索引、索引はカバレッジを宣言、実体は親へ逆リンク、機械が検証、コストは比例」であり、L1/L2/L3 はデフォルト・プロファイルにすぎません——小規模(≤20 ファイル)は自動的に 2 層へ(台帳は L1 に統合);**再帰フラクタル**は上方向への拡張:`PROJECT_INDEX.md` を持つサブディレクトリはサブプロジェクト(その L1 が親の L2 を兼ねる)で、検査・同期は自動再帰——monorepo ネイティブ対応。生成ファイル・設定・vendored 依存にはヘッダ不要。
5. **ボトムアップ初期化**:L3 はコードを読んで書き、L2 は L3 の要約、L1 は L2 の要約——全層が事実に基づきます。捏造されたドキュメントは無いより悪い。
6. **透明で監査可能**:タスク終了時に必ず `GEB loop: L3 ✓ | L2 ✓ | L1 —` の一行レポートを付加。サンドボックスでスクリプト実行が禁止された場合は、チェッカーのロジックに従って手動照合し、その旨を正直に申告します。

## インストール

### Codex

本リポジトリのディレクトリで実行し、パスを対象プロジェクトに置き換えてください:

```bash
python3 scripts/geb_install_codex.py --project /path/to/project --hooks --dry-run
python3 scripts/geb_install_codex.py --project /path/to/project --hooks
```

スキルは `.agents/skills/fugue-docs` に、`--hooks` による設定はプロジェクトの `.codex/hooks.json` に配置します。個人用は `--user --hooks` で、設定先は `${CODEX_HOME:-~/.codex}/hooks.json` です。任意の配置先 `--dest /path/to/skills/fugue-docs --hooks` では `--hooks-dir <設定ディレクトリ>` も必要です。プロジェクトと個人の hooks は累積するため、同じプロジェクトには一方だけを登録します。linked worktree は実際の設定元を `--hooks-dir` で明示してください。

プロジェクトを開き直すか新しい会話を始め、スキル一覧を確認し、Codex の **Hooks need review** または `/hooks` でコマンドを確認して信頼します。インストーラーは信頼の事前登録、bypass の設定、`config.toml` の変更を行いません。初回は `$fugue-docs このプロジェクトの索引を初期化して` と依頼できます。配置だけでは初期化しません。索引があり、信頼済みフックが有効なら日常保守は自動で、モデルは意味の通知に応答します。プロジェクトのテストは引き続き実行してください。

`--hooks` を省略すると既定のスキル単独配置となり、[手動で同期・検査](references/manual-workflow.md)します。手動の `--changed` はリポジトリ全体の未コミット変更を含むため、先に範囲を確認し、他の編集を保持します。ネイティブフックの自動計量は、ログの欠落や会話 ID の不一致を unknown/不明として続行します。`doctor` の反復や計量のための権限昇格は不要です。`FUGUE_DATA_DIR` でフックのデータディレクトリを指定できます。

更新は `--update`、事前確認は `--dry-run` を使います。他の hooks を保持し、ローカル変更された管理対象ファイル・項目の上書きは拒否します。許可リスト内のスキルファイルだけをコピーし、Claude の `.claude-plugin/` と `hooks/` は含めず、pre-commit や CI も登録しません。全コマンドと環境の制限は [Codex ガイド](references/codex.md) を参照してください。

ネイティブスキルを使わない場合は `python3 scripts/geb_adapt.py /path/to/project --tool codex --copy-tools` を使い、先に `--dry-run` を付けて確認します。既存の `AGENTS.override.md`、なければ `AGENTS.md` に規則を挿入し、プロジェクト内にスクリプトをコピーします。詳しくは [references/codex.md](references/codex.md) を参照してください。

### Devin

本リポジトリのディレクトリから Devin skill と任意のネイティブ hooks を配置します:

```bash
python3 scripts/geb_install_devin.py --project /path/to/project --hooks --dry-run
python3 scripts/geb_install_devin.py --project /path/to/project --hooks
```

プロジェクト skill は `.agents/skills/fugue-docs`、hooks は `.devin/hooks.v1.json` に配置します。個人用は `--user` を使い、skill は `~/.config/devin/skills/fugue-docs`、hooks は `~/.config/devin/config.json` に置きます。`--hooks` を省略すると skill のみです。CLI の `/hooks` で読み込みを確認してください。Devin Cloud がプロジェクト hooks を読み込むかは未検証で、使用量は常に unknown/不明です。イベントと制限は [Devin ガイド](references/devin.md)を参照してください。

### Claude Code

方法 1:プラグイン・マーケットプレイス(推奨、Claude Code 内で 2 行):

```
/plugin marketplace add AaronXinzhian/fugue-docs
/plugin install fugue-docs@fugue-docs
```

方法 2:個人スキルとして手動インストール:

```bash
git clone https://github.com/AaronXinzhian/fugue-docs.git
cp -r fugue-docs ~/.claude/skills/fugue-docs
```

## 使い方

以下の `/fugue-docs` は Claude Code 向けです。Codex の明示的な呼び出しは `$fugue-docs` を使い、信頼済みのネイティブフックが有効なら日常保守は自動、未使用なら手動手順を使います:

- **自動トリガ**:どのプロジェクトでも、Claude にコードの追加・変更・削除・リネームをさせると、プロトコルが自動適用されます(変更後すぐ L3→L2→L1 のループ更新)。「ドキュメントを初期化して」「プロジェクト構造を整理して」「ドキュメントとコードが合っていない」などの依頼でも発動します。
- **手動呼び出し `/fugue-docs`**:これはシステム組み込みコマンドではありません——Claude Code はインストール済みの各スキルに同名のスラッシュコマンドを自動生成します。明示的にプロトコルを使いたいときは `/fugue-docs` に依頼を添えて入力してください。例:`/fugue-docs このプロジェクトに索引を作って`。
- **CLI ツール**(AI 非依存、単体で使用可能):

| コマンド | 用途 |
|----------|------|
| `python3 scripts/geb_sync.py <プロジェクト>` | 機械フィールド同期:`[INPUT]` 行と台帳テーブルをコードから再生成(意味列は保持)。`--graph` で依存グラフ再描画 |
| `python3 scripts/geb_check.py <プロジェクト>` | 構造チェック。`--strict` ドリフト照合、`--complete` TODO 残存検査、`--report` ループ行、`--emit-facts` 機械ファクト JSON、`--json` で CI 向け |
| `python3 scripts/geb_scaffold.py <プロジェクト>` | 決定論的スキャフォールド。`--dry-run` でプレビュー |
| `python3 scripts/geb_adapt.py <プロジェクト> --tool …` | 他の AI ツールへプロトコルを接続(次節) |
| `python3 scripts/geb_install_codex.py --project <プロジェクト> --hooks` | Codex スキルとフック配置。`--user` 個人用、`--dry-run` プレビュー、`--update` 更新 |
| `python3 scripts/geb_install_devin.py --project <プロジェクト> --hooks` | Devin スキルとネイティブ hooks 配置。`--user` 個人用、`--dry-run` プレビュー、`--update` 更新 |

## あらゆるツール・モデルで使える

プロトコルはツールから分離されています:[adapters/PROTOCOL.md](adapters/PROTOCOL.md) が**可搬なプロトコル・コア**(単一の事実源、中/英)であり、`geb_adapt.py` がそれを任意のツールのルールファイルへコマンド一発で注入します(ハード制約の同時インストールも可能):

```bash
python3 scripts/geb_adapt.py /path/to/project --tool cursor codex --pre-commit
python3 scripts/geb_adapt.py /path/to/project --tool all --lang en --ci
```

対象プロジェクトのルールファイル、`.git/hooks/`、`.github/workflows/` を変更します——実行前に書き込み先一覧を表示します。変更せず確認だけしたい場合は `--dry-run` を付けてください。

| ツール / モデル | 接続方式 | コマンド |
|----------------|---------|---------|
| Claude Code | スキル自動トリガ(最良の体験) | `/plugin install fugue-docs@fugue-docs` |
| OpenAI Codex | ネイティブスキル、または `AGENTS.override.md` / `AGENTS.md` | `geb_install_codex.py --project …` または `--tool codex --copy-tools` |
| Devin | ネイティブスキルと任意 hooks、またはプロジェクト `AGENTS.md` | `geb_install_devin.py --project … --hooks` または `--tool devin` |
| Cursor | `.cursorrules` | `--tool cursor` |
| Windsurf | `.windsurfrules` | `--tool windsurf` |
| Cline / Roo Code(DeepSeek など任意のモデル) | `.clinerules` | `--tool cline` |
| GitHub Copilot | `.github/copilot-instructions.md` | `--tool copilot` |
| 任意のチャットモデル(Grok / DeepSeek Web など) | `GEB_PROTOCOL.md` をシステムプロンプトに貼り付け | `--tool generic` |
| 任意の git リポジトリ(AI 非依存) | 不一致コミットを pre-commit が拒否 | `--pre-commit` |
| 任意の CI | GitHub Actions 検査ワークフロー | `--ci` |

注入は**冪等**です:プロトコルは `GEB-PROTOCOL BEGIN/END` マーカーの間に書かれ、再実行時はその場で更新、ルールファイルの他の内容には一切触れません。`--pre-commit` のフックは自己完結型(チェッカーを同梱コピー)で、本リポジトリへの依存はありません。低コンテキストのモデルやルール字数制限のあるツールには `--compact` で約 300 語の簡約版を注入できます。

**なぜ Claude 以外のモデルでも同等に近い効果が出るのか?** プロトコルが「モデルの自覚」への要求を決定論的ツールへ体系的に移したからです:スキャフォールドは明示的な `TODO` 作業リストを、チェッカーは違反の逐条リストを出力し、pre-commit/CI がそれを無視できないフィードバックに変えます。モデルに必要なのは「エラーメッセージを読んで直す」能力だけ——現代のモデルなら全て備えています。強いモデルほど意味の質は上がりますが、**構造の完全性はツールが保証し、モデルに依存しません**。

## 構成

```
fugue-docs/
├── SKILL.md                       # プロトコル本体(教義、ルーティング、ループ、戒律)
├── references/templates.md        # L1/L2 テンプレート + 13 言語の L3 ヘッダテンプレート
├── adapters/PROTOCOL.md           # 可搬なプロトコル・コア(中/英、単一の事実源)
├── scripts/geb_check.py           # 同型性チェッカー(単体利用可、CI 対応)
├── scripts/geb_scaffold.py        # 決定論的スキャフォールド(静的解析)
├── scripts/geb_adapt.py           # 汎用アダプタ:任意ツールへ注入 + ハード制約導入
├── scripts/geb_install_codex.py   # Codex スキルと任意のネイティブフック配置
├── scripts/geb_codex_hook.py      # Codex イベント:帰属追跡、自動同期、意味の通知
├── scripts/geb_install_devin.py   # Devin スキルと任意のネイティブ hooks 配置
├── scripts/geb_devin_hook.py      # Devin イベント:帰属追跡、自動同期、意味の通知
├── scripts/geb_codex_metering.py  # Codex ネイティブフックのローカル計量
├── scripts/geb_codex_config.py    # フック設定の管理対象マージと競合確認
├── scripts/geb_hook.py            # Claude Code フック:セッション基準、自動同期、意味の欠落の指示、会話記録の計量
├── adapters/DEVIN*.md             # Devin 実行規約(中/英)
├── scripts/geb_stop_hook.py       # 旧版 Stop フック:全体検査、違反があれば終了不可
├── hooks/hooks.json               # プラグイン同梱のフック登録
├── references/manual-workflow.md  # Codex などの明示的な同期・検査手順
├── references/codex.md            # Codex の配置、呼び出し、環境の説明
├── references/devin.md            # Devin の配置、イベント、未検証項目と保守の境界
├── references/codex-hooks.md      # Codex イベント、保守の境界、プロトコル参照元
├── scripts/git-pre-commit-hook.sh # git pre-commit フック:ツール非依存のハード制約
├── .claude-plugin/                # マーケットプレイス配布マニフェスト
└── evals/evals.json               # テストケースとアサーション(再実行可能)
```

### 決定論的スキャフォールド(大規模プロジェクトの初期化を高速化)

```bash
python3 scripts/geb_scaffold.py /path/to/project           # 骨格生成(冪等。既存内容は決して上書きしない)
python3 scripts/geb_scaffold.py /path/to/project --dry-run # プレビューのみ
```

`[INPUT]` は import 解析、`[OUTPUT]` は export 解析(Python は AST、その他はパターンマッチ——C/C++/C#/Ruby/PHP/Swift/Shell/Scala/Lua/Objective-C など、対応拡張子を言語別のベストエフォート解析で処理)で算出し、ディレクトリツリーと Mermaid 依存グラフの草案も同時生成。意味的な箇所([POS]・モジュールの役割)は `TODO` として残します。大規模プロジェクトの初期化が「全ファイル精読」から「意味の補完」に変わり、手作業での事実転記を減らします。token の純削減量は対照測定が必要です。

### ハード制約モード(任意、推奨)

**Claude Code ユーザー**:プラグインを入れるとフックが自動で有効になります。ルートに `PROJECT_INDEX.md` があるプロジェクト(=プロトコル採用済み)では、各ターン終了時に機械フィールドを同期し、このセッションで生じた意味の欠落だけをモデルに渡します。未採用プロジェクトには一切干渉しません。スキルを手動で入れた場合は `~/.claude/settings.json` に追加:

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "timeout": 30,
      "command": "python3 \"$HOME/.claude/skills/fugue-docs/scripts/geb_hook.py\" session-start"}]}],
    "UserPromptSubmit": [{"hooks": [{"type": "command", "timeout": 30,
      "command": "python3 \"$HOME/.claude/skills/fugue-docs/scripts/geb_hook.py\" prompt"}]}],
    "PreToolUse": [{"matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash", "hooks": [{"type": "command", "timeout": 30,
      "command": "python3 \"$HOME/.claude/skills/fugue-docs/scripts/geb_hook.py\" pre-tool"}]}],
    "PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "timeout": 30,
      "command": "python3 \"$HOME/.claude/skills/fugue-docs/scripts/geb_hook.py\" post-tool"}]}],
    "Stop": [{"hooks": [{"type": "command", "timeout": 60,
      "command": "python3 \"$HOME/.claude/skills/fugue-docs/scripts/geb_hook.py\" stop"}]}],
    "SessionEnd": [{"hooks": [{"type": "command", "timeout": 30,
      "command": "python3 \"$HOME/.claude/skills/fugue-docs/scripts/geb_hook.py\" session-end"}]}]
  }
}
```

フックはこのセッションで変更し、まだコミットしていないファイルだけを扱うため、以前からのずれでモデルが止められることはありません。それは pre-commit と CI に任せます。小規模プロジェクトの上限を超えたときは、L1 に書かれた役割を新しく作る FOLDER_INDEX.md に移し、失いません。`FUGUE_HOOK_QUIET=1` でセッション開始時の案内を無効にできます。旧版 `geb_stop_hook.py` も残しています。プロジェクト全体を検査し、違反があれば終了を止める最も厳しい設定です。`geb_hook.py stop` と同時に登録しないでください。

**他ツールのユーザー**:上記「あらゆるツール・モデルで使える」を参照——`geb_adapt.py --pre-commit` 一発で同じコミットゲートを導入できます(自己完結型、本リポジトリへの依存なし)。両相不一致のコミットは、書いたのが人間でもどの AI でも拒否されます。

**チーム導入パス**(軽い順に、一足飛びにしない):① まず `geb_adapt.py --dry-run` で変更内容を確認;② 1 リポジトリで pre-commit を 1〜2 週間試運転;③ 価値を確認できたら CI をチームのゲートに昇格;④ グローバル skill はヘビーユーザーの個人オプトイン。強制の強さは信頼に従うべきで、先行してはいけません。

## 実測データ

評価方法:現実的な 3 シナリオ × スキル有/無の対照実験。各側を独立した Claude Code サブエージェントが実行(互いの存在を知らない)し、16 のアサーションすべてをスクリプトで自動判定(人間の印象ではない)。完全な評価パッケージ(テストケース + プロジェクト・フィクスチャ + 自動採点器)は [evals/](evals/README.md) に同梱、再実行手順もそこにあります。正直な注記:下表は**各シナリオ 1 回の実行(n=1)**の結果です。時間・トークンの絶対値は参考程度とし、アサーション通過率を主要指標としてください。再実行歓迎。

| シナリオ | スキル有 | ベースライン | 所要時間(有 / 無) | トークン(有 / 無) |
|----------|---------|-------------|--------------------|--------------------|
| レガシープロジェクトのドキュメント初期化 | **5/5** | 4/5 | **222s** / 367s | 37.9k / 35.7k |
| 機能追加後のループ維持 | **5/5** | 5/5 | 140s / 139s | 24.4k / 21.8k |
| リファクタ後の幽霊参照の掃除 | **6/6** | 6/6 | 127s / 110s | 24.9k / 21.0k |

この表は各シナリオ 1 回の観測です。初期化は 222 秒対 367 秒でしたが、一般的に 40% 高速化するとは結論できません。3 件すべてでスキル有の token 数がベースラインを上回っています。新しいプログラム主導の処理の効果は、別途測定する必要があります。

v2.3 の 30/30 は同じ 6 グループを 5 回繰り返した結果であり、独立した 30 シナリオではありません。意味の正確さや token 削減の証明ではありません。理解テストのキーワード採点には別途品質確認が必要で、欠損 token は不明として保持します。

## プロジェクトの現状と適用範囲

率直に言えば、これは若いプロジェクトです(2026 年 6 月公開)。以下の範囲で適合を判断してください。

**適している**:AI が開発の主力である個人・小規模チームのプロジェクト;ドキュメントのないレガシーコードの引き継ぎ(スキャフォールドで骨格生成 + AI が意味を補完);新しい AI セッションや新メンバーが入った瞬間に構造を理解できるべき長期保守プロジェクト。

**慎重に / まだ向かない**:AI をほぼ使わないチーム——ループの保守コストは AI が担ってこそ釣り合います;超大規模 monorepo——再帰フラクタル対応は実装されたばかりで、実戦検証が不足しています;また、万能ドキュメントソリューションではありません——担当するのは**構造と依存の同期**であり、チュートリアル・API リファレンス・設計書は対象外です。

**検証状況(正直に)**:小規模なスクリプト判定の対照実験(各シナリオ n=1、再実行可能)+ 本リポジトリ自身のドッグフーディング(push ごとに CI が --strict 自己検査)+ 複数回の外部モデルレビュー(全指摘と対応はコミット履歴に記録);**チームでの長期運用データはまだありません**。問題を見つけたら issue を——批判を消化することがこのプロジェクトの開発手法です。

## ライセンス

[MIT](LICENSE)。プロトコルの思想は趙純想氏に、『ゲーデル、エッシャー、バッハ』はダグラス・ホフスタッター氏に帰属します。本リポジトリのコードとテキストは独立した創作物です。
