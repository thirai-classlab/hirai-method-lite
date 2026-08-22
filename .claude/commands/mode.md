---
description: 動作モードを normal / loop で切替える。.claude/mode.yml を書き換え、現在のモードを 1 行で報告する。
---

# /mode [normal|loop]

このコマンドの出力は 1〜2 行に収める。前置きと理由の説明を付けない。

## 引数なし

現在のモードを読んで報告するだけで、ファイルは書き換えない。

```bash
cat .claude/mode.yml 2>/dev/null || echo "mode: normal"
```

報告書式: `現在 <normal|loop>。切替は /mode loop または /mode normal`

## /mode normal

`.claude/mode.yml` を次の 1 行で上書きする。

```yaml
mode: normal
```

報告書式: `normal に切替。重要な分岐で確認を取る`

## /mode loop

`.claude/mode.yml` を次の 1 行で上書きする。

```yaml
mode: loop
```

報告書式: `loop に切替。停止は「止めて」/ タスク完了 / 致命的エラーの 3 つ`

## loop モードの動作

`mode: loop` の間、メインは次のように振る舞う。

- 実装の方式選択・branch 名・commit 件名・build を green にするまでの試行は、user に聞かずに決めて進める。
- 次の 3 つは loop 中でも user 承認を取る。
  - 設計 draft の新規追加 (`docs/draft/` への新規 Write)
  - 承認済 draft の採用案から外れる仕様変更
  - 元へ戻せない操作 (`main` への push / PR merge / 本番 deploy / DB migration / secrets 操作)
- サブエージェントを起動したら、完了通知を待つ間に別の独立タスクか台帳更新を進める。待つだけで止まらない。
- context 使用率 80% に達したら `/save-state` を実行し、新セッションでの再開を提案する。

## ファイルが無い場合

`.claude/mode.yml` が存在しなければ `mode: normal` を書き込んでから報告する。

## 判定できる終了条件

- `grep -c '^mode: \(normal\|loop\)$' .claude/mode.yml` が 1 を返す。
- 出力が 2 行以内。
