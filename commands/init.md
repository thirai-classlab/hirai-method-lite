---
description: プラグインの rules / settings / mode.yml / 台帳を、いま開いているリポジトリへ冪等に配置する。既存ファイルは上書きしない。
---

# /init

`$CLAUDE_PLUGIN_ROOT` を素材置き場、`$PWD` を配置先として実行する。**既存ファイルは 1 つも上書きしない。** 差分がある場合は差分を提示し、user が反映を指示したときだけ書き換える。各手順の結果を `placed` / `kept` / `diff` のいずれか + パスで 1 行ずつ報告する。

## 1. rules を配置する

```bash
mkdir -p .claude/rules
for f in "$CLAUDE_PLUGIN_ROOT"/rules/*.md; do
  d=".claude/rules/$(basename "$f")"
  if [ -e "$d" ]; then echo "kept   $d"; else cp "$f" "$d" && echo "placed $d"; fi
done
head -3 .claude/rules/_meta.md .claude/rules/core.md .claude/rules/tasks.md
```

`_meta.md` と `core.md` は frontmatter を持たない (T0 = 常時ロード)。`tasks.md` `code.md` `ops.md` は 1 行目が `---` で `paths:` を持つ (T1 = 条件ロード)。`head -3` の出力でこの 2 種を確認する。frontmatter が消えていたら cp をやり直す。

## 2. 退避先を作る

失効したルールの移動先 (T3)。ロードされない。

```bash
mkdir -p .claude/rules-archive && ls -d .claude/rules-archive
```

## 3. permissions をマージする

```bash
cat "$CLAUDE_PLUGIN_ROOT/templates/settings.json"
```

- `.claude/settings.json` が無い → そのままコピーする。
- ある → **上書きしない**。既存の `permissions.deny` / `permissions.ask` と突き合わせ、素材にしかないエントリだけを一覧で提示し「この N 件を追記しますか?」と聞く。承認された分だけ既存 JSON の配列末尾に追加する。他のキー (`hooks` / `statusLine` / `env` 等) には触れない。

```bash
python3 -m json.tool .claude/settings.json >/dev/null && echo "settings.json は妥当な JSON"
```
## 4. mode.yml を配置する

```bash
[ -e .claude/mode.yml ] && echo "kept   .claude/mode.yml" \
  || { cp "$CLAUDE_PLUGIN_ROOT/templates/mode.yml" .claude/mode.yml && echo "placed .claude/mode.yml"; }
```

## 5. 台帳を作る

`docs/` があるリポジトリは `docs/tasks/`、無ければ `.claude/tasks/` を使う。

```bash
LIST="$([ -d docs ] && echo docs/tasks/list.md || echo .claude/tasks/list.md)"
mkdir -p "$(dirname "$LIST")"
[ -e "$LIST" ] || printf '# タスク台帳\n\nstatus は 未着手 / 進行中 / 完了 の 3 種。\n\n| # | status | タスク | 概要 | 依存先 | 詳細 |\n|---|--------|-------|------|-------|------|\n' > "$LIST"
[ -e "$(dirname "$LIST")/parking-lot.md" ] || printf '# 保留タスク\n\n| # | 状態 | タスク | 保留理由 | 再開条件 | 元の設計 |\n|---|------|-------|---------|---------|---------|\n' > "$(dirname "$LIST")/parking-lot.md"
if [ -d docs ]; then mkdir -p docs/draft docs/rules-reference
  [ -e docs/rules-reference/incidents.md ] || printf '# 事故記録\n\n1 回目はここに 1 行。2 回目で /add-rule に回す。\n\n| 日付 | 事象 | 影響 | 直し方 | 再発回数 |\n|-----|------|------|-------|--------|\n' > docs/rules-reference/incidents.md
fi
ls "$LIST"
```

## 6. ロードを実測する

配置しただけでは検証にならない。**新しいセッションを開いて**次を確認する。

1. 新セッションの冒頭で `.claude/rules/core.md` の文言 (例: `commit 粒度`) が context に載っている → T0 が正しい。
2. その時点で `.claude/rules/tasks.md` の文言 (例: `台帳は 1 枚`) は載っていない → T1 が正しい。
3. `docs/tasks/list.md` を Read した**後**に `台帳は 1 枚` が載る → `paths:` が効いている。

2 の時点で T1 が既に載っていたら `paths:` frontmatter が壊れている。該当ファイルの 1〜6 行目を直して 1 からやり直す。

## 判定できる終了条件

- `ls .claude/rules/*.md` が 5 件返す。
- `head -1 .claude/rules/core.md` が `---` **ではない**。
- `head -1 .claude/rules/tasks.md` が `---` **である**。
- `ls .claude/rules-archive` が exit 0、`ls .claude/mode.yml` が exit 0、台帳が exit 0。
- 手順 6 の 3 点を新セッションで実測した。
