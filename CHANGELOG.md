# 変更履歴

版の付け方は [semver](https://semver.org/lang/ja/)。`VERSION` / `.claude-plugin/plugin.json` / `.claude-plugin/marketplace.json` の 3 つは常に同じ値を持ち、`tests/smoke.sh` case 9 が一致を検証する。

更新のしかたは [README の「更新する」](README.md#更新する自動では新しくなりません)。**プラグインは自動更新されない。**

## v1.4.0

- **`/init` を「聞いてから実行する」に変えた。** v1.3.0 までは引数なしで実行すると、何も聞かずに置き場所を決め、`docs/` の有無を見て台帳の場所を決め、`templates/settings.json` をそのまま配置して **`ultracode` を有効にし**、終わってから「不要なら false にしてください」と報告していた。**利用量（費用）が増える設定を、承諾を取らずに有効にして事後報告していた**のが問題。手順 1 を新設し、**1 バイトも書き込む前に** 3 つ（どこに入れますか / ファイルの置き場所 / 濃いめに考える設定を有効にしますか）を 1 通で尋ねて返事を待つようにした。既定を明示してあるので「はい」の一言で全部既定のまま進む。
- **質問 2 は推測でなく実測を書く。** 新設の手順 0（読むだけ。書き込まない）で `docs/` の有無と既存ファイルの有無を先に調べ、**確定した配置先**を質問文に埋める（「ある場合は… ない場合は…」と両論併記しない）。`${TMPDIR}` に `docs/` あり・なしの空プロジェクトを作って逐語実行し、それぞれ `docs/tasks/list.md` / `.claude/tasks/list.md` になることを実測した。
- **「有効にしない」の分岐を追加。** 質問 3 で有効にしないと答えられた場合、配置後に `ultracode` と `workflowSizeGuideline` の 2 キーを落とす。実測した結果は top-level が `statusLine` と `permissions` の 2 キーのみで、`deny` 6 件 / `ask` 8 件は保全され、JSON も妥当（`python3 -m json.tool` exit 0）。全プロジェクト共通（`user`）指定と併用しても、`statusLine.command` の絶対パス化と両立する。
- **進め方（`mode.yml`）は聞かない。** 質問を増やしすぎないため既定の「確認あり」で置き、報告に `後から /hirai-lite:mode loop で「いちいち確認しない」に変えられます` の 1 行を添える形にした。
- **再実行時は質問しない。** 手順 0 で配置先の 4 つ（`rules` / `settings.json` / `mode.yml` / `statusline.sh`）が揃っていれば質問を全部省き、「すでに一式が入っています。今回は何も上書きしません」と 1 行伝えて進む。`settings.json` だけがある場合も質問 3 を省き、差分提示に回す（上書きしないため聞く意味がない）。
- **`$CLAUDE_PLUGIN_ROOT` が空でも動くようにした。** 実行ログで `PLUGIN_ROOT=[]` と空になり、AI がキャッシュを手で探して回避していた。解決順を `$CLAUDE_PLUGIN_ROOT` → `~/.claude/plugins/cache/hirai-lite/hirai-lite/<版>/` の**最新版**（`sort -V`）→ `~/.claude/plugins/marketplaces/hirai-lite` と明記し、素材を読むブロックの先頭に同じ 1 行を置いた。偽 HOME に `1.9.0` と `1.10.0` の 2 版を置いて空実行し、`1.10.0` が選ばれること、3 段目でも動くこと、どちらでも結果が既定と完全一致することを実測した。**なぜ空になるかの原因は特定できていない**（確実に動く手順を優先した）。
- **手順の中身は変えていない。** 何を配置するか・冪等性・`docs/` 解決順は v1.3.0 と同じ。既定のまま進めた結果を v1.3.0 の手順の結果と `diff -r` / `shasum` で突き合わせ、**14 ファイル完全一致**（回帰なし）。2 回実行しても shasum は一致する。
- 予算は据え置き（T0 警告 6,000 / 上限 10,000、hook 5 / command 12 / smoke case 10）。**T0 実測 3,652 tokens**（`rules/` は未変更）。hook 2 / command 12 / smoke 10 case は全 PASS / exit 0、`claude plugin validate` も PASS。`commands/init.md` は 147 → 198 行（自らに課した上限 200 行以内）。

## v1.3.0

- **常時読まれる分 (T0) の予算を 2 段階にした。** 上限 3,000 tokens の 1 段階では実測 2,890 に対し残り 110 しかなく、ルールを 1 行足すだけで上限に触れていた。**6,000 tokens で警告（PASS のまま。余裕があるうちに降格候補を決める）／ 10,000 tokens で FAIL** に変更（`tests/smoke.sh` case 4 / `rules/_meta.md` 条 3）。3 パターン（現状値・6,000 超・10,000 超）を実測して判定が効くことを確認した。**上限を上げても「既定は入れない」原則は変えない** — 条 2 のとおり新規ルールの既定は T1 で、T0 に置くには立証が要る点を `_meta.md` と README で明記した。
- **今回の実失敗から T0 に規範を 3 件追加。** いずれも本セッションで 2 回以上踏んだもの（条 1「事故 2 回目でルール化」に適合）。**宣言と実体を突き合わせる**（`plugin.json` のキー衝突で v0.1.0〜v0.6.0 が登録 0 件のまま公開され、`validate` は PASS していた）／ **テストは壊して確かめる**（smoke の空振り 2 件をこの手法で発見した）／ **同種の欠陥を横に探す**（scope 決め打ちを 1 コマンドだけ直し、mode 解決 3 か所と 2 コマンドに残していた）。
- **T1 の 2 件を T0 へ昇格。** 「レビューは並列で立てる」「判断を求められたら止まる」は `rules/code.md`（`src/**` 等でのみロード）に置いていたが、コード以外の作業でも同じく要るため `rules/core.md` へ移した。`code.md` からは削除し、重複させていない。
- **詰め込んでいた 2 条を複数行に展開**（Loop モードと「事実で答える」）。内容は変えていない。
- **`rules/_meta.md` に条 9「無い保証を書かない」を追加。** 機械強制が無い事項を「BLOCK する」「禁止する」と書かない。前身のハーネスは docs に「BLOCK」と書きながら実際には止まらない状態を作り、AI が存在しない制約に萎縮する帰結を招いた。このハーネスは機械強制がほぼ無いため、強制の語で書けば同じ失敗を再現する。
- **`docs/rules-reference/plugin-development.md` 項目 3 の表現を緩和。** 公式 `plugin-dev` プラグインの `plugin-structure` skill を「誤り」と名指ししていた箇所を、「公式 plugins-reference (Path behavior rules) と記述が異なるため公式仕様を優先する」という書き方に改めた。実測で確認した事実（`commands` キーを書くと既定フォルダが置換され登録 0 件になる）と回避方法はそのまま残している。
- T0 実測は 2,890 → **3,652 tokens**（警告線 6,000 の下）。hook 2 本 / command 12 個 / smoke 10 case は変更なし（全 PASS / exit 0）。

## v1.2.0

- **前ハーネス (hirai-method) の実務ノウハウを T2 参照層 (`docs/rules-reference/`) へ移植。** 主題別に 9 ファイルを新設した（並列実行・委譲 / レビューの収束判断 / 設計・承認 / タスク台帳 / テスト / git・PR / shell / プラグイン開発 / コンテキスト予算と出力）。いずれも常時ロードされないため **T0 予算 (3,000 tokens) には影響しない**（実測 2,890 tokens で据え置き）。前ハーネス固有の機械強制 (hook / preset / 各種 guard) に依存する記述は持ち込まず、仕組みが無くても再発しうる事例だけを残した。
- **事故台帳を 2 つに分離。** `incidents.md` は `rules/_meta.md` 条 1「事故 2 回目で初めてルール化する」の**判定に使う唯一の台帳**なので、**このハーネスで起きた事故だけ**を置く（現在 5 件）。前ハーネス由来の 33 件は、最初から再発回数 2 を持つものを含み、混ぜると**一度も起きていない事象が「2 回目」と数えられて推測ルールが生える**。参考資料として `incidents-legacy.md` に分離し、そちらの再発回数は判定に使わないことを両ファイル冒頭に明記した。`incidents.md` が数行しかないのは正常。
- 公開に先立ち `docs/rules-reference/` 全 11 ファイルを個人情報・社内固有名・秘密情報の観点で点検。前ハーネスの commit hash 1 件と PR 番号 3 件（公開後に本リポジトリの PR へ誤リンクする）を一般化した。
- smoke は 10 件のまま、内容の変更なし（全 PASS / exit 0）。

## v1.1.0

- **進め方 (`mode.yml`) の探し方が 3 か所でバラバラだった不具合を修正。** セッション冒頭の表示 (`hooks/session-start.sh`) はプロジェクト側しか見ず、画面下部 (`scripts/statusline.sh`) はホーム側も見て、`/mode` (`commands/mode.md`) は `.claude/mode.yml` 決め打ちだった。全プロジェクト共通 (`/init user`) に `mode: loop` を置くと、**冒頭は「確認あり」・画面下部は「自動」と食い違う**（実測で再現）。さらに `/mode loop` を叩くと、設定していないプロジェクトに `.claude/mode.yml` が新設され、共通側を黙って覆い隠していた。解決を `scripts/tasks-path.sh` の `harness_mode` / `harness_mode_file` / `harness_mode_write_file` の 3 関数に集約し、**3 か所とも同じ関数を通す**ように変更。解決順は `HC_MODE` → プロジェクト側 → ホーム側 → `normal`。**`/mode` の書き込み先は「すでに在る側」**とし、両方に無いときだけプロジェクト側に作る（`/update` が v0.9.0 で採った「在る側だけ扱う」方式と揃えた）。
- **`/add-rule` と `/rules-audit` が全プロジェクト共通のルールを見ていなかった不具合を修正。** 両コマンドが `.claude/rules/*.md` を決め打ちしていたため、`/init user` で `~/.claude/rules/` に置いた利用者に対し、**常時読まれる分の予算計算も重複検査も対象 0 件で走っていた**（実測: T0 が 0 tokens と出る）。「既存ルール無し」と誤判定して重複ルールを追加でき、`rules/_meta.md` の条 3（予算制）と条 7（パイプライン）が実質無効になっていた。置き場の解決を `harness_rules_dir` に集約し、両コマンドから使うよう変更。2 か所に在る場合は `scripts/scope-check.sh` の二重ロード警告を先に出し、**予算は 2 か所の合計で効いている**ことを明記した。
- **同梱する外部ツール接続 (MCP) の版を固定。** `serena` は `git+…/serena`（ref なし = 既定ブランチの最新コミット）、`context7` は `@latest` だったため、**利用者の環境で配布元の任意のコミットが実行される**状態だった。プラグイン同梱の MCP は承認を挟まずつながるため、公開配布物としては固定が要る。`serena` をタグ `v1.7.0`、`context7` を `4.0.3` に固定し、両方が実際に起動することを実測で確認。更新したいときの手順を README に追記。
- **`CONTRIBUTING.md` を新設。** マーケットプレイス定義の `source: "./"` は既定ブランチ (`main`) の HEAD を指すため、**タグを打っても利用者に届くのは常に `main` の最新コミット**。`main` に途中の状態を push した瞬間、未リリース状態が全利用者に配布される。「**`main` は常に配布物。リリース可能な状態だけを置く**」ことを明記した（ブランチ運用の変更は今回行わず、選択肢と代償だけを記載）。
- **README に 2 点追記。** 外部ツール接続を自分で設定済みの場合、起動コマンドが完全一致すると重複としてまとめられ、プラグイン側が登録されないことがある（動作に支障は無いが `plugin details` の表示が実態と違って見える）。実際につながっている一覧は `claude mcp list` で確かめる。
- smoke は 10 件のまま（上限）。**既存 case を拡張**した。case 1 に進め方の一致検査（置き場 5 通りで冒頭と画面下部が一致すること、`/mode` が在る側に書くこと）、case 4 にルールの置き場の解決検査（4 通り）、case 10 に同梱 MCP の版固定検査を追加。いずれも v1.0.0 のコードに当てると落ちることを実測で確かめた。

## v1.0.0

- **画面下部の表示にお知らせ枠を追加。** いちばん右に、上から見て当てはまった 1 つだけを出す（1: `更新あり → /hirai-lite:update` / 2: ctx が閾値以上のとき `きりの良いところで /hirai-lite:state save`）。どちらでもなければ区切りごと出さない。止めるなら `HC_STATUSLINE_NOTICE=off`。
- **お知らせ枠は通信しない。** 画面下部は何度も描き直されるため、`scripts/statusline.sh` からは一切通信せず、SessionStart 側 (`scripts/update-check.sh` の `harness_update_flag_sync`) が置いた控え 1 ファイル (`${TMPDIR:-/tmp}/claude-harness-lite/update-available`) の有無を見るだけにした。到達不能な URL を設定しても遅くならないことを実測（38ms）。`${CLAUDE_PLUGIN_ROOT}` が settings.json で展開されず、画面下部からはプラグインの `VERSION` もキャッシュ dir も見えないため、版の比較は SessionStart 側で済ませて結果だけを渡す形にしている。
- **`/state save` の最後に復帰手順の案内文を定義**（`commands/state.md`）。保存先 → `/clear` → `/hirai-lite:state resume` の順に、平易な日本語で出す型を追加。
- **`/clear` の挙動を公式ドキュメントで確認し、README に「`/clear` と続きの再開」節を追加。** `/clear` は「空のコンテキストで新しい会話を始める」操作で、`CLAUDE.md` と `.claude/rules/` は「毎回の会話のはじめに読み込まれる」ため、`/clear` の後もルールは消えない。閉じて開き直すのと結果は同じ。ただし両者が細部まで同一である旨の記述は公式に無いため、その点は「確認できず」と明記した。
- smoke は 10 件のまま。case 1 に画面下部の fail-open（空 stdin / 壊れた JSON / 控えが不在・空・壊れ）を、case 8 にお知らせ枠の優先順位・`off` での停止・閾値可変・通信しないことの検査を追加した。

## v0.9.0

- **`/update` が全プロジェクト共通 (`/init user`) の導入先を更新しない不具合を修正。** 手順 3 が入れ替え先を `.claude/` に決め打ちしていたため、`/hirai-lite:init user` でホーム側 (`$HOME/.claude/`) に入れた人は、実際に使われている `~/.claude/statusline.sh` が古いまま残り、使われないコピーがプロジェクト側に新しく作られていた（実測で再現）。**プロジェクト側とホーム側の両方を見て、すでに在る側だけを入れ替える**ように変更（置いていない場所に新規作成しない）。
- **`/update` 手順 1 のコマンドを正確化。** `/plugin marketplace update hirai-lite` → `/plugin update hirai-lite@hirai-lite` の 2 行と、1 行目を飛ばすと 2 行目が古い控えを見て「最新です」と答えることを明記。ターミナル実行時に `--scope` の既定が `user` である点も追記。
- **更新の合図が出ない条件を文書化。** 合図は「入れた直後の 1 セッション目」と「前回調べてから 24 時間」の間は必ず沈黙する。**合図が出ないことは最新であることの証明にならない。** いますぐ確かめる手順（リモートの `VERSION` と `claude plugin list` の比較、控え `${TMPDIR:-/tmp}/claude-harness-lite` の削除）を README と `/update` に追記。
- **README に「更新する」節を新設**し、v0.6.0 以前の注意を明記。

## v0.8.1

- 利用者向け説明の「リポジトリ」を「プロジェクト」に統一。

## v0.8.0

- 導入手順を 1 節に統合し、入れる範囲は **Local** を推奨に変更。

## v0.7.0

- **`plugin.json` の `hooks` キー衝突を解消**（`9b9e991`）。`hooks` / `commands` / `agents` の 3 キーを外し、Claude Code の既定配置（`hooks/hooks.json` / `commands/` / `agents/`）に任せる形へ。**v0.6.0 以前で出ていた `✘ failed to load` はここで解消した。**
- インストール時に表示される確認の説明を追記。

## v0.6.0 以前 — `✘ failed to load` と表示される（要更新）

**v0.1.0 〜 v0.6.0 には不具合がある。** `plugin.json` の `hooks` キーが、Claude Code が自動で読み込む `hooks/hooks.json` を二重に指していたため、`/plugin` の一覧や `claude plugin list` で次のように表示される。

```
Status: ✘ failed to load
Error: Hook load failed: Duplicate hooks file detected: ./hooks/hooks.json resolves to
already-loaded file …/hooks/hooks.json. The standard hooks/hooks.json is loaded
automatically, so manifest.hooks should only reference additional hook files.
```

**Claude Code 2.1.247 で実測した範囲では、この表示が出ていても機能そのものは動いていた** — v0.6.0 を実際にインストールして計測したところ `Registered 2 hooks` / `Total plugin commands loaded: 12` / `Total plugin agents loaded: 3` で、MCP サーバー 2 つ（`serena` / `context7`）も接続できた。ただし `claude plugin details` はエージェント数を 0 と誤表示する。

とはいえ「読み込みに失敗した」と表示され続けるのは正常な状態ではなく、Claude Code の版によっては本当に読み込まれない可能性がある。**該当版を入れている場合は [README の「更新する」](README.md#更新する自動では新しくなりません)の手順で v0.7.0 以降へ更新すること。**

| 版 | 主な内容 |
|---|---|
| v0.6.0 | README を平易化し、`/hirai-lite:init user`（全プロジェクト共通への配置）に対応 |
| v0.5.0 | MCP サーバー 2 種とエージェント 3 種を同梱。`/update` の更新漏れを修正 |
| v0.4.0 | `/init` と mode の表示を平易な日本語に |
| v0.3.0 | `docs/` 非依存の徹底と `/init` 手順の欠陥 6 件を修正 |
| v0.2.0 | `ultracode` を既定で有効化 |
| v0.1.0 | Claude Code プラグイン構成へ移行（`install.sh` 廃止） |
