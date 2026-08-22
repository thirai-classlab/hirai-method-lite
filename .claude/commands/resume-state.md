---
description: .claude/state/latest.md を読み、branch と進行中タスクを突き合わせて作業を再開する。
---

# /resume-state

## 手順

1. `.claude/state/latest.md` を Read する。ファイルが無ければ「保存された state が無い。/save-state で作る」と報告して終了する。
2. state に書かれた branch と現在の branch を突き合わせる。

```bash
git rev-parse --abbrev-ref HEAD
```

不一致なら state の branch 名を提示し「切替えますか?」と聞く。承認されたら `git switch <state の branch>` を実行する。承認が無ければ現 branch のまま 3 へ進む。

3. HEAD を突き合わせる。

```bash
git log --oneline -1
```

state の HEAD と一致しなければ、`git log --oneline <state の hash>..HEAD` で state 保存後に積まれた commit を列挙し、チャットに提示する。

4. `docs/tasks/list.md` を Read し、state の「進行中タスク」の id が今も `進行中` かを確認する。`完了` になっていれば「state より台帳が新しい」と報告し、list.md 側を正とする。
5. 進行中タスクの `docs/tasks/task-<id>-<slug>.md` を Read し、status が `未着手` の最初の step を特定する。
6. 再開サマリを次の書式で 1 回だけ出す。

```
再開: branch <name> / HEAD <hash>
進行中: task-<id> <タイトル> — 残り step <番号> <作業概要>
詰まり: <state の「詰まっている点」または なし>
次に実行: <state の「次に実行するコマンド」>
```

7. state の「次に実行するコマンド」を実行する。exit 0 なら step の作業を続ける。exit 0 以外なら出力末尾 20 行を提示して停止する。

## loop 引数

`/resume-state loop` で呼ばれた場合、6 のサマリ出力後に `.claude/mode.yml` を `mode: loop` へ書き換え、list.md の `進行中` → `未着手` の順に連続で着手する。着手できるのは対応 draft の `approved_at:` が埋まっているタスクのみ。空のタスクに到達したら、その id を報告して停止する。

loop 実行を止める条件は 3 つ。
- user が停止を指示した。
- 同一のエラー文字列で 3 回連続して失敗した。
- context 使用率が 80% に達した (この場合は `/save-state` を実行してから停止する)。

## 判定できる終了条件

- `git rev-parse --abbrev-ref HEAD` が state の branch と一致する、または user が現 branch 続行を選んだ。
- 再開サマリ 4 行を出力した。
