#!/usr/bin/env bash
# ハーネス自己検証 smoke (6 case)。1 件でも FAIL なら exit 1。
# 予算監査 (case 4-6) は不可逆操作ではないため hook にせず本 smoke で担保する (設計 §4.7)。
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$here/../.." && pwd)}"
HOOKS="$ROOT/.claude/hooks"
FAILED=0

pass() { echo "PASS  case $1: $2"; }
fail() { echo "FAIL  case $1: $2 -- $3"; FAILED=1; }

# ---------- case 1: session-start.sh は対象ファイル不在でも exit 0 ----------
case_1() {
  local tmp out rc
  tmp="$(mktemp -d)"; mkdir -p "$tmp/.claude/hooks"
  cp "$HOOKS/session-start.sh" "$tmp/.claude/hooks/" 2>/dev/null
  out="$(CLAUDE_PROJECT_DIR="$tmp" bash "$tmp/.claude/hooks/session-start.sh" 2>&1)"; rc=$?
  local lines; lines="$(printf '%s\n' "$out" | grep -c . || true)"
  rm -rf "$tmp"
  if [ "$rc" -ne 0 ]; then fail 1 "session-start exit 0 (対象ファイル不在)" "exit=$rc"; return; fi
  if [ "${lines:-0}" -gt 5 ]; then fail 1 "session-start 出力 5 行以内" "${lines} 行"; return; fi
  pass 1 "session-start.sh は対象ファイル不在でも exit 0 / ${lines} 行出力"
}

# ---------- case 2: 閾値未満では無出力 ----------
case_2() {
  local out rc
  out="$(TMPDIR="$(mktemp -d)" HC_CONTEXT_RATIO=0.50 bash "$HOOKS/context-budget.sh" \
        <<< '{"session_id":"smoke-under"}' 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then fail 2 "閾値未満は無出力" "exit=$rc"; return; fi
  if [ -n "$out" ]; then fail 2 "閾値未満は無出力" "出力あり: $out"; return; fi
  pass 2 "context-budget.sh は閾値未満 (0.50) で無出力"
}

# ---------- case 3: 閾値超過で 1 度だけ発火 ----------
case_3() {
  local td first second
  td="$(mktemp -d)"
  first="$(TMPDIR="$td" HC_CONTEXT_RATIO=0.85 bash "$HOOKS/context-budget.sh" <<< '{"session_id":"smoke-over"}' 2>&1)"
  second="$(TMPDIR="$td" HC_CONTEXT_RATIO=0.85 bash "$HOOKS/context-budget.sh" <<< '{"session_id":"smoke-over"}' 2>&1)"
  rm -rf "$td"
  if ! printf '%s' "$first" | grep -q 'save-state'; then fail 3 "閾値超過で 1 度だけ発火" "1 回目が無出力"; return; fi
  if [ -n "$second" ]; then fail 3 "閾値超過で 1 度だけ発火" "2 回目も出力: $second"; return; fi
  pass 3 "context-budget.sh は 0.85 で 1 度発火し 2 度目は沈黙"
}

# ---------- case 4: T0 予算 (常時ロード合計 <= 3,000 tokens) ----------
case_4() {
  local total=0 files=() f bytes tokens
  [ -f "$ROOT/CLAUDE.md" ] && files+=("$ROOT/CLAUDE.md")
  if [ -d "$ROOT/.claude/rules" ]; then
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      [ "$(head -1 "$f" 2>/dev/null)" = "---" ] || files+=("$f")
    done < <(find "$ROOT/.claude/rules" -maxdepth 1 -name '*.md' 2>/dev/null | sort)
  fi
  if [ "${#files[@]}" -eq 0 ]; then
    fail 4 "T0 予算 <= 3,000 tokens" "CLAUDE.md / .claude/rules/*.md が未作成のため測定不可"; return
  fi
  for f in "${files[@]}"; do
    bytes="$(wc -c < "$f" 2>/dev/null | tr -d ' ')"
    total=$(( total + ${bytes:-0} ))
  done
  tokens=$(( total / 3 ))
  if [ "$tokens" -gt 3000 ]; then
    fail 4 "T0 予算 <= 3,000 tokens" "${tokens} tokens (${total} bytes / ${#files[@]} file)"; return
  fi
  pass 4 "T0 常時ロード ${tokens} tokens <= 3,000 (${#files[@]} file / ${total} bytes)"
}

# ---------- case 5: 層違反検出 (paths: 無し rule <= 3 本) ----------
case_5() {
  local n=0 f names=""
  if [ ! -d "$ROOT/.claude/rules" ]; then
    fail 5 "paths: 無し rule <= 3 本" ".claude/rules/ が未作成のため測定不可"; return
  fi
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    if ! head -20 "$f" 2>/dev/null | grep -q '^paths:'; then
      n=$(( n + 1 )); names="$names $(basename "$f")"
    fi
  done < <(find "$ROOT/.claude/rules" -maxdepth 1 -name '*.md' 2>/dev/null | sort)
  if [ "$n" -eq 0 ]; then fail 5 "paths: 無し rule <= 3 本" ".claude/rules/*.md が 0 件 (未作成)"; return; fi
  if [ "$n" -gt 3 ]; then fail 5 "paths: 無し rule <= 3 本" "${n} 本:${names}"; return; fi
  pass 5 "T0 層の rule は ${n} 本 <= 3 (${names# })"
}

# ---------- case 6: 数の予算 (hook<=5 / command<=12 / smoke case<=10) ----------
case_6() {
  local hooks cmds cases
  hooks="$(find "$ROOT/.claude/hooks" -maxdepth 1 -name '*.sh' 2>/dev/null | wc -l | tr -d ' ')"
  cmds="$(find "$ROOT/.claude/commands" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
  cases="$(grep -c '^case_[0-9][0-9]*()' "$here/smoke.sh" 2>/dev/null | tr -d ' ')"
  local msg="hook=${hooks}/5 command=${cmds}/12 smoke case=${cases}/10"
  if [ "${hooks:-0}" -gt 5 ] || [ "${cmds:-0}" -gt 12 ] || [ "${cases:-0}" -gt 10 ]; then
    fail 6 "数の予算" "$msg"; return
  fi
  pass 6 "数の予算 ${msg}"
}

case_1; case_2; case_3; case_4; case_5; case_6

echo "---"
if [ "$FAILED" -ne 0 ]; then echo "RESULT: FAIL"; exit 1; fi
echo "RESULT: PASS"
exit 0
