---
description: 承認済 draft から docs/tasks/task-<id>-<slug>.md を作り、docs/tasks/list.md に 1 行追加する。GitHub Project の形では起票のスキルに委ねる。
---

# /new-task <id> <slug>

引数が 2 つ揃っていない場合は `id` と `slug` を聞き返して停止する。

## 形の見分け (最初に 1 回)

台帳の形 (このファイル本来の手順) と GHP の形 (GitHub Project) は排他ではなく、リポごとに見分ける。

```bash
P="${CLAUDE_PLUGIN_ROOT}"; [ -d "$P" ] || P="$(command -v python3 >/dev/null 2>&1 && python3 -c 'import json,re,sys; d=json.load(open(sys.argv[1])); r=[x for k,v in d.get("plugins",{}).items() if k.split("@",1)[0]==sys.argv[2] for x in v if x.get("installPath")]; r.sort(key=lambda x:[int(n) if n.isdigit() else 0 for n in re.split(r"[.]", str(x.get("version","0")))]); print(r[-1]["installPath"] if r else "")' "$HOME/.claude/plugins/installed_plugins.json" hirai-lite-v2 2>/dev/null)"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite-v2/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"
[ -f "$P/scripts/tasks-path.sh" ] || { echo "プラグイン本体が見つからない"; exit 2; }
. "$P/scripts/tasks-path.sh"; harness_ghp_form "$PWD"
```

exit code が 2 (プラグイン本体が見つからない) なら、その場で報告して停止する (台帳の手順にもフォールバックしない)。出力が空で exit code が 1 の場合は `harness_ghp_refresh now "$PWD"` を 1 回呼んで取り直し、もう一度上のコマンドを実行する。それでも空、または `ambiguous` なら、GHP と台帳のどちらで進めるか user に尋ねて停止する。`ghp` が出たら、下の「## GHP の形の場合」だけを行い、以降の台帳の手順は行わない (台帳は作らず、書かない)。`none` が出たら、この節は無視して下の「## 台帳の解決」から続ける。

## GHP の形の場合

起票は起票のスキル（`hirai-task new <id> <slug>`）に任せる。`command -v hirai-task` が無ければ「hirai-task が見つからない（PATH に入っていない）」と報告して終了する。台帳は読まない・作らない・書かない。

判定できる終了条件: `hirai-task new <id> <slug>` が exit 0 で、作った issue 番号を報告できたこと。成立しなければ原因を 1 行で報告して停止する。

## 台帳の解決 (最初に 1 回)

台帳パスは `$HARNESS_TASKS_FILE` > `docs/tasks/list.md` > (旧レイアウト) `.claude/tasks/list.md` の順に解決する。**新しく作るときは常に `docs/tasks/list.md`**。

```bash
P="${CLAUDE_PLUGIN_ROOT}"; [ -d "$P" ] || P="$(command -v python3 >/dev/null 2>&1 && python3 -c 'import json,re,sys; d=json.load(open(sys.argv[1])); r=[x for k,v in d.get("plugins",{}).items() if k.split("@",1)[0]==sys.argv[2] for x in v if x.get("installPath")]; r.sort(key=lambda x:[int(n) if n.isdigit() else 0 for n in re.split(r"[.]", str(x.get("version","0")))]); print(r[-1]["installPath"] if r else "")' "$HOME/.claude/plugins/installed_plugins.json" hirai-lite-v2 2>/dev/null)"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite-v2/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"
[ -f "$P/scripts/tasks-path.sh" ] || { echo "プラグイン本体が見つからない"; exit 2; }
. "$P/scripts/tasks-path.sh"; LIST="$(harness_tasks_file "$PWD")"; echo "台帳 ${LIST:-なし}"
```

exit code が 2 (プラグイン本体が見つからない) なら、その場で報告して停止する (**既存の `docs/tasks/list.md` を上書きしない**)。空 (exit 1) なら台帳が無い。**その場で `docs/tasks/list.md` に作ってから続行する**。

```bash
LIST=docs/tasks/list.md
mkdir -p "$(dirname "$LIST")"
printf '# タスク台帳\n\nstatus は 未着手 / 進行中 / 完了 の 3 種。\n\n| # | status | タスク | 概要 | 依存先 | 詳細 |\n|---|--------|-------|------|-------|------|\n' > "$LIST"
```

以降この文書の `docs/tasks/list.md` は `$LIST` に、`docs/tasks/` は `$(dirname "$LIST")` に読み替える (タスクファイルは台帳と同じディレクトリに置く)。`docs/draft/` は `harness_draft_dir "$PWD"` が返す draft dir (通常 `docs/draft/`) に読み替える。

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
