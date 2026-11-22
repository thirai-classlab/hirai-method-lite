---
description: GitHub Project の全体像と、どこで何件止まっているか（承認待ち・判断待ち・依存待ち・保留・レビュー中・着手できない理由・人の作業）と、あなたの番（承認・判断・人の作業のカードの決めることと推奨）を出す。進捗を聞かれたとき（スマートフォンから Remote Control で聞かれたときも）に使う。読むだけで、publish を付けたときだけ進捗用 issue の本文を書く。
argument-hint: "[text [wave|feature|task <n>] | html | refresh | publish <issue番号>]"
---

# /board [text [wave|feature|task <n>] | html | refresh | publish <issue番号>]

GitHub Project のやること（wave → feature → task）を `hirai-task board` で読み、**どこで何件止まっているか**を出す。正本は GitHub の issue と Project。着手できるかの最終判断は `hirai-task ready` が正で、ここは全体を見るための表示。

`command -v hirai-task` が無ければ「hirai-task が見つからない（PATH に入っていない）」と報告して終了する。

## 引数で分ける

| 引数 | 実行するもの | 会話に出すもの |
|---|---|---|
| なし | `hirai-task board --summary` と `hirai-task board` | `--summary` の出力をそのまま。最後に 1 行 `詳しい版（依存図・表）: <HTML のパス>（PC のブラウザで開く）` |
| `text` / `text wave <n>` / `text feature <n>` / `text task <n>` | `hirai-task board --text`（`--wave <n>` / `--feature <n>` / `--task <n>`。task はその行に `←` が付く） | 出力をそのまま（wave → feature → task の木） |
| `html` | `hirai-task board` | 出力（書いたパスと 1 行の要約）をそのまま。macOS なら `open <パス>` で開けることを添える。既定の置き場は git の管理ディレクトリの下の `hirai-task/board.html`（作業ツリーを汚さない） |
| `refresh` | 上の「なし」に `--refresh` を付ける | 「なし」と同じ |
| `publish <issue番号>` | `hirai-task board --publish <issue番号>` | 書き込んだ issue の URL 1 行 |

- **出力を加工しない。** 件数を数え直したり、言い換えたりしない（数字の出どころが 2 つになる）。足すのは最後の 1 行だけ。
- **`publish` は引数で頼まれたときだけ実行する。** GitHub の issue の本文を書く唯一の操作で、目印（`<!-- hirai-board:start -->` と `<!-- hirai-board:end -->`）の間だけを置き換える。控えが新しくても取り直してから書く。自分の判断で publish しない。
- **あなたの番**は、承認待ちの feature・判断待ち・`[User]` の作業・承認待ちの `[操作]`（操作の承認）を、カード（`docs/rules-reference/approval-template.md`）の「決めること」と「推奨」（判断カードは期限も）で出す。カードの無い行は「カード無し」、承認しても子の task が動かない feature は「動かない（理由）」と出る。カードの抜けの一覧は `hirai-task card --lint`。
- 取得は 10 分のあいだ控え（git の管理ディレクトリの下の `hirai-task/gh-board-cache.json`）を使い、GitHub に問い合わせない。今すぐ取り直すときは `refresh`。行が多い Project は取得に数十秒かかる（1,471 行で約 34 秒）。

## 止まったとき

| exit code | 意味 | すること |
|---|---|---|
| 0 | 出せた | 上の表のとおり出す |
| 1 | 取得に失敗した（gh の失敗・認証・レート制限・打ち切り）、またはリポに Project が紐づいていない（標準エラーが `Project: 無し`） | `Project: 無し` なら、利用者が `/hirai-project-method:project-setup` を打てば立ち上げられることを 1 行で伝える。それ以外は標準エラーの末尾 5 行を出し、`refresh` で取り直せることを 1 行添える。どちらも「0 件」とは言わない |
| 2 | 呼び方の誤り、または紐づいた Project が 2 件以上で決まらない | 標準エラーをそのまま出す |

## スマートフォンから聞かれたとき

Claude アプリ（Remote Control）からは、文で「進捗を見せて」と届くことが多い。そのときも引数なしと同じにする。`--summary` は 1 行 40 字前後・表は 2〜3 列に収めてあるので、そのまま出す。HTML のパスはスマートフォンでは開けないので、最後の 1 行は `詳しい版は PC で /hirai-project-method:board html` に替える（手元の端末から聞かれたか分からないときは、パスの行のままでよい）。

## 判定できる終了条件

- 引数なし・`refresh` のとき: `hirai-task board --summary` が exit 0 で、その出力が会話にそのまま出ている。
- `publish` のとき: `hirai-task board --publish <n>` が exit 0 で、`gh issue view <n> --json body --jq .body` に `<!-- hirai-board:start -->` が 1 回だけある。
