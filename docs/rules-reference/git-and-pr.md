# git / PR の落とし穴

`rules/core.md` の commit 粒度・承認が要る操作、`rules/code.md` の commit 規約の背景。

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

## 3. 完了 commit に台帳を同乗させる

merge 後に統合先ブランチ上で台帳だけを直すことはできない (承認が要る操作のため)。台帳の 1 行を直すためだけに追加の PR が必要になった記録がある。詳細は [`task-ledger.md`](task-ledger.md) の項目 4 を参照。

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

## 関連

- 並列委譲時の git 制約: [`subagent-operations.md`](subagent-operations.md)
- 台帳と完了 commit: [`task-ledger.md`](task-ledger.md)
- 事故の一覧台帳: [`incidents.md`](incidents.md)
