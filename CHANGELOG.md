# 変更履歴

版の付け方は [semver](https://semver.org/lang/ja/)。`VERSION` / `.claude-plugin/plugin.json` / `.claude-plugin/marketplace.json` の 3 つは常に同じ値を持ち、`tests/smoke.sh` case 9 が一致を検証する。

更新のしかたは [README の「更新する」](README.md#更新する自動では新しくなりません)。**プラグインは自動更新されない。**

## v1.12.0

- **案件ヒアリング（`/init` の 2 回目）が、リポジトリの開発と無関係な質問を出す問題を直した。** 実使用で「弁護士費用パッケージの一括発注（予算枠の確保）」という調達・法務の質問が出て、「意味わかりません」と報告された。**原因は `commands/init.md` の第 2 段階が、`grilling` に観点だけを渡し、事実を 1 つも渡していなかったこと。** 手順 10-1 は「ゴール / 背景 / スコープ / 体制 / …を明らかにせよ」という抽象的な観点の列挙で、足がかりが無い。`grilling` は前提が確定した質問から design tree を広げる skill なので、材料がゼロだと**案件一般で聞かれそうな問い（予算・調達・契約）に流れる**。加えて**対象範囲の制約がどこにも書かれておらず**、枝が無制限に伸びた。
- **「事実は自分で調べる」という 1 文自体は v1.8.0 から書いてあった。** ただし置き場所が悪く、`grilling` の呼び出しと同じ 1 段落の中の従属節だった。そのため (a) 呼び出しより**前に**調べることが手順として強制されず (b) **調べた事実が `grilling` へ渡されず**（この文は外側のエージェント宛てで、skill の指示文には 1 文字も入らない）、原則が実質的に効いていなかった。`grilling` 自身は「事実調査は AI の仕事、決定は user の仕事」を明記しているので、**skill の欠陥ではなく渡し方の欠陥**である。
- **第 2 段階を 事実収集 → 範囲提示 → `grilling` 呼び出し の 3 手順に分けた**（手順 10-1 / 10-2 / 10-3。以降は 10-4 / 10-5 / 10-6 に繰り下げ）。10-1 は README / 設定ファイル（`package.json` `pyproject.toml` `go.mod` `Cargo.toml` `composer.json` `Gemfile` `pom.xml` `build.gradle` `Makefile` `requirements.txt` `deno.json` `.github/workflows`）/ フォルダ構成 / `git log` / 既存の `docs/` を読む bash 5 行で、**空のリポジトリでも見出しだけを並べて exit 0 を返す**（`set -e` 付きでも落ちない）。10-2 は分かったことを「ここまでは自分で調べました」の型で**利用者に見せてから**質問に入る。
- **`grilling` へ渡す指示に、対象範囲の制約を明文で載せた。**「このリポジトリのソフトウェア開発に関する決定に限る」「調達・法務・人事・営業・予算枠・契約・発注など、利用者が自分から挙げていない領域には踏み込まない（利用者がその話題を自分から出したときだけ扱ってよい）」「事実は自分で調べ、利用者に聞くのは決定だけ」「『その質問は不要』と答えられた質問はその枝ごと即座に落とし、言い換えて聞き直さない」の 4 項目。あわせて 10-2 の型に「聞く必要のないことがあれば『その質問は不要』と言ってください」の 1 行を入れ、**範囲外の質問が出たときに利用者が止められる**ようにした。
- **空のリポジトリでは、まず「何を作りますか」の 1 問だけ聞く。** 材料がゼロの状態で多数の質問を出すと、今回と同じ「一般論からの質問生成」に戻るため。その答えを「分かっている事実」に足してから広げる。
- **`skills/grilling/SKILL.md` は 1 バイトも変えていない**（MIT の同梱物）。sha256 = `10ff989e7498b23b5acb49d5048f11dcd906757d2f79c5cdf8a00001381296f2`（1,987 bytes）が `NOTICE.md` の記載と一致することを実測で確認した。直したのは `commands/init.md` の**渡し方**だけである。
- **再発検査は既存の case 1 に追加した（case は 10 のまま増やしていない）。** case 1 はすでに `commands/update.md` の移行手順を**逐語に取り出して実行**しており、「手順書そのものを走らせる」検査の置き場として揃っている。追加したのは (a) 並びが 事実収集 → 範囲提示 → `grilling` 呼び出し の順であること（位置を見出し番号ではなく**中身**で拾うので、番号を振り直しても壊れない）(b) 事実収集の bash を取り出し、**README + `package.json` のあるプロジェクト**と**空のプロジェクト**の 2 つで実行して exit 0 と出力内容を見る (c) `grilling` へ渡す指示に `調達` / `法務` / `踏み込まない` / `その質問は不要` / `自分で調べる` が入っていること。**壊して確かめた**: 事実収集の bash を消す・範囲の制約を消す・`grilling` 呼び出しを事実収集より前に動かす・空リポジトリで落ちるように壊す、の 4 通りいずれでも `FAIL case 1` になり exit 1 になる。
- 予算は据え置き（T0 警告 6,000 / 上限 10,000、hook 5 / command 12 / skill 3 / smoke case 10）。**T0 実測 4,114 tokens で v1.11.0 から変化なし**（`rules/` と `templates/CLAUDE.md` を触っていない。`commands/init.md` は呼ばれた時だけ読まれるので T0 に入らない）。hook 3/5・command 12/12・skill 1/3・smoke case 10/10 も据え置き。`commands/init.md` は 260 → **298 行**（自ら課した上限 300 行の内側）。
- **実測。** (1) 事実収集の bash を 3 通り（README + `package.json` あり / 空 / 空 + `set -e`）で実行し、いずれも exit 0。中身のあるほうでは `name: demo-app` `scripts: dev, test` `deps: next, react` と構成・`git log`・`docs/overview.md` が出た。(2) 第 2 段階の判定条件（v1.8.0 実装）は 3 通り（4 点セット + プレースホルダあり → 第 2 段階 / プレースホルダ 0 → 第 1 段階 / 4 点セット不足 → 第 1 段階）とも従来どおり。(3) 新規 `/init`（第 1 段階、手順 2〜8）を偽 HOME の空プロジェクトで通し、rules 5 件（T0 2 / T1 3）・妥当な JSON・`rules-archive/.gitkeep`・`statusline.sh`・`mode: normal` 1 行・`CLAUDE.md`・台帳 / parking-lot / incidents / `draft/` がすべて揃い、続けて手順 0 が「第 2 段階へ」と出すことを確認した。(4) smoke 10 case 全 PASS / exit 0、`claude plugin validate --strict` PASS。(5) 公開版を偽 HOME に実インストールして第 2 段階の記述が届いていることを確認した。
- 事故台帳（`docs/rules-reference/incidents.md`）に 1 行追加した（2026-08-31、再発回数 1）。

## v1.11.0

- **`loop`（自動で進む）の途中停止に対処するため、進め方を毎ターン思い出させる hook を足した（`hooks/loop-reminder.sh`、3 本目）。** 実使用で「lite の loop 機能してますか? よく止まりますが..」と報告された。調べると `loop` の規範は `rules/core.md` の 3 行だけで、**それを維持する仕組みが 1 つも無かった**（前身のハーネスには毎ターン再注入 / 待機停止の検出 / 確認質問の検出の 3 本があったが、lite ではすべて廃止した）。`core.md` はセッション開始時に一度読まれるだけなので、会話が伸びるほど効きが薄れて途中で止まる。UserPromptSubmit で毎ターン 4 行だけ要点（止まる条件は 3 つだけ / subagent の完了待ちは停止理由にならない / 新しい設計の追加・決めた内容の変更・元に戻せない操作は `loop` でも確認する）を差し込む。
- **`normal`（確認あり）では 1 バイトも出さない。** 確認しながら進めたい利用者に毎ターン「確認を求めるな」が入るのは機能ではなく害なので、無出力を最優先の検査項目に置いた（`tests/smoke.sh` case 2 が置き場 6 通り＝ホーム側 / プロジェクト側 / 両方 / 無し で出す・出さないを見る）。進め方の解決は `scripts/tasks-path.sh` の `harness_mode` に通していて、セッション冒頭・画面下部・`/config` と同じ 1 本を使う（ここで独自に解決しない）。止めるときは `HC_LOOP_REMINDER=off`。
- **これは `_meta.md` 条 5「機械強制は不可逆操作のみ」の例外ではなく、対象外である。** 条 5 が禁じているのは**止める**仕組み（無害な操作を BLOCK して速度を削り、やがて無効化されて規範と実挙動の乖離を生む guard）であって、今回足したのは context を注ぐだけで何も止めない reminder である。次に読む人が同じ誤りを繰り返さないよう、**この判断を `rules/_meta.md` 条 5 の条文そのものに 1 文で書き足した**（「本条が禁じているのは止める仕組みなので、context を注ぐだけの hook（reminder / 表示）は対象外」）。README の設計方針 3 にも同じ 1 文を足している。
- **Stop hook による確認質問の検出は、あえて入れなかった。** 前身のハーネスは「進めてよいですか」等を AI の最終出力から regex で検出して次ターンに是正を注ぐ hook を持っていたが、(a) hook が 1 本増える (b) 誤検知したときの帰結が「**聞くべきときに聞けない**」という悪化方向である、の 2 点から見送った。まず reminder 1 本で様子を見て、それでも止まるようなら再検討する。
- 数の予算は hook 2/5 → **3/5**（上限 5 の範囲内、`tests/smoke.sh` case 6）。command 12/12・skill 1/3・smoke case 10/10 は据え置き。T0 常時ロードは 4,070 → **4,114 tokens**（警告線 6,000 / 上限 10,000。増分 44 tokens は条 5 への 1 文追記のみ）。
- **`claude plugin details` の `Hooks (N)` は、スクリプトの本数ではなく**きっかけ（イベント）の種類数**だと実測で分かった。** v1.11.0 は hook スクリプトが 3 本になるが、表示は `Hooks (2)  SessionStart, UserPromptSubmit` のままである（3 本目を `UserPromptSubmit` にぶら下げたため）。偽 HOME への実インストールを 2 通り（イベント 2 / スクリプト 3 のとき `(2)`、別イベントを 1 つ足したコピーでは `(3)`）行って確かめた。`Skills (13)` がコマンドとスキルの合計だったのと同じ種類の読み違いなので、README の注記に 1 段落として並べた。本数を数えるなら `ls hooks/*.sh` か `tests/smoke.sh` case 6 の `hook=3/5` を見る。

## v1.10.0

- **context 使用率が 2 か所で食い違う不具合を修正した（同じ瞬間に `ctx 17%` と「83% に達しました」が出た）。** 画面下部（`scripts/statusline.sh`）は Claude Code が渡す計算済みの百分率（`context_window.used_percentage`）をそのまま表示し、自動処理（`hooks/context-budget.sh`）は transcript の直近トークン数を **`HC_CONTEXT_WINDOW` の既定 `200000` 固定**で割っていた。窓が 1,000,000 の会話（Claude Opus 5）では分母が 5 分の 1 になり、約 170,000 tokens で画面下部 17% / 自動処理 85%（実測の表示は 83%）と矛盾した。**正しかったのは画面下部の 17%**、誤っていたのは自動処理の 83% である。`17 + 83 = 100` は偶然で、残量と使用率を取り違えていたわけではない（両者とも使用率を見ていた）。
- **計算を共通ライブラリ `scripts/context-usage.sh` に集約し、画面下部と自動処理の両方がそこを通るようにした**（`scripts/tasks-path.sh` の `harness_mode` と同じ作法）。関数は `harness_ctx_window`（分母の解決）/ `harness_ctx_tokens_from_json`・`harness_ctx_tokens_from_transcript`（分子）/ `harness_ctx_percent`（四捨五入した整数の百分率）/ `harness_ctx_threshold`・`harness_ctx_over_threshold`（閾値判定）。**分子は 4 つの合計に統一**（`input_tokens` + `cache_creation_input_tokens` + `cache_read_input_tokens` + `output_tokens`。Claude Code 自身が `exceeds_200k_tokens` を判定する量と同じ）。**閾値の向きも統一**し、両者とも「使用率 >= 閾値」で発火する（片方が残量を見る状態を作らない）。丸めも共通で、v1.9.0 の切り捨て（0.5% → 0%）から四捨五入（0.5% → 1%）に変わる。
- **窓サイズを実測して使うようにした（1M / 200k の自動判別）。** 実サイズは Claude Code が**画面下部にだけ**渡す [`context_window.context_window_size`](https://code.claude.com/docs/en/statusline)（`200000` か `1000000`）にあり、**自動処理（hook）の入力 JSON にも transcript にも環境変数にも無い**（公式ドキュメントで確認。取得手段は画面下部の入力 JSON 1 経路のみ）。そこで画面下部が観測値を `${TMPDIR:-/tmp}/claude-harness-lite/ctx-window-<セッション ID>` に控え、自動処理はそれを読む（更新の合図を SessionStart → 画面下部へ渡しているのと同じ作法）。解決順は `HC_CONTEXT_WINDOW`（env）→ 控え → 既定 `200000`。**既定が外れる条件**（`statusLine` 未設定 / `/init` 未実行 / 1 ターン目でまだ画面下部が描かれていない）と、そのとき使用率が**実際より高く出る**こと（低くは出ない）を README「context 使用率の出し方」に明記した。
- **`/init` と `/update` が入れ替えるプラグイン所有ファイルを 2 本 → 3 本にした**（`statusline.sh` / `tasks-path.sh` / `context-usage.sh`）。画面下部は導入先へ複製されて動くため、共通ライブラリも隣に要る。**v1.9.0 以前から使っている環境には `context-usage.sh` がまだ無い**ので、`/update` の手順 4 は「`statusline.sh` が在る側にだけ新しく置く」を先に行う（置いていない場所には作らない方針は維持）。共通ライブラリが無い環境でも画面下部は 2 行 + exit 0 を返す（使用率だけ Claude Code の計算済みの値に落ちる）。
- **再発検査は既存の case 3 に追加した（case は 10 のまま増やしていない）。** 同じ量と同じ窓を与えて画面下部と自動処理の使用率が 1 の位まで一致することを **窓 2 通り × 5 値**で見る（`in=168000 out=2000 窓=1000000 → 17%` を含む）。併せて (a) 窓が分からなければ 200,000 とみなす (b) `HC_CONTEXT_WINDOW` が控えより優先される (c) 空 stdin / 壊れた JSON / transcript 不在でも無出力 exit 0、を検査する。case 8 の版比較表には `1.9.0 → 1.10.0` と `1.10.0 → 1.9.0` の 2 行を足した。**壊して確かめた**: v1.9.0（`18edeb7`）の `statusline.sh` と `context-budget.sh` に戻し `context-usage.sh` を消すと、`FAIL case 3 … [in=168000 out=2000 窓=1000000] 自動処理=85(期待 17)` で落ち exit 1 になる。
- **`1.10.0` は `1.9.0` より新しい。** 更新検知の比較（`scripts/update-check.sh` の `harness_semver_gt`）は awk による**数値比較**なので、`1.10.0 > 1.9.0` が true、`1.9.0 > 1.10.0` が false になることを実測した（shell の文字列比較 `[ "1.10.0" \> "1.9.0" ]` は false になる。この経路は使っていない）。
- 予算は据え置き（T0 警告 6,000 / 上限 10,000、hook 5 / command 12 / skill 3 / smoke case 10）。**T0 実測 4,070 tokens で v1.9.0 から変化なし**（rules と `templates/CLAUDE.md` を触っていないため）。**コマンドは 12 個ちょうど / hook は 2 本のまま**（`scripts/` は常時ロードの対象外）。`plugin.json` に `hooks` / `commands` / `agents` キーは復活させていない。画面下部は通信しない / 2 行構成 / 色分け / fail-open を維持している。
- **実測。** (1) 同じ入力で画面下部と自動処理が一致（`168000+2000` を窓 1M で 17% / 200k で 85%、`850000` を窓 1M で 85%、`40000` を 200k で 20%、`0` で 0%、全 5 組一致）。(2) 閾値 80% で 79% は無出力、80%（ちょうど）で 1 度だけ発火、同一セッションの 2 度目は沈黙、別セッションの 85% では発火。(3) 色分けは 12%/49% 緑・50%/79% 黄・80%/95% 赤、120% 相当は 100% に丸めて赤（`NO_COLOR` では制御文字なしで同じ数字）。(4) 空 stdin / 壊れた JSON / `context_window` が空 / transcript 不在のいずれでも画面下部は 2 行 + exit 0 で `ctx —`、自動処理は無出力 exit 0。(5) smoke 10 case 全 PASS / exit 0、`claude plugin validate --strict` PASS。

## v1.9.0

- **プロジェクトの書類は常に `docs/` を使うことに統一し、旧レイアウトからの移行手順を `/update` に追加した。** v1.8.0 は「`.claude/tasks/` がすでにある既存環境ではそちらを続ける」という例外を残していたため、置き場が 2 通りのまま固定され、`CLAUDE.md` の書類一覧（`docs/…`）と実際の置き場が食い違い続けていた。**新規プロジェクトは `docs/`（v1.8.0 で実装済み）／旧版由来の環境は `/hirai-lite:update` が `docs/` へ移す**、の 2 経路に整理した。全プロジェクト共通（`/init user`）で台帳・設計メモ・事故記録を作らない点は現状維持。
- **`/update` に手順 2「書類を docs/ へ移す（旧レイアウトのときだけ）」を新設した（手順は 5 → 6 段に繰り上げ）。** 移すのは `.claude/tasks/` `.claude/draft/` `.claude/rules-reference/` の**中身**で、`list.md` `parking-lot.md` `task-<id>-<slug>.md` `<slug>.md` `incidents.md` がすべて対象。**フォルダごとではなく 1 件ずつ `mv` する**（フォルダごとだと移動先が既にある場合に `docs/tasks/tasks/` の入れ子ができ、1 件ごとの重複判定もできない）。**移動先に同名のファイルがあれば移さず、両方残して報告する**（上書きは利用者が書いた中身を消すため）。移行後に空になった置き場だけ削除する（`.gitkeep` は中身と数えない）。`.claude/state/`（作業の控え）は書類ではないので移さない。手順 2-1 で移す前に中身を読ませ、手順 6 の報告で「どこからどこへ移したか」を平易な日本語で必ず伝えるようにした。
- **`/init` の手順 7 は、旧レイアウトが残っている間は台帳を作らない。** `docs/` 側に新しい台帳を作ると、パス解決が `docs/` を先に見るため**既存の台帳が黙って隠れる**（中身は残るが誰も読まなくなる）。`skip 旧レイアウト` と出して `/hirai-lite:update` へ回す。新規プロジェクトの挙動は v1.8.0 と同一。
- **`scripts/tasks-path.sh` の解決順（`$HARNESS_TASKS_FILE` → `docs/…` → `.claude/…`）は 1 バイトも変えていない。** 移行前の環境と、移行しない選択をした環境で台帳を見失わないため。変えたのは冒頭のコメント（なぜ `.claude/` 側を見続けるのかの説明）だけ。
- **`scripts/scope-check.sh` に台帳の二重存在検査を足した。** 移行で 1 件だけ同名衝突が残ると、`docs/` 側だけが読まれて `.claude/` 側は誰にも見られないまま更新され続ける。両方に `tasks/list.md` があれば「読まれるのは docs/ 側だけ」と警告する（第 3 引数でリポジトリ直下を渡す。省略時は第 1 引数の親）。どの場合も exit 0 のまま（検査で `/init` を止めない）。
- **rules 5 本・commands 7 本・`templates/CLAUDE.md`・README の文言を「常に `docs/`」に統一した。** 「`docs/` が無ければ `.claude/`」という条件分岐の記述を消し、`.claude/` 側は「旧レイアウト」「`/update` が移す」としてだけ残した。`rules/tasks.md` の `paths:` に `.claude/{tasks,draft}/**` を残しているのは、未移行の環境でルールが読まれなくならないようにするため。
- **移行の検査を `tests/smoke.sh` の既存 case に足した（case は 10 のまま増やしていない）。** case 1 に「`commands/update.md` の手順 2-2 の bash を**逐語に取り出して実行**し、(a) 移した中身が 1 バイトも変わらない (b) 同名衝突は上書きせず両方残す (c) 空になった置き場だけ消える (d) 2 回目も走る (e) 移行後に `hooks/session-start.sh` と `scripts/statusline.sh` が `docs/tasks/list.md` を読む」を追加。手順書そのものを実行するので、文書と実挙動が離れた時点で落ちる。case 4 には台帳の二重存在警告の検査を追加。**壊して確かめた**: 上書きガードを消すと case 1 が FAIL、`task-*.md` を移さないようにすると case 1 が FAIL、二重存在検査を消すと case 4 が FAIL。
- 予算は据え置き（T0 警告 6,000 / 上限 10,000、hook 5 / command 12 / skill 3 / smoke case 10）。**T0 実測 4,167 → 4,070 tokens**（条件分岐の記述を消した分 -97、警告線 6,000 の下）。**コマンドは 12 個ちょうど**（追加も削除もなし）、`plugin.json` に `hooks` / `commands` / `agents` キーは復活させていない。`commands/init.md` は 260 行（上限ちょうど）。hook 2 / command 12 / skill 1 / smoke 10 case は全 PASS / exit 0、`claude plugin validate --strict` も PASS。
- **実測。** `${TMPDIR}` に旧レイアウトのプロジェクト（`.claude/tasks/list.md` 3 タスク記入済 / `parking-lot.md` / `task-1-login.md` / `.claude/draft/rate-limit.md` / `.claude/draft/foo.md` / `.claude/rules-reference/incidents.md` 記入済、加えて `docs/draft/foo.md` を先に置いて同名衝突を作る）を用意し、`/update` の手順 2-1 / 2-2 を逐語実行した: (1) 5 件が `docs/` へ移り、`diff -r` で**衝突させた `foo.md` 以外に差分ゼロ**（記入内容は 1 文字も失われていない）。(2) `foo.md` は移さず**両方が原本のまま**残り、`移さなかった:` に出る。(3) 空になった `.claude/tasks/` `.claude/rules-reference/` は削除され、中身の残る `.claude/draft/` は残る。(4) 移行後の `session-start.sh` が `やること: 2 件 (docs/tasks/list.md)`、`statusline.sh` が `やること 2` を出す。(5) 2 回目の実行で全ファイルの shasum が完全一致（冪等）。(6) 台帳そのものを衝突させた場合は両方残り、`scope-check.sh` が「タスク一覧表が 2 か所にあります」を出す。(7) 新規プロジェクトへの `/init` は v1.8.0（HEAD）と**同じ 15 ファイル・同じパス構成**で、`docs/` が作られる（回帰なし）。(8) 旧レイアウトのまま `/init` の手順 7 を実行すると `skip 旧レイアウト` と出て `docs/` を作らない。

## v1.8.0

- **`grilling` skill を同梱した（`skills/grilling/SKILL.md`、新設の `skills/` フォルダ 1 件目）。** [mattpocock/skills](https://github.com/mattpocock/skills) の `skills/productivity/grilling/SKILL.md` を **1 バイトも変えずに**取り込んでいる。取得元は Claude Code 公式マーケットプレイスのプラグイン `mattpocock-skills` v1.2.3 が pin している commit `0ab1b63a410a03d3627979a109c8695de27af954`。取り込み時点の上流 `main` HEAD は `6654f6b60cd9d5be8b54c6fafe44346dabeb3b76` と別コミットだが、**この 1 ファイルの内容は両者で完全に同一**（sha256 `10ff989e…381296f2` / 1,987 bytes）であることを実測したうえで pin 側を採用した。MIT License と `Copyright (c) 2026 Matt Pocock` の全文・出典 URL・commit・sha256 を [`NOTICE.md`](NOTICE.md) に既存エントリと同じ体裁で追記している。`plugin.json` に `skills` キーは**書いていない**（既定の `skills/` が自動で読まれる。`commands` / `agents` と違い `skills` は「追加」挙動だが、書かないのが安全）。上流の 25 スキル全部が欲しい人向けに `claude plugins install mattpocock-skills` を README で案内した。
- **skill の予算枠を新設した（上限 3 個）。** `rules/_meta.md` に「数の予算」節を足し、hook 5 / command 12 / **skill 3** / smoke case 10 を 1 つの表にまとめた（これまで README と smoke にしか無く、ルール側に無かった）。`tests/smoke.sh` case 6 に `skills/*/SKILL.md` の件数検査を追加（**case は 10 のまま増やしていない**）。skill 本体は呼ばれた時だけ読まれるが `name` と `description` は常時ロードされるため、数で抑える方針を明記した。
- **`/init` の質問を 4 問 → 3 問にし、`docs/` を常に作るようにした。** 質問 2（配置先）を削除（置き場所 / `ultracode` / `mode` の 3 問）。プロジェクト scope では **`docs/` が無ければ作る**（`docs/tasks/` `docs/draft/` `docs/rules-reference/`）。`.claude/` へのフォールバックは**残している** — `user` scope では台帳を作らず、`.claude/tasks/` がすでにある既存環境ではそちらを続ける（`docs/` 側に作るとパス解決が `docs/` を先に見るため既存の台帳が黙って隠れる）。`scripts/tasks-path.sh` の解決順（`harness_tasks_file` 等）は 1 バイトも変えていない。省略条件表からも質問 2 の行を消した。
- **`/init` の mode 書き込みを `/config` と統一した（既知の不整合の修正）。** v1.7.0 までの手順 6 は `$D/mode.yml` 固定だったため、**ホーム側だけに `mode.yml` を持っている人のプロジェクトで `/init` を実行すると `.claude/mode.yml` が新設され、ホーム側を黙って覆い隠していた**（`/config` は `harness_mode_write_file` = すでに在る側に書く、を使っていた）。`/init` も同じ関数に寄せ、`user` 指定のときだけホーム側を直に指す。省略条件（質問 3 を省くか）も「プロジェクト側かホーム側のどちらかに `mode.yml` がある」に揃えた。実測: ホーム側だけに `mode: loop` がある状態でプロジェクト scope の手順 6 を逐語実行し、**書き込み先が `~/.claude/mode.yml`（`kept`）になり、`.claude/mode.yml` が作られず、ホーム側の `loop` も書き換わらない**ことを確認（同条件で v1.7.0 の `$D` 基準を再現すると `.claude/mode.yml (normal)` が新設される）。`user` scope では逆に、プロジェクト側に `mode.yml` があってもホーム側へ置き、プロジェクト側は 1 バイトも触らない。
- **`/init` に第 2 段階（案件ヒアリング → ドキュメント生成）を足した。コマンドは 12 個のまま**（新設していない）。1 回目はセットアップ、**セッションを開き直して 2 回目を実行すると案件を伺う**。判定条件は 3 つとも真であること: (1) 配置先（`.claude/` か `~/.claude/`）に `rules` / `settings.json` / `mode.yml` / `statusline.sh` の 4 つが揃っている (2) 対応する `CLAUDE.md` がある (3) その `CLAUDE.md` に `<...>` プレースホルダが 1 行以上残っている。**埋め終われば第 2 段階には入らない**（実測で両方向を確認）。ヒアリングは**自前で質問を作らず同梱の `grilling` skill を呼ぶ**（`Skill` ツール）。質問は列挙せず観点だけ渡す（ゴール / 背景 / スコープ / 関係者と体制 / ドメイン用語 / 要件 / 技術構成 / データ / 関連リポジトリ / 進捗 / コマンド）。`grilling` が使えないときは `AskUserQuestion` で最低限 3 問を聞く手順も残してある。
- **ヒアリング結果は `CLAUDE.md` のプレースホルダと `docs/` に落とす。空のファイルを量産しない。** 得られた分だけ `docs/overview.md`（ゴール / 背景 / スコープ / 体制 / ドメイン用語 / 関連リポジトリ）/ `docs/requirements.md` / `docs/architecture.md`（構成 / データの持ち方 / 技術判断の理由）を作り、やることは既存の `docs/tasks/list.md` に行を足す。**進捗表は新しく作らない** — 台帳の `status` 列がその役目。得られていない章のためにプレースホルダだけのファイルは置かない（「既定は入れない」原則）。これは前身ハーネス `hirai-method` の CLAUDE.md にあった 5 節（User Context / Architecture / Data / Implementation Status / Related Repositories / Domain Knowledge）を、**`CLAUDE.md` を厚くせずに** `docs/` 側へ逃がす形で吸収したもの。
- **`templates/CLAUDE.md` に Documents index を追加した。** 「どこに何があるか」の地図で、各行に「旧ハーネスのどの観点をカバーするか」が分かる説明を入れている。**注記を 1 行入れた**: `.claude/rules/` のルールはこの表に書かなくても自動で読み込まれる（frontmatter 無し = 常時 / `paths:` 付き = 該当ファイルを触った時）、この表は所在を把握するためのもの — 事実誤認を防ぐため。実在しない行は `/init` の 2 回目が消す。**節の追加は Documents index だけ**で、User Context 等の節は新設していない（T0 を厚くしないため）。既存の Rules index は維持（**予算の数値は v1.3.0 の時点ですでに「警告 6,000 / 上限 10,000」に直っており、古い「3,000 tokens 上限」の記述は残っていなかった**ため変更なし）。
- 予算は据え置き（T0 警告 6,000 / 上限 10,000、hook 5 / command 12 / smoke case 10）。**skill 3 だけ新設。T0 実測 3,668 → 4,167 tokens**（+499、警告線 6,000 の下）。内訳は `templates/CLAUDE.md` の Documents index と `rules/_meta.md` の「数の予算」節。**コマンドは 12 個ちょうど**（追加も削除もなし）、`plugin.json` に `hooks` / `commands` / `agents` キーは復活させていない。`commands/init.md` は 199 → **260 行**（第 2 段階の追加に伴い上限を 260 行としたので、ちょうど上限）。hook 2 / command 12 / skill 1 / smoke 10 case は全 PASS / exit 0、`claude plugin validate --strict` はプラグイン側・マーケットプレイス側とも PASS。
- **実測。** `${TMPDIR}` の `docs/` を持たない空プロジェクトで `commands/init.md` の手順 0/2〜8 を逐語実行した: (1) 手順 0 が `第 1 段階 (セットアップ) へ` と出し、**`docs/` `docs/tasks/` `docs/draft/` `docs/rules-reference/` が作られ**、15 ファイルが置かれる（v1.7.0 と同数。台帳の置き場が `docs` になった点だけが違う）。(2) 2 回目は `placed` 0 件で **15 ファイルの shasum が完全一致**（冪等）。`MODE=normal` を渡しても既存の `mode: loop` は書き換わらず、`.bak` の残骸も無い。(3) 2 回目の手順 0 は `第 2 段階 (ヒアリング) へ: CLAUDE.md にプレースホルダ 13 行` と出る。プレースホルダを全部埋めると `第 1 段階` に戻る（もう伺わない）。(4) 台帳の置き場は 3 通り（新規 → `docs` / `.claude/tasks/` 既存 → `.claude` を維持し `docs/` を作らない / `docs/` 既存 → `docs`）とも期待どおりで、`harness_tasks_file` は既存環境で `.claude/tasks/list.md` を返し続ける。

## v1.7.0

- **`/init` のヒアリングに mode（進め方）を足した（3 問 → 4 問）。** v1.6.0 までは `AskUserQuestion` で 3 問（置き場所 / 配置先 / `ultracode`）を出し、**mode は聞かずに既定の `normal`（確認あり）で置いていた**。`AskUserQuestion` は 1 回に 4 問まで出せるので、4 問目として `mode（進め方）をどちらにしますか` を追加した（`normal（確認あり）(推奨)` / `loop（自動で進む）`）。選ばれた値は手順 6 で `templates/mode.yml` をコピーしたあと `mode:` の行だけ書き換えて `.claude/mode.yml`（`user` 指定なら `~/.claude/mode.yml`）に入る。**`mode.yml` がすでにある場合はこの質問を省く**（省略条件表に 1 行追加。既存の設定を上書きしないため）。完了報告の「後から `/hirai-lite:config` で変えられます」の案内はどちらを選んでも必ず残す。
- **`CLAUDE.md` を `/init` が配置するようにした。** `CLAUDE.md` は **T0（常時ロード）の柱の 1 本**で `tests/smoke.sh` case 4 の予算計算にも入っているのに、`/init` は置かず README が「手でコピーする」と案内していただけだった。**読み飛ばされると T0 が 1 本欠けたまま運用される**。手順 6 に配置を追加し、**無ければ黙って置き、あれば `kept` として 1 バイトも触らない**。質問は増やさない（手順 1 は 4 問が上限）。置き先はこのプロジェクトなら**リポジトリ直下の `CLAUDE.md`**、`user` 指定なら `~/.claude/CLAUDE.md`（`.claude/` の中ではない）。中身は `<...>` のプレースホルダのままなので、完了報告で「埋めてください」と 1 行伝える。
- **雛形をリポジトリ直下から `templates/CLAUDE.md` へ移した（`git mv`。中身は 1 バイトも変えていない）。** `claude plugin validate --strict .claude-plugin/plugin.json` が `root: CLAUDE.md at the plugin root is not loaded as project context.` の警告を出し、`--strict` は警告を失敗として扱うため exit していた。移動後は同じコマンドが `✔ Validation passed` になることを実測（マーケットプレイス側 `claude plugin validate --strict .` も PASS のまま）。`tests/smoke.sh` case 4 の計測対象も `$ROOT/CLAUDE.md` → `$ROOT/templates/CLAUDE.md` に付け替え、**移動前後で T0 実測が 3,668 tokens（3 file / 11,005 bytes）のまま変わらない**ことを確認した。`templates/CLAUDE.md` を隠すと case 4 が FAIL することも実測しており、計測対象を見失っていない。
- **手順の中身は変えていない。** 配置物の解決順（`$CLAUDE_PLUGIN_ROOT` → キャッシュ最新版 → marketplaces）と冪等性、`docs/` の有無による台帳の置き場は v1.6.0 と同じ。`${TMPDIR}` の空プロジェクトで `commands/init.md` の手順 0/2〜8 を逐語実行した実測: (1) 新規プロジェクトで **15 ファイル**が置かれる（v1.6.0 の 14 + `CLAUDE.md`）、`mode.yml` は選んだ `loop` になり画面下部も `mode: loop（自動で進む）` と一致、`.bak` の残骸なし。(2) 2 回目の実行は `placed` 0 件で **15 ファイルの shasum が完全一致**（冪等）。このとき `MODE=normal` を渡しても既存の `mode: loop` は書き換わらない。(3) 利用者が書いた `CLAUDE.md` があるプロジェクトでは `kept` になり shasum が 1 バイトも変わらない。(4) `user` 指定では `~/.claude/CLAUDE.md` に置かれ、プロジェクト側には 1 ファイルも作られない。
- **README を更新した。** ステップ 4 の「3 つだけ質問されます」を「4 つだけ」に、置かれるものの一覧に `CLAUDE.md` を追加。「詳しい導入手順」の 2 は `templates/CLAUDE.md` の配置先を明記し、3 は「このリポジトリの `CLAUDE.md` を雛形として手で置く」から「`/init` が置く。プレースホルダを埋める」に書き換えた。「mode（進め方）とは」に `/init` の 4 問目で選ぶことを、「全プロジェクトで使いたいとき」に `~/.claude/CLAUDE.md` へ置かれることを追記。リポジトリ構成表の `templates/` 行に `CLAUDE.md` と移動理由を足した。
- 予算は据え置き（T0 警告 6,000 / 上限 10,000、hook 5 / command 12 / smoke case 10）。**T0 実測 3,668 tokens で v1.6.0 から変化なし**（移動のみで雛形の中身を変えていないため）。**コマンドは 12 個ちょうど**（追加も削除もなし）、`plugin.json` に `hooks` / `commands` / `agents` キーは復活させていない。`commands/init.md` は 189 → 199 行（自らに課した上限 200 行以内）。hook 2 / command 12 / smoke 10 case は全 PASS / exit 0、`claude plugin validate --strict` も PASS。

## v1.6.0

- **ヒアリングを Claude Code 標準の選択 UI にした。** v1.5.0 までの `/hirai-lite:init` 手順 1 は、平文のメッセージで 3 問を投げて自由入力の返事を待っていた。これを **`AskUserQuestion` ツールを 1 回だけ呼び、3 問をまとめて提示する**形に変えた（`commands/init.md` 手順 1）。各問は `header` / `question` / `options`（`label` + `description`）を持ち、**既定にしたい選択肢を先頭に置いて `label` に `(推奨)` を付ける**。`description` には「選ぶと何が起きるか」を 1 行で書く。v1.4.0 で決めた**質問を省く条件はそのまま**で、省いた質問は `AskUserQuestion` に含めない。**全問が省かれるときは `AskUserQuestion` を呼ばない**（その 1 行だけ伝えて手順 2 へ進む）。ツールが使えないときの代替（平文で聞いて待つ、従来のやり方）も 1 行残している。
- **利用者に見せる表記を「正式名 + 解説」に統一した。** v1.5.0 までは正式名が消えていた（`normal` → 「確認あり」、`ultracode` → 「濃いめに考える設定」）ため、設定ファイルの中身と表示が結び付かなかった。`<正式名>（<短い解説>）` の形に揃える: `mode（進め方）` / `normal（確認あり）` / `loop（自動で進む）` / `ultracode（深く考えて自動で手分けする。利用量が増える）` / `statusLine（画面下部の情報表示）`。**解説は残す** — 正式名だけにすると非エンジニアが読めなくなるため。適用先は `commands/init.md` `commands/config.md` `commands/update.md` `commands/state.md` `hooks/session-start.sh` `scripts/statusline.sh` `scripts/tasks-path.sh` `templates/mode.yml` `rules/core.md` `CLAUDE.md` `README.md` `docs/rules-reference/context-and-output.md`（`git grep` で全件洗った）。CHANGELOG の過去の版の記述は履歴なので変更していない。
- **画面下部は 2 行構成と色分けを維持したまま、1 行目の `mode` だけ表記を変えた。** 実測した表示幅（全角 2 桁換算）は `mode: normal（確認あり）` で **99 桁**、`loop（自動で進む）` でも **99 桁**、未知の値（`experimental`）で 93 桁。2 行目の設定リンクは 37 桁。v1.5.0 は 89 桁（`normal`）/ 85 桁（`loop`）だったので 10〜14 桁伸びた。**解説を `確認` `自動` まで縮めても 95 桁 / 93 桁にしかならず、収まる端末の幅（80 桁には入らない／100 桁・120 桁には入る）は変わらない**ため、1 行目の他の要素を削らず、解説も縮めずそのままにした。色分け（v1.5.0）はロジックごと未変更。
- smoke は 10 件のまま（上限）。**case 1 の進め方一致検査の期待値**を `確認あり` / `自動` から `normal（確認あり）` / `loop（自動で進む）` へ更新した（置き場 5 通りとも）。`statusline.sh` の表示を `確認あり` に戻すと `FAIL case 1 ... 期待=normal（確認あり） 冒頭=normal（確認あり） 画面下部=確認あり` になることを実測で確認している。`hooks/session-start.sh` は `進め方: <値> — <説明>` の `—` の前に半角空白を残し、smoke の切り出し（`sed -n '1s/.*進め方: \([^ ]*\).*/\1/p'`）が壊れないようにした。
- **手順の中身は変えていない。** 何を配置するか・冪等性・`docs/` 解決順は v1.5.0 と同じ。`${TMPDIR}` の空プロジェクトで `commands/init.md` の手順 0/2〜8 を逐語実行し、v1.5.0（タグ `v1.5.0` の worktree）の結果と突き合わせた。**配置される 14 ファイルの一覧は完全一致**、内容の差分は表記を直した 4 ファイル（`mode.yml` / `rules/core.md` / `statusline.sh` / `tasks-path.sh`）のコメント・文言のみで、残る 10 ファイルは shasum まで一致した（回帰なし）。2 回目・3 回目の実行では `placed` が 0 件、14 ファイルの shasum も 1 バイト変わらない（冪等）。
- 予算は据え置き（T0 警告 6,000 / 上限 10,000、hook 5 / command 12 / smoke case 10）。**T0 実測 3,663 → 3,668 tokens**（警告線 6,000 の下）。増分 5 tokens は `rules/core.md` の該当条を `**進め方が「自動」のとき (Loop)**` から `**`loop`（自動で進む）のとき**` に書き替えた分。`commands/init.md` は 198 → 188 行（上限 200）、`commands/config.md` は 81 → 79 行（上限 80）。hook 2 / command 12 / smoke 10 case は全 PASS / exit 0、`claude plugin validate` も PASS。

## v1.5.0

- **⚠️ 破壊的変更: `/hirai-lite:mode` を廃止した。** 進め方の切替は `/hirai-lite:config` の「1. 進め方」に移した。**`/hirai-lite:mode normal` / `/hirai-lite:mode loop` は動かなくなる**（`commands/mode.md` を削除）。機能は 1 つも失っていない — 引数での直接指定（`/hirai-lite:config 進め方 自動`、`normal` / `loop` も可）・書き込み先を「すでに在る側」にする挙動・「自動」の間の振る舞いの説明・全プロジェクト共通に書いたときの 1 行追記まで、すべて `commands/config.md` が引き継いでいる。コマンド数は 12 個ちょうどのまま（上限）で、`config` の新設と `mode` の削除は同数の入れ替え。
- **`/hirai-lite:config` を新設。** 引数なしで設定を 6 項目一覧する（進め方 / 濃いめに考える設定 / 常時読まれる量 / 置き場所 / 画面下部の表示 / 更新の確認）。値の読み取りは既存の共通ライブラリ（`scripts/tasks-path.sh` の `harness_mode` / `harness_mode_write_file` / `harness_rules_dir` / `harness_tasks_file`、`scripts/update-check.sh` の `harness_update_cache_dir`）を通し、解決順を書き起こしていない。**変更するときは書き込み先のパスを見せてから実行する。** 濃いめに考える設定は利用量（費用）が増える旨を一覧にもそのまま書いている。
- **画面下部の表示を 2 行にした。** 1 行目が**いまの状態**（モデル / 残り容量 / 進め方 / ブランチ / やること）、2 行目が**次にできる操作**。2 行目の先頭に `設定を確認・変更 → /hirai-lite:config` を**常時**置き、お知らせ（更新あり / `/state save` の促し）はその後ろに 1 件だけ出す。お知らせを止めても（`HC_STATUSLINE_NOTICE=off`）設定リンクは残る。
- **色分けを追加した。** モデル名 / ブランチ / やること はグレー、`ctx` `5h` `7d` は緑 → 黄 → 赤（閾値は従来どおり 50% / 80%、ロジック未変更）、`mode` の値は進め方ごとに別の色、設定リンクは控えめなシアン、お知らせは黄。**色は補助でしかない** — 数値には `%`、進め方には「確認あり / 自動」、リンクにはコマンド名を文字として必ず出しており、色を落としても情報は 1 つも失われない（色覚特性や配色設定で色が伝わらない環境を想定）。`NO_COLOR` が設定されていれば色を一切出さない（従来どおり）。
- **fail-open と「通信しない」は維持。** 空 stdin / 壊れた JSON / お知らせの控えが不在・空・壊れ、いずれでも **2 行 + exit 0** を返す。到達不能な URL と 5 秒 sleep する curl スタブを噛ませても実測 0.02 秒台で、`statusline.sh` からは一切通信しない。
- smoke は 10 件のまま（上限）。**既存 case を拡張**した。**case 1** は「常に 1 行」の検査を「**常に 2 行 + 2 行目が設定リンクで始まる**」へ差し替え、あわせて色あり／`NO_COLOR` の両方で行数と語が変わらないこと（`NO_COLOR` では制御文字が 1 つも出ないこと）を追加。**case 8** はお知らせの検査を 2 行目基準に変え、`HC_STATUSLINE_NOTICE=off` や該当なしのときに**設定リンクだけが残る**ことを検査対象に加えた。どちらも「1 行に戻す」「設定リンクを消す」の 2 通りに壊して FAIL することを実測で確認した。
- 予算は据え置き（T0 警告 6,000 / 上限 10,000、hook 5 / command 12 / smoke case 10）。**T0 実測 3,652 → 3,663 tokens**（警告線 6,000 の下）。`rules/` は 1 バイトも変えていない。増分 11 tokens は `CLAUDE.md` の「進め方」節に切替コマンド名（`/hirai-lite:config`）を書き足した分。`rules/core.md` に `/mode` の言及は元から無く、T0 のルール本体には手を入れていない。hook 2 / command 12 / smoke 10 case は全 PASS / exit 0、`claude plugin validate` も PASS。

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
