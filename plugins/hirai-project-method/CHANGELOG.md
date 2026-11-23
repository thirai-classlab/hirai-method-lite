# 変更履歴

版の付け方は [semver](https://semver.org/lang/ja/)。`VERSION` と `.claude-plugin/plugin.json` の `version` は常に同じ値を持ち、`tests/smoke.sh` が一致を検証する。tag は `hirai-project-method--v<版>`。

## v1.0.0
hirai-lite 2.9.0 の GitHub Project の部品を、土台（hirai-lite 3.0.0）から分けて足すプラグインにした。設計: hirai-lite の設計「hirai-lite を土台にし、GitHub Project のタスク管理を hirai-project-method に分ける」（2026-11-23 承認）。

- **移したもの**（`git mv`。履歴は hirai-lite 2.9.0 から続く）: `bin/hirai-task`・`scripts/hirai_board.py`・`hirai_card.py`・`hirai_project_setup.py`・`hirai_task_selftest.py`・`commands/board.md`・`commands/project-setup.md`・`skills/github-project/`・`docs/rules-reference/project-setup.md`・`glossary.md`・土台の `scripts/tasks-path.sh` の GitHub Project の関数（`harness_ghp_*`）。
- **`scripts/ghp-path.sh`**: 上の関数の置き場。土台の関数には依存しない。控えの置き場の id は `hirai-project-method-hirai-lite`（`~/.claude/plugins/data/` の下）。2.x の控え（`hirai-lite-v2-hirai-lite`）は読まない。件数は初回の取り直しで作り直される。
- **`hirai-task line [--refresh]`**（新）: 会話の開始時と画面下に出す「やること」の 1 行（件数の控えを読むだけ）を出す。控えが無い・form が ghp でないときは何も出さず exit 0。`--refresh` を付けると出したあとに背景で取り直す（Project の見分けは 24 時間に 1 回・件数は 2 分に 1 回まで）。付けない呼び出しは gh を打たない。土台の `hooks/session-start.sh`（`--refresh` つき）と `scripts/statusline.sh`（なし）が、`.claude/mode.yml` の `tasks: github-project` のときだけ呼ぶ。
- **`hirai-task today` の前夜の CI の 1 行**（新）: `.claude/mode.yml` の `nightly_ci: <workflow のファイル名>` があるとき、`today` の先頭に直近の schedule の run の結果を 1 行出す（`前夜の CI（ci.yml・11-24 03:17）: 成功`。失敗は url つき・実行中・run が無い・取れない（理由）は別の文。時刻は JST。36 時間より古ければ注記）。値は足すプラグインの中の読み方（土台の `harness_yml_value` と同じ規則: プロジェクト → ホーム・引用符と行末の注を外す）で読み、空か無ければ何も出さず gh も呼ばない。
- **`hirai-task after-merge` の末尾の 1 行**（新）: 土台の `hirai-worktrees list` で消してよい worktree が 1 本以上あるとき「消してよい worktree: N 本（うち退避が要る M 本。`hirai-worktrees list` で見る）」を出す（0 本なら出さない）。
- **呼び名**: `/hirai-project-method:board`・`/hirai-project-method:project-setup`（2.x の `/hirai-lite:board`・`/hirai-lite:project-setup` から変わる）。
- **依存**: `plugin.json` の `dependencies` に `hirai-lite >=3.0.0`。土台が無いと読み込まれない。自己検査（`hirai-task --selftest`）は土台の `docs/rules-reference/approval-template.md` と `templates/draft.md` を読むので、土台の場所を `HIRAI_LITE_ROOT`・リポ内の配置・`installed_plugins.json` の `hirai-lite` の順に探す。
- **入れる前に**: 1.x が入っている範囲では先に `/plugin marketplace update hirai-lite` → 端末で `claude plugin update hirai-lite@hirai-lite --scope <入れた範囲>`（画面なら `/plugin` → Installed → Update now）。2.x が入っている範囲では、土台の移り方の順（disable まで）を先に行う。install・disable・uninstall は、このリポの行（`git rev-parse --git-common-dir` が同じ行）の `projectPath` と同じ場所（本体の checkout）で打つ（user の範囲ならどこでもよい。端末なら `--scope <v2 の範囲>`）。
- **検査**: `tests/smoke.sh`（このプラグインだけの確かめ。`hirai-task --selftest`・`line` の出し分け・移した部品の揃い・依存の宣言・控えの id と entry 名の一致）。
