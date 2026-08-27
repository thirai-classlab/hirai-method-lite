# 変更履歴

版の付け方は [semver](https://semver.org/lang/ja/)。`VERSION` / `.claude-plugin/plugin.json` / `.claude-plugin/marketplace.json` の 3 つは常に同じ値を持ち、`tests/smoke.sh` case 9 が一致を検証する。

更新のしかたは [README の「更新する」](README.md#更新する自動では新しくなりません)。**プラグインは自動更新されない。**

## v0.9.0

- **`/update` が全プロジェクト共通 (`/init user`) の導入先を更新しない不具合を修正。** 手順 3 が入れ替え先を `.claude/` に決め打ちしていたため、`/hirai-lite:init user` でホーム側 (`$HOME/.claude/`) に入れた人は、実際に使われている `~/.claude/statusline.sh` が古いまま残り、使われないコピーがプロジェクト側に新しく作られていた（実測で再現）。**プロジェクト側とホーム側の両方を見て、すでに在る側だけを入れ替える**ように変更（置いていない場所に新規作成しない）。
- **`/update` 手順 1 のコマンドを正確化。** `/plugin marketplace update hirai-lite` → `/plugin update hirai-lite@hirai-lite` の 2 行と、1 行目を飛ばすと 2 行目が古い控えを見て「最新です」と答えることを明記。ターミナル実行時に `--scope` の既定が `user` である点も追記。
- **更新の合図が出ない条件を文書化。** 合図は「入れた直後の 1 セッション目」と「前回調べてから 24 時間」の間は必ず沈黙する。**合図が出ないことは最新であることの証明にならない。** いますぐ確かめる手順（リモートの `VERSION` と `claude plugin list` の比較、控え `${TMPDIR:-/tmp}/claude-harness-lite` の削除）を README と `/update` に追記。
- **README に「更新する」節を新設**し、v0.6.0 以前の注意を明記。

## v0.8.1

- 利用者向け説明の「リポジトリ」を「プロジェクト」に統一。

## v0.8.0

- 導入手順を 1 節に統合し、入れる範囲は **Local** を推奨に変更。

## v0.7.0

- **`plugin.json` の `hooks` キー衝突を解消**（`9b9e991`）。`hooks` / `commands` / `agents` の 3 キーを外し、Claude Code の既定配置（`hooks/hooks.json` / `commands/` / `agents/`）に任せる形へ。**v0.6.0 以前で出ていた `✘ failed to load` はここで解消した。**
- インストール時に表示される確認の説明を追記。

## v0.6.0 以前 — `✘ failed to load` と表示される（要更新）

**v0.1.0 〜 v0.6.0 には不具合がある。** `plugin.json` の `hooks` キーが、Claude Code が自動で読み込む `hooks/hooks.json` を二重に指していたため、`/plugin` の一覧や `claude plugin list` で次のように表示される。

```
Status: ✘ failed to load
Error: Hook load failed: Duplicate hooks file detected: ./hooks/hooks.json resolves to
already-loaded file …/hooks/hooks.json. The standard hooks/hooks.json is loaded
automatically, so manifest.hooks should only reference additional hook files.
```

**Claude Code 2.1.247 で実測した範囲では、この表示が出ていても機能そのものは動いていた** — v0.6.0 を実際にインストールして計測したところ `Registered 2 hooks` / `Total plugin commands loaded: 12` / `Total plugin agents loaded: 3` で、MCP サーバー 2 つ（`serena` / `context7`）も接続できた。ただし `claude plugin details` はエージェント数を 0 と誤表示する。

とはいえ「読み込みに失敗した」と表示され続けるのは正常な状態ではなく、Claude Code の版によっては本当に読み込まれない可能性がある。**該当版を入れている場合は [README の「更新する」](README.md#更新する自動では新しくなりません)の手順で v0.7.0 以降へ更新すること。**

| 版 | 主な内容 |
|---|---|
| v0.6.0 | README を平易化し、`/hirai-lite:init user`（全プロジェクト共通への配置）に対応 |
| v0.5.0 | MCP サーバー 2 種とエージェント 3 種を同梱。`/update` の更新漏れを修正 |
| v0.4.0 | `/init` と mode の表示を平易な日本語に |
| v0.3.0 | `docs/` 非依存の徹底と `/init` 手順の欠陥 6 件を修正 |
| v0.2.0 | `ultracode` を既定で有効化 |
| v0.1.0 | Claude Code プラグイン構成へ移行（`install.sh` 廃止） |
