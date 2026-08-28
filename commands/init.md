---
description: 1 回目はプラグインの rules / settings / mode.yml / CLAUDE.md / statusline / 台帳を、このプロジェクト (既定) または全プロジェクト共通 (user) へ冪等に配置する (確認は 3 問)。2 回目は grilling skill で案件を伺い、CLAUDE.md と docs/ を埋める。既存ファイルは上書きしない。
argument-hint: "[user]"
---

# /init [user]

**2 段階ある。** 1 回目は**セットアップ** (手順 0〜9)、2 回目以降は**案件ヒアリング** (手順 10 だけ実行し、手順 1〜9 は飛ばす)。どちらに進むかは手順 0 の実測で決め、**利用者に選ばせない**。第 1 段階は、素材置き場 (プラグイン本体) を読み、**手順 1 で確認のとれた配置先**へ書き込む。**手順 1 の返事をもらうまで 1 バイトも書き込まない** (手順 0 は読むだけ、手順 2 以降が書き込み)。**既存ファイルは 1 つも上書きしない。** 差分がある場合は差分を提示し、user が反映を指示したときだけ書き換える。各手順の結果は `placed` / `kept` / `diff` + パスで手元に控えるだけにし、**利用者に見せる文章は手順 9 の型でまとめる**。

## 0. 素材の置き場所といまの状態を調べる（読むだけ）

`$CLAUDE_PLUGIN_ROOT` は空で渡ることがある。空・不在ならキャッシュから探す。解決順は `$CLAUDE_PLUGIN_ROOT` → `~/.claude/plugins/cache/hirai-lite/hirai-lite/<版>/` のうち**版が最新のもの** → `~/.claude/plugins/marketplaces/hirai-lite`。下の 1 行目を**素材行**と呼び、素材を読む bash ブロックの先頭に毎回そのまま置く (ブロックごとに新しいシェルで動くため、変数は持ち越されない)。

```bash
P="${CLAUDE_PLUGIN_ROOT:-}"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"; [ -d "$P" ] || P="$HOME/.claude/plugins/marketplaces/hirai-lite"
ls -d "$P/rules" "$P/templates/settings.json" >/dev/null && echo "素材 $P (版 $(cat "$P/VERSION" 2>/dev/null))"
{ [ -d .claude/tasks ] || [ -d .claude/draft ] || [ -d .claude/rules-reference ]; } && echo "旧レイアウトあり (.claude/ の書類を /hirai-lite:update で docs/ へ移す)"; echo "台帳の置き場 docs (無ければ作る)"
for d in .claude "$HOME/.claude"; do for t in rules settings.json mode.yml statusline.sh; do [ -e "$d/$t" ] && echo "既存 $d/$t"; done; done; for c in CLAUDE.md "$HOME/.claude/CLAUDE.md"; do [ -e "$c" ] && echo "既存 $c"; done; echo "(出ていないものは未配置)"
# 第 2 段階に進むか: 4 点セットが揃った配置先があり、対応する CLAUDE.md にプレースホルダ <...> が残っている
SD=; for d in .claude "$HOME/.claude"; do n=0; for t in rules settings.json mode.yml statusline.sh; do [ -e "$d/$t" ] && n=$((n+1)); done; [ "$n" -eq 4 ] && SD="$d"; done
CM=; [ "$SD" = .claude ] && CM=CLAUDE.md; [ -n "$SD" ] && [ "$SD" != .claude ] && CM="$HOME/.claude/CLAUDE.md"
if [ -n "$CM" ] && [ -f "$CM" ] && [ "$(grep -c '<[^<>]*>' "$CM")" -gt 0 ]; then echo "第 2 段階 (ヒアリング) へ: $CM にプレースホルダ $(grep -c '<[^<>]*>' "$CM") 行"; else echo "第 1 段階 (セットアップ) へ"; fi
```

`ls -d` が失敗したら素材が見つかっていない。そこで止め、`/plugin` で入れ直してもらう。**この手順では書き込まない。** **`第 2 段階 (ヒアリング) へ` と出たら、手順 1〜9 を飛ばして手順 10 へ進む。** 判定条件は 3 つとも真であること: (1) 配置先 (`.claude/` か `~/.claude/`) に `rules` / `settings.json` / `mode.yml` / `statusline.sh` の 4 つが揃っている (2) その配置先に対応する `CLAUDE.md` がある (3) その `CLAUDE.md` に `<...>` 形式のプレースホルダが 1 行以上残っている。**プレースホルダが 0 行なら第 2 段階に入らない** (もう伺い済み)。そのときは第 1 段階を走らせ、手順 1 の「すでに一式が入っています」で終わる。

## 1. 実行前に確認する（返事を待つ）

**`AskUserQuestion` ツールを 1 回だけ呼び、下の 3 問をまとめて出す**。返事が来るまで手順 2 以降を実行しない。各問は既定にしたい選択肢を**先頭**に置き、その `label` に `(推奨)` を付ける。`description` には「選ぶと何が起きるか」を 1 行で書く。

| # | `header` | `question` | `options` (先頭が既定 / `label` — `description`) |
|---|---|---|---|
| 1 | `置き場所` | 設定一式をどこに入れますか | `このプロジェクトのみ (推奨)` — いま開いているフォルダの `.claude/` に置きます。ほかのプロジェクトには影響しません ／ `全プロジェクト共通` — ホームの `~/.claude/` に置き、このパソコンで開く全プロジェクトに効きます |
| 2 | `ultracode` | `ultracode`（深く考えて自動で手分けする。利用量が増える）を有効にしますか | `有効にする (推奨)` — 回答が丁寧になりますが、そのぶん利用量（費用）が増えます ／ `有効にしない` — 利用量は増えません。あとから `/hirai-lite:config` で有効にできます |
| 3 | `mode` | `mode`（進め方）をどちらにしますか | `normal（確認あり）(推奨)` — 重要な分かれ道で確認してから進みます。はじめて使うときはこちら ／ `loop（自動で進む）` — 確認を求めず最後まで進みます。止めたいときは「stop」と伝えます |

**書類の置き場所は聞かない。** このプロジェクトに入れるときは**常に `docs/`** を使う (無ければ作る、手順 7)。 **`AskUserQuestion` が使えないとき** (ツール不在・呼び出しに失敗した等) は、同じ 3 問を平文 1 通で送って返事を待つ (v1.5.0 までのやり方。既定を明記し「はい」の一言で 3 つとも既定で進める)。

**聞く数を減らす条件。** 当てはまる質問は `AskUserQuestion` に**含めず**、代わりにその 1 行を本文で伝える (質問が 1 つも残らなければ、**`AskUserQuestion` を呼ばずに**その 1 行だけ伝えて手順 2 へ進む)。

| 条件 | 省く質問 | 代わりに伝える 1 行 |
|---|---|---|
| 引数に `user` が付いている | 1 | 全プロジェクト共通（ホーム）に入れます。 |
| 配置先に `settings.json` がすでにある | 2 | 安全設定のファイルはすでにあります。上書きしないので、違いがあれば後でお見せします。 |
| `mode.yml` がプロジェクト側かホーム側のどちらかにすでにある（手順 0 の「既存 …/mode.yml」） | 3 | 進め方の設定はすでにあるので、そのまま使います（上書きしません）。 |
| 手順 0 で配置先の 4 つとも「既存」だった | 1〜3 すべて | すでに一式が入っています。**今回は何も上書きしません**（すべてそのまま）。違いがあれば後でお見せします。 |

質問 1 で「全プロジェクト共通」を選ばれたとき、および引数が `user` のときは、**手順 7 を丸ごと飛ばす**（台帳などはプロジェクトごとの中身なので作らない）。

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
for f in "$P"/rules/*.md; do d="$D/rules/$(basename "$f")"; if [ -e "$d" ]; then echo "kept   $d"; else cp "$f" "$d" && echo "placed $d"; fi; done
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

`ULTRA` は手順 1 の質問 2 の答え。「有効にする」(既定) なら `on`、「有効にしない」なら `off`。

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

- 無かった場合は上の `cp` で配置済み。素材は `"ultracode": true` を含み、**xhigh 推論と自動 workflow オーケストレーションが有効になってトークン消費が増える**。だから手順 1 の質問 2 で先に聞く。`off` を選ばれたときは上の `python3` が `ultracode` と `workflowSizeGuideline` の 2 キーを落とす (`permissions` と `statusLine` は残る)。
- **`user` 指定時だけ** `statusLine.command` を `$HOME` を展開した絶対パス (`bash "/…/.claude/statusline.sh"`) に書き換える。素材の `${CLAUDE_PROJECT_DIR}` は開くプロジェクトごとに変わるため、全プロジェクト共通の設定からは使えない。既存 settings.json に差分提示する場合も、`user` 指定時は同じ絶対パスの形で提案する。
- あった場合は **上書きしない**。素材と突き合わせて差分だけを提示し、承認された分だけ既存 JSON へ追加する。`permissions` キーが無ければ素材の `permissions` をそのまま**新設してよい**。`permissions.deny` / `permissions.ask` があるときは素材にしかないエントリを一覧で出し「この N 件を追記しますか?」と聞き、承認分だけ配列末尾に足す。
  - **既存の `permissions.allow` は 1 件も削らず、並び順も変えない** (素材に `allow` は無いのでそのまま残す)。`deny` / `ask` の既存エントリも同じく保全する。top-level の `ultracode` / `workflowSizeGuideline` / `statusLine` も同じく差分として提示し、**`ultracode` は利用量が増えるキーなので差分に含まれるときは「入れますか」と必ず聞く。** `hooks` / `env` など素材に無いキーには触れない。
- マージ後は必ず `python3 -m json.tool "$D/settings.json" >/dev/null` を再実行し、exit 0 を確認する。0 以外なら編集前の内容へ戻す。

## 6. mode.yml / CLAUDE.md / statusline を配置する

`MODE` は手順 1 の質問 3 の答え。「normal（確認あり）」(既定) なら `normal`、「loop（自動で進む）」なら `loop`。

**進め方の書き込み先は `$D` で決め打ちせず、`/config` と同じ `harness_mode_write_file`（すでに在る側に書く）に通す。** `$D` 基準にすると、ホーム側だけに `mode.yml` を置いている人のプロジェクトへ `.claude/mode.yml` を新設し、ホーム側を黙って覆い隠す。`user` 指定のときだけはホーム側に入れると決まっているので、そちらを直に指す。

```bash
SCOPE=; D=.claude; [ "$SCOPE" = user ] && D="$HOME/.claude"; MODE=normal
P="${CLAUDE_PLUGIN_ROOT:-}"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"; [ -d "$P" ] || P="$HOME/.claude/plugins/marketplaces/hirai-lite"
. "$P/scripts/tasks-path.sh"
if [ "$SCOPE" = user ]; then MF="$HOME/.claude/mode.yml"; else MF="$(harness_mode_write_file "$PWD")"; fi
mkdir -p "$(dirname "$MF")"
[ -e "$MF" ] && echo "kept   $MF" || { cp "$P/templates/mode.yml" "$MF" && sed -i.bak "s/^mode: .*/mode: $MODE/" "$MF" && rm -f "$MF.bak" && echo "placed $MF ($MODE)"; }
grep -c '^mode: \(normal\|loop\)$' "$MF"
C=CLAUDE.md; [ "$SCOPE" = user ] && C="$HOME/.claude/CLAUDE.md"; [ -e "$C" ] && echo "kept   $C" || { cp "$P/templates/CLAUDE.md" "$C" && echo "placed $C"; }
for s in statusline.sh tasks-path.sh; do [ -e "$D/$s" ] && echo "kept   $D/$s" || { cp "$P/scripts/$s" "$D/$s" && chmod +x "$D/$s" && echo "placed $D/$s"; }; done
bash "$D/statusline.sh" </dev/null
```

`statusline.sh` と `tasks-path.sh` の 2 本は**プラグイン所有**で、`/update` を実行すると配布版で置き換わる (中身を変えていた場合は `.bak` に退避される)。手を入れるなら別名でコピーして使う。`${CLAUDE_PLUGIN_ROOT}` は settings.json では展開されない (hook / MCP など プラグインコンポーネント側だけの機能) ため、statusline はスクリプトごと配置先へ複製し、手順 5 の `statusLine.command` から呼ぶ。最後に 2 行 (いまの状態 / 設定リンク) が出力されれば配線は成立している。進め方 (`mode.yml`) はプロジェクト側を先に見て、無ければホーム側を見る。

`CLAUDE.md` は**常時読まれる分 (T0) の 1 本**で、プロジェクト固有情報 (概要 / Tech Stack / Commands) と rules への index を持つ雛形。**無ければ黙って置き、あれば触らない** (`kept`)。質問は増やさない (手順 1 は 4 問が上限)。置き先は、このプロジェクトなら**リポジトリ直下の `CLAUDE.md`**、`user` 指定なら `~/.claude/CLAUDE.md` (`.claude/` の中ではない — Claude Code が読むのはこの 2 か所)。中身は `<...>` のプレースホルダのままなので、埋めてもらうことを手順 9 の報告で 1 行伝える。行動規範は書かない (それは `rules/core.md` の担当)。

## 7. 台帳・draft・事故記録を作る（このプロジェクトに入れるときだけ）

台帳 / 設計メモ / 事故記録は**プロジェクトごとの中身**なので、`user` 指定時は作らない。**置き場は常に `docs/`** で、無ければ作る (`docs/tasks/` `docs/draft/` `docs/rules-reference/` の 3 つ)。ただし**旧レイアウト (`.claude/tasks/` などが残っている環境) では、ここでは何も作らず `/hirai-lite:update` の移行手順 (手順 2) に回す** — `docs/` 側に新しい台帳を作ると、パス解決が `docs/` を先に見るため既存の台帳が黙って隠れる (中身は残るが誰も読まなくなる)。

```bash
SCOPE=; if [ "$SCOPE" = user ]; then echo "skip 台帳 / 設計メモ / 記録帳 (全プロジェクト共通には作らない)"; elif ls -d .claude/tasks .claude/draft .claude/rules-reference 2>/dev/null | grep -q .; then echo "skip 旧レイアウト — .claude/ の書類を /hirai-lite:update で docs/ へ移してから作る"
else BASE=docs; mkdir -p "$BASE/tasks" "$BASE/draft" "$BASE/rules-reference"; : > "$BASE/draft/.gitkeep"
[ -e "$BASE/tasks/list.md" ] || printf '# タスク台帳\n\nstatus は 未着手 / 進行中 / 完了 の 3 種。\n\n| # | status | タスク | 概要 | 依存先 | 詳細 |\n|---|--------|-------|------|-------|------|\n' > "$BASE/tasks/list.md"
[ -e "$BASE/tasks/parking-lot.md" ] || printf '# 保留タスク\n\n| # | 状態 | タスク | 保留理由 | 再開条件 | 元の設計 |\n|---|------|-------|---------|---------|---------|\n' > "$BASE/tasks/parking-lot.md"
[ -e "$BASE/rules-reference/incidents.md" ] || printf '# 事故記録\n\n1 回目はここに 1 行。2 回目で /add-rule に回す。\n\n| 日付 | 事象 | 影響 | 直し方 | 再発回数 |\n|-----|------|------|-------|--------|\n' > "$BASE/rules-reference/incidents.md"
ls "$BASE/tasks/list.md" "$BASE/tasks/parking-lot.md" "$BASE/rules-reference/incidents.md" && ls -d "$BASE/draft"
fi
```

`docs/` が新しくできたかどうかを手元に控える (手順 9 の報告で 1 行使う)。`skip 旧レイアウト` と出たときは、手順 9 の報告で書類の行を出さず、代わりに `/hirai-lite:update` を案内する 1 行を書く。

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
✅ ultracode（深く考えて自動で手分けする。利用量が増える）を有効にしました
✅ mode（進め方）の設定を置きました → .claude/mode.yml（いまは normal（確認あり））
   後から /hirai-lite:config で loop（自動で進む）に変えられます
✅ プロジェクト情報の下書きを置きました → CLAUDE.md（中身は次回に伺って埋めます）
✅ タスク一覧表を作りました → docs/tasks/list.md
✅ 設計メモの置き場を作りました → docs/draft/
✅ 困ったことの記録帳を作りました → docs/rules-reference/incidents.md
✅ statusLine（画面下部の情報表示）を有効にしました（進め方・残り容量・やること の数が見えます）

すでにあったファイルは変更していません（3 件）。

次にやること
このセッションを一度閉じて開き直すと、置いたルールが読み込まれます。そのうえで
**もう一度 /hirai-lite:init と入力してください。今度は案件のことを伺い、CLAUDE.md と
docs/ の書類を埋めます。**
```

- 質問 2 で「有効にしない」を選ばれたら、3 行目を `✅ ultracode（深く考えて自動で手分けする設定）は入れていません（利用量は増えません）` に差し替える。
- 質問 3 で `loop（自動で進む）` を選ばれたら、mode の 2 行を `✅ mode（進め方）の設定を置きました → <実際の書き込み先>（いまは loop（自動で進む））` ＋ `後から /hirai-lite:config で normal（確認あり）に戻せます。止めたいときは「stop」と伝えてください` に差し替える。**どちらを選んでも「後から /hirai-lite:config で変えられます」の 1 行は必ず残す。** パスは手順 6 の `$MF` の実測値を書く（ホーム側だった場合は `~/.claude/mode.yml` と出る）。
- `docs/` を新しく作ったときは、台帳の行の前に 1 行足す: `✅ 書類の置き場を作りました → docs/`。手順 7 が `skip 旧レイアウト` だったときは台帳まわりの 3 行を出さず、代わりに 1 行書く: `やることの一覧表などは .claude/ の下にあります。/hirai-lite:update を実行すると docs/ へ移します（中身はそのまま移動します）。`
- `CLAUDE.md` がすでにあった場合は、その 2 行を出さず「そのままにしたもの」に数える (中身は 1 バイトも触っていない)。手順 1 で「すでに一式が入っています」と伝えた再実行のときは、1 行目を `すでに入っている一式を確認しました。変更はありません。` にし、`✅` 行を出さずに「そのままにしたもの」の件数と一覧だけを書く。
- `user` 指定時は 1 行目を `すべてのプロジェクトで使えるようにしました。` にし、パスを `~/.claude/…` に差し替え、**タスク一覧表 / 設計メモの置き場 / 困ったことの記録帳の 3 行を省く**。代わりに 1 行足す: `やることの一覧表と設計メモは、プロジェクトごとの中身なので作っていません（各プロジェクトで /hirai-lite:init を実行すると作られます）。`
- 手順 8 の警告が出ていたら、報告の末尾にその全文をそのまま貼る。中身が違うファイルがあれば末尾に 1 行足し、指示を待ってから書き換える。例: `.claude/settings.json はすでにあり、中身が違います。足したい安全設定が 4 件あります。入れてよいですか?`
- 途中で止まったら同じ調子で「何が起きたか」「どうすればよいか」「ここまでに置いたもの」を書く。例: `⚠️ 安全設定のファイル (.claude/settings.json) が読めませんでした。書き方が壊れている可能性があります。中身を直すか、別名に退避してから /init をもう一度実行してください。ここまでに置いたもの: ルール 5 件 / タスク一覧表 / 設計メモの置き場`

## 10. 案件を伺い、CLAUDE.md と docs/ を埋める（第 2 段階）

手順 0 が `第 2 段階 (ヒアリング) へ` と出したときだけ実行する。**手順 1〜8 は飛ばす。**

### 10-1. 伺う

**質問を自分で組み立てない。同梱の `grilling` skill を使う。** `Skill` ツールで `grilling` を呼び、目的として「**このプロジェクトのゴールから詳細までを明らかにする**」を渡す。**質問は列挙せず、明らかにしたい観点だけを渡す** (design tree は `grilling` が組む): ゴール / 背景 / スコープ（何を作らないかを含む）/ 関係者と体制 / ドメイン用語 / 要件 / 技術構成 / データの持ち方 / 関連リポジトリ / いまの進捗 / よく使うコマンド。`grilling` は前提が確定した質問群 (frontier) を毎ラウンドまとめて出し、各問に推奨回答を添える。**事実は自分で調べる** — リポジトリの中身・言語・依存・既存コマンドは、利用者に聞かずに読んで確かめる (`package.json` / `Makefile` / `pyproject.toml` / `go.mod` / `README` / `.github/workflows/` など)。利用者に聞くのは**決定**だけ。frontier が空になるまで続ける。

`grilling` が呼べないとき (skill が読み込まれていない等) は、`AskUserQuestion` で最低限の 3 問 (このプロジェクトは何をするものか / 使っている技術 / よく使うコマンド) を 1 回で聞き、その答えだけで先へ進む。

### 10-2. CLAUDE.md のプレースホルダを埋める

伺った内容で `<...>` を実値に置換する (置き場は手順 0 の `$CM`)。**行動規範は書かない** (それは `rules/core.md` の担当)。冒頭の `> 汎用ハーネステンプレート。…` の引用ブロックは丸ごと消す (もう雛形ではない)。

- 「プロジェクト概要」「Tech Stack」「Commands」の 3 節を実値にする。**伺えていない項目は行ごと消す** (`<URL>` のまま残さない)。
- 「Rules index」は触らない。「Documents index」は 10-3 で実際に作ったファイルの行だけ残し、作らなかった行は消す。増えた書類があれば行を足す。
- 終わったら `grep -c '<[^<>]*>' "$CM"` が **0** であることを確かめる。0 なら次回以降の `/init` は第 2 段階に入らない。

### 10-3. docs/ に書類を作る

**空のファイルを量産しない。伺って中身が得られたものだけ作る。** 得られていない章のために見出しだけのファイルを置かない (このハーネスの「既定は入れない」原則に反する)。置き場は手順 7 の `$BASE` (通常 `docs`)。

| ファイル | 中身 | 作る条件 |
|---|---|---|
| `$BASE/overview.md` | ゴール / 背景 / スコープ（**何を作らないか**を含む）/ 関係者と体制 / ドメイン用語 / 関連リポジトリ | ゴールが 1 文で書ける |
| `$BASE/requirements.md` | 要件（機能・非機能） | 要件が 1 件以上挙がった |
| `$BASE/architecture.md` | 構成 / データの持ち方 / その技術を選んだ理由 | 構成・データ・技術判断のどれかが 1 件以上挙がった |
| `$BASE/tasks/list.md` | 台帳（既存。**上書きしない**）。**進捗もここで表す** | やることが挙がったら行を追加する |
| `$BASE/draft/<slug>.md` | 設計メモ | これから作るものが具体化している。雛形は `templates/draft.md` |

各ファイルは**得られた項目だけ**を書く（挙がらなかった見出しは置かない）。`list.md` は既存の表に行を足すだけにする (`status` は `未着手`)。**進捗表 (`status.md` の類) は新しく作らない** — 台帳の `status` 列がその役目。`draft/` に起こしたものは、承認を経てから `list.md` の task にする (`/hirai-lite:new-task`)。

### 10-4. 報告する

```
案件のことを伺えたので、書類にまとめました。

✅ CLAUDE.md を埋めました（プロジェクト概要 / Tech Stack / Commands）
✅ ゴールと背景をまとめました → docs/overview.md
✅ 要件をまとめました → docs/requirements.md
✅ やることを 3 件、一覧表に足しました → docs/tasks/list.md

伺えなかったところは書類を作っていません（構成の判断 → docs/architecture.md）。
あとから話していただければ足します。

次にやること: docs/overview.md を読んで、違うところがあれば教えてください。
```

実際に作ったファイルだけを `✅` で挙げ、**作らなかったものは「作っていません」の 1 行にまとめる**（見出しだけのファイルを置いたと誤解させない）。`<...>` / `T0` / `frontmatter` といった内部の言葉は出さない。

## 判定できる終了条件

### 第 1 段階（手順 0〜9）

次の 4 つが揃った時点で完了。**大前提として、手順 1 の `AskUserQuestion` を呼んで返事を得てから手順 2 以降を実行していること** (質問を全部省ける条件に当てはまった場合は、`AskUserQuestion` を呼ばずその 1 行を伝えてから実行したこと)。揃ったことを確認したうえで、手順 9 の型で報告する (`$D` は手順 2 で決めた配置先)。

- `ls "$D"/rules/*.md` が 5 件返し、手順 3 の層判定が T0 2 本 / T1 3 本になる。
- `python3 -m json.tool "$D/settings.json"` が exit 0。質問 2 で「有効にしない」を選ばれた場合は加えて `grep -c 'ultracode\|workflowSizeGuideline' "$D/settings.json"` が 0。
- `ls "$D/rules-archive/.gitkeep" "$D/statusline.sh"` が exit 0。進め方は `ls "$MF"` が exit 0 で `grep -c '^mode: \(normal\|loop\)$' "$MF"` が 1 (質問 3 で選ばれた値、既存を残したときはその値のまま)。**`$MF` がホーム側だったときは `.claude/mode.yml` が作られていないこと** (`ls .claude/mode.yml` が exit 1)。CLAUDE.md も置き場に在る (`ls CLAUDE.md`、`user` 指定なら `ls "$HOME/.claude/CLAUDE.md"`)。このプロジェクトに入れたときは加えて `ls -d docs` と手順 7 の最終行 (台帳 / parking-lot / incidents / draft dir の 4 パス) も exit 0 (手順 7 が `skip 旧レイアウト` だった場合を除く)。
- 手順 8 を実行済み。警告が出た場合は報告に転記済み。

### 第 2 段階（手順 10）

- `grep -c '<[^<>]*>' "$CM"` が 0（プレースホルダが 1 つも残っていない）。
- `$CM` の「Documents index」に載っている行のファイルが**すべて実在する**（`ls` が exit 0）。
- 作ったと報告したファイルがすべて実在し、**中身が見出しだけのファイルが 1 つも無い**。

## 次回セッションの宿題 (ロードの実測)

配置しただけではロードは検証できず、**同じセッションでは確認できない** (rules は起動時に読まれるため)。`/init` の終了条件には含めない。次にこのリポジトリでセッションを開いた時、冒頭で `core.md` の文言 (例: `commit 粒度`) が載っていて `tasks.md` の文言 (例: `台帳は 1 枚`) が載っておらず、台帳を Read した後に後者が載れば層は正しい。載り方が違えば該当ファイルの `paths:` を直す。

ホーム側 (`user` 指定) に置いた場合、`~/.claude/rules/` が読まれること自体は[公式ドキュメント](https://code.claude.com/docs/en/memory.md)に明記があるが、`paths:` 付きファイルがホーム側でも「該当ファイルを開いた時だけ」読まれるかは明記が無い。上の宿題で実測して確かめる。
