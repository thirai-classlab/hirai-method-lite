# rules-reference (T2 参照層)

ここは **常時ロードされない参照専用の領域** である。背景・経緯・事故記録・長い手順書を置く。

## なぜ常時ロードしないのか

コンテキストに常駐させてよいのは「全作業に例外なく効く規範」だけで、その総量には上限 (T0 合計 10,000 tokens、6,000 tokens で警告) がある。背景や経緯は読む価値があるが、毎セッション全員が読む必要はない。ここに置いたものは AI が明示的に Read したときだけ読み込まれるので、量を気にせず書ける。

## なぜ `.claude/rules/` の外に置くのか

`.claude/rules/` 配下の `.md` は Claude Code が再帰的に発見する。frontmatter の `paths:` を書き忘れたファイルはその瞬間に常時ロード (T0) へ昇格し、予算を壊す。ここを `docs/` 側に物理的に出しておけば、書き忘れても昇格しない。**構造で事故を防いでいる。**

## 層の対応

| 層 | 場所 | ロード条件 |
|---|---|---|
| T0 常時 | `CLAUDE.md` / `.claude/rules/_meta.md` / `.claude/rules/core.md` | 毎セッション |
| T1 条件 | `.claude/rules/<domain>.md` (`paths:` あり) | 該当ファイルを触った時 |
| **T2 参照** | **`docs/rules-reference/**` (ここ)** | **AI が明示 Read した時のみ** |
| T3 退避 | `.claude/rules-archive/**` | ロードされない |

## 収録ファイル

| ファイル | 内容 | 読むとき |
|---|---|---|
| [`incidents.md`](incidents.md) | **このハーネスで起きた**事故の台帳。1 事故 = 1 行、再発回数つき | 事故が起きたとき / 2 回目かを判定するとき |
| [`incidents-legacy.md`](incidents-legacy.md) | **前ハーネスで起きた**事故 33 件。参考資料で、判定には使わない | 過去に同種の事例があったか調べるとき |
| [`subagent-operations.md`](subagent-operations.md) | 並列起動数の実測、委譲、共有ファイル競合、ファイル間契約、委譲先の検証 | subagent を立てる前 |
| [`review-practice.md`](review-practice.md) | 偽収束、反復回数、誤報 CRITICAL の潰し方、指摘の集約、設計乖離 | レビューを回すとき / 収束を判断するとき |
| [`design-process.md`](design-process.md) | 依存の実在確認、前提崩壊時の動き方、規範の書き方、計測値の検証 | draft を起こすとき / 規範を足すとき |
| [`task-ledger.md`](task-ledger.md) | タスク構造、完了条件の書き方、一括計画、完了 commit | 台帳を触るとき |
| [`testing-practice.md`](testing-practice.md) | テストが嘘をつく典型、失敗の分類、並行性のテスト | テストを書く / 直すとき |
| [`git-and-pr.md`](git-and-pr.md) | stacked PR、複合コマンド、PR 本文の渡し方 | PR を出すとき |
| [`shell-pitfalls.md`](shell-pitfalls.md) | `set -e` の leak、`grep -c` の exit code、実行ビット、コマンド解決 | bash を書くとき |
| [`plugin-development.md`](plugin-development.md) | manifest のキー、`validate` の限界、`${CLAUDE_PLUGIN_ROOT}`、更新経路 | プラグインを触るとき |
| [`context-and-output.md`](context-and-output.md) | コンテキスト予算の実測、出力の形について user が求めたこと | 層構成を変えるとき / 出力形式を決めるとき |

記録の大半は**前ハーネス (hirai-method) から 2026-08-27 に移入した実測と事故**である。前ハーネス固有の仕組み (hook / preset / 各種 guard) に依存する記述は、そのまま持ち込まず「前ハーネスの事例」と明示してある。**新ハーネスに機械強制はほとんど無い** — ここに書かれた対処は原則すべて指針であり、実際に止まるのは `settings.json` の `permissions` に登録された操作だけである。

### 台帳を 2 つに分けている理由

`incidents.md` は `rules/_meta.md` 条 1「事故 2 回目で初めてルール化する」の**判定に使う唯一の台帳**なので、**このハーネスで起きた事故だけ**を入れる。他所の記録を混ぜると、一度も起きていない事象が「2 回目」と数えられ、推測ルールが生える。前ハーネスの記録は参考資料として `incidents-legacy.md` に分離し、そちらの再発回数は判定に使わない。**`incidents.md` が数行しかない (あるいは空である) のは正常。**

## 置いてよいもの

- 事故・失敗の記録
- ルールが生まれた経緯、過去に採用して廃止した方式
- 長い手順書 (セットアップ、移行、リカバリ)
- 調査ログ、実測値、比較検討の結果

## 置いてはいけないもの

- **守らせたい規範そのもの**。ここは読まれない前提の領域なので、規範を置くと誰も守らない。規範は T0 か T1 に置き、ここへは T1 の末尾から 1 行のポインタを張る。

## ポインタの向き

ポインタは **T1 → T2 の一方向**だけに張る。T0 からここへリンクを張ると、T0 が索引で膨らむ (前ハーネスが T0 肥大した実際の経路がこれ)。

## 参照のしかた

必要になったときに、AI か user が明示的にファイルを指定して読む。

```
docs/rules-reference/incidents.md を読んで、同種の事故が過去にあったか確認して
```
