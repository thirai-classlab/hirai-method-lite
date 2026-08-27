---
description: 進め方を「確認あり (normal)」と「自動 (loop)」で切替える。設定ファイルはすでに在る側 (プロジェクト / 全プロジェクト共通) を書き換え、いまの進め方を 1 行で報告する。
---

# /mode [normal|loop]

進め方は 2 つだけ。**確認あり (`normal`)** は重要な分かれ道でひとこと聞いてから進む。**自動 (`loop`)** は確認を求めず最後まで進む。

このコマンドの出力は 1〜2 行に収める。前置きと理由の説明を付けない。

## 設定ファイルの場所を決め打ちしない

進め方の設定は、このプロジェクト (`.claude/mode.yml`) と全プロジェクト共通 (`~/.claude/mode.yml`) の
2 通りに置ける (`/init` に `user` を付けたかで決まる)。**どちらに置いたかを決め打ちしない。**
読む順も書き込み先も、セッション冒頭の表示・画面下部の表示と同じ共通ライブラリに任せる。

```bash
. "$CLAUDE_PLUGIN_ROOT/scripts/tasks-path.sh"
harness_mode "$PWD"                 # いまの進め方 (env HC_MODE > プロジェクト > 共通 > normal)
harness_mode_write_file "$PWD"      # 書き込み先 (すでに在る側。両方に無ければプロジェクト側)
```

書き込み先を自分で組み立てない。全プロジェクト共通に置いている人のプロジェクトへ `.claude/mode.yml`
を新しく作ると、共通側の設定を黙って覆い隠す (画面の表示と実際の進め方が食い違う原因になる)。

## 引数なし

いまの進め方を読んで報告するだけで、ファイルは書き換えない。

```bash
. "$CLAUDE_PLUGIN_ROOT/scripts/tasks-path.sh"; harness_mode "$PWD"; echo
```

報告書式 (`normal` のとき): `いまは「確認あり」。重要な分かれ道でひとこと確認してから進みます。確認なしで進めるなら /mode loop`
報告書式 (`loop` のとき): `いまは「自動」。確認を求めず最後まで進みます。止めたいときは「stop」。確認しながらに戻すなら /mode normal`

## /mode normal

すでに在る側の `mode.yml` を `mode: normal` の 1 行で上書きする。

```bash
. "$CLAUDE_PLUGIN_ROOT/scripts/tasks-path.sh"
f="$(harness_mode_write_file "$PWD")"; mkdir -p "$(dirname "$f")"
printf 'mode: normal\n' > "$f" && echo "wrote $f"
```

報告書式: `「確認あり」にしました。重要な分かれ道でひとこと確認してから進みます`

## /mode loop

すでに在る側の `mode.yml` を `mode: loop` の 1 行で上書きする。

```bash
. "$CLAUDE_PLUGIN_ROOT/scripts/tasks-path.sh"
f="$(harness_mode_write_file "$PWD")"; mkdir -p "$(dirname "$f")"
printf 'mode: loop\n' > "$f" && echo "wrote $f"
```

報告書式: `「自動」にしました。確認を求めず最後まで進みます。止めたいときは「stop」と伝えてください`

書き込み先が全プロジェクト共通 (`~/.claude/mode.yml`) だった場合だけ、報告に 1 行足す:
`この設定はすべてのプロジェクトに効きます`

## 「自動」のときの振る舞い

`mode: loop` の間、メインは次のように振る舞う。

- 作り方の選び方・branch 名・commit の件名・ビルドが通るまでの試行錯誤は、聞かずに決めて進める。
- 次の 3 つは自動のときでも必ず確認を取る。
  - 新しい設計メモを足すとき (`docs/draft/` への新規 Write)
  - 一度決めた内容から外れる作り方に変えるとき
  - 元に戻せない操作 (`main` への push / PR の取り込み / 本番反映 / DB の作り替え / 秘密情報の操作)
- サブエージェントに作業を任せたら、終わるのを待つ間に別の作業かタスク一覧の更新を進める。待つだけで止まらない。
- 会話の使用量が 80% に達したら `/state save` を実行し、新しいセッションでの再開を提案する。

## ファイルが無い場合

どちらにも `mode.yml` が無ければ、`harness_mode_write_file` が返すパス (プロジェクト側) に
`mode: normal` を書き込んでから報告する。

## 判定できる終了条件

```bash
. "$CLAUDE_PLUGIN_ROOT/scripts/tasks-path.sh"
grep -c '^mode: \(normal\|loop\)$' "$(harness_mode_write_file "$PWD")"
```

- 上が 1 を返す。
- 書き換えた後の `harness_mode "$PWD"` が、指定した進め方 (`normal` / `loop`) と一致する。
- 出力が 2 行以内。
