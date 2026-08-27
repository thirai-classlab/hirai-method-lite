---
description: プラグインの rules / settings / mode.yml / statusline / 台帳を、いま開いているリポジトリへ冪等に配置する。既存ファイルは上書きしない。
---

# /init

`$CLAUDE_PLUGIN_ROOT` を素材置き場、`$PWD` を配置先として実行する。**既存ファイルは 1 つも上書きしない。** 差分がある場合は差分を提示し、user が反映を指示したときだけ書き換える。各手順の結果は `placed` / `kept` / `diff` + パスで手元に控えるだけにし、**利用者に見せる文章は手順 6 の型でまとめる**。

## 1. rules を配置する

```bash
mkdir -p .claude/rules
for f in "$CLAUDE_PLUGIN_ROOT"/rules/*.md; do
  d=".claude/rules/$(basename "$f")"
  if [ -e "$d" ]; then echo "kept   $d"; else cp "$f" "$d" && echo "placed $d"; fi
done
for f in .claude/rules/*.md; do sed -n '1,10p' "$f" | grep -q '^paths:' && echo "T1 $f" || echo "T0 $f"; done
```

**5 本すべて**を判定する。期待値は `T0` が `_meta.md` `core.md` の 2 本、`T1` が `tasks.md` `code.md` `ops.md` の 3 本。T1 のはずのファイルが `T0` と出たら `paths:` frontmatter が欠けている。その 1 本を消して cp をやり直す。

## 2. 退避先を作る

失効したルールの移動先 (T3)。ロードされない。空ディレクトリは git に載らないため `.gitkeep` を置く。

```bash
mkdir -p .claude/rules-archive && : > .claude/rules-archive/.gitkeep && ls -a .claude/rules-archive
```

## 3. settings.json を配置・マージする

```bash
cat "$CLAUDE_PLUGIN_ROOT/templates/settings.json"   # 素材。差分提示の元にする
[ -e .claude/settings.json ] && echo "kept   .claude/settings.json (下記手順で差分を提示する)" || { cp "$CLAUDE_PLUGIN_ROOT/templates/settings.json" .claude/settings.json && echo "placed .claude/settings.json"; }
python3 -m json.tool .claude/settings.json >/dev/null && echo "settings.json は妥当な JSON"
```

- 無かった場合は上の `cp` で配置済み。素材は `"ultracode": true` を含むため **xhigh 推論と自動 workflow オーケストレーションが有効になり、トークン消費が増える** (不要なら配置後にこのキーを削除するか `false` にする)。
- あった場合は **上書きしない**。素材と突き合わせて差分だけを提示し、承認された分だけ既存 JSON へ追加する。
  - `permissions` キーが無い → 素材の `permissions` をそのまま**新設してよい** (他の既存キーには触らない)。
  - `permissions.deny` / `permissions.ask` がある → 素材にしかないエントリを一覧で出し「この N 件を追記しますか?」と聞き、承認分だけ配列末尾に追加する。
  - **既存の `permissions.allow` は 1 件も削らず、並び順も変えない** (素材に `allow` は無いのでそのまま残す)。`deny` / `ask` の既存エントリも同じく保全する。
  - top-level の `ultracode` / `workflowSizeGuideline` / `statusLine` も同じく差分として提示する。`hooks` / `env` など素材に無いキーには触れない。
- マージ後は必ず `python3 -m json.tool .claude/settings.json >/dev/null` を再実行し、exit 0 を確認する。0 以外なら編集前の内容へ戻す。

## 4. mode.yml と statusline を配置する

```bash
[ -e .claude/mode.yml ] && echo "kept   .claude/mode.yml" || { cp "$CLAUDE_PLUGIN_ROOT/templates/mode.yml" .claude/mode.yml && echo "placed .claude/mode.yml"; }
for s in statusline.sh tasks-path.sh; do
  [ -e ".claude/$s" ] && echo "kept   .claude/$s" || { cp "$CLAUDE_PLUGIN_ROOT/scripts/$s" ".claude/$s" && chmod +x ".claude/$s" && echo "placed .claude/$s"; }
done
bash .claude/statusline.sh </dev/null
```

`${CLAUDE_PLUGIN_ROOT}` は settings.json では展開されない (hook / MCP など プラグインコンポーネント側だけの機能) ため、statusline はスクリプトごと導入先へ複製し、手順 3 の `statusLine.command` から相対パスで呼ぶ。最後の 1 行が出力されれば配線は成立している。

## 5. 台帳・draft・事故記録を作る

`docs/` があるリポジトリは `docs/` 配下、無ければ `.claude/` 配下を使う (台帳・draft・事故記録で同じ解決順)。

```bash
if [ -d docs ]; then BASE=docs; else BASE=.claude; fi; mkdir -p "$BASE/tasks" "$BASE/draft" "$BASE/rules-reference"; : > "$BASE/draft/.gitkeep"
[ -e "$BASE/tasks/list.md" ] || printf '# タスク台帳\n\nstatus は 未着手 / 進行中 / 完了 の 3 種。\n\n| # | status | タスク | 概要 | 依存先 | 詳細 |\n|---|--------|-------|------|-------|------|\n' > "$BASE/tasks/list.md"
[ -e "$BASE/tasks/parking-lot.md" ] || printf '# 保留タスク\n\n| # | 状態 | タスク | 保留理由 | 再開条件 | 元の設計 |\n|---|------|-------|---------|---------|---------|\n' > "$BASE/tasks/parking-lot.md"
[ -e "$BASE/rules-reference/incidents.md" ] || printf '# 事故記録\n\n1 回目はここに 1 行。2 回目で /add-rule に回す。\n\n| 日付 | 事象 | 影響 | 直し方 | 再発回数 |\n|-----|------|------|-------|--------|\n' > "$BASE/rules-reference/incidents.md"
ls "$BASE/tasks/list.md" "$BASE/tasks/parking-lot.md" "$BASE/rules-reference/incidents.md" && ls -d "$BASE/draft"
```

## 6. 利用者へ報告する

bash の出力は作業ログであって報告ではない。**最後に必ず下の型で日本語 1 通にまとめる。** `placed` は「新しく置きました」、`kept` は「すでにあったので、そのままにしました」、`diff` は「違いがあるので、変更してよいか確認します」と言い換える。`T0` / `T1` / `paths:` / `exit 0` といった内部の言葉は出さない。パスは出してよいが、何のファイルかを日本語で必ず添える。件数とパスは実測値に差し替え、すでにあったファイルが 0 件ならその 1 行ごと省く。

```
セットアップが完了しました。

✅ ルールを 5 件置きました → .claude/rules/
   ・いつも読まれるルール 2 件（作業の基本方針と、ルールの増やし方）
   ・必要なときだけ読まれるルール 3 件（タスク管理 / コード / インフラ）
✅ 安全設定を追加しました → .claude/settings.json
   本番反映や強制 push など、取り返しのつかない操作の前に確認が入ります
✅ 進め方の設定を置きました → .claude/mode.yml（いまは「確認あり」）
✅ タスク一覧表を作りました → docs/tasks/list.md
✅ 設計メモの置き場を作りました → docs/draft/
✅ 困ったことの記録帳を作りました → docs/rules-reference/incidents.md
✅ 画面下部の情報表示を有効にしました（進め方・残り容量・やること の数が見えます）

すでにあったファイルは変更していません（3 件）。

次にやること
このセッションを一度閉じて開き直すと、置いたルールが読み込まれます。
```

- 中身が違うファイルがあれば末尾に 1 行足し、指示を待ってから書き換える。例: `.claude/settings.json はすでにあり、中身が違います。足したい安全設定が 4 件あります。入れてよいですか?`
- 途中で止まったら同じ調子で「何が起きたか」「どうすればよいか」「ここまでに置いたもの」を書く。例: `⚠️ 安全設定のファイル (.claude/settings.json) が読めませんでした。書き方が壊れている可能性があります。中身を直すか、別名に退避してから /init をもう一度実行してください。ここまでに置いたもの: ルール 5 件 / タスク一覧表 / 設計メモの置き場`

## 判定できる終了条件

次の 3 つが揃った時点で `/init` は完了。揃ったことを確認したうえで、手順 6 の型で報告する。

- `ls .claude/rules/*.md` が 5 件返し、手順 1 の層判定が T0 2 本 / T1 3 本になる。
- `python3 -m json.tool .claude/settings.json` が exit 0。
- `ls .claude/rules-archive/.gitkeep .claude/mode.yml .claude/statusline.sh` と手順 5 の最終行 (台帳 / parking-lot / incidents / draft dir の 4 パス) が全部 exit 0。

## 次回セッションの宿題 (ロードの実測)

配置しただけではロードは検証できず、**同じセッションでは確認できない** (rules は起動時に読まれるため)。`/init` の終了条件には含めない。次にこのリポジトリでセッションを開いた時、冒頭で `core.md` の文言 (例: `commit 粒度`) が載っていて `tasks.md` の文言 (例: `台帳は 1 枚`) が載っておらず、台帳を Read した後に後者が載れば層は正しい。載り方が違えば該当ファイルの `paths:` を直す。
