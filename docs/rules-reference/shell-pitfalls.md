# shell の罠

bash で書いたスクリプト (hook / smoke / CI の小片) で実際に踏んだ罠。いずれも「静かに壊れる」種類のもので、エラーメッセージが出ないため発見が遅れる。

---

## 1. `grep -c` は 0 件のとき「0 を出力して exit 1」を返す

**何が起きたか**: 件数を数える定番の書き方が算術展開で syntax error を起こした。

```bash
n=$(grep -c PATTERN file || echo 0)   # 0 件のとき n="0\n0" になる
echo $(( n + 1 ))                      # syntax error
```

**なぜ起きたか**: `grep -c` は「0 件」を stdout に `0` として **出力しつつ**、マッチ無しを示す exit 1 を返す。`|| echo 0` は exit 1 に反応して追加の `0` を出力するため、`grep` 自身の `0` と合わさって 2 行になる。`$(( ))` は改行を含む文字列を数値として解釈できない。

**どう対処するか**: 数字以外を落とす。

```bash
n=$(grep -c PATTERN file | tr -cd '0-9')
```

`|| echo 0` を使うなら `grep -c` の出力を捨てる (`grep -c ... 2>/dev/null` ではなく、出力そのものを分岐させる) こと。混ぜると必ず二重になる。

**教訓の一般形**: exit code と stdout の両方を持つコマンドで、`|| fallback` は **stdout を上書きせず追記する**。fallback を書く前に「失敗時に stdout は空か」を確認する。

**出典**: 本セッション実測 (2026-08-27)。

---

## 2. source されるライブラリの file-top に `set -euo pipefail` を書かない

**何が起きたか**: hook が発火しなくなった。エラーメッセージは一切出ず、単に何も起きない。原因判明まで時間を要した。

**なぜ起きたか**: source されるライブラリの先頭に `set -euo pipefail` を書くと、**呼び出し元の shell の flags が書き換わる**。その状態で呼び出し元が `cmd | head -1` を実行すると:

```
head が先に終了 → cmd に SIGPIPE → pipefail が拾う → errexit が発火 → exit 141 で静かに終了
```

`set -e` による終了は stderr に何も出さないため、「途中で無言で死ぬ」挙動になる。

**どう対処するか**: strict mode を使いたいなら **subshell 関数の中に閉じ込める**。

```bash
# NG: file-top に書く
set -euo pipefail

# OK: subshell 関数 ( ) で局所化する
load_config() (
  set -euo pipefail
  ...
)
```

`{ }` ではなく `( )` であることが要点。`{ }` は同じ shell で実行されるので局所化にならない。

**教訓の一般形**: `set -e` は **呼び出し元に leak する副作用**であり、ライブラリが勝手に設定してよいものではない。エントリポイントのスクリプトだけが決める。

**出典**: 旧ハーネス `.claude/CommonRules.md` の Critical Operational Lessons (2026-05-12 に修正)。旧ハーネスでは hook のライブラリで発生したが、罠そのものは source を使うあらゆる bash に当てはまる。

---

## 3. bash 内の `python3` は shell の alias を経由しない

**何が起きたか**: `python3 -c "import yaml"` によるライブラリ検出が、対話 shell では成功するのに bash スクリプト内では失敗した。

**なぜ起きたか**: 対話 shell では `python3` が alias / shim 経由で目的のバージョン (PyYAML 入り) を指していても、スクリプトの非対話 subprocess では alias が解除され、素の system `python3` (PyYAML 不在) が呼ばれる。

**どう対処するか**: 特定バージョンから順に試すループを書き、最初に条件を満たしたものを使う。

```bash
for py in python3.13 python3.12 python3.11 python3; do
  command -v "$py" >/dev/null 2>&1 || continue
  "$py" -c 'import yaml' 2>/dev/null && { PY="$py"; break; }
done
```

**教訓の一般形**: スクリプトから見えるコマンド解決は、対話 shell から見えるものと **別物**。「手元で動いた」を検証結果として扱わない。

**出典**: 旧ハーネス memory `feedback_python3_pyaml_detection_alias_trap` (2026-05-27)。

---

## 4. `mv` によるファイル配置で実行ビットが落ちる

**何が起きたか**: サブエージェントが `/tmp` にファイルを書いてから最終位置へ `mv` する手順を取った結果、スクリプトの mode が 755 から 644 に落ちた。commit した後に気づいた。

**なぜ起きたか**: 新規に Write されたファイルは 644 で作られる。`mv` は mode を保持するので、`/tmp` 側の 644 がそのまま最終位置に来る。既存ファイルを上書きした場合も、置換なので元の 755 は残らない。

**どう対処するか**: 配置後に `git diff --stat` で mode change (`old mode 100755 → new mode 100644`) を確認し、`chmod +x` で戻して amend する。実行されるファイルを扱う手順には chmod を必ず含める。

**教訓の一般形**: ファイルの内容だけを検証して mode を検証しない検査は、実行可能ファイルに対して不十分。

**出典**: 旧ハーネス memory `feedback_subagent_staging_mv_exec_bit_loss` (2026-06-01)。

---

## 関連

- サブエージェント経由でのファイル配置全般: [`subagent-operations.md`](subagent-operations.md)
- 事故の一覧台帳: [`incidents.md`](incidents.md)
