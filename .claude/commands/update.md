---
description: ハーネス本体を最新版に更新する。導入経路 (プラグイン / install.sh) で手順を分け、更新後に VERSION で版が上がったことを検証する。
---

# /update

**最優先の注意: ユーザーのカスタマイズを壊さない。**
`CLAUDE.md` / `docs/` / 台帳 (`list.md` `parking-lot.md`) / `.claude/mode.yml` / `.claude/settings.local.json`
はユーザーの資産であり、更新で上書きしない。上書きされるのは `.claude/rules` `.claude/hooks`
`.claude/commands` `.claude/scripts` と `VERSION` に限る。この 4 ディレクトリを直接編集して
運用している場合は、先に差分を退避してから実行する。

## 手順 0: 現在の版と導入経路を確認する

```bash
cat VERSION 2>/dev/null || echo "VERSION なし"
ls -d ~/.claude/plugins/*/hirai-method-lite 2>/dev/null || echo "プラグイン導入ではない"
```

`VERSION` の値を「更新前の版」として控える。以降は経路ごとに分岐する。

## 手順 A: プラグイン経由で入れた場合

```
/plugin marketplace update
/plugin update
```

- `/plugin marketplace update` でマーケットプレイスの一覧を取り直し、`/plugin update` で本体を入れ替える。
- **rules はプラグイン更新では再配置されない。** 更新後に init 系コマンド (`/init-tasks` 等、
  ハーネスが提供する初期化コマンド) を実行して `.claude/rules/` を配置し直す。
- 既に置いてある rules に手を入れている場合は、再配置前に `cp -R .claude/rules /tmp/rules.bak` で退避する。

## 手順 B: install.sh 経由で入れた場合

ハーネスのクローンを最新にしてから、`--update` を対象リポジトリに向けて実行する。

```bash
git -C <harness-repo> pull --ff-only
bash <harness-repo>/install.sh "$PWD" --update
```

- `--update` は `rules/` `hooks/` `commands/` `scripts/` と `VERSION` だけを更新する。
- `CLAUDE.md` と `docs/` (台帳を含む) には触れない。

## 手順 1: 版が上がったことを検証する

```bash
cat VERSION
bash .claude/tests/smoke.sh
```

- `VERSION` が手順 0 で控えた値より新しくなっていること。
- smoke が全 case PASS / exit 0 であること。FAIL が出たら更新を止め、内容を報告する。

版が変わらない場合は、既に最新か、更新コマンドが別のディレクトリに当たっている。
`ls -l .claude/hooks` のタイムスタンプで実際に置き換わったかを確かめる。

## 更新検知について

SessionStart で `[harness] 更新あり vX → vY (/update で適用)` が出た時だけ実行すればよい。
検知は 24 時間に 1 回・背景通信で、オフラインでも起動を遅らせない。
止めたい場合は `HARNESS_UPDATE_CHECK=off` を環境変数に設定する。

## 判定できる終了条件

- `cat VERSION` が更新前より新しい semver を返す。
- `bash .claude/tests/smoke.sh` が exit 0。
- `git status --short` に `CLAUDE.md` と `docs/` の変更が出ていない。
