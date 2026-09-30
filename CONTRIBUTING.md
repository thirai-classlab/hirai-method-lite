# 開発の進め方

## 配布は系列ごと。1.x は main、2.x は v2 ブランチ

**1.x は `main`（entry 名 `hirai-lite`・`source: "./"`）から、2.x は `v2` ブランチ（entry 名
`hirai-lite-v2`・`ref: v2`）から配ります。**

マーケットプレイス定義（`.claude-plugin/marketplace.json`）は `main` に置きます。`hirai-lite` entry の
`source` は `"./"` のままで、利用者が `/plugin marketplace update hirai-lite` →
`/plugin update hirai-lite@hirai-lite` を実行すると受け取るのは **その時点の `main`** です。
2.x は、別の entry 名で `v2` ブランチを指す形で足します（`ref` は github source のキーで、ブランチか
タグを指します。[marketplace reference](https://code.claude.com/docs/en/plugins/marketplace-reference)。
同じ entry 名を 2 つ持つと `claude plugin validate` が `Duplicate plugin name` で落ちるため、
entry 名は系列ごとに分けます）。

**1.x を `main` から配るあいだは、`main` の `VERSION` / `.claude-plugin/plugin.json` /
`.claude-plugin/marketplace.json` の `hirai-lite` の版を 2.x の値に上げません。** 1.x の案件は更新の
合図として `main` の `VERSION` を読み、`main` の変更をそのまま受け取るため、上げると 2.x が
自動更新で 1.x の全案件に届きます。2.x の版は `v2` の `VERSION` と、カタログの `hirai-lite-v2` の行だけを動かします。

タグ（`v1.1.0` など）は履歴の目印であって、配布の単位ではありません。
**タグを打っても、利用者に届くものは変わりません。**

そのため次を守ります。

- **配布ブランチ（`main` / `v2`）には、リリースしてよい状態だけを置く。** 途中の状態・動作未確認の変更を push しない。
- 作業は作業用ブランチで行い、まとまってから配布ブランチに入れる。
- 配布ブランチに入れる前に、必ず次を通す。
  - `bash tests/smoke.sh` が全項目 PASS で終了する
  - `claude plugin validate . --strict` と `claude plugin validate .claude-plugin/plugin.json --strict` が PASS する
  - `VERSION` / `.claude-plugin/plugin.json` / `.claude-plugin/marketplace.json` の（その系列の）版が一致している
- 版を上げたら、配布ブランチのコミットに注釈付きタグ（`git tag -a v<版>`）を打つ。タグは配布の単位ではないが、
  「どのコミットがどの版か」をあとから追うために残す。

## 版の上げ方

`VERSION` は更新の合図にも使われます（セッション開始時に、配布元の `VERSION` と手元の版を比べて
「更新あり」を出す仕組み）。**3 か所を必ず同じ値に揃えます。** `tests/smoke.sh` の case 9 が同じ検査をします。

- **1.x（`main`）:** `main` の `VERSION` / `plugin.json` / `marketplace.json` の `metadata.version` と
  `hirai-lite` の行（`plugins[0]`）を揃えて上げ、`main` に入れます。
- **2.x（`v2`）:** `v2` の `VERSION` / `plugin.json` / `marketplace.json` の `hirai-lite-v2` の行
  （`ref` が自分の branch の entry）を揃えて上げます。カタログ（`main`）の `hirai-lite-v2` の行の版も
  同じ値にします（`main` の case 9 が、`v2` が手元に在るときに見ます）。`main` の `VERSION` は上げません。
- `v2` の `marketplace.json` は、配られない写しです。`hirai-lite` の行は、`plugin.json` が 2.0.0 の `v2` 上で
  `validate --strict` が「版が違う」と落ちないよう `ref: main`（1.16.0）の github source にしてあります。
  実際に配られるカタログは `main` の方で、そちらは `source: "./"` です。
- **push は `v2` → `main` の順。** カタログ（`main`）を先に配ると、まだ `v2` に無い版を指す entry が
  利用者に見えます。

## いま採っていない選択肢

配布ブランチを分ける方法にはほかの形もあります。どれも運用の手間が増えるため、
いまは「1.x は `main`、2.x は `ref` で固定した `v2` ブランチから別の entry 名で配る」
という形で対応しています。将来まとまった変更を継続的に扱うようになったら、改めて選び直します。

**なお、いまの形（ref でブランチを固定する）でも、配る版を明示的に指定することはできます。**
下の比較は、それでも解決しない代償（運用の手間）についてのものです。

| 選択肢 | やり方 | 得られるもの | 代償 |
|---|---|---|---|
| 既定ブランチ自体を切り替える | 既定ブランチを `release` にし、`main` は開発用にする | カタログと配布物が同じブランチに戻る | 既定ブランチの切り替えが要り、リポジトリの見た目が変わる |
| マーケットプレイスを別リポジトリにする | `marketplace.json` だけ別リポジトリに置き、`source` でコミットを指す | 版を明示的に指定して配れる | リポジトリが 2 つになり、版上げが 2 手になる |
| 開発をフォークで行う | 本体には完成品だけを入れる | 本体の履歴が常にきれい | 個人開発では手間に見合わない |

## 触らないもの

- `rules/` は利用者が `/add-rule` で育てる資産の**素材**です。予算（常時読まれる分の合計は 6,000 tokens で警告 / 10,000 tokens が上限）
  に直結するため、増やすときは `tests/smoke.sh` の case 4・5 が通ることを必ず確かめます。
- 数の上限（常時読まれるルール 3 本 / 自動処理 5 本 / コマンド 12 個 / 自己検証 10 項目）は
  `tests/smoke.sh` の case 6 が守っています。上限に達している枠に足すときは、
  先に何を減らすかを決めます。
