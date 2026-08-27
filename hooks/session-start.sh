#!/usr/bin/env bash
# SessionStart hook: 現在の mode / 未完了タスク数 / 直近 state を 5 行以内で出力する。
# 対象ファイルが 1 つも無くても正常終了する (fail-open)。
#
# パス解決は 2 段構え。
#   plugin_root : $CLAUDE_PLUGIN_ROOT > このスクリプトの 1 つ上 ($BASH_SOURCE 起点)
#   root        : $CLAUDE_PROJECT_DIR > $PWD   (導入先リポジトリ = ユーザーの資産)
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || here="."
plugin_root="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$plugin_root" ] || [ ! -d "$plugin_root" ]; then
  plugin_root="$(cd "$here/.." 2>/dev/null && pwd)" || plugin_root="."
fi
root="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$root" ] || [ ! -d "$root" ]; then
  root="$PWD"
fi

# --- mode: env HC_MODE > 導入先の .claude/mode.yml > normal ---
mode="${HC_MODE:-}"
if [ -z "$mode" ] && [ -f "$root/.claude/mode.yml" ]; then
  mode="$(sed -n 's/^[[:space:]]*mode:[[:space:]]*\([a-z]*\).*/\1/p' "$root/.claude/mode.yml" 2>/dev/null | head -1)"
fi
[ -n "$mode" ] || mode="normal"

# --- 未完了タスク数: 台帳 (解決順は scripts/tasks-path.sh) の table 行から数える ---
list=""
if [ -f "$plugin_root/scripts/tasks-path.sh" ]; then
  # shellcheck source=../scripts/tasks-path.sh
  . "$plugin_root/scripts/tasks-path.sh" 2>/dev/null || true
  list="$(harness_tasks_file "$root" 2>/dev/null || true)"
fi
if [ -n "$list" ] && [ -f "$list" ]; then
  task_line="未完了タスク: $(harness_open_tasks "$list") 件 (${list#"$root"/})"
else
  task_line="台帳なし (/new-task が作成します)"
fi

# --- 更新検知: 取得は背景 + 24h に 1 回、表示は前回キャッシュ値 (通信を待たない) ---
# 版を比べる VERSION はプラグイン側にあるので plugin_root を渡す。
update_line=""
if [ -f "$plugin_root/scripts/update-check.sh" ]; then
  # shellcheck source=../scripts/update-check.sh
  . "$plugin_root/scripts/update-check.sh" 2>/dev/null || true
  if command -v harness_update_notice >/dev/null 2>&1; then
    harness_update_fetch_async "$plugin_root" >/dev/null 2>&1 || true
    update_line="$(harness_update_notice "$plugin_root" 2>/dev/null || true)"
  fi
fi

# --- 直近 state (導入先リポジトリ側) ---
state=""
for d in "$root/.claude/state" "$root/docs/state"; do
  [ -d "$d" ] || continue
  f="$(ls -t "$d" 2>/dev/null | head -1)"
  [ -n "$f" ] && state="${d#"$root"/}/$f" && break
done

echo "[harness] mode: ${mode}"
echo "[harness] ${task_line}"
if [ -n "$state" ]; then
  echo "[harness] 直近 state: ${state} (/state resume で復元)"
else
  echo "[harness] 直近 state: なし"
fi
[ -n "$update_line" ] && echo "$update_line"

exit 0
