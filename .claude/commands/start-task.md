---
description: タスクに着手する。台帳から対象を読み、feature branch へ切替え、list.md の status を「進行中」に更新する。
---

# /start-task <task-id>

引数が空なら `docs/tasks/list.md` の status が `未着手` の行を一覧表示し、どの id に着手するか聞き返して停止する。

## 手順

1. `docs/tasks/list.md` を Read し、`<task-id>` の行を特定する。行が無ければ「id <task-id> は list.md に存在しない」と報告して終了する。
2. 同行の詳細列にある `docs/tasks/task-<task-id>-<slug>.md` を Read する。ファイルが存在しなければ「タスクファイル不在。/new-task で作成する」と報告して終了する。
3. タスクファイルに `依存先:` があれば、そこに並ぶ id のタスクファイルを全部 Read し、ゴールと完了条件を確認する。依存先の status が `完了` でないものが 1 件以上あれば、その id を列挙して「先に着手するか、この依存を外すか」を user に聞く。
4. 対応する `docs/draft/<slug>.md` が存在すれば Read する。draft に `approved_at:` が空、または行自体が無い場合は「未承認 draft のため着手しない」と報告して終了する。
5. branch を切替える。

```bash
git rev-parse --abbrev-ref HEAD                 # 現在 branch を記録
git status --porcelain                           # 出力が空でなければ 6 へ
git switch -c <type>/<slug> 2>/dev/null || git switch <type>/<slug>
```

`<type>` はタスクの性質で `feat` / `fix` / `refactor` / `docs` / `test` / `chore` から選ぶ。`<slug>` は task ファイル名の slug をそのまま使う。

6. `git status --porcelain` の出力が空でない場合は、未コミット変更のファイル名を列挙し「commit するか stash するか」を user に聞いてから 5 をやり直す。
7. `docs/tasks/list.md` の `<task-id>` 行の status 列を `進行中` に書き換える。他の行は変更しない。
8. 完了報告を 1 行で出す。書式: `task-<id> 着手。branch <name>、ゴール: <ゴール 1 文>`

## 判定できる終了条件

- `git rev-parse --abbrev-ref HEAD` が `<type>/<slug>` を返す。
- `grep '<task-id>' docs/tasks/list.md` の出力に `進行中` が含まれる。

この 2 つが両方成立した時点で着手完了とする。片方でも成立しなければ原因を 1 行で報告して停止する。
