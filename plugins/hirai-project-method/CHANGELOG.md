# 変更履歴

版の付け方は [semver](https://semver.org/lang/ja/)。`VERSION` と `.claude-plugin/plugin.json` の `version` は常に同じ値を持ち、`tests/smoke.sh` が一致を検証する。tag は `hirai-project-method--v<版>`。

## v1.1.0
見回り（`hirai-task today`）の直し 3 つと、`bug` の定義 1 行（土台 3.1.0 の `/hirai-lite:new-task`）。**見回りが書くものが 1 種増える**（align・close-parents に、閉じたのに完了でない task への Status=完了 が加わる）。

- **閉じたのに完了でない → 完了を書く**: `today` は、閉じているのに Status が 完了 でない task（種別が task か空）へ Status=完了 だけを書き、「閉じたのに完了でない N 件を完了にした: #a・#b」と 1 行で出す。閉じた理由が not planned でも同じ（`done --not-planned` が書く Status も 完了）。1 件書けなくても理由を 1 行出してほかを続け（403・429 の rate limit なら残りを打ち切り、その旨を 1 行出す）、書けない行は stuck に残る（別の repo の行は repo 名を添える）。align・close-parents と同じ許可（切り替え・open の issue の「- today は書かない: はい」）に従い、journal に `close-sync` で 1 件ずつ残す。書く前に「N 件のうち 5 件を完了にする: #a・…」と 1 行出し（時間切れで止められても何を書いていたかが残る）、item id と選択肢 id を先に引き、そのあとで issue の state を REST で読み直して開き直された行・state が読めない行は飛ばし、読み直した直後に item_id を渡して書く。対象はこの repo の行だけで、書けた数の上限は 5・試す数の上限は 15（失敗・飛ばしは書けた枠に数えない。試さなかった分は「残り N 件は次の today」）。journal が書けないときも警告 1 行で続け、`today | head` で出力先が閉じても stdout を捨てて続ける。today に `--json`・`--dry-run` などの引数は無く、付けると exit 2。書いた行は、取り直した板でも state が CLOSED の行だけ 完了 として以降の段が見る。板の読みは増えない（書いた回は、書き込みの owner の種類の問い合わせ 1 回と、終了時の件数の控えの取り直し（GraphQL 最大 2 回）が増える）。
- **種別なしに直すコマンド**: orphans の「種別なし」の行の次に `直す: hirai-task set <n> 種別 task（feature・wave・設計メモならその値）` を出す（別 repo の行には出さない）。`set`・`start` は、相手の種別が空なら stderr に同じ直し方つきの警告 1 行（止めない・exit code は変えない。種別自身の `set` は警告しない）。
- **no-issue の merge**: 直近 7 日に `no-issue` ラベルで merge された PR を「no-issue の merge（7 日）N 件: #a・#b」の 1 行で出す（0 件なら出さない。ただし 100 件で見切れているときは 0 件でも「0 件」と出す）。既定の branch 向けの PR だけを数える（設計の PR も入る）。merged-designs が読む closed の PR 100 件を共有し、API は増えない。100 件で 7 日に届かないときは「（7 日・直近の closed PR 100 件まで）」と添える。ラベル名は `NO_ISSUE_LABEL` の 1 か所。
- **merged-designs**: 本文の印 `pr-template-design-v1` に加え、「種別: 設計・決定の文書」の行（土台 3.1.0 の PR の雛形）でも設計の PR を見分ける。
- **検査**: `hirai_task_selftest.py` に、完了を書く・書けない 1 件＋書ける 1 件・許可なし・0 件と feature・not planned と同じ値・書く直前の読み直しが 404・403・state なし・null・open のとき・検索の間の reopen・rate limit での打ち切り・失敗が枠を食わない・出力先が閉じたとき・journal の失敗・種別なしの直し・set と start の警告・no-issue の 0 件／3 件／6 日前／8 日前／境目／100 件で切れる・closed の PR を 1 回だけ読む、などを足した。偽の板の行は url を持ち、別 repo の同じ番号・書く間に開き直される場合・journal・8.5 秒おき・書く順・GraphQL の回数・today の引数も見る（実装を 1 か所ずつ壊した写しで落ちることを確かめた）。

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
