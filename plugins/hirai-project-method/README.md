# hirai-project-method

[hirai-lite](../../README.md)（土台）に足す、GitHub Project でタスクを回すためのプラグイン。台帳（`docs/tasks/`）で足りるリポは入れない。

## 入れる

```
/plugin install hirai-project-method@hirai-lite
```

土台の hirai-lite（3.0.0 以上）が依存として一緒に入る。そのうえで、導入先の `.claude/mode.yml` に次を書く。形は自動では見分けない。

```yaml
tasks: github-project
```

`tasks: github-project` で `hirai-task` が PATH に無いとき、土台は上の入れ方を示して止まる。

夜間に回す CI の赤を見逃さないときは、同じ `.claude/mode.yml` に `nightly_ci: ci.yml`（workflow のファイル名）を足す。`hirai-task today` の先頭に、その workflow の直近の schedule の run の結果を 1 行出す（成功・失敗と url・実行中・run が無い・取れない。36 時間より古ければ注記）。空か無ければ何も出さず gh も呼ばない。

## 入っているもの

| 部品 | 中身 |
|---|---|
| `bin/hirai-task` | リポに紐づいた GitHub Project のタスクを読み書きする 1 本の道具（ready・start・new・board・card・setup・line ほか）。Claude Code がプラグインの `bin/` を PATH に入れる |
| `commands/board.md` | `/hirai-project-method:board` 全体像と、どこで何件止まっているか |
| `commands/project-setup.md` | `/hirai-project-method:project-setup` Project の作成・紐づけ・項目・ビューの立ち上げ（既定は計画だけ。`--apply` で書く） |
| `skills/github-project/` | GitHub Project の形の規範（正本は Project・3 段・Status 8 値・書き込みはメイン専任・承認カード） |
| `docs/rules-reference/project-setup.md`・`glossary.md` | 立ち上げの手順と、wave・feature・8 状態の用語 |
| `hirai-task today` の `nightly_ci` の 1 行 | `.claude/mode.yml` の `nightly_ci: <workflow のファイル名>` があるときだけ、`gh run list --event schedule -L 1` の結果を先頭に 1 行出す |
| `scripts/ghp-path.sh` | 件数の控え（`~/.claude/plugins/data/hirai-project-method-hirai-lite/`）を読み書きするシェル関数 |

## 土台との約束

- 土台は `hirai-task` を PATH で呼ぶだけで、`harness_ghp_*` を直接呼ばない。
- 会話の開始時（`hirai-task line --refresh`）と画面下（`hirai-task line`）の 1 行は、`tasks: github-project` のときだけ呼ばれる。`line` は控えを読むだけで、GraphQL を打つのは `--refresh` の背景の取り直しと、書き込みの直後だけ。
- 承認カードの型（`approval-template.md`）と draft の雛形は土台にある。`hirai-task --selftest` は土台の場所を `HIRAI_LITE_ROOT`・リポ内の配置・`installed_plugins.json` の順に探す。

## 確かめる

```
bash plugins/hirai-project-method/tests/smoke.sh
```

## 2.x（hirai-lite-v2）から移る

`/hirai-lite:board`・`/hirai-lite:project-setup` は `/hirai-project-method:board`・`/hirai-project-method:project-setup` になる。件数の控えの置き場が変わるので、最初の会話では画面下の件数が出るまで 1 回待つ。移し方の全体は土台の README と CHANGELOG（3.0.0）に書く。
