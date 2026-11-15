---
name: github-project
description: GitHub Project でやること（wave・feature・task の issue と Status）を読む・書くとき、hirai-task や gh issue を使う前に読む。正本・3 段・Status 8 値・着手可は人だけ・完了条件・書き込みはメイン専任の決まり。
---

# GitHub Project でのやること管理

`rules/tasks.md`（T1）の `paths:` は `docs/` の書類にしか当たらず、`hirai-task` と `gh` だけで進む作業では読まれない。そのため GitHub Project の形の規範はこの skill に置く（v2.7.0 で `tasks.md` から移した）。

- **正本は Project**: メインエージェントは、やることの正本を GitHub の issue と Project に置き、着手前に `gh issue view <n>` で本文と依存を読む ／ 例: `hirai-task ready` で着手できる issue を出す ／ 失効: 外部トラッカー（Asana / Jira）に正本を移したとき
- **3 段**: メインエージェントは、仕事を wave → feature → task の 3 段（項目「種別」と sub-issue）で組み、task は PR 1 本で閉じる粒度にする ／ 例: PR の本文に `Closes #12` を書く ／ 失効: なし
- **Status は 8 値**: メインエージェントは、Status を次の 8 値で扱う。承認待ち / 着手可 / 判断待ち / 依存待ち / 進行中 / レビュー中 / 完了 / 保留。レビュー中と完了は原則として組込の自動化が動かす。自動化が動かない PR（既定の branch 以外向け）のときだけ `hirai-task review <n>` で レビュー中 にする ／ 例: 既定の branch 向けの PR は出せばレビュー中になる ／ 失効: なし
- **feature の着手可は人だけ**: メインエージェントは、feature の着手を人がボードで「着手可」にするまで待ち、自分では動かさない ／ 例: feature が着手可で、先の wave が出ていて、未完了の blocked by が無ければ、子の task はあとから足したものも `hirai-task start` で着手してよい（feature が承認待ちの間は呼ばない） ／ 失効: なし
- **完了条件は検証可能に**: メインエージェントは、issue の完了条件を再現コマンドか観察可能な事実で書く ／ 例: 「ログイン E2E が green」「`GET /health` が 200 を返す」 ／ 失効: なし
- **書き込みはメイン専任**: サブエージェントは issue を読むだけにし、Status や本文の変更は結果報告でメインに返す ／ 例: 報告に「#12 完了、Status を 完了 へ」と書く ／ 失効: なし

## 承認の場所とカード（v2.8.0）

- **着手の承認は承認ビューで受ける**: メインエージェントは、feature の本文の先頭に承認カードを置いて `hirai-task card <n> --sync` で項目「ひとこと」「推奨」に写し、会話では承認を求めず承認ビューの件数を案内する ／ 例: 「承認ビューに 3 件あります（推奨: 承認 2・見送り 1）」 ／ 失効: 承認を別の場（会議・外部の道具）に移したとき
- **PR の取り込みは着手の承認ではない**: メインエージェントは、承認待ちの feature の子の task の PR を出さず、先に承認ビューで承認を受ける ／ 例: feature #12 が承認待ちなら、その子の PR を作らずに #12 のカードを出す ／ 失効: なし
- **箱をカードに合わせる**: メインエージェントは、判断待ちには判断カード（選択肢・推奨・期限）のある問いだけを置き、`[User]`・`[操作]` の task には人の作業カードを置く ／ 例: 外部の申込を待つ issue は判断待ちでなく `[User]` にする ／ 失効: なし
- **答えが出た判断はその日に閉じる**: メインエージェントは、判断待ちの問いに答えが出たら、出どころ（会議・PR・ADR）を本文に書いてその日のうちに閉じ、止めていた issue を `hirai-task unblocked` で確かめる ／ 例: 「PR #46 で決着。案 A を採用」と書いて閉じる ／ 失効: なし
- **カードを見回る**: メインエージェントは、会話の最初に `hirai-task card --lint` を回し、カードの無い・形の崩れた承認待ち・判断待ち・人の作業を直してから作業に入る ／ 例: 「承認待ち 2 件にカードが無い → 書いて --sync」 ／ 失効: なし

## 関連

- 立ち上げ・Status の動かし方・ビュー: `docs/rules-reference/project-setup.md`（無ければプラグイン同梱の同名ファイル）。新しいリポでは利用者に `/hirai-lite:project-setup` を打ってもらう（Claude からは呼べない）
- 全体像と、どこで何件止まっているか: `/hirai-lite:board`（`hirai-task board`）
- 承認を求めるときの型（承認カード・判断カード・人の作業カード）: `docs/rules-reference/approval-template.md`
- 進め方の用語: `docs/rules-reference/glossary.md`（案件を知らない人に渡すとき）
