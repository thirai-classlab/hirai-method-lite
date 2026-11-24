# hirai-project-method

[hirai-lite](../../README.md)（土台）に足す、GitHub Project でタスクを回すためのプラグイン。台帳（`docs/tasks/`）で足りるリポは入れない。

## 入れる

```
/plugin install hirai-project-method@hirai-lite
```

土台の hirai-lite（3.0.0 以上）が依存として一緒に入る。**1.x が入っている範囲では、先に `/plugin marketplace update hirai-lite` → 端末で `claude plugin update hirai-lite@hirai-lite --scope <入れた範囲>`（画面なら `/plugin` → Installed → Update now） で土台を 3.0.0 に上げる**（1.16.0 のままだと、上の install は依存の版で断られる。行は残るが読み込まれないだけで、土台を上げて開き直すと入れ直さなくても読み込まれる）。**2.x（`hirai-lite-v2`）が入っている範囲では、足すプラグインだけを先に入れない**（開始時の表示とコマンドは 2.9.0 のままで、`/hirai-lite:board` と `/hirai-project-method:board` が並ぶ）。土台の README「1.x・2.x から 3.0.0 へ移る」の表の順（disable まで）を先に行う。そのうえで、導入先の `.claude/mode.yml` に次を書く。形は自動では見分けない。

```yaml
tasks: github-project
```

`tasks: github-project` で `hirai-task` が見つからないとき（`installed_plugins.json` の足すプラグインの行から引いた絶対 path に無いとき）、土台は上の入れ方を示して止まる。

全体の進みに期限の行や本線の印を出すときは、`.claude/mode.yml` に `load_deadline`・`load_deadline_label`・`load_mainline`・`load_mainline_label`（どれも任意。書き方は `skills/github-project/SKILL.md`）を足す。

夜間に回す CI の赤を見逃さないときは、同じ `.claude/mode.yml` に `nightly_ci: ci.yml`（workflow のファイル名）を足す。`hirai-task today` の先頭に、その workflow の直近の schedule の run の結果を 1 行出す（成功・失敗と url・実行中・run が無い・取れない。36 時間より古ければ注記）。空か無ければ何も出さず gh も呼ばない。

## 入っているもの

| 部品 | 中身 |
|---|---|
| `bin/hirai-task` | リポに紐づいた GitHub Project のタスクを読み書きする 1 本の道具（ready・start・new・board・card・setup・line ほか）。Claude Code がプラグインの `bin/` を PATH に入れる |
| `commands/board.md` | `/hirai-project-method:board` 全体像と、どこで何件止まっているか |
| `commands/project-setup.md` | `/hirai-project-method:project-setup` Project の作成・紐づけ・項目・ビューの立ち上げ（既定は計画だけ。`--apply` で書く） |
| `bin/hirai-task load`・`assign` | 全体の %・担当ごとの順番と進捗率の表と、割り振り・Assignees の決まり（「進捗を見せて」などで出る。決まりは `skills/github-project/` の「進みと割り振りの表」） |
| `hooks/coordinator-load.sh` | コーディネーターの会話だけの PostToolUse（止めない・控えだけ読む・動いたときだけ表を足す。`.claude/mode.yml` の `notify: orca` と `tasks: github-project`・`HC_NOTIFY=off`・Orca の端末・linked worktree でない、が全部そろうとき） |
| `skills/github-project/` | GitHub Project の形の規範（正本は Project・3 段・Status 8 値・書き込みはメイン専任・承認カード） |
| `docs/rules-reference/project-setup.md`・`glossary.md` | 立ち上げの手順と、wave・feature・8 状態の用語 |
| `hirai-task today` の見回りの書き込み | align・close-parents に加え、**閉じたのに Status が 完了 でない task へ Status=完了 だけを書く**（書き込みが 1 種増える。書くのは今の Status が 進行中・レビュー中・空 で、[操作]・[User] でない task（この repo の行だけ。閉じた理由が not planned・duplicate でも同じ）。[操作]・[User] と、承認待ち・判断待ち・依存待ち・着手可・保留 のまま閉じた行は、今までどおり stuck に番号と題を出すだけ（誤って閉じた・実行していないものがありうる）。書く直前に state・種別・Status・題を読み直し、書く相手でなくなっていれば飛ばす。1 件書くたびに `完了にした: #n（前の Status → 完了）題` を出し、書けない 1 件は理由を出してほかを続け、rate limit・権限の 403 なら残りを打ち切る（rate limit の回は align も一覧だけ）。1 回 5 件・45 秒まで（45 秒を超える前に次を始めないだけで、始めた 1 件は最後まで行う）。次の today は試した所の続きから。align と同じ許可（`- today は書かない: はい`）に従う。today に `--json`・`--dry-run` は無く、付けると exit 2）。**「この repo の行だけ」は完了の書き込みだけの決まり**（align・close-parents は、複数のリポを載せた Project で別 repo の行を絞らない。1.0.0 と同じ）。種別なしの行には直すコマンドを 1 行出し、`set`・`start` は相手の種別が空なら stderr に警告 1 行（止めない。種別の項目が無い Project では、どちらも出さない）。直近 7 日に `no-issue` ラベルで merge した既定の branch 向けの PR を番号で出す（closed の PR 100 件の読みを使い、API を増やさない。100 件で見切れて 0 件のときも「0 件」と出す） |
| `hirai-task today` の `nightly_ci` の 1 行 | `.claude/mode.yml` の `nightly_ci: <workflow のファイル名>` があるときだけ、`gh run list --event schedule -L 1` の結果を先頭に 1 行出す |
| `scripts/ghp-path.sh` | 件数の控え（`~/.claude/plugins/data/hirai-project-method-hirai-lite/`）を読み書きするシェル関数 |

## 土台との約束

- 土台は `hirai-task` を、`installed_plugins.json` から引いた絶対 path で呼ぶだけで、`harness_ghp_*` を直接呼ばない。
- 会話の開始時（`hirai-task line --refresh`）と画面下（`hirai-task line`）の 1 行は、`tasks: github-project` のときだけ呼ばれる。`line` は控えを読むだけで、GraphQL を打つのは `--refresh` の背景の取り直しと、書き込みの直後だけ。
- 土台の `harness_pm_task_bin` と更新の知らせは、`installed_plugins.json` の足すプラグインの行のうち、今のリポと同じ git のリポ（`git rev-parse --git-common-dir` が同じ。無い path・git でないときだけ前方一致）の行だけを使う。scope が user・managed の行は通す。足すプラグインを worktree で入れても、本体とほかの worktree で見つかる。
- `hirai-task after-merge` の出力の末尾に、土台の `hirai-worktrees list` で消してよい worktree が 1 本以上あるとき「消してよい worktree: N 本（うち退避が要る M 本。`hirai-worktrees list` で見る）」の 1 行を足す（0 本なら出さない）。
- 承認カードの型（`approval-template.md`）と draft の雛形は土台にある。`hirai-task --selftest` は土台の場所を `HIRAI_LITE_ROOT`・リポ内の配置・`installed_plugins.json` の順に探す。

## 確かめる

```
bash plugins/hirai-project-method/tests/smoke.sh
```

## 2.x（hirai-lite-v2）から移る

install・disable・uninstall は、2.x の行の `projectPath` と同じ場所（worktree ではなく本体の checkout）で打つ。

`/hirai-lite:board`・`/hirai-lite:project-setup` は `/hirai-project-method:board`・`/hirai-project-method:project-setup` になる。件数の控えの置き場が変わるので、最初の会話では画面下の件数が出るまで 1 回待つ。移し方の全体は土台の README と CHANGELOG（3.0.0）に書く。
