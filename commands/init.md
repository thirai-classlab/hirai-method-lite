---
description: プラグインの rules / settings / mode.yml / statusline / 台帳を、このプロジェクト (既定) または全プロジェクト共通 (user) へ冪等に配置する。既存ファイルは上書きしない。
argument-hint: "[user]"
---

# /init [user]

`$CLAUDE_PLUGIN_ROOT` を素材置き場、**引数で決まる配置先**を書き込み先として実行する。**既存ファイルは 1 つも上書きしない。** 差分がある場合は差分を提示し、user が反映を指示したときだけ書き換える。各手順の結果は `placed` / `kept` / `diff` + パスで手元に控えるだけにし、**利用者に見せる文章は手順 7 の型でまとめる**。

## 0. 配置先を決める

| 引数 | 配置先 (`$D`) | 効く範囲 |
|---|---|---|
| なし (既定) | `.claude`（いま開いているプロジェクト） | このプロジェクトだけ |
| `user` | `$HOME/.claude` | このパソコンの全プロジェクト |

**以降の bash ブロックは毎回この 1 行から始める** (ブロックごとに新しいシェルで動くため、変数は持ち越されない)。

```bash
D=.claude; [ "$ARGUMENTS" = user ] && D="$HOME/.claude"; mkdir -p "$D"; echo "配置先 $D"
```

## 1. rules を配置する

```bash
D=.claude; [ "$ARGUMENTS" = user ] && D="$HOME/.claude"; mkdir -p "$D/rules"
for f in "$CLAUDE_PLUGIN_ROOT"/rules/*.md; do
  d="$D/rules/$(basename "$f")"
  if [ -e "$d" ]; then echo "kept   $d"; else cp "$f" "$d" && echo "placed $d"; fi
done
for f in "$D"/rules/*.md; do sed -n '1,10p' "$f" | grep -q '^paths:' && echo "T1 $f" || echo "T0 $f"; done
```

**5 本すべて**を判定する。期待値は `T0` が `_meta.md` `core.md` の 2 本、`T1` が `tasks.md` `code.md` `ops.md` の 3 本。T1 のはずのファイルが `T0` と出たら `paths:` frontmatter が欠けている。その 1 本を消して cp をやり直す。

## 2. 退避先を作る

失効したルールの移動先 (T3)。ロードされない。空ディレクトリは git に載らないため `.gitkeep` を置く。

```bash
D=.claude; [ "$ARGUMENTS" = user ] && D="$HOME/.claude"
mkdir -p "$D/rules-archive" && : > "$D/rules-archive/.gitkeep" && ls -a "$D/rules-archive"
```

## 3. settings.json を配置・マージする

```bash
D=.claude; [ "$ARGUMENTS" = user ] && D="$HOME/.claude"
cat "$CLAUDE_PLUGIN_ROOT/templates/settings.json"   # 素材。差分提示の元にする
if [ -e "$D/settings.json" ]; then echo "kept   $D/settings.json (下記手順で差分を提示する)"; else
  cp "$CLAUDE_PLUGIN_ROOT/templates/settings.json" "$D/settings.json" && echo "placed $D/settings.json"
  [ "$D" = .claude ] || python3 -c 'import json,os,sys;p=sys.argv[1];d=json.load(open(p));d["statusLine"]={"type":"command","command":"bash \""+os.path.expanduser("~/.claude/statusline.sh")+"\""};json.dump(d,open(p,"w"),ensure_ascii=False,indent=2)' "$D/settings.json"
fi
python3 -m json.tool "$D/settings.json" >/dev/null && echo "settings.json は妥当な JSON"
```

- 無かった場合は上の `cp` で配置済み。素材は `"ultracode": true` を含むため **xhigh 推論と自動 workflow オーケストレーションが有効になり、トークン消費が増える** (不要なら配置後にこのキーを削除するか `false` にする)。
- **`user` 指定時だけ** `statusLine.command` を `$HOME` を展開した絶対パス (`bash "/…/.claude/statusline.sh"`) に書き換える。素材の `${CLAUDE_PROJECT_DIR}` は開くプロジェクトごとに変わるため、全プロジェクト共通の設定からは使えない。既存 settings.json に差分提示する場合も、`user` 指定時は同じ絶対パスの形で提案する。
- あった場合は **上書きしない**。素材と突き合わせて差分だけを提示し、承認された分だけ既存 JSON へ追加する。
  - `permissions` キーが無い → 素材の `permissions` をそのまま**新設してよい** (他の既存キーには触らない)。
  - `permissions.deny` / `permissions.ask` がある → 素材にしかないエントリを一覧で出し「この N 件を追記しますか?」と聞き、承認分だけ配列末尾に追加する。
  - **既存の `permissions.allow` は 1 件も削らず、並び順も変えない** (素材に `allow` は無いのでそのまま残す)。`deny` / `ask` の既存エントリも同じく保全する。
  - top-level の `ultracode` / `workflowSizeGuideline` / `statusLine` も同じく差分として提示する。`hooks` / `env` など素材に無いキーには触れない。
- マージ後は必ず `python3 -m json.tool "$D/settings.json" >/dev/null` を再実行し、exit 0 を確認する。0 以外なら編集前の内容へ戻す。

## 4. mode.yml と statusline を配置する

```bash
D=.claude; [ "$ARGUMENTS" = user ] && D="$HOME/.claude"
[ -e "$D/mode.yml" ] && echo "kept   $D/mode.yml" || { cp "$CLAUDE_PLUGIN_ROOT/templates/mode.yml" "$D/mode.yml" && echo "placed $D/mode.yml"; }
for s in statusline.sh tasks-path.sh; do
  [ -e "$D/$s" ] && echo "kept   $D/$s" || { cp "$CLAUDE_PLUGIN_ROOT/scripts/$s" "$D/$s" && chmod +x "$D/$s" && echo "placed $D/$s"; }
done
bash "$D/statusline.sh" </dev/null
```

`statusline.sh` と `tasks-path.sh` の 2 本は**プラグイン所有**で、`/update` を実行すると配布版で置き換わる (中身を変えていた場合は `.bak` に退避される)。手を入れるなら別名でコピーして使う。

`${CLAUDE_PLUGIN_ROOT}` は settings.json では展開されない (hook / MCP など プラグインコンポーネント側だけの機能) ため、statusline はスクリプトごと配置先へ複製し、手順 3 の `statusLine.command` から呼ぶ。最後の 1 行が出力されれば配線は成立している。進め方 (`mode.yml`) はプロジェクト側を先に見て、無ければホーム側を見る。

## 5. 台帳・draft・事故記録を作る（このプロジェクトに入れるときだけ）

台帳 / 設計メモ / 事故記録は**プロジェクトごとの中身**なので、`user` 指定時は作らない。`docs/` があるリポジトリは `docs/` 配下、無ければ `.claude/` 配下を使う (3 つとも同じ解決順)。

```bash
if [ "$ARGUMENTS" = user ]; then echo "skip 台帳 / 設計メモ / 記録帳 (全プロジェクト共通には作らない)"; else
if [ -d docs ]; then BASE=docs; else BASE=.claude; fi; mkdir -p "$BASE/tasks" "$BASE/draft" "$BASE/rules-reference"; : > "$BASE/draft/.gitkeep"
[ -e "$BASE/tasks/list.md" ] || printf '# タスク台帳\n\nstatus は 未着手 / 進行中 / 完了 の 3 種。\n\n| # | status | タスク | 概要 | 依存先 | 詳細 |\n|---|--------|-------|------|-------|------|\n' > "$BASE/tasks/list.md"
[ -e "$BASE/tasks/parking-lot.md" ] || printf '# 保留タスク\n\n| # | 状態 | タスク | 保留理由 | 再開条件 | 元の設計 |\n|---|------|-------|---------|---------|---------|\n' > "$BASE/tasks/parking-lot.md"
[ -e "$BASE/rules-reference/incidents.md" ] || printf '# 事故記録\n\n1 回目はここに 1 行。2 回目で /add-rule に回す。\n\n| 日付 | 事象 | 影響 | 直し方 | 再発回数 |\n|-----|------|------|-------|--------|\n' > "$BASE/rules-reference/incidents.md"
ls "$BASE/tasks/list.md" "$BASE/tasks/parking-lot.md" "$BASE/rules-reference/incidents.md" && ls -d "$BASE/draft"
fi
```

## 6. 二重ロードを調べる

同じルールがプロジェクト側とホーム側の両方にあると、同じ文章が 2 回読み込まれて容量を無駄に使う。**引数に関わらず毎回**実行する。引数の順番は固定。

```bash
bash "$CLAUDE_PLUGIN_ROOT/scripts/scope-check.sh" .claude "$HOME/.claude"
```

無出力なら重なりなし。警告が出たら**その全文をそのまま手順 7 の報告の末尾に載せる**。勝手に消さない (どちらを残すかは利用者が決める)。

## 7. 利用者へ報告する

bash の出力は作業ログであって報告ではない。**最後に必ず下の型で日本語 1 通にまとめる。** `placed` は「新しく置きました」、`kept` は「すでにあったので、そのままにしました」、`diff` は「違いがあるので、変更してよいか確認します」と言い換える。`T0` / `T1` / `paths:` / `exit 0` / `scope` といった内部の言葉は出さない。パスは出してよいが、何のファイルかを日本語で必ず添える。件数とパスは実測値に差し替え、すでにあったファイルが 0 件ならその 1 行ごと省く。

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

- `user` 指定時は 1 行目を `すべてのプロジェクトで使えるようにしました。` にし、パスを `~/.claude/…` に差し替え、**タスク一覧表 / 設計メモの置き場 / 困ったことの記録帳の 3 行を省く**。代わりに 1 行足す: `やることの一覧表と設計メモは、プロジェクトごとの中身なので作っていません（各プロジェクトで /hirai-lite:init を実行すると作られます）。`
- 手順 6 の警告が出ていたら、報告の末尾にその全文をそのまま貼る。
- 中身が違うファイルがあれば末尾に 1 行足し、指示を待ってから書き換える。例: `.claude/settings.json はすでにあり、中身が違います。足したい安全設定が 4 件あります。入れてよいですか?`
- 途中で止まったら同じ調子で「何が起きたか」「どうすればよいか」「ここまでに置いたもの」を書く。例: `⚠️ 安全設定のファイル (.claude/settings.json) が読めませんでした。書き方が壊れている可能性があります。中身を直すか、別名に退避してから /init をもう一度実行してください。ここまでに置いたもの: ルール 5 件 / タスク一覧表 / 設計メモの置き場`

## 判定できる終了条件

次の 4 つが揃った時点で `/init` は完了。揃ったことを確認したうえで、手順 7 の型で報告する (`$D` は手順 0 で決めた配置先)。

- `ls "$D"/rules/*.md` が 5 件返し、手順 1 の層判定が T0 2 本 / T1 3 本になる。
- `python3 -m json.tool "$D/settings.json"` が exit 0。
- `ls "$D/rules-archive/.gitkeep" "$D/mode.yml" "$D/statusline.sh"` が exit 0。引数なしのときは加えて手順 5 の最終行 (台帳 / parking-lot / incidents / draft dir の 4 パス) も exit 0。
- 手順 6 を実行済み。警告が出た場合は報告に転記済み。

## 次回セッションの宿題 (ロードの実測)

配置しただけではロードは検証できず、**同じセッションでは確認できない** (rules は起動時に読まれるため)。`/init` の終了条件には含めない。次にこのリポジトリでセッションを開いた時、冒頭で `core.md` の文言 (例: `commit 粒度`) が載っていて `tasks.md` の文言 (例: `台帳は 1 枚`) が載っておらず、台帳を Read した後に後者が載れば層は正しい。載り方が違えば該当ファイルの `paths:` を直す。

ホーム側 (`user` 指定) に置いた場合、`~/.claude/rules/` が読まれること自体は[公式ドキュメント](https://code.claude.com/docs/en/memory.md)に明記があるが、`paths:` 付きファイルがホーム側でも「該当ファイルを開いた時だけ」読まれるかは明記が無い。上の宿題で実測して確かめる。
