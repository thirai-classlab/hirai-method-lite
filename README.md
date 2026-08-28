# hirai-method-lite

Claude Code に「AI が守る決まりごと（ルール）」をひとそろい配る、小さな追加パーツです。あわせて、mode（進め方）の設定・やることの一覧表・取り返しのつかない操作の前の確認・statusLine（画面下部の情報表示）が手に入ります。

いちばんの特徴は、**決まりごとが増えすぎないように上限を決めて管理する**こと。ルールを足すときは必ず決まった手順を通すので、AI が毎回読む文章が際限なく膨らんで肝心なことが埋もれる、という状態を防げます。

## 使いはじめる

所要 5 分ほど。上から順に、書いてあるとおり操作すれば終わります。

⚠️ **表示は Claude Code のバージョンや環境によって変わることがあります。** ここに書いたのは Claude Code 2.1.247 で実際に確かめた内容です。見覚えのない画面が出たときは、文面を読んでから判断してください。確かめきれなかった点は[この節の最後](#確認できなかったこと)にまとめました。

### 1. プラグインを追加する

Claude Code で次の 2 行を順に実行します。

```
/plugin marketplace add thirai-classlab/hirai-method-lite
/plugin install hirai-lite@hirai-lite
```

- **1 行目は配布元の一覧を登録するだけ**です。この時点では何もインストールされません。
- **2 行目で実際に入ります。** 詳細画面が開き、次のステップの選択を求められます。

ターミナルから同じ操作（`claude plugin marketplace add …`）を試したときは確認は出ず、`✔ Successfully added marketplace: hirai-lite` とだけ表示されました。**画面の中から `/plugin` で実行した場合に確認が出るかは未確認です。** 出た場合は、追加先が `thirai-classlab/hirai-method-lite` になっていることを確かめてから進めてください。

なお公式ドキュメントには「プラグインとマーケットプレイスは、あなたの権限で任意のプログラムを実行できる。信頼できる配布元のものだけを入れること」という注意書きがあります（[Security](https://code.claude.com/docs/en/discover-plugins.md#security)）。

### 2. 「どこに入れますか」と聞かれます → **Local** を選びます

2 行目を実行すると、**入れる範囲**を 3 つから選ぶよう求められます。ここは必ず答える必要があります。

| 選択肢 | 効く範囲 | 記録される場所 | ほかの人にも配られるか |
|---|---|---|---|
| **Local**（おすすめ） | いま開いているプロジェクトで、自分だけ | そのフォルダの `.claude/settings.local.json` | 配られない（git に入らない） |
| **User** | このパソコンで開くすべてのプロジェクト、自分だけ | ホームの `~/.claude/settings.json` | 配られない |
| **Project** | いま開いているプロジェクトを触る人全員 | そのフォルダの `.claude/settings.json` | **配られる**（このファイルを commit すると全員に効く） |

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
| コマンド 12 個 + スキル 1 個（画面では合わせて **Skills**） | `/hirai-lite:init` `/hirai-lite:commit` など、こちらから呼び出して使う操作 12 個と、AI が必要なときに自分で読む手引き `grilling` 1 個 |
| エージェント 3 個（**Agents**） | テストの進め方・コード品質・脆弱性をそれぞれ見る担当（`tdd-guide` / `code-reviewer` / `security-reviewer`） |
| 自動処理 2 個（**Hooks**） | セッション開始時の 1 行表示と、容量が増えたときの警告 |
| 外部ツール接続 2 個（**MCP servers**） | コードを検索する `serena` と、ライブラリの公式ドキュメントを取ってくる `context7` |

あわせて、毎回のセッションで常にかかる容量の見積もりも出ます（v1.8.0 をターミナルの `claude plugin details` で見ると `Always-on: ~520 tok` と表示されました。v1.7.0 は約 452 tokens で、増えた分は `grilling` の名前と説明が常時載るぶんです）。

> **`Skills` の件数はコマンドとスキルの合計です。** v1.8.0 の `claude plugin details hirai-lite` は `Skills (13)` と出ます — コマンド 12 個 + スキル 1 個（`grilling`）で、**コマンドが 13 個に増えたわけではありません**。コマンドは `/hirai-lite:` から始まる 12 個のままです。

- **自動処理（hooks）だけを対象にした承認画面は出ません。** 入れた時点で動きます。中身は `hooks/session-start.sh` と `hooks/context-budget.sh` の 2 本だけで、どちらも短いシェルスクリプトです。
- **外部ツール接続（MCP）の 2 つも、承認なしで自動的につながります。** `claude mcp list` で確かめると `plugin:hirai-lite:serena: uvx … - ✔ Connected` のように、名前の頭に `plugin:hirai-lite:` が付いて出ます。`serena` は `uvx`（[uv](https://docs.astral.sh/uv/)）、`context7` は `npx`（Node.js）が必要です。無い場合は該当のものが「つながらない」と出るだけで、ほかの機能はそのまま動きます。

選び終わると `Plugin is now active.`（もう使えます）か `Run /reload-plugins to activate.`（`/reload-plugins` と入力すると使えます）のどちらかが出ます。後者なら、そのまま `/reload-plugins` を実行してください。

### 4. 使いたいプロジェクトで `/hirai-lite:init` と入力します

ここで初めて、決まりごと（ルール）と設定がそのプロジェクトに置かれます。

**置く前に 3 つだけ質問されます**（v1.4.0 から。v1.6.0 から Claude Code 標準の選択 UI で出ます。v1.8.0 で「ファイルの置き場所」を聞くのをやめて 3 つになりました）。どこに入れるか / [`ultracode`（深く考えて自動で手分けする。利用量が増える）](#ultracode-について)を有効にするか / [mode（進め方）](#mode進め方とは)を `normal`（確認あり）と `loop`（自動で進む）のどちらにするか の 3 つで、それぞれ既定の選択肢に `(推奨)` が付いているので、そのまま選べば進みます。すでに入っている設定は上書きしないので、該当する質問は省かれます（`mode.yml` がすでにあれば mode は聞かれません）。すでに一式が入っているプロジェクトで実行したときは質問されず、「すべてそのまま」と報告されます。

置かれるのは次のものです。

- `.claude/rules/` — 決まりごと本体
- `.claude/settings.json` — 安全設定と画面下部の表示
- `.claude/mode.yml` — mode（進め方）（→ [mode（進め方）とは](#mode進め方とは)）。**すでにホーム側（`~/.claude/mode.yml`）に持っている人には、プロジェクト側に新しく作りません**（そちらを黙って覆い隠さないため）
- `CLAUDE.md` — このプロジェクトの説明（概要 / 使っている技術 / よく使うコマンド）の下書き。中身は**次の `/hirai-lite:init` で伺って埋めます**。すでにある場合は触りません
- `docs/` — 書類の置き場。**無ければ作ります**（`docs/tasks/` やることの一覧表 / `docs/draft/` 設計メモ / `docs/rules-reference/` 困ったことの記録帳）。**プロジェクトの書類は常にここです。** 旧版（v1.8.0 以前）で `.claude/tasks/` などに作った環境は、`/hirai-lite:update` が `docs/` へ移します（中身はそのまま移動します）

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

**開き直したら、もう一度 `/hirai-lite:init` と入力してください。今度は案件のことを伺います。** 同梱の `grilling`（[同梱している skill](#同梱している-skillスキル)）が、ゴール → 背景 → スコープ → 体制 → 技術構成 → やること の順に、**前提が決まった質問だけをまとめて出し、それぞれに推奨回答を添えて**聞いてきます。ファイルの中身や依存関係のような「調べれば分かること」は聞かれません（AI が自分で読みます）。伺った内容は `CLAUDE.md` と `docs/`（`overview.md` / `requirements.md` / `architecture.md` / `tasks/list.md`）に書き込まれます。**伺えなかった章のファイルは作られません**（見出しだけの空ファイルを置かないため）。

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

## `/clear` と続きの再開

会話が長くなったら `/clear` と入力してリセットできます。**消えるのは会話の履歴だけ**です。`CLAUDE.md` と `.claude/rules/` に書いた決まりごとは、[新しい会話のはじめに読み込み直されます](https://code.claude.com/docs/en/memory.md)ので、消えません。ウィンドウを閉じて開き直しても結果は同じで、どちらでも構いません。

ただし**会話の中だけで伝えたことは消えます**。続きをやるなら、消す前に `/hirai-lite:state save` で今の状況を保存し、リセットしたあとに `/hirai-lite:state resume` と入力してください。

（`/clear` と「閉じて開き直す」が細かい点まで完全に同じかどうかは、公式ドキュメントに書かれていません。迷うときは閉じて開き直すほうが確実です。）

## 更新する（自動では新しくなりません）

⚠️ **Claude Code のプラグインは、放っておいても新しくなりません。** 入れたときの中身がそのまま残り続けます。新しい版が出たら、下の手順で自分で入れ替えてください。

### 更新の合図

セッションを開いたとき、画面の最初のほうにこんな 1 行が出ることがあります。

```
[harness] 更新あり v0.3.0 → v0.9.0 (/update で適用)
```

これが **更新してくださいの合図**です。出たら下の 4 ステップを上から順にやります。合図が出ていなくても更新はできます（合図には時間差があります → [合図が出ないとき](#合図が出ないとき)）。

### 手順（上から順に）

| 順番 | 入力するもの | 何が起きるか |
|---|---|---|
| 1 | `/plugin marketplace update hirai-lite` | 配布元の一覧を取り直します。**ここを飛ばすと 2 が「すでに最新です」と答えてしまいます** |
| 2 | `/plugin update hirai-lite@hirai-lite` | 本体を新しい版に入れ替えます |
| 3 | Claude Code を閉じて開き直す | ここで入れ替えが実際に効きます |
| 4 | `/hirai-lite:update` | プロジェクト側にコピーされているスクリプトを最新にし、旧版で `.claude/` に作った書類を `docs/` へ移します |

**4 を飛ばすと、画面下部の表示が古いままになります。** ステップ 1〜3 で新しくなるのはコマンド・自動処理・エージェント・外部ツール接続だけで、`/hirai-lite:init` のときにプロジェクトへ**コピーされた**ファイル（画面下部の表示スクリプトなど）は、その場に残った古いコピーのままだからです。

ステップ 4 が入れ替えるのは、あなたが編集する前提でない 2 本（`statusline.sh` / `tasks-path.sh`）だけです。手を入れていた場合は、元の内容を `.bak` という名前で残してから入れ替えます。**決まりごと（ルール）・安全設定・mode（進め方）の設定・やることの一覧表には触りません。**

### 合図が出ないとき

**合図が出ないことは「最新である」ことの証明にはなりません。** 次の 2 つの間は必ず黙っています（実際に動かして確かめました）。

- **入れた直後の 1 セッション目。** 表示に使うのは前回調べた結果なので、初回は比べる相手がありません。**2 セッション目から**出ます。
- **前回調べてから 24 時間の間。** 調べた時点で最新だったなら、その直後に新しい版が出ても、次に調べるまで気づきません。

いますぐ確かめたいときは、`/hirai-lite:update` と入力して「更新があるか調べて」と伝えてください。手で確かめるなら次の 2 つを見比べます（値が違えば更新できます）。

```bash
curl -fsSL https://raw.githubusercontent.com/thirai-classlab/hirai-method-lite/main/VERSION   # 公開されている最新版
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

全プロジェクト共通に入れると、決まりごと・安全設定・mode（進め方）の設定・statusLine（画面下部の情報表示）がどこでも効きます。プロジェクトの説明の下書き（`CLAUDE.md`）も `~/.claude/CLAUDE.md` に置かれます（`.claude/` の中ではなく、この位置が Claude Code の読む場所です）。ただし**やることの一覧表・設計メモの置き場・困ったことの記録帳は作られません**。これらはプロジェクトごとの中身なので、共通の場所に置いても意味がないためです。

⚠️ **両方には入れないでください。** 同じ決まりごとが 2 か所にあると、まったく同じ文章が 2 回読み込まれ、AI が一度に読める容量を無駄に使います（実測で約 3,600 が約 7,300 になり、このハーネスが自分に課している警告線 6,000 を超えます）。`/hirai-lite:init` はもう一方の場所に同じ名前のファイルを見つけると警告を出すので、案内どおりどちらか一方を消してください。

**確認できたこと / できなかったこと**（実装の根拠）:

- ホームの `~/.claude/rules/` が読み込まれることは公式ドキュメントに明記があります。[memory.md](https://code.claude.com/docs/en/memory.md) の「User-level rules」: *Personal rules in `~/.claude/rules/` apply to every project on your machine.* / *User-level rules are loaded before project rules, giving project rules higher priority.*
- 一方、**`paths:` を書いたファイルがホーム側でも「そのファイルを開いた時だけ読まれる」のかは、公式ドキュメントに明記がありません**（`paths:` の説明はプロジェクト側 `.claude/rules/` の節にあり、ホーム側の節では触れられていない）。全プロジェクト共通に入れた場合、必要なときだけ読まれるはずの 3 件が常に読まれる可能性がある点は**未確認**です。気になる場合はこのプロジェクトだけに入れる既定の使い方を選んでください。

## mode（進め方）とは

作業の進め方の設定で、値は 2 つだけ。`.claude/mode.yml` に入っていて、**`/hirai-lite:init` の 3 問目で選ぶ**（v1.7.0 から。すでに `mode.yml` がある場合は聞かれず、いまの設定がそのまま残る）。後から `/hirai-lite:config` で切り替えられる（一覧の「1. mode（進め方）」）。画面下部の表示にも出る。

利用者に見せる表記は **`<正式名>（<短い解説>）`** に統一している（v1.6.0 から）。正式名だけでは設定を触ったことのない人に伝わらず、解説だけでは `mode.yml` や `settings.json` の中身と結び付かないため、両方を出す。同じ規則を `ultracode（深く考えて自動で手分けする。利用量が増える）` と `statusLine（画面下部の情報表示）` にも適用している。

| 値 | 表示 | 挙動 |
|---|---|---|
| `normal`（既定） | `normal（確認あり）` | 重要な分かれ道で確認しながら進む |
| `loop` | `loop（自動で進む）` | 確認を求めず最後まで自動で進む（止めたいときは「stop」と伝える） |

## ultracode について

`templates/settings.json` は `"ultracode": true` を含む。ultracode は xhigh 推論と、タスクごとの自動 workflow オーケストレーションを常時 on にする設定で、**通常運用よりトークン消費が大きい**。従量課金で使う場合はコスト増を見込むこと。

**v1.4.0 から、`/hirai-lite:init` は配置する前にこれを有効にしてよいか尋ねる**（既定は「有効にする」。v1.6.0 から Claude Code 標準の選択 UI で尋ね、既定の選択肢に `(推奨)` が付く）。「有効にしない」と答えると、`ultracode` と `workflowSizeGuideline` の 2 キーを外した settings.json を配置する（安全設定 `permissions` と画面下部の表示 `statusLine` は残る）。あとから変えるときは、導入先の `.claude/settings.json` の `ultracode` キーを削除するか `false` にする。プラグイン側の素材を編集する必要はない。

併せて `"workflowSizeGuideline": "small"` を置き、1 workflow あたりのエージェント数を 5 未満に抑えている。根拠は実測（2026-08-21）。同時 4 subagent を起動した際、3 件が 600 秒無進捗で stall し 1 件が API 接続断となり成果物はゼロだった。同時 2 件へ落としたところ 5 件連続で成功した。並列度を上げるほど stall 率が上がるため、既定は `small` とする。

## statusline について

`/hirai-lite:init` は `scripts/statusline.sh` と `scripts/tasks-path.sh` を配置先の `.claude/` へ複製し、`templates/settings.json` の `statusLine.command`（`bash "${CLAUDE_PROJECT_DIR:-.}/.claude/statusline.sh"`）から呼ぶ。表示は **2 行**で、1 行目が**いまの状態**、2 行目が**次にできる操作**（v1.5.0 から）。

```
Claude Opus 4.5 | ctx 12% ・5h 3% ・7d 8% | mode: normal（確認あり） | feat/rate-limit | やること 4
設定を確認・変更 → /hirai-lite:config
```

1 行目は `<model> | ctx <N>% ・5h <N>% ・7d <N>% | mode: <進め方> | <branch> | やること <N>`。進め方は正式名 + 解説で出す（`normal` → `normal（確認あり）` / `loop` → `loop（自動で進む）`、未知の値はそのまま）。上の例の 1 行目は**表示幅 99 桁**（`loop` でも 99 桁、未知の値なら 93 桁）。v1.5.0 の 89 桁から 10 桁伸びたが、解説を `確認` `自動` まで削っても 95 桁 / 93 桁にしかならず「収まる端末の幅」は変わらないため、読めることを優先して解説を残している。2 行目の設定リンクは**常に出る**（37 桁）。

**色は補助でしかない。** モデル名 / ブランチ / やること はグレー、`ctx` `5h` `7d` は緑 → 黄 → 赤（50% 以上で黄、80% 以上で赤）、`mode` の値は進め方ごとに別の色、設定リンクは控えめなシアン、お知らせは黄。**色を落としても意味は変わらない**ように、数値には `%`、進め方には `normal（確認あり）` / `loop（自動で進む）`、リンクにはコマンド名を文字として必ず出している（色覚特性や配色設定で色が伝わらない環境を想定）。環境変数 `NO_COLOR` が設定されていれば色を一切出さない。

**お知らせ**は 2 行目の設定リンクの後ろに、下の表を上から見て**当てはまった 1 つだけ**を出す。どれにも当てはまらなければ設定リンクだけが残る。

| 優先 | 出るとき | 表示 |
|---|---|---|
| 1 | 新しい版が出ている | `更新あり → /hirai-lite:update` |
| 2 | ctx が閾値以上（既定 80%、`HC_CONTEXT_THRESHOLD` で変更） | `きりの良いところで /hirai-lite:state save` |

```
設定を確認・変更 → /hirai-lite:config    きりの良いところで /hirai-lite:state save
```

お知らせを止めるなら環境変数 `HC_STATUSLINE_NOTICE=off`（1 の行だけ止めるなら `HARNESS_UPDATE_CHECK=off`）。どちらの場合も設定リンクは残る。**画面下部の表示は通信しない。** 何度も描き直されるため、新しい版が出ているかどうかはセッション開始時の調べ物が置いた控えを読むだけで、`statusline.sh` からは一切通信しない（実測 38ms / 到達不能な URL を設定しても遅くならない）。控えは 24 時間に 1 回しか取り直さないので、更新の合図が出る条件は[合図が出ないとき](#合図が出ないとき)と同じ。

全プロジェクト共通（`/hirai-lite:init user`）に入れた場合だけは、`statusLine.command` を `$HOME` を展開した絶対パス（例: `bash "/home/you/.claude/statusline.sh"`）に書き換える。`${CLAUDE_PROJECT_DIR}` は開いているプロジェクトごとに変わるため、全プロジェクト共通の設定からは使えないため。進め方（`mode.yml`）はプロジェクト側を先に見て、無ければホーム側を見る。

`.claude/statusline.sh` と `.claude/tasks-path.sh` の 2 本は**プラグイン所有**であり、`/update` で配布版に置き換わる（中身を変えていた場合は `.bak` に退避してから置き換える）。`.claude/rules/` `settings.json` `mode.yml` `CLAUDE.md` 台帳は利用者所有で、更新では触らない。

プラグイン側のパスを直接指さないのは、**`${CLAUDE_PLUGIN_ROOT}` が settings.json では展開されないため**（[公式仕様](https://code.claude.com/docs/en/plugins-reference.md)の「Where `${CLAUDE_PLUGIN_ROOT}` is Available」に statusLine と project settings は含まれない）。手で配線する場合は `.claude/settings.json` に上記 `statusLine` ブロックを足すか、絶対パスを書く。不要なら `statusLine` キーを消す。

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

`skills/` に 1 つ。コマンドと違って**こちらから呼び出さなくてよい** — 必要な場面を AI が判断して自分で読む手引き。

| 名前 | 役割 |
|---|---|
| `grilling` | 決めごとを掘り下げて聞く進め方。決定事項を design tree に置き、**前提が確定した質問だけをまとめて 1 ラウンドで出し、各問に推奨回答を添える**。事実（ファイルの中身・依存・既存コマンド）は AI が自分で調べ、**決定だけを利用者に聞く** |

`/hirai-lite:init` の 2 回目（案件ヒアリング）がこれを呼ぶ。単体でも「この案を詰めたい」「grill me」のように頼めば起動する。

[mattpocock/skills](https://github.com/mattpocock/skills)（MIT License, Copyright (c) 2026 Matt Pocock）の `skills/productivity/grilling/SKILL.md` を **1 バイトも変えずに**取り込み、出典・commit・sha256 を [`NOTICE.md`](NOTICE.md) に保持している。

**上流にはこれを含む 25 個のスキルがある。** 全部欲しいときは、このプラグインとは別に入れる:

```
claude plugins install mattpocock-skills
```

（このハーネスが `grilling` だけを同梱しているのは、`rules/_meta.md` の「数の予算」で skill を 3 個までに抑えているため。25 個を抱えると `name` と `description` が常時ロードされて予算を食う。）

## 同梱しているエージェント

`agents/` に 3 つ。`rules/code.md` のレビュー規範（「観点の異なる reviewer を 2 本以上並列起動する」）が名指しする相手を実体として配るためのもの。

| 名前 | 役割 |
|---|---|
| `tdd-guide` | テストを先に書く進め方の案内 |
| `code-reviewer` | コード品質・保守性のレビュー |
| `security-reviewer` | 脆弱性・秘密情報混入のレビュー |

3 つとも [everything-claude-code](https://github.com/affaan-m/everything-claude-code)（MIT License, Copyright (c) 2026 Affaan Mustafa）から取り込み、出典と著作権表示を各ファイル冒頭と [`NOTICE.md`](NOTICE.md) に保持している。`rules/code.md` は例として `database-reviewer` にも触れるが、これは同梱していない（必要なら利用者が `.claude/agents/` に置く）。

## 詳しい導入手順

ここから下は仕組みを知りたい人向け。配布は **Claude Code プラグイン** 1 経路のみ。プラグイン名は `hirai-lite`。

1. **マーケットプレイスを追加してインストールする**。

   ```
   /plugin marketplace add thirai-classlab/hirai-method-lite
   /plugin install hirai-lite@hirai-lite
   ```

   commands / hooks / agents / MCP サーバー定義はこの時点で有効になる。**rules はまだ配られていない** — プラグインには rules というコンポーネントが無いため。

2. **rules を配置する** — 対象プロジェクトを開いて `/hirai-lite:init` を実行する（全プロジェクト共通に入れるなら `/hirai-lite:init user`）。`rules/*.md` を `.claude/rules/` へ、`templates/settings.json` の permissions と `statusLine` を `.claude/settings.json` へ、`templates/mode.yml` を `.claude/mode.yml` へ（`mode:` の値は手順 1 の質問 3 の答え。ホーム側にすでにあればそちらを使い、プロジェクト側に新設しない）、`templates/CLAUDE.md` をリポジトリ直下の `CLAUDE.md` へ（`user` 指定なら `~/.claude/CLAUDE.md`）、`scripts/statusline.sh` と `scripts/tasks-path.sh` を `.claude/` へ配置し、台帳・draft dir・事故記録・`.claude/rules-archive/` を作る。既存ファイルは上書きしない。

   台帳 / draft / 事故記録は **常に `docs/` 配下に作る（`docs/` が無ければ作る）**。旧レイアウト（`.claude/tasks/` `.claude/draft/` `.claude/rules-reference/` が残っている環境）のときは**ここでは何も作らず `/hirai-lite:update` の手順 2 に回す** — `docs/` 側に作るとパス解決が `docs/` を先に見るため既存の台帳が黙って隠れるので、先に `mv` で移してから 1 通りに揃える。`scripts/tasks-path.sh` の解決順（`$HARNESS_TASKS_FILE` → `docs/…` → `.claude/…`）は移行前・未移行の環境で台帳を見失わないために残してある。`user` 指定時は台帳 / draft / 事故記録を作らず、`statusLine.command` だけ絶対パスへ書き換える。

3. **CLAUDE.md を埋める（`/init` の 2 回目）** — 雛形（`templates/CLAUDE.md`）は手順 2 の `/init` が置く（無いときだけ置き、あれば触らない）。**次のセッションで `/hirai-lite:init` をもう一度実行すると、`grilling` skill でヒアリングを行い、`<...>` プレースホルダを実値（概要 / Tech Stack / Commands）に置換し、`docs/` に得られた分だけ書類を作る。** 第 2 段階に入る条件は「配置先に `rules` / `settings.json` / `mode.yml` / `statusline.sh` の 4 つが揃っている」かつ「対応する `CLAUDE.md` に `<...>` が 1 行以上残っている」の 2 つ（埋め終われば入らない）。行動規範は書かない。それは `.claude/rules/core.md` の担当。**`CLAUDE.md` は T0（常時ロード）の 1 本**で、`tests/smoke.sh` case 4 の予算計算にも `templates/CLAUDE.md` として含まれている。雛形をプラグイン直下でなく `templates/` に置いているのは、`claude plugin validate --strict` が「プラグインルートの `CLAUDE.md` は project context として読まれない」と警告するため（v1.7.0 で移動）。

4. **ロード検証** — **`/init` の次に開くセッション**で行う（rules は起動時に読まれるため、`/init` を実行したセッション内では確認できない。`/init` の終了条件にも含めていない）。新しいセッションを開き、T0 の 3 ファイルが載っていること、T1 が `paths:` 該当ファイルを開くまで載らないことを確認する。想定と違えば frontmatter を直す。

5. **更新する** — プラグインは自動更新されない。`/plugin marketplace update hirai-lite` → `/plugin update hirai-lite@hirai-lite` → 再起動 → `/hirai-lite:update`（旧レイアウトの書類を `docs/` へ `mv` で移す → rules を再配置 → プラグイン所有の `statusline.sh` と `tasks-path.sh` を、配置先 (`.claude/` または `$HOME/.claude/`) のうち**実際に在る側だけ**配布版に入れ替え）。利用者向けの手順は[更新する](#更新する自動では新しくなりません)。

## このリポジトリの構成

| パス | 中身 |
|---|---|
| `.claude-plugin/plugin.json` | プラグインのマニフェスト（`VERSION` と同じ版を書く） |
| `.claude-plugin/marketplace.json` | 自分自身を 1 エントリとして指すマーケットプレイス定義 |
| `.mcp.json` | 同梱する MCP サーバー 2 つの定義（キーは環境変数参照のみ） |
| `agents/` | サブエージェント 3 個（MIT、出典は `NOTICE.md`） |
| `commands/` | スラッシュコマンド 12 個 |
| `skills/` | スキル 1 個（`grilling`。MIT、出典は `NOTICE.md`）。`plugin.json` に `skills` キーは書かない（既定で読まれる） |
| `hooks/` | `hooks.json` + SessionStart / UserPromptSubmit の 2 本 |
| `rules/` | **プラグインは読まない。** `/init` が配置先の `.claude/rules/` へ配る素材 |
| `scripts/` | hook / statusline が source する共通ライブラリ + `/init` の二重ロード検査 |
| `templates/` | `settings.json` / `mode.yml` / `CLAUDE.md` / draft / task の雛形（`CLAUDE.md` は `/init` が導入先へ置く。プラグイン直下に置くと `validate --strict` が警告するため `templates/` に置いている） |
| `tests/smoke.sh` | 自己検証 10 case（予算監査を含む。hook 5 / command 12 / skill 3 / case 10 の数の予算も case 6 が見る） |
| `CHANGELOG.md` | 版ごとの変更点。v0.6.0 以前の既知の不具合もここに記録 |
| `CONTRIBUTING.md` | 開発の進め方。**`main` は常に配布物**（タグではなく `main` の最新が利用者に届く） |

自己テストは `claude --plugin-dir .` でこのリポジトリ自身をプラグインとして読ませて行う。

## rules 3 層 + 退避層

Claude Code は `.claude/rules/*.md` を再帰的に発見する。`paths:` frontmatter を持つファイルは**該当ファイルを読んだ時にだけ**ロードされ、持たないファイルは**起動時に常時**ロードされる（[公式仕様](https://code.claude.com/docs/en/memory.md)）。この挙動をそのまま層設計に使う。

| 層 | 置き場所 | ロード条件 | 予算 | 入れてよいもの |
|---|---|---|---|---|
| **T0 常時** | `CLAUDE.md` / `.claude/rules/*.md`（frontmatter 無し） | 毎セッション | **警告 6,000 / 上限 10,000 tokens** | 全作業に例外なく効く規範のみ。既定では入れない |
| **T1 条件** | `.claude/rules/*.md`（`paths:` あり） | 該当ファイルを触った時 | 1 file 2,000 tokens | ドメイン規範（タスク運用 / コード / インフラ） |
| **T2 参照** | `docs/rules-reference/**` | AI が明示 Read した時のみ | 無制限 | 背景・事故記録・詳細手順・過去の経緯 |
| **T3 退避** | `.claude/rules-archive/**` | ロードしない | — | 失効したルール（履歴として保持） |

T2 を `.claude/rules/` の**外**に置くのは意図的。`rules/` の中に置くと `paths:` を書き忘れた瞬間に T0 へ昇格してしまう。物理配置でこの事故を防いでいる。同じ理由で T0 から T2 へのポインタは張らない（張ると T0 が背景説明で膨らむ）。ポインタは T1 から張る。

同じ理由で **T0 の二重計上も禁止**する。`~/.claude/rules/` と `<project>/.claude/rules/` の両方に同じファイルがあると T0 は倍（実測 3,643 → 7,286 tokens）になり、6,000 の警告線を無言で割る。`/init` は反対側の scope を毎回検査し、重なりがあれば警告を出す（`scripts/scope-check.sh`、`tests/smoke.sh` case 4 で検証）。

`@import` は使わない。CLAUDE.md 展開時に常時展開されるため、context 削減効果がゼロどころか純増になる。

## 設計思想

**常時ロードされるコンテキストの総量に予算を置き、ルールの追加をパイプライン化する**ことだけを設計の中心に据えている。

前身の `hirai-method` は 1,629 file / shell 54,373 行まで肥大し、guard 36 個中 10 個が「ハーネス自身の開発を妨げるため」という理由で無効化されていた。原因は個々のルールではなく、**ルールを追加するときに置き場所・分量・表現・重複を検討する工程が無かった**ことにある。本リポジトリはその 1 点を構造で解く。

**1. 既定は「入れない」。** T0 は 2 段階の予算を持つ。6,000 tokens で `tests/smoke.sh` case 4 が警告を出し（PASS のまま。余裕があるうちに降格候補を決める）、10,000 tokens が hard cap で FAIL する。追加は容易で削除は困難、という非対称を予算で打ち消す。上限に達した後の追加は、既存 1 件を T1/T2 へ降格するまで通らない。**上限は「入れてよい量」ではない** — 新規ルールの既定はあくまで T1 で、T0 に置くには「全作業に例外なく効く」ことの立証が要る（`_meta.md` 条 2）。

**2. 事故 2 回目で初めてルール化する。** 1 回目は事故記録（`docs/rules-reference/incidents.md`）に 1 行記録するだけ。推測による予防ルールを禁じる。前身のハーネスでは、規範の多くが発火実績ゼロの先回りだった。

**3. 機械強制は不可逆操作のみ。** `settings.json` の `deny` / `ask` と hook で止めてよいのは「間違えたら戻せない」操作だけ。無害な操作を止める guard は速度を削り、やがて無効化されて規範と実挙動の乖離を生む。

**4. メタルールが最初に適用される対象は、メタルール自身。** 「機械強制は不可逆操作のみ」に従えば、予算監査そのものを hook にはできない（予算超過は不可逆ではない）。よって予算チェックと層違反検出は `tests/smoke.sh` の case として実装し、commit 前に走らせる。結果 hook は 2 本に収まる。

**5. ゼロから始めて、必要になったものだけ足す。** 前身の 1,629 file から選び出すのではない。実プロジェクトで使い、不足したものだけを `/add-rule` のパイプライン経由で戻す。何が本当に必要かは、削ってみないと分からない。

## ルールを追加するとき

`rules/_meta.md`（配置先では `.claude/rules/_meta.md`）に 9 条とパイプラインがある。要点だけ:

- 追加はユーザー承認必須。削除は承認不要（削除の摩擦を追加より低くする）
- 1 ルール 1 事象・3 行以内。書式は `- **<名前>**: <肯定形 1 行> ／ 例: <1 つ> ／ 失効: <条件>`
- 禁止語彙: `適切に` / `必要に応じて` / `可能な限り` / `十分に` / `慎重に`
- 四半期ごとに点検し、発火 0 のルールは `.claude/rules-archive/` へ退避する（`/rules-audit`）
