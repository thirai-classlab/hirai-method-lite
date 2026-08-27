#!/usr/bin/env bash
# 台帳 / 設計 draft / 事故記録の パス解決を 1 箇所に集める共通ライブラリ。source して使う。
#
# 共通の解決順: env 上書き > 既存パス (docs 側 → .claude 側) > docs/ の有無で決める
#   台帳     : HARNESS_TASKS_FILE     > docs/tasks/list.md            > .claude/tasks/list.md
#   draft    : HARNESS_DRAFT_DIR      > docs/draft/                   > .claude/draft/
#   事故記録 : HARNESS_INCIDENTS_FILE > docs/rules-reference/…        > .claude/rules-reference/…
# 台帳が 1 つも無い場合は空文字 + exit 1 を返す (エラーにせず呼び出し側で分岐する)。
# draft / 事故記録は未作成でも「これから作るべきパス」を返す (rc 0)。
#
# file-top に set -e / set -o pipefail を書かない。source 元の shell flags を汚染し、
# パイプ先の早期終了で呼び出し元ごと落ちる事故を防ぐため (関数内で局所化する)。

# harness_tasks_file [root] -> 台帳パスを stdout、無ければ空 + rc 1
harness_tasks_file() {
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" p
  if [ -n "${HARNESS_TASKS_FILE:-}" ]; then
    printf '%s' "$HARNESS_TASKS_FILE"
    return 0
  fi
  for p in "$root/docs/tasks/list.md" "$root/.claude/tasks/list.md"; do
    if [ -f "$p" ]; then
      printf '%s' "$p"
      return 0
    fi
  done
  return 1
}

# harness_draft_dir [root] -> 設計 draft の置き場を stdout (末尾スラッシュなし)
harness_draft_dir() {
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" p
  if [ -n "${HARNESS_DRAFT_DIR:-}" ]; then
    printf '%s' "$HARNESS_DRAFT_DIR"
    return 0
  fi
  for p in "$root/docs/draft" "$root/.claude/draft"; do
    if [ -d "$p" ]; then
      printf '%s' "$p"
      return 0
    fi
  done
  if [ -d "$root/docs" ]; then printf '%s' "$root/docs/draft"; else printf '%s' "$root/.claude/draft"; fi
}

# harness_incidents_file [root] -> 事故記録 (T2) のパスを stdout
harness_incidents_file() {
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" p
  if [ -n "${HARNESS_INCIDENTS_FILE:-}" ]; then
    printf '%s' "$HARNESS_INCIDENTS_FILE"
    return 0
  fi
  for p in "$root/docs/rules-reference/incidents.md" "$root/.claude/rules-reference/incidents.md"; do
    if [ -f "$p" ]; then
      printf '%s' "$p"
      return 0
    fi
  done
  if [ -d "$root/docs" ]; then
    printf '%s' "$root/docs/rules-reference/incidents.md"
  else
    printf '%s' "$root/.claude/rules-reference/incidents.md"
  fi
}

# harness_open_tasks <list.md> -> 未完了 (完了 / done / ✅ 以外) の行数を stdout
harness_open_tasks() {
  local f="${1:-}" total done_n n
  [ -f "$f" ] || { printf '0'; return 0; }
  # grep -c は 0 件のとき "0" を出しつつ exit 1 を返す。数字以外を捨てて必ず整数にする。
  total="$(grep -c '^|[[:space:]]*[0-9]' "$f" 2>/dev/null | tr -cd '0-9')"
  done_n="$(grep '^|[[:space:]]*[0-9]' "$f" 2>/dev/null | grep -c -e '✅' -e '完了' -e '[Dd]one' | tr -cd '0-9')"
  n=$(( ${total:-0} - ${done_n:-0} ))
  [ "$n" -ge 0 ] 2>/dev/null || n=0
  printf '%s' "$n"
}
