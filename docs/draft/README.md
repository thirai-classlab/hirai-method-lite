# 設計 draft

新機能・仕様変更の設計をここに起こす。**承認を得た draft だけがタスクになる。**

運用規範は [`rules/tasks.md`](../../rules/tasks.md) (/init が `.claude/rules/tasks.md` へ配置する)。

## 流れ

```
1. 起案   docs/draft/<slug>.md を プラグイン同梱の templates/draft.md から作る
2. 承認   user がレビューし、承認したら draft 冒頭の approved_at: に日付か PR 番号を書く
3. 起票   承認済みの draft だけを issue にする（hirai-task new）。本文から draft へリンクする
4. 着手   Status が 着手可 になってから hirai-task start で 進行中 にし、実装を始める
5. 完了   PR の本文に Closes #<番号> を書く。merge で issue が閉じ、Status は 完了 になる
```

draft は起票後も**消さない**。設計の根拠として残し、issue 側からリンクし続ける。

（ファイルに一覧表を持つ形のリポでは、3 を `docs/tasks/list.md` への 1 行追加、4・5 を list.md の status 書き換えと読み替える。形は `rules/tasks.md` の冒頭で見分ける。）

## 命名

`<slug>.md` — 小文字・数字・ハイフンのみ。

```
login-rate-limit.md
notify-email.md
search-index-migration.md
```

## 承認前と承認後

| | 承認前 | 承認後 |
|---|---|---|
| 置き場所 | `docs/draft/` | `docs/draft/` (そのまま) |
| `approved_at:` | 空 | `approved_at: 2026-08-22（チャット）` |
| issue | 作らない | 作る |
| 実装着手 | しない | する |

承認前の設計を issue にしない。issue になっているものは着手の対象、という区別を保つため。

## 承認が要るもの

- 新機能の設計
- 承認済み設計からの逸脱 (仕様変更・スコープ拡張)
- アーキテクチャや採用技術の選択

Loop モードでもこの 3 つの承認は省略しない。

## 却下されたら

draft はそのまま残し、種別「設計メモ」・Status「保留」の issue を作って、判断日・理由・再開条件を本文に書く（台帳の形では [`../tasks/parking-lot.md`](../tasks/parking-lot.md) に「不採用」の行）。同じ提案が再燃したときに、前回何を理由に見送ったかを辿れるようにする。
