#!/usr/bin/env bash
# statusLine (1 行): <model> | ctx <N>% ・5h <N>% ・7d <N>% | mode: <進め方> | <branch> | やること <N> [| <お知らせ>]
# 進め方は normal を「確認あり」、loop を「自動」と日本語で出す (値そのものを平易にする)。
# 末尾のお知らせ枠は最大 1 件だけ (優先: 更新あり > context 使用率が閾値以上)。どちらでもなければ
# 区切りごと出さない。HC_STATUSLINE_NOTICE=off で枠ごと止める。
# stdin は Claude Code の session JSON。jq 不在 / JSON 破損 / 台帳不在 / git 外でも
# 必ず 1 行返して exit 0 (fail-open)。NO_COLOR が非空なら色を落とす。
#
# **この scripts は通信しない。** 画面下部は何度も描き直されるため、更新の有無は
# SessionStart 側 (scripts/update-check.sh の harness_update_flag_sync) が置いたフラグ 1 ファイルの
# 有無を見るだけにする。取得も版の比較もここでは行わない。
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

# ctx_over_threshold <使用率> -> 閾値以上なら rc 0。閾値は HC_CONTEXT_THRESHOLD で、
# 0.80 のような割合でも 80 のような百分率でも受ける (既定 0.80 = 80%)。非数は常に rc 1。
ctx_over_threshold() {
  local v="${1%%.*}"
  case "$v" in ''|null|*[!0-9]*) return 1 ;; esac
  awk -v r="$v" -v th="${HC_CONTEXT_THRESHOLD:-0.80}" \
    'BEGIN {t = th + 0; if (t <= 1) t *= 100; exit !(r + 0 >= t)}' 2>/dev/null
}

model="$(jqf '.model.display_name')"; [ -n "$model" ] || model="Claude"
ctx_raw="$(jqf '.context_window.used_percentage')"
ctx="$(pct "$ctx_raw")"
h5="$(pct "$(jqf '.rate_limits.five_hour.used_percentage')")"
d7="$(pct "$(jqf '.rate_limits.seven_day.used_percentage')")"

branch="$(jqf '.workspace.repo.branch')"
[ -n "$branch" ] || branch="$(git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
[ -n "$branch" ] || branch="-"

# 共通ライブラリ (同じディレクトリ) を先に読む。進め方と台帳のパス解決はここに集約している。
# tasks-path.sh と statusline.sh はどちらもプラグイン所有で、/init と /update が対で入れ替える。
[ -f "$here/tasks-path.sh" ] && . "$here/tasks-path.sh" 2>/dev/null || true

# mode: 解決順は harness_mode (env HC_MODE > プロジェクトの mode.yml > ホームの mode.yml > normal)。
# SessionStart (hooks/session-start.sh) と /mode も同じ関数を通す。ここで独自に解決しない。
# 表示は日本語に置き換える (未知の値はそのまま出す)。
if command -v harness_mode >/dev/null 2>&1; then
  mode="$(harness_mode "$root")"
else
  mode="${HC_MODE:-normal}"
fi
[ -n "$mode" ] || mode="normal"
case "$mode" in
  normal) mode_label="確認あり" ;;
  loop)   mode_label="自動" ;;
  *)      mode_label="$mode" ;;
esac

# 未完了タスク: 台帳の解決順は scripts/tasks-path.sh (冒頭で source 済み、台帳なしは "—")
todo="—"
if command -v harness_tasks_file >/dev/null 2>&1; then
  list="$(harness_tasks_file "$root" 2>/dev/null || true)"
  if [ -n "$list" ] && [ -f "$list" ]; then todo="$(harness_open_tasks "$list")"; fi
fi

# --- お知らせ枠 (最終段): 上から順に 1 つだけ、どれにも当たらなければ何も出さない ---
#   1. 更新あり  … SessionStart が置いたフラグの有無だけを見る (通信しない)
#   2. context 高 … 使用率が HC_CONTEXT_THRESHOLD 以上
notice=""
if [ "${HC_STATUSLINE_NOTICE:-on}" != "off" ]; then
  if [ "${HARNESS_UPDATE_CHECK:-on}" != "off" ] \
    && [ -s "${TMPDIR:-/tmp}/claude-harness-lite/update-available" ]; then
    notice="更新あり → /hirai-lite:update"
  elif ctx_over_threshold "$ctx_raw"; then
    notice="きりの良いところで /hirai-lite:state save"
  fi
fi

line="$(printf '%s%s%s%s%s %s %s・%s %s %s・%s %s%s%s %s%s%s%s%s %s' \
  "$CYA" "$model" "$R" "$SEP" \
  "$(lbl ctx)" "$ctx" "$DIM" "$(lbl 5h)" "$h5" "$DIM" "$(lbl 7d)" "$d7" \
  "$SEP" "$(lbl 'mode:')" "$mode_label" \
  "$SEP" "$branch" \
  "$SEP" "$(lbl やること)" "$todo")"
[ -n "$notice" ] && line="${line}${SEP}${YEL}${notice}${R}"
printf '%s\n' "$line"
exit 0
