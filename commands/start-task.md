---
description: タスクに着手する。台帳から対象を読み、feature branch へ切替え、list.md の status を「進行中」に更新する。
---

# /start-task <task-id>

引数が空なら `docs/tasks/list.md` の status が `未着手` の行を一覧表示し、どの id に着手するか聞き返して停止する。

## 形の見分け (最初に 1 回)

台帳の形 (このファイル本来の手順) と GHP の形 (GitHub Project) は排他ではなく、リポごとに見分ける。

```bash
P="${CLAUDE_PLUGIN_ROOT}"; [ -d "$P" ] || P="$(command -v python3 >/dev/null 2>&1 && python3 -c 'import json,re,sys; d=json.load(open(sys.argv[1])); r=[x for k,v in d.get("plugins",{}).items() if k.split("@",1)[0]==sys.argv[2] for x in v if x.get("installPath")]; r.sort(key=lambda x:[int(n) if n.isdigit() else 0 for n in re.split(r"[.]", str(x.get("version","0")))]); print(r[-1]["installPath"] if r else "")' "$HOME/.claude/plugins/installed_plugins.json" hirai-lite-v2 2>/dev/null)"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite-v2/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"
. "$P/scripts/tasks-path.sh"; harness_ghp_form "$PWD"
```

`ghp` が出たら、下の「## GHP の形の場合」だけを行い、以降の台帳の手順は行わない (台帳は作らず、書かない)。`ghp` 以外 (空 / `none` / `ambiguous`) なら、この節は無視して下の「## 台帳の解決」から続ける。

## GHP の形の場合

`hirai-task start <task-id>` を呼ぶ。branch の切替えと Status の更新はこのコマンドが行うので、下の「## 手順」の 5〜7 (branch 切替え・台帳の書き換え) はここでは実行しない。`command -v hirai-task` が無ければ「hirai-task が見つからない。H-4 の完了後に使える」と報告して終了する。

## 台帳の解決 (最初に 1 回)

台帳パスは `$HARNESS_TASKS_FILE` > `docs/tasks/list.md` > (旧レイアウト) `.claude/tasks/list.md` の順に解決する。**新しく作るときは常に `docs/tasks/list.md`**。

```bash
P="${CLAUDE_PLUGIN_ROOT}"; [ -d "$P" ] || P="$(command -v python3 >/dev/null 2>&1 && python3 -c 'import json,re,sys; d=json.load(open(sys.argv[1])); r=[x for k,v in d.get("plugins",{}).items() if k.split("@",1)[0]==sys.argv[2] for x in v if x.get("installPath")]; r.sort(key=lambda x:[int(n) if n.isdigit() else 0 for n in re.split(r"[.]", str(x.get("version","0")))]); print(r[-1]["installPath"] if r else "")' "$HOME/.claude/plugins/installed_plugins.json" hirai-lite-v2 2>/dev/null)"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite-v2/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"
. "$P/scripts/tasks-path.sh"; LIST="$(harness_tasks_file "$PWD")"; echo "台帳 ${LIST:-なし}"
```

空 (exit 1) なら台帳が無い。**その場で空の台帳を `docs/tasks/list.md` に作ってから続行する** (見出しと 6 列ヘッダは `/new-task` と同じ)。作った直後は行が 0 なので「台帳を作成した。task が無いので /new-task <id> <slug> で追加する」と報告して終了する。

以降この文書の `docs/tasks/list.md` は `$LIST` に、`docs/tasks/` は `$(dirname "$LIST")` に読み替える。`docs/draft/` は `harness_draft_dir "$PWD"` が返す draft dir (通常 `docs/draft/`) に読み替える。

## 手順

1. `$LIST` を Read し、`<task-id>` の行を特定する。行が無ければ「id <task-id> は台帳に存在しない」と報告して終了する。
2. 同行の詳細列にある `docs/tasks/task-<task-id>-<slug>.md` を Read する。ファイルが存在しなければ「タスクファイル不在。/new-task で作成する」と報告して終了する。
3. タスクファイルに `依存先:` があれば、そこに並ぶ id のタスクファイルを全部 Read し、ゴールと完了条件を確認する。依存先の status が `完了` でないものが 1 件以上あれば、その id を列挙して「先に着手するか、この依存を外すか」を user に聞く。
   **承認を求めるときは判断材料 5 項目**（何をしたいか / なぜ / しないとどうなる / トレードオフ / どうやるか）**を本文に示してから** `AskUserQuestion`（`承認する` / `承認しない` / `修正して提案し直す`）**を出す。型と記入例**: `docs/rules-reference/approval-template.md`（プロジェクトに無ければプラグイン同梱の同名ファイル）。 「なぜ」には未完了の依存 id と、それを待たずに進められる step の範囲を書く。
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
