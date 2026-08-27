# 設計 draft

新機能・仕様変更の設計をここに起こす。**承認を得た draft だけがタスクになる。**

運用規範は [`rules/tasks.md`](../../rules/tasks.md) (/init が `.claude/rules/tasks.md` へ配置する)。

## 流れ

```
1. 起案   docs/draft/<slug>.md を $CLAUDE_PLUGIN_ROOT/templates/draft.md から作る
2. 承認   user がレビューし、承認したら draft 冒頭に approved: YYYY-MM-DD を書く
3. 台帳化 docs/tasks/list.md に 1 行 (status = 未着手) を追加し、詳細欄から draft へリンク
4. 着手   status を 進行中 にしてから実装を始める
5. 完了   status を 完了 にし、その更新を完了 commit に同梱する
```

draft は台帳化後も**消さない**。設計の根拠として残し、タスク側からリンクし続ける。

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
| `approved:` | 無い | `approved: 2026-08-22` |
| list.md の行 | 作らない | 作る |
| 実装着手 | しない | する |

承認前の設計を list.md に載せない。載っているものは着手してよい、という区別を保つため。

## 承認が要るもの

- 新機能の設計
- 承認済み設計からの逸脱 (仕様変更・スコープ拡張)
- アーキテクチャや採用技術の選択

Loop モードでもこの 3 つの承認は省略しない。

## 却下されたら

draft はそのまま残し、[`../tasks/parking-lot.md`](../tasks/parking-lot.md) に「不採用」の行を作って判断日と理由を書く。同じ提案が再燃したときに、前回何を理由に見送ったかを辿れるようにする。
