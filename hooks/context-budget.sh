#!/usr/bin/env bash
# UserPromptSubmit hook: context 使用率が閾値以上になった最初の 1 回だけ /state save を促す。
#
# 使用率の計算は **scripts/context-usage.sh に集約している**。画面下部 (scripts/statusline.sh) と
# 同じ関数を通すので、同じ瞬間に別々の数字が出ることはない (v1.9.0 まではここだけ
# 「直近のトークン数 ÷ 200,000 固定」で計算しており、窓が 1,000,000 の会話では
# 画面下部の 17% に対しこの hook が 83% と警告していた)。
#
#   分子: transcript の直近の API 応答 1 件の input + cache 作成 + cache 読み + output
#   分母: HC_CONTEXT_WINDOW (env) > 画面下部が観測した窓サイズの控え > 推定 (トークン数が
#         200,000 を超えていれば 1,000,000) > 既定 200,000
#   閾値: HC_CONTEXT_THRESHOLD (既定 0.50 = 50%。割合でも百分率でも受ける)
#   使用率の直接指定 (検査用): HC_CONTEXT_RATIO (0-1 の割合)
#
# 推定してもなお 100% を超える (窓が分からない) ときは発火しない (誤発火より沈黙が安全、v1.15.0)。
# 発火フラグはリポジトリ外 (${TMPDIR:-/tmp}) に置く。内部エラーでも常に exit 0 (fail-open)。
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || here="."
plugin_root="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$plugin_root" ] || [ ! -d "$plugin_root" ]; then
  plugin_root="$(cd "$here/.." 2>/dev/null && pwd)" || plugin_root="."
fi
# shellcheck source=../scripts/context-usage.sh
[ -f "$plugin_root/scripts/context-usage.sh" ] \
  && . "$plugin_root/scripts/context-usage.sh" 2>/dev/null || true
command -v harness_ctx_percent >/dev/null 2>&1 || exit 0   # 共通ライブラリ不在なら黙って通す

input="$(cat 2>/dev/null || true)"
session="$(harness_ctx_json_string "$input" session_id || true)"; [ -n "$session" ] || session="default"
transcript="$(harness_ctx_json_string "$input" transcript_path || true)"

estimated=""
if [ -n "${HC_CONTEXT_RATIO:-}" ]; then
  # 割合の直接指定は分母を通さない (検査用の入口)。丸めは共通の四捨五入に合わせる。
  pct="$(awk -v r="$HC_CONTEXT_RATIO" 'BEGIN {printf "%d", int((r + 0) * 100 + 0.5)}' 2>/dev/null)"
  window="$(harness_ctx_window 0 "$session")"
else
  tokens="$(harness_ctx_tokens_from_transcript "$transcript")"
  # 控えも明示も無く、推定 (200,000 超 → 1,000,000) してもなお超えるときは窓サイズ不明。
  # 誤って大きい使用率 (例: 386%) を出すより、発火せず沈黙するほうが安全 (v1.15.0)。
  harness_ctx_window_unknown "$tokens" "$session" && exit 0
  window="$(harness_ctx_window "$tokens" "$session")"
  harness_ctx_window_is_estimated "$tokens" "$session" && estimated="（推定）"
  pct="$(harness_ctx_percent "$tokens" "$window")"
fi

harness_ctx_over_threshold "$pct" || exit 0

flag_dir="${TMPDIR:-/tmp}/claude-harness-lite"
mkdir -p "$flag_dir" 2>/dev/null || exit 0
flag="$flag_dir/ctx-$(printf '%s' "$session" | tr -c 'A-Za-z0-9_.-' '_').fired"
[ -e "$flag" ] && exit 0
: > "$flag" 2>/dev/null || exit 0

echo "[harness] context 使用率が ${pct}% (閾値 $(harness_ctx_threshold)% / 窓 ${window} tokens${estimated}) に達しました。"
echo "[harness] このターン内で /state save を実行し、新セッションで /state resume するか継続するかを提案してください。"
exit 0
