---
description: 承認済 draft から docs/tasks/task-<id>-<slug>.md を作り、docs/tasks/list.md に 1 行追加する。GitHub Project の形では、親と依存と目印を決めて hirai-task new で issue を起票する。
---

# /new-task <id> <slug>（GitHub Project の形では /new-task <題名>）

引数の読み方は形で変わる。台帳の形は `id` と `slug` の 2 つ、GitHub Project の形は題名 1 つ。「形の見分け」のあとで、揃っていなければ聞き返して停止する。

## 形の見分け (最初に 1 回)

台帳の形 (このファイル本来の手順) と GHP の形 (GitHub Project) は排他ではなく、リポごとに見分ける。

```bash
P="${CLAUDE_PLUGIN_ROOT}"; [ -d "$P" ] || P="$(command -v python3 >/dev/null 2>&1 && python3 -c 'import json,re,sys; d=json.load(open(sys.argv[1])); r=[x for k,v in d.get("plugins",{}).items() if k.split("@",1)[0]==sys.argv[2] for x in v if x.get("installPath")]; r.sort(key=lambda x:[int(n) if n.isdigit() else 0 for n in re.split(r"[.]", str(x.get("version","0")))]); print(r[-1]["installPath"] if r else "")' "$HOME/.claude/plugins/installed_plugins.json" hirai-lite-v2 2>/dev/null)"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite-v2/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"
[ -f "$P/scripts/tasks-path.sh" ] || { echo "プラグイン本体が見つからない"; exit 2; }
. "$P/scripts/tasks-path.sh"; harness_ghp_form "$PWD"
```

exit code が 2 (プラグイン本体が見つからない) なら、その場で報告して停止する (台帳の手順にもフォールバックしない)。出力が空で exit code が 1 の場合は `harness_ghp_refresh now "$PWD"` を 1 回呼んで取り直し、もう一度上のコマンドを実行する。それでも空、または `ambiguous` なら、GHP と台帳のどちらで進めるか user に尋ねて停止する。`ghp` が出たら、下の「## GHP の形の場合」だけを行い、以降の台帳の手順は行わない (台帳は作らず、書かない)。`none` が出たら、この節は無視して下の「## 台帳の解決」から続ける。

## GHP の形の場合

台帳は読まない・作らない・書かない。`command -v hirai-task` が無ければ「hirai-task が見つからない（PATH に入っていない）」と報告して終了する。題名が無ければ聞き返して停止する。

`hirai-task new` は issue を作るだけで、親の決め方や依存の張り方は決めない。決めてから `new` を呼ぶ。判定はここで、書き込みは `hirai-task` で行う。

### 書式

- **1 issue = ゴール 1 文 + 手順 + 完了条件**: 本文にこの 3 つを書く。draft から起こすなら `--from-draft <パス>` で渡す（承認済み、つまり `approved_at:` のある draft だけ通る）
- **1 issue = 1 セッション**: 変更ファイルが 10 を超えるか、完了条件が 7 コマンドを超えるか、参照点が 8 箇所を超えるときは、同じ feature の子として task を分ける（task の下にはさらに子を作らない。親子は wave → feature → task の 3 段まで）
- **完了条件はコマンドで書く**: 「`<テストコマンド>` が exit 0」のように、実行できるコマンドと期待する結果で書く
- **参照は path:line で書く**: 本文に正本の `path:line` と、元 draft の相対 path・節を書き、会話の文脈に依存させない
- **やらないことを名指しする**: 隣の issue の範囲を issue 番号で名指しする（例: 「認証の実装は #12 の範囲」）

### 親の決め方

task と feature は親が必須。親は feature（task の場合）か wave（feature の場合）で、`new` はこの組み合わせを確かめ、親が無い・違えば理由を出して exit 2 にする（REST は 1 回も呼ばない）。`hirai-task show <n>` で対象の feature・wave の番号を見てから `--parent <n>` で渡す（`hirai-task ready` の行の `[feature #<番号>]` が親の feature。承認待ちの feature は `hirai-task pending` が出す）。wave・設計メモは親を持たない（`--parent` を渡すと exit 2）。

親が無いときは、`new` で作る（1 件ずつ・作った直後に承認待ちで出る）。

- **feature が無い**: `hirai-task new <題名> --kind feature --parent <wave の番号>`。承認待ちで作られ、「ボードで着手可にする」と 1 行で知らされる。着手可にするのは人（AI は動かさない）
- **wave が無い**: `hirai-task new <題名> --kind wave`。wave の issue の本文の「まだ作っていない wave」の節にあるものだけ作れる。節の書式は 1 行 1 件で、`- P3 基盤の部品・着手順 4・blocked by P1・目的と条件`（名前は最初の「・」まで。blocked by は `#番号` か短い ID）。作ったあと、節の blocked by が張られ、「並び順をボードで直してください」と知らされる。節に無い wave は作らず exit 2

### 止める依存と緩い依存

- **止める依存**（着手を実際に止めるもの）は `--blocked-by <n1,n2,...>` で GitHub の issue dependencies（blocked by）に張る。task 同士・裁定の issue への依存はここに入れる
- **緩い依存**（並行してよい・順序の目印）は blocked by にせず、本文に文章で書く（例: 「#15 の完了を待たずに書ける」）

### 目印

題名の先頭に付ける。

- `[操作]`: 実行の前にチャットで 1 件ずつ承認を取る task。`hirai-task start <n> --approved <出どころ>` でだけ承認待ちから進行中に進められる
- `[User]`: 人が手を動かす task。`hirai-task ready` にも align にも出ない。`hirai-task today` が番号で出す

### bug の親

ラベル bug を付ける task（`--label-bug`）は、不具合の出た機能の、いま進んでいる wave の feature に付ける。親は bug でも必須。決められなければ作らず、候補を添えて人に聞く。親を無理にこじつけない。

判定できる終了条件: `hirai-task new` が exit 0 で、作った issue 番号を報告できたこと。成立しなければ原因を 1 行で報告して停止する。

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

1. `grep -E '^approved_at: (20|PR #)' docs/draft/<slug>.md` が exit 0。失敗 → 「draft が未承認。/new-draft <slug> で承認を得る」と報告して終了。
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
