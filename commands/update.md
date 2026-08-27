---
description: ハーネス (プラグイン hirai-lite) を最新版に更新し、rules を再配置し、プラグイン所有の 2 ファイルを入れ替えて、VERSION で版が上がったことを検証する。
---

# /update

**最優先の注意: ユーザーのカスタマイズを壊さない。**
導入先の `.claude/` にあるファイルは、所有者で 2 種に分かれる。**この区別が更新の全体像**。

| 種別 | 対象 | 更新時の扱い |
|---|---|---|
| プラグイン所有 | `statusline.sh` / `tasks-path.sh` | **配布版で上書きする**（中身が違えば `.bak` に退避してから） |
| 利用者所有 | `rules/*.md` / `settings.json` / `mode.yml` / 台帳 (`list.md` `parking-lot.md`) / `CLAUDE.md` / `docs/` | **上書きしない** |

配置先はプロジェクト側 (`.claude/`) と全プロジェクト共通 (`$HOME/.claude/`) の 2 通りある (`/init` に `user` を付けたかで決まる)。
**どちらに置いたかを決め打ちしない。** 手順 3 は両方を見て、**すでに在る側だけ**を入れ替える。

`.claude/rules/` は `/add-rule` で育てる利用者の資産なので、更新では 1 件も書き換えない。
新しい rules を取り込みたいときだけ、取り込む 1 本を自分で消してから手順 2 の `/init` を実行する。

## 手順 0: 現在の版を控える

```bash
cat "$CLAUDE_PLUGIN_ROOT/VERSION" 2>/dev/null || echo "VERSION なし"
[ -d .claude/rules ]        && cp -R .claude/rules        /tmp/rules.bak.project && echo "退避 .claude/rules → /tmp/rules.bak.project"
[ -d "$HOME/.claude/rules" ] && cp -R "$HOME/.claude/rules" /tmp/rules.bak.home    && echo "退避 ~/.claude/rules → /tmp/rules.bak.home"
```

`VERSION` の値を「更新前の版」として控える。

## 手順 1: プラグインを更新する

```
/plugin marketplace update hirai-lite
/plugin update hirai-lite@hirai-lite
```

- **2 行とも必要。** 1 行目は配布元の控えを取り直すだけで、これを飛ばすと 2 行目は古い控えを見て「最新です」と答える。
- 入れ替えは**再起動で反映される**。Claude Code を開き直してから次へ進む。
- commands / hooks / agents / MCP サーバー定義はこの入れ替えで新しくなる。導入先の `.claude/` は手順 2 と 3 で扱う。
- ターミナルから `claude plugin update` を使う場合、**scope の既定は `user`**。入れた範囲が違うと
  `Plugin "hirai-lite" is not installed at scope user` で失敗するので `--scope local` / `--scope project` を付ける
  (どの範囲に入っているかは `claude plugin list` の `Scope:` 行)。画面の中から `/plugin` で実行する場合は指定不要。

## 手順 2: rules を再配置する

**rules はプラグイン更新では導入先に配られない。** 更新後に必ず実行する。

```
/hirai-lite:init
```

全プロジェクト共通 (`~/.claude/rules/`) に入れている場合は `/hirai-lite:init user` を実行する。
どちらに入れたか分からないときは `ls ~/.claude/rules/*.md .claude/rules/*.md 2>/dev/null` で確かめる
(両方に出たら二重ロードなので、`/init` の警告に従ってどちらか一方を消す)。

`/init` は既存ファイルを 1 つも上書きしない。新しい rules を取り込むには、取り込みたいファイルを
rules から先に削除してから `/init` を実行する。手順 0 の控えと
`diff -ru /tmp/rules.bak.project .claude/rules` (ホーム側なら `diff -ru /tmp/rules.bak.home "$HOME/.claude/rules"`)
で突き合わせ、自分の変更が消えていないかを確認する。

## 手順 3: プラグイン所有の 2 ファイルを入れ替える

`statusline.sh` と `tasks-path.sh` はプラグインの `scripts/` の複製であり、
利用者が編集する前提のファイルではない。`/init` は既存を残すため、この 2 本だけはここで入れ替える。
**中身が配布版と違う場合は上書きせず先に `.bak` へ退避する**（手を入れていた場合の復旧経路）。

**置いていない場所に新しく作らない。** プロジェクト側とホーム側の両方を見て、**すでに在るものだけ**を入れ替える
(片方に決め打ちすると、`/init user` で入れた人はホーム側が古いまま残り、使われないファイルがプロジェクト側に増える)。

```bash
for D in .claude "$HOME/.claude"; do
  for s in statusline.sh tasks-path.sh; do
    src="$CLAUDE_PLUGIN_ROOT/scripts/$s"; dst="$D/$s"
    [ -e "$dst" ] || continue
    if cmp -s "$src" "$dst"; then
      echo "same    $dst"
    else
      cp "$dst" "$dst.bak" && cp "$src" "$dst" && chmod +x "$dst" && echo "updated $dst (backup: $dst.bak)"
    fi
  done
done
for D in .claude "$HOME/.claude"; do
  [ -e "$D/statusline.sh" ] && bash "$D/statusline.sh" </dev/null && echo
done
```

- `same` / `updated` が 1 件も出ない場合は、手順 2 の `/init` がまだ済んでいない。手順 2 に戻る。
- 最後に 2 行出力されれば、入れ替え後も画面下部の表示は動いている。出力が無い / エラーになる場合は
  `cp <その statusline.sh>.bak <その statusline.sh>` で戻し、内容を報告する。
- `.bak` を作ったときは手順 5 の報告に必ず 1 行入れる。作っていなければ触れない。
- **この 2 本以外には触れない。**

## 手順 4: 版が上がったことを検証する

```bash
cat "$CLAUDE_PLUGIN_ROOT/VERSION"
bash "$CLAUDE_PLUGIN_ROOT/tests/smoke.sh"
git status --short
```

- `VERSION` が手順 0 で控えた値より新しくなっていること。
- smoke が全 case PASS / exit 0 であること。FAIL が出たら更新を止め、内容を報告する。
- `git status --short` に `CLAUDE.md` `docs/` `.claude/rules/` の変更が出ていないこと。

版が変わらない場合は、既に最新か、`/plugin update` の後に再起動していない。
`claude plugin list` で導入済みの版を確認する。

## 手順 5: 利用者へ報告する

bash の出力は作業ログであって報告ではない。**最後に必ず下の型で日本語 1 通にまとめる。**
`updated` は「最新版にしました」、`same` は「すでに最新でした」、`.bak` は「元の内容を …bak に保存しました」と
言い換える。内部の言葉は出さない。件数とパスは実測値に差し替え、該当しない行は省く。

```
ハーネスを v0.4.0 から v0.5.0 に更新しました。

✅ コマンド・自動処理・エージェント・外部ツール接続を最新版にしました
✅ 画面下部の情報表示スクリプトを最新版にしました
   変更されていたため、元の内容を .claude/statusline.sh.bak に保存しました
✅ タスク一覧の置き場所を調べるスクリプトを最新版にしました
✅ ルール・設定・進め方の設定・タスク一覧はそのままにしました（あなたが育てたものなので触りません）
✅ 自己チェック 10 項目すべて問題なしでした

次にやること
新しいルールも取り込みたい場合は、入れ替えたいルールを .claude/rules/ から消してから /hirai-lite:init を実行してください。
```

- 途中で止まったら同じ調子で「何が起きたか」「どうすればよいか」「ここまでにやったこと」を書く。

## 更新検知について

SessionStart で `[harness] 更新あり vX → vY (/update で適用)` が出た時だけ実行すればよい。
検知は 24 時間に 1 回・背景通信で、オフラインでも起動を遅らせない。
止めたい場合は `HARNESS_UPDATE_CHECK=off` を環境変数に設定する。

**通知が出ないことは「最新である」ことの証明にはならない**（実測で確認済み）。次の 2 つの間は必ず沈黙する。

- **入れた直後の 1 セッション目。** 表示に使うのは前回の取得結果なので、初回は比べる相手が無い。2 セッション目から出る。
- **前回の取得から 24 時間の間。** 取得した時点で最新だったなら、その後に新版が出ても次の取得まで気づかない。

いますぐ確かめるには、控えを消してからセッションを開き直す（次の起動で取り直す）。

```bash
rm -rf "${TMPDIR:-/tmp}/claude-harness-lite"
curl -fsSL https://raw.githubusercontent.com/thirai-classlab/hirai-method-lite/main/VERSION   # 公開されている最新版
cat "$CLAUDE_PLUGIN_ROOT/VERSION"                                                             # いま入っている版
```

2 つの値が違えば更新できる。同じなら最新。

## 判定できる終了条件

- `cat "$CLAUDE_PLUGIN_ROOT/VERSION"` が更新前より新しい semver を返す。
- 手順 3 で `same` / `updated` と出た `$D` (プロジェクト側 / ホーム側のうち実際に置いてある方) について、
  `cmp -s "$CLAUDE_PLUGIN_ROOT/scripts/statusline.sh" "$D/statusline.sh"` と
  `cmp -s "$CLAUDE_PLUGIN_ROOT/scripts/tasks-path.sh" "$D/tasks-path.sh"` が両方 exit 0。
- `bash "$D/statusline.sh" </dev/null` が 2 行出力する (1 行目 = いまの状態 / 2 行目 = 設定リンク)。
- `bash "$CLAUDE_PLUGIN_ROOT/tests/smoke.sh"` が exit 0。
- `git status --short` に `CLAUDE.md` `docs/` `.claude/rules/` の変更が出ていない。
