---
name: github-project
description: GitHub Project でやること（wave・feature・task の issue と Status）を読む・書くとき、hirai-task や gh issue を使う前に読む。「進捗を見せて」「進捗は?」「タスクの状況」「だれが何をしている?」と聞かれたとき（スマートフォンからも）と、task の割り振り・着手・完了のときにも読む。正本・3 段・Status 8 値・着手可は人だけ・完了条件・書き込みはメイン専任・承認カード・進みと割り振りの表（hirai-task load）の決まり。
---

# GitHub Project でのやること管理

`rules/tasks.md`（T1）の `paths:` は `docs/` の書類にしか当たらず、`hirai-task` と `gh` だけで進む作業では読まれない。そのため GitHub Project の形の規範はこの skill に置く（v2.7.0 で `tasks.md` から移した）。

- **正本は Project**: メインエージェントは、やることの正本を GitHub の issue と Project に置き、着手前に `gh issue view <n>` で本文と依存を読む ／ 例: `hirai-task ready` で着手できる issue を出す ／ 失効: 外部トラッカー（Asana / Jira）に正本を移したとき
- **3 段**: メインエージェントは、仕事を wave → feature → task の 3 段（項目「種別」と sub-issue）で組み、PR は feature ごとに 1 本にしてその feature の task を全部閉じる ／ 例: feature #10 の PR の本文に `Closes #11`・`Closes #12` を書く ／ 失効: なし
- **Status は 8 値**: メインエージェントは、Status を次の 8 値で扱う。承認待ち / 着手可 / 判断待ち / 依存待ち / 進行中 / レビュー中 / 完了 / 保留。レビュー中と完了は原則として組込の自動化が動かす（進行中・レビュー中・空 のまま閉じた task は `today` が 完了 にする）。自動化が動かない PR（既定の branch 以外向け）のときだけ `hirai-task review <n>` で レビュー中 にする ／ 例: 既定の branch 向けの PR は出せばレビュー中になる ／ 失効: なし
- **feature の着手可は人だけ**: メインエージェントは、feature の着手を人がボードで「着手可」にするまで待ち、自分では動かさない ／ 例: feature が着手可で、未完了の blocked by が無ければ（先の wave が出ていなくても。着手可が wave の門を越えてよいの意思表示）、子の task はあとから足したものも `hirai-task start` で着手してよい（feature が承認待ちの間は呼ばない） ／ 失効: なし
- **完了条件は検証可能に**: メインエージェントは、issue の完了条件を再現コマンドか観察可能な事実で書く ／ 例: 「ログイン E2E が green」「`GET /health` が 200 を返す」 ／ 失効: なし
- **書き込みはメイン専任**: サブエージェントは issue を読むだけにし、Status や本文の変更は結果報告でメインに返す ／ 例: 報告に「#12 完了、Status を 完了 へ」と書く ／ 失効: なし
- **見回りの時機**: メインエージェントは、会話の最初に `hirai-task today`、自分が出した PR の merge の直後に `hirai-task after-merge <PR 番号>` を回す ／ 例: 新しい会話の最初の操作は `today` ／ 失効: 正本を GitHub 以外へ移したとき
- **見回りが書くもの**: `today` は align・close-parents に加え、閉じたのに Status が 完了 でない task のうち、今の Status が 進行中・レビュー中・空 で、[操作]・[User] でない task（この repo の行だけ）へ Status=完了 だけを書く（[操作]・[User] と、ほかの Status のまま閉じた行は stuck に番号と題を出すだけ。書く直前に読み直して書く相手でなければ飛ばし、1 回 5 件・45 秒まで、残りは次の today。書けない 1 件は理由を出してほかを続け、rate limit・権限の 403 なら残りを打ち切る。align と同じ許可 `- today は書かない: はい` に従う。today に `--json` は無い） ／ 例: `完了にした: #1（進行中 → 完了）題` ／ 失効: 正本を GitHub 以外へ移したとき
- **見回りが出す警告**: メインエージェントは、today の orphans が出す種別なしの行に「直す: `hirai-task set <n> 種別 task（feature・wave・設計メモならその値）`」を見たら、その行が feature・wave・設計メモなら種別をその値にして打つ。`set`・`start` は相手の種別が空だと同じ直し方つきの stderr に警告 1 行（止めない）。直近 7 日の `no-issue` ラベルの merge（既定の branch 向け。設計の PR もここに数える）は、issue を付け忘れた PR が混じっていないかを見る ／ 例: `no-issue の merge（7 日）3 件: #11・#12・#13` ／ 失効: 正本を GitHub 以外へ移したとき

## 承認の場所とカード（v2.8.0）

- **着手の承認は承認ビューで受ける**: メインエージェントは、承認待ちの feature の本文の先頭に承認カードを置き、`hirai-task card <n> --sync` で項目「ひとこと」「推奨」に写す ／ 例: 会話では「承認ビューに 3 件あります（推奨: 承認する 2・承認しない 1）」と件数を伝える ／ 失効: 承認を別の場（会議・外部の道具）に移したとき
- **承認ビューの答えを拾う**: メインエージェントは、会話の最初に `hirai-task comments` で承認ビューの答え（承認しない・直して出し直す・条件つき）を拾い、カードと本文の承認の記録を直す ／ 例: 「直して出し直す: 範囲を画面 1 つに」→ カードを直して `--sync` ／ 失効: なし
- **着手は承認のあとに**: メインエージェントは、承認待ちの feature の子の作業を、feature が着手可になってから PR にする ／ 例: feature #12 が承認待ちなら #12 のカードを出して待つ ／ 失効: なし
- **箱をカードに合わせる**: メインエージェントは、判断待ちには判断カードのある問いだけを置き、人が行う作業は `[User]`（人の作業カード）、人の権限で AI が行う操作は `[操作]`（承認カード）にする ／ 例: 外部の申込を待つ issue は `[User]` にする ／ 失効: なし
- **答えが出た判断はその日に閉じる**: メインエージェントは、判断待ちの問いに答えが出たら、出どころ（会議・PR・ADR）を本文に書いてその日のうちに閉じる ／ 例: 「PR #46 で決着。案 A を採用」と書いて閉じる ／ 失効: なし
- **カードは今日の分から書く**: メインエージェントは、会話の最初に `hirai-task card --lint` の件数を伝え、カードを書くのは今日着手するものと期限の近い判断に絞る ／ 例: 「カードの抜け: 承認 12・判断 16。今日は #12 と #40 を書く」 ／ 失効: なし

## 進みと割り振りの表（進捗を聞かれたとき）

`hirai-task load` が、GitHub Project の issue・PR・CI の実物から表を出す（読むだけ。`--json` は同じ材料の機械可読）。「どこで何件止まっているか」は `/hirai-project-method:board`（件数と止まり）、`load` は進み（%）と、だれが何をどの順でしているか。

- **表はそのまま貼る**: メインエージェントは、`hirai-task load` の出力を言い換えず、数え直さず貼る ／ 例: 「進捗を見せて」に `hirai-task load` の出力だけを返す ／ 失効: なし
- **表を出すのは 4 つの時機だけ**: メインエージェントは、新しい task を振ったとき（着手を含む）・完了したとき・進捗の確認を頼まれたとき・task に進捗があったとき（段が上がった・止まった）に表を出し、返答のたびには出さない ／ 例: 割り振りは `hirai-task assign 40 sess-a 1` の出力の終わりに出る ／ 失効: なし
- **警告の出た task は振らない**: メインエージェントは、`start`・`assign` が「ほかの人の task」と警告した task の割り振りを `hirai-task assign <n> --clear` で外し（`assign` は警告しても控えに書く）、ユーザーに聞く ／ 例: 「#51 は other-dev の task。開いている PR #160」→ `--clear` してから、どう進めるかを聞く ／ 失効: なし

| 時機 | 打つもの |
|---|---|
| 進捗の確認を頼まれた | `hirai-task load` |
| 新しい task を振った | `hirai-task assign <n> <作業のセッションの名前> [順]`（外すときは `hirai-task assign <n> --clear`。名前に空白があれば引用符で囲む。`-` で始めない） |
| 着手した・完了した | `hirai-task start <n>`・`hirai-task done <n>`・`hirai-task after-merge <PR>` |
| 進捗があった | `hirai-task load --changed`（前回と比べて段・担当・順番・止まりの印が動いたときだけ出し、動いていなければ 1 行も出さず exit 3）。コーディネーターの会話では、前景の `orca orchestration check` で知らせを受けたとき（出力に message の id があるか `--ack` を付けたとき）、hook が「打つ」の 1 行を足す。背景で待って受けたときは出ないので、自分で打つ |

**割り振り・着手・完了のあとの表は、コーディネーターの会話だけに出る。** コーディネーターの会話は、次の全部がそろうとき: `HC_NOTIFY=off` で開いた・Orca の端末・linked worktree でない・`.claude/mode.yml` が `tasks: github-project` と `notify: orca`。板の控えが 1 本も無いときは 1 行の断り、10 分より古い控えで描くときは表の下に「（控え: N 分前）」が出る。`start`・`done`・`reopen`・`review`・`set Status`・`after-merge` で閉じた issue の変更は、板の控えが追いつくまで表に重なる。`--cached` は gh を叩かず、手元の控えだけを読む（板と PR の控えのどちらかが無ければ exit 3・何も出さない）。

### 表の読み方

- 進捗は申告でなく実物で決まる: 0 着手前／20 進行中・レビュー中（PR なし）／50 draft の PR／60 ready で CI が走っているか赤・検査なし／70 CI 緑／90 merge 済みで issue が開いている（Status が 完了 の開いた issue も）／100 issue が閉じた。控えに無い（新しい）issue は 0% で、完了に数えない
- **止まっているもの**: CI が赤・PR が衝突している task（draft の CI 赤は出さない。担当の無い行も入る）。段の数だけでは分からない止まりを別の行に出す
- **担当の列**: 自分の作業のセッションの名前と順番は手元の控え（git の管理ディレクトリの下の `hirai-task/load-assign.json`）から、ほかの人の行は GitHub の Assignees の名前から出す（Project に「担当」の項目は足さない）。閉じた task は割り振りの順番の後ろの 3 つだけ
- **進行中・レビュー中なのに担当の居ないもの**: 手元の控えに名前が無く、ほかの人だけの Assignees でもない 進行中・レビュー中の task（Assignees が自分だけの行も入る。ほかの開発者の開いている PR がある行は「ほかの開発者の PR」に出す）。残さない
- **ほかの開発者の PR**: 割り振りもほかの人の Assignees も無い open の task を閉じる、自分でない人の開いている PR
- 期限の行・本線の印は、**そのリポの** `.claude/mode.yml`（ホームの `~/.claude/mode.yml` は読まない）に設定があるときだけ出る:

```yaml
load_deadline: 2026-12-15        # 本文に「期限: 2026-12-15」の行がある open の issue を数える（日付に触れただけの issue は数えない）
load_deadline_label: ベータ（12/15・エージェントのオンボーディング）
load_mainline: 営業の登録          # この語を含むセクションに印を付ける
load_mainline_label: ベータの本線
```

### Assignees（だれの task か）

`start` と `assign` は、Assignees が空なら動かしている GitHub ユーザーを入れる。ほかの人（複数人を含む）が入っていたら警告を 1 行出す（その人の開いている PR も）。空でも、ほかの人の開いている PR がその task を閉じるなら、入れずに警告する。PR を確かめられないときも入れない。上書き・追加・停止はしない。確かめられないときは標準エラーに 1 行で、着手や割り振りの結果は変わらない。

### 止まったとき

- exit 1: 取得に失敗した（gh の失敗・認証・レート制限）。標準エラーの末尾を伝え、`hirai-task load --refresh` を添える。「0%」「0 件」とは言わない
- exit 2: 呼び方の誤り。標準エラーをそのまま出す
- exit 3: 出すものが無い（`--changed` で動きが無い・`--cached` で控えが無い・`--if-coordinator` の対象外）。標準出力は 1 行も出ない

## 関連

- 立ち上げ・Status の動かし方・ビュー: `docs/rules-reference/project-setup.md`（無ければプラグイン同梱の同名ファイル）。新しいリポでは利用者に `/hirai-project-method:project-setup` を打ってもらう（Claude からは呼べない）
- 全体像と、どこで何件止まっているか: `/hirai-project-method:board`（`hirai-task board`）
- 承認を求めるときの型（承認カード・判断カード・人の作業カード）: `docs/rules-reference/approval-template.md`
- 進め方の用語: `docs/rules-reference/glossary.md`（案件を知らない人に渡すとき）
