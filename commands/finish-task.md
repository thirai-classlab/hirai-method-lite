---
description: タスクを完了させる。完了条件のコマンドを実行して exit 0 を確認し、list.md を「完了」に更新して台帳ごと 1 commit にまとめる。GitHub Project の形では issue 本文の完了条件を読む。
---

# /finish-task <task-id>

## 形の見分け (最初に 1 回)

台帳の形 (このファイル本来の手順) と GHP の形 (GitHub Project) は排他ではなく、リポごとに見分ける。

```bash
P="${CLAUDE_PLUGIN_ROOT}"; [ -d "$P" ] || P="$(command -v python3 >/dev/null 2>&1 && python3 -c 'import json,re,sys; d=json.load(open(sys.argv[1])); r=[x for k,v in d.get("plugins",{}).items() if k.split("@",1)[0]==sys.argv[2] for x in v if x.get("installPath")]; r.sort(key=lambda x:[int(n) if n.isdigit() else 0 for n in re.split(r"[.]", str(x.get("version","0")))]); print(r[-1]["installPath"] if r else "")' "$HOME/.claude/plugins/installed_plugins.json" hirai-lite-v2 2>/dev/null)"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite-v2/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"
[ -f "$P/scripts/tasks-path.sh" ] || { echo "プラグイン本体が見つからない"; exit 2; }
. "$P/scripts/tasks-path.sh"; harness_ghp_form "$PWD"
```

exit code が 2 (プラグイン本体が見つからない) なら、その場で報告して停止する (台帳の手順にもフォールバックしない)。出力が空で exit code が 1 の場合は `harness_ghp_refresh now "$PWD"` を 1 回呼んで取り直し、もう一度上のコマンドを実行する。それでも空、または `ambiguous` なら、GHP と台帳のどちらで進めるか user に尋ねて停止する。`ghp` が出たら、下の「## GHP の形の場合」だけを行い、以降の台帳の手順は行わない (台帳は作らず、書かない)。`none` が出たら、この節は無視して下の「## 台帳の解決」から続ける。

## GHP の形の場合

引数が空なら `hirai-task today` の結果から 進行中 の id を選び、どの id を完了させるか聞き返して停止する。

1. issue `<task-id>` の本文の「完了条件」の節から検証コマンドを取り出す（`gh issue view <task-id> --json body --jq .body` などで読む）。1 つずつ実行し、1 つでも exit code が 0 以外なら、その出力の末尾 20 行を提示して停止する。完了条件が書かれていなければ `/verify` を実行し、build / test / lint が全部 exit 0 になることを確認する。
2. PR の `Closes` と base を確かめる。`gh pr view --json baseRefName,closingIssuesReferences` を実行する。`baseRefName` が既定ブランチ（例: `main`）でない、または `closingIssuesReferences` が空なら、base を既定ブランチに直すか `Closes #<task-id>` を足すよう案内して停止する。
3. `hirai-task review <task-id>` を呼ぶ（Status を レビュー中 に書くだけの補助。2 の確認はこのコマンドの役目ではない）。`command -v hirai-task` が無ければ「hirai-task が見つからない（PATH に入っていない）」と報告して終了する。
4. 台帳は読まない・書かない（GHP の形は台帳を持たない）。実装の commit は通常の作業中（`/commit` 等）に作られている前提とし、ここでは新たに commit を作らない。

判定できる終了条件: 1・2 の確認が exit 0、かつ `hirai-task review` が exit 0 だったこと。1 つでも成立しなければ原因を 1 行で報告して停止する。

## 台帳の解決 (最初に 1 回)

引数が空なら `docs/tasks/list.md` の status が `進行中` の行を一覧表示し、どの id を完了させるか聞き返して停止する。

台帳パスは `$HARNESS_TASKS_FILE` > `docs/tasks/list.md` > (旧レイアウト) `.claude/tasks/list.md` の順に解決する。**新しく作るときは常に `docs/tasks/list.md`**。

```bash
P="${CLAUDE_PLUGIN_ROOT}"; [ -d "$P" ] || P="$(command -v python3 >/dev/null 2>&1 && python3 -c 'import json,re,sys; d=json.load(open(sys.argv[1])); r=[x for k,v in d.get("plugins",{}).items() if k.split("@",1)[0]==sys.argv[2] for x in v if x.get("installPath")]; r.sort(key=lambda x:[int(n) if n.isdigit() else 0 for n in re.split(r"[.]", str(x.get("version","0")))]); print(r[-1]["installPath"] if r else "")' "$HOME/.claude/plugins/installed_plugins.json" hirai-lite-v2 2>/dev/null)"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite-v2/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"
[ -f "$P/scripts/tasks-path.sh" ] || { echo "プラグイン本体が見つからない"; exit 2; }
. "$P/scripts/tasks-path.sh"; LIST="$(harness_tasks_file "$PWD")"; echo "台帳 ${LIST:-なし}"
```

exit code が 2 (プラグイン本体が見つからない) なら、その場で報告して停止する (**既存の `docs/tasks/list.md` を上書きしない**)。空 (exit 1) なら台帳が無い。**その場で空の台帳を `docs/tasks/list.md` に作ってから続行する** (見出しと 6 列ヘッダは `/new-task` と同じ)。作った直後は対象行が無いので、検証だけ実施して「台帳を作成した。task-<id> の行が無いので status 更新は行わない」と報告する。

以降この文書の `docs/tasks/list.md` は `$LIST` に、`docs/tasks/` は `$(dirname "$LIST")` に読み替える (`git add` も同じパスに読み替える)。

## 手順

1. `docs/tasks/task-<task-id>-<slug>.md` を Read し、`完了条件:` に書かれた検証コマンドを取り出す。
2. 検証コマンドを 1 つずつ実行する。1 つでも exit code が 0 以外なら、その出力の末尾 20 行を提示して停止する。status は更新しない。
3. 検証コマンドが書かれていない場合は `/verify` を実行し、build / test / lint が全部 exit 0 になることを確認する。
4. 全ステップの status が `完了` になっているかタスクファイルで確認する。`進行中` が残っていれば残り step 名を列挙して user に確認を取る。
   **承認を求めるときは判断材料 5 項目**（何をしたいか / なぜ / しないとどうなる / トレードオフ / どうやるか）**を本文に示してから** `AskUserQuestion`（`承認する` / `承認しない` / `修正して提案し直す`）**を出す。型と記入例**: `docs/rules-reference/approval-template.md`（プロジェクトに無ければプラグイン同梱の同名ファイル）。 「何をしたいか」には残 step 名と、それでも完了とする範囲を書く。
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

feature branch への `git push` と `gh pr create` はここでは実行しない。user が push を指示した時点で実行する。`main` への push と `gh pr merge` は user 承認を取る。元に戻せない操作なので、**承認を求めるときは判断材料 5 項目**（何をしたいか / なぜ / しないとどうなる / トレードオフ / どうやるか）**を本文に示してから** `AskUserQuestion`（`承認する` / `承認しない` / `修正して提案し直す`）**を出す。型と記入例**: `docs/rules-reference/approval-template.md`（プロジェクトに無ければプラグイン同梱の同名ファイル）。
