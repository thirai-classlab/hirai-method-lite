#!/usr/bin/env bash
# UserPromptSubmit hook: context 使用率が閾値を超えた最初の 1 回だけ /save-state を促す。
# 閾値: HC_CONTEXT_THRESHOLD (default 0.80) / 使用率直接指定: HC_CONTEXT_RATIO
# 発火フラグはリポジトリ外 (${TMPDIR:-/tmp}) に置く。内部エラーでも常に exit 0 (fail-open)。
set -uo pipefail

THRESHOLD="${HC_CONTEXT_THRESHOLD:-0.80}"
WINDOW="${HC_CONTEXT_WINDOW:-200000}"
input="$(cat 2>/dev/null || true)"

field() { printf '%s' "$input" | sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -1; }
session="$(field session_id)"; [ -n "$session" ] || session="default"
transcript="$(field transcript_path)"

ratio="${HC_CONTEXT_RATIO:-}"
if [ -z "$ratio" ]; then
  tokens=0
  if [ -f "$transcript" ]; then
    tokens="$(tail -200 "$transcript" 2>/dev/null | grep -o '"usage":[[:space:]]*{[^}]*}' | tail -1 \
      | grep -o '[0-9][0-9]*' | awk '{s+=$1} END {print s+0}')"
  fi
  ratio="$(awk -v t="${tokens:-0}" -v w="$WINDOW" 'BEGIN {printf "%.4f", (w+0>0 ? t/w : 0)}')"
fi

awk -v r="$ratio" -v th="$THRESHOLD" 'BEGIN {exit !((r+0) > (th+0))}' || exit 0

flag_dir="${TMPDIR:-/tmp}/claude-harness-lite"
mkdir -p "$flag_dir" 2>/dev/null || exit 0
flag="$flag_dir/ctx-$(printf '%s' "$session" | tr -c 'A-Za-z0-9_.-' '_').fired"
[ -e "$flag" ] && exit 0
: > "$flag" 2>/dev/null || exit 0

pct="$(awk -v r="$ratio" 'BEGIN {printf "%d", (r+0)*100}')"
echo "[harness] context 使用率が ${pct}% (閾値 $(awk -v t="$THRESHOLD" 'BEGIN{printf "%d", (t+0)*100}')%) を超えました。"
echo "[harness] このターン内で /save-state を実行し、新セッションで /resume-state するか継続するかを提案してください。"
exit 0
