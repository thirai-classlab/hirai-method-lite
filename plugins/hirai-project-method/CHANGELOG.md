# 変更履歴

版の付け方は [semver](https://semver.org/lang/ja/)。`VERSION` と `.claude-plugin/plugin.json` の `version` は常に同じ値を持ち、`tests/smoke.sh` が一致を検証する。tag は `hirai-project-method--v<版>`。

## v1.0.0
hirai-lite 2.9.0 の GitHub Project の部品を、土台（hirai-lite 3.0.0）から分けて足すプラグインにした。設計: hirai-lite の設計「hirai-lite を土台にし、GitHub Project のタスク管理を hirai-project-method に分ける」（2026-11-23 承認）。

- **移したもの**（`git mv`。履歴は hirai-lite 2.9.0 から続く）: `bin/hirai-task`・`scripts/hirai_board.py`・`hirai_card.py`・`hirai_project_setup.py`・`hirai_task_selftest.py`・`commands/board.md`・`commands/project-setup.md`・`skills/github-project/`・`docs/rules-reference/project-setup.md`・`glossary.md`・土台の `scripts/tasks-path.sh` の GitHub Project の関数（`harness_ghp_*`）。
- **`scripts/ghp-path.sh`**: 上の関数の置き場。土台の関数には依存しない。控えの置き場の id は `hirai-project-method-hirai-lite`（`~/.claude/plugins/data/` の下）。2.x の控え（`hirai-lite-v2-hirai-lite`）は読まない。件数は初回の取り直しで作り直される。
- **`hirai-task line [--refresh]`**（新）: 会話の開始時と画面下に出す「やること」の 1 行（件数の控えを読むだけ）を出す。控えが無い・form が ghp でないときは何も出さず exit 0。`--refresh` を付けると出したあとに背景で取り直す（Project の見分けは 24 時間に 1 回・件数は 2 分に 1 回まで）。付けない呼び出しは gh を打たない。土台の `hooks/session-start.sh`（`--refresh` つき）と `scripts/statusline.sh`（なし）が、`.claude/mode.yml` の `tasks: github-project` のときだけ呼ぶ。
- **呼び名**: `/hirai-project-method:board`・`/hirai-project-method:project-setup`（2.x の `/hirai-lite:board`・`/hirai-lite:project-setup` から変わる）。
- **依存**: `plugin.json` の `dependencies` に `hirai-lite >=3.0.0`。土台が無いと読み込まれない。自己検査（`hirai-task --selftest`）は土台の `docs/rules-reference/approval-template.md` と `templates/draft.md` を読むので、土台の場所を `HIRAI_LITE_ROOT`・リポ内の配置・`installed_plugins.json` の `hirai-lite` の順に探す。
- **検査**: `tests/smoke.sh`（このプラグインだけの確かめ。`hirai-task --selftest`・`line` の出し分け・移した部品の揃い・依存の宣言・控えの id と entry 名の一致）。
