---
description: draft dir (docs/draft/ または .claude/draft/) に設計 draft を起こす。承認を得るまでタスク化しない、設計→承認→タスク化フローの起点。
---

# /new-draft <slug>

`<slug>` は lowercase の英数字とハイフンのみ、3〜49 文字。引数が空、または書式に一致しない場合は正しい slug を聞き返して停止する。

## draft dir の解決 (最初に 1 回)

draft dir は `$HARNESS_DRAFT_DIR` > 既存の `docs/draft/` > 既存の `.claude/draft/` > (どちらも無ければ) `docs/` があるリポジトリは `docs/draft/`、無ければ `.claude/draft/` の順に解決する。台帳と同じ解決順。

```bash
DRAFT="$(bash -c '. "$CLAUDE_PLUGIN_ROOT/scripts/tasks-path.sh"; harness_draft_dir "$PWD"')"
mkdir -p "$DRAFT"
echo "$DRAFT"
```

以降この文書の `docs/draft/` は `$DRAFT/` に読み替える。

## 手順

1. `ls "$DRAFT/<slug>.md"` が exit 0 を返したら「既に存在する」と報告し、上書きせずに終了する。
2. `$DRAFT/<slug>.md` を以下の骨格で新規作成する。

```markdown
---
slug: <slug>
created_at: YYYY-MM-DD
approved_at:
---
# <タイトル>

## 1. 解きたい課題
<現状の観察できる事実を 3 行以内。推測は「推測:」と明記する>

## 2. 制約
<守る条件。既存の互換性 / 予算 / 期限を列挙>

## 3. 案と採用案
| 案 | 内容 | 長所 | 短所 |
|---|---|---|---|
| A | | | |
| B | | | |

採用: <A or B> / 理由: <1 行>

## 4. 変更するファイル
<path を列挙。新規は (new) を付ける>

## 5. 完了条件
<再現できる検証コマンド、または観察できる事実で書く>

## 6. リスクと戻し方
<失敗時に何をすれば元に戻るか>

## 7. 承認履歴
- YYYY-MM-DD 起案
```

3. §1〜§6 を埋める。§5 は `npm test` の exit 0 のような判定できる形にする。埋められない項目は `未定:` を付けて残し、user に質問する。
4. 禁止語彙を検査する。`grep -nE '適切に|必要に応じて|可能な限り|十分に|慎重に' "$DRAFT/<slug>.md"` が 1 件でもヒットしたら、その行を判定できる条件へ書き換えて再検査する。
5. draft の §3 採用案と §5 完了条件を要約してチャットに提示し、`承認しますか? [y/N]` と聞く。
6. user が承認したら frontmatter の `approved_at:` に当日の日付を入れ、§7 に `- YYYY-MM-DD 承認` を追記する。承認が無い間 `approved_at:` は空のままにする。

## 判定できる終了条件

- `$DRAFT/<slug>.md` が存在する (`docs/` があれば `docs/draft/`、無ければ `.claude/draft/` の下)。
- 禁止語彙 grep が 0 件。
- 承認済なら `grep '^approved_at: 20' "$DRAFT/<slug>.md"` が exit 0。

## この後

承認済 draft は `/new-task <id> <slug>` でタスク化する。`approved_at:` が空の draft をタスク化しない。
