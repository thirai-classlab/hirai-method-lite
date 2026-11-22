---
description: ルールを 6 工程パイプライン (分類→重複検査→層決定→記述最適化→予算→配置と検証) で追加する。どの工程も飛ばせない。
---

# /add-rule "<ルール案 1 行>"

引数が空なら追加したい規範を 1 行で聞き返して停止する。以下 6 工程を順に実行し、各工程の判定結果をチャットに 1 行ずつ出力する。

**ルールの置き場を決め打ちしない。** ルールはこのプロジェクト (`.claude/rules/`) と全プロジェクト共通 (`~/.claude/rules/`) の 2 通りに置ける (`/init` に `user` を付けたかで決まる)。工程 ② と ⑤ は下のブロック（1 行目が素材行）で置き場を解決してから走らせる。決め打ちすると、全プロジェクト共通に置いた利用者に対して「既存ルール 0 件・予算 0 tokens」と誤判定し、重複ルールを素通しさせる。

```bash
P="${CLAUDE_PLUGIN_ROOT}"; [ -d "$P" ] || P="$(command -v python3 >/dev/null 2>&1 && python3 -c 'import json,re,sys; d=json.load(open(sys.argv[1])); r=[x for k,v in d.get("plugins",{}).items() if k.split("@",1)[0]==sys.argv[2] for x in v if x.get("installPath")]; r.sort(key=lambda x:[int(n) if n.isdigit() else 0 for n in re.split(r"[.]", str(x.get("version","0")))]); print(r[-1]["installPath"] if r else "")' "$HOME/.claude/plugins/installed_plugins.json" hirai-lite 2>/dev/null)"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"
. "$P/scripts/tasks-path.sh"; R="$(harness_rules_dir "$PWD")"; echo "ルールの置き場 $R"
bash "$P/scripts/scope-check.sh" .claude "$HOME/.claude"
```

2 行目が警告を出したら 2 か所に同じルールが在る (= 二重ロード)。その場合は**両方が読み込まれている**ので予算は 2 か所の合計で効いている。先に警告の指示どおり片方を消してから工程 ② に進む。

## ① 分類
1. 「この事象は何回目ですか?」と聞く。
2. 「1 回目」→ 事故記録 (`tasks-path.sh` の `harness_incidents_file "$PWD"` が返すパス。通常は `docs/rules-reference/incidents.md`) に `- YYYY-MM-DD <事象 1 行> / 対処: <1 行>` を追記して**終了**。ルール化しない。
3. 「2 回目以降」→ 「不可逆操作 (実行後に元へ戻せない操作) ですか?」と聞く。
4. Yes → `.claude/settings.json` の `permissions.deny` (常に禁止) か `permissions.ask` (承認すれば実行可) に 1 行追加する案を作り工程 ⑤ へ飛ぶ。
5. No → 工程 ② へ。

## ② 重複・矛盾検査
`CLAUDE.md` と `$R/*.md` (`$R` は冒頭で解決した置き場) を全部 Read し、既存ルールを箇条書きで数え上げて新ルール案と照合する。**Read した件数が 0 件なら照合できていない** ので、置き場の解決からやり直す (「既存ルール無し」と結論づけない)。あわせて組み込みの `/doctor prompt-audit "$R"`（Claude Code 2.1.283 以降の skill）を回し、古い書き方・存在しない参照・矛盾の指摘のうち新ルール案に関わるものを照合結果に足す。修正案はここでは当てない（当てるなら別の承認にする）。
- 同趣旨の既存ルールあり → **既存行を書き換える案**にする。新規行は追加しない。
- 反対の指示をする既存ルールあり → どちらを失効させるか user に選ばせ、失効側を `.claude/rules-archive/<元ファイル名>.md` へ移す案にする。
- どちらでもない → 工程 ③ へ。

## ③ 層の決定
「どの作業のときだけ必要か」を 1 文で言えるか判定する。
- 言える → **T1**。その作業のファイル glob を `paths:` に書き、`$R` の tasks.md / code.md / ops.md のうち glob が一致する 1 本に入れる。一致が無ければ新規 T1 ファイル案を出す (T1 は 6 本まで)。
- 言えない → 「全作業に例外なく効く」根拠を user に求める。根拠が出なければ T1 に落とす。出たら **T0** 候補として ④ へ。

## ④ 記述の最適化
書式は `- **<短い名前>**: <規範を肯定形で 1 行> ／ 例: <具体例 1 つ> ／ 失効: <いつ消せるか>`。
- 主語 (メインは / サブエージェントは) を明示する。
- 否定形は肯定形へ変換する (「main を直接編集しない」→「main への変更は feature branch と PR 経由で行う」)。
- 判定できる条件・数値にする (「粒度を揃えてコミット」→「1 commit = 1 機能または 1 修正。各 commit でテストが green」)。
- 具体例は 1 つだけ。1 ルール 1 事象。全体 3 行以内。
- 禁止語彙を `grep -E '適切に|必要に応じて|可能な限り|十分に|慎重に'` で検査する。1 件でもヒットしたら書き直して再検査する。

## ⑤ 予算チェック
T0 実測 (frontmatter に `paths:` を持たないファイルの合計) を測る。`CLAUDE.md` も置き場に合わせて 2 通りあるので、在るものだけを足す。`AGENTS.md` も、CLAUDE.md が無ければそのまま、あれば `@AGENTS.md` で毎回読まれるので足す（CLAUDE.md が取り込んでいないときは多めに出る）。
```bash
P="${CLAUDE_PLUGIN_ROOT}"; [ -d "$P" ] || P="$(command -v python3 >/dev/null 2>&1 && python3 -c 'import json,re,sys; d=json.load(open(sys.argv[1])); r=[x for k,v in d.get("plugins",{}).items() if k.split("@",1)[0]==sys.argv[2] for x in v if x.get("installPath")]; r.sort(key=lambda x:[int(n) if n.isdigit() else 0 for n in re.split(r"[.]", str(x.get("version","0")))]); print(r[-1]["installPath"] if r else "")' "$HOME/.claude/plugins/installed_plugins.json" hirai-lite 2>/dev/null)"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"
. "$P/scripts/tasks-path.sh"; R="$(harness_rules_dir "$PWD")"
for f in CLAUDE.md "$HOME/.claude/CLAUDE.md" AGENTS.md .claude/AGENTS.md "$R"/*.md; do  # AGENTS.md は直接か @AGENTS.md で毎回読まれる
  [ -f "$f" ] || continue
  head -5 "$f" | grep -q '^paths:' || wc -c "$f"
done | awk '{s+=$1} END {print "T0 bytes:", s, "≈ tokens:", int(s/3)}'
```
**`T0 bytes:` が空 or 0 なら測れていない** (置き場の解決に失敗している)。その値で「空きあり」と判定しない。
上の値は概算 (bytes÷3)。実測も並べるときは、user に `/context all` を打ってもらい (組み込みのコマンドで Claude からは呼べない)、Memory files の行の tokens を概算の横に出す。auto memory (`MEMORY.md`) も毎回読まれる量なので、ここに含めて見る。
T1 は対象 1 ファイルのみ同じ式で測る。追加案の推定バイト数を足して判定する。
- T0 追加後 ≤ 10,000 tokens かつ T1 追加後 ≤ 2,000 tokens → 工程 ⑥ へ。T0 が 6,000 tokens を超えていれば「警告域: 降格候補を 1 件決めてから足す」と伝える。
- 超過 → **削除候補を提示する**。既存 T0 ルールを「最終発火日が古い順」「失効条件が既に成立している順」で並べ、上位 3 件を `候補 N: <ルール名> (<tokens> 相当) → T1 降格 or 削除` の形で出し user に 1 件選ばせる。選ばれた 1 件を降格・削除してから追加する。「どれも消さない」と答えたら**追加を中止**して終了する。

## ⑥ 配置と検証
1. 「失効条件はいつ成立しますか?」と聞き ④ の `失効:` を確定する。
2. **承認を求める。** 本文に承認カードを**この語で**示してから `AskUserQuestion`（`承認する` / `承認しない` / `修正して提案し直す`）を出す。カードは本文に書き、選択肢の説明文に詰め込まない（切り詰められて肝心の数字が消える）。型と記入例（`AskUserQuestion` が使えないときの平文の出し方も）は `docs/rules-reference/approval-template.md`（プロジェクトに無ければプラグイン同梱の同名ファイル）。
   - **決めること・推奨** — 足す決まりを 1 文で言い換えたもの（「〜の落とし穴を決まりに 1 行足すか」）と推奨
   - **目的** — 何の失敗を防ぎ、誰の何が良くなるか。① で聞いた「何回目か」を含める
   - **位置** — 層（毎回読まれる／特定の作業でだけ読まれる）と置き場の名前
   - **承認すると** — ⑤ で測った**読む量の現在値 → 追加後の値**、いつから効くか、戻し方
   - **しないと** — 放置した結果。**確かめていないなら「推測」と書く**
   - **注意** — 既存ルールとの重なりか、いちばん大きい副作用を 1 つ
   - **詳しく** — 配置先のフルパス。カードの下に、追加する行の**全文**を置く（「1 件足します」では判断できない）

   `承認する` 以外なら追記しない。`修正して提案し直す` なら ④ に戻って作り直す。`承認しない` なら提案を取り下げ、言い換えて聞き直さない。
3. 承認後にファイルへ追記する。T1 は対象ファイル冒頭に `paths:` frontmatter があることを確認し、無ければ追加する。
4. **ロード検証**: user に新しいセッションを開いてもらい、次を実測する。
   - T0 → 新セッション冒頭で当該ルール文字列がコンテキストに載る。
   - T1 → 新セッション冒頭では載らず、`paths:` の glob に一致するファイルを Read・Write・Edit したか、Bash の単一ファイルの読み (`cat`・`head` など) で開いた後に載る (Claude Code 2.1.293 以降。それより前は Read のときだけ)。
5. 実測が想定と食い違えば frontmatter を修正して 4 をやり直す。
6. **開いている PR に知らせる。** ルールを変える PR を出すとき、`gh pr list --state open --json number,title,headRefName` で開いている PR を引く（`gh` が使えないリポは飛ばして「飛ばした」と 1 行出す）。自分の PR 以外が 1 件でもあれば、規範が変わったことと、取り込む手順（base を merge して衝突を見る）を 1 行ずつ、その PR にコメントしてよいか user に確かめてから書く。0 件なら「開いている PR 0 件」と 1 行出す。
7. 想定どおりなら完了報告 1 行を出す。

## 対話イメージ
```
/hirai-lite:add-rule "タスク完了 commit に list.md を含める"

① 分類    : 何回目ですか? → 2 回目 / 不可逆操作ですか? → No
   置き場   : .claude/rules (このプロジェクト) / 重なりなし
② 重複検査 : T0/T1 の既存 14 ルールと照合 … 重複なし。近い規範: tasks.md「完了条件」→ 統合せず新規で可
③ 層決定   : どの作業のときだけ必要か → 「タスクを完了させる時」
             → docs/tasks/** に限定できるため T1 (rules/tasks.md) に配置
④ 記述最適化: 「メインは、タスク完了 commit に list.md の status 更新を含める」
             禁止語彙 grep … 0 件
⑤ 予算     : rules/tasks.md 1,240 → 1,310 tokens (上限 2,000) … 空きあり
⑥ 失効条件 : いつ消せますか? → 「list.md を廃止したら」
---
決めること: 完了の commit に一覧表の更新を含める決まりを1行足すか。推奨: 承認する
目的: 一覧表と実際の進み具合がずれるのを防ぐ（2回目の失敗）
位置: 一覧表を触る作業でだけ読まれる決まり（毎回は読まれない）
承認すると: 読む量は1,240→1,310 tokens（上限2,000）。消せば戻せる
しないと: 一覧表と実態がずれた状態が残りうる（推測）
注意: 既存の「完了条件」と近いが、あちらは満たすこと、これは commit に含めるもの
詳しく: .claude/rules/tasks.md に追記する1行の全文は下に

  - **完了 commit に台帳を含める**: メインエージェントは、タスク完了 commit に list.md の
    status 更新を含める ／ 例: `git add docs/tasks/list.md docs/tasks/task-12.md` ／ 失効: list.md 廃止時

→ AskUserQuestion（承認する / 承認しない / 修正して提案し直す）
→ 承認後、新セッションで docs/tasks/list.md を開き、ロードされることを検証
```
