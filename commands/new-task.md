---
description: 承認済 draft から docs/tasks/task-<id>-<slug>.md を作り、docs/tasks/list.md に 1 行追加する。
---

# /new-task <id> <slug>

引数が 2 つ揃っていない場合は `id` と `slug` を聞き返して停止する。

## 台帳の解決 (最初に 1 回)

台帳パスは `$HARNESS_TASKS_FILE` > `docs/tasks/list.md` > `.claude/tasks/list.md` の順に解決する。

```bash
LIST="$(bash -c '. "$CLAUDE_PLUGIN_ROOT/scripts/tasks-path.sh"; harness_tasks_file "$PWD"')"
```

空 (exit 1) なら台帳が無い。**その場で作ってから続行する** — `docs/` があるリポジトリは `docs/tasks/list.md`、無ければ `.claude/tasks/list.md` に置く。

```bash
LIST="$([ -d docs ] && echo docs/tasks/list.md || echo .claude/tasks/list.md)"
mkdir -p "$(dirname "$LIST")"
printf '# タスク台帳\n\nstatus は 未着手 / 進行中 / 完了 の 3 種。\n\n| # | status | タスク | 概要 | 依存先 | 詳細 |\n|---|--------|-------|------|-------|------|\n' > "$LIST"
```

以降この文書の `docs/tasks/list.md` は `$LIST` に、`docs/tasks/` は `$(dirname "$LIST")` に読み替える (タスクファイルは台帳と同じディレクトリに置く)。`docs/draft/` は `harness_draft_dir "$PWD"` が返す draft dir (`docs/` が無ければ `.claude/draft/`) に読み替える。

## 事前チェック (どれか 1 つでも失敗したら作成しない)

1. `grep '^approved_at: 20' docs/draft/<slug>.md` が exit 0。失敗 → 「draft が未承認。/new-draft <slug> で承認を得る」と報告して終了。
2. `ls docs/tasks/task-<id>-*.md` が exit 1 (同 id が未使用)。exit 0 なら「id <id> は既に使われている」と既存ファイル名を出して終了。
3. `grep -c '^| <id> ' docs/tasks/list.md` が 0。1 以上なら既存行を表示して終了。

hot fix で draft を省く場合のみ `--no-draft` を付ける。その場合 1 を飛ばし、タスクファイルの `設計:` に `なし (hot fix)` と書く。

## タスクファイルの作成

`docs/tasks/task-<id>-<slug>.md` を以下で作る。

```markdown
# task-<id>: <タイトル>

- 設計: docs/draft/<slug>.md
- 依存先: <task-N1, task-N2 または なし>
- status: 未着手

## ゴール
<観察できる状態を 1 文>

## 完了条件
<再現できる検証コマンド。例: `npm test -- auth` が exit 0>

## Step
| # | status | 作業概要 | 完了条件 |
|---|---|---|---|
| 1 | 未着手 | | |
| 2 | 未着手 | | |
| 3 | 未着手 | テストを green にする | <検証コマンド> |
```

- ゴール・完了条件・Step は draft §4 §5 から写す。
- 依存先を書く場合は task id を列挙し、依存が無ければ `なし` と書く。空欄で残さない。
- status は `未着手` / `進行中` / `完了` の 3 種のみ使う。

## list.md への追加

`docs/tasks/list.md` の一覧テーブル末尾に 1 行 append する。既存行は変更しない。

```
| <id> | 未着手 | <タイトル> | <何のため × 何をやる × 何ができるようになる> | <依存先 id or —> | [task-<id>-<slug>.md](task-<id>-<slug>.md) |
```

概要列は 3 要素を 1 文にまとめる (例: 「認証エラーの再ログインループを止めるため、token 更新処理を書き換え、期限切れでも再ログインなしで継続できるようにする」)。

## 判定できる終了条件

- `ls docs/tasks/task-<id>-<slug>.md` が exit 0。
- `grep -c '^| <id> ' docs/tasks/list.md` が 1。
- `grep -E '適切に|必要に応じて|可能な限り|十分に|慎重に' docs/tasks/task-<id>-<slug>.md` が 0 件。

3 つ成立したら `task-<id> 追加。着手は /start-task <id>` と 1 行で報告する。
