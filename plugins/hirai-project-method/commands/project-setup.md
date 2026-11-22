---
description: このリポのやることを載せる GitHub Project を立ち上げる。計画を見せて承認を取ってから、Project の作成（またはテンプレートの複製）・リポへの紐づけ・項目（Status 8 値・種別・着手順・承認カードを写す「ひとこと」「推奨」）・ビュー 8 枚を自動で入れ、画面でしかできない作業を URL つきで案内する。すでにあれば足りないものだけを足す。
argument-hint: "[--title <名前>] [--from-template <owner>/<番号>]"
disable-model-invocation: true
---

# /project-setup [--title <名前>] [--from-template <owner>/<番号>]

`/hirai-lite:init` のあとに 1 回だけ使う。中身は `hirai-task setup`（`scripts/hirai_project_setup.py`）。**引数なしの `hirai-task setup` は計画を出すだけで、GitHub に何も書かない。** 書き込むのは `--apply` を付けたときだけ。手順の本体と値は `docs/rules-reference/project-setup.md`（無ければプラグイン同梱の同名ファイル）。

`command -v hirai-task` が無ければ「hirai-task が見つからない（PATH に入っていない）」と報告して終了する。

## 1. 計画を取る（読むだけ）

```bash
hirai-task setup --json $ARGUMENTS
```

`--title` の名前に空白があれば、引用符で囲んで渡す（`--title "営業 CRM"`）。囲まないと分かれて exit 2 になる。

| exit code | 意味 | すること |
|---|---|---|
| 0 | 計画が出た | 2 へ |
| 1 | gh が無い・未ログイン・token に `project` の権限が無い・gh が失敗した | 出力にある直し方（`gh auth login -s project` / `gh auth refresh -s project`）をそのまま伝えて止まる。打つのは利用者 |
| 2 | 引数の誤り・リポが決まらない・紐づいた Project が 2 件以上で決まらない | 出力の候補を見せ、どれを使うか聞く。決まったら `HIRAI_TASK_PROJECT=<番号>` を付けて 1 からやり直す |

## 2. 承認を取る（書くものがあるときだけ）

`steps` が 0 件なら書くものは無い。承認を取らずに 4 へ進む。

1 件以上なら、**承認を求めるときは承認カード**（決めること・推奨 / 目的 / 位置 / 承認すると / しないと / 注意 / 詳しく）**を本文に示してから** `AskUserQuestion`（`承認する` / `承認しない` / `修正して提案し直す`）**を出す。型と記入例**: `docs/rules-reference/approval-template.md`（プロジェクトに無ければプラグイン同梱の同名ファイル。`AskUserQuestion` が使えないときの平文の出し方も同じファイル）。カードのあとに `steps` の全文（各行の説明とコマンド）を置く。

- **決めること**: 「このリポのやることを載せる Project を作る（足りないものを足す）か」。推奨は承認する
- **承認すると**: `steps` の件数と中身の要約（Project の名前と、個人か組織か）。既存の選択肢・項目・ビューは消さない・名前を変えない
- **注意**: GitHub に Project・項目・ビューが増え、消すのは画面での手作業
- Project を新しく作るときは、同じ `AskUserQuestion` で名前（`--title`。既定はリポ名）とテンプレートの有無（`--from-template <owner>/<番号>`。組織にテンプレートの Project があれば推奨）も聞く。答えで引数が変わったら、1 の計画を取り直してから承認を取り直す

## 3. 書き込む（承認されたときだけ）

```bash
hirai-task setup --apply $ARGUMENTS
```

exit 0 なら、行った件数を 1 行で報告する。exit 1 なら、出力の末尾 20 行を出して止まる（途中まで作ったものは消さない）。Project を作った直後に落ちたときは、出力に `HIRAI_TASK_PROJECT=<番号>` が出る。続きはそれを付けて 1 から回す（付けずに回すと、まだ紐づいていない Project を見つけられず、もう 1 つ作る計画になる）。

## 4. 画面でしかできない作業を頼む

3 の `--apply` の出力の `checklist`（書き込みが無かったときは 1 の計画のもの。何を・どこで（URL）・どの値で・いま）を表のまま出し、利用者に画面で行ってもらう。組込の自動化の On と、全体ビューの階層表示・wave の並びは API では設定できない。承認ビューの「ひとこと」「推奨」の列は、3 の `--apply` が API で出す（計画の手順「ビュー『承認』に列 ひとこと・推奨 を出す」。この 2 列があれば、本文を開かずにスマートフォンでも承認できる）。組織の Project なら `templateHint`（テンプレートにする 1 行）も添える。

## 5. 確かめる

`docs/rules-reference/project-setup.md` の 8 章で確かめる。少なくとも `hirai-task ready` が exit 0 で終わる（空でもよい）ことを実行して見せる。そのあと `/hirai-project-method:board` で全体像が出ることを 1 回見せる。すでに承認待ちの feature があるリポでは `hirai-task card --lint` を回し、カードの無い feature の件数を伝える（カードを書くのは別の作業。書いたら `hirai-task card <番号> --sync`）。

## 判定できる終了条件

- `hirai-task setup --json` を引数なしで回し直したとき（1 で `HIRAI_TASK_PROJECT` を付けたなら同じものを付けて）、`steps` が 0 件。
- `hirai-task ready` が exit 0。
- `checklist` の表を利用者に出した（画面の作業が済んだかは利用者の返事で確かめる）。
