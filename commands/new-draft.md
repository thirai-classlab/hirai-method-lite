---
description: 現在形の文書（仕様・設計・規範）を変える、仕様を変える、会話・会議・Slack・issue で決まったことを文書へ入れる、と言われたとき、分かれ道（提案なしで直す／決定だけ ADR／提案を起こす）を判定し、提案が要るなら draft dir（通常 docs/draft/）に設計 draft を起こす。承認を得るまでタスク化しない、設計→承認→タスク化フローの起点。
---

# /new-draft <slug>

`<slug>` は lowercase の英数字とハイフンのみ、3〜49 文字。引数が空、または書式に一致しない場合は正しい slug を聞き返して停止する。

## draft dir の解決 (最初に 1 回)

draft dir は `$HARNESS_DRAFT_DIR` > 既存の `docs/draft/` > (旧レイアウト) 既存の `.claude/draft/` > (どちらも無ければ) `docs/draft/` の順に解決する。台帳と同じ解決順で、**新しく作るときは常に `docs/draft/`**。

```bash
P="${CLAUDE_PLUGIN_ROOT}"; [ -d "$P" ] || P="$(command -v python3 >/dev/null 2>&1 && python3 -c 'import json,re,sys; d=json.load(open(sys.argv[1])); r=[x for k,v in d.get("plugins",{}).items() if k.split("@",1)[0]==sys.argv[2] for x in v if x.get("installPath")]; r.sort(key=lambda x:[int(n) if n.isdigit() else 0 for n in re.split(r"[.]", str(x.get("version","0")).split("-",1)[0])]); print(r[-1]["installPath"] if r else "")' "$HOME/.claude/plugins/installed_plugins.json" hirai-lite 2>/dev/null)"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"
. "$P/scripts/tasks-path.sh"; DRAFT="$(harness_draft_dir "$PWD")"
mkdir -p "$DRAFT"
echo "$DRAFT"
```

以降この文書の `docs/draft/` は `$DRAFT/` に読み替える。

## 分かれ道（最初に判定する）

現在形の文書を変える依頼は、すべてここを通す。外で決まったこと（会話・会議・Slack・issue）を文書へ入れる依頼も同じ。次の順で最初に当たる行で決める。判定と根拠をチャットに 1 行で出す。

| 当たる条件 | 行き先 |
|---|---|
| 要件・受入・範囲・利用者の振る舞いが増減する／2 案以上から選ぶ必要がある | **C 提案が要る** → 下の手順へ進む |
| 決まった決定を 1 つ残すだけで、要件・受入・範囲は増減しない | **B 決定だけ ADR** → ADR を 1 本起こして終える（この draft は作らない。ADR の置き場は導入先の `CLAUDE.md` の書類の表が指す場所。表に無ければ user に聞く） |
| 現在形の文を、すでに決まった内容に合わせて直すだけ（誤記・リンク切れ・実装との食い違い） | **A 提案なし** → 文書を直す PR で終える |

外で決まったことの受け方: 決まった内容・決めた人・日付・出どころ（URL か発言）を 1 行ずつ書き出してから上の表にかける。出どころが示せないものは「未検証」と書き、決まったこととして文書へ入れない。迷ったら C に倒す（提案は承認で止まるので、戻せる側に倒れる）。手順の詳細: `docs/rules-reference/design-process.md`。

## 手順

1. `ls "$DRAFT/<slug>.md"` が exit 0 を返したら「既に存在する」と報告し、上書きせずに終了する。
2. **変える文書を聞く。** この提案が変える現在形の文書（path）を 1 つ以上、`AskUserQuestion` で 1 問ずつ聞く。導入先の `CLAUDE.md` が文書を層や領域で分けているときは、その層と領域も聞く。答えが決まらないときは先へ進まない。
3. **読む束を読む。** 次を読む（無いものは「無い」と言って飛ばし、推測で埋めない）。
   - `$P/templates/draft.md`（雛形。12 節の見出しと先頭の 13 項目はここが正。この文書は雛形を写さない）
   - 導入先の `CLAUDE.md` が「文書の形式」として指す文書（例: `docs/harness/doc-formats.md`）。見出しの文字列と先頭の項目の置き方の正
   - 変える文書と、導入先の `CLAUDE.md` が指す領域ごとの README（領域を持つ導入先のとき）
4. `$DRAFT/<slug>.md` を `$P/templates/draft.md` から新規作成する。`id_prefix:` を決め（英大文字 2〜10 字。既存の提案と重ならないこと）、`<…>` をすべて埋めるか消す。`status: 起案`・`approved_at:` は空のまま。節の見出しは変えない（導入先に `scripts/check-drafts.sh` があれば、それが見る）。
   §1〜§11 を埋める（§10 完了条件と §11 task は `/hirai-lite:new-task` が読む節。完了条件は task の完了条件へ、§11 は task の一覧へ写される）。§10 は `npm test` の exit 0 のような判定できる形にする。埋められない項目は `未定:` を付けて残し、user に質問する。
   禁止語彙を検査する。`grep -nE '適切に|必要に応じて|可能な限り|十分に|慎重に' "$DRAFT/<slug>.md"` が 1 件でもヒットしたら、その行を判定できる条件へ書き換えて再検査する。
5. draft の §6 採用と §10 完了条件を要約してチャットに提示し、承認を求める。
   **承認を求めるときは承認カード**（決めること・推奨 / 目的 / 位置 / 承認すると / しないと / 注意 / 詳しく）**を本文に示してから** `AskUserQuestion`（`承認する` / `承認しない` / `修正して提案し直す`）**を出す。型と記入例**: `docs/rules-reference/approval-template.md`（プロジェクトに無ければプラグイン同梱の同名ファイル。`AskUserQuestion` が使えないときの平文の出し方も同じファイル）。 「決めること」は採る案を 1 文で（§6 採用の要旨）、「目的」は §1 の利用者と事業への効果、「承認すると」は §10 完了条件と作業の数を入れる。
6. user がチャットで承認したら frontmatter の `approved_at:` に `YYYY-MM-DD（チャット）` を入れ、§12 に `- YYYY-MM-DD 承認（チャット）` を追記する。承認が無い間 `approved_at:` は空のままにする。
7. チャットではなく PR で承認を得る運用のときは、この draft には対応する issue を作らず、`no-issue` の PR (依頼元の issue があれば `Refs #n` を本文に書く) で出す。その PR の merge を承認とみなす。**PR を出すときに** `approved_at:` へ `PR #<n> の merge で承認` と書き、§12 にも `- PR #<n> の merge で承認` を足してから merge を頼む（merge の後に埋める人がいないため）。merge したあとの追記は要らない。未裁定の論点が残る間は merge しない。

## 判定できる終了条件

- 分かれ道の判定（A・B・C のどれか）と根拠がチャットに出ている。A と B なら、ここで終わり（draft は作らない）。
- `$DRAFT/<slug>.md` が存在する (通常 `docs/draft/` の下)。
- 禁止語彙 grep が 0 件。
- `bash scripts/check-drafts.sh "$DRAFT/<slug>.md"` が exit 0（プロジェクトに無ければ省く）。
- 承認済なら `grep -E '^approved_at: (20|PR #)' "$DRAFT/<slug>.md"` が exit 0。

## この後

承認済 draft は `/hirai-lite:new-task <id> <slug>` でタスク化する。`approved_at:` が空の draft をタスク化しない。
