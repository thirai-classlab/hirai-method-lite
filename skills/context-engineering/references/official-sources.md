# 出典（Anthropic 公式）

`SKILL.md` の `[a]`〜`[i]` に対応する。**取得日 2026-09-07**（WebFetch で取得）。引用は原文（英語）のまま載せる。訳や要約だけを残すと、次に読む人が原文にあたれない。

---

## [a] Effective context engineering for AI agents（Anthropic Engineering）

<https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents>

> "context engineering refers to the set of strategies for curating and maintaining the optimal set of tokens (information) during LLM inference"

> "as the number of tokens in the context window increases, the model's ability to accurately recall information ... decreases"（記事が **context rot** として引く研究）

> "the minimal set of information that fully outlines your expected behavior"（システムプロンプトの "right altitude" — 決め打ちの硬いロジックと曖昧な指示の中間）

その他、この記事から取った要点:

- **just-in-time retrieval** — 全部を先読みせず「軽い識別子（ファイルパス、保存済みクエリ、リンク）」を持ち、実行時に必要な分だけ読み込む。
- **compaction** — 上限に近づいた会話を要約して新しいコンテキストで再開する。まず recall を最大化し、その後 precision を上げる。
- **structured note-taking** — コンテキストの外にメモを書き出し、後で必要な分だけ引き戻す。
- **sub-agent** — 探索は分離したコンテキストで行い、戻すのは 1,000〜2,000 tokens の要約だけ。

→ このハーネスでの対応: T2 の物理分離（just-in-time）、`/state save`（structured note-taking）、`rules/core.md` の「重い作業は委譲する」（sub-agent）。

---

## [b] How Claude remembers your project（CLAUDE.md / auto memory）

<https://code.claude.com/docs/en/memory.md>

> "CLAUDE.md files are loaded into the context window at the start of every session, consuming tokens alongside your conversation."

> "**Size**: target under 200 lines per CLAUDE.md file. Longer files consume more context and reduce adherence."

> "**Specificity**: write instructions that are concrete enough to verify. For example: 'Use 2-space indentation' instead of 'Format code properly'"

> "**Consistency**: if two rules contradict each other, Claude may pick one arbitrarily."

> "Imported files are expanded and loaded into context at launch alongside the CLAUDE.md that references them."

> "Splitting into `@path` imports helps organization but doesn't reduce context, since imported files load at launch."

> "Add to it when: Claude makes the same mistake a second time"（`_meta.md` 条 1「二度目で書く」と同じ判断）

---

## [c] `.claude/rules/` の発見とパススコープ（同上ページ内）

<https://code.claude.com/docs/en/memory.md>（"Organize rules with `.claude/rules/`" 節）

> "All `.md` files are discovered recursively, so you can organize rules into subdirectories"

> "Rules without [`paths` frontmatter] are loaded at launch with the same priority as `.claude/CLAUDE.md`."

> "Rules can be scoped to specific files using YAML frontmatter with the `paths` field. These conditional rules only apply when Claude is working with files matching the specified patterns."

> "Path-scoped rules trigger when Claude reads files matching the pattern, not on every tool use."

> "Rules load into context every session or when matching files are opened. For task-specific instructions that don't need to be in context all the time, use skills instead, which only load when you invoke them or when Claude determines they're relevant to your prompt."

→ **T0 = `paths:` 無し / T1 = `paths:` あり** はこの規則そのもの。`_meta.md` が T2 を `.claude/rules/` の**外**に置くのは、再帰発見の対象から物理的に外すため（`paths:` の書き忘れが T0 昇格になる事故を構造で防ぐ）。

---

## [d] Skills（progressive disclosure）

<https://code.claude.com/docs/en/skills>

3 段階でロードされる:

1. **メタデータ（name / description）** — 毎ターン context に載る。Claude が使うかどうかを判断するため。
2. **SKILL.md 本文** — 呼ばれた時だけ。> "Unlike CLAUDE.md content, a skill's body loads only when it's used, so long reference material costs almost nothing until you need it."
3. **同梱ファイル（`references/*.md` 等）** — Claude がそれを読んだ時だけ。

> "Keep `SKILL.md` under 500 lines. Move detailed reference material to separate files."

> "Once loaded, skill content stays in context across turns, so every line is a recurring token cost."

> Create a skill when "you keep pasting the same instructions, checklist, or multi-step procedure into chat, or when a section of CLAUDE.md has grown into a procedure rather than a fact."

→ 方法論（手順・判断基準）を T0 ではなく skill に置く根拠。`disable-model-invocation: true` を付ければ説明文すら載らないが、`/state save` から Claude 自身に読ませたいので**付けていない**。

---

## [e] 指示は強制ではない（同 memory ページ）

<https://code.claude.com/docs/en/memory.md>

> "Claude treats them as context, not enforced configuration. To block an action regardless of what Claude decides, use a PreToolUse hook instead."

> "CLAUDE.md content is delivered as a user message after the system prompt, not as part of the system prompt itself. Claude reads it and tries to follow it, but there's no guarantee of strict compliance"

<https://code.claude.com/docs/en/features-overview>

> "Put guardrails in hooks. An instruction like 'never edit `.env`' in CLAUDE.md or a skill is a request, not a guarantee. A `PreToolUse` hook that blocks the edit is enforcement."

→ `_meta.md` 条 9「無い保証を書かない」と条 5「機械強制は不可逆操作のみ」の公式側の裏付け。

---

## [f] 機能ごとのコンテキスト費用と、追加のきっかけ

<https://code.claude.com/docs/en/features-overview>

> "Every feature you add consumes some of Claude's context. Too much can fill up your context window, but it can also add noise that makes Claude less effective; skills may not trigger correctly, or Claude may lose track of your conventions."

| Feature | When it loads | Context cost（原文） |
|---|---|---|
| CLAUDE.md | Session start | "Every request" |
| Skills | Session start + when used | "Low (descriptions every request)" |
| Hooks | On trigger | "Zero, unless hook returns additional context" |
| Subagents | When spawned | "Isolated from main session" |

"Build your setup over time" の対応表（抜粋）:

> "Claude gets a convention or command wrong twice → Add it to CLAUDE.md"
> "You paste the same playbook or multi-step procedure into chat for the third time → Capture it as a skill"
> "You want something to happen every time without asking → Write a hook"

→ 「2 回目で書く」「手順は skill へ」「毎回必ずなら hook」という切り分けは公式と一致している。

---

## [g] 圧縮（`/compact`）で何が残るか

<https://code.claude.com/docs/en/context-window>

| 対象 | 圧縮後（原文） |
|---|---|
| Project-root CLAUDE.md and unscoped rules | "Re-injected from disk" |
| Auto memory | "Re-injected from disk" |
| Files Claude read or edited | "Claude Code re-reads up to five, most recently modified first" |
| Invoked skill bodies | "Re-injected, capped at 5,000 tokens per skill and 25,000 tokens total; oldest dropped first" |

> "Path-scoped rules and nested CLAUDE.md files load into message history when their trigger file is read, so compaction summarizes them away with everything else. ... If a rule must persist across compaction, drop the `paths:` frontmatter or move it to the project-root CLAUDE.md."

> "Truncation keeps the start of the file, so put the most important instructions near the top of `SKILL.md`."

→ **T1 は圧縮で消える**（一致ファイルを読み直すまで戻らない）。圧縮をまたいで効かせたい規範は T0 に置く、という層選択の根拠。skill の書き方（結論を上、詳細を `references/`）の根拠でもある。

---

## [h] プロンプトの書き方（理由を添える / 長い入力の置き方）

<https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices>
（`.../prompt-engineering/long-context-tips` は 302 でこのページへ転送される。2026-09-07 実測）

> "Providing context or motivation behind your instructions, such as explaining to Claude why such behavior is important, can help Claude better understand your goals and deliver more targeted responses."

Long context prompting（20k+ tokens の入力を扱うとき）:

> "**Put longform data at the top:** Place your long documents and inputs near the top of your prompt, above your query, instructions, and examples. This improves performance across all models."

> "**Ground responses in quotes:** For long document tasks, ask Claude to quote relevant parts of the documents first before carrying out its task."

---

## [i] 複数コンテキストにまたがる作業（`/state save` の裏付け）

<https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices>（"Long-horizon reasoning and state tracking" 節）

> "This capability especially emerges over multiple context windows or task iterations, where Claude can work on a complex task, save the state, and continue with a fresh context window."

> "As you approach your token budget limit, save your current progress and state to memory before the context window refreshes."

> "**Starting fresh versus compacting:** When a context window is cleared, consider starting with a brand new context window rather than using compaction. Claude's latest models are extremely effective at discovering state from the local filesystem."

> "Be prescriptive about how it should start: ... 'Review progress.txt, tests.json, and the git logs.'"

→ `/state save` → `/clear` → `/state resume` という流れ（要約ではなくファイルから復元し、次に実行するコマンドを 1 つだけ書く）は、この節の指示と同じ形をしている。

---

## 参考: auto memory との関係（確認できた事実）

`[b]` のページには、Claude 自身が学びを書き溜める **auto memory**（`~/.claude/projects/<project>/memory/`、既定 on、`MEMORY.md` の先頭 200 行 / 25KB が毎セッション読み込まれる）がある。

- **auto memory はマシンローカル**で、チームに共有されない（原文: "Auto memory is machine-local. ... Files are not shared across machines or cloud environments."）。
- **Claude はスキップする対象を持つ** — 原文: "It also skips anything your CLAUDE.md files already say."

→ このハーネスが `/state save` で**リポジトリ内のファイル**に書くのは、共有・レビュー・履歴（git）が要るため。auto memory と競合はしない（あちらは個人の学び、こちらはチームの規範と記録）。
