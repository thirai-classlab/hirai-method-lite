---
description: ハーネス (プラグイン hirai-lite) を最新版に更新し、rules を再配置して、VERSION で版が上がったことを検証する。
---

# /update

**最優先の注意: ユーザーのカスタマイズを壊さない。**
`CLAUDE.md` / `docs/` / 台帳 (`list.md` `parking-lot.md`) / `.claude/mode.yml` / `.claude/settings.json`
はユーザーの資産であり、更新で上書きしない。プラグイン更新が入れ替えるのはプラグイン本体
(`commands/` `hooks/` `rules/` `scripts/` `templates/` と `VERSION`) だけで、導入先リポジトリの
`.claude/` には触れない。`.claude/rules/` を直接編集して運用している場合は、再配置の前に退避する。

## 手順 0: 現在の版を控える

```bash
cat "$CLAUDE_PLUGIN_ROOT/VERSION" 2>/dev/null || echo "VERSION なし"
cp -R .claude/rules /tmp/rules.bak 2>/dev/null && echo "rules を /tmp/rules.bak へ退避"
```

`VERSION` の値を「更新前の版」として控える。

## 手順 1: プラグインを更新する

```
/plugin marketplace update
/plugin update hirai-lite
```

- `/plugin marketplace update` でマーケットプレイスの一覧を取り直し、`/plugin update` で本体を入れ替える。
- 入れ替えは**再起動で反映される**。Claude Code を開き直してから次へ進む。

## 手順 2: rules を再配置する

**rules はプラグイン更新では導入先に配られない。** 更新後に必ず実行する。

```
/hirai-lite:init
```

`/init` は既存ファイルを上書きしない。新しい rules を取り込むには、取り込みたいファイルを
`.claude/rules/` から先に削除してから `/init` を実行する。手順 0 の `/tmp/rules.bak` と
`diff -ru /tmp/rules.bak .claude/rules` で突き合わせ、自分の変更が消えていないかを確認する。

## 手順 3: 版が上がったことを検証する

```bash
cat "$CLAUDE_PLUGIN_ROOT/VERSION"
bash "$CLAUDE_PLUGIN_ROOT/tests/smoke.sh"
git status --short
```

- `VERSION` が手順 0 で控えた値より新しくなっていること。
- smoke が全 case PASS / exit 0 であること。FAIL が出たら更新を止め、内容を報告する。
- `git status --short` に `CLAUDE.md` と `docs/` の変更が出ていないこと。

版が変わらない場合は、既に最新か、`/plugin update` の後に再起動していない。
`claude plugin list` で導入済みの版を確認する。

## 更新検知について

SessionStart で `[harness] 更新あり vX → vY (/update で適用)` が出た時だけ実行すればよい。
検知は 24 時間に 1 回・背景通信で、オフラインでも起動を遅らせない。
止めたい場合は `HARNESS_UPDATE_CHECK=off` を環境変数に設定する。

## 判定できる終了条件

- `cat "$CLAUDE_PLUGIN_ROOT/VERSION"` が更新前より新しい semver を返す。
- `bash "$CLAUDE_PLUGIN_ROOT/tests/smoke.sh"` が exit 0。
- `git status --short` に `CLAUDE.md` と `docs/` の変更が出ていない。
