# CLAUDE.md

> 汎用ハーネステンプレート。`<...>` をプロジェクトの実値に置換して使う。
> 行動規範は書かない（`.claude/rules/core.md` が担う）。ここはプロジェクト固有情報と rules への index に限る。

## プロジェクト概要

`<プロジェクト名>` — `<1〜2 行で役割を説明>`

- 本番: `<URL>`
- リポジトリの責務: `<このリポが何を持ち、何を持たないか>`

## Tech Stack

- 言語 / フレームワーク: `<例: TypeScript / Next.js App Router>`
- ランタイム: `<例: Node 22+, React 19>`
- DB: `<例: PostgreSQL on Supabase>`
- ホスティング: `<例: Vercel>`
- 詳細: `<docs/tech-stack.md>`

## Commands

```bash
<例: npm run dev>      # 開発サーバ
<例: npm run build>    # ビルド
<例: npm test>         # テスト
<例: npm run lint>     # lint
```

## Rules index

決まりごとは `.claude/rules/` にあり、プラグイン `hirai-lite` の `/hirai-lite:init` が置く。層・予算・追加の手順は `.claude/rules/_meta.md`。毎回読まれるのは本ファイルと `_meta.md`・`core.md` で、`tasks.md`・`code.md`・`ops.md` は `paths:` に当たるファイルを読む・書くときだけ読まれる。背景と事故記録は `docs/rules-reference/`（必要なときだけ読む）。ルールの追加は `/hirai-lite:add-rule` を通す。`@import` は使わない（例外は `@AGENTS.md` だけ）。

## Documents index

| ファイル | 内容 |
|---|---|
| `docs/overview.md` | ゴール / 背景 / スコープ / 体制と関係者 / ドメイン用語 / 関連リポジトリ |
| `docs/requirements.md` | 要件（機能・非機能） |
| `docs/architecture.md` | 構成 / データの持ち方 / 技術判断とその理由 |
| `docs/tasks/list.md` | やること一覧（台帳）。**いまどこまで進んでいるかもここで分かる**（進捗表は別に作らない）。`.claude/mode.yml` が `tasks: github-project` のリポは、この行を「GitHub Project」に置き換える（立ち上げは `/hirai-project-method:project-setup`） |
| `docs/draft/` | 設計メモ（承認後に task 化） |
| `docs/rules-reference/` | 背景・事故記録・承認の型（必要なとき読む） |

`.claude/rules/` のルールは、この表に書かなくても自動で読み込まれる（frontmatter 無し = 常時 / `paths:` 付き = 該当ファイルを触った時）。この表は所在を把握するためのもの。**実在しない行は消す**（`/hirai-lite:init` の 2 回目が実際に作った分だけ残す）。

## mode（進め方）

`.claude/mode.yml` の `mode:` で決まる。`normal`（確認あり）/ `loop`（自動で進む）。切替は `/hirai-lite:config`。詳細は `.claude/rules/core.md` の該当条。
