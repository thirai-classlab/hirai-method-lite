#!/usr/bin/env bash
# Notification(permission_prompt) と PermissionDenied の hook: 権限の確認の画面で止まった・auto mode の分類器が止めた、
# ことを Orca のコーディネーターへ知らせる（担当の会話はユーザーが画面を見に行くまで止まったままになるため）。
#
# `.claude/mode.yml` の `notify: orca`（env HC_NOTIFY が優先）のときだけ bin/hirai-notify waiting を呼ぶ。
# 判断は変えない: 標準出力に何も出さず常に exit 0。送れなかったときは stderr に 1 行だけ。
# 同じ会話から 1 分に 2 通以上送らない（最後に送った時刻を ${CLAUDE_PLUGIN_DATA} か <root>/.claude/state/ に置く）。
# tool_input の中身は送らない（秘密を含みうる）。Bash のコマンドは先頭 60 字まで。
# 入力を読む道具（jq か python3）が無いときは何もしない。
set -uo pipefail

plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"
input="$(cat 2>/dev/null)" || input=""
[ -n "$input" ] || exit 0

# fields: event / ntype / message / tool / cmd / reason / cwd / session を 1 行ずつ（改行は空白に）
fields=""
if command -v jq >/dev/null 2>&1; then
  fields="$(printf '%s' "$input" | jq -r '[.hook_event_name, .notification_type, .message, .tool_name, (.tool_input.command // ""), .reason, .cwd, .session_id] | map((. // "") | tostring | gsub("[\r\n]+"; " ")) | .[]' 2>/dev/null)" || fields=""
elif command -v python3 >/dev/null 2>&1; then
  fields="$(printf '%s' "$input" | python3 -c '
import json,re,sys
try: d=json.load(sys.stdin)
except Exception: sys.exit(1)
ti=d.get("tool_input")
cmd=ti.get("command","") if isinstance(ti,dict) else ""
for v in [d.get("hook_event_name"),d.get("notification_type"),d.get("message"),d.get("tool_name"),cmd,d.get("reason"),d.get("cwd"),d.get("session_id")]:
    print(re.sub(r"[\r\n]+"," ","" if v is None else str(v)))
' 2>/dev/null)" || fields=""
fi
[ -n "$fields" ] || exit 0
{ IFS= read -r event; IFS= read -r ntype; IFS= read -r message; IFS= read -r tool; IFS= read -r cmd; IFS= read -r reason; IFS= read -r cwd; IFS= read -r session; } <<EOF2
$fields
EOF2

cwd="${cwd:-$PWD}"
[ -d "$cwd" ] || exit 0
cd "$cwd" 2>/dev/null || exit 0
root="$(git rev-parse --show-toplevel 2>/dev/null)" || root="$PWD"

notify="${HC_NOTIFY:-}"
if [ -z "$notify" ] && [ -f "$plugin_root/scripts/tasks-path.sh" ]; then
  notify="$( . "$plugin_root/scripts/tasks-path.sh" 2>/dev/null && harness_yml_value "$root" notify )" || notify=""
fi
[ "$notify" = "orca" ] || exit 0

trunc() { printf '%s' "$1" | cut -c1-"$2"; }

case "$event" in
  Notification)
    [ -z "$ntype" ] || [ "$ntype" = "permission_prompt" ] || exit 0
    subject="権限の確認で止まっています"
    summary="$(trunc "${message:-権限の確認待ち}" 200)" ;;
  PermissionDenied)
    subject="分類器が止めました"
    what="${tool:-不明のツール}"
    [ -z "$cmd" ] || what="${what} $(trunc "$cmd" 60)"
    summary="${what}｜$(trunc "${reason:-理由なし}" 200)" ;;
  *) exit 0 ;;
esac

# 1 分に 2 通以上送らない（会話ごと）
sid="$(printf '%s' "${session:-nosession}" | tr -c 'A-Za-z0-9_-' '_')"
state_dir="${CLAUDE_PLUGIN_DATA:-$root/.claude/state}"
stamp="$state_dir/notify-attention-${sid}.last"
now="$(date +%s)"
if [ -f "$stamp" ]; then
  last="$(cat "$stamp" 2>/dev/null)" || last=""
  case "$last" in ''|*[!0-9]*) last=0 ;; esac
  [ $((now - last)) -ge 60 ] || exit 0
fi
mkdir -p "$state_dir" 2>/dev/null && printf '%s' "$now" > "$stamp" 2>/dev/null

notifier="$plugin_root/bin/hirai-notify"
[ -x "$notifier" ] || { echo "notify-attention: bin/hirai-notify が無い" >&2; exit 0; }
if ! "$notifier" waiting "$summary" --subject "$subject" >/dev/null 2>"${TMPDIR:-/tmp}/notify-attention.$$.err"; then
  echo "notify-attention: 送れなかった: $(head -1 "${TMPDIR:-/tmp}/notify-attention.$$.err" 2>/dev/null)" >&2
fi
rm -f "${TMPDIR:-/tmp}/notify-attention.$$.err" 2>/dev/null
exit 0
