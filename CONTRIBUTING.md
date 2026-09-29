# 開発の進め方

## 配布は系列ブランチから。main はカタログ

**1.x は `v1` ブランチ、2.x は `v2` ブランチ（別の entry 名）から配ります。`main` は
カタログ（マーケットプレイス定義）を持つだけで、プラグイン本体として `install` される
経路には乗りません。**

マーケットプレイス定義（`.claude-plugin/marketplace.json`）は `main` に置きますが、
`hirai-lite` entry の `source` は `{"source": "github", "repo": "thirai-classlab/hirai-method-lite",
"ref": "v1"}` に固定してあります（`ref` は github source のキーで、ブランチかタグを指します。
既定は既定ブランチ。[marketplace reference](https://code.claude.com/docs/en/plugins/marketplace-reference)）。
利用者が `/plugin marketplace update hirai-lite` →
`/plugin update hirai-lite@hirai-lite` を実行すると、カタログ自体は `main`（既定ブランチ）から
取り直しますが、**受け取るプラグイン本体は `v1` ブランチの内容**です。2.x は、別の entry 名
で `v2` ブランチを指す形で足します（同じ entry 名を 2 つ持つと
`claude plugin validate` が `Duplicate plugin name` で落ちるため、entry 名は系列ごとに分けます）。

**例外として、`main` の作業ツリーそのものが利用者の手元に置かれる経路が 1 つだけあります。**
マーケットプレイスを一度でも取り込むと、`main` の clone が `~/.claude/plugins/marketplaces/hirai-lite`
に置かれます。1.x の素材行と `scripts/update-check.sh` は、通常はキャッシュ済みのプラグイン本体
（`CLAUDE_PLUGIN_ROOT` や `installed_plugins.json` の解決先）を読みますが、そのキャッシュが
見つからないときの最後の fallback として、この `main` の clone を読みます。そのため
`main` の中身（`commands/` や `rules/` などプラグイン本体の部分）は `v1` と揃えたまま保ち、
2.x のコードは入れません。

`main` の `VERSION` / `.claude-plugin/plugin.json` / `.claude-plugin/marketplace.json` は、
**1.x の最新値に揃えたまま**にします（2.x の版では上げません）。**1.16.0 以前に導入した
案件は、`v1` ブランチの存在を知らず、更新の合図として `main` の `VERSION` を読み続けます**
（`scripts/update-check.sh` の既定 URL が `main` を向いていた版のため）。`main` の `VERSION` を
2.x に上げると、それらの案件に「更新あり」が出続けます。カタログを持つ `main` 自身も
`tests/smoke.sh` の case 9（3 か所の版の一致）を満たす必要があるため、1.x への変更は
**`v1` と `main` の両方に同じ diff を入れます**（`git cherry-pick` で足ります。衝突した
ときの扱いは下の手順 4 を見てください）。

タグ（`v1.1.0` など）は履歴の目印であって、配布の単位ではありません。
**タグを打っても、利用者に届くものは変わりません。**

そのため次を守ります。

- **配布ブランチ（`v1` / `v2`）には、リリースしてよい状態だけを置く。** 途中の状態・動作未確認の変更を push しない。
- 作業は作業用ブランチで行い、まとまってから配布ブランチに入れる。
- 配布ブランチに入れる前に、必ず次を通す。
  - `bash tests/smoke.sh` が全項目 PASS で終了する
  - `claude plugin validate .` が PASS する
  - `VERSION` / `.claude-plugin/plugin.json` / `.claude-plugin/marketplace.json` の版が一致している
- 同じ確認を、同じ diff を当てた `main` でも行う。ただし `main` は entry の `source` を
  `v1` に固定しているため、**`claude plugin validate . --strict` はカタログのスキーマしか
  見ません**（プラグイン本体の中身は検証対象に入りません）。`main` ではこれに加えて
  `claude plugin validate .claude-plugin/plugin.json --strict` も実行し、プラグイン本体側の
  スキーマ（`main` に置いたままの `plugin.json` 自体）が壊れていないことを見ます。
  プラグイン本体の**動作**は `v1` 側の `bash tests/smoke.sh` で見ます。
- 版を上げたら、配布ブランチのコミットに注釈付きタグ（`git tag -a v<版>`）を打つ。タグは配布の単位ではないが、
  「どのコミットがどの版か」をあとから追うために残す。

## 版の上げ方（1.x・`v1` ブランチ）

`VERSION` は更新の合図にも使われます（セッション開始時に、`v1` ブランチの `VERSION` と
手元の版を比べて「更新あり」を出す仕組み）。**3 か所を必ず同じ値に揃えます。**

```bash
# 1. v1 ブランチで版を書き換える
git switch v1
V=1.16.2
printf '%s\n' "$V" > VERSION
# .claude-plugin/plugin.json の "version"
# .claude-plugin/marketplace.json の metadata.version と plugins[0].version

# 2. 揃っていることを確かめる (smoke の case 9 が同じ検査をする)
bash tests/smoke.sh
claude plugin validate . --strict

# 3. 1 コミットにまとめる
#    git add -A ではなく、変更したファイルを明示して足す
git status --short
git add VERSION .claude-plugin/plugin.json .claude-plugin/marketplace.json CHANGELOG.md  # + 変更した分
git commit -m "<種別>: <1 行>"

# 4. 同じ diff を main にも入れる
#    v1 の変更が marketplace.json の plugins[0].source の前後の行を触らなければ
#    cherry-pick でそのまま入る。衝突したら source は main 側 (github・ref: v1) を残す
git switch main
git cherry-pick v1
bash tests/smoke.sh
claude plugin validate . --strict
claude plugin validate .claude-plugin/plugin.json --strict

# 5. push は v1 → main の順 (main を先に配ると、まだ v1 に無い版への「更新あり」が出る)
git push origin v1
git push origin main
git tag -a "v$V" -m "v$V" v1
git push origin "v$V"
```

2.x は `v2` ブランチ・entry 名 `hirai-lite-v2` で、`main` のカタログに `ref: v2` の entry として
足してあります。版は同じく 3 か所（`v2` の `VERSION` / `plugin.json` / `marketplace.json` の
`hirai-lite-v2` の行）を揃えます（`tests/smoke.sh` の case 9 が `ref` が自分の branch の entry を
探して見ます）。カタログの `hirai-lite-v2` の行の版は、`v2` を上げたら `main` にも同じ値を入れます。
`main` の `VERSION` はこの手順の対象外のままです。

## いま採っていない選択肢

配布ブランチを分ける方法にはほかの形もあります。どれも運用の手間が増えるため、
いまは「系列ごとに ref で固定したブランチ（`v1` / `v2`）を指し、`main` はカタログのまま」
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
