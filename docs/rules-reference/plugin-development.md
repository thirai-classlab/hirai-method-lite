# プラグイン開発の落とし穴

Claude Code プラグイン (`.claude-plugin/plugin.json` + marketplace) を作る際に、実際に踏んだ罠の記録。

出典が「本セッション実測」のものは 2026-08-27 に hirai-lite プラグインを構築した際の観測。それ以外は出典を明記する。

---

## 1. `plugin.json` に `commands` キーを書くと既定フォルダが失われる

**何が起きたか**: `plugin.json` に `"commands": [...]` を書いた結果、`commands/` 配下の既定コマンドが 1 件も登録されなくなった。プラグインは正常にインストールされ、エラーも警告も出ない。

**なぜ起きたか**: 公式仕様 (plugins-reference の Path behavior rules) では、manifest の以下のキーは既定ディレクトリを **置換 (replace)** する。

| キー | 既定ディレクトリへの作用 |
|---|---|
| `commands` | **置換** |
| `agents` | **置換** |
| `workflows` | **置換** |
| `outputStyles` | **置換** |
| `skills` | 追加 (既定 `skills/` は残る) |

`skills` だけが追加で、他は置換。この非対称性が事故の温床になる。

**どう対処するか**: 既定ディレクトリ (`commands/` / `agents/`) をそのまま使うなら、対応するキーを **manifest に書かない**。追加の場所も併用したいなら、既定パスも明示的に列挙する。

**出典**: 本セッション実測 (2026-08-27) + 公式 plugins-reference。

---

## 2. `claude plugin validate` は宣言と実体の乖離を検出しない

**何が起きたか**: 上記 1 の状態 — コマンドが 0 件登録になっている状態 — で `claude plugin validate` は PASS した。

**なぜ起きたか**: `validate` は manifest の **スキーマ的な正しさ** (JSON として妥当か、必須キーがあるか、参照先パスが存在するか) を見る。「宣言した結果として実際に何件のコンポーネントが登録されるか」は見ていない。

**どう対処するか**: 登録件数を突合する。これが唯一の検出手段である。

```
claude --plugin-dir <dir> plugin details <name>
```

出力に並ぶ commands / agents / skills / hooks の件数を、リポジトリ内の実ファイル数と突き合わせる。件数が合わなければ manifest のキーが既定を潰している。

**教訓の一般形**: **「lint が通る」は「宣言と実体が一致する」の証明にならない。** 実体を数えるステップを別に持つ。

**出典**: 本セッション実測 (2026-08-27)。

---

## 3. path 挙動は skill の記述ではなく公式 plugins-reference を優先する

**何が起きたか**: 公式 marketplace の `plugin-dev` プラグインに同梱されている `plugin-structure` skill には、次の記述がある。

> **Important**: Custom paths supplement defaults—they don't replace them. Components in both default directories and custom paths will load.
> **Override behavior**: Custom paths in `plugin.json` supplement (not replace) default directories

一方、公式ドキュメント (plugins-reference の Path behavior rules) では `commands` / `agents` / `workflows` / `outputStyles` は既定ディレクトリを **置換** すると定義されている。実測でも `commands` キーを書いた結果、既定の `commands/` から 1 件も登録されなくなった (項目 1)。両者は記述が異なる。

**なぜ起きたか**: 未確認。記述時点の仕様との差か、`skills` の挙動 (こちらは追加) を他キーへ一般化したものと推測されるが、裏付けは取っていない。

**どう対処するか**: プラグインの path 挙動については、**公式 plugins-reference (Path behavior rules) を一次情報として優先する**。既定ディレクトリをそのまま使うなら、対応するキーを manifest に書かない (項目 1 の回避方法)。

**教訓の一般形**: 記述が食い違うときは、より一次に近い仕様書と自分の実測に戻る。

**出典**: 本セッション実測 (2026-08-27)。該当記述は `plugin-dev` plugin の `skills/plugin-structure/SKILL.md`。

---

## 4. `${CLAUDE_PLUGIN_ROOT}` は settings.json では展開されない

**何が起きたか**: `statusLine` の設定やプロジェクト `settings.json` の中で `${CLAUDE_PLUGIN_ROOT}` を使ったが、変数が展開されずリテラル文字列のまま渡された。

**なぜ起きたか**: `${CLAUDE_PLUGIN_ROOT}` が展開されるのは **プラグインコンポーネント側の文脈** (hook 定義、MCP サーバ定義など) に限られる。`settings.json` はプラグイン外の設定ファイルであり、この変数の展開対象ではない。

**どう対処するか**: settings.json から呼びたいスクリプトは、プラグイン内に置いたまま参照するのではなく、**リポジトリ側に複製して相対パスで呼ぶ**。SSoT が二重化するので、複製であることをファイル冒頭にコメントで書く。

**未確認**: プラグイン側から settings.json を配布する公式経路があるかは調べていない。

**出典**: 本セッション実測 (2026-08-27)。

---

## 5. プラグインは自動更新されない

**何が起きたか**: marketplace 側のプラグインを更新しても、インストール済みの環境には反映されなかった。

**なぜ起きたか**: Claude Code の更新検知は **通知するだけ**で、適用は行わない。適用は手動の 2 手順を要する。

```
/plugin marketplace update    # marketplace のメタデータを取り直す
/plugin update                # インストール済みプラグインを更新する
```

**どう対処するか**: プラグインを配布側として直したら、利用側に「上の 2 コマンドを叩く必要がある」ことを明示的に伝える。直したことと届いたことは別。

**出典**: 本セッション実測 (2026-08-27)。

---

## 6. 更新検知の 24 時間キャッシュ — 通知が無いことは最新である証明にならない

**何が起きたか**: 新版を publish した直後に更新確認をしても、通知が出ないことがある。

**なぜ起きたか**: 更新検知には 24 時間のキャッシュがある。キャッシュ取得のタイミングが新版の publish 直前だった場合、**最大 24 時間**は新版の存在に気づけない。

**どう対処するか**: 「通知が出ていない = 最新」と判断しない。バージョンを確かめたいときは `/plugin marketplace update` を明示的に叩いてキャッシュを更新してから見る。

**教訓の一般形**: キャッシュ付きの検知機構において、**シグナルの不在は否定の証拠ではない**。確認したいなら能動的に取り直す。

**出典**: 本セッション実測 (2026-08-27)。

---

## 7. scope 決め打ちは同一クラスの欠陥を複数箇所に残す

**何が起きたか**: `/update` コマンドの中でパス解決の欠陥を 1 箇所修正した。しかし同じクラスの欠陥が、`mode.yml` の解決 (3 箇所) と `/add-rule` / `/rules-audit` にそのまま残っていた。

**なぜ起きたか**: 「報告された 1 箇所を直す」という scope の決め打ち。欠陥のクラス (この場合は「パス解決の前提が環境によって崩れる」) で横断検索していなかった。

**どう対処するか**: 欠陥を 1 件直したら、**修正前に、その欠陥のクラスをキーワード化して全体を grep する**。1 箇所の修正で閉じてよいのは、grep して他に該当が無いことを確認したときだけ。

**教訓の一般形**: バグ報告の scope は「発見された場所」であって「存在する場所」ではない。同一パターンの横展開検索を修正とセットにする。

**出典**: 本セッション実測 (2026-08-27)。

---

## 関連

- shell 由来の罠: [`shell-pitfalls.md`](shell-pitfalls.md)
- 事故の一覧台帳: [`incidents.md`](incidents.md)
