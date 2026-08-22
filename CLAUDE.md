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

T0 は毎セッション常時ロード（合計 3,000 tokens 上限）。T1 は `paths:` に該当するファイルを触った時のみロードされる。

| 層 | ファイル | ロード条件 | 内容 |
|---|---|---|---|
| T0 | `CLAUDE.md`（本ファイル） | 常時 | プロジェクト固有情報 + rules index |
| T0 | `.claude/rules/_meta.md` | 常時 | ルール追加のルール 8 条 / 層定義 / 記述テンプレート |
| T0 | `.claude/rules/core.md` | 常時 | 全作業に例外なく効く行動規範 |
| T1 | `.claude/rules/tasks.md` | `docs/tasks/**`, `docs/draft/**` | タスク台帳と draft 承認の運用 |
| T1 | `.claude/rules/code.md` | `src/**`, `tests/**` | 実装とレビューの運用 |
| T1 | `.claude/rules/ops.md` | `.github/**`, `infra/**`, `*.tf` | CI / インフラの運用 |
| T2 | `docs/rules-reference/**` | 明示 Read のみ | 背景・事故記録・詳細手順 |
| T3 | `.claude/rules-archive/**` | ロードしない | 失効ルールの履歴 |

ルールの追加は `.claude/rules/_meta.md` のパイプラインを通す。`@import` は使わない。

## Mode

`.claude/mode.yml` の `mode:` が `normal` か `loop` を決める。挙動は `.claude/rules/core.md` の Loop モード条を参照。
