---
paths:
  - "docs/tasks/**"
  - "docs/draft/**"
  - ".claude/tasks/**"
  - ".claude/draft/**"
---
# タスク運用

対象: 設計 draft と、台帳の形のやること管理を触る作業。立ち上げ・Status・ビューの詳細は `docs/rules-reference/project-setup.md`（無ければプラグイン同梱の同名ファイル）。台帳（`list.md`）の形のリポは `docs/rules-reference/task-ledger.md` に従う。

## GitHub Project の形

規範は skill `github-project` にある（`hirai-task` と `gh` だけで進む作業はこのファイルの `paths:` に当たらず、ここに置くと読まれないため。v2.7.0 で移した）。

## 設計 draft

- **設計の起点は draft**: 新機能・仕様変更は `docs/draft/<slug>.md` に設計を起こす ／ 例: `docs/draft/login-rate-limit.md` ／ 失効: なし
- **承認してから起票する**: メインエージェントは、承認を得た draft だけを issue にする。承認は設計の PR の merge かチャットで、draft の `approved_at:` に書く ／ 例: `approved_at: PR #14 の merge で承認` ／ 失効: なし
- **未承認は draft に留める**: 承認前の設計は issue にせず、user レビューに出す ／ 例: 検討中の案は draft のまま ／ 失効: なし
- **止めた設計は保留の issue**: 着手しない設計は種別「設計メモ」・Status「保留」の issue にし、理由と再開条件を本文に書く ／ 例: 「保留理由: 外部 API の仕様未確定 / 再開条件: v2 API 公開」 ／ 失効: なし

- **承認はカードで求める**: メインエージェントは、着手 / 完了 / 優先順の変更 / draft 承認を求めるとき承認カードを示す ／ 例: 型と記入例は `docs/rules-reference/approval-template.md` ／ 失効: なし

---
背景・過去の経緯・事故記録: `docs/rules-reference/`
