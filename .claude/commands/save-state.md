---
description: セッション状態を .claude/state/latest.md に保存する。context 使用率 80% 到達時と、作業を中断する時に実行する。
---

# /save-state

## 手順

1. 現在の git 状態を実測する。

```bash
git rev-parse --abbrev-ref HEAD
git log --oneline -5
git status --porcelain
```

2. `docs/tasks/list.md` を Read し、status が `進行中` の行と `未着手` の行を取り出す。
3. `.claude/state/latest.md` を以下の書式で**上書き**保存する。ディレクトリが無ければ `mkdir -p .claude/state` で作る。

```markdown
# session state — YYYY-MM-DD HH:MM

## branch / commit
- branch: <branch 名>
- HEAD: <短縮 hash> <commit 件名>
- 未コミット: <git status --porcelain の行数> 件
  <ファイル名を最大 10 件列挙。11 件以上は「他 N 件」と書く>

## 進行中タスク
- task-<id>: <タイトル> / 残り step: <step 番号と作業概要>
- 直前に実行して成功したコマンド: <コマンド>
- 次に実行するコマンド: <コマンド 1 つ>

## 未着手タスク
- task-<id>: <タイトル>

## 判明した事実
- <このセッションで実測して確定した事実。1 行 1 件、推測は書かない>

## 詰まっている点
- <再現手順と観察したエラー文字列。無ければ「なし」>
```

4. 「次に実行するコマンド」は 1 つだけ書く。複数書かない。
5. 「判明した事実」には実行結果で確認できたものだけ書く。推測は書かない。
6. 保存後に `wc -l .claude/state/latest.md` を実行し、120 行を超えていたら「判明した事実」の古い行から削って 120 行以内にする。

## 履歴を残す場合

上書き前の内容を残すなら、保存の直前に退避する。

```bash
[ -f .claude/state/latest.md ] && cp .claude/state/latest.md ".claude/state/$(date +%Y%m%d-%H%M).md"
```

## 判定できる終了条件

- `ls .claude/state/latest.md` が exit 0。
- `head -1 .claude/state/latest.md` が `# session state` で始まる。
- `wc -l .claude/state/latest.md` が 120 以下。

3 つ成立したら `state 保存。branch <name>、進行中 task-<id>、再開は /resume-state` と 1 行で報告する。
