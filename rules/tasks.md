---
paths:
  - "docs/tasks/**"
  - "docs/draft/**"
  - ".claude/tasks/**"
  - ".claude/draft/**"
---
# タスク運用

対象: やることの管理（GitHub Project の形）と設計 draft を触る作業。立ち上げ・Status・ビューの詳細は `docs/rules-reference/project-setup.md`（無ければプラグイン同梱の同名ファイル）。台帳（`list.md`）の形のリポは `docs/rules-reference/task-ledger.md` に従う。

## GitHub Project の形

- **正本は Project**: メインエージェントは、やることの正本を GitHub の issue と Project に置き、着手前に `gh issue view <n>` で本文と依存を読む ／ 例: `hirai-task ready` で着手できる issue を出す ／ 失効: 外部トラッカー（Asana / Jira）に正本を移したとき
- **3 段**: メインエージェントは、仕事を wave → feature → task の 3 段（項目「種別」と sub-issue）で組み、task は PR 1 本で閉じる粒度にする ／ 例: PR の本文に `Closes #12` を書く ／ 失効: なし
- **Status は 8 値**: 承認待ち / 着手可 / 判断待ち / 依存待ち / 進行中 / レビュー中 / 完了 / 保留。レビュー中と完了は原則として組込の自動化が動かす。自動化が動かない PR（main 以外向け）のときだけ `hirai-task review <n>` で レビュー中 にする ／ 例: main 向けの PR は出せばレビュー中になる ／ 失効: なし
- **feature の着手可は人だけ**: メインエージェントは、feature の着手を人がボードで「着手可」にするまで待ち、自分では動かさない ／ 例: feature が着手可で、先の wave が出ていて、未完了の blocked by が無ければ、子の task はあとから足したものも `hirai-task start` で着手してよい（feature が承認待ちの間は呼ばない） ／ 失効: なし
- **完了条件は検証可能に**: メインエージェントは、issue の完了条件を再現コマンドか観察可能な事実で書く ／ 例: 「ログイン E2E が green」「`GET /health` が 200 を返す」 ／ 失効: なし
- **書き込みはメイン専任**: サブエージェントは issue を読むだけにし、Status や本文の変更は結果報告でメインに返す ／ 例: 報告に「#12 完了、Status を 完了 へ」と書く ／ 失効: なし

## 設計 draft

- **設計の起点は draft**: 新機能・仕様変更は `docs/draft/<slug>.md` に設計を起こす ／ 例: `docs/draft/login-rate-limit.md` ／ 失効: なし
- **承認してから起票する**: メインエージェントは、承認を得た draft だけを issue にする。承認は設計の PR の merge かチャットで、draft の `approved_at:` に書く ／ 例: `approved_at: PR #14 の merge で承認` ／ 失効: なし
- **未承認は draft に留める**: 承認前の設計は issue にせず、user レビューに出す ／ 例: 検討中の案は draft のまま ／ 失効: なし
- **止めた設計は保留の issue**: 着手しない設計は種別「設計メモ」・Status「保留」の issue にし、理由と再開条件を本文に書く ／ 例: 「保留理由: 外部 API の仕様未確定 / 再開条件: v2 API 公開」 ／ 失効: なし

- **承認は判断材料つきで求める**: メインエージェントは、着手 / 完了 / 優先順の変更 / draft 承認を求めるとき 5 項目を示す ／ 例: 型と記入例は `docs/rules-reference/approval-template.md` ／ 失効: なし

---
背景・過去の経緯・事故記録: `docs/rules-reference/`
