# hirai-method-lite

Claude Code 用の軽量ハーネス。**常時ロードされるコンテキストの総量に予算を置き、ルールの追加をパイプライン化する**ことだけを設計の中心に据えている。

前身の `hirai-method` は 1,629 file / shell 54,373 行まで肥大し、guard 36 個中 10 個が「ハーネス自身の開発を妨げるため」という理由で無効化されていた。原因は個々のルールではなく、**ルールを追加するときに置き場所・分量・表現・重複を検討する工程が無かった**ことにある。本リポジトリはその 1 点を構造で解く。

## 導入 4 ステップ

配布は **Claude Code プラグイン** 1 経路のみ。プラグイン名は `hirai-lite`。

1. **マーケットプレイスを追加してインストールする**。

   ```
   /plugin marketplace add thirai-classlab/hirai-method-lite
   /plugin install hirai-lite@hirai-lite
   ```

   commands / hooks はこの時点で有効になる。**rules はまだ配られていない** — プラグインには rules というコンポーネントが無いため。

2. **rules を配置する** — 対象リポジトリを開いて `/hirai-lite:init` を実行する。`rules/*.md` を `.claude/rules/` へ、`templates/settings.json` の permissions を `.claude/settings.json` へ、`templates/mode.yml` を `.claude/mode.yml` へ配置し、台帳と `.claude/rules-archive/` を作る。既存ファイルは上書きしない。

3. **CLAUDE.md を埋める** — このリポジトリの `CLAUDE.md` を雛形として対象リポジトリのルートに置き、`<...>` プレースホルダを実値（概要 / Tech Stack / Commands）に置換する。行動規範は書かない。それは `.claude/rules/core.md` の担当。

4. **ロード検証** — 新しいセッションを開き、T0 の 3 ファイルが載っていること、T1 が `paths:` 該当ファイルを開くまで載らないことを確認する。想定と違えば frontmatter を直す。

更新は `/update`（`/plugin update` → `/hirai-lite:init` で rules を再配置）。

## ultracode について

`/hirai-lite:init` は `templates/settings.json` を配置するため、**導入先で ultracode が既定で有効になる**（`"ultracode": true`）。ultracode は xhigh 推論と、タスクごとの自動 workflow オーケストレーションを常時 on にする設定で、**通常運用よりトークン消費が大きい**。従量課金で使う場合はコスト増を見込むこと。

無効化するときは、導入先の `.claude/settings.json` から `ultracode` キーを削除するか `false` にする。プラグイン側の素材を編集する必要はない。

併せて `"workflowSizeGuideline": "small"` を置き、1 workflow あたりのエージェント数を 5 未満に抑えている。根拠は実測（2026-08-21）。同時 4 subagent を起動した際、3 件が 600 秒無進捗で stall し 1 件が API 接続断となり成果物はゼロだった。同時 2 件へ落としたところ 5 件連続で成功した。並列度を上げるほど stall 率が上がるため、既定は `small` とする。

## このリポジトリの構成

| パス | 中身 |
|---|---|
| `.claude-plugin/plugin.json` | プラグインのマニフェスト（`VERSION` と同じ版を書く） |
| `.claude-plugin/marketplace.json` | 自分自身を 1 エントリとして指すマーケットプレイス定義 |
| `commands/` | スラッシュコマンド 12 個 |
| `hooks/` | `hooks.json` + SessionStart / UserPromptSubmit の 2 本 |
| `rules/` | **プラグインは読まない。** `/init` が導入先の `.claude/rules/` へ配る素材 |
| `scripts/` | hook / statusline が source する共通ライブラリ |
| `templates/` | `settings.json` / `mode.yml` / draft / task の雛形 |
| `tests/smoke.sh` | 自己検証 9 case（予算監査を含む） |

自己テストは `claude --plugin-dir .` でこのリポジトリ自身をプラグインとして読ませて行う。

## rules 3 層 + 退避層

Claude Code は `.claude/rules/*.md` を再帰的に発見する。`paths:` frontmatter を持つファイルは**該当ファイルを読んだ時にだけ**ロードされ、持たないファイルは**起動時に常時**ロードされる（[公式仕様](https://code.claude.com/docs/en/memory.md)）。この挙動をそのまま層設計に使う。

| 層 | 置き場所 | ロード条件 | 予算 | 入れてよいもの |
|---|---|---|---|---|
| **T0 常時** | `CLAUDE.md` / `.claude/rules/*.md`（frontmatter 無し） | 毎セッション | **合計 3,000 tokens** | 全作業に例外なく効く規範のみ。既定では入れない |
| **T1 条件** | `.claude/rules/*.md`（`paths:` あり） | 該当ファイルを触った時 | 1 file 2,000 tokens | ドメイン規範（タスク運用 / コード / インフラ） |
| **T2 参照** | `docs/rules-reference/**` | AI が明示 Read した時のみ | 無制限 | 背景・事故記録・詳細手順・過去の経緯 |
| **T3 退避** | `.claude/rules-archive/**` | ロードしない | — | 失効したルール（履歴として保持） |

T2 を `.claude/rules/` の**外**に置くのは意図的。`rules/` の中に置くと `paths:` を書き忘れた瞬間に T0 へ昇格してしまう。物理配置でこの事故を防いでいる。同じ理由で T0 から T2 へのポインタは張らない（張ると T0 が背景説明で膨らむ）。ポインタは T1 から張る。

`@import` は使わない。CLAUDE.md 展開時に常時展開されるため、context 削減効果がゼロどころか純増になる。

## 設計思想

**1. 既定は「入れない」。** T0 は 3,000 tokens の hard cap を持つ。追加は容易で削除は困難、という非対称を予算で打ち消す。上限に達した後の追加は、既存 1 件を T1/T2 へ降格するまで通らない。

**2. 事故 2 回目で初めてルール化する。** 1 回目は `docs/rules-reference/incidents.md` に 1 行記録するだけ。推測による予防ルールを禁じる。前身のハーネスでは、規範の多くが発火実績ゼロの先回りだった。

**3. 機械強制は不可逆操作のみ。** `settings.json` の `deny` / `ask` と hook で止めてよいのは「間違えたら戻せない」操作だけ。無害な操作を止める guard は速度を削り、やがて無効化されて規範と実挙動の乖離を生む。

**4. メタルールが最初に適用される対象は、メタルール自身。** 「機械強制は不可逆操作のみ」に従えば、予算監査そのものを hook にはできない（予算超過は不可逆ではない）。よって予算チェックと層違反検出は `tests/smoke.sh` の case として実装し、commit 前に走らせる。結果 hook は 2 本に収まる。

**5. ゼロから始めて、必要になったものだけ足す。** 前身の 1,629 file から選び出すのではない。実プロジェクトで使い、不足したものだけを `/add-rule` のパイプライン経由で戻す。何が本当に必要かは、削ってみないと分からない。

## ルールを追加するとき

`rules/_meta.md`（導入先では `.claude/rules/_meta.md`）に 8 条とパイプラインがある。要点だけ:

- 追加はユーザー承認必須。削除は承認不要（削除の摩擦を追加より低くする）
- 1 ルール 1 事象・3 行以内。書式は `- **<名前>**: <肯定形 1 行> ／ 例: <1 つ> ／ 失効: <条件>`
- 禁止語彙: `適切に` / `必要に応じて` / `可能な限り` / `十分に` / `慎重に`
- 四半期ごとに点検し、発火 0 のルールは `.claude/rules-archive/` へ退避する（`/rules-audit`）
