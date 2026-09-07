---
description: セッション状態を .claude/state/latest.md に保存 (/state save) し、そこから作業を再開する (/state resume)。
---

# /state save | /state resume [loop]

第 1 引数で分岐する。`save` なら「保存」節、`resume` なら「再開」節を実行する。引数が空、または `save` / `resume` のどちらでもない場合は `使い方: /state save | /state resume [loop]` と 1 行返して停止する。

---

# 保存 (`/state save`)

context 使用率 80% 到達時と、作業を中断する時に実行する。

## 手順

1. `git rev-parse --abbrev-ref HEAD` / `git log --oneline -5` / `git status --porcelain` を実行し、現在の git 状態を実測する。
2. 台帳 (`$HARNESS_TASKS_FILE` > `docs/tasks/list.md` > 旧レイアウトの `.claude/tasks/list.md`) を Read し、status が `進行中` の行と `未着手` の行を取り出す。
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

## 次回に効くものを置く

state ファイルは**次のセッションの最初の 1 手**を渡すもので、会話が終われば役目を終える。ここでやるのは別の仕事 — このセッションで確定して**次回以降も効くもの**を、次回も読み込まれる場所へ移す。層の選び方に迷ったら `/hirai-lite:context-engineering` を読む（どこに置くと・いつ読まれるかの公式の根拠が入っている）。

7. 次の 3 種を列挙する。**意思決定**（採った案と、採らなかった案とその理由）/ **教訓**（失敗、詰まった点、うまくいった手順）/ **取り決め**（会話の中で決まったルール的なもの）。実際に決まった / 実際に詰まったものだけを書き、推測を混ぜない。
8. **0 件なら「次回に効くものはありません」と 1 行返してこの節を終える。** 無理に記録を作らない（既定は入れない）。ここで作った 1 件が来年も毎セッション載り続ける。
9. 各件の置き場を `.claude/rules/_meta.md` の条文で決める（条 1 = 事故 1 回目は記録して終わり / 条 2 = 既定は T1 / 条 5 = 元に戻せない操作だけ `settings.json` の `deny` / `ask` / 条 8 = 追加は承認必須）。4 択に整理した表は上の skill の §3 にある。**新しい判定基準を作らない。**
10. **自動で書いてよいもの**（承認不要。**追記のみ**で、既存行の書き換え・削除はしない）。
    - 事故 1 回目 / 背景・経緯 / 詳細 → 事故記録（`tasks-path.sh` の `harness_incidents_file "$PWD"` が返すパス。通常は `docs/rules-reference/incidents.md`）か `docs/rules-reference/` の該当ファイル
    - 意思決定の記録 → `docs/` の該当ファイル（技術判断なら `docs/architecture.md`）
11. **ルールの追加（T0 / T1 / `settings.json`）は自分で書かない。** 本文に **何をしたいか / なぜ / しないとどうなる / トレードオフ / どうやるか** の 5 点をこの語で示し（型と記入例は `docs/rules-reference/approval-template.md`）、そのうえで `AskUserQuestion`（`承認する` / `承認しない` / `修正して提案し直す`）を出す。5 項目は本文に書き、選択肢の説明文に詰め込まない。**承認されたものだけ** `/hirai-lite:add-rule "<ルール案 1 行>"` に渡す（分類 → 重複検査 → 層決定 → 記述最適化 → 予算 → 配置とロード検証の 6 工程）。承認が得られなければ 1 バイトも書かない（`_meta.md` 条 8）。ここで自前の追記手順を作らない。実際に出す文面の例:

    ```
    ### 提案: bash の grep -c の戻り値を T1 に足す
    **何をしたいか**: `.claude/rules/code.md` に 1 行追記 —「メインエージェントは、`grep -c` の結果を
      `tr -cd '0-9'` に通してから数値比較する ／ 例: `n="$(grep -c x f | tr -cd '0-9')"` ／ 失効: なし」
    **なぜ**: 今回 `grep -c` が 0 件で `0` を出しつつ exit 1 を返し、`set -e` の下で落ちた。記録では 2 回目。
    **しないとどうなる**: 同じ書き方が再び入る可能性がある（3 回目が必ず起きるとは言えない。推測）。
    **トレードオフ**: 得る = bash を書く時の判断材料が 1 つ増える ／ 失う = `code.md` が 1,240 → 1,310
      tokens（bash を書かないセッションには影響しない）／ 副作用 = 既存の背景記述と重なるが、
      あちらは背景でこれは規範。
    **どうやるか**: T1（`.claude/rules/code.md`、`paths: src/**, tests/**`）。T0 は 4,231 のまま。
      次に `src/` か `tests/` を読んだ時から効く。
    ```
12. `docs/` に新しいファイルを作った場合だけ、`CLAUDE.md` の Documents index に 1 行足す（実在しない行は消す、という既存の方針に従う）。
13. 何をどこに置いたかを 1 行ずつ報告する。承認待ちのものは「承認待ち」と明示する。

## 履歴を残す場合

上書き前の内容を残すなら、保存の直前に `[ -f .claude/state/latest.md ] && cp .claude/state/latest.md ".claude/state/$(date +%Y%m%d-%H%M).md"` で退避する。

## 判定できる終了条件 (save)

- `ls .claude/state/latest.md` が exit 0。
- `head -1 .claude/state/latest.md` が `# session state` で始まる。
- `wc -l .claude/state/latest.md` が 120 以下。
- 「次回に効くもの」を仕分け済み。0 件ならその旨を 1 行出した。1 件以上なら T2 / `docs/` は追記済み、ルール案は承認を取ったものだけ `/add-rule` に渡した。

4 つ成立したら、次の「利用者へ出す案内」を応答本文に出す。

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

- **手順 1 を「閉じて開き直す」だけに限定しない。** `/clear` は「空のコンテキストで新しい会話を始める」操作で ([公式](https://code.claude.com/docs/en/commands.md))、CLAUDE.md と `.claude/rules/` は「毎回の会話のはじめに読み込まれる」([公式](https://code.claude.com/docs/en/memory.md))。この 2 つから、`/clear` の後もルールは読み込み直される。
- ただし `/clear` と「閉じて開き直す」が**あらゆる点で同じ**とは公式に書かれていない (そこは確認できていない)。迷う利用者には安全側の「閉じて開き直す」を勧めてよい。どちらでも再開はできる。
- 会話の中だけで伝えた指示 (ファイルに書いていないもの) は `/clear` で消える。残したいものは上の「次回に効くものを置く」で置き場を決めるか、この保存に書く。

---

# 再開 (`/state resume`)

## 手順

1. `.claude/state/latest.md` を Read する。ファイルが無ければ「保存された state が無い。/state save で作る」と報告して終了する。
2. `git rev-parse --abbrev-ref HEAD` を実行し、state に書かれた branch と突き合わせる。不一致なら state の branch 名を提示し「切替えますか?」と聞く。承認されたら `git switch <state の branch>` を実行する。承認が無ければ現 branch のまま 3 へ進む。
3. `git log --oneline -1` を実行し、HEAD を突き合わせる。state の HEAD と一致しなければ、`git log --oneline <state の hash>..HEAD` で state 保存後に積まれた commit を列挙し、チャットに提示する。

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

`/state resume loop` で呼ばれた場合、6 のサマリ出力後に mode（進め方）を `loop`（自動で進む）へ書き換え（書き込み先は決め打ちせず `tasks-path.sh` の `harness_mode_write_file "$PWD"` が返す**すでに在る側**。`/hirai-lite:config` と同じ経路）、台帳の `進行中` → `未着手` の順に連続で着手する。着手できるのは対応 draft の `approved_at:` が埋まっているタスクのみ。空のタスクに到達したら、その id を報告して停止する。

loop 実行を止める条件は 3 つ。
- user が停止を指示した。
- 同一のエラー文字列で 3 回連続して失敗した。
- context 使用率が 80% に達した (この場合は `/state save` を実行してから停止する)。

## 判定できる終了条件 (resume)

- `git rev-parse --abbrev-ref HEAD` が state の branch と一致する、または user が現 branch 続行を選んだ。
- 再開サマリ 4 行を出力した。
