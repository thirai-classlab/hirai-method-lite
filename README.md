# hirai-method-lite

Claude Code に「AI が守る決まりごと（ルール）」をひとそろい配る、小さな追加パーツです。あわせて、mode（進め方）の設定・やること（ファイルの一覧表 list.md が既定。GitHub の issue と Project で回すリポは、足すプラグイン hirai-project-method を入れて選ぶ）・取り返しのつかない操作の前の確認・statusLine（画面下部の情報表示）が手に入ります。

いちばんの特徴は、**決まりごとが増えすぎないように上限を決めて管理する**こと。ルールを足すときは必ず決まった手順を通すので、AI が毎回読む文章が際限なく膨らんで肝心なことが埋もれる、という状態を防げます。

## 使いはじめる

所要 5 分ほど。上から順に、書いてあるとおり操作すれば終わります。

⚠️ **表示は Claude Code のバージョンや環境によって変わることがあります。** ここに書いたのは Claude Code 2.1.247 で実際に確かめた内容です。見覚えのない画面が出たときは、文面を読んでから判断してください。確かめきれなかった点は[この節の最後](#確認できなかったこと)にまとめました。

**前提: Claude Code 2.1.89 以上**です（`PermissionDenied` hook は 2.1.89 で追加されました。それより古いと `hooks/hooks.json` 全体が読まれず、hook が 1 本も動きません。会話には何も出ません）。足りないときは先に `claude update` を打ちます。出典: [Claude Code の CHANGELOG](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)。

### 1. プラグインを追加する

Claude Code で次の 2 行を順に実行します。

```
/plugin marketplace add thirai-classlab/hirai-method-lite
/plugin install hirai-lite@hirai-lite
```

- **1 行目は配布元の一覧を登録するだけ**です。この時点では何もインストールされません。
- **2 行目で実際に入ります。** 詳細画面が開き、次のステップの選択を求められます。

> **ターミナルから 1 行で入れることもできます**（使いたいプロジェクトのフォルダで実行。配布元の登録と導入を 1 回で行い、範囲は Local）。
>
> ```
> claude plugin install hirai-lite --marketplace thirai-classlab/hirai-method-lite --scope local
> ```
>
> Claude Code 2.1.312 の `claude plugin install --help` で `--marketplace`（まだ登録していない配布元は先にユーザー設定へ登録する）と `--scope` があることを確かめました。このあとは手順 4 の `/hirai-lite:init` へ進みます。

ターミナルから同じ操作（`claude plugin marketplace add …`）を試したときは確認は出ず、`✔ Successfully added marketplace: hirai-lite` とだけ表示されました。**画面の中から `/plugin` で実行した場合に確認が出るかは未確認です。** 出た場合は、追加先が `thirai-classlab/hirai-method-lite` になっていることを確かめてから進めてください。

なお公式ドキュメントには「プラグインとマーケットプレイスは、あなたの権限で任意のプログラムを実行できる。信頼できる配布元のものだけを入れること」という注意書きがあります（[Security](https://code.claude.com/docs/en/discover-plugins.md#security)）。

### 2. 「どこに入れますか」と聞かれます → **Local** を選びます

2 行目を実行すると、**入れる範囲**を 3 つから選ぶよう求められます。ここは必ず答える必要があります。

| 選択肢 | 効く範囲 | 記録される場所 | ほかの人にも配られるか |
|---|---|---|---|
| **Local**（おすすめ） | いま開いているプロジェクトで、自分だけ | そのフォルダの `.claude/settings.local.json` | 配られない（git に入らない） |
| **User** | このパソコンで開くすべてのプロジェクト、自分だけ | ホームの `~/.claude/settings.json` | 配られない |
| **Project** | いま開いているプロジェクトを触る人全員 | そのフォルダの `.claude/settings.json` | **配られる**（このファイルを commit すると全員に効く。ただし commit は有効にするだけで入れません。入れる操作は人ごとに要ります → 下の「1.x・2.x から 3.0.0 へ移る」） |

**Local をおすすめする理由**は 3 つです。

- **自分の作業だけに効く。** 合わない・重いと感じたら、自分の側だけで止められます。
- **チームの共有設定を書き換えない。** Project は `.claude/settings.json` に書き込みます。これは commit してチーム全員に配るためのファイルなので、まず自分で試す段階では触らないのが安全です。
- **後から変えられる。** 一度消して入れ直すだけです（→ [後から変えたいとき](#後から変えたいとき)）。

> **全プロジェクトで使いたい場合は User を選びます。**（決まりごと（ルール）を**どこに置くか**はこれとは別の話です → [全プロジェクトで使いたいとき](#全プロジェクトで使いたいとき)）

（ターミナルから `claude plugin install …` を実行した場合、この選択画面は出ずに **User** に入ります。範囲を指定したいときは `--scope local` のように付けます。）

### 3. 導入される内容が一覧で表示されます

同じ詳細画面に、このプラグインが持ち込むものが出ます。入れる前に中身を確かめられます。

| 表示 | 中身 |
|---|---|
| コマンド 12 個 + スキル 2 個（画面では合わせて **Skills**） | `/hirai-lite:init` `/hirai-lite:commit` `/hirai-lite:start-task` など、こちらから呼び出して使う操作 12 個と、AI が必要なときに自分で読む手引き 2 個（`grilling` / `context-engineering`）。GitHub Project 用の `/hirai-project-method:board`・`:project-setup` と skill `github-project` は足すプラグインにある |
| エージェント 1 個（**Agents**） | テストを先に書く進め方の担当（`tdd-guide`）。v2.7.0 でレビューの agent 2 個は外した（正しさは組み込みの `/code-review`。脆弱性は観点を指示した reviewer と、利用者が打つ `/security-review`。詳しくは「同梱しているエージェント」） |
| 自動処理 5 本 | セッション開始時の表示（版と効いている設定を含む）、容量が増えたときの警告、`loop`（自動で進む）のときの進め方の再掲、`worktree: block` のときだけ働く編集前の確認（`worktree-guard.sh`。既定の `off` では何もしない）、`notify: orca` のときだけ働く「権限の確認で止まっています」の知らせ（`notify-attention.sh`。判断は変えない） |
| 外部ツール接続 2 個（**MCP servers**） | コードを検索する `serena` と、ライブラリの公式ドキュメントを取ってくる `context7` |

あわせて、毎回のセッションで常にかかる容量の見積もりも出ます（v1.8.0 をターミナルの `claude plugin details` で見ると `Always-on: ~520 tok` と表示されました。v1.7.0 は約 452 tokens で、増えた分は `grilling` の名前と説明が常時載るぶんです）。

> **`Skills` の件数はコマンドとスキルの合計です。** 3.0.0 はコマンド 12 個 + スキル 2 個の 14 件になるはずです（3.0.0 の実機での表示は未確認。v2.7.0 は `Skills (17)` = コマンド 14 + スキル 3 でした）。`Agents (1)`、`MCP servers (2)` と並びます（2026-11-15、偽の HOME に手元の写しを入れて Claude Code 2.1.312 で確認。`Always-on: ~637 tok` と出ました。2.6.0 は `Skills (14)`・`Agents (3)`・約 609 tokens。この見積もりは `disable-model-invocation: true` の 5 本の説明文も数えていますが、[公式](https://code.claude.com/docs/en/skills) ではその説明文は会話に載りません）。
>
> **`Hooks` の件数はスクリプトの本数ではなく、きっかけ（イベント）の種類数です。** v1.11.0 の `claude plugin details hirai-lite` は `Hooks (2)  SessionStart, UserPromptSubmit` と出ますが、スクリプトは 3 本あります（`UserPromptSubmit` に 2 本ぶら下がっているため）。偽 HOME への実インストールで確かめた挙動で、3 本目を足しても表示は `(2)` のままです（別イベントを足したコピーでは `(3)` に増えました）。本数を数えるなら `ls <プラグイン>/hooks/*.sh`、または `tests/smoke.sh` case 6 の `hook=3/5` を見てください。

- **自動処理（hooks）だけを対象にした承認画面は出ません。** 入れた時点で動きます。中身は `hooks/session-start.sh` と `hooks/context-budget.sh` と `hooks/loop-reminder.sh` と `hooks/worktree-guard.sh` と `hooks/notify-attention.sh` の 5 本だけで、どれも短いシェルスクリプトです。**`worktree-guard.sh` 以外は操作を止めません**（文章を足すか、コーディネーターへ知らせるだけで、承認・拒否の判断は変えません）。`worktree-guard.sh` は `.claude/mode.yml` に `worktree: block` を置いたリポでだけ、Orca の worktree でない会話からの Edit・Write・NotebookEdit と `git commit` を止めます（MCP の書き込みの道具は止めません。既定は `off` で何もしません。→ [Orca で並行に進める](#orca-で並行に進める選べる機能)）。`loop-reminder.sh` は進め方が `loop` のときだけ動き、`normal`（確認あり）では 1 バイトも出しません。
- **外部ツール接続（MCP）の 2 つも、承認なしで自動的につながります。** `claude mcp list` で確かめると `plugin:hirai-lite:serena: uvx … - ✔ Connected` のように、名前の頭に `plugin:hirai-lite:` が付いて出ます。`serena` は `uvx`（[uv](https://docs.astral.sh/uv/)）、`context7` は `npx`（Node.js）が必要です。無い場合は該当のものが「つながらない」と出るだけで、ほかの機能はそのまま動きます。

選び終わると `Plugin is now active.`（もう使えます）か `Run /reload-plugins to activate.`（`/reload-plugins` と入力すると使えます）のどちらかが出ます。後者なら、そのまま `/reload-plugins` を実行してください。

### 4. 使いたいプロジェクトで `/hirai-lite:init` と入力します

ここで初めて、決まりごと（ルール）と設定がそのプロジェクトに置かれます。

**置く前に 3 つだけ質問されます**（ユーザー設定にすでに画面下部の表示がある人には、それを替えるかの 1 問が足されて 4 つ。v2.7.0 から。v1.4.0 から。v1.6.0 から Claude Code 標準の選択 UI で出ます。v1.8.0 で「ファイルの置き場所」を聞くのをやめて 3 つになりました）。どこに入れるか / [`ultracode`（深く考えて自動で手分けする。利用量が増える）](#ultracode-について)を有効にするか / [mode（進め方）](#mode進め方とは)を `normal`（確認あり）と `loop`（自動で進む）のどちらにするか の 3 つで、それぞれ既定の選択肢に `(推奨)` が付いているので、そのまま選べば進みます。すでに入っている設定は上書きしないので、該当する質問は省かれます（`mode.yml` がすでにあれば mode は聞かれません）。すでに一式が入っているプロジェクトで実行したときは質問されず、「すべてそのまま」と報告されます。

置かれるのは次のものです。

- `.claude/rules/` — 決まりごと本体
- `.claude/settings.json` — 安全設定と画面下部の表示
- `.claude/mode.yml` — mode（進め方）（→ [mode（進め方）とは](#mode進め方とは)）。**すでにホーム側（`~/.claude/mode.yml`）に持っている人には、プロジェクト側に新しく作りません**（そちらを黙って覆い隠さないため）
- `CLAUDE.md` — このプロジェクトの説明（概要 / 使っている技術 / よく使うコマンド）の下書き。中身は**次の `/hirai-lite:init` で伺って埋めます**。すでにある場合は触りません
- `docs/` — 書類の置き場。**無ければ作ります**（`docs/draft/` 設計メモ / `docs/rules-reference/` 困ったことの記録帳と承認の型）。**プロジェクトの書類は常にここです。** 旧版（v1.8.0 以前）で `.claude/tasks/` などに作った環境は、`/hirai-lite:update` が `docs/` へ移します（中身はそのまま移動します）

**このとき、ファイルを作るためのシェルコマンド（`cp` `mkdir` `python3` など）を実行してよいか、そのつど聞かれます。**

| 選択肢 | 意味 |
|---|---|
| はい | 今回だけ実行する |
| はい、今後は確認しない | 同じコマンドを次回から聞かずに実行する |
| いいえ | 実行しない |

許可しないとファイルが置かれません。`/init` は既存のファイルを 1 つも上書きしません。許可しなかった手順は飛ばされ、そのぶん置かれないままになります。最後に何を置いたかの報告が出るので、足りなければもう一度 `/hirai-lite:init` を実行してください。

> **ここで別の確認が出ることがあります。** 開いたプロジェクト自身が直下に `.mcp.json` を持っている場合、そのサーバーについて「つないでよいか」を別途聞かれます。これはプラグインとは無関係で、そのプロジェクトが持ち込む設定です。答えないままにすると `⏸ Pending approval` と表示され、**そのサーバーだけが使えません**（プラグイン側の 2 つや、決まりごと・コマンド・画面下部の表示には影響しません）。いまの状態を見るには `claude mcp list`、答え直すには `claude mcp reset-project-choices` です。

### 5. セッションを閉じて開き直し、もう一度 `/hirai-lite:init` と入力します

決まりごとはセッションを始めるときに読み込まれるため、`/hirai-lite:init` を実行したセッションにはまだ反映されていません。閉じて開き直すと有効になります。

**開き直したら、もう一度 `/hirai-lite:init` と入力してください。今度は案件のことを伺います。** 質問より先に、**AI がリポジトリを調べて「ここまでは調べました」と見せます**（README / `package.json` などの設定ファイル / フォルダ構成 / `git log` / 既存の `docs/`）。そのうえで同梱の `grilling`（[同梱している skill](#同梱している-skillスキル)）が、ゴール → 背景 → スコープ → 体制 → 技術構成 → やること の順に、**前提が決まった質問だけをまとめて出し、それぞれに推奨回答を添えて**聞いてきます。ファイルの中身や依存関係のような「調べれば分かること」は聞かれません（AI が自分で読みます）。**伺うのはこのリポジトリの開発について決めていただくことだけ**で、調達・法務・人事・営業といった、こちらから挙げていない領域には踏み込みません（v1.12.0）。**範囲外だと思ったら「その質問は不要」と答えてください。その枝はその場で取り下げられ、聞き直されません。** 伺った内容は `CLAUDE.md` と `docs/`（`overview.md` / `requirements.md` / `architecture.md`）に書き込まれます。やることは台帳（`docs/tasks/list.md`）に足します。`tasks: github-project` のリポ（足すプラグインを入れたリポ）だけ、GitHub の issue と Project に載せます（立ち上げの手順は足すプラグインの `project-setup.md`。`/new-task`・`/start-task`・`/finish-task` は `hirai-task` を呼んで Project の Status を動かします）。**伺えなかった章のファイルは作られません**（見出しだけの空ファイルを置かないため）。

これで準備完了です。2 回目の `/init` を済ませたあとは、`/init` は「すべてそのまま」と報告するだけになります。

### うまくいったか確かめる

画面下部に「mode: normal（確認あり）」（`loop` を選んだ場合は「mode: loop（自動で進む）」）と出ていれば OK です。

### 後から変えたいとき

| やりたいこと | 入力するもの |
|---|---|
| 入れる範囲を変える | いったん消してから入れ直す。ターミナルなら `claude plugin uninstall hirai-lite@hirai-lite --scope local` のあと `claude plugin install hirai-lite@hirai-lite --scope user` |
| プラグインを止める / 消す | `/plugin` →「Installed」タブ |
| 外部ツール接続（MCP）を個別に切る | `/mcp` |
| `.mcp.json` の承認をやり直す | `claude mcp reset-project-choices`（選択が消え、次回また聞かれます） |
| コマンドの実行許可を見直す | `/permissions` |

### 確認できなかったこと

- 画面の中から `/plugin marketplace add` / `/plugin install` を実行したときの表示そのもの（対話画面のため、ターミナルからの実行結果と公式ドキュメントの記述で代用しています）
- 「入れる範囲」を選ぶ画面での並び順と、はじめから選ばれている選択肢。3 つの選択肢があることと[それぞれの意味](https://code.claude.com/docs/en/discover-plugins.md#install-plugins)は公式ドキュメントに、記録される場所はターミナルから `--scope` を指定して実際に入れた結果で確かめています
- フォルダを信頼するか尋ねる画面が出る条件。このプラグインが配る安全設定は「禁止」と「確認」だけで、公式ドキュメントによればこの 2 つは信頼の確認を待たずに効きます

## やることの形と Orca の設定（`.claude/mode.yml`）

3.0.0 は、効かせる機能を `.claude/mode.yml` の 3 項目で選びます。**自動では見分けません**（会話の開始時の 1 行目に、版と今の値が出ます。例: `hirai-lite v3.0.0・tasks: ledger・worktree: off・notify: off`）。変えるときは `/hirai-lite:config`（項目 8）。

| 項目 | 値（既定が先頭） | 効くこと |
|---|---|---|
| `tasks` | `ledger` ／ `github-project` | `ledger`: やることを `docs/tasks/list.md`（台帳）で持つ。`/hirai-lite:new-task`・`start-task`・`finish-task`・`state` は尋ねて止まらず、GitHub に通信しません。`github-project`: 同じコマンドが足すプラグインの `hirai-task` を呼びます。`installed_plugins.json` から引いた足すプラグインの `hirai-task`（絶対 path）が無ければ `/plugin install hirai-project-method@hirai-lite` を 1 行で示して止まります |
| `worktree` | `off` ／ `warn` ／ `block` | Orca の worktree でない会話の扱い。`warn` は開始時に警告を 1 行出すだけ。`block` は Edit・Write・NotebookEdit と `git commit` を止める（MCP の書き込みの道具は止めません。下の節） |
| `notify` | `off` ／ `orca` | Orca のコーディネーターへの知らせ（下の節） |

### 足すプラグイン hirai-project-method を入れる

GitHub Project でやることを回すリポだけが入れます。

```
/plugin install hirai-project-method@hirai-lite
```

- 依存で、土台の hirai-lite 3.0.0 以上も一緒に入ります（土台が入っていないリポでは、足すプラグインだけを入れても土台が入ります）。**1.x が入っている範囲では、先に `/plugin marketplace update hirai-lite` → 端末で `claude plugin update hirai-lite@hirai-lite --scope <入れた範囲>`（画面なら `/plugin` → Installed → Update now） で土台を 3.0.0 に上げてから足すプラグインを入れます**（1.16.0 のまま入れると、依存の版で断られます）。**2.x（`hirai-lite-v2`）が入っている範囲では、足すプラグインだけを先に入れません**（3.0.0 は入りますが、開始時の表示とコマンドは 2.9.0 のもので、`/hirai-lite:board` と `/hirai-project-method:board` が両方並びます）。下の「1.x・2.x から 3.0.0 へ移る」の表の順（disable まで）を先に行います。土台だけを切ることはできません。先に足すプラグインを切ります（使い捨ての HOME で `claude plugin disable hirai-lite@hirai-lite` が「still required by hirai-project-method」で断られることを確かめた）
- 中身: `hirai-task`（`bin/`）・`/hirai-project-method:board`・`/hirai-project-method:project-setup`・skill `github-project`
- `mode.yml` に `tasks: github-project` を書いたあとで使えます

### Orca で並行に進める（選べる機能）

[Orca](https://github.com/stablyai/orca) の worktree で複数の会話を並行に動かすリポ向けです。どちらも既定は `off` で、入れただけでは何も変わりません。

- `worktree: block`: Orca の worktree でない会話からの、**リポの中の git に入るファイル**への Edit・Write・NotebookEdit と、`git commit` を止め、worktree の作り方を 1 行で示します。Orca の会話とみなすのは、`ORCA_WORKTREE_ID` の path の `git rev-parse --git-common-dir` が対象のリポと同じで、対象の toplevel が id の path そのものか `/.claude/worktrees/` の下にあるときです（Orca の worktree の中に `isolation: 'worktree'` の subagent が作る入れ子の worktree も通ります）。macOS で大文字小文字だけが違う path は同じ場所として扱います（`-ef`）。**serena などの MCP の書き込みの道具と、Bash でのファイルの書き換えは止めません。** **読み取り・リポの外（`~/.claude` の記憶の置き場など）・git に入らない場所（`.tmp/` など）への書き込み・`git switch`・`git checkout` は止めません。** 並行の会話が同じ作業ツリーを触る事故を編集の時点で止めるための、`rules/_meta.md` 条 5 の唯一の例外です。`block` を外せば例外も消えます
- `notify: orca`: 担当の会話が終わったとき・止まったとき・ユーザーに決めてもらうことができたときに、`hirai-notify` でコーディネーターへ知らせます。Orca が立ち上げた担当は `worker_done`・`question`（Dispatch の id は、Orca が担当の最初に差し込む前置きの文から `--dispatch-id` で渡す）、立ち上げられていない会話は依頼文で渡された宛先へ `status`・`question`（`bin/hirai-notify`）。宛先の決め方は上が先で、`--dispatch-id` ＞ `--to` ＞ 環境変数 `HIRAI_DISPATCH_ID` ＞ `HIRAI_COORDINATOR` ＞ 導入先の `.claude/state/coordinator`（1 行 `run:<id>`。担当が依頼文で宛先を渡されたら最初に書く。**更新から 24 時間を過ぎたら使わず、担当が終わるとき（`done`）に消えます**）＞ どれも無く `ORCA_TERMINAL_HANDLE` があれば宛先を省いて送ります。**担当は、終わる前に報告の頭へ worktree の残りの作業（なし／あり: 内容）を書きます**（`scripts/orca-context.sh` が開始時に出す知らせ方の 1 行）。`hirai-notify done` は、今いる worktree の残りを自分で数えて本文に足します（未コミット 0・未 push 0 なら「worktree の残り: なし」、そうでなければ「worktree の残り: 未コミット N 件・未 push M 件」。upstream が無ければ「upstream なし」。git でない場所では足しません）
- `notify: orca` のときは、担当の会話が**権限の確認の画面で止まったとき**（Notification の `permission_prompt`。約 6 秒待っても答えが無いとき）と、auto mode の分類器が操作を止めたとき（`PermissionDenied`）にも、`hooks/notify-attention.sh` が `hirai-notify waiting <要約>`（`--type escalation`。件名は「権限の確認で止まっています」「分類器が止めました」、本文は `<リポの root>｜<message か tool_name と reason の要約>`）を送ります。ユーザーが画面を見に行くまで止まりに気付けない事故（2026-11-23 に 2 回）への手当てです。**判断は変えません**（何も出力せず exit 0）。送れなくても会話は止めず、stderr に 1 行だけ出します。同じ会話から 1 分に 2 通以上は送りません。秘密を含みうる `tool_input` の中身は送りません。送るのは道具の名前（`tool_name`）と Bash の**先頭のコマンド名だけ**で、`VAR=値 cmd` は `VAR=…` に伏せ、`VAR=…`・`(VAR=…)`・`$(…)`・括弧で始まる形では代入とコマンド置換の中身を読まず、コマンド名が決められなければ道具の名前だけです。`reason` は 80 字までで、値らしい並びは伏せます
- `notify: orca` のときは、担当の会話が **API エラーで手番を終えたとき**（`StopFailure`。`error` は `rate_limit`・`authentication_failed`・`server_error`・`unknown` など）にも、`hooks/notify-attention.sh` が `hirai-notify waiting`（`--type escalation`。件名は「API エラーで止まりました（<error>）」、本文は `<リポの root>｜<last_assistant_message の先頭 80 字>`）を送ります。判断は変えず、1 分に 2 通以上は送りません。「Request timed out」で必ず `StopFailure` が起きるかは公式の文書に無いので、取りこぼしは次の `hirai-watch` が拾います
- **コーディネーターの見回り（`hirai-watch`）**: PC のスリープや API の時間切れで担当の会話が応答の途中で止まると、知らせる側も止まっていることがあります。コーディネーターは `hirai-watch [--minutes N] [--wait-hours N] [--orca] [<worktree の path> ...]`（`bin/`）で、各 worktree の会話の記録（`~/.claude/projects/<cwd の / と . を - に置き換えた名前>/*.jsonl` の最新 1 本）を読み、止まりと待ちを 1 行ずつ出します。止まりは 2 つ: (a) 最後の会話の行が API エラーの assistant（`isApiErrorMessage: true`）かその直後の `turn_duration`、(b) 最後の行が `api-request` のまま、または最後の会話の行が user（tool_result を含む）のままで、記録の更新が N 分（既定 15）より前。待ちは 1 つ: 最後の会話の行が `stop_reason: end_turn` の assistant（または直後の `turn_duration`）で、記録の更新が `--wait-hours N`（既定 4）より前で、最後の手番に「`orca orchestration send` の `--type question`」「`hirai-notify question`・`waiting`」の Bash の呼び出しがあるか、最後の assistant の本文に「承認」があるとき、「`<path>: 待ち（N 時間）`」を出します（本文は出しません）。人の返事を待っている会話なので、止まりには数えません。止まりが 1 件でもあれば exit 1、待ちだけなら exit 3、どちらも無ければ何も出さず exit 0。`--orca` は `orca worktree list --json` から、今のリポ（`git remote get-url origin`）と同じ `projectId` の worktree を全部見ます（`orca` が無ければ exit 2 と理由）。記録の dir が無い worktree は「記録が無い」と出すだけで止まりに数えません。回し方の例: Monitor や定期の起き上がりで 10 分ごとに `hirai-watch --orca --minutes 15` を回し、exit 1 のときだけ出力を見て、止まった担当の端末に「続けて」を送る（`orca terminal send`）。**待ち（exit 3）には「続けて」を送りません。問いの中身（`orca orchestration check`・承認の文）を見て、答えるか、人に回します。** 出すのは API エラーの文の先頭 80 字だけで、本文は出しません
- **worktree の片付け（`hirai-worktrees list [--orca] [--json]`）**: 今のリポの worktree を 1 行ずつ、`消してよい` か `残す` かを理由つきで出します。**消す操作は持ちません**（`git worktree remove` を呼びません。消すのは人です）。`消してよい` は次の 8 つが**全部**そろった worktree だけで、1 つでも欠ける・読めないときは理由つきで `残す` です。(1) 作業がない（`git status --porcelain` が空。`GIT_OPTIONAL_LOCKS=0` で打ち、ほかの会話の index を触りません）。(2) 動いているプロセスが無い（その worktree か下を cwd に持つプロセスが 0。`lsof` を 1 回だけ打って全 worktree に使い、無ければ `/proc/*/cwd`。どちらも読めなければ「プロセス 未確認」。この道具自身とその親は数えません）。(3) 動いている端末が無い（`orca terminal list --json`。`worktreePath` が空なら `worktreeId` の `::` の後ろを使い、どちらも無い端末・`truncated: true` があれば「端末 未確認」。**入れ子の worktree は、祖先の worktree に端末かプロセスがあれば `残す（外側の worktree が使用中）`**）。(4) locked・prunable・bare・本体の checkout・今いる worktree ではない。(5) その path の下にほかの worktree が無い（`git worktree list` の全行で見る。locked・detached・prunable の入れ子も数え、あれば `残す（入れ子の worktree がある: …）`）。(6) branch がある（detached は `残す`）。(7) 取り込み済み（先頭が既定の branch〈`origin/HEAD`〉の祖先、`git cherry` がすべて `-`、または HEAD の commit を head に持つ PR が MERGED）。(8) 中身が origin にある（upstream があり `git rev-list @{u}..` が 0 件、または HEAD の commit を head に持つ PR が MERGED。PR は `gh api repos/{owner}/{repo}/commits/<HEAD>/pulls` の行のうち `merged_at` があり `head.sha` が HEAD と同じものを見る。Orca の branch 名は PR の head と違うので名前では引きません）。upstream が無く PR も確かめられないときは `残す（upstream が無い）`。中身が既定の branch に入っているだけでは通しません（作りたての worktree が入るため）。`gh` が無い・失敗したときは、PR で決める条件を通さず、理由に「gh 未確認」と書きます。
  - 作り直せない無視ファイル: `git status --porcelain --ignored` の `!!` の行から、作り直せる dir（`node_modules`・`dist`・`build`・`out`・`.next`・`.turbo`・`.cache`・`coverage`・`__pycache__`・`.venv`・`.pytest_cache`・`playwright-report`・`test-results`・`*.tsbuildinfo`・`.eslintcache`・`.DS_Store`）を除いた残りのファイル数を、先頭の dir ごとに数えます（上限 1,000 で止めて「1000 件以上」）。1 件以上あれば、行は「消してよい  <path>  [branch]  作業なし・…／退避が要る: .tmp 12 件・…／持ち主の会話: 未確認」の形で出て（verdict は `消してよい` のまま。`--json` は `evacuate` の配列）、消す前に持ち主が退避します。
  - 「消してよい」の行には必ず「持ち主の会話: 未確認（コーディネーターが確かめる）」が付きます。道具は会話の持ち主を知りません。コーディネーターが持ち主に聞いてから消します。
  - 一覧の末尾に「消し方: `git worktree remove <path>`（branch は残る）。`orca worktree rm` は merge 済みの手元の branch も消そうとするので、残したいときは使わない」の 1 行が出ます。
  - `local-ci.sh` の `lci-*` と Workflow の `.claude/worktrees` の `agent-*`・`wf_*` も一覧に出ます（外しません）。使用中の判定（(2)(3)(5)）に当たれば `残す` です。
  - exit code は 0（一覧が出た）・2（git のリポでない・使い方の誤り。`--orca` で `orca` が無いときも 2）。足すプラグインの `hirai-task after-merge` の出力の末尾と、`hirai-notify done` の本文の末尾に、1 本以上あるときだけ「消してよい worktree: N 本（うち退避が要る M 本。`hirai-worktrees list` で見る）」の 1 行を足します（0 本なら出しません）
- **`worktree: block` の限界（止める範囲を広げません。`_meta.md` 条 5 は止めすぎを避ける）**:
  - `cd <別のリポ> && git commit` は `cd` を追わず、**会話の cwd のリポ**で判定します。別のリポへ commit するときは `git -C <dir> commit` を使ってください（拒否の文言にも 1 行出します）
  - `git -C` の引数に変数やコマンド置換（`$DIR`・`$(...)`）を含む形は、値を解決できないので**通します**
  - **読み切れないコマンドは、止める側に倒さず通します**（`_meta.md` 条 5 の例外は編集と commit だけ）。通る例: 二重引用符の中のバッククォートの `git commit`（`echo "`git commit -m x`"`）、`bash -c $'git commit -m x'`、`git -C "$DIR" commit`（`-C` の先が変数）、`$GIT commit`（コマンド名が変数）、heredoc や pipe で bash に渡す `git commit`（`bash <<'EOF'`）、別の道具（スクリプト）が中で打つ `git commit`。`eval "git commit …"`・`bash -c 'git commit …'`・`$(…)` の中の `git commit` は中身を調べて止めます
  - 外側のリポの `.tmp/` と `.claude/state/` の下は、その写し自身の `mode.yml` が `worktree: block` でも止めません（そこに作った別の clone・worktree の編集と commit は、その clone の toplevel が対象です）

### PR の本文と画面のキャプチャ

PR の本文は 9 節（ひとことで → 課題 → 解決の方針 → 何が変わるか → 読む順 → 実装の要点 → 確かめたこと → 承認カード・決めてほしいこと → 対応する issue）で、課題から実装へ抽象から具体の順に書きます。雛形は `templates/pull_request_template.md` で、`/hirai-lite:init` が導入先の `.github/pull_request_template.md` に**無ければ**置きます（あれば触りません）。「解決の方針」と「何が変わるか」では、流れ・つながり・前後の違いを、文の前に mermaid の図で全体像として置きます（flowchart・sequenceDiagram・stateDiagram・erDiagram。図は文の代わりではありません。GitHub は PR の本文の mermaid を描きます。雛形に例が 1 つ、注の中にあります）。背景と各節の書き方は `docs/rules-reference/git-and-pr.md` の §9、規範は `rules/code.md` の「PR」の節です。画面を変えた PR は、前後のキャプチャを `hirai-pr-asset <PR 番号> <png ...>` で branch `pr-assets` に置き、出た Markdown の 1 行を「何が変わるか」に貼ります（作業ツリーの branch は動かしません。押し先は git の remote から引き、読めないと exit 1）。

## やること管理（GitHub Project）・コンソール・スマートフォン

この節は**足すプラグイン `hirai-project-method` を入れたリポ（`.claude/mode.yml` が `tasks: github-project`）だけ**の話です。やることを GitHub の issue と Project（wave → feature → task、Status 8 値）で持ち、読み書きは足すプラグインの `hirai-task` が行います（足すプラグインを入れると `bin/` が PATH に入ります）。台帳の形（既定）のリポは読まなくて構いません。

### 新しいプロジェクトで立ち上げる（`/hirai-project-method:project-setup`、v2.7.0）

`/hirai-lite:init` のあとに `/hirai-project-method:project-setup` と入力します。

1. まず**計画だけ**を見せます（何を作るか・何がすでにあるか）。GitHub に Project を作る外向きの操作なので、ここで承認をお願いします
2. 承認すると、Project の作成・リポへの紐づけ・項目（Status 8 値・種別・着手順・ひとこと・推奨）・ビュー 8 枚までを自動で行います。組織にテンプレートの Project があれば `--from-template <owner>/<番号>` で複製して作ります（ビュー・項目・auto-add 以外の自動化を引き継ぎます）
3. 組込の自動化の On と、全体ビューの階層表示・wave の並びは GitHub の API では設定できないので、**何を・どこで（URL）・どの値で**の表で案内します
4. 最後に `hirai-task ready` が動くことを確かめます

すでに Project が紐づいているリポでは作り直さず、足りない項目・選択肢だけを足します。手順の本体は 足すプラグインの `docs/rules-reference/project-setup.md` です。`gh` の token に `project` の権限が要ります（無ければ `gh auth refresh -s project` を案内します）。

### 全体像と、どこで何件止まっているか（`/hirai-project-method:board`、v2.7.0）

`/hirai-project-method:board` と入力するか、「進捗を見せて」と頼むと、GitHub Project から次をまとめて出します（読むだけで、GitHub には書き込みません）。

- **止まっているものの件数**: 承認待ち・判断待ち（裁定）・依存待ち・保留・レビュー中・着手可なのに着手できない（理由ごと）・人の作業（`[User]`）
- **あなたの番**: 人が動かすもの（承認待ちの feature・判断待ち・`[User]`・レビュー中の PR）
- wave ごと × Status の件数

会話には短い表で出し、詳しい版は HTML（wave の依存図・wave ごとの feature 表・止まっている task の表）に書き出してパスを出します。ターミナルでは `hirai-task board --text` で wave → feature → task の木も見られます。着手できるかの最終判断は `hirai-task ready` が正です（「着手できる」の数は `ready` と同じ判定で数えます）。HTML と取得の控えは git の管理ディレクトリの下（`.git/hirai-task/`）に置くので、作業ツリーは汚れません。控えは 10 分使い、そのあいだは GitHub に問い合わせません（今すぐ取り直すときは `/hirai-project-method:board refresh`）。

### 承認・判断・人の作業をカードで受ける（v2.8.0）

承認待ちの feature・判断待ち・人の作業（`[User]`・`[操作]`）には、issue の本文の先頭に**カード**を置きます（型は `docs/rules-reference/approval-template.md`）。1 行目に「決めること」と「推奨」があるので、案件を知らない人でも本文の頭だけで判断できます。

| 道具 | すること |
|---|---|
| `hirai-task card <番号>` | 本文のカードを読み、形（必要な行・順番・長さ）を確かめて会話の形で出す。問題があれば理由を並べる |
| `hirai-task card <番号> --sync` | 承認カードの「決めること」「推奨」を、ボードの項目「ひとこと」「推奨」に写す（承認しても今は作業が動かない feature は、その理由も添える）。承認ビューで一覧を並べて選べる。決めるのは本文のカードを開いてから |
| `hirai-task card --lint` | カードの無い・形の崩れた承認待ち・判断待ち・人の作業を一覧にする（読むだけ。会話の最初に回す） |
| `/hirai-project-method:board` | 「あなたの番」にカードの 1 行目を出し、**承認しても作業が動かない feature**（中身が保留・判断待ちだけ、blocked by がある、子が無い）に理由つきの印を付ける |

feature を起こすと（`hirai-task new --kind feature`・`new --from-table`）、本文の先頭に承認カードの雛形が入ります。設計メモから埋められる行は埋め、推奨は空けておきます（推奨は AI が案件を読んで書きます。承認する人が書くものではありません）。`hirai-task setup` は項目「ひとこと」「推奨」と、ビュー「人の作業」「人の操作」を足し、承認ビューを「承認待ちの feature だけ」に絞ります。

### スマートフォンから進捗を見て、指示する（v2.7.0）

| やりたいこと | やり方 | 前提 |
|---|---|---|
| 進捗を聞く・指示する | Claude アプリの **Code** から、手元で動いているセッションを開き、「進捗を見せて」と送る。スマホの幅で読める短い表で返ります。そのまま「#123 に着手して」と指示できます | 手元の PC で Claude Code が動いていること（[Remote Control](https://code.claude.com/docs/en/remote-control)）。`/config` の **Enable Remote Control for all sessions** をオンにすると毎回自動でつながります。アプリは Claude Code で `/mobile` と打つと QR が出ます |
| 確認や質問にスマホで答える | 許可の確認・質問が来たら通知が届くので、アプリで答える | `/config` の **Push when actions required** をオン |
| PC を閉じていても進捗を見る | 進捗用の issue を 1 本作ってピン留めし、`hirai-task board --publish <その issue の番号>` で本文に要約を書いておく。GitHub アプリでいつでも読めます。Project のビュー（承認・裁定・止まっているもの）も GitHub アプリで開けます | `--publish` だけは GitHub に書き込みます（目印の間だけを置き換え、ほかの本文は変えません） |
| 着手を承認する・裁定する | GitHub アプリで feature の Status を「着手可」に動かす。判断待ちの issue にはコメントで答える | コメントは次の会話の最初に `hirai-task comments` が拾います |

- Remote Control は claude.ai のログインが要ります（API キーや Bedrock・Vertex では使えません）。実行とファイルは手元の PC のままです
- アプリから打ったスラッシュコマンドが通るかは確かめていません。「進捗を見せて」のように文で頼めば、Claude が `/hirai-project-method:board` を呼びます

## 1.x・2.x から 3.0.0 へ移る

3.0.0 は、1.x（`hirai-lite`・1.16.0）と 2.x（`hirai-lite-v2`・2.9.0）の両方の続きです。配る系列は `main` の 1 本になり、2.x は退役して `v2` ブランチに凍結します（新しい版は出ません）。

**install・disable・uninstall は、このリポの行の `projectPath` と同じ場所（worktree ではなく本体の checkout）で打ちます。** このリポの行とは、`~/.claude/plugins/installed_plugins.json` の `hirai-lite-v2@hirai-lite` の行のうち `git rev-parse --git-common-dir` が同じものです。user の範囲の行は `projectPath` を持たないので、どこで打ってもかまいません。行が 2 本あれば 1 本ずつ打ちます。worktree で打つと 3.0.0 の行がその worktree の path で記録され、worktree を消したあと本体とほかの worktree で読み込まれなくなります（エラーも出ません）。`--scope <v2 の範囲>` は、端末で打つ uninstall・install・update に要ります（uninstall は付けないと「installed in project scope, not user」で失敗します）。disable・enable は範囲を自動で見つけるので、複数の範囲に入っているときだけ付けます。`worktree: block` のリポでは、install・disable・uninstall は本体で、commit だけ Orca の worktree で行います。

| いま | 移り方 |
|---|---|
| 1.x（`hirai-lite@hirai-lite`） | 更新だけ（`/plugin marketplace update hirai-lite` → 端末で `claude plugin update hirai-lite@hirai-lite --scope <入れた範囲>`（画面なら `/plugin` → Installed → Update now） → 開き直し → `/hirai-lite:update`）。台帳の形のまま動きます。2.x の痕跡が無ければ `mode.yml` には何も書きません（`tasks:` が無くても `ledger` で動きます）。手順 4 で `updated` と出た写しが git に入っているなら commit します（ほかの worktree の画面下が古い写しのまま「更新あり」を出し続けないため） |
| 2.x（退役した `hirai-lite-v2@hirai-lite`）で台帳の形 | `/plugin marketplace update hirai-lite` → `/plugin install hirai-lite@hirai-lite`（**2.x の行と同じ範囲で入れる**。user なら `--scope user`、project なら `--scope project`、local なら `--scope local`）→ `/plugin disable hirai-lite-v2@hirai-lite`（2.x の行の範囲で）→ 会話を開き直し、開始時の 1 行に `hirai-lite v3.0.0` が出ることを確かめる → `/hirai-lite:update`（`tasks:` を書く）→ `.claude/mode.yml` の `tasks:`（手順 2b が書いたとき）、`/hirai-lite:update` の手順 4 で `updated` と出た写しが git に入っているなら（`.claude/statusline.sh`・`tasks-path.sh`・`context-usage.sh`）、2.x の行が **project の範囲**のときだけ `.claude/settings.json` の `enabledPlugins`（`hirai-lite-v2` の行を `hirai-lite` に書き換えたもの。local・user の範囲では settings.json は無いので触りません）を **1 つの commit** で既定の branch に入れ、開いている worktree が取り込んだら、取り込みを確かめて（手順 2b が `tasks:` を書いたときは、各 worktree の `.claude/mode.yml` に `tasks:` がある。書かなかったリポでは、project の範囲なら `settings.json` の `enabledPlugins`、それ以外は開始時の表示の `v3.0.0`）→ ほかの人は、持ち主の commit を**取り込んだ直後に**、各自の clone で、自分が 2.x を入れた範囲と同じ範囲で `claude plugin install hirai-lite@hirai-lite --scope <範囲>`（GitHub Project のリポは `hirai-project-method@hirai-lite` も）を打つ（取り込む前に打つと `.claude/settings.json` が書き換わって pull が止まる。打ってしまったら `git checkout -- .claude/settings.json` で戻してから取り込む）→ `/plugin uninstall hirai-lite-v2@hirai-lite`。`/hirai-lite:update` は、書く値が既定と同じ `ledger` でプロジェクト側に `mode.yml` が無いときは書きません（その旨を 1 行で報告します）。**uninstall は update と commit のあと**です（uninstall すると 2.x の控えが消え、`/hirai-lite:update` が 2.x の形を読めません。`tasks:` を commit していないと、同じリポのほかの worktree・clone は `ledger` のまま戻れません。`enabledPlugins` が `hirai-lite-v2: true` のまま uninstall すると、その worktree では `hirai-lite` が 1 つも読み込まれず、エラーも出ません） |
| 2.x で GitHub Project の形 | `/plugin marketplace update hirai-lite` → `/plugin install hirai-lite@hirai-lite` と `/plugin install hirai-project-method@hirai-lite` を入れる（**2.x の行と同じ範囲で入れる**。user なら `--scope user`、project なら `--scope project`、local なら `--scope local`）→ `/plugin disable hirai-lite-v2@hirai-lite`（2.x の行の範囲で）→ 会話を開き直し、開始時の 1 行に `hirai-lite v3.0.0` が出ることを確かめる → `/hirai-lite:update`（`tasks:` を書く）→ `.claude/mode.yml` の `tasks:`（手順 2b が書いたとき）、`/hirai-lite:update` の手順 4 で `updated` と出た写しが git に入っているなら（`.claude/statusline.sh`・`tasks-path.sh`・`context-usage.sh`）、2.x の行が **project の範囲**のときだけ `.claude/settings.json` の `enabledPlugins`（`hirai-lite-v2` の行を `hirai-lite` に書き換えたもの。local・user の範囲では settings.json は無いので触りません）を **1 つの commit** で既定の branch に入れ、開いている worktree が取り込んだら、取り込みを確かめて（手順 2b が `tasks:` を書いたときは、各 worktree の `.claude/mode.yml` に `tasks:` がある。書かなかったリポでは、project の範囲なら `settings.json` の `enabledPlugins`、それ以外は開始時の表示の `v3.0.0`）→ ほかの人は、持ち主の commit を**取り込んだ直後に**、各自の clone で、自分が 2.x を入れた範囲と同じ範囲で `claude plugin install hirai-lite@hirai-lite --scope <範囲>`（GitHub Project のリポは `hirai-project-method@hirai-lite` も）を打つ（取り込む前に打つと `.claude/settings.json` が書き換わって pull が止まる。打ってしまったら `git checkout -- .claude/settings.json` で戻してから取り込む）→ `/plugin uninstall hirai-lite-v2@hirai-lite`。`/hirai-lite:update` が 2.x の控え（`~/.claude/plugins/data/hirai-lite-v2-hirai-lite/`）を見て `tasks: github-project` を書きます（書いたことと、commit が要ることが 1 行ずつ報告されます）。**commit して既定の branch に入れ、開いている worktree が取り込む前に uninstall しない**でください（ほかの worktree・clone に `tasks:` が届かず `ledger` のまま動きます）。呼び名は `/hirai-lite:board`・`:project-setup` から `/hirai-project-method:board`・`:project-setup` に変わります |

- **commit は有効にするだけで、入れません。** 公式の仕組みでは、`enabledPlugins` の commit を取り込んだ人も、clone ごとに `claude plugin install <name>@<marketplace> --scope project` を打つまで、`hirai-lite` が 1 つも読み込まれません（2.x は `enabledPlugins` から消えて無効、3.0.0 は入っていない状態になります）。入れる操作は人ごとに要り、持ち主の commit を取り込んだ直後に、自分が 2.x を入れた範囲と同じ範囲で打ちます（取り込む前に打つと `.claude/settings.json` が書き換わって pull が止まります。打ってしまったら `git checkout -- .claude/settings.json` で戻してから取り込みます）。
- **2.x を user の範囲で入れたとき**は、控えが機械に 1 つ（`~/.claude/plugins/data/hirai-lite-v2-hirai-lite/tasks-<slug>.json`）で、uninstall するとどのリポの控えも消えます。2.x を使う全部のリポで手順 3（`/hirai-lite:update` と commit）まで済ませてから uninstall します（控えの一覧: `ls ~/.claude/plugins/data/hirai-lite-v2-hirai-lite/`）。
- **local の範囲で入れたとき**は、`enabledPlugins` が git に入らない `.claude/settings.local.json` にあり、`.claude/settings.json` は触りません。取り込みの確かめは `.claude/mode.yml` の `tasks:` で行います。

`enabledPlugins` を直接書いているリポ（`.claude/settings.json`）は、2.x の `hirai-lite-v2@hirai-lite` を `hirai-lite@hirai-lite`（と、使うなら `hirai-project-method@hirai-lite`）に書き換えます。

### ターミナルから入れるとき、clone で落ちることがある

`claude plugin install` が `git@github.com:` で clone する環境では、SSH の鍵が無いと落ちることがあります（2.x の github source で起きた記録があります。3.0.0 の `hirai-lite`・`hirai-project-method` はカタログと同じリポジトリの中を指す相対 path ですが、カタログの追加の clone で同じ形になる可能性があり、3.0.0 では未検証です）。その実行だけ HTTPS に読み替えて打ちます。

```
GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=url.https://github.com/.insteadOf GIT_CONFIG_VALUE_0=git@github.com: claude plugin install hirai-lite --marketplace thirai-classlab/hirai-method-lite --scope local
```

## `/clear` と続きの再開

会話が長くなったら `/clear` と入力してリセットできます。**消えるのは会話の履歴だけ**です。`CLAUDE.md` と `.claude/rules/` に書いた決まりごとは、[新しい会話のはじめに読み込み直されます](https://code.claude.com/docs/en/memory.md)ので、消えません。ウィンドウを閉じて開き直しても結果は同じで、どちらでも構いません。

ただし**会話の中だけで伝えたことは消えます**。続きをやるなら、消す前に `/hirai-lite:state save` で今の状況を保存し、リセットしたあとに `/hirai-lite:state resume` と入力してください。

`/hirai-lite:state save` は、今の状況を保存したあとに **「次回以降も効くもの」を仕分けます**（v1.14.0）。会話で決まった判断や、詰まって学んだことを、`docs/` 側（背景・事故記録・技術判断）へは**そのまま追記**し、**ルールにあたるもの（`.claude/rules/` や `settings.json`）は必ず承認を取ってから** `/hirai-lite:add-rule` の 6 工程に通します。**次回に効くものが無ければ何も書かず、その旨を 1 行返します**（セッションのたびにルールが勝手に増えないように）。

**承認を求めるときは、承認カードで出します**（v2.8.0。それまでの「判断材料 5 項目」を置き換えました）。1 行目に**決めることと推奨**、続けて**目的（誰の何が良くなるか）/ 位置（全体のどこか）/ 承認すると / しないと / 注意**、最後に番号とリンク。7 行・400 字以内で、案件を知らない人でも 1 分で決められることを目指します。そのうえで、承認する・承認しない・修正して提案し直す、から選んでいただきます。

```
決めること: ログインの試行回数に上限を設けるか。推奨: 承認する
目的: 他人のパスワードを当て続ける攻撃を止め、利用者の口座を守る
位置: 公開前の「安全の仕上げ」の段。この段の残りは3件
承認すると: AIが3つの作業を順に進め、変更3本で出す。1本ずつ戻せる
しないと: 公開後、総当たりの攻撃を止める手段がない（推測。今は観測なし）
注意: 正しい利用者が5回間違えると15分待つ。問い合わせが増えるおそれ
詳しく: feature #7（作業 #31〜#33）／用語は「進め方の用語」
```

「どれにするか」は**判断カード**（選択肢・推奨・期限）、人の手が要る作業は**人の作業カード**（やること・手順・終わったら）で頼みます。**同じ型を、頼むすべての場面で使います** — ルール追加、タスクの着手・完了、設計メモの承認、ルールの棚卸し、commit の分割と元に戻せない操作、費用や動きが変わる設定、参照されていないファイルの削除、既存の安全設定への差分の反映、GitHub Project の立ち上げ。型の本体は `docs/rules-reference/approval-template.md`（記入例 5 つと、悪い例→良い例つき）で、**常時読まれる場所にはカードの名前と 1 行目の形だけ**を置いています。この型は **`/init` が導入先の `docs/rules-reference/` にも配置します**（進め方の用語集 `glossary.md` は足すプラグイン hirai-project-method にあり、`/init` は配置しません）。すでに入っている環境では `/update` が、写しが古い型のままかを見分け、置き換えてよいかを承認カードで伺います（元の写しは `.bak` に残します）。

GitHub Project でやることを管理するリポでは、**着手の承認はボードの承認ビューで受けます**。feature の本文の先頭に承認カードを置き、項目「ひとこと」「推奨」に写すので、ボードの表で一覧を並べて選べます。承認ビューのこの 2 列は `/hirai-project-method:project-setup`（`hirai-task setup`）が出します（今の列は消さず末尾に足します。v2.8.1。スマートフォンの GitHub アプリでこの列がどう見えるかは未確認です）。決めるのは本文のカード（7 行）を開いてからです。答え方は 4 つです — **承認する**: 状態を「着手可」に ／ **条件つきで承認する**: 「着手可」にして条件をコメント ／ **承認しない**: 「保留」にして理由をコメント ／ **直して出し直す**: 直してほしい点をコメント（AI が次の会話の最初に拾ってカードを直します）。会話や PR では着手の承認を求めません（PR の取り込みは出来上がりの確認です）。

（`/clear` と「閉じて開き直す」が細かい点まで完全に同じかどうかは、公式ドキュメントに書かれていません。迷うときは閉じて開き直すほうが確実です。）

## 更新する（既定では自動で新しくなりません）

⚠️ **既定では、放っておいても新しくなりません。** 入れたときの中身がそのまま残り続けます。新しい版が出たら、下の手順で自分で入れ替えてください。自動にすることもできます（[更新を自動にする](#更新を自動にする既定は無効)）が、**このプラグインは自動処理と決まりごとを配るので、更新は動きの変更になります。** 黙って書き換わると「昨日と違う動きをする理由」を追えなくなるため、**既定は無効**にしてあります。

### 更新の合図

セッションを開いたとき、画面の最初のほうにこんな 1 行が出ることがあります。

```
[harness] 更新あり v0.3.0 → v0.9.0 (/hirai-lite:update で適用)
```

これが **更新してくださいの合図**です。足すプラグイン（`hirai-project-method`）が入っているリポでは、その `VERSION` も配布元と比べ、更新があれば同じ行（区切りは「／」）にまとめます。更新の知らせは、今のリポと同じ git のリポ（`git rev-parse --git-common-dir` が同じ）に入っている行だけを数えます（user・managed の範囲の行は通します）。出たら下の 4 ステップを上から順にやります。合図が出ていなくても更新はできます（合図には時間差があります → [合図が出ないとき](#合図が出ないとき)）。

### 手順（上から順に）

| 順番 | 入力するもの | 何が起きるか |
|---|---|---|
| 1 | `/plugin marketplace update hirai-lite` | 配布元の一覧を取り直します。2 の前に打ちます（直前に取り直していないと、2 が古い一覧を見ることがあります） |
| 2 | 端末で `claude plugin update hirai-lite@hirai-lite --scope <入れた範囲>`（画面なら `/plugin` → Installed → Update now）（足すプラグインを入れていれば `claude plugin update hirai-project-method@hirai-lite --scope <入れた範囲>` も） | 本体（と足すプラグイン）を新しい版に入れ替えます。`/plugin update …` と打っても会話の中のコマンドとしては無く、`/plugin` のメニューが開くだけで更新されません |
| 3 | Claude Code を閉じて開き直す | ここで入れ替えが実際に効きます |
| 4 | `/hirai-lite:update` | プロジェクト側にコピーされているスクリプトを最新にし、旧版で `.claude/` に作った書類を `docs/` へ移します |

**4 を飛ばすと、画面下部の表示が古いままになります。** ステップ 1〜3 で新しくなるのはコマンド・自動処理・エージェント・外部ツール接続だけで、`/hirai-lite:init` のときにプロジェクトへ**コピーされた**ファイル（画面下部の表示スクリプトなど）は、その場に残った古いコピーのままだからです。

ステップ 4 が入れ替えるのは、あなたが編集する前提でない 3 本（`statusline.sh` / `tasks-path.sh` / `context-usage.sh`）だけです。手を入れていた場合は、元の内容を `.bak` という名前で残してから入れ替えます。**決まりごと（ルール）・安全設定・mode（進め方）の設定・やること（GitHub の issue と Project。台帳の形のリポでは list.md）には触りません。**

### 更新を自動にする（既定は無効）

ステップ 1〜3 と ステップ 4 は、それぞれ別々に自動にできます。**どちらも既定は無効**で、`/hirai-lite:config` の項目 7 で今の状態を確認・切り替えできます。片方だけ有効にしても構いません。

| 自動にできるもの | 切り替え方 | 誰がやるのか |
|---|---|---|
| **ステップ 1〜3**（本体の入れ替え） | `/plugin` → **Marketplaces** → `hirai-lite` → **Enable auto-update** | **Claude Code 本体の機能です。** このプラグインは何もしていません |
| **ステップ 4**（複製された 3 本） | `/hirai-lite:config` → 7 → 更新後の入れ替えを有効 | このプラグイン |

**ステップ 1〜3 の自動化は、Claude Code がもともと持っている仕組みです。** マーケットプレイス単位で切り替えるもので、`hirai-lite` のような第三者のマーケットプレイスは**既定で無効**です（Anthropic 公式のものは既定で有効）。有効にすると、Claude Code がセッション開始後の背景で（最大 10 分の遅延を挟んで）一覧と本体を新しくします。**動いているセッションはそのまま**で、反映は `/reload-plugins` か次に開いたときからです。同じ切り替えは `settings.json` に直接書くこともできます。

```json
{
  "extraKnownMarketplaces": {
    "hirai-lite": {
      "source": { "source": "github", "repo": "thirai-classlab/hirai-method-lite" },
      "autoUpdate": true
    }
  }
}
```

**ステップ 4 の自動化がこのプラグインの受け持ちです。** 有効にすると、`mode.yml` に `auto_sync: on` が書かれ、**プラグインの版が変わった回のセッション冒頭だけ**、複製された 3 本を配布版に揃えて 1 行報告します。

```
[harness] v1.13.0 に合わせてスクリプト 2 件を入れ替えました (元の内容は .bak に保存) — 反映は次回起動から
```

- **版が同じ回は何もしません。** 比較すらしないので、ふだんのセッション開始は 1 バイトも遅くなりません。手を入れた複製も、その版のうちは上書きされません。
- **中身が配布版と違うものは `.bak` に控えてから**入れ替えます。控えが取れなかったファイルは入れ替えません（戻り道を必ず残します）。
- **決まりごと（ルール）・安全設定・`CLAUDE.md`・やること（GitHub の issue と Project。台帳の形のリポでは list.md）は、自動では一切書き換えません。** 対象は上の 3 本だけです。
- 失敗してもセッションは壊れません（通信も CLI 呼び出しもせず、何が起きても `exit 0` で抜けます）。
- ステップ 2（書類の移動）と ステップ 3（rules の再配置）は**自動にできません**。どちらも「同名衝突をどちらに寄せるか」「どのルールを新しくするか」という利用者の判断を含むので、`/hirai-lite:update` で人が見ます。
- 1 回だけ止めたいときは環境変数 `HC_AUTO_SYNC=off`（`mode.yml` より優先されます）。

### 合図が出ないとき

**合図が出ないことは「最新である」ことの証明にはなりません。** 次の 2 つの間は必ず黙っています（実際に動かして確かめました）。

- **入れた直後の 1 セッション目。** 表示に使うのは前回調べた結果なので、初回は比べる相手がありません。**2 セッション目から**出ます。
- **前回調べてから 24 時間の間。** 調べた時点で最新だったなら、その直後に新しい版が出ても、次に調べるまで気づきません。

いますぐ確かめたいときは、`/hirai-lite:update` と入力して「更新があるか調べて」と伝えてください。手で確かめるなら次の 2 つを見比べます（値が違えば更新できます）。

```bash
curl -fsSL https://raw.githubusercontent.com/thirai-classlab/hirai-method-lite/main/VERSION     # 公開されている最新版
claude plugin list                                                                            # いま入っている版
```

24 時間を待たずに調べ直させたいときは、控えを消してからセッションを開き直します。

```bash
rm -rf "${TMPDIR:-/tmp}/claude-harness-lite"
```

（合図そのものを止めたいときは環境変数 `HARNESS_UPDATE_CHECK=off` を設定してください。）

### v0.6.0 以前を入れている場合

**v0.1.0 〜 v0.6.0 には不具合があります。** マニフェスト (`plugin.json`) が自動で読み込まれる `hooks/hooks.json` を二重に指していたため、`/plugin` の一覧や `claude plugin list` で次のように表示されます。

```
Status: ✘ failed to load
Error: Hook load failed: Duplicate hooks file detected: ./hooks/hooks.json …
```

Claude Code 2.1.247 で実際に確かめたところ、この表示が出ていても**コマンド 12 個・自動処理 2 個・エージェント 3 個・外部ツール接続 2 個はいずれも動いていました**（`claude plugin details` の一覧だけがエージェント数を 0 と誤って表示します）。とはいえ「読み込みに失敗した」と表示され続けるのは正常ではなく、Claude Code の版によっては本当に読み込まれない可能性があります。**v0.7.0 で修正済みなので、上の手順で更新してください。**

いま入っている版は `claude plugin list` の `Version:` 行で分かります。

## 全プロジェクトで使いたいとき

> ここは**決まりごと（ルール）をどこに置くか**の話です。[ステップ 2](#2-どこに入れますかと聞かれます--local-を選びます) の「プラグインを入れる範囲」とは**別の話**で、`/hirai-lite:init` に `user` を付けるかどうかだけで決まります。どこでも使えるようにしたいなら、ステップ 2 で **User** を選んだうえで、ここでも `user` を付けます。

置き場所は 2 つあります。ふつうは `/hirai-lite:init`（既定）のままで大丈夫です。

| やり方 | 入力するもの | 置かれる場所 | 効く範囲 |
|---|---|---|---|
| このプロジェクトだけ（既定） | `/hirai-lite:init` | いま開いているフォルダの `.claude/` | このプロジェクトだけ |
| 全プロジェクト共通 | `/hirai-lite:init user` | ホームの `~/.claude/` | このパソコンで開くすべてのプロジェクト |

全プロジェクト共通に入れると、決まりごと・安全設定・mode（進め方）の設定・statusLine（画面下部の情報表示）がどこでも効きます。プロジェクトの説明の下書き（`CLAUDE.md`）も `~/.claude/CLAUDE.md` に置かれます（`.claude/` の中ではなく、この位置が Claude Code の読む場所です）。ただし**やること（台帳の形のときの list.md）・設計メモの置き場・困ったことの記録帳は作られません**。これらはプロジェクトごとの中身なので、共通の場所に置いても意味がないためです。

⚠️ **両方には入れないでください。** 同じ決まりごとが 2 か所にあると、まったく同じ文章が 2 回読み込まれ、AI が一度に読める容量を無駄に使います（実測で約 3,600 が約 7,300 になり、このハーネスが自分に課している警告線 6,000 を超えます）。`/hirai-lite:init` はもう一方の場所に同じ名前のファイルを見つけると警告を出すので、案内どおりどちらか一方を消してください。

**確認できたこと / できなかったこと**（実装の根拠）:

- ホームの `~/.claude/rules/` が読み込まれることは公式ドキュメントに明記があります。[memory.md](https://code.claude.com/docs/en/memory.md) の「User-level rules」: *Personal rules in `~/.claude/rules/` apply to every project on your machine.* / *User-level rules are loaded before project rules, giving project rules higher priority.*
- **`paths:` を書いたファイルは、ホーム側（`~/.claude/rules/`）でも「該当するファイルを読む・書くときだけ」読まれます。** 照合の基準は、セッションを始めたフォルダです（[公式](https://code.claude.com/docs/en/memory.md) の Path-specific rules。2026-11-15 に確認。以前この節で「未確認」としていた点は、公式に明記されました）。

## mode（進め方）とは

作業の進め方の設定で、値は 2 つだけ。`.claude/mode.yml` に入っていて、**`/hirai-lite:init` の 3 問目で選ぶ**（v1.7.0 から。すでに `mode.yml` がある場合は聞かれず、いまの設定がそのまま残る）。後から `/hirai-lite:config` で切り替えられる（一覧の「1. mode（進め方）」）。画面下部の表示にも出る。

利用者に見せる表記は **`<正式名>（<短い解説>）`** に統一している（v1.6.0 から）。正式名だけでは設定を触ったことのない人に伝わらず、解説だけでは `mode.yml` や `settings.json` の中身と結び付かないため、両方を出す。同じ規則を `ultracode（深く考えて自動で手分けする。利用量が増える）` と `statusLine（画面下部の情報表示）` にも適用している。

| 値 | 表示 | 挙動 |
|---|---|---|
| `normal`（既定） | `normal（確認あり）` | 重要な分かれ道で確認しながら進む |
| `loop` | `loop（自動で進む）` | 確認を求めず最後まで自動で進む（止めたいときは「stop」と伝える） |

**`loop` の進め方は毎ターン思い出させる（v1.11.0）。** ルール本体（`.claude/rules/core.md`）はセッション開始時に一度読まれるだけなので、会話が長くなると効きが薄れて途中で止まる（実使用で「よく止まる」と報告された）。`hooks/loop-reminder.sh` が毎ターン 4 行だけ要点を差し込んで、これを補う。

- **止まる条件は 3 つだけ**（「stop」と言われた / やることが終わった / 続けられないエラー）、**subagent の完了待ちは停止理由にならない**、**ただし新しい設計の追加・決めた内容の変更・元に戻せない操作は `loop` でも確認する**、の 3 点を再掲する
- **`normal` のときは 1 バイトも出さない。** 確認しながら進めたい人に「確認を求めるな」が毎ターン入るのは害でしかないため（`tests/smoke.sh` case 2 が置き場 6 通りで検査する）
- **何も止めない。** 文章を足すだけで、操作を BLOCK も `ask` もしない（`rules/_meta.md` 条 5 の「機械強制は不可逆操作のみ」は**止める**仕組みへの制限なので、reminder は対象外）
- 止めたいときは環境変数 `HC_LOOP_REMINDER=off`
- **Claude Code 2.1.x の後半から、UserPromptSubmit は利用者の入力以外でも動く**（`/loop` の繰り返し・背景の subagent の報告・他のセッションからのメッセージなど。カタログ調査 2026-11-15）。`loop` のときは、そのたびに 4 行が足されます。気になるなら上の環境変数で止めてください

**止まらずに続けるのは、組み込みの `/goal` と組み合わせる（v2.7.0）。** `loop` は「確認を求めない」設定で、ターンが終わったあとに次のターンを始める仕組みではありません。組み込みの `/goal <終わりの条件>` を打つと、ターンごとに別のモデルが条件を満たしたかを判定し、満たすまで続けます（[公式](https://code.claude.com/docs/en/goal)）。たとえば次のように打ちます。

```
/goal hirai-task ready が空で、着手した task はすべて PR を出した
```

- `/goal` は組み込みのコマンドなので、打つのは利用者です（Claude からは呼べません）。判定するモデルはコマンドを実行せずファイルも読まないので、会話の中に出る結果（`hirai-task ready` の出力など）で判定できる条件にします
- `/goal` は権限の確認を減らしません。確認なしで続けるには auto mode と組み合わせます。元に戻せない操作の前の確認は `loop` でも残ります

## ultracode について

`templates/settings.json` は `"ultracode": true` を含む。ultracode は xhigh 推論と、タスクごとの自動 workflow オーケストレーションを常時 on にする設定で、**通常運用よりトークン消費が大きい**。従量課金で使う場合はコスト増を見込むこと。

**v1.4.0 から、`/hirai-lite:init` は配置する前にこれを有効にしてよいか尋ねる**（既定は「有効にする」。v1.6.0 から Claude Code 標準の選択 UI で尋ね、既定の選択肢に `(推奨)` が付く）。「有効にしない」と答えると、`ultracode` を外した settings.json を配置する（`workflowSizeGuideline` は残す。安全設定 `permissions` と画面下部の表示 `statusLine` は残る）。あとから変えるときは、導入先の `.claude/settings.json` の `ultracode` キーを削除するか `false` にする。プラグイン側の素材を編集する必要はない。

併せて `"workflowSizeGuideline": "medium"`（10 本未満の目安）を置く。この値は 1 本の Workflow の総数の助言で、同時数はランタイムが別に抑える（強制上限ではなく、ultracode の付属でもない。on・off のどちらでも効く）。ultracode が on のあいだは「Large workflow」の警告が出ないので、この目安と、レビューの規範（`rules/core.md` の「レビューは並列で立てる」: 観点 2〜3 本・HIGH 以上の行にだけ反証）が歯止めになる。手動起動の同時数の根拠は実測（2026-08-21）。**メインエージェントが Agent tool で手動で** 4 subagent を同時起動した際、3 件が 600 秒無進捗で stall し 1 件が API 接続断となり成果物はゼロだった。同時 2 件へ落としたところ 5 件連続で成功した（`rules/core.md` の「同時起動は 2 件まで」の根拠）。この事故は**メインが手で並べて起動する場合**の話であり、Workflow ツール内部の並列実行は Workflow ランタイム自身が制御するため別問題（同じ制約を負わない）。小さいスライスで試してから本番実行する、大きな監査は目安を `small` などへ絞る、が肥大への対処になる。

## statusline について

`/hirai-lite:init` は `scripts/statusline.sh` と `scripts/tasks-path.sh` と `scripts/context-usage.sh` を配置先の `.claude/` へ複製し、`templates/settings.json` の `statusLine.command`（`bash "${CLAUDE_PROJECT_DIR:-.}/.claude/statusline.sh"`）から呼ぶ。表示は **2 行**で、1 行目が**いまの状態**、2 行目が**次にできる操作**（v1.5.0 から）。

**ユーザー設定（`~/.claude/settings.json`）にすでに statusLine がある人は、`/hirai-lite:init` が書くかどうかを聞きます（v2.7.0）。** statusLine は 1 つしか持てず、プロジェクトの設定に書くとユーザー設定の表示（Orca など別の道具のものを含む）が隠れるためです。既定は「いまの表示のまま」で、あとから `/hirai-lite:config` の 5 で切り替えられます。

```
Claude Opus 4.5 | ctx 12% ・5h 3% ・7d 8% | mode: normal（確認あり） | feat/rate-limit | やること 4
設定を確認・変更 → /hirai-lite:config
```

GitHub の形のリポでは、末尾の「やること <N>」が「あなたの番 <N>（…）」に替わる。値は `gh` を呼ばず、控えのファイルを読むだけで出す（通信しない）。

1 行目は `<model> | ctx <N>% ・5h <N>% ・7d <N>% | mode: <進め方> | <branch> | やること <N>`。進め方は正式名 + 解説で出す（`normal` → `normal（確認あり）` / `loop` → `loop（自動で進む）`、未知の値はそのまま）。上の例の 1 行目は**表示幅 99 桁**（`loop` でも 99 桁、未知の値なら 93 桁）。v1.5.0 の 89 桁から 10 桁伸びたが、解説を `確認` `自動` まで削っても 95 桁 / 93 桁にしかならず「収まる端末の幅」は変わらないため、読めることを優先して解説を残している。2 行目の設定リンクは**常に出る**（37 桁）。

**色は補助でしかない。** モデル名 / ブランチ / やること はグレー、`ctx` `5h` `7d` は緑 → 黄 → 赤（50% 以上で黄、80% 以上で赤）、`mode` の値は進め方ごとに別の色、設定リンクは控えめなシアン、お知らせは黄。**色を落としても意味は変わらない**ように、数値には `%`、進め方には `normal（確認あり）` / `loop（自動で進む）`、リンクにはコマンド名を文字として必ず出している（色覚特性や配色設定で色が伝わらない環境を想定）。環境変数 `NO_COLOR` が設定されていれば色を一切出さない。

**お知らせ**は 2 行目の設定リンクの後ろに、下の表を上から見て**当てはまった 1 つだけ**を出す。どれにも当てはまらなければ設定リンクだけが残る。

| 優先 | 出るとき | 表示 |
|---|---|---|
| 1 | 新しい版が出ている | `更新あり → /hirai-lite:update` |
| 2 | ctx が閾値以上（既定 50%、`HC_CONTEXT_THRESHOLD` で変更）| `きりの良いところで /hirai-lite:state save` |

```
設定を確認・変更 → /hirai-lite:config    きりの良いところで /hirai-lite:state save
```

お知らせを止めるなら環境変数 `HC_STATUSLINE_NOTICE=off`（1 の行だけ止めるなら `HARNESS_UPDATE_CHECK=off`）。どちらの場合も設定リンクは残る。**画面下部の表示は通信しない。** 何度も描き直されるため、新しい版が出ているかどうかはセッション開始時の調べ物が置いた控えを読むだけで、`statusline.sh` からは一切通信しない（実測 38ms / 到達不能な URL を設定しても遅くならない）。控えは 24 時間に 1 回しか取り直さないので、更新の合図が出る条件は[合図が出ないとき](#合図が出ないとき)と同じ。

全プロジェクト共通（`/hirai-lite:init user`）に入れた場合だけは、`statusLine.command` を `$HOME` を展開した絶対パス（例: `bash "/home/you/.claude/statusline.sh"`）に書き換える。`${CLAUDE_PROJECT_DIR}` は開いているプロジェクトごとに変わるため、全プロジェクト共通の設定からは使えないため。進め方（`mode.yml`）はプロジェクト側を先に見て、無ければホーム側を見る。

`.claude/statusline.sh` と `.claude/tasks-path.sh` と `.claude/context-usage.sh` の 3 本は**プラグイン所有**であり、`/update` で配布版に置き換わる（中身を変えていた場合は `.bak` に控えを取ってから置き換える。コピーなので元の内容は残る）。`.claude/rules/` `settings.json` `mode.yml` `CLAUDE.md`（と、台帳の形のリポなら `docs/tasks/list.md`）は利用者所有で、更新では触らない。入れ替えの実装は `scripts/update-check.sh` の `harness_sync_owned_scripts` 1 本に集約してあり、`/update` の手順 4（`force` 付き = 必ず実行 + 1 件ずつ作業ログ）と SessionStart の自動入れ替え（opt-in + 版が変わった回だけ + 1 行報告）が**同じ関数**を通る。

プラグイン側のパスを直接指さないのは、**`${CLAUDE_PLUGIN_ROOT}` が settings.json では展開されないため**（[公式仕様](https://code.claude.com/docs/en/plugins-reference.md)の「Where `${CLAUDE_PLUGIN_ROOT}` is Available」に statusLine と project settings は含まれない）。手で配線する場合は `.claude/settings.json` に上記 `statusLine` ブロックを足すか、絶対パスを書く。不要なら `statusLine` キーを消す。

## context 使用率の出し方（画面下部と自動処理で 1 本に統一）

画面下部の `ctx <N>%` と、自動処理（`hooks/context-budget.sh`）が出す「context 使用率が N% に達しました」は、**v1.10.0 から同じ計算を通る**。計算は共通ライブラリ [`scripts/context-usage.sh`](scripts/context-usage.sh) の 1 か所にあり、両方がそれを読む（`scripts/tasks-path.sh` の `harness_mode` と同じ作法）。

| | 中身 |
|---|---|
| 分子 | `input_tokens` + `cache_creation_input_tokens` + `cache_read_input_tokens` + `output_tokens`（**直近の応答 1 件**。会話全体の足し算ではない）|
| 分母 | 窓（context window）のサイズ。`HC_CONTEXT_WINDOW` → 実測値の控え → 既定 `200000` の順に決める |
| 使用率 | 分子 ÷ 分母 を四捨五入した整数の百分率 |
| 閾値 | `HC_CONTEXT_THRESHOLD`（既定 `0.50`。`0.50` でも `50` でも受ける、v1.15.0 で 80% → 50% に変更）。**使用率がこれ以上**で発火する（残量では見ない）|

**窓のサイズは画面下部だけが知っている。** Claude Code が画面下部に渡す JSON には [`context_window.context_window_size`](https://code.claude.com/docs/en/statusline)（`200000` か `1000000`）が入っているが、**自動処理（hook）に渡される JSON にも、transcript にも、環境変数にも入っていない**。そこで画面下部が観測した値を `${TMPDIR:-/tmp}/claude-harness-lite/ctx-window-<セッション ID>` に控え、自動処理はそれを読む（更新の合図を SessionStart → 画面下部へ渡しているのと同じ作法）。

**控えが無いときは推定する（v1.15.0）。** Claude Code の窓は 200,000 か 1,000,000 の 2 種類しか無い。控えが無い条件は次のとおり。

- `statusLine` を設定していない、または `/hirai-lite:init` を実行していない（画面下部が一度も動かないため控えができない）
- 会話の 1 ターン目で、画面下部がまだ一度も描かれていない
- 窓が 1,000,000 の会話（Claude Opus 5 など）で、上記のどちらかに当たる

このとき、直近の使用トークン数が 200,000 を超えていれば「200k の窓ではあり得ない量」として窓を 1,000,000 と**推定**し、表示に「（推定）」を添える（例: `窓 1000000 tokens（推定）`）。推定してもなお 100% を超える（使用トークン数が 1,000,000 も超える）ときは「窓サイズ不明」として扱い、**自動処理は発火しない**（誤って大きい使用率を出すより、沈黙するほうが安全）。

**v1.10.0 〜 v1.14.x の不具合**: 上記の控えが無い条件では窓を 200,000 固定とみなしていたため、控えの無い 1M セッションで実際の使用率とかけ離れた値（例: 使用率 386%）が出ることがあった。実環境で観測（2026-09-15）。

推定が効く条件・効かない条件は次のとおり。

| 状況 | 推定は効くか |
|---|---|
| 控えが無く、直近の使用トークン数が 200,000 を超えている | 効く（窓 1,000,000 と推定し「（推定）」を表示） |
| 控えが無く、直近の使用トークン数が 200,000 以下 | 効かない（200k の会話と 1M の会話の使用開始直後を区別できないため、既定の 200,000 のまま。1M 会話の使用開始直後はこのケースに当たり、実際より高めに出ることがある） |
| 控えが無く、直近の使用トークン数が 1,000,000 を超えている | 効かない（推定してもなお 100% を超える = 窓サイズ不明として発火しない） |
| `HC_CONTEXT_WINDOW` を明示している | 効かない（明示が優先、推定はしない。窓を実際より小さく指定すると使用率は 100% を超えて出ることがある） |
| 控え（画面下部が観測した実測値）がある | 効かない（実測値をそのまま使うため、推定の出番が無い） |

確実に外したいとき、または 1M 会話の使用開始直後（トークン数がまだ 200,000 以下）で早めに正しい値を出したいときは `HC_CONTEXT_WINDOW` で明示する。

```bash
export HC_CONTEXT_WINDOW=1000000   # 窓が 1M の会話
```

**v1.9.0 までの不具合**: 画面下部は Claude Code が計算済みの百分率をそのまま出し、自動処理は「直近のトークン数 ÷ 200,000 **固定**」を自分で計算していた。窓が 1,000,000 の会話では、同じ瞬間に画面下部が `ctx 17%`、自動処理が「83% に達しました」と表示した。**正しかったのは画面下部の 17%** で、自動処理の 83% は分母を 5 分の 1 に取り違えた誤りだった。

## 同梱している MCP サーバー（外部ツール接続）

プラグインの `.mcp.json` で 2 つ配る。インストールした時点で有効になり、`/init` の配置対象ではない。

| 名前 | 用途 | 起動方法 | 必要なもの |
|---|---|---|---|
| `serena` | コードの検索とシンボル操作 | `uvx --from git+https://github.com/oraios/serena@v1.7.0 serena start-mcp-server --context ide-assistant` | [uv](https://docs.astral.sh/uv/)（`uvx`） |
| `context7` | ライブラリ公式ドキュメントの取得 | `npx -y @upstash/context7-mcp@4.0.3` | Node.js（`npx`） |

- **バージョンを固定している。** 同梱の外部ツール接続は、インストールすると承認を挟まずにつながる。固定しないと、配布元の最新コミットがそのままあなたのパソコンで実行されることになるため、`serena` はタグ `v1.7.0`、`context7` は `4.0.3` に固定している。**新しい版に上げたいときは `.mcp.json` の 2 か所を書き換える**（`git+https://github.com/oraios/serena@<タグ>` と `@upstash/context7-mcp@<バージョン>`）。実在するタグ・バージョンかを [serena のタグ一覧](https://github.com/oraios/serena/tags) と `npm view @upstash/context7-mcp versions` で確かめてから書き換える（存在しない指定にすると起動しなくなる）。
- **API キーは書かない。** `context7` は `CONTEXT7_API_KEY` 環境変数を参照するだけで、未設定でも動く（レート制限が緩くなる有料キーを持っている人だけが設定する）。
- **すでに自分で `context7` を設定している場合、プラグイン側は登録されないことがある。** 起動コマンドが完全に一致するものは重複として 1 つにまとめられるため。動作に支障は無いが、`claude plugin details hirai-lite` の外部ツール接続の数が実際の状態と違って見えることがある。実際につながっている一覧は `claude mcp list` で確かめる。
- **起動できなくてもセッションは壊れない。** `uvx` や `npx` が無い環境では該当サーバーが接続失敗として表示されるだけで、rules / commands / hooks / 画面下部の表示はそのまま動く。使わないなら `/plugin` の設定でそのサーバーを無効にする。

## 同梱している skill（スキル）

`skills/` に 2 つ（上限 3。`github-project` は足すプラグインへ移した）。コマンドと違って**こちらから呼び出さなくてよい** — 必要な場面を AI が判断して自分で読む手引き。名前と説明だけが常時載り、**本文は読まれた時にだけ**コンテキストに入る（[公式](https://code.claude.com/docs/en/skills)）ので、長い手引きを持っても普段の容量を食わない。

| 名前 | 役割 |
|---|---|
| `grilling` | 決めごとを掘り下げて聞く進め方。決定事項を design tree に置き、**前提が確定した質問だけをまとめて 1 ラウンドで出し、各問に推奨回答を添える**。事実（ファイルの中身・依存・既存コマンド）は AI が自分で調べ、**決定だけを利用者に聞く** |
| `context-engineering` | 決まったこと・学んだことを**次のセッションでも読まれる場所**へ置く判断。T0（毎回）/ T1（該当ファイルを触った時）/ T2（明示 Read のみ）/ T3（読まない）のどれに何をどう書くか、予算をどう守るかを、**Anthropic 公式の記述と URL つき**でまとめてある。承認の型は全作業に効く汎用規範なのでこの skill には入れず、T2 に置いてある（v1.14.0） |

`/hirai-lite:init` の 2 回目（案件ヒアリング）が `grilling` を呼ぶ。単体でも「この案を詰めたい」「grill me」のように頼めば起動する。`context-engineering` は `/hirai-lite:state save` の「次回に効くものを置く」工程と `/hirai-lite:add-rule` が参照する。出典は `skills/context-engineering/references/official-sources.md` に逐語引用と取得日つきで置いてある。

[mattpocock/skills](https://github.com/mattpocock/skills)（MIT License, Copyright (c) 2026 Matt Pocock）の `skills/productivity/grilling/SKILL.md` を **1 バイトも変えずに**取り込み、出典・commit・sha256 を [`NOTICE.md`](NOTICE.md) に保持している（`context-engineering` は本ハーネスの自作）。

**上流にはこれを含む 25 個のスキルがある。** 全部欲しいときは、このプラグインとは別に入れる:

```
claude plugins install mattpocock-skills
```

（上流から取り込んだのが `grilling` 1 個だけなのは、`rules/_meta.md` の「数の予算」で skill を 3 個までに抑えているため。25 個を抱えると `name` と `description` が常時ロードされて予算を食う。）

## 同梱しているエージェント

`agents/` に 1 つ（`tdd-guide`。テストを先に書く進め方の案内）。

**レビューの担当は v2.7.0 で Claude Code 組み込みのものに替えた。** 以前は `code-reviewer` と `security-reviewer` も同梱していたが、外した。

- **正しさ**: 組み込みの `/code-review`（bundled skill。Claude が回せる。本体と一緒に更新され、effort の段階や PR の指定も使える）。`rules/core.md` のレビューの例もこれを名指しする
- **再利用・簡素化**: 組み込みの `/simplify`（bundled skill）。**直しまで当てる**ので、並列レビューの観点には入れず、指摘の対応が終わってから単独で回す
- **脆弱性**: 組み込みの `/security-review` は**利用者が打つコマンド**で、Claude からは呼べない（[公式のコマンド一覧](https://code.claude.com/docs/en/commands) で Skill の印が無い）。AI が回すレビューでは、脆弱性の観点を指示した reviewer（サブエージェント）を立て、merge 前に利用者が `/security-review` を打つ

以前の `hirai-lite:code-reviewer` を呼んでいた手順は `/code-review` に、`hirai-lite:security-reviewer` は脆弱性の観点の reviewer か利用者の `/security-review` に読み替える。

`tdd-guide` は [everything-claude-code](https://github.com/affaan-m/everything-claude-code)（MIT License, Copyright (c) 2026 Affaan Mustafa）から取り込み、出典と著作権表示をファイル冒頭と [`NOTICE.md`](NOTICE.md) に保持している（v2.7.0 でカバレッジの「80%+」を「導入先が決めた基準」に替えた。hirai-lite の rules に無い数値を持ち込まないため）。

## 詳しい導入手順

ここから下は仕組みを知りたい人向け。配布は **Claude Code プラグイン** 1 経路のみ。プラグイン名は `hirai-lite`。

1. **マーケットプレイスを追加してインストールする**。

   ```
   /plugin marketplace add thirai-classlab/hirai-method-lite
   /plugin install hirai-lite@hirai-lite
   ```

   GitHub Project でやることを回すリポだけ、続けて `/plugin install hirai-project-method@hirai-lite`（足すプラグイン。土台の hirai-lite 3.0.0 以上が依存で入る。1.x が入っている範囲では、先に `/plugin marketplace update hirai-lite` → 端末で `claude plugin update hirai-lite@hirai-lite --scope <入れた範囲>`（画面なら `/plugin` → Installed → Update now） で土台を上げる。2.x が入っている範囲では、先に「1.x・2.x から 3.0.0 へ移る」の表の順（disable まで）を行う）。

   commands / hooks / agents / MCP サーバー定義はこの時点で有効になる。**rules はまだ配られていない** — プラグインには rules というコンポーネントが無いため。

2. **rules を配置する** — 対象プロジェクトを開いて `/hirai-lite:init` を実行する（全プロジェクト共通に入れるなら `/hirai-lite:init user`）。`rules/*.md` を `.claude/rules/` へ、`templates/settings.json` の permissions と `statusLine` を `.claude/settings.json` へ、`templates/mode.yml` を `.claude/mode.yml` へ（`mode:` の値は手順 1 の質問 3 の答え。ホーム側にすでにあればそちらを使い、プロジェクト側に新設しない）、`templates/CLAUDE.md` をリポジトリ直下の `CLAUDE.md` へ（`user` 指定なら `~/.claude/CLAUDE.md`）、`scripts/statusline.sh` と `scripts/tasks-path.sh` と `scripts/context-usage.sh` を `.claude/` へ配置し、draft dir・事故記録・`.claude/rules-archive/` を作る（`tasks: ledger` のリポでは `docs/tasks/list.md` と `parking-lot.md` も作る。`tasks: github-project` のリポでは作らない）。既存ファイルは上書きしない。

   draft / 事故記録は **常に `docs/` 配下に作る（`docs/` が無ければ作る）**。旧レイアウト（`.claude/tasks/` `.claude/draft/` `.claude/rules-reference/` が残っている環境）のときは**ここでは何も作らず `/hirai-lite:update` の手順 2 に回す** — `docs/` 側に作るとパス解決が `docs/` を先に見るため既存の台帳が黙って隠れるので、先に `mv` で移してから 1 通りに揃える。`scripts/tasks-path.sh` の解決順（`$HARNESS_TASKS_FILE` → `docs/…` → `.claude/…`）は移行前・未移行の環境で台帳を見失わないために残してある。`user` 指定時は draft / 事故記録を作らず、`statusLine.command` だけ絶対パスへ書き換える。

3. **CLAUDE.md を埋める（`/init` の 2 回目）** — 雛形（`templates/CLAUDE.md`）は手順 2 の `/init` が置く（無いときだけ置き、あれば触らない）。**次のセッションで `/hirai-lite:init` をもう一度実行すると、`grilling` skill でヒアリングを行い、`<...>` プレースホルダを実値（概要 / Tech Stack / Commands）に置換し、`docs/` に得られた分だけ書類を作る。** 第 2 段階に入る条件は「配置先に `rules` / `settings.json` / `mode.yml` / `statusline.sh` の 4 つが揃っている」かつ「対応する `CLAUDE.md` に `<...>` が 1 行以上残っている」の 2 つ（埋め終われば入らない）。行動規範は書かない。それは `.claude/rules/core.md` の担当。**`CLAUDE.md` は T0（常時ロード）の 1 本**で、`tests/smoke.sh` case 4 の予算計算にも `templates/CLAUDE.md` として含まれている。雛形をプラグイン直下でなく `templates/` に置いているのは、`claude plugin validate --strict` が「プラグインルートの `CLAUDE.md` は project context として読まれない」と警告するため（v1.7.0 で移動）。

4. **ロード検証** — **`/init` の次に開くセッション**で行う（rules は起動時に読まれるため、`/init` を実行したセッション内では確認できない。`/init` の終了条件にも含めていない）。新しいセッションを開き、T0 の 3 ファイルが載っていること、T1 が `paths:` 該当ファイルを開くまで載らないことを確認する。想定と違えば frontmatter を直す。

5. **更新する** — 既定では自動更新しない（本体の自動更新は Claude Code 本体の機能で、第三者マーケットプレイスは既定 off。複製された 3 本の入れ替えは `mode.yml` の `auto_sync`、既定 off。どちらも `/hirai-lite:config` の項目 7）。手順は `/plugin marketplace update hirai-lite` → 端末で `claude plugin update hirai-lite@hirai-lite --scope <入れた範囲>`（画面なら `/plugin` → Installed → Update now）（足すプラグインを入れていれば `hirai-project-method@hirai-lite` も） → 再起動 → `/hirai-lite:update`（旧レイアウトの書類を `docs/` へ `mv` で移す → rules を再配置 → プラグイン所有の `statusline.sh` / `tasks-path.sh` / `context-usage.sh` を、配置先 (`.claude/` または `$HOME/.claude/`) のうち**実際に在る側だけ**配布版に入れ替え）。利用者向けの手順は[更新する](#更新する既定では自動で新しくなりません)。

## このリポジトリの構成

| パス | 中身 |
|---|---|
| `.claude-plugin/plugin.json` | プラグインのマニフェスト（`VERSION` と同じ版を書く） |
| `.claude-plugin/marketplace.json` | マーケットプレイス定義。3 行: `hirai-lite`（土台・`source: "./"`）・`hirai-project-method`（足すプラグイン・`./plugins/hirai-project-method`）・退役した 2.x（`ref: v2`） |
| `plugins/hirai-project-method/` | 足すプラグイン（`hirai-task`・`/board`・`/project-setup`・skill `github-project`・自分の `plugin.json`・`tests/smoke.sh`）。土台に依存する（`hirai-lite >=3.0.0`） |
| `bin/` | `hirai-notify`（Orca のコーディネーターへの知らせ）・`hirai-watch`（止まった会話の見回り）・`hirai-worktrees`（worktree の片付けの一覧。消さない）・`hirai-pr-retarget`（積んだ PR の付け替え）・`hirai-pr-asset`（PR の本文に載せる画面のキャプチャを branch `pr-assets` に置く）。足すプラグインの `hirai-task` は `plugins/hirai-project-method/bin/` |
| `.mcp.json` | 同梱する MCP サーバー 2 つの定義（キーは環境変数参照のみ） |
| `agents/` | サブエージェント 1 個（`tdd-guide`。MIT、出典は `NOTICE.md`） |
| `commands/` | スラッシュコマンド 12 個（数の上限は v2.7.0 で外した。`init`・`update`・`config`・`rules-audit` は `disable-model-invocation: true` で説明文が常時載らず、Claude からは呼ばれない） |
| `skills/` | スキル 2 個（`grilling` は MIT で出典は `NOTICE.md` / `context-engineering` は自作、`references/` に公式出典。`github-project` は足すプラグインへ移した）。`plugin.json` に `skills` キーは書かない（既定で読まれる） |
| `hooks/` | `hooks.json` + SessionStart 1 本（`session-start.sh`）と UserPromptSubmit 2 本（`loop-reminder.sh` / `context-budget.sh`）は context を足すだけで、操作は止めない。PreToolUse 1 本（`worktree-guard.sh`）は `worktree: block` のときだけ Edit・Write・NotebookEdit と `git commit` を止める（MCP の書き込みの道具は止めない。条 5 の例外。既定の `off` では何もしない）。Notification・PermissionDenied・StopFailure に結ぶ 1 本（`notify-attention.sh`）は `notify: orca` のときだけコーディネーターへ知らせる（判断は変えない） |
| `rules/` | **プラグインは読まない。** `/init` が配置先の `.claude/rules/` へ配る素材 |
| `scripts/` | hook / statusline が source する共通ライブラリ（パス解決 `tasks-path.sh` / context 使用率 `context-usage.sh` / 更新検知 `update-check.sh`）+ `/init` の二重ロード検査 |
| `templates/` | `settings.json` / `mode.yml` / `CLAUDE.md` / draft / `pull_request_template.md`（PR の本文の 9 節。`/init` が導入先の `.github/` に、無ければ置く）の雛形（`CLAUDE.md` は `/init` が導入先へ置く。プラグイン直下に置くと `validate --strict` が警告するため `templates/` に置いている） |
| `tests/smoke.sh` | 自己検証 10 case（予算監査を含む。hook 5 / skill 3 / case 10 の上限も case 6 が見る。command は数だけ出す）。足すプラグインは `plugins/hirai-project-method/tests/smoke.sh` が別に見る |
| `CHANGELOG.md` | 版ごとの変更点。v0.6.0 以前の既知の不具合もここに記録 |
| `CONTRIBUTING.md` | 開発の進め方。**3.0.0 から `main` 1 本で配る**（土台 `hirai-lite` と足すプラグイン `hirai-project-method`。退役した 2.x の `v2` は凍結） |

自己テストは `claude --plugin-dir .` でこのリポジトリ自身をプラグインとして読ませて行う。

## rules 3 層 + 退避層

Claude Code は `.claude/rules/*.md` を再帰的に発見する。`paths:` frontmatter を持つファイルは**該当ファイルを Read・Write・Edit した時と、Bash の単一ファイルの読み（`cat`・`head` など）の時にだけ**ロードされ、持たないファイルは**起動時に常時**ロードされる（[公式仕様](https://code.claude.com/docs/en/memory.md)。Write・Edit は Claude Code 2.1.288、Bash の読みは 2.1.293 から）。`gh` や `hirai-task` だけで進む作業ではファイルに触れないので、T1 は載らない。この挙動をそのまま層設計に使う。

| 層 | 置き場所 | ロード条件 | 予算 | 入れてよいもの |
|---|---|---|---|---|
| **T0 常時** | `CLAUDE.md` / `.claude/rules/*.md`（frontmatter 無し） | 毎セッション | **警告 6,000 / 上限 10,000 tokens** | 全作業に例外なく効く規範のみ。既定では入れない |
| **T1 条件** | `.claude/rules/*.md`（`paths:` あり） | 該当ファイルを触った時 | 1 file 2,000 tokens | ドメイン規範（タスク運用 / コード / インフラ） |
| **T2 参照** | `docs/rules-reference/**` | AI が明示 Read した時のみ | 無制限 | 背景・事故記録・詳細手順・過去の経緯・**承認テンプレート** |
| **T3 退避** | `.claude/rules-archive/**` | ロードしない | — | 失効したルール（履歴として保持） |

T2 を `.claude/rules/` の**外**に置くのは意図的。`rules/` の中に置くと `paths:` を書き忘れた瞬間に T0 へ昇格してしまう。物理配置でこの事故を防いでいる。同じ理由で T0 から T2 へのポインタは張らない（張ると T0 が背景説明で膨らむ）。ポインタは T1 から張る。

同じ理由で **T0 の二重計上も禁止**する。`~/.claude/rules/` と `<project>/.claude/rules/` の両方に同じファイルがあると T0 は倍（実測 3,643 → 7,286 tokens）になり、6,000 の警告線を無言で割る。`/init` は反対側の scope を毎回検査し、重なりがあれば警告を出す（`scripts/scope-check.sh`、`tests/smoke.sh` case 4 で検証）。

`@import` は使わない。CLAUDE.md 展開時に常時展開されるため、context 削減効果がゼロどころか純増になる。

## 設計思想

**常時ロードされるコンテキストの総量に予算を置き、ルールの追加をパイプライン化する**ことだけを設計の中心に据えている。

前身の `hirai-method` は 1,629 file / shell 54,373 行まで肥大し、guard 36 個中 10 個が「ハーネス自身の開発を妨げるため」という理由で無効化されていた。原因は個々のルールではなく、**ルールを追加するときに置き場所・分量・表現・重複を検討する工程が無かった**ことにある。本リポジトリはその 1 点を構造で解く。

**1. 既定は「入れない」。** T0 は 2 段階の予算を持つ。6,000 tokens で `tests/smoke.sh` case 4 が警告を出し（PASS のまま。余裕があるうちに降格候補を決める）、10,000 tokens が hard cap で FAIL する。追加は容易で削除は困難、という非対称を予算で打ち消す。上限に達した後の追加は、既存 1 件を T1/T2 へ降格するまで通らない。**上限は「入れてよい量」ではない** — 新規ルールの既定はあくまで T1 で、T0 に置くには「全作業に例外なく効く」ことの立証が要る（`_meta.md` 条 2）。

**2. 事故 2 回目で初めてルール化する。** 1 回目は事故記録（`docs/rules-reference/incidents.md`）に 1 行記録するだけ。推測による予防ルールを禁じる。前身のハーネスでは、規範の多くが発火実績ゼロの先回りだった。

**3. 機械強制は不可逆操作のみ。** `settings.json` の `deny` / `ask` と hook で止めてよいのは「間違えたら戻せない」操作だけ。無害な操作を止める guard は速度を削り、やがて無効化されて規範と実挙動の乖離を生む。禁じているのは**止めること**なので、context を注ぐだけの hook（`loop-reminder.sh` のような reminder、`session-start.sh` のような表示）はこの条の対象外である。例外は 1 つだけ（3.0.0・2026-11-23 承認）— `.claude/mode.yml` に `worktree: block` を置いたリポでは、Orca の worktree でない会話からの、リポの中の git に入るファイルの編集と `git commit` を止めてよい。読み取り・リポの外（`~/.claude` の記憶の置き場など）・git に入らない場所への書き込み・branch の切り替えは止めない。

**4. メタルールが最初に適用される対象は、メタルール自身。** 「機械強制は不可逆操作のみ」に従えば、予算監査そのものを hook にはできない（予算超過は不可逆ではない）。よって予算チェックと層違反検出は `tests/smoke.sh` の case として実装し、commit 前に走らせる。結果、止めない hook が 4 本と、`worktree: block` のときだけ止める hook が 1 本（条 5 の例外）の計 5 本に収まる。

**5. ゼロから始めて、必要になったものだけ足す。** 前身の 1,629 file から選び出すのではない。実プロジェクトで使い、不足したものだけを `/add-rule` のパイプライン経由で戻す。何が本当に必要かは、削ってみないと分からない。

## ルールを追加するとき

`rules/_meta.md`（配置先では `.claude/rules/_meta.md`）に 9 条とパイプラインがある。要点だけ:

- 追加はユーザー承認必須。削除は承認不要（削除の摩擦を追加より低くする）
- 1 ルール 1 事象・3 行以内。書式は `- **<名前>**: <肯定形 1 行> ／ 例: <1 つ> ／ 失効: <条件>`
- 禁止語彙: `適切に` / `必要に応じて` / `可能な限り` / `十分に` / `慎重に`
- 四半期ごとに点検し、発火 0 のルールは `.claude/rules-archive/` へ退避する（`/rules-audit`）
