#!/usr/bin/env bash
# statusLine (1 行): <model> | ctx <N>% ・5h <N>% ・7d <N>% | mode: <進め方> | <branch> | やること <N>
# 進め方は normal を「確認あり」、loop を「自動」と日本語で出す (値そのものを平易にする)。
# stdin は Claude Code の session JSON。jq 不在 / JSON 破損 / 台帳不在 / git 外でも
# 必ず 1 行返して exit 0 (fail-open)。NO_COLOR が非空なら色を落とす。
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || here="."
root="${CLAUDE_PROJECT_DIR:-$PWD}"
input="$(cat 2>/dev/null || true)"

E=$'\033'; R="${E}[0m"; DIM="${E}[2m"; GRN="${E}[32m"; YEL="${E}[33m"; RED="${E}[31m"; CYA="${E}[36m"
if [ -n "${NO_COLOR:-}" ]; then R=""; DIM=""; GRN=""; YEL=""; RED=""; CYA=""; fi
SEP="${DIM} | ${R}"

jqf() {  # JSON から 1 フィールド。jq 不在なら空。
  command -v jq >/dev/null 2>&1 || return 0
  printf '%s' "$input" | jq -r "$1 // empty" 2>/dev/null || true
}

lbl() { printf '%s%s%s' "$DIM" "$1" "$R"; }

pct() {  # 使用率を整数 % + 色に。非数は "—"。0-100 に clamp。
  local v="${1%%.*}" col="$GRN"
  case "$v" in ''|null|*[!0-9-]*) printf '%s—%s' "$DIM" "$R"; return 0 ;; esac
  if [ "$v" -lt 0 ] 2>/dev/null; then v=0; elif [ "$v" -gt 100 ] 2>/dev/null; then v=100; fi
  if [ "$v" -ge 80 ] 2>/dev/null; then col="$RED"; elif [ "$v" -ge 50 ] 2>/dev/null; then col="$YEL"; fi
  printf '%s%s%%%s' "$col" "$v" "$R"
}

model="$(jqf '.model.display_name')"; [ -n "$model" ] || model="Claude"
ctx="$(pct "$(jqf '.context_window.used_percentage')")"
h5="$(pct "$(jqf '.rate_limits.five_hour.used_percentage')")"
d7="$(pct "$(jqf '.rate_limits.seven_day.used_percentage')")"

branch="$(jqf '.workspace.repo.branch')"
[ -n "$branch" ] || branch="$(git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
[ -n "$branch" ] || branch="-"

# mode: env HC_MODE > プロジェクトの mode.yml > ホームの mode.yml (全プロジェクト共通) > normal。
# 表示は日本語に置き換える (未知の値はそのまま出す)。
mode="${HC_MODE:-}"
if [ -z "$mode" ]; then
  for mf in "$root/.claude/mode.yml" "${HOME:-}/.claude/mode.yml"; do
    [ -f "$mf" ] || continue
    mode="$(sed -n 's/^[[:space:]]*mode:[[:space:]]*\([a-z]*\).*/\1/p' "$mf" 2>/dev/null | head -1)"
    [ -n "$mode" ] && break
  done
fi
[ -n "$mode" ] || mode="normal"
case "$mode" in
  normal) mode_label="確認あり" ;;
  loop)   mode_label="自動" ;;
  *)      mode_label="$mode" ;;
esac

# 未完了タスク: 台帳の解決順は scripts/tasks-path.sh (同じディレクトリ、台帳なしは "—")
todo="—"
if [ -f "$here/tasks-path.sh" ]; then
  . "$here/tasks-path.sh" 2>/dev/null || true
  list="$(harness_tasks_file "$root" 2>/dev/null || true)"
  if [ -n "$list" ] && [ -f "$list" ]; then todo="$(harness_open_tasks "$list")"; fi
fi

printf '%s%s%s%s%s %s %s・%s %s %s・%s %s%s%s %s%s%s%s%s %s\n' \
  "$CYA" "$model" "$R" "$SEP" \
  "$(lbl ctx)" "$ctx" "$DIM" "$(lbl 5h)" "$h5" "$DIM" "$(lbl 7d)" "$d7" \
  "$SEP" "$(lbl 'mode:')" "$mode_label" \
  "$SEP" "$branch" \
  "$SEP" "$(lbl やること)" "$todo"
exit 0
