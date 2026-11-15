---
name: github-project
description: GitHub Project でやること（wave・feature・task の issue と Status）を読む・書くとき、hirai-task や gh issue を使う前に読む。正本・3 段・Status 8 値・着手可は人だけ・完了条件・書き込みはメイン専任の決まり。
---

# GitHub Project でのやること管理

`rules/tasks.md`（T1）の `paths:` は `docs/` の書類にしか当たらず、`hirai-task` と `gh` だけで進む作業では読まれない。そのため GitHub Project の形の規範はこの skill に置く（v2.7.0 で `tasks.md` から移した）。

- **正本は Project**: メインエージェントは、やることの正本を GitHub の issue と Project に置き、着手前に `gh issue view <n>` で本文と依存を読む ／ 例: `hirai-task ready` で着手できる issue を出す ／ 失効: 外部トラッカー（Asana / Jira）に正本を移したとき
- **3 段**: メインエージェントは、仕事を wave → feature → task の 3 段（項目「種別」と sub-issue）で組み、task は PR 1 本で閉じる粒度にする ／ 例: PR の本文に `Closes #12` を書く ／ 失効: なし
- **Status は 8 値**: メインエージェントは、Status を次の 8 値で扱う。承認待ち / 着手可 / 判断待ち / 依存待ち / 進行中 / レビュー中 / 完了 / 保留。レビュー中と完了は原則として組込の自動化が動かす。自動化が動かない PR（main 以外向け）のときだけ `hirai-task review <n>` で レビュー中 にする ／ 例: main 向けの PR は出せばレビュー中になる ／ 失効: なし
- **feature の着手可は人だけ**: メインエージェントは、feature の着手を人がボードで「着手可」にするまで待ち、自分では動かさない ／ 例: feature が着手可で、先の wave が出ていて、未完了の blocked by が無ければ、子の task はあとから足したものも `hirai-task start` で着手してよい（feature が承認待ちの間は呼ばない） ／ 失効: なし
- **完了条件は検証可能に**: メインエージェントは、issue の完了条件を再現コマンドか観察可能な事実で書く ／ 例: 「ログイン E2E が green」「`GET /health` が 200 を返す」 ／ 失効: なし
- **書き込みはメイン専任**: サブエージェントは issue を読むだけにし、Status や本文の変更は結果報告でメインに返す ／ 例: 報告に「#12 完了、Status を 完了 へ」と書く ／ 失効: なし

## 関連

- 立ち上げ・Status の動かし方・ビュー: `docs/rules-reference/project-setup.md`（無ければプラグイン同梱の同名ファイル）。新しいリポでは利用者に `/hirai-lite:project-setup` を打ってもらう（Claude からは呼べない）
- 全体像と、どこで何件止まっているか: `/hirai-lite:board`（`hirai-task board`）
- 承認を求めるときの型: `docs/rules-reference/approval-template.md`
