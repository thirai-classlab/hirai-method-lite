#!/usr/bin/env bash
# context（会話の入れ物）使用率の計算を 1 か所に集める共通ライブラリ。source して使う。
#
# **なぜ 1 か所に集めるのか。** v1.9.0 までは画面下部 (scripts/statusline.sh) と
# 自動処理 (hooks/context-budget.sh) が別々に使用率を出していた。前者は Claude Code が
# 渡す済みの百分率をそのまま表示し、後者は「直近のトークン数 ÷ 200,000 固定」を自分で計算していた。
# 窓が 1,000,000 の会話では前者が 17%、後者が 83% と、同じ瞬間に矛盾する 2 つの数字が出た
# (v1.10.0 で修正)。分子・分母・丸め・閾値の判定をここに集め、両方が同じ関数を通す。
#
# 分子 = input_tokens + cache_creation_input_tokens + cache_read_input_tokens + output_tokens
#        (= 画面下部の入力 JSON では total_input_tokens + total_output_tokens と同じ量。
#         Claude Code 自身も exceeds_200k_tokens をこの 4 つの合計で判定している)
# 分母 = 窓サイズ。解決順は HC_CONTEXT_WINDOW (env) > 控え (画面下部が観測した実測値)
#        > 推定 (トークン数が既定窓を超えていれば 1,000,000) > 既定 200,000。
# 使用率 = 四捨五入した整数の百分率。閾値の判定も**使用率**で行う (残量では見ない)。
#
# **窓サイズの実測値はどこから来るか。** 画面下部の入力 JSON だけが
# `context_window.context_window_size` (200000 か 1000000) を持つ。自動処理 (hook) の入力 JSON には
# 無く、transcript にも環境変数にも無い。そこで画面下部が観測値を控え 1 ファイルへ書き、
# hook はそれを読む (更新検知が SessionStart → 画面下部へ控えを渡しているのと同じ作法)。
#
# **控えが無いときは推定する (v1.15.0)。** Claude Code の窓は 200,000 か 1,000,000 の 2 種類しか
# 無い。トークン数が既定 (200,000) を超えていれば、200k の窓ではあり得ない量なので窓は
# 1,000,000 と推定する (画面下部が一度も描かれない環境 — 旧ハーネスの別 statusLine が設定済み等 —
# では控えが一生できず、v1.10.0 までは 200,000 固定のまま割り、1M の会話で使用率が 386% のような
# 値になった)。推定してもなお 100% を超える (トークン数が 1,000,000 も超える) ときは「窓サイズ不明」
# として扱い、自動処理は発火しない (誤発火より沈黙が安全)。`HC_CONTEXT_WINDOW` が明示されていれば
# 推定はしない (明示が優先)。詳しくは README「context 使用率の出し方」。
#
# file-top に set -e / set -o pipefail を書かない。source 元の shell flags を汚染し、
# パイプ先の早期終了で呼び出し元ごと落ちる事故を防ぐため (関数内で局所化する)。

# 窓サイズが分からないときの既定。Claude Code の既定の窓と同じ値にしてある。
HARNESS_CTX_WINDOW_DEFAULT="${HARNESS_CTX_WINDOW_DEFAULT:-200000}"
# 控えも明示も無いとき、既定を超えるトークン数から推定する窓サイズ。Claude Code の窓は
# 200,000 か 1,000,000 の 2 種類のみなので、既定を超えた時点でこちらしかあり得ない。
HARNESS_CTX_WINDOW_ESTIMATE="${HARNESS_CTX_WINDOW_ESTIMATE:-1000000}"

# harness_ctx_window_file [session_id] -> 窓サイズの控えのパスを stdout (作成はしない)
# 会話ごとに分ける (同じマシンで 1M の会話と 200k の会話が同時に走っても混ざらない)。
harness_ctx_window_file() (
  set -uo pipefail
  local s
  s="$(printf '%s' "${1:-}" | tr -c 'A-Za-z0-9_.-' '_')"
  [ -n "$s" ] || s="default"
  printf '%s/claude-harness-lite/ctx-window-%s' "${TMPDIR:-/tmp}" "$s"
)

# harness_ctx_window_remember <session_id> <窓サイズ> -> 観測値を控える。常に rc 0 (無出力)。
# 値が変わっていなければ書かない (画面下部は何度も描き直されるため)。
harness_ctx_window_remember() (
  set -uo pipefail
  local s="${1:-}" n="${2:-}" f cur
  n="$(printf '%s' "$n" | tr -cd '0-9')"
  [ -n "$n" ] || return 0
  [ "$n" -gt 0 ] 2>/dev/null || return 0
  f="$(harness_ctx_window_file "$s")"
  cur="$(head -1 "$f" 2>/dev/null | tr -cd '0-9')"
  [ "$cur" = "$n" ] && return 0
  mkdir -p "${f%/*}" 2>/dev/null || return 0
  printf '%s' "$n" > "$f.tmp" 2>/dev/null && mv -f "$f.tmp" "$f" 2>/dev/null
  return 0
)

# harness_ctx_window <合計トークン> [session_id] -> 窓サイズ (正の整数) を stdout。常に rc 0。
# 解決順: HC_CONTEXT_WINDOW (env) > 控え > 推定 (トークン数が既定を超えていれば
# HARNESS_CTX_WINDOW_ESTIMATE) > 既定 (HARNESS_CTX_WINDOW_DEFAULT)。
# <合計トークン> は推定の判定にだけ使う (0 / 省略なら推定は働かず既定のまま)。
harness_ctx_window() (
  set -uo pipefail
  local tokens="${1:-0}" v
  tokens="$(printf '%s' "$tokens" | tr -cd '0-9')"; [ -n "$tokens" ] || tokens=0
  v="$(printf '%s' "${HC_CONTEXT_WINDOW:-}" | tr -cd '0-9')"
  if [ -n "$v" ] && [ "$v" -gt 0 ] 2>/dev/null; then printf '%s' "$v"; return 0; fi
  v="$(head -1 "$(harness_ctx_window_file "${2:-}")" 2>/dev/null | tr -cd '0-9')"
  if [ -n "$v" ] && [ "$v" -gt 0 ] 2>/dev/null; then printf '%s' "$v"; return 0; fi
  if [ "$tokens" -gt "$HARNESS_CTX_WINDOW_DEFAULT" ] 2>/dev/null; then
    printf '%s' "$HARNESS_CTX_WINDOW_ESTIMATE"; return 0
  fi
  printf '%s' "$HARNESS_CTX_WINDOW_DEFAULT"
)

# harness_ctx_window_is_estimated <合計トークン> [session_id] -> harness_ctx_window が
# 明示 (env) でも実測 (控え) でもなく推定で答えたときだけ rc 0。表示に「（推定）」を
# 添えるかどうかの判定に使う。
harness_ctx_window_is_estimated() (
  set -uo pipefail
  local tokens="${1:-0}" v
  tokens="$(printf '%s' "$tokens" | tr -cd '0-9')"; [ -n "$tokens" ] || tokens=0
  v="$(printf '%s' "${HC_CONTEXT_WINDOW:-}" | tr -cd '0-9')"
  { [ -n "$v" ] && [ "$v" -gt 0 ]; } 2>/dev/null && return 1
  v="$(head -1 "$(harness_ctx_window_file "${2:-}")" 2>/dev/null | tr -cd '0-9')"
  { [ -n "$v" ] && [ "$v" -gt 0 ]; } 2>/dev/null && return 1
  [ "$tokens" -gt "$HARNESS_CTX_WINDOW_DEFAULT" ] 2>/dev/null
)

# harness_ctx_window_unknown <合計トークン> [session_id] -> 推定してもなお 100% を超える
# (= トークン数が推定窓 HARNESS_CTX_WINDOW_ESTIMATE も超える) ときだけ rc 0。
# 明示 (env) や実測 (控え) があるときは常に rc 1 (常に「不明」ではない — 明示は信頼する)。
# 呼び出し側はこれが rc 0 のとき、使用率を出さない (誤発火より沈黙が安全)。
harness_ctx_window_unknown() (
  set -uo pipefail
  local tokens="${1:-0}" win
  tokens="$(printf '%s' "$tokens" | tr -cd '0-9')"; [ -n "$tokens" ] || tokens=0
  harness_ctx_window_is_estimated "$tokens" "${2:-}" || return 1
  win="$(harness_ctx_window "$tokens" "${2:-}")"
  [ "$tokens" -gt "$win" ] 2>/dev/null
)

# harness_ctx_json_number <入力 JSON> <キー名> -> そのキーの整数値を stdout、無ければ空 + rc 1。
# jq が無い環境でも動くようにするための最小限の取り出し (改行を潰してから最初の 1 個を拾う)。
harness_ctx_json_number() (
  set -uo pipefail
  local out
  out="$(printf '%s' "${1:-}" | tr '\n\r\t' '   ' \
    | sed -n "s/.*\"${2:-}\"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p" \
    | head -1 | tr -cd '0-9')"
  [ -n "$out" ] || return 1
  printf '%s' "$out"
)

# harness_ctx_json_string <入力 JSON> <キー名> -> そのキーの文字列値を stdout、無ければ空 + rc 1。
# 使うのは JSON 全体で 1 度しか出てこないキー (session_id / transcript_path) に限る。
harness_ctx_json_string() (
  set -uo pipefail
  local out
  out="$(printf '%s' "${1:-}" | tr '\n\r\t' '   ' \
    | sed -n "s/.*\"${2:-}\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -1)"
  [ -n "$out" ] || return 1
  printf '%s' "$out"
)

# harness_ctx_tokens_from_json <入力 JSON> -> 分子 (合計トークン) を stdout、取れなければ空 + rc 1。
# 画面下部の入力 JSON 用。total_input_tokens は input + cache 作成 + cache 読みの合計。
harness_ctx_tokens_from_json() (
  set -uo pipefail
  local i o
  i="$(harness_ctx_json_number "${1:-}" total_input_tokens)" || return 1
  o="$(harness_ctx_json_number "${1:-}" total_output_tokens)" || o=0
  printf '%s' "$(( i + o ))"
)

# harness_ctx_window_from_json <入力 JSON> -> context_window_size を stdout、無ければ空 + rc 1
harness_ctx_window_from_json() (
  set -uo pipefail
  local out
  out="$(harness_ctx_json_number "${1:-}" context_window_size)" || return 1
  [ "$out" -gt 0 ] 2>/dev/null || return 1
  printf '%s' "$out"
)

# harness_ctx_tokens_from_transcript <transcript のパス> -> 分子 (合計トークン) を stdout。
# 直近の API 応答 1 件だけを見る (会話全体の足し算ではない)。読めなければ 0。常に rc 0。
harness_ctx_tokens_from_transcript() (
  set -uo pipefail
  local f="${1:-}" out
  if [ -z "$f" ] || [ ! -f "$f" ]; then printf '0'; return 0; fi
  out="$(tail -n 400 "$f" 2>/dev/null | awk '
    /"usage"/ { line = $0 }
    END {
      if (line == "") { print 0; exit }
      s = substr(line, index(line, "\"usage\""))
      n = split("input_tokens cache_creation_input_tokens cache_read_input_tokens output_tokens", k, " ")
      t = 0
      for (j = 1; j <= n; j++) {
        # match() は最初の 1 個に当たる。usage の中の iterations[] にある同名は数えない。
        p = "\"" k[j] "\"[ \t]*:[ \t]*[0-9]+"
        if (match(s, p)) { v = substr(s, RSTART, RLENGTH); sub(/^.*:[ \t]*/, "", v); t += v }
      }
      printf "%d", t
    }' 2>/dev/null)"
  out="$(printf '%s' "$out" | tr -cd '0-9')"
  [ -n "$out" ] || out="0"
  printf '%s' "$out"
)

# harness_ctx_percent <合計トークン> <窓サイズ> -> 0 以上の整数の百分率を stdout。常に rc 0。
# 丸めは四捨五入。窓サイズが 0 以下 / 非数なら 0 を返す (嘘の警告を出さない)。
harness_ctx_percent() (
  set -uo pipefail
  awk -v t="${1:-0}" -v w="${2:-0}" 'BEGIN {
    t += 0; w += 0
    if (w <= 0 || t <= 0) { print 0; exit }
    p = int(t * 100 / w + 0.5)
    print (p < 0 ? 0 : p)
  }' 2>/dev/null || printf '0'
)

# harness_ctx_threshold -> 閾値を 0-100 の整数 (使用率の百分率) にして stdout。常に rc 0。
# HC_CONTEXT_THRESHOLD は 0.50 のような割合でも 50 のような百分率でも受ける (既定 0.50 = 50%)。
# 非数 / 0 以下は既定の 50 に倒す (「常に警告」になって狼少年化するのを防ぐ)。
harness_ctx_threshold() (
  set -uo pipefail
  awk -v th="${HC_CONTEXT_THRESHOLD:-0.50}" 'BEGIN {
    t = th + 0
    if (t <= 0) t = 50
    else if (t <= 1) t *= 100
    printf "%d", int(t + 0.5)
  }' 2>/dev/null || printf '50'
)

# harness_ctx_over_threshold <使用率 (整数 %)> -> 閾値**以上**なら rc 0。非数は常に rc 1。
# 画面下部のお知らせと hook の発火が同じ向き (使用率 >= 閾値) を見るための 1 本。
harness_ctx_over_threshold() (
  set -uo pipefail
  local p="${1:-}" th
  case "$p" in ''|*[!0-9]*) return 1 ;; esac
  th="$(harness_ctx_threshold)"
  [ "$p" -ge "$th" ] 2>/dev/null
)
