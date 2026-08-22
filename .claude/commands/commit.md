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
/verify                            # build / test / lint が exit 0
git commit -m "<type>: <件名>"
```

`git add -A` と `git add .` は使わない。ファイル名を明示して add する。

5. `/verify` が exit 0 以外を返した単位は commit しない。出力末尾 20 行を提示して停止する。
6. 全単位の commit 後に結果を検証する。

```bash
git log --oneline -<単位数>
git status --porcelain            # 出力が空、または意図的に残した file のみ
```

## commit メッセージ

書式は `<type>: <件名>`。`<type>` は `feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `perf` / `ci` から選ぶ。

- 件名は 50 文字以内、何が変わったかを現在形で書く。
- タスクに紐づく場合は末尾に ` (task-<id>)` を付ける。
- 本文が要る場合は `-m` を 2 回使う。heredoc は使わない。

## 承認が要る操作

以下は user が承認するまで実行しない。

- `main` への push (`git push origin main`)
- `gh pr merge`
- `git push --force` と `git reset --hard`
- `git commit --amend` で push 済 commit を書き換えること

feature branch への `git push` と `gh pr create` は実行してよい。この 2 つは別々の Bash 呼び出しに分けて実行する。

## 判定できる終了条件

- `git log --oneline -1` が新しい commit を返す。
- `git status --porcelain` の出力に、意図せず残ったファイルが無い。
- 各 commit 時点で `/verify` が exit 0 だった。
