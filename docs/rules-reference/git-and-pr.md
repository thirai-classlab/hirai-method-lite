# git / PR の落とし穴

`rules/core.md` の commit 粒度・承認が要る操作、`rules/code.md` の commit 規約・PR の規範の背景。

---

## 1. 未 merge の PR のブランチに積むと、本流に届かない

**何が起きたか**: あるタスクの PR を、まだ merge されていない別の PR のブランチを base にして作った。親の PR が merge された後、`gh` の表示は **MERGED** になったが、子 PR の内容は `main` に一切届いていなかった。`main` から新しいブランチを切って cherry-pick し、新しい PR で入れ直して復旧した。2026-06-01 観測。

**なぜ起きたか**: 親 PR を `main` に merge すると、その瞬間の**親ブランチの HEAD** が入る。その後に親ブランチへ merge された子は同乗しない。`gh` の MERGED 表示は「親ブランチへ merge された」ことを指しており、`main` に届いたことを意味しない。

**どう対処するか**:

- 独立したタスクの PR は **base を `main` にする**
- 積むしかないときは、親の merge 後に `main` から新しいブランチを切って `git cherry-pick <子の commit>` で入れ直す
- **merge 後は `git checkout main && git pull` して、実際にファイルがあるか `ls` / `grep` で確認する**。`gh` の表示を根拠にしない

**出典**: 旧ハーネス memory `feedback_stacked_pr_base_pitfall` (2026-06-01)。

---

## 2. 並列エージェントに `git reset` を使わせない

同一ブランチで並列に commit させていた subagent の 1 件が `git reset --soft HEAD^` を実行し、他のエージェントの commit を巻き込んで orphan 化させた記録がある。詳細と対処、および orphan の回収方法 (`git log --all --reflog --oneline` → `git cherry-pick`) は [`subagent-operations.md`](subagent-operations.md) の項目 6 を参照。

---

## 3. 完了の印は PR に同乗させる

merge 後に統合先ブランチ上で完了の印だけを直すことはできない (承認が要る操作のため)。GitHub の形では、PR の本文に `Closes #<番号>` を書いておけば merge で issue が閉じ、Status が 完了 になる。積み上げ PR（base が main 以外）は自動では閉じない。`hirai-task review <番号>` は PR を出したときに Status を レビュー中 にするだけで、issue は閉じない。積み上げの PR は、merge のあと `hirai-task done <番号>` で issue を閉じる。ファイルに一覧表を持つ形（台帳の形）で追加の PR が必要になった記録は [`task-ledger.md`](task-ledger.md) の項目 4 を参照。

---

## 4. 複合コマンドは、文字列で判定する層を誤作動させる

**何が起きたか**: `git push -u origin <feature> && gh pr create --base main ...` を 1 つの Bash 呼び出しにまとめたところ、`--base main` に含まれる `main` が push 先と誤解され、保護ブランチへの push として拒否された。2026-07-05 観測。

**旧ハーネス固有の注記**: この拒否をしたのは旧ハーネスの独自ガードであり、新ハーネスには存在しない。ただし、**コマンド文字列を正規表現で判定する層は一般に存在する** (`settings.json` の `permissions` もその一種) ため、教訓は残る。

**どう対処するか**: push と PR 作成は**別の呼び出しに分ける**。複合コマンドは、文字列マッチで判定するあらゆる層を誤作動させうる。加えて、複合コマンドはツール呼び出しの構造化出力自体を壊す要因でもある ([`subagent-operations.md`](subagent-operations.md) 項目 2)。

**出典**: 旧ハーネス memory `feedback_push_prcreate_compound_guard_false_positive` (2026-07-05)。

---

## 5. PR 本文や commit message は、長くなるならファイル経由で渡す

**何が起きたか**: 複数行の本文をヒアドキュメントでコマンドラインに埋め込んだところ、旧ハーネスのガードがコマンドの区切りを誤認して拒否した。累計 4 回発生し、`-F <file>` / `--body-file <path>` 経由に切り替えて解決した。2026-05-23 / 2026-05-24 / 2026-05-28 観測。

**旧ハーネス固有の注記**: 拒否の原因は旧ハーネス独自のコマンド分割処理のバグであり、新ハーネスには無い。

**それでも残る理由**: 引用符と改行を多く含むペイロードをコマンドラインに詰めることは、ツール呼び出しの構造化出力を壊す既知の要因である (同上)。**長い本文はファイルに書いて `-F` で渡す**のは、ガードの有無と関係なく妥当な習慣である。

**出典**: 旧ハーネス memory `feedback_dash_bullet_heredoc_commit_block` / `feedback_pr_create_minimal_body_pattern`。

---

## 6. 着手前に「すでに直っていないか」を履歴で確認する

指摘に対する作業を計画・委譲したが、既存の commit ですでに解消済みで空振りした記録がある。`git log --all --grep <キーワード>` を計画段階で掛ける。詳細は [`design-process.md`](design-process.md) の項目 10 を参照。

---

## 7. 積み上げた PR は、下が squash で入ったら付け替えて出し直す

**何が起きたか**: 下の PR が squash で入ったあと、上の PR の base を `gh pr edit --base` で付け替えた。付け替えが起こすのは `edited` だけで、CI もレビューも走らず、検査の結果は古い base で測ったまま残った。

**どう対処するか**: `git fetch origin` → `git rebase --onto origin/<既定の branch> <下の PR の最後の commit> <上の branch>` → `git push --force-with-lease`（user の承認を取る）→ `hirai-pr-retarget <PR 番号> <新しい base>`（土台の `bin/`。Bash ツールでは PATH に入る）。閉じて開き直すので `reopened` で CI とレビューが起動する。付け替えのあとは `gh pr checks <n>` で新しい実行を待つ。

---

## 8. merge を頼む前に、検査とレビューの合格を見る

**何が起きたか**: 検査が止まっている（課金・queue）PR と、AI レビューが終わっていない PR に merge を頼み、merge のあとで直しが入って追いの PR になった。

**どう対処するか**: merge を頼む前に、`gh pr checks <n>` で必須の検査が全て pass、AI レビューが CRITICAL・HIGH 0 件で終わっていることを見る。検査が走らない事情があるときは、手元で通した CI の全ジョブの結果を PR に貼り、user に「検査が止まっている」と伝えたうえで頼む。PR を作る手順では、本文に `Closes #<n>`（台帳の形は `task-<id>`）を 1 行入れる。

---

## 9. PR の本文は、課題から実装へ抽象から具体の順に書く

**何が起きたか**: PR の本文がコードの変え方（「関数 X を Y に変えた」）から始まり、読む人はどのファイルから読めばよいか、何がどう変わるのか、どんな課題の解決なのかを本文から読み取れなかった（2026-11-23 のユーザーの指摘。「どのファイルを読めばいいのか、何がどう変わるのか、抽象から具体までを説明してくれないとわからない」）。

**どう対処するか**: 本文は 9 節の型で書く。雛形は `templates/pull_request_template.md`（`/hirai-lite:init` が導入先の `.github/pull_request_template.md` に、無ければ置く。あれば触らない）。

| 節 | 書くこと |
|---|---|
| 1 ひとことで | 課題と解決を 2 行。1 行目は何に困っていたか、2 行目はどう解いたか |
| 2 課題 | 誰が・いつ・何に困るか。起きた事故と数字（件数は何の件数かを書く） |
| 3 解決の方針 | 考え方と、採らなかった案とその理由 |
| 4 何が変わるか | 前と後。画面は前後のキャプチャ、CI や検査は「こういう変更が、こう落ちる」の例を 1 つ |
| 5 読む順 | ファイル 3〜5 本と、そこで何を見るか。読まなくてよいもの（生成物・整形だけの差分）も名指しする |
| 6 実装の要点 | 読む順のファイルの中で、判断が入ったところだけ（3〜5 行） |
| 7 確かめたこと | 走らせたコマンドと exit code。未検証は「未検証」と書く |
| 8 承認カード・決めてほしいこと | merge を頼む 7 行のカード（型は [`approval-template.md`](approval-template.md)）。決めてほしいことが他にあれば 1 行ずつ |
| 9 対応する issue | `Closes #<n>`（台帳の形は `task-<id>`）と、設計・ADR の path と役割を 1 行ずつ |

**画面のキャプチャ**: GitHub には画像を CLI から PR に添付する口が無い。`hirai-pr-asset <PR 番号> <png ...>`（土台の `bin/`。Bash ツールでは PATH に入る）が、画像だけを積む branch `pr-assets` に置き、本文に貼る Markdown の 1 行を出す。作業ツリーの branch と index は動かさない。押し先は git の remote の URL から引く（remote を読めないと exit 1）。

**ユーザーへの報告も同じ向き**: 結論と意味を先に、詳細はあとに書く（`rules/core.md`「事実で答える」）。

## 関連

- 並列委譲時の git 制約: [`subagent-operations.md`](subagent-operations.md)
- 完了の印と PR: 上の項目 3、台帳の形の記録は [`task-ledger.md`](task-ledger.md)
- 事故の一覧台帳: [`incidents.md`](incidents.md)
