---
description: 設定の確認と変更。mode（進め方）/ ultracode / 常時読まれる量 / 置き場所 / statusLine（画面下部の情報表示）/ 更新の確認 / 更新の自動化 を一覧し、選ばれた項目だけ書き換える。
argument-hint: [mode normal|loop]
---

# /config [mode normal|loop]

いまの設定を一覧で見せ、変えたいものだけ書き換える。**変える前に必ず「どのファイルが変わるか」を伝えてから実行する。** 出力は平易な日本語だけにし、内部の呼び名 (層 / frontmatter / scope / exit code など) は出さない。

**表記のきまり。** 設定の名前と値は **`<正式名>（<短い解説>）`** の形で出す (正式名だけだと意味が伝わらず、解説だけだと設定ファイルの中身と結び付かない)。`mode（進め方）` / `normal（確認あり）` / `loop（自動で進む）` / `ultracode（深く考えて自動で手分けする。利用量が増える）` / `statusLine（画面下部の情報表示）`。同じ 1 通のなかで 2 回目からは正式名だけでよい。

## 読み取り (ここでは 1 バイトも書き換えない)
置き場所は人によって 2 通りある (このプロジェクトの `.claude/` と全プロジェクト共通の `~/.claude/`)。**解決を自分で組み立てず**、セッション冒頭・画面下部と同じ共通ライブラリに任せる。
```bash
. "$CLAUDE_PLUGIN_ROOT/scripts/tasks-path.sh"
R="$(harness_rules_dir "$PWD")"; D="$(dirname "$R")"
m="$(harness_mode "$PWD")"; case "$m" in normal) m="normal（確認あり）" ;; loop) m="loop（自動で進む）" ;; esac
echo "mode（進め方）: $m / 設定ファイル: $(harness_mode_write_file "$PWD")"
echo "設定一式の置き場: $D / やること一覧: $(harness_tasks_file "$PWD" || echo '(まだありません)')"
grep -q '"ultracode"[[:space:]]*:[[:space:]]*true' "$D/settings.json" 2>/dev/null && echo "ultracode: 有効" || echo "ultracode: 無効"
grep -q '"statusLine"' "$D/settings.json" 2>/dev/null && echo "statusLine（画面下部の情報表示）: 有効" || echo "statusLine（画面下部の情報表示）: 無効"
for f in CLAUDE.md "$HOME/.claude/CLAUDE.md" "$R"/*.md; do
  [ -f "$f" ] || continue
  head -5 "$f" | grep -q '^paths:' || wc -c "$f"
done | awk '{s+=$1} END {print "常時読まれる量:", int(s/3)}'
. "$CLAUDE_PLUGIN_ROOT/scripts/update-check.sh"
[ "${HARNESS_UPDATE_CHECK:-on}" = off ] && echo "更新の確認: 無効" || echo "更新の確認: 有効"
date -r "$(harness_update_cache_dir "$CLAUDE_PLUGIN_ROOT")/stamp" '+%Y-%m-%d %H:%M' 2>/dev/null || echo "最後に確認: まだありません"
# 7-a プラグイン本体の自動更新は **Claude Code 本体の機能**（マーケットプレイス単位）。既定は無効。
#     置き場は settings.json の extraKnownMarketplaces.hirai-lite.autoUpdate で、
#     /plugin の Marketplaces タブの切り替えと同じ場所を読む（ここで独自の仕組みを作らない）。
au="無効"; auf=""
for f in .claude/settings.local.json .claude/settings.json "$HOME/.claude/settings.json"; do
  [ -f "$f" ] || continue
  v="$(python3 -c 'import json,sys
try: d = json.load(open(sys.argv[1]))
except Exception: sys.exit(0)
m = (d.get("extraKnownMarketplaces") or {}).get("hirai-lite")
print("" if not m else ("on" if m.get("autoUpdate") else "off"))' "$f" 2>/dev/null)"
  [ -n "$v" ] && { auf="$f"; [ "$v" = on ] && au="有効"; break; }
done
echo "プラグイン本体の自動更新: $au${auf:+ / 設定ファイル: $auf}"
# 7-b 更新後の入れ替え（ハーネス側）。既定は無効。mode（進め方）と同じ mode.yml に載る。
as="$(harness_auto_sync "$PWD")"; case "$as" in on|true|yes) as="有効" ;; *) as="無効" ;; esac
echo "更新後の入れ替え: $as / 設定ファイル: $(harness_mode_write_file "$PWD")"
```

## 引数なし — 一覧を出す
下の型に**実測値**を埋めて出す (推測で埋めない)。

```
いまの設定

1. mode（進め方）      normal（確認あり）— 重要な分かれ道で聞いてから進みます
2. ultracode           有効（深く考えて自動で手分けする。そのぶん利用量が増えます）
3. 常時読まれる量      3,663 ／ 警告 6,000 ／ 上限 10,000
4. 置き場所            このプロジェクトのみ（.claude/）
                       やること一覧 → docs/tasks/list.md
5. statusLine（画面下部の情報表示）  有効
6. 更新の確認          有効（最後に確認したのは 2026-08-27 10:12）
7. 更新の自動化        プラグイン本体: 無効 ／ 更新後の入れ替え: 無効
                       どちらも既定は無効です（更新は動きの変更なので、黙って変えません）

番号か項目名を言ってもらえれば変更します（例:「1 を loop に」）。
```

- 1 は `loop` なら `loop（自動で進む）— 確認を求めず最後まで進みます`（`normal` / `loop` 以外の値はそのまま出す）。2 は無効なら `無効（利用量は増えません）`
- 3 は警告を超えていたら 1 行足す: `警告線を超えています。ルールを 1 件減らすことを勧めます`
- 4 は置き場が `~/.claude` なら `全プロジェクト共通（~/.claude/）`。台帳が無ければ `やること一覧 → まだありません`
- 6 は一度も調べていなければ `有効（まだ一度も確認していません）`
- 7 はどちらか一方でも有効なら、その行を `有効` に差し替えて 2 行目を `プラグイン本体が新しくなると自動で入れ替わります` にする

## 変更する
変えられるのは 1・2・5・6・7 の 5 つ。**3 と 4 は表示のみ**（3 は `/hirai-lite:add-rule`、4 は `/hirai-lite:init` の担当）。どれも「これから変わるファイル」を 1 行見せてから実行し、終わったら結果を 1 行で報告する。

### 1. mode（進め方）
`/hirai-lite:config mode loop` のように引数で直接指定してもよい（`進め方 確認あり` / `進め方 自動` のような日本語でも受け付ける）。書き込み先は**すでに在る側**で、両方に無いときだけこのプロジェクト側に作る（共通側に置いている人のプロジェクトへ新しく作ると、共通側を黙って覆い隠す）。
```bash
. "$CLAUDE_PLUGIN_ROOT/scripts/tasks-path.sh"
f="$(harness_mode_write_file "$PWD")"; echo "変えるファイル: $f"
harness_yml_set "$f" mode normal   # 自動で進めるときは loop
grep -c '^mode: \(normal\|loop\)$' "$f"
```

`harness_yml_set` は **その 1 行だけ**を書き換える（`mode.yml` には 7 の `auto_sync` も載るので、丸ごと書き直すともう片方が消える）。

報告書式: `normal（確認あり）にしました → <パス>。重要な分かれ道でひとこと確認してから進みます` ／ `loop（自動で進む）にしました → <パス>。確認を求めず最後まで進みます。止めたいときは「stop」`。書き込み先が `~/.claude/mode.yml` だったときだけ 1 行足す: `この設定はすべてのプロジェクトに効きます`

**`loop`（自動で進む）の間の振る舞い。** 作り方の選び方・branch 名・commit の件名・ビルドが通るまでの試行錯誤は聞かずに決める。止まるのは 3 つだけ（「stop」と言われた / やることが終わった / 続けられないエラー）。ただし新しい設計を足すとき・決めた内容から外れるとき・元に戻せない操作（`main` への push / PR の取り込み / 本番反映 / DB の作り替え / 秘密情報）は自動でも必ず確認を取る。作業を任せた相手を待つ間は別の作業を進め、会話の使用量が 80% に達したら `/hirai-lite:state save` を実行する。

### 2. ultracode（深く考えて自動で手分けする。利用量が増える）
`$D/settings.json` の `ultracode` を切り替える。**有効にすると利用量（費用）が増える。** 無効にするときは `ultracode` と `workflowSizeGuideline` の 2 つを外す。書き換えたら `python3 -m json.tool "$D/settings.json"` を通し、失敗したら編集前へ戻す。

### 5. statusLine（画面下部の情報表示）／ 6. 更新の確認
5 は `$D/settings.json` の `statusLine`（消すと画面下部の 2 行が出なくなる）。6 は環境変数 `HARNESS_UPDATE_CHECK=off` で止まる（設定ファイルは変えない）。どちらも変える前にファイル名か環境変数名を伝える。

### 7. 更新の自動化（既定は無効。有効にするかは利用者が決める）

**先に必ず伝える。** このプラグインは自動処理と決まりごとを配るので、更新は**動きの変更**になる。有効にすると、次にセッションを開いたとき、断りなく新しい版に入れ替わる。**迷うなら無効のままでよい**（`/hirai-lite:update` でいつでも手動更新できる）。2 つは独立しているので、片方だけ有効にしてもよい。

**7-a プラグイン本体の自動更新 — これは Claude Code 本体の機能で、ハーネスは何もしない。**
`/plugin` → **Marketplaces** → `hirai-lite` → **Enable auto-update** で切り替える（元に戻すのは同じ場所の **Disable auto-update**）。**この案内を第一に出す。** Claude Code が起動後の背景で（最大 10 分の遅延を挟んで）マーケットプレイスの一覧とプラグイン本体を新しくする。**動いているセッションはそのまま**で、反映は `/reload-plugins` か次回起動から。

画面を開かずに切り替えたいと言われたときだけ、上の読み取りで見つかった `settings.json`（見つからなければ `.claude/settings.json`）の `extraKnownMarketplaces.hirai-lite.autoUpdate` を `true` / `false` に書き換える。**これは `/plugin` の切り替えと同じ場所**で、書いた値は起動時に Claude Code 側へ取り込まれる。書き換えたら `python3 -m json.tool "$f"` を通し、失敗したら編集前へ戻す。

```bash
f=.claude/settings.json   # 読み取りで見つかったファイルに差し替える
python3 - "$f" <<'PY'
import json, sys
p = sys.argv[1]; d = json.load(open(p))
m = d.setdefault("extraKnownMarketplaces", {}).setdefault(
    "hirai-lite", {"source": {"source": "github", "repo": "thirai-classlab/hirai-method-lite"}})
m["autoUpdate"] = True          # 止めるときは False
json.dump(d, open(p, "w"), indent=2, ensure_ascii=False)
PY
python3 -m json.tool "$f" >/dev/null && echo "OK $f"
```

報告書式: `プラグイン本体の自動更新を有効にしました → <パス>。次に開いたときから、Claude Code が背景で新しい版に入れ替えます（反映は入れ替えの次の起動から）`

**7-b 更新後の入れ替え — こちらがハーネスの受け持ち。**
プラグイン本体が新しくなっても、`/hirai-lite:init` で**導入先へ複製された** 3 本（`statusline.sh` / `tasks-path.sh` / `context-usage.sh`）は古いまま残る。有効にすると、**プラグインの版が変わった回のセッション冒頭だけ**、その 3 本を配布版に揃え、何件入れ替えたかを 1 行で報告する（中身が違うものは `.bak` に控えてから）。**決まりごと・安全設定・`CLAUDE.md`・やることの一覧表には触らない。** 版が同じ回は何もしない（手を入れた複製も、その版のうちは上書きされない）。

```bash
. "$CLAUDE_PLUGIN_ROOT/scripts/tasks-path.sh"
f="$(harness_mode_write_file "$PWD")"; echo "変えるファイル: $f"
harness_yml_set "$f" auto_sync on   # 止めるときは off
harness_auto_sync "$PWD"
```

報告書式: `更新後の入れ替えを有効にしました → <パス>。プラグインが新しくなった回に、画面下部などのスクリプトを自動で最新にします（元の内容は .bak に残します）` ／ 無効にしたときは `更新後の入れ替えを無効にしました → <パス>。これまでどおり /hirai-lite:update で手動更新してください`。書き込み先が `~/.claude/mode.yml` だったときだけ 1 行足す: `この設定はすべてのプロジェクトに効きます`

## 判定できる終了条件

- 引数なしのとき、7 項目すべてに実測値が入っている。
- 7 の 2 つの値が、`extraKnownMarketplaces.hirai-lite.autoUpdate`（無ければ無効）と `harness_auto_sync "$PWD"` の実測値と一致している。
- 1・2・5 の表示が `<正式名>（<解説>）` の形になっている（`normal` / `loop` / `ultracode` / `statusLine` の文字が出ている）。
- 変更したときは、変更したファイルのパスが報告に入っており、`mode` なら `harness_mode "$PWD"` が指定した値と一致する。
