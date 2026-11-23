# 開発の進め方

## 配布は main 1 本（3.0.0 から）

**`main` から、土台 `hirai-lite` と足すプラグイン `hirai-project-method` の 2 つを配ります。** マーケットプレイス定義
（`.claude-plugin/marketplace.json`）は `main` に置き、3 行を持ちます。

| entry | source | 版 |
|---|---|---|
| `hirai-lite`（土台） | `"./"`（リポの root） | `VERSION`・`.claude-plugin/plugin.json` と同じ |
| `hirai-project-method`（足すプラグイン） | `./plugins/hirai-project-method` | `plugins/hirai-project-method/VERSION`・その `.claude-plugin/plugin.json` と同じ |
| `hirai-lite-v2`（退役） | url（https）・`ref: v2` | 2.9.0 のまま動かさない。description は「退役。hirai-lite 3.0.0 と hirai-project-method へ移る」 |

利用者が `/plugin marketplace update hirai-lite` → 端末で `claude plugin update hirai-lite@hirai-lite --scope <入れた範囲>`（画面なら `/plugin` → Installed → Update now） を実行すると受け取るのは
**その時点の `main`** です。2.x（`v2` ブランチ）は凍結し、新しい版を出しません（entry 名を残すのは、2.x の利用者に
退役の案内を出すためです。同じ entry 名を 2 つ持つと `claude plugin validate` が `Duplicate plugin name` で落ちるので、
entry 名は系列ごとに分けてあります）。

相対 path の source（`./plugins/…`）は、カタログを github・git・file・directory で追加したときに使えます（url で追加
したときは使えません。[marketplace reference](https://code.claude.com/docs/en/plugins/marketplace-reference)）。
土台と足すプラグインの間の約束（`installed_plugins.json` から引いた絶対 path で `hirai-task` を呼ぶ・`mode.yml` の項目）を変えるときは、**1 本の PR で両方を直します**
（同じリポジトリに置いている理由です）。

タグは版ごとに付けます。土台は `hirai-lite--v<版>`、足すプラグインは `hirai-project-method--v<版>`（公式の依存の仕組みが、
相対 path のプラグインの版を `<plugin-name>--v<version>` の tag で見るため。[dependencies](https://code.claude.com/docs/en/plugins/dependencies)）。
足すプラグインを入れた人には、依存の範囲に合う最大の tag の版の土台が届きます（[依存の解き方](https://code.claude.com/docs/en/plugins/dependencies.md)）。**版ごとに必ず tag を打ちます**（打ち忘れると、足すプラグインを入れた人の土台が古い tag の版に留まりえます。tag が 1 本も無いうちは `main` の中身が入ります — 2026-11-23 に手元の git source で、tag の有無で差が無いことを実測。github のカタログでは未実施）。土台だけを入れた人に届くのは `main` の中身です。

そのため次を守ります。

- **`main` には、リリースしてよい状態だけを置く。** 途中の状態・動作未確認の変更を push しない。
- 作業は作業用ブランチで行い、まとまってから `main` に入れる。
- `main` に入れる前に、必ず次を通す。
  - `bash tests/smoke.sh` と `bash plugins/hirai-project-method/tests/smoke.sh` が全項目 PASS で終了する
  - `claude plugin validate . --strict` と `claude plugin validate plugins/hirai-project-method --strict` が PASS する
  - 下の「版の上げ方」の版が一致している
- 版を上げたら、`main` のコミットに注釈付きタグ（`git tag -a hirai-lite--v<版>` など）を打つ。「どのコミットがどの版か」を
  あとから追うために残す。

## 版の上げ方

`VERSION` は更新の合図にも使われます（セッション開始時に、配布元の `VERSION` と手元の版を比べて
「更新あり」を出す仕組み。比べるのは土台の `VERSION` と、入っていれば足すプラグインの `plugins/hirai-project-method/VERSION` です。足すプラグインの `VERSION` を上げ忘れると、足すプラグインの更新の合図が出ません）。**それぞれ 3 か所を必ず同じ値に揃えます。**
`tests/smoke.sh` の case 9 が同じ検査をします。

- **土台（`hirai-lite`）:** `VERSION` / `.claude-plugin/plugin.json` / `marketplace.json` の `hirai-lite` の行。
  `marketplace.json` の `metadata.version` も合わせる。
- **足すプラグイン（`hirai-project-method`）:** `plugins/hirai-project-method/VERSION` / その
  `.claude-plugin/plugin.json` / `marketplace.json` の `hirai-project-method` の行。依存（`dependencies` の
  `hirai-lite` の版の範囲）は、土台の約束が変わったときだけ上げる。
- `hirai-lite-v2` の行は動かさない。

## いま採っていない選択肢

配布の形にはほかの形もあります。どれも運用の手間が増えるため、いまは「`main` 1 本から、土台と足すプラグインを
同じリポジトリの `plugins/` の下で配る」形にしています。将来まとまった変更を継続的に扱うようになったら、改めて選び直します。

下の比較は、いまの形で解決しない代償（運用の手間）についてのものです。

| 選択肢 | やり方 | 得られるもの | 代償 |
|---|---|---|---|
| 足すプラグインを別のリポジトリにする | 足すプラグインを別のリポジトリへ置き、カタログから github の source で指す | 版と公開を別々に回せる | 土台との約束（`hirai-task` を呼ぶ口・`mode.yml` の項目）を変えるたびに 2 つのリポジトリで PR を出し、間の版の組み合わせを確かめる手間が要る |
| 既定ブランチ自体を切り替える | 既定ブランチを `release` にし、`main` は開発用にする | カタログと配布物が同じブランチに戻る | 既定ブランチの切り替えが要り、リポジトリの見た目が変わる |
| マーケットプレイスを別リポジトリにする | `marketplace.json` だけ別リポジトリに置き、`source` でコミットを指す | 版を明示的に指定して配れる | リポジトリが 2 つになり、版上げが 2 手になる |
| 開発をフォークで行う | 本体には完成品だけを入れる | 本体の履歴が常にきれい | 個人開発では手間に見合わない |

## 触らないもの

- `rules/` は利用者が `/add-rule` で育てる資産の**素材**です。予算（常時読まれる分の合計は 6,000 tokens で警告 / 10,000 tokens が上限）
  に直結するため、増やすときは `tests/smoke.sh` の case 4・5 が通ることを必ず確かめます。
- 数の上限（常時読まれるルール 3 本 / 自動処理 5 本 / skill 3 個 / 自己検証 10 項目。足すプラグインは command 2・skill 1）は
  `tests/smoke.sh` の case 6 が守っています。上限に達している枠に足すときは、
  先に何を減らすかを決めます。
