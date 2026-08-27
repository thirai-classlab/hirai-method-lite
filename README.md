# hirai-method-lite

Claude Code に「AI が守る決まりごと（ルール）」をひとそろい配る、小さな追加パーツです。あわせて、作業の進め方の設定・やることの一覧表・取り返しのつかない操作の前の確認・画面下部の情報表示が手に入ります。

いちばんの特徴は、**決まりごとが増えすぎないように上限を決めて管理する**こと。ルールを足すときは必ず決まった手順を通すので、AI が毎回読む文章が際限なく膨らんで肝心なことが埋もれる、という状態を防げます。

## 使いはじめる（3 ステップ）

1. Claude Code で次の 2 行を実行します。

   ```
   /plugin marketplace add thirai-classlab/hirai-method-lite
   /plugin install hirai-lite@hirai-lite
   ```

   途中でいくつか確認の画面が出ます。答え方は次の節にまとめました。

2. 使いたいプロジェクトを開いて `/hirai-lite:init` と入力します。
   何が置かれたかが表示されます。
   **このとき、ファイルを作るためのコマンドを実行してよいか聞かれます。** 許可しないとファイルが置かれません（→ [インストール中に聞かれること](#インストール中に聞かれること)）。

3. いったんセッションを閉じて開き直します。これで準備完了です。

うまくいったか確かめる: 画面下部に「mode: 確認あり」と出ていれば OK です。

## インストール中に聞かれること

上の 3 ステップの間に、確認の画面がいくつか出ます。どの画面で何を答えればよいかを順に書きます。

⚠️ **表示は Claude Code のバージョンや環境によって変わることがあります。** ここに書いたのは Claude Code 2.1.247 で実際に確かめた内容です。見覚えのない画面が出たときは、文面を読んでから判断してください。

### 1. マーケットプレイスを追加するとき

`/plugin marketplace add thirai-classlab/hirai-method-lite` は、配布元の一覧を登録するだけです。この時点では何もインストールされません。

ターミナルから同じ操作（`claude plugin marketplace add …`）を試したときは確認は出ず、`✔ Successfully added marketplace: hirai-lite` とだけ表示されました。**画面の中から `/plugin` で実行した場合に確認が出るかは未確認です。** 出た場合は、追加先が `thirai-classlab/hirai-method-lite` になっていることを確かめてから進めてください。

なお公式ドキュメントには「プラグインとマーケットプレイスは、あなたの権限で任意のプログラムを実行できる。信頼できる配布元のものだけを入れること」という注意書きがあります（[Security](https://code.claude.com/docs/en/discover-plugins.md)）。

### 2. プラグインを入れるとき — 入れる範囲を選ぶ

`/plugin install hirai-lite@hirai-lite` を実行すると詳細画面が開き、**どの範囲に入れるかを選ぶ**よう求められます。ここは必ず答える必要があります。

| 選択肢 | 意味 |
|---|---|
| **User** | このパソコンの、自分が開くすべてのプロジェクトで使う |
| **Project** | このリポジトリを触る人全員で使う（`.claude/settings.json` に記録され、共有される） |
| **Local** | このリポジトリで、自分だけが使う |

迷ったら **User** を選んでください。ひとりで使う分にはこれがいちばん素直です。

同じ画面に、このプラグインが持ち込むもの（コマンド 12 個 / エージェント 3 個 / hooks 2 本 / MCP サーバー 2 つ）と、常時かかる容量の見積もりが出ます。入れる前に中身を確かめられます。

選び終わると `Plugin is now active.`（もう使えます）か `Run /reload-plugins to activate.`（`/reload-plugins` と入力すると使えます）のどちらかが出ます。後者なら、そのまま `/reload-plugins` を実行してください。

（ターミナルから `claude plugin install …` を実行した場合は、この選択画面は出ずに User 範囲へ入ります。範囲を指定したいときは `--scope` を付けます。）

### 3. hooks について — 専用の確認は出ません

このプラグインは hooks を 2 本含みます（セッション開始時の 1 行表示と、容量が増えたときの警告）。**hooks だけを対象にした承認画面は出ません。** 公式ドキュメントにもその記載はなく、実際に入れたときにも出ませんでした。

hooks は入れた時点で動きます。中身を確かめたいときは `hooks/session-start.sh` と `hooks/context-budget.sh` を読んでください。どちらも短いシェルスクリプトです。

### 4. MCP サーバー（serena / context7）について

**このプラグインが配る 2 つは、承認なしで自動的につながります。** 実際に入れて `claude mcp list` で確かめたところ、こう表示されました。

```
plugin:hirai-lite:serena: uvx … - ✔ Connected
plugin:hirai-lite:context7: npx … - ✔ Connected
```

名前の頭に `plugin:hirai-lite:` が付いているのが目印です。

いっぽう、**開いたリポジトリの直下に `.mcp.json` が置いてある場合は、そちらのサーバーについて別途「つないでよいか」を聞かれます。** これはプラグインとは無関係で、そのリポジトリが持ち込む設定です。MCP サーバーは外部のプログラムを起動するため、確認が入ります。

答えないままにすると `⏸ Pending approval` と表示され、**そのサーバーだけが使えません。** プラグイン側の 2 つや、ルール・コマンド・画面下部の表示には影響しません。

- いまの状態を見る: `claude mcp list`
- 答え直す: `claude mcp reset-project-choices`（選択が消え、次回また聞かれます）
- 個別に切る: `/mcp`

`serena` は `uvx`（[uv](https://docs.astral.sh/uv/)）、`context7` は `npx`（Node.js）が必要です。無い場合は該当サーバーが「つながらない」と出るだけで、他の機能はそのまま動きます。

### 5. `/hirai-lite:init` を実行するとき — コマンドの実行許可

`/hirai-lite:init` は、ファイルをコピーしてフォルダを作るために、シェルコマンド（`cp` `mkdir` `python3` など）をいくつか実行します。そのたびに実行してよいかを聞かれます。

| 選択肢 | 意味 |
|---|---|
| はい | 今回だけ実行する |
| はい、今後は確認しない | 同じコマンドを次回から聞かずに実行する |
| いいえ | 実行しない |

`/init` は既存のファイルを 1 つも上書きしません。許可しなかった手順は飛ばされ、そのぶんファイルが置かれないままになります。最後に何を置いたかの報告が出るので、足りなければもう一度 `/hirai-lite:init` を実行してください。

### 後から変えたいとき

| やりたいこと | 入力するもの |
|---|---|
| プラグインを止める / 消す | `/plugin` →「Installed」タブ |
| MCP サーバーを個別に切る | `/mcp` |
| `.mcp.json` の承認をやり直す | `claude mcp reset-project-choices` |
| コマンドの実行許可を見直す | `/permissions` |

### 確認できなかったこと

- 画面の中から `/plugin marketplace add` / `/plugin install` を実行したときの表示そのもの（対話画面のため、ターミナルからの実行結果と公式ドキュメントの記述で代用しています）
- フォルダを信頼するか尋ねる画面が出る条件。このプラグインが配る安全設定は「禁止」と「確認」だけで、公式ドキュメントによればこの 2 つは信頼の確認を待たずに効きます

## どこに入れるか（このプロジェクトだけ / 全プロジェクト）

置き場所は 2 つあります。ふつうは上のままで大丈夫です。

| やり方 | 入力するもの | 置かれる場所 | 効く範囲 |
|---|---|---|---|
| このプロジェクトだけ（既定） | `/hirai-lite:init` | いま開いているフォルダの `.claude/` | このプロジェクトだけ |
| 全プロジェクト共通 | `/hirai-lite:init user` | ホームの `~/.claude/` | このパソコンで開くすべてのプロジェクト |

全プロジェクト共通に入れると、決まりごと・安全設定・進め方の設定・画面下部の表示がどこでも効きます。ただし**やることの一覧表・設計メモの置き場・困ったことの記録帳は作られません**。これらはプロジェクトごとの中身なので、共通の場所に置いても意味がないためです。

⚠️ **両方には入れないでください。** 同じ決まりごとが 2 か所にあると、まったく同じ文章が 2 回読み込まれ、AI が一度に読める容量を無駄に使います（実測で約 2,900 が約 5,800 になり、このハーネスが自分に課している上限 3,000 を超えます）。`/hirai-lite:init` はもう一方の場所に同じ名前のファイルを見つけると警告を出すので、案内どおりどちらか一方を消してください。

**確認できたこと / できなかったこと**（実装の根拠）:

- ホームの `~/.claude/rules/` が読み込まれることは公式ドキュメントに明記があります。[memory.md](https://code.claude.com/docs/en/memory.md) の「User-level rules」: *Personal rules in `~/.claude/rules/` apply to every project on your machine.* / *User-level rules are loaded before project rules, giving project rules higher priority.*
- 一方、**`paths:` を書いたファイルがホーム側でも「そのファイルを開いた時だけ読まれる」のかは、公式ドキュメントに明記がありません**（`paths:` の説明はプロジェクト側 `.claude/rules/` の節にあり、ホーム側の節では触れられていない）。全プロジェクト共通に入れた場合、必要なときだけ読まれるはずの 3 件が常に読まれる可能性がある点は**未確認**です。気になる場合はこのプロジェクトだけに入れる既定の使い方を選んでください。

## mode（進め方）とは

作業の進め方の設定で、値は 2 つだけ。`.claude/mode.yml` に入っていて `/mode normal` / `/mode loop` で切り替える。画面下部の表示にも出る。

| 値 | 表示 | 挙動 |
|---|---|---|
| `normal`（既定） | 確認あり | 重要な分かれ道で確認しながら進む |
| `loop` | 自動 | 確認を求めず最後まで自動で進む（止めたいときは「stop」と伝える） |

## ultracode について

`/hirai-lite:init` は `templates/settings.json` を配置するため、**導入先で ultracode が既定で有効になる**（`"ultracode": true`）。ultracode は xhigh 推論と、タスクごとの自動 workflow オーケストレーションを常時 on にする設定で、**通常運用よりトークン消費が大きい**。従量課金で使う場合はコスト増を見込むこと。

無効化するときは、導入先の `.claude/settings.json` から `ultracode` キーを削除するか `false` にする。プラグイン側の素材を編集する必要はない。

併せて `"workflowSizeGuideline": "small"` を置き、1 workflow あたりのエージェント数を 5 未満に抑えている。根拠は実測（2026-08-21）。同時 4 subagent を起動した際、3 件が 600 秒無進捗で stall し 1 件が API 接続断となり成果物はゼロだった。同時 2 件へ落としたところ 5 件連続で成功した。並列度を上げるほど stall 率が上がるため、既定は `small` とする。

## statusline について

`/hirai-lite:init` は `scripts/statusline.sh` と `scripts/tasks-path.sh` を配置先の `.claude/` へ複製し、`templates/settings.json` の `statusLine.command`（`bash "${CLAUDE_PROJECT_DIR:-.}/.claude/statusline.sh"`）から呼ぶ。表示は 1 行で `<model> | ctx <N>% ・5h <N>% ・7d <N>% | mode: <進め方> | <branch> | やること <N>`。進め方は値そのものを日本語で出す（`normal` → `確認あり` / `loop` → `自動`、未知の値はそのまま）。実例: `Claude Opus 4.5 | ctx 12% ・5h 3% ・7d 8% | mode: 確認あり | feat/rate-limit | やること 4`。

全プロジェクト共通（`/hirai-lite:init user`）に入れた場合だけは、`statusLine.command` を `$HOME` を展開した絶対パス（例: `bash "/home/you/.claude/statusline.sh"`）に書き換える。`${CLAUDE_PROJECT_DIR}` は開いているプロジェクトごとに変わるため、全プロジェクト共通の設定からは使えないため。進め方（`mode.yml`）はプロジェクト側を先に見て、無ければホーム側を見る。

`.claude/statusline.sh` と `.claude/tasks-path.sh` の 2 本は**プラグイン所有**であり、`/update` で配布版に置き換わる（中身を変えていた場合は `.bak` に退避してから置き換える）。`.claude/rules/` `settings.json` `mode.yml` `CLAUDE.md` 台帳は利用者所有で、更新では触らない。

プラグイン側のパスを直接指さないのは、**`${CLAUDE_PLUGIN_ROOT}` が settings.json では展開されないため**（[公式仕様](https://code.claude.com/docs/en/plugins-reference.md)の「Where `${CLAUDE_PLUGIN_ROOT}` is Available」に statusLine と project settings は含まれない）。手で配線する場合は `.claude/settings.json` に上記 `statusLine` ブロックを足すか、絶対パスを書く。不要なら `statusLine` キーを消す。

## 同梱している MCP サーバー（外部ツール接続）

プラグインの `.mcp.json` で 2 つ配る。インストールした時点で有効になり、`/init` の配置対象ではない。

| 名前 | 用途 | 起動方法 | 必要なもの |
|---|---|---|---|
| `serena` | コードの検索とシンボル操作 | `uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant` | [uv](https://docs.astral.sh/uv/)（`uvx`） |
| `context7` | ライブラリ公式ドキュメントの取得 | `npx -y @upstash/context7-mcp@latest` | Node.js（`npx`） |

- **API キーは書かない。** `context7` は `CONTEXT7_API_KEY` 環境変数を参照するだけで、未設定でも動く（レート制限が緩くなる有料キーを持っている人だけが設定する）。
- **起動できなくてもセッションは壊れない。** `uvx` や `npx` が無い環境では該当サーバーが接続失敗として表示されるだけで、rules / commands / hooks / 画面下部の表示はそのまま動く。使わないなら `/plugin` の設定でそのサーバーを無効にする。

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

2. **rules を配置する** — 対象リポジトリを開いて `/hirai-lite:init` を実行する（全プロジェクト共通に入れるなら `/hirai-lite:init user`）。`rules/*.md` を `.claude/rules/` へ、`templates/settings.json` の permissions と `statusLine` を `.claude/settings.json` へ、`templates/mode.yml` を `.claude/mode.yml` へ、`scripts/statusline.sh` と `scripts/tasks-path.sh` を `.claude/` へ配置し、台帳・draft dir・事故記録・`.claude/rules-archive/` を作る。既存ファイルは上書きしない。

   `docs/` を持つリポジトリでは台帳 / draft / 事故記録が `docs/` 配下（`docs/tasks/list.md` `docs/draft/` `docs/rules-reference/incidents.md`）に、持たないリポジトリでは `.claude/` 配下（`.claude/tasks/list.md` `.claude/draft/` `.claude/rules-reference/incidents.md`）に作られる。`rules/core.md` と `rules/_meta.md` はこの解決順をそのまま書いているため、`docs/` 無しのリポジトリでも存在しないパスを指さない。`user` 指定時は台帳 / draft / 事故記録を作らず、`statusLine.command` だけ絶対パスへ書き換える。

3. **CLAUDE.md を埋める** — このリポジトリの `CLAUDE.md` を雛形として対象リポジトリのルートに置き、`<...>` プレースホルダを実値（概要 / Tech Stack / Commands）に置換する。行動規範は書かない。それは `.claude/rules/core.md` の担当。

4. **ロード検証** — **`/init` の次に開くセッション**で行う（rules は起動時に読まれるため、`/init` を実行したセッション内では確認できない。`/init` の終了条件にも含めていない）。新しいセッションを開き、T0 の 3 ファイルが載っていること、T1 が `paths:` 該当ファイルを開くまで載らないことを確認する。想定と違えば frontmatter を直す。

更新は `/update`（`/plugin update` → `/hirai-lite:init` で rules を再配置 → プラグイン所有の `.claude/statusline.sh` と `.claude/tasks-path.sh` を配布版に入れ替え）。

## このリポジトリの構成

| パス | 中身 |
|---|---|
| `.claude-plugin/plugin.json` | プラグインのマニフェスト（`VERSION` と同じ版を書く） |
| `.claude-plugin/marketplace.json` | 自分自身を 1 エントリとして指すマーケットプレイス定義 |
| `.mcp.json` | 同梱する MCP サーバー 2 つの定義（キーは環境変数参照のみ） |
| `agents/` | サブエージェント 3 個（MIT、出典は `NOTICE.md`） |
| `commands/` | スラッシュコマンド 12 個 |
| `hooks/` | `hooks.json` + SessionStart / UserPromptSubmit の 2 本 |
| `rules/` | **プラグインは読まない。** `/init` が配置先の `.claude/rules/` へ配る素材 |
| `scripts/` | hook / statusline が source する共通ライブラリ + `/init` の二重ロード検査 |
| `templates/` | `settings.json` / `mode.yml` / draft / task の雛形 |
| `tests/smoke.sh` | 自己検証 10 case（予算監査を含む） |

自己テストは `claude --plugin-dir .` でこのリポジトリ自身をプラグインとして読ませて行う。

## rules 3 層 + 退避層

Claude Code は `.claude/rules/*.md` を再帰的に発見する。`paths:` frontmatter を持つファイルは**該当ファイルを読んだ時にだけ**ロードされ、持たないファイルは**起動時に常時**ロードされる（[公式仕様](https://code.claude.com/docs/en/memory.md)）。この挙動をそのまま層設計に使う。

| 層 | 置き場所 | ロード条件 | 予算 | 入れてよいもの |
|---|---|---|---|---|
| **T0 常時** | `CLAUDE.md` / `.claude/rules/*.md`（frontmatter 無し） | 毎セッション | **合計 3,000 tokens** | 全作業に例外なく効く規範のみ。既定では入れない |
| **T1 条件** | `.claude/rules/*.md`（`paths:` あり） | 該当ファイルを触った時 | 1 file 2,000 tokens | ドメイン規範（タスク運用 / コード / インフラ） |
| **T2 参照** | `docs/rules-reference/**`（`docs/` が無ければ `.claude/rules-reference/**`） | AI が明示 Read した時のみ | 無制限 | 背景・事故記録・詳細手順・過去の経緯 |
| **T3 退避** | `.claude/rules-archive/**` | ロードしない | — | 失効したルール（履歴として保持） |

T2 を `.claude/rules/` の**外**に置くのは意図的。`rules/` の中に置くと `paths:` を書き忘れた瞬間に T0 へ昇格してしまう。物理配置でこの事故を防いでいる。同じ理由で T0 から T2 へのポインタは張らない（張ると T0 が背景説明で膨らむ）。ポインタは T1 から張る。

同じ理由で **T0 の二重計上も禁止**する。`~/.claude/rules/` と `<project>/.claude/rules/` の両方に同じファイルがあると T0 は倍（実測 2,890 → 5,780 tokens）になり、3,000 の上限を無言で割る。`/init` は反対側の scope を毎回検査し、重なりがあれば警告を出す（`scripts/scope-check.sh`、`tests/smoke.sh` case 4 で検証）。

`@import` は使わない。CLAUDE.md 展開時に常時展開されるため、context 削減効果がゼロどころか純増になる。

## 設計思想

**常時ロードされるコンテキストの総量に予算を置き、ルールの追加をパイプライン化する**ことだけを設計の中心に据えている。

前身の `hirai-method` は 1,629 file / shell 54,373 行まで肥大し、guard 36 個中 10 個が「ハーネス自身の開発を妨げるため」という理由で無効化されていた。原因は個々のルールではなく、**ルールを追加するときに置き場所・分量・表現・重複を検討する工程が無かった**ことにある。本リポジトリはその 1 点を構造で解く。

**1. 既定は「入れない」。** T0 は 3,000 tokens の hard cap を持つ。追加は容易で削除は困難、という非対称を予算で打ち消す。上限に達した後の追加は、既存 1 件を T1/T2 へ降格するまで通らない。

**2. 事故 2 回目で初めてルール化する。** 1 回目は事故記録（`docs/rules-reference/incidents.md`、`docs/` が無ければ `.claude/rules-reference/incidents.md`）に 1 行記録するだけ。推測による予防ルールを禁じる。前身のハーネスでは、規範の多くが発火実績ゼロの先回りだった。

**3. 機械強制は不可逆操作のみ。** `settings.json` の `deny` / `ask` と hook で止めてよいのは「間違えたら戻せない」操作だけ。無害な操作を止める guard は速度を削り、やがて無効化されて規範と実挙動の乖離を生む。

**4. メタルールが最初に適用される対象は、メタルール自身。** 「機械強制は不可逆操作のみ」に従えば、予算監査そのものを hook にはできない（予算超過は不可逆ではない）。よって予算チェックと層違反検出は `tests/smoke.sh` の case として実装し、commit 前に走らせる。結果 hook は 2 本に収まる。

**5. ゼロから始めて、必要になったものだけ足す。** 前身の 1,629 file から選び出すのではない。実プロジェクトで使い、不足したものだけを `/add-rule` のパイプライン経由で戻す。何が本当に必要かは、削ってみないと分からない。

## ルールを追加するとき

`rules/_meta.md`（配置先では `.claude/rules/_meta.md`）に 8 条とパイプラインがある。要点だけ:

- 追加はユーザー承認必須。削除は承認不要（削除の摩擦を追加より低くする）
- 1 ルール 1 事象・3 行以内。書式は `- **<名前>**: <肯定形 1 行> ／ 例: <1 つ> ／ 失効: <条件>`
- 禁止語彙: `適切に` / `必要に応じて` / `可能な限り` / `十分に` / `慎重に`
- 四半期ごとに点検し、発火 0 のルールは `.claude/rules-archive/` へ退避する（`/rules-audit`）
