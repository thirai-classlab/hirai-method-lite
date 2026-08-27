# 開発の進め方

## main は常に配布物

**このリポジトリの `main` は、そのまま利用者に配られます。**

マーケットプレイス定義（`.claude-plugin/marketplace.json`）の `source` は `"./"`、つまり
このリポジトリの既定ブランチ（`main`）を指しています。利用者が
`/plugin marketplace update hirai-lite` → `/plugin update hirai-lite@hirai-lite` を実行すると、
受け取るのは **その時点の `main` の最新コミット**です。

タグ（`v1.1.0` など）は履歴の目印であって、配布の単位ではありません。
**タグを打っても、利用者に届くものは変わりません。**

そのため次を守ります。

- **`main` には、リリースしてよい状態だけを置く。** 途中の状態・動作未確認の変更を `main` に push しない。
- 作業は作業用ブランチで行い、まとまってから `main` に入れる。
- `main` に入れる前に、必ず次を通す。
  - `bash tests/smoke.sh` が全項目 PASS で終了する
  - `claude plugin validate .` が PASS する
  - `VERSION` / `.claude-plugin/plugin.json` / `.claude-plugin/marketplace.json` の版が一致している
- 版を上げたら注釈付きタグ（`git tag -a v<版>`）を打つ。タグは配布の単位ではないが、
  「どのコミットがどの版か」をあとから追うために残す。

## 版の上げ方

`VERSION` は更新の合図にも使われます（セッション開始時に、公開されている `VERSION` と
手元の版を比べて「更新あり」を出す仕組み）。**3 か所を必ず同じ値に揃えます。**

```bash
# 1. 版を書き換える
V=1.2.0
printf '%s\n' "$V" > VERSION
# .claude-plugin/plugin.json の "version"
# .claude-plugin/marketplace.json の metadata.version と plugins[0].version

# 2. 揃っていることを確かめる (smoke の case 9 が同じ検査をする)
bash tests/smoke.sh

# 3. 1 コミットにまとめてから main へ
#    git add -A ではなく、変更したファイルを明示して足す
#    (main は配布物なので、意図しない変更を巻き込むと即座に利用者へ届く)
git status --short
git add VERSION .claude-plugin/plugin.json .claude-plugin/marketplace.json CHANGELOG.md  # + 変更した分
git commit -m "<種別>: <1 行>"
git push origin main
git tag -a "v$V" -m "v$V"
git push origin "v$V"
```

## いま採っていない選択肢

配布ブランチを `main` から分ける方法もあります。どれも運用の手間が増えるため、
いまは採らず、「`main` は常に配布物」という規律で対応しています。
将来まとまった変更を継続的に扱うようになったら、改めて選び直します。

| 選択肢 | やり方 | 得られるもの | 代償 |
|---|---|---|---|
| 配布用ブランチを分ける | 既定ブランチを `release` にし、`main` は開発用にする | 開発中の状態が配布されない | ブランチ間の同期作業が常時発生する |
| マーケットプレイスを別リポジトリにする | `marketplace.json` だけ別リポジトリに置き、`source` でコミットを指す | 版を明示的に指定して配れる | リポジトリが 2 つになり、版上げが 2 手になる |
| 開発をフォークで行う | 本体には完成品だけを入れる | 本体の履歴が常にきれい | 個人開発では手間に見合わない |

## 触らないもの

- `rules/` は利用者が `/add-rule` で育てる資産の**素材**です。予算（常時読まれる分の合計は 6,000 tokens で警告 / 10,000 tokens が上限）
  に直結するため、増やすときは `tests/smoke.sh` の case 4・5 が通ることを必ず確かめます。
- 数の上限（常時読まれるルール 3 本 / 自動処理 5 本 / コマンド 12 個 / 自己検証 10 項目）は
  `tests/smoke.sh` の case 6 が守っています。上限に達している枠に足すときは、
  先に何を減らすかを決めます。
