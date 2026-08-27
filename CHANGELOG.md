# 変更履歴

版の付け方は [semver](https://semver.org/lang/ja/)。`VERSION` / `.claude-plugin/plugin.json` / `.claude-plugin/marketplace.json` の 3 つは常に同じ値を持ち、`tests/smoke.sh` case 9 が一致を検証する。

更新のしかたは [README の「更新する」](README.md#更新する自動では新しくなりません)。**プラグインは自動更新されない。**

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
