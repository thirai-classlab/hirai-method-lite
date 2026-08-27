---
description: セッション状態を .claude/state/latest.md に保存 (/state save) し、そこから作業を再開する (/state resume)。
---

# /state save | /state resume [loop]

第 1 引数で分岐する。`save` なら「保存」節、`resume` なら「再開」節を実行する。引数が空、または `save` / `resume` のどちらでもない場合は `使い方: /state save | /state resume [loop]` と 1 行返して停止する。

---

# 保存 (`/state save`)

context 使用率 80% 到達時と、作業を中断する時に実行する。

## 手順

1. 現在の git 状態を実測する。

```bash
git rev-parse --abbrev-ref HEAD
git log --oneline -5
git status --porcelain
```

2. 台帳 (`$HARNESS_TASKS_FILE` > `docs/tasks/list.md` > `.claude/tasks/list.md`) を Read し、status が `進行中` の行と `未着手` の行を取り出す。
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

## 判定できる終了条件 (save)

- `ls .claude/state/latest.md` が exit 0。
- `head -1 .claude/state/latest.md` が `# session state` で始まる。
- `wc -l .claude/state/latest.md` が 120 以下。

3 つ成立したら、次の「利用者へ出す案内」を応答本文に出す。

## 利用者へ出す案内 (save の最後)

保存が済んだら、**必ず下の型で案内する**。画面下部の表示ではなく応答本文に出す。
内部の言葉 (`state` / `T0` / `exit 0` など) は出さず、平易な日本語で時系列に書く。
`<保存先パス>` と `<進行中タスク>` は実測値に差し替える。

```
保存しました → .claude/state/latest.md
進行中: task-12 レート制限の実装 — 残り step 3

新しいセッションで続きから始めるには:
1. /clear と入力します
   会話の履歴だけが消えます。プロジェクトの決まりごと (CLAUDE.md と .claude/rules/) は
   新しい会話のはじめに読み込み直されるので、消えません。
   ウィンドウを閉じて開き直しても結果は同じです。どちらでも構いません。
2. /hirai-lite:state resume と入力します
   いま保存した内容を読み込んで、続きから再開します
```

- **手順 1 を「閉じて開き直す」だけに限定しない。** `/clear` は「空のコンテキストで新しい会話を始める」操作で
  ([公式](https://code.claude.com/docs/en/commands.md))、CLAUDE.md と `.claude/rules/` は
  「毎回の会話のはじめに読み込まれる」([公式](https://code.claude.com/docs/en/memory.md))。
  この 2 つから、`/clear` の後もルールは読み込み直される。
- ただし `/clear` と「閉じて開き直す」が**あらゆる点で同じ**とは公式に書かれていない (そこは確認できていない)。
  迷う利用者には安全側の「閉じて開き直す」を勧めてよい。どちらでも再開はできる。
- 会話の中だけで伝えた指示 (ファイルに書いていないもの) は `/clear` で消える。残したいものは
  この保存に書くか、`CLAUDE.md` へ追記するよう 1 行添える。

---

# 再開 (`/state resume`)

## 手順

1. `.claude/state/latest.md` を Read する。ファイルが無ければ「保存された state が無い。/state save で作る」と報告して終了する。
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

4. 台帳を Read し、state の「進行中タスク」の id が今も `進行中` かを確認する。`完了` になっていれば「state より台帳が新しい」と報告し、台帳側を正とする。
5. 進行中タスクの `task-<id>-<slug>.md` を Read し、status が `未着手` の最初の step を特定する。
6. 再開サマリを次の書式で 1 回だけ出す。

```
再開: branch <name> / HEAD <hash>
進行中: task-<id> <タイトル> — 残り step <番号> <作業概要>
詰まり: <state の「詰まっている点」または なし>
次に実行: <state の「次に実行するコマンド」>
```

7. state の「次に実行するコマンド」を実行する。exit 0 なら step の作業を続ける。exit 0 以外なら出力末尾 20 行を提示して停止する。

## loop 引数

`/state resume loop` で呼ばれた場合、6 のサマリ出力後に mode（進め方）を `loop`（自動で進む）へ書き換え（書き込み先は決め打ちせず `. "$CLAUDE_PLUGIN_ROOT/scripts/tasks-path.sh"; harness_mode_write_file "$PWD"` が返す**すでに在る側**。`/hirai-lite:config` と同じ経路）、台帳の `進行中` → `未着手` の順に連続で着手する。着手できるのは対応 draft の `approved_at:` が埋まっているタスクのみ。空のタスクに到達したら、その id を報告して停止する。

loop 実行を止める条件は 3 つ。
- user が停止を指示した。
- 同一のエラー文字列で 3 回連続して失敗した。
- context 使用率が 80% に達した (この場合は `/state save` を実行してから停止する)。

## 判定できる終了条件 (resume)

- `git rev-parse --abbrev-ref HEAD` が state の branch と一致する、または user が現 branch 続行を選んだ。
- 再開サマリ 4 行を出力した。
