---
description: プラグインの rules / settings / mode.yml / statusline / 台帳を、このプロジェクト (既定) または全プロジェクト共通 (user) へ冪等に配置する。書き込む前に 3 つだけ確認する。既存ファイルは上書きしない。
argument-hint: "[user]"
---

# /init [user]

素材置き場 (プラグイン本体) を読み、**手順 1 で確認のとれた配置先**へ書き込む。**手順 1 の返事をもらうまで 1 バイトも書き込まない** (手順 0 は読むだけ、手順 2 以降が書き込み)。**既存ファイルは 1 つも上書きしない。** 差分がある場合は差分を提示し、user が反映を指示したときだけ書き換える。各手順の結果は `placed` / `kept` / `diff` + パスで手元に控えるだけにし、**利用者に見せる文章は手順 9 の型でまとめる**。

## 0. 素材の置き場所といまの状態を調べる（読むだけ）

`$CLAUDE_PLUGIN_ROOT` は空で渡ることがある。空・不在ならキャッシュから探す。解決順は `$CLAUDE_PLUGIN_ROOT` → `~/.claude/plugins/cache/hirai-lite/hirai-lite/<版>/` のうち**版が最新のもの** → `~/.claude/plugins/marketplaces/hirai-lite`。下の 1 行目を**素材行**と呼び、素材を読む bash ブロックの先頭に毎回そのまま置く (ブロックごとに新しいシェルで動くため、変数は持ち越されない)。

```bash
P="${CLAUDE_PLUGIN_ROOT:-}"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"; [ -d "$P" ] || P="$HOME/.claude/plugins/marketplaces/hirai-lite"
ls -d "$P/rules" "$P/templates/settings.json" >/dev/null && echo "素材 $P (版 $(cat "$P/VERSION" 2>/dev/null))"
[ -d docs ] && echo "docs あり" || echo "docs なし"
for d in .claude "$HOME/.claude"; do for t in rules settings.json mode.yml statusline.sh; do [ -e "$d/$t" ] && echo "既存 $d/$t"; done; done; echo "(出ていないものは未配置)"
```

`ls -d` が失敗したら素材が見つかっていない。そこで止め、`/plugin` で入れ直してもらう。**この手順では書き込まない。**

## 1. 実行前に確認する（返事を待つ）

**手順 0 の結果を埋めた下の型を 1 通で送り、返事を待つ。** 返事が来るまで手順 2 以降を実行しない。「はい」「そのままで」と答えられたら 3 つとも既定 (このプロジェクトだけ / 手順 0 が出した置き場所 / 有効にする) で進める。質問 2 の `docs/` の有無と置き場所は、**手順 0 で実際に調べた結果**を書く (「ある場合は…ない場合は…」と両論で書かない)。

```
セットアップの前に 3 つだけ確認させてください。
そのままで良ければ「はい」とお答えください。

1. どこに入れますか
   ・このプロジェクトだけ（既定）
   ・全プロジェクト共通（ホームに置きます）

2. ファイルの置き場所
   このプロジェクトには docs/ フォルダが<ある / ない>ので、
   一覧表などは <docs/ か .claude/ の実際の方> に作ります。これでよいですか。

3. 濃いめに考える設定を有効にしますか
   有効にすると回答が丁寧になりますが、そのぶん利用量（費用）が増えます。
   ・有効にする（既定）
   ・有効にしない
```

**聞く数を減らす条件。** 当てはまる質問は番号ごと省き、代わりにその 1 行を質問文の下に添える (質問が 1 つも残らなければ、質問文を送らずその 1 行だけ伝えて手順 2 へ進む)。

| 条件 | 省く質問 | 代わりに添える 1 行 |
|---|---|---|
| 引数に `user` が付いている | 1 | 全プロジェクト共通（ホーム）に入れます。 |
| 引数が `user` / 質問 1 で「全プロジェクト共通」を選んだ | 2 | 一覧表などはプロジェクトごとの中身なので、今回は作りません。 |
| 配置先に `settings.json` がすでにある | 3 | 安全設定のファイルはすでにあります。上書きしないので、違いがあれば後でお見せします。 |
| 手順 0 で配置先の 4 つとも「既存」だった | 1〜3 すべて | すでに一式が入っています。**今回は何も上書きしません**（すべてそのまま）。違いがあれば後でお見せします。 |
| （常に） | 進め方 (`mode.yml`) は聞かない | 既定の「確認あり」で置き、後から変えられることを手順 9 の報告で 1 行伝える |

## 2. 配置先を決める

手順 1 の答え (引数 `user` も同じ) で `SCOPE` を確定する。「このプロジェクトだけ」(既定) は `SCOPE=` を空のままにし、配置先 `$D` は `.claude`（いま開いているプロジェクトだけに効く）。「全プロジェクト共通」/ 引数 `user` は `SCOPE=user` とし、`$D` は `$HOME/.claude`（このパソコンの全プロジェクトに効く）。

**以降の bash ブロックは毎回この 1 行から始める**（`SCOPE=` を確定値に埋めてから実行する）。

```bash
SCOPE=; D=.claude; [ "$SCOPE" = user ] && D="$HOME/.claude"; mkdir -p "$D"; echo "配置先 $D"
```

## 3. rules を配置する

```bash
SCOPE=; D=.claude; [ "$SCOPE" = user ] && D="$HOME/.claude"; mkdir -p "$D/rules"
P="${CLAUDE_PLUGIN_ROOT:-}"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"; [ -d "$P" ] || P="$HOME/.claude/plugins/marketplaces/hirai-lite"
for f in "$P"/rules/*.md; do
  d="$D/rules/$(basename "$f")"
  if [ -e "$d" ]; then echo "kept   $d"; else cp "$f" "$d" && echo "placed $d"; fi
done
for f in "$D"/rules/*.md; do sed -n '1,10p' "$f" | grep -q '^paths:' && echo "T1 $f" || echo "T0 $f"; done
```

**5 本すべて**を判定する。期待値は `T0` が `_meta.md` `core.md` の 2 本、`T1` が `tasks.md` `code.md` `ops.md` の 3 本。T1 のはずのファイルが `T0` と出たら `paths:` frontmatter が欠けている。その 1 本を消して cp をやり直す。

## 4. 退避先を作る

失効したルールの移動先 (T3)。ロードされない。空ディレクトリは git に載らないため `.gitkeep` を置く。

```bash
SCOPE=; D=.claude; [ "$SCOPE" = user ] && D="$HOME/.claude"
mkdir -p "$D/rules-archive" && : > "$D/rules-archive/.gitkeep" && ls -a "$D/rules-archive"
```

## 5. settings.json を配置・マージする

`ULTRA` は手順 1 の質問 3 の答え。「有効にする」(既定) なら `on`、「有効にしない」なら `off`。

```bash
SCOPE=; D=.claude; [ "$SCOPE" = user ] && D="$HOME/.claude"; ULTRA=on
P="${CLAUDE_PLUGIN_ROOT:-}"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"; [ -d "$P" ] || P="$HOME/.claude/plugins/marketplaces/hirai-lite"
cat "$P/templates/settings.json"   # 素材。差分提示の元にする
if [ -e "$D/settings.json" ]; then echo "kept   $D/settings.json (下記手順で差分を提示する)"; else
  cp "$P/templates/settings.json" "$D/settings.json" && echo "placed $D/settings.json"
  [ "$ULTRA" = off ] && python3 -c 'import json,sys;p=sys.argv[1];d=json.load(open(p));[d.pop(k,None) for k in ("ultracode","workflowSizeGuideline")];json.dump(d,open(p,"w"),ensure_ascii=False,indent=2)' "$D/settings.json" && echo "removed ultracode / workflowSizeGuideline"
  [ "$D" = .claude ] || python3 -c 'import json,os,sys;p=sys.argv[1];d=json.load(open(p));d["statusLine"]={"type":"command","command":"bash \""+os.path.expanduser("~/.claude/statusline.sh")+"\""};json.dump(d,open(p,"w"),ensure_ascii=False,indent=2)' "$D/settings.json"
fi
python3 -m json.tool "$D/settings.json" >/dev/null && echo "settings.json は妥当な JSON"
```

- 無かった場合は上の `cp` で配置済み。素材は `"ultracode": true` を含み、**xhigh 推論と自動 workflow オーケストレーションが有効になってトークン消費が増える**。だから手順 1 の質問 3 で先に聞く。`off` を選ばれたときは上の `python3` が `ultracode` と `workflowSizeGuideline` の 2 キーを落とす (`permissions` と `statusLine` は残る)。
- **`user` 指定時だけ** `statusLine.command` を `$HOME` を展開した絶対パス (`bash "/…/.claude/statusline.sh"`) に書き換える。素材の `${CLAUDE_PROJECT_DIR}` は開くプロジェクトごとに変わるため、全プロジェクト共通の設定からは使えない。既存 settings.json に差分提示する場合も、`user` 指定時は同じ絶対パスの形で提案する。
- あった場合は **上書きしない**。素材と突き合わせて差分だけを提示し、承認された分だけ既存 JSON へ追加する。
  - `permissions` キーが無い → 素材の `permissions` をそのまま**新設してよい** (他の既存キーには触らない)。
  - `permissions.deny` / `permissions.ask` がある → 素材にしかないエントリを一覧で出し「この N 件を追記しますか?」と聞き、承認分だけ配列末尾に追加する。
  - **既存の `permissions.allow` は 1 件も削らず、並び順も変えない** (素材に `allow` は無いのでそのまま残す)。`deny` / `ask` の既存エントリも同じく保全する。
  - top-level の `ultracode` / `workflowSizeGuideline` / `statusLine` も同じく差分として提示する。**`ultracode` は利用量が増えるキーなので、差分に含まれるときは「入れますか」と必ず聞く。** `hooks` / `env` など素材に無いキーには触れない。
- マージ後は必ず `python3 -m json.tool "$D/settings.json" >/dev/null` を再実行し、exit 0 を確認する。0 以外なら編集前の内容へ戻す。

## 6. mode.yml と statusline を配置する

```bash
SCOPE=; D=.claude; [ "$SCOPE" = user ] && D="$HOME/.claude"
P="${CLAUDE_PLUGIN_ROOT:-}"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"; [ -d "$P" ] || P="$HOME/.claude/plugins/marketplaces/hirai-lite"
[ -e "$D/mode.yml" ] && echo "kept   $D/mode.yml" || { cp "$P/templates/mode.yml" "$D/mode.yml" && echo "placed $D/mode.yml"; }
for s in statusline.sh tasks-path.sh; do
  [ -e "$D/$s" ] && echo "kept   $D/$s" || { cp "$P/scripts/$s" "$D/$s" && chmod +x "$D/$s" && echo "placed $D/$s"; }
done
bash "$D/statusline.sh" </dev/null
```

`statusline.sh` と `tasks-path.sh` の 2 本は**プラグイン所有**で、`/update` を実行すると配布版で置き換わる (中身を変えていた場合は `.bak` に退避される)。手を入れるなら別名でコピーして使う。`${CLAUDE_PLUGIN_ROOT}` は settings.json では展開されない (hook / MCP など プラグインコンポーネント側だけの機能) ため、statusline はスクリプトごと配置先へ複製し、手順 5 の `statusLine.command` から呼ぶ。最後に 2 行 (いまの状態 / 設定リンク) が出力されれば配線は成立している。進め方 (`mode.yml`) はプロジェクト側を先に見て、無ければホーム側を見る。

## 7. 台帳・draft・事故記録を作る（このプロジェクトに入れるときだけ）

台帳 / 設計メモ / 事故記録は**プロジェクトごとの中身**なので、`user` 指定時は作らない。`docs/` があるリポジトリは `docs/` 配下、無ければ `.claude/` 配下を使う (3 つとも同じ解決順)。手順 1 の質問 2 で示した置き場所と一致することを確かめる。

```bash
SCOPE=; if [ "$SCOPE" = user ]; then echo "skip 台帳 / 設計メモ / 記録帳 (全プロジェクト共通には作らない)"; else
if [ -d docs ]; then BASE=docs; else BASE=.claude; fi; mkdir -p "$BASE/tasks" "$BASE/draft" "$BASE/rules-reference"; : > "$BASE/draft/.gitkeep"
[ -e "$BASE/tasks/list.md" ] || printf '# タスク台帳\n\nstatus は 未着手 / 進行中 / 完了 の 3 種。\n\n| # | status | タスク | 概要 | 依存先 | 詳細 |\n|---|--------|-------|------|-------|------|\n' > "$BASE/tasks/list.md"
[ -e "$BASE/tasks/parking-lot.md" ] || printf '# 保留タスク\n\n| # | 状態 | タスク | 保留理由 | 再開条件 | 元の設計 |\n|---|------|-------|---------|---------|---------|\n' > "$BASE/tasks/parking-lot.md"
[ -e "$BASE/rules-reference/incidents.md" ] || printf '# 事故記録\n\n1 回目はここに 1 行。2 回目で /add-rule に回す。\n\n| 日付 | 事象 | 影響 | 直し方 | 再発回数 |\n|-----|------|------|-------|--------|\n' > "$BASE/rules-reference/incidents.md"
ls "$BASE/tasks/list.md" "$BASE/tasks/parking-lot.md" "$BASE/rules-reference/incidents.md" && ls -d "$BASE/draft"
fi
```

## 8. 二重ロードを調べる

同じルールがプロジェクト側とホーム側の両方にあると、同じ文章が 2 回読み込まれて容量を無駄に使う。**引数に関わらず毎回**実行する。引数の順番は固定。

```bash
P="${CLAUDE_PLUGIN_ROOT:-}"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"; [ -d "$P" ] || P="$HOME/.claude/plugins/marketplaces/hirai-lite"
bash "$P/scripts/scope-check.sh" .claude "$HOME/.claude"
```

無出力なら重なりなし。警告が出たら**その全文をそのまま手順 9 の報告の末尾に載せる**。勝手に消さない (どちらを残すかは利用者が決める)。

## 9. 利用者へ報告する

bash の出力は作業ログであって報告ではない。**最後に必ず下の型で日本語 1 通にまとめる。** `placed` は「新しく置きました」、`kept` は「すでにあったので、そのままにしました」、`diff` は「違いがあるので、変更してよいか確認します」と言い換える。`T0` / `T1` / `paths:` / `exit 0` / `scope` といった内部の言葉は出さない。パスは出してよいが、何のファイルかを日本語で必ず添える。件数とパスは実測値に差し替え、すでにあったファイルが 0 件ならその 1 行ごと省く。

```
セットアップが完了しました。

✅ ルールを 5 件置きました → .claude/rules/
   ・いつも読まれるルール 2 件（作業の基本方針と、ルールの増やし方）
   ・必要なときだけ読まれるルール 3 件（タスク管理 / コード / インフラ）
✅ 安全設定を追加しました → .claude/settings.json
   本番反映や強制 push など、取り返しのつかない操作の前に確認が入ります
✅ 濃いめに考える設定を有効にしました（そのぶん利用量が増えます）
✅ 進め方の設定を置きました → .claude/mode.yml（いまは「確認あり」）
   後から /hirai-lite:config で「いちいち確認しない」に変えられます
✅ タスク一覧表を作りました → docs/tasks/list.md
✅ 設計メモの置き場を作りました → docs/draft/
✅ 困ったことの記録帳を作りました → docs/rules-reference/incidents.md
✅ 画面下部の情報表示を有効にしました（進め方・残り容量・やること の数が見えます）

すでにあったファイルは変更していません（3 件）。

次にやること
このセッションを一度閉じて開き直すと、置いたルールが読み込まれます。
```

- 質問 3 で「有効にしない」を選ばれたら、3 行目を `✅ 濃いめに考える設定は入れていません（利用量は増えません）` に差し替える。
- 手順 1 で「すでに一式が入っています」と伝えた再実行のときは、1 行目を `すでに入っている一式を確認しました。変更はありません。` にし、`✅` 行を出さずに「そのままにしたもの」の件数と一覧だけを書く。
- `user` 指定時は 1 行目を `すべてのプロジェクトで使えるようにしました。` にし、パスを `~/.claude/…` に差し替え、**タスク一覧表 / 設計メモの置き場 / 困ったことの記録帳の 3 行を省く**。代わりに 1 行足す: `やることの一覧表と設計メモは、プロジェクトごとの中身なので作っていません（各プロジェクトで /hirai-lite:init を実行すると作られます）。`
- 手順 8 の警告が出ていたら、報告の末尾にその全文をそのまま貼る。
- 中身が違うファイルがあれば末尾に 1 行足し、指示を待ってから書き換える。例: `.claude/settings.json はすでにあり、中身が違います。足したい安全設定が 4 件あります。入れてよいですか?`
- 途中で止まったら同じ調子で「何が起きたか」「どうすればよいか」「ここまでに置いたもの」を書く。例: `⚠️ 安全設定のファイル (.claude/settings.json) が読めませんでした。書き方が壊れている可能性があります。中身を直すか、別名に退避してから /init をもう一度実行してください。ここまでに置いたもの: ルール 5 件 / タスク一覧表 / 設計メモの置き場`

## 判定できる終了条件

次の 4 つが揃った時点で `/init` は完了。**大前提として、手順 1 を送って返事を得てから手順 2 以降を実行していること** (質問を全部省ける条件に当てはまった場合は、その 1 行を伝えてから実行したこと)。揃ったことを確認したうえで、手順 9 の型で報告する (`$D` は手順 2 で決めた配置先)。

- `ls "$D"/rules/*.md` が 5 件返し、手順 3 の層判定が T0 2 本 / T1 3 本になる。
- `python3 -m json.tool "$D/settings.json"` が exit 0。質問 3 で「有効にしない」を選ばれた場合は加えて `grep -c 'ultracode\|workflowSizeGuideline' "$D/settings.json"` が 0。
- `ls "$D/rules-archive/.gitkeep" "$D/mode.yml" "$D/statusline.sh"` が exit 0。このプロジェクトに入れたときは加えて手順 7 の最終行 (台帳 / parking-lot / incidents / draft dir の 4 パス) も exit 0。
- 手順 8 を実行済み。警告が出た場合は報告に転記済み。

## 次回セッションの宿題 (ロードの実測)

配置しただけではロードは検証できず、**同じセッションでは確認できない** (rules は起動時に読まれるため)。`/init` の終了条件には含めない。次にこのリポジトリでセッションを開いた時、冒頭で `core.md` の文言 (例: `commit 粒度`) が載っていて `tasks.md` の文言 (例: `台帳は 1 枚`) が載っておらず、台帳を Read した後に後者が載れば層は正しい。載り方が違えば該当ファイルの `paths:` を直す。

ホーム側 (`user` 指定) に置いた場合、`~/.claude/rules/` が読まれること自体は[公式ドキュメント](https://code.claude.com/docs/en/memory.md)に明記があるが、`paths:` 付きファイルがホーム側でも「該当ファイルを開いた時だけ」読まれるかは明記が無い。上の宿題で実測して確かめる。
