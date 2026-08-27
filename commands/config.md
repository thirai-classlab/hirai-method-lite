---
description: 設定の確認と変更。mode（進め方）/ ultracode / 常時読まれる量 / 置き場所 / statusLine（画面下部の情報表示）/ 更新の確認 を一覧し、選ばれた項目だけ書き換える。
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

番号か項目名を言ってもらえれば変更します（例:「1 を loop に」）。
```

- 1 は `loop` なら `loop（自動で進む）— 確認を求めず最後まで進みます`（`normal` / `loop` 以外の値はそのまま出す）。2 は無効なら `無効（利用量は増えません）`
- 3 は警告を超えていたら 1 行足す: `警告線を超えています。ルールを 1 件減らすことを勧めます`
- 4 は置き場が `~/.claude` なら `全プロジェクト共通（~/.claude/）`。台帳が無ければ `やること一覧 → まだありません`
- 6 は一度も調べていなければ `有効（まだ一度も確認していません）`

## 変更する
変えられるのは 1・2・5・6 の 4 つ。**3 と 4 は表示のみ**（3 は `/hirai-lite:add-rule`、4 は `/hirai-lite:init` の担当）。どれも「これから変わるファイル」を 1 行見せてから実行し、終わったら結果を 1 行で報告する。

### 1. mode（進め方）
`/hirai-lite:config mode loop` のように引数で直接指定してもよい（`進め方 確認あり` / `進め方 自動` のような日本語でも受け付ける）。書き込み先は**すでに在る側**で、両方に無いときだけこのプロジェクト側に作る（共通側に置いている人のプロジェクトへ新しく作ると、共通側を黙って覆い隠す）。
```bash
. "$CLAUDE_PLUGIN_ROOT/scripts/tasks-path.sh"
f="$(harness_mode_write_file "$PWD")"; echo "変えるファイル: $f"
mkdir -p "$(dirname "$f")"; printf 'mode: normal\n' > "$f"   # 自動で進めるときは loop
grep -c '^mode: \(normal\|loop\)$' "$f"
```

報告書式: `normal（確認あり）にしました → <パス>。重要な分かれ道でひとこと確認してから進みます` ／ `loop（自動で進む）にしました → <パス>。確認を求めず最後まで進みます。止めたいときは「stop」`。書き込み先が `~/.claude/mode.yml` だったときだけ 1 行足す: `この設定はすべてのプロジェクトに効きます`

**`loop`（自動で進む）の間の振る舞い。** 作り方の選び方・branch 名・commit の件名・ビルドが通るまでの試行錯誤は聞かずに決める。止まるのは 3 つだけ（「stop」と言われた / やることが終わった / 続けられないエラー）。ただし新しい設計を足すとき・決めた内容から外れるとき・元に戻せない操作（`main` への push / PR の取り込み / 本番反映 / DB の作り替え / 秘密情報）は自動でも必ず確認を取る。作業を任せた相手を待つ間は別の作業を進め、会話の使用量が 80% に達したら `/hirai-lite:state save` を実行する。

### 2. ultracode（深く考えて自動で手分けする。利用量が増える）
`$D/settings.json` の `ultracode` を切り替える。**有効にすると利用量（費用）が増える。** 無効にするときは `ultracode` と `workflowSizeGuideline` の 2 つを外す。書き換えたら `python3 -m json.tool "$D/settings.json"` を通し、失敗したら編集前へ戻す。

### 5. statusLine（画面下部の情報表示）／ 6. 更新の確認
5 は `$D/settings.json` の `statusLine`（消すと画面下部の 2 行が出なくなる）。6 は環境変数 `HARNESS_UPDATE_CHECK=off` で止まる（設定ファイルは変えない）。どちらも変える前にファイル名か環境変数名を伝える。

## 判定できる終了条件

- 引数なしのとき、6 項目すべてに実測値が入っている。
- 1・2・5 の表示が `<正式名>（<解説>）` の形になっている（`normal` / `loop` / `ultracode` / `statusLine` の文字が出ている）。
- 変更したときは、変更したファイルのパスが報告に入っており、`mode` なら `harness_mode "$PWD"` が指定した値と一致する。
