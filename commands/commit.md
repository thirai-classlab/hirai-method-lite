---
description: 変更を論理単位に分けて commit する。1 commit = 1 機能または 1 修正、各 commit でテストが green。
---

# /commit

## 手順

1. 変更の全体を実測する。

```bash
git status --porcelain
git diff --stat
git diff --cached --stat
```

2. 変更ファイルを論理単位に分ける。1 単位 = 1 機能追加、1 バグ修正、1 リファクタ、1 ドキュメント更新のいずれか 1 つ。異なる単位を同じ commit に混ぜない。
3. 単位が 2 つ以上ある場合は、単位ごとのファイル一覧と commit 件名案をチャットに一覧表示し、この順で commit してよいか user に確認する。単位が 1 つなら確認せず 4 へ進む。
4. 単位ごとに以下を実行する。

```bash
git add <その単位のファイルを明示列挙>
git diff --cached --stat          # 意図した file だけが載っていることを確認
/hirai-lite:verify                 # build / test / lint が exit 0（素の /verify は組み込みのアプリ確認に当たる）
git commit -m "<type>: <件名>"
```

`git add -A` と `git add .` は使わない。ファイル名を明示して add する。

5. `/hirai-lite:verify` が exit 0 以外を返した単位は commit しない。出力末尾 20 行を提示して停止する。
6. 全単位の commit 後に結果を検証する。

```bash
git log --oneline -<単位数>
git status --porcelain            # 出力が空、または意図的に残した file のみ
```

## commit メッセージ

書式は `<type>: <件名>`。`<type>` は `feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `perf` / `ci` から選ぶ。

- 件名は 50 文字以内、何が変わったかを現在形で書く。
- issue に紐づく場合は件名の中に `(#n)` を書く（台帳の形のリポでは末尾に `(task-<id>)`）。末尾の `(#PR)` は squash merge に任せ、自分では付けない (付けると PR 番号と二重になる)。
- 本文が要る場合は `-m` を 2 回使う。heredoc は使わない。

## 承認が要る操作

以下は user が承認するまで実行しない。**承認を求めるときは承認カード**（決めること・推奨 / 目的 / 位置 / 承認すると / しないと / 注意 / 詳しく）**を本文に示してから** `AskUserQuestion`（`承認する` / `承認しない` / `修正して提案し直す`）**を出す。型と記入例**: `docs/rules-reference/approval-template.md`（プロジェクトに無ければプラグイン同梱の同名ファイル。`AskUserQuestion` が使えないときの平文の出し方も同じファイル）。

- 既定ブランチ（`gh repo view --json defaultBranchRef --jq .defaultBranchRef.name` で引く）への push (`git push origin <既定ブランチ>`)
- `gh pr merge`
- `git push --force` と `git reset --hard`
- `git commit --amend` で push 済 commit を書き換えること

feature branch への `git push` と `gh pr create` は実行してよい。この 2 つは別々の Bash 呼び出しに分けて実行する。

## PR を作る

- 1 PR = 1 task。差分が 500 行を超えるなら task を分けて、下の PR から積む。
- 本文の型は導入先のものに従う。PR の雛形（`.github/`・`docs/`・直下の `pull_request_template.md` か、`PULL_REQUEST_TEMPLATE/` の種別ごとの file）か本文を見る検査があれば、その型で書く。雛形も検査も無いときだけ、プラグインの 4 種別の型（`templates/pull_request_template.md`。書き方は `docs/rules-reference/git-and-pr.md` §9）で書く。どちらも、雛形を作業用の file に写して埋め、`gh pr create --title <題> --body-file <file>` で出す（CLI は雛形を自動では読まない）。
- 本文に `Closes #<n>` を 1 行入れる（台帳の形は `task-<id>`）。部分の PR は、残りの完了条件を別 task へ移してから `Closes` にする。
- 積み上げた PR の下が squash で入ったら `hirai-pr-retarget`（土台の `bin/`。Bash ツールでは PATH に入る）で付け替える。
- merge を頼む前に `gh pr checks <n>` を見る手順は `rules/code.md` の「PR」にある。

## 判定できる終了条件

- `git log --oneline -1` が新しい commit を返す。
- `git status --porcelain` の出力に、意図せず残ったファイルが無い。
- 各 commit 時点で `/hirai-lite:verify` が exit 0 だった。
