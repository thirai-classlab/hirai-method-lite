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

T0 は毎セッション常時ロード（合計 6,000 tokens で警告 / 10,000 tokens が上限）。T1 は `paths:` に該当するファイルを触った時のみロードされる。

| 層 | ファイル | ロード条件 | 内容 |
|---|---|---|---|
| T0 | `CLAUDE.md`（本ファイル） | 常時 | プロジェクト固有情報 + rules index |
| T0 | `.claude/rules/_meta.md` | 常時 | ルール追加のルール 9 条 / 層定義 / 記述テンプレート |
| T0 | `.claude/rules/core.md` | 常時 | 全作業に例外なく効く行動規範 |
| T1 | `.claude/rules/tasks.md` | `docs/{tasks,draft}/**` + `.claude/{tasks,draft}/**` | タスク台帳と draft 承認の運用 |
| T1 | `.claude/rules/code.md` | `src/**`, `tests/**` | 実装とレビューの運用 |
| T1 | `.claude/rules/ops.md` | `.github/**`, `infra/**`, `*.tf` | CI / インフラの運用 |
| T2 | `docs/rules-reference/**`（無ければ `.claude/rules-reference/**`） | 明示 Read のみ | 背景・事故記録・詳細手順 |
| T3 | `.claude/rules-archive/**` | ロードしない | 失効ルールの履歴 |

`.claude/rules/` の中身は プラグイン `hirai-lite` の `/init` が配置する。ルールの追加は `.claude/rules/_meta.md` のパイプライン（`/add-rule`）を通す。`@import` は使わない。

## Documents index

| ファイル | 内容 |
|---|---|
| `docs/overview.md` | ゴール / 背景 / スコープ / 体制と関係者 / ドメイン用語 / 関連リポジトリ |
| `docs/requirements.md` | 要件（機能・非機能） |
| `docs/architecture.md` | 構成 / データの持ち方 / 技術判断とその理由 |
| `docs/tasks/list.md` | やること一覧。**いまどこまで進んでいるかもここで分かる**（進捗表は別に作らない） |
| `docs/draft/` | 設計メモ（承認後に task 化） |
| `docs/rules-reference/` | 背景・事故記録（必要なとき読む） |

`.claude/rules/` のルールは、この表に書かなくても自動で読み込まれる（frontmatter 無し = 常時 / `paths:` 付き = 該当ファイルを触った時）。この表は所在を把握するためのもの。**実在しない行は消す**（`/hirai-lite:init` の 2 回目が実際に作った分だけ残す）。

## mode（進め方）

`.claude/mode.yml` の `mode:` で決まる。`normal`（確認あり）/ `loop`（自動で進む）。切替は `/hirai-lite:config`。詳細は `.claude/rules/core.md` の該当条。
