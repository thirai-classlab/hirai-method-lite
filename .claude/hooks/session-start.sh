#!/usr/bin/env bash
# SessionStart hook: 現在の mode / 未完了タスク数 / 直近 state を 5 行以内で出力する。
# 対象ファイルが 1 つも無くても正常終了する (fail-open)。
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || here="."
root="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$root" ] || [ ! -d "$root" ]; then
  root="$(cd "$here/../.." 2>/dev/null && pwd)" || root="."
fi

# --- mode: env HC_MODE > mode.yml > normal ---
mode="${HC_MODE:-}"
if [ -z "$mode" ] && [ -f "$root/.claude/mode.yml" ]; then
  mode="$(sed -n 's/^[[:space:]]*mode:[[:space:]]*\([a-z]*\).*/\1/p' "$root/.claude/mode.yml" 2>/dev/null | head -1)"
fi
[ -n "$mode" ] || mode="normal"

# --- 未完了タスク数: list.md の table 行のうち完了 (✅ / done) でないもの ---
list="$root/docs/tasks/list.md"
if [ -f "$list" ]; then
  open_tasks="$(grep -c '^|[[:space:]]*[0-9]' "$list" 2>/dev/null || echo 0)"
  done_tasks="$(grep '^|[[:space:]]*[0-9]' "$list" 2>/dev/null | grep -c -e '✅' -e '完了' -e '[Dd]one' || true)"
  open_tasks=$(( ${open_tasks:-0} - ${done_tasks:-0} ))
  [ "$open_tasks" -ge 0 ] 2>/dev/null || open_tasks=0
  task_line="未完了タスク: ${open_tasks} 件 (docs/tasks/list.md)"
else
  task_line="未完了タスク: — (docs/tasks/list.md 未作成)"
fi

# --- 直近 state ---
state=""
for d in "$root/.claude/state" "$root/docs/state"; do
  [ -d "$d" ] || continue
  f="$(ls -t "$d" 2>/dev/null | head -1)"
  [ -n "$f" ] && state="${d#"$root"/}/$f" && break
done

echo "[harness] mode: ${mode}"
echo "[harness] ${task_line}"
if [ -n "$state" ]; then
  echo "[harness] 直近 state: ${state} (/resume-state で復元)"
else
  echo "[harness] 直近 state: なし"
fi

exit 0
