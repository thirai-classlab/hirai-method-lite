---
description: ハーネス (プラグイン hirai-lite) を最新版に更新し、旧レイアウトの書類を docs/ へ移し、rules を再配置し、プラグイン所有の 3 ファイルを入れ替えて、VERSION で版が上がったことを検証する。
---

# /update

**最優先の注意: ユーザーのカスタマイズを壊さない。** 導入先の `.claude/` にあるファイルは所有者で 2 種に分かれる。**この区別が更新の全体像**。

| 種別 | 対象 | 更新時の扱い |
|---|---|---|
| プラグイン所有 | `statusline.sh` / `tasks-path.sh` / `context-usage.sh` | **配布版で上書きする**（中身が違えば `.bak` に控えを取ってから） |
| 利用者所有 | `rules/*.md` / `settings.json` / `mode.yml` / 台帳 (`list.md` `parking-lot.md`) / `CLAUDE.md` / `docs/` | **上書きしない** |

配置先はプロジェクト側 (`.claude/`) と全プロジェクト共通 (`$HOME/.claude/`) の 2 通りある (`/init` に `user` を付けたかで決まる)。**どちらに置いたかを決め打ちしない。** 手順 4 は両方を見て、**すでに在る側だけ**を入れ替える。`.claude/rules/` は `/add-rule` で育てる利用者の資産なので 1 件も書き換えない。新しい rules を取り込みたいときだけ、取り込む 1 本を自分で消してから手順 3 の `/init` を実行する。
**語の使い分け（表示も報告もこれで統一する）。** `移動` は中身が元の場所から消える操作 (`mv`) だけに使う。`控えを作成` / `複製` はコピー (`cp`) で、**元のファイルはそのまま残る**。混ぜて書くと、利用者は自分の資産が消えたと受け取る。

## 素材行 — プラグイン本体の場所を解決する 1 行

`$CLAUDE_PLUGIN_ROOT` は**空で渡ることがある**。空のまま `"$CLAUDE_PLUGIN_ROOT/VERSION"` と書くと `/VERSION` を読みに行って失敗し、版の比較・`scripts/` の読み込み・smoke・終了条件が**全部空振りする**（v1.14.0 の `/update` が実環境で動かなかった原因）。解決順は `$CLAUDE_PLUGIN_ROOT` → `~/.claude/plugins/cache/hirai-lite/hirai-lite/<版>/` のうち**版が最新のもの** → `~/.claude/plugins/marketplaces/hirai-lite`。`/init` の手順 0 と**同じ 1 行**を使う。下の 1 行目を**素材行**と呼び、素材を読む bash ブロックの先頭に毎回そのまま置く（ブロックごとに新しいシェルで動くため変数は持ち越されない）。以降は解決済みの `$P` だけを使う。

## 手順 0: 現在の版と rules の控えを取る

```bash
P="${CLAUDE_PLUGIN_ROOT:-}"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"; [ -d "$P" ] || P="$HOME/.claude/plugins/marketplaces/hirai-lite"
echo "更新前の版 $(cat "$P/VERSION" 2>/dev/null || echo 不明)  (素材 $P)"
B="${TMPDIR:-/tmp}/claude-harness-lite/rules-backup-$(date +%Y%m%d-%H%M%S)"; mkdir -p "$B"
[ -d .claude/rules ]         && cp -R .claude/rules         "$B/rules.project" && echo "控えを作成 (コピー) .claude/rules → $B/rules.project"
[ -d "$HOME/.claude/rules" ] && cp -R "$HOME/.claude/rules" "$B/rules.home"    && echo "控えを作成 (コピー) ~/.claude/rules → $B/rules.home"
echo "元のルールはそのまま残ります。控えは一時領域にあるので、パソコンを再起動すると消えます。"
ls -d .claude/rules "$HOME/.claude/rules" 2>/dev/null; true   # 元が残っていることの確認
```

- `更新前の版` が `不明` なら素材が見つかっていない。そこで止め、`/plugin` で入れ直してもらう。出た値を「更新前の版」として控え、手順 5 で比べる。
- **控えはコピーであって移動ではない。** 元の `rules/` は 1 バイトも動かない（最終行の `ls` で確認できる）。置き場は更新の控えと同じ `${TMPDIR:-/tmp}/claude-harness-lite/` の下。**一時領域なので再起動で消える**。長く残したいものは別の場所へコピーする。この 1 行は報告にも入れる。

## 手順 1: プラグインを更新する

```
/plugin marketplace update hirai-lite
/plugin update hirai-lite@hirai-lite
```

- **2 行とも必要。** 1 行目は配布元の控えを取り直すだけで、これを飛ばすと 2 行目は古い控えを見て「最新です」と答える。
- 入れ替えは**再起動で反映される**。Claude Code を開き直してから次へ進む。commands / hooks / agents / MCP サーバー定義はこの入れ替えで新しくなる。導入先の `.claude/` は手順 2〜4 で扱う。
- ターミナルから `claude plugin update` を使う場合、**scope の既定は `user`**。入れた範囲が違うと `Plugin "hirai-lite" is not installed at scope user` で失敗するので `--scope local` / `--scope project` を付ける (どの範囲に入っているかは `claude plugin list` の `Scope:` 行)。画面の中から `/plugin` で実行する場合は指定不要。

## 手順 2: 書類を docs/ へ移す（旧レイアウトのときだけ）

**プロジェクトの書類は常に `docs/` に置く。** v1.7.0 までに導入した環境は台帳などが `.claude/` の下にあり、`CLAUDE.md` の書類一覧 (`docs/…`) と食い違ったままになる。ここで `docs/` へ移して 1 通りに揃える。移すのは下の 3 つのフォルダの中身だけで、**`mv`（移動）であって複製ではない**（中身はそのまま移る）。

| 移動元 | 移動先 | 主な中身 |
|---|---|---|
| `.claude/tasks/` | `docs/tasks/` | `list.md`（やることの一覧表） / `parking-lot.md`（保留の一覧表） / `task-<id>-<slug>.md` |
| `.claude/draft/` | `docs/draft/` | 設計メモ `<slug>.md` |
| `.claude/rules-reference/` | `docs/rules-reference/` | `incidents.md`（困ったことの記録帳）ほか背景資料 |

**フォルダごと `mv` せず 1 件ずつ移す。** 移動先のフォルダが既にあるとフォルダごとの `mv` は入れ子（`docs/tasks/tasks/`）を作るうえ、1 件ごとの重複判定ができない。`.claude/state/`（作業の控え）は書類ではないので移さない。**移動先に同名のファイルが既にある場合は移さない。** 上書きすると利用者が書いた中身が消える。その 1 件は動かさずに両方残し、報告に挙げてどちらを残すかを利用者に決めてもらう。

### 2-1. 何があるかを調べる（読むだけ・書き込まない）

```bash
for d in .claude/tasks .claude/draft .claude/rules-reference; do
  [ -d "$d" ] || continue
  for f in "$d"/* "$d"/.[!.]*; do
    [ -f "$f" ] || continue
    [ "$(basename "$f")" = .gitkeep ] && continue
    echo "--- $f ($(wc -l < "$f" | tr -d ' ') 行)"; sed -n '1,15p' "$f"
  done
done
```

**何も出なければ移行は不要**（すでに `docs/` を使っている）。手順 3 へ進む。出てきたものは利用者が書いた中身なので、**移す前にここで目を通す**（行数と冒頭を控え、手順 6 の報告で件数を書く）。

### 2-2. 移す

```bash
P="${CLAUDE_PLUGIN_ROOT:-}"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"; [ -d "$P" ] || P="$HOME/.claude/plugins/marketplaces/hirai-lite"
moved=""; kept=""
mv1() {  # mv1 <移動元> <移動先>: 移動先に在れば移さずに控える (上書きしない)
  [ -e "$1" ] || return 0
  if [ -e "$2" ]; then kept="$kept  $1 (移動先 $2 が既にある)\n"; return 0; fi
  mkdir -p "$(dirname "$2")" && mv "$1" "$2" && moved="$moved  $1 → $2\n"
}
mvdir() {  # mvdir <移動元 dir> <移動先 dir>: 中身を 1 件ずつ移す (.gitkeep はハーネスが置いた目印なので移さない)
  [ -d "$1" ] || return 0; mkdir -p "$2"
  for f in "$1"/* "$1"/.[!.]*; do
    [ -e "$f" ] || continue
    [ "$(basename "$f")" = .gitkeep ] || mv1 "$f" "$2/$(basename "$f")"
  done
}
mvdir .claude/tasks           docs/tasks
mvdir .claude/draft           docs/draft
mvdir .claude/rules-reference docs/rules-reference
# 空になった置き場だけ片付ける (.gitkeep は中身と数えない)
for d in .claude/tasks .claude/draft .claude/rules-reference; do
  [ -d "$d" ] && [ -z "$(ls -A "$d" | grep -v '^\.gitkeep$')" ] && rm -rf "$d" && echo "空になったので削除 $d"
done
printf '移した:\n%b' "${moved:-  なし\n}"; printf '移さなかった:\n%b' "${kept:-  なし\n}"
ls -A docs/tasks docs/draft docs/rules-reference 2>/dev/null
bash "$P/scripts/scope-check.sh" .claude "$HOME/.claude" .
```

- `mv1` は**移動先に在るものを 1 バイトも触らない**。`移さなかった` に出た分は両方残っているので、中身を見比べてどちらを残すかを利用者に決めてもらう（勝手に消さない）。
- 最後の `scope-check.sh` は、台帳が `docs/` と `.claude/` の両方に残っていないかの検査。警告が出たら**その全文をそのまま手順 6 の報告の末尾に載せる**。移動したものは手順 6 の報告で「どこからどこへ移したか」を平易な日本語で必ず伝える。

## 手順 3: rules を再配置する

**rules はプラグイン更新では導入先に配られない。** 更新後に必ず `/hirai-lite:init` を実行する（全プロジェクト共通 `~/.claude/rules/` に入れている場合は `/hirai-lite:init user`）。どちらに入れたか分からないときは `ls ~/.claude/rules/*.md .claude/rules/*.md 2>/dev/null` で確かめる（両方に出たら二重ロードなので、`/init` の警告に従ってどちらか一方を消す）。
`/init` は既存ファイルを 1 つも上書きしない。新しい rules を取り込むには、取り込みたいファイルを rules から先に削除してから `/init` を実行する。手順 0 の控えと `diff -ru "$B/rules.project" .claude/rules`（ホーム側なら `diff -ru "$B/rules.home" "$HOME/.claude/rules"`）で突き合わせ、自分の変更が消えていないかを確認する。

## 手順 4: プラグイン所有の 3 ファイルを入れ替える

`statusline.sh` と `tasks-path.sh` と `context-usage.sh` はプラグインの `scripts/` の複製であり、利用者が編集する前提のファイルではない。`/init` は既存を残すため、この 3 本だけはここで入れ替える。`context-usage.sh` は v1.10.0 で足した context 使用率の共通ライブラリで、**`statusline.sh` と同じディレクトリに無いと画面下部と自動処理が別々の使用率を出す**（v1.9.0 の不具合）。v1.9.0 以前から使っている場合はまだ置かれていないので、`statusline.sh` が在る側にだけ新しく置く。**中身が配布版と違う場合は上書きせず、先に `.bak` へ控えを取る**（コピーなので、戻したいときは `.bak` から書き戻せる）。
**置いていない場所に新しく作らない。** プロジェクト側とホーム側の両方を見て、**すでに在るものだけ**を入れ替える（片方に決め打ちすると、`/init user` で入れた人はホーム側が古いまま残り、使われないファイルがプロジェクト側に増える）。入れ替えそのものは共通ライブラリの `harness_sync_owned_scripts` 1 本に集約してある（セッション冒頭の自動入れ替えと**同じ関数**を通す。手順書と自動処理で作法が離れないようにするため）。`force` を渡すと、設定に関係なく必ず実行し、1 件ずつ作業ログを出す。

```bash
P="${CLAUDE_PLUGIN_ROOT:-}"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"; [ -d "$P" ] || P="$HOME/.claude/plugins/marketplaces/hirai-lite"
. "$P/scripts/update-check.sh"
harness_sync_owned_scripts "$P" "$PWD" force
for D in .claude "$HOME/.claude"; do
  [ -e "$D/statusline.sh" ] && bash "$D/statusline.sh" </dev/null && echo
done
```

- `same` / `updated` が 1 件も出ない場合は、手順 3 の `/init` がまだ済んでいない。手順 3 に戻る。
- 最後に 2 行出力されれば、入れ替え後も画面下部の表示は動いている。出力が無い / エラーになる場合は `cp <その statusline.sh>.bak <その statusline.sh>` で戻し、内容を報告する。
- `.bak` を作ったときは手順 6 の報告に必ず 1 行入れる。作っていなければ触れない。**この 3 本以外には触れない。**

## 手順 5: 版が上がったことを検証する

```bash
P="${CLAUDE_PLUGIN_ROOT:-}"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"; [ -d "$P" ] || P="$HOME/.claude/plugins/marketplaces/hirai-lite"
cat "$P/VERSION"
bash "$P/tests/smoke.sh"
git status --short
```

- `VERSION` が手順 0 で控えた値より新しくなっていること。smoke が全 case PASS / exit 0 であること（FAIL が出たら更新を止め、内容を報告する）。`git status --short` に `CLAUDE.md` `docs/` `.claude/rules/` の変更が出ていないこと。
  版が変わらない場合は、既に最新か、`/plugin update` の後に再起動していない。`claude plugin list` で導入済みの版を確認する。

## 手順 6: 利用者へ報告する

bash の出力は作業ログであって報告ではない。**最後に必ず下の型で日本語 1 通にまとめる。** `updated` は「最新版にしました」、`same` は「すでに最新でした」、`.bak` は「元の内容を …bak に保存しました」と言い換える。内部の言葉は出さない。**コピーを「退避」「移した」と書かない**（利用者は自分の資産が消えたと受け取る）。件数とパスは実測値に差し替え、該当しない行は省く。

```
ハーネスを v0.4.0 から v0.5.0 に更新しました。

✅ コマンド・自動処理・エージェント・外部ツール接続を最新版にしました
✅ 念のためルールの控え（コピー）を取りました → <手順 0 の $B>
   元のルールはそのまま残っています。控えは一時領域なので、パソコンを再起動すると消えます
✅ 書類の置き場を docs/ にそろえました（中身はそのまま移動しています）
   ・やることの一覧表 .claude/tasks/list.md → docs/tasks/list.md（12 行）
   ・設計メモ 2 件 .claude/draft/ → docs/draft/
   空になった .claude/tasks/ .claude/draft/ は片付けました
✅ statusLine（画面下部の情報表示）のスクリプトを最新版にしました
   変更されていたため、元の内容を .claude/statusline.sh.bak に保存しました
✅ タスク一覧の置き場所を調べるスクリプトと、context（会話の入れ物）の使用率を出すスクリプトを最新版にしました
✅ ルール・設定・mode（進め方）の設定・タスク一覧はそのままにしました（あなたが育てたものなので触りません）
✅ 自己チェック 10 項目すべて問題なしでした

次にやること
新しいルールも取り込みたい場合は、入れ替えたいルールを .claude/rules/ から消してから /hirai-lite:init を実行してください。
```

- 移行が起きなかった場合（すでに `docs/` を使っている / `.claude/` に書類が無い）は、**書類の置き場の行を丸ごと省く**。移した件数とパスは手順 2 の実測値に差し替える（行数は 2-1 で控えた値）。
- **移さなかったものがあれば必ず 1 行足す**（消していないこと・どちらを残すか決めてほしいことを伝える）。例: `⚠️ .claude/tasks/list.md は移していません。docs/tasks/list.md が既にあり、上書きすると中身が消えるためです。いまは両方残っています。読まれるのは docs/ 側です。中身を見比べて、残すほうを教えてください。`
- `scope-check.sh` が警告を出していたら、報告の末尾にその全文をそのまま貼る。途中で止まったら同じ調子で「何が起きたか」「どうすればよいか」「ここまでにやったこと」を書く。

## 手動でやらずに済ませたいとき（既定は無効）

手順 1 と手順 4 は、それぞれ**自動にできる**。どちらも既定は無効で、`/hirai-lite:config` の項目 7 から切り替える。**有効にするかどうかは利用者が決める**ので、こちらから勝手に有効化しない。

| 手順 | 自動にする方法 | 受け持ち |
|---|---|---|
| 1（本体の入れ替え） | `/plugin` → Marketplaces → `hirai-lite` → **Enable auto-update** | **Claude Code 本体の機能。** 起動後の背景で最大 10 分の遅延を挟んで実行し、反映は `/reload-plugins` か次回起動から |
| 4（複製した 3 本） | `/hirai-lite:config` → 7 → 更新後の入れ替えを有効 | ハーネス。プラグインの版が変わった回のセッション冒頭だけ実行する |

手順 2（書類の移動）と手順 3（rules の再配置）は**自動にしない**。どちらも利用者が書いた中身に関わる判断（同名衝突をどちらに寄せるか / どのルールを新しくするか）を含むので、必ず人が見る。

## 更新検知について

SessionStart で `[harness] 更新あり vX → vY (/update で適用)` が出た時だけ実行すればよい。検知は 24 時間に 1 回・背景通信で、オフラインでも起動を遅らせない。止めたい場合は `HARNESS_UPDATE_CHECK=off` を環境変数に設定する。
**通知が出ないことは「最新である」ことの証明にはならない**（実測で確認済み）。入れた直後の 1 セッション目（表示に使うのは前回の取得結果なので、比べる相手が無い）と、前回の取得から 24 時間の間（その後に新版が出ても次の取得まで気づかない）は必ず沈黙する。いますぐ確かめるには:

```bash
P="${CLAUDE_PLUGIN_ROOT:-}"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"; [ -d "$P" ] || P="$HOME/.claude/plugins/marketplaces/hirai-lite"
curl -fsSL https://raw.githubusercontent.com/thirai-classlab/hirai-method-lite/main/VERSION   # 公開されている最新版
cat "$P/VERSION"                                                                              # いま入っている版
```

2 つの値が違えば更新できる。同じなら最新。控えを消してセッションを開き直すと次の起動で取り直す（`rm -rf "${TMPDIR:-/tmp}/claude-harness-lite"`。手順 0 のルールの控えも同じ場所にあるので、消す前に要否を確かめる）。

## 判定できる終了条件

- `cat "$P/VERSION"` が更新前より新しい semver を返す（`$P` は素材行で解決した値。環境変数を直に書いた行は空振りする）。
- 手順 0 の控えが `${TMPDIR:-/tmp}/claude-harness-lite/rules-backup-*/` にあり、**元の `rules/` も残っている**（コピーであって移動ではない）。
- 手順 2 のあと、`ls .claude/tasks .claude/draft .claude/rules-reference 2>/dev/null` が**移さなかったもの以外は何も返さない**（移した分は `docs/` 側に在り、`git status --short` で `R` (rename) か 削除 + 追加 として見える）。移行が不要だった場合は最初から何も返さない。
- 手順 4 で `same` / `updated` と出た `$D`（プロジェクト側 / ホーム側のうち実際に置いてある方）について、`cmp -s "$P/scripts/statusline.sh" "$D/statusline.sh"` と `cmp -s "$P/scripts/tasks-path.sh" "$D/tasks-path.sh"` と `cmp -s "$P/scripts/context-usage.sh" "$D/context-usage.sh"` が 3 つとも exit 0。
- `bash "$D/statusline.sh" </dev/null` が 2 行出力する（1 行目 = いまの状態 / 2 行目 = 設定リンク）。`bash "$P/tests/smoke.sh"` が exit 0 で、`git status --short` に `CLAUDE.md` `docs/` `.claude/rules/` の変更が出ていない。
