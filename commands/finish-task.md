---
description: タスクを完了させる。完了条件のコマンドを実行して exit 0 を確認し、list.md を「完了」に更新して台帳ごと 1 commit にまとめる。
---

# /finish-task <task-id>

引数が空なら `docs/tasks/list.md` の status が `進行中` の行を一覧表示し、どの id を完了させるか聞き返して停止する。

## 台帳の解決 (最初に 1 回)

台帳パスは `$HARNESS_TASKS_FILE` > `docs/tasks/list.md` > (旧レイアウト) `.claude/tasks/list.md` の順に解決する。**新しく作るときは常に `docs/tasks/list.md`**。

```bash
LIST="$(bash -c '. "$CLAUDE_PLUGIN_ROOT/scripts/tasks-path.sh"; harness_tasks_file "$PWD"')"
```

空 (exit 1) なら台帳が無い。**その場で空の台帳を `docs/tasks/list.md` に作ってから続行する** (見出しと 6 列ヘッダは `/new-task` と同じ)。作った直後は対象行が無いので、検証だけ実施して「台帳を作成した。task-<id> の行が無いので status 更新は行わない」と報告する。

以降この文書の `docs/tasks/list.md` は `$LIST` に、`docs/tasks/` は `$(dirname "$LIST")` に読み替える (`git add` も同じパスに読み替える)。

## 手順

1. `docs/tasks/task-<task-id>-<slug>.md` を Read し、`完了条件:` に書かれた検証コマンドを取り出す。
2. 検証コマンドを 1 つずつ実行する。1 つでも exit code が 0 以外なら、その出力の末尾 20 行を提示して停止する。status は更新しない。
3. 検証コマンドが書かれていない場合は `/verify` を実行し、build / test / lint が全部 exit 0 になることを確認する。
4. 全ステップの status が `完了` になっているかタスクファイルで確認する。`進行中` が残っていれば残り step 名を列挙して user に確認を取る。
5. `docs/tasks/list.md` の `<task-id>` 行の status 列を `完了` に書き換える。
6. **完了 commit に台帳を含める**。以下 3 種を 1 つの commit にまとめる。

```bash
git add docs/tasks/list.md docs/tasks/task-<task-id>-<slug>.md
git add <実装で変更したファイル>
git status --porcelain            # 追加漏れが無いことを確認
git commit -m "<type>: <タスクゴール 1 文> (task-<task-id>)"
```

`git add -A` と `git add .` は使わない。ファイルを明示して add する。

7. commit 後に台帳が commit に含まれたことを検証する。

```bash
git show --stat --name-only HEAD | grep 'docs/tasks/list.md'
```

この grep が exit 1 を返したら `git add docs/tasks/list.md && git commit --amend --no-edit` で取り込み、再度 grep する。

8. 完了報告を 1 行で出す。書式: `task-<id> 完了。commit <短縮 hash>、検証 <N> 件 exit 0。次: <list.md の次の未着手 id or なし>`

## 判定できる終了条件

- 完了条件の全コマンドが exit 0。
- `git show --name-only HEAD` の出力に `docs/tasks/list.md` が含まれる。
- `grep '<task-id>' docs/tasks/list.md` の出力に `完了` が含まれる。

3 つ全部が成立した時点でタスク完了とする。

## push は別扱い

feature branch への `git push` と `gh pr create` はここでは実行しない。user が push を指示した時点で実行する。`main` への push と `gh pr merge` は user 承認を取る。
