---
description: commit 前に build / test / lint を通す。3 つ全部が exit 0 になるまで commit しない。
---

# /verify

## 実行するコマンドの決め方

リポジトリ直下のファイルを見て、この順で最初に一致した 1 組を使う。

| 判定 | build | test | lint |
|---|---|---|---|
| `package.json` がある | `npm run build` | `npm test` | `npm run lint` |
| `Cargo.toml` がある | `cargo build` | `cargo test` | `cargo clippy -- -D warnings` |
| `go.mod` がある | `go build ./...` | `go test ./...` | `go vet ./...` |
| `pyproject.toml` がある | (なし) | `pytest` | `ruff check .` |
| どれも無い | (なし) | `bash "$P/tests/smoke.sh"` | (なし) |

`$P` はプラグイン本体の場所。プラグインの場所を指す環境変数は**空で渡ることがある**ので、下の 1 行目（`/init` `/update` と同じ**素材行**）で解決してから使う。

```bash
P="${CLAUDE_PLUGIN_ROOT:-}"; [ -d "$P" ] || P="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/hirai-lite/*/ 2>/dev/null | sort -V | tail -1)"; P="${P%/}"; [ -d "$P" ] || P="$HOME/.claude/plugins/marketplaces/hirai-lite"
bash "$P/tests/smoke.sh"
```

`package.json` の場合は `scripts` に該当キーが存在するかを確認し、無いコマンドは飛ばして「build: script 不在のため未実行」と報告する。推測でコマンドを作らない。

## 手順

1. 3 コマンドを build → test → lint の順に 1 つずつ実行する。
2. exit 0 以外を返した時点で止める。後続は実行しない。
3. 失敗したコマンドについて、出力末尾 20 行と、原因になっているファイル名・行番号を提示する。
4. 修正して 1 からやり直す。同じエラー文字列で 3 回連続して失敗したら、その旨を報告して user の判断を仰ぐ。
5. 3 つ全部が exit 0 になったら結果表を出す。

```
build: exit 0 (Ns)
test : exit 0 (N passed / N total)
lint : exit 0 (0 warnings)
→ commit 可
```

## 追加で見るもの

test が exit 0 でも、以下に 1 件でも該当すれば `commit 可` と報告しない。

- `git diff` に `console.log` / `debugger` / `TODO:` の新規追加行がある。

```bash
git diff | grep -nE '^\+.*(console\.log|debugger|TODO:)'
```

- `git diff` に API key / token / password のリテラルがある。

```bash
git diff | grep -inE '^\+.*(api[_-]?key|secret|password|token)\s*[:=]\s*["'"'"'][^"'"'"']{8,}'
```

該当した行を提示し、削除するか user に確認する。元に戻せない操作なので、**承認を求めるときは判断材料 5 項目**（何をしたいか / なぜ / しないとどうなる / トレードオフ / どうやるか）**を本文に示してから** `AskUserQuestion`（`承認する` / `承認しない` / `修正して提案し直す`）**を出す。型と記入例**: `docs/rules-reference/approval-template.md`（プロジェクトに無ければプラグイン同梱の同名ファイル）。

## 判定できる終了条件

- build / test / lint のうち実行対象としたコマンドが全部 exit 0。
- 上記 2 つの grep が 0 件。

両方成立した時のみ `commit 可` と報告する。片方でも成立しなければ `commit 不可` と理由 1 行を報告する。
