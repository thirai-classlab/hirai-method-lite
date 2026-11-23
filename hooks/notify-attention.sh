#!/usr/bin/env bash
# Notification(permission_prompt)・PermissionDenied・StopFailure の hook: 権限の確認の画面で止まった・auto mode の分類器が止めた・
# API エラー（時間切れ等）で手番が終わった、ことを Orca のコーディネーターへ知らせる（担当の会話はユーザーが画面を見に行くまで止まったままになるため）。
#
# `.claude/mode.yml` の `notify: orca`（env HC_NOTIFY が優先）のときだけ bin/hirai-notify waiting を呼ぶ。
# 判断は変えない: 標準出力に何も出さず常に exit 0。送れなかったときは stderr に 1 行だけ。
# 同じ会話から 1 分に 2 通以上送らない（最後に送った時刻を ${CLAUDE_PLUGIN_DATA} か <root>/.claude/state/ に置く）。
# StopFailure は件名に error の種類、本文に last_assistant_message の先頭 80 字だけを送る。
# tool_input の中身は送らない（秘密を含みうる）。Bash のコマンドは本文を送らず、tool_name と先頭のコマンド名だけ（`VAR=値` は `VAR=…`）。
# reason は `NAME=値` と 20 字以上の英数字の並びを伏せてから 80 字で切る。時刻の控えは、送れたときだけ書く。
# 入力を読む道具（jq か python3）が無いときは何もしない。
set -uo pipefail

plugin_root="$(CDPATH= builtin cd -- "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && builtin pwd -P)"
input="$(cat 2>/dev/null)" || input=""
[ -n "$input" ] || exit 0

# fields: event / ntype / message / tool / cmd / reason / cwd / session / error / last_assistant_message を 1 行ずつ（改行は空白に）
fields=""
if command -v jq >/dev/null 2>&1; then
  fields="$(printf '%s' "$input" | jq -r '[.hook_event_name, .notification_type, .message, .tool_name, (.tool_input.command // ""), .reason, .cwd, .session_id, .error, .last_assistant_message] | map((. // "") | tostring | gsub("[\r\n]+"; " ")) | .[]' 2>/dev/null)" || fields=""
elif command -v python3 >/dev/null 2>&1; then
  fields="$(printf '%s' "$input" | python3 -I -c '
import json,re,sys
try: d=json.load(sys.stdin)
except Exception: sys.exit(1)
ti=d.get("tool_input")
cmd=ti.get("command","") if isinstance(ti,dict) else ""
for v in [d.get("hook_event_name"),d.get("notification_type"),d.get("message"),d.get("tool_name"),cmd,d.get("reason"),d.get("cwd"),d.get("session_id"),d.get("error"),d.get("last_assistant_message")]:
    print(re.sub(r"[\r\n]+"," ","" if v is None else str(v)))
' 2>/dev/null)" || fields=""
fi
[ -n "$fields" ] || exit 0
{ IFS= read -r event; IFS= read -r ntype; IFS= read -r message; IFS= read -r tool; IFS= read -r cmd; IFS= read -r reason; IFS= read -r cwd; IFS= read -r session; IFS= read -r apierr; IFS= read -r lastmsg; } <<EOF2
$fields
EOF2

cwd="${cwd:-$PWD}"
[ -d "$cwd" ] || exit 0
CDPATH= builtin cd -- "$cwd" >/dev/null 2>&1 || exit 0
root="$(git rev-parse --show-toplevel 2>/dev/null)" || root="$PWD"

notify="${HC_NOTIFY:-}"
if [ -z "$notify" ] && [ -f "$plugin_root/scripts/tasks-path.sh" ]; then
  notify="$( . "$plugin_root/scripts/tasks-path.sh" 2>/dev/null && harness_yml_value "$PWD" notify )" || notify=""
fi
[ "$notify" = "orca" ] || exit 0

trunc() { printf '%s' "$1" | cut -c1-"$2"; }

# 先頭のコマンド名だけ（先頭の VAR=値 は VAR=… にして読み進める）。値・引数は送らない。
# 代入の語は、値が 1 語で閉じる "…"・'…'、または区切り（; & | < > ( ) { } 空白）・\・$・バッククォート・引用符を含まない並びのときだけ読む。
# それ以外（空白を含む引用・\＋空白・$'…'・$( ・&& 区切りなし）は中身を読まずに空を返す（呼ぶ側は道具の名前だけ送る）。
# コマンド名は ^[A-Za-z0-9_./-]+$ に当たる語だけ（当たらなければ空）
cmd_head() {
  printf '%s' "$1" | LC_ALL=C awk '
  function safe_value(v,   q) {
    q = substr(v, 1, 1)
    if (q == "\"") return (length(v) >= 2 && substr(v, length(v), 1) == "\"" && substr(v, 2, length(v) - 2) !~ /["\\$`]/)
    if (q == "\047") return (length(v) >= 2 && substr(v, length(v), 1) == "\047" && substr(v, 2, length(v) - 2) !~ /\047/)
    return (v !~ /[;&|<>(){}`$"\\\047]/)
  }
  {
    out = ""
    for (i = 1; i <= NF && i <= 8; i++) {
      w = $i
      if (w ~ /^[A-Za-z_][A-Za-z0-9_]*=/) {
        v = w; sub(/^[^=]*=/, "", v)
        if (!safe_value(v)) exit
        sub(/=.*/, "=…", w); out = out (out == "" ? "" : " ") w; continue
      }
      sub(/.*\//, "", w)
      if (w ~ /^[A-Za-z0-9_.\/-]+$/) { out = out (out == "" ? "" : " ") substr(w, 1, 40); printf "%s", out }
      exit
    }
  }'
}

# 秘密らしい並びを伏せる
redact() {
  printf '%s' "$1" | sed -E -e 's/[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]+/NAME=…/g' -e 's/(Bearer|Basic)[[:space:]]+[^[:space:]]+/\1 …/g' -e 's/[A-Za-z0-9_+\/-]{20,}/…/g'
}

case "$event" in
  Notification)
    [ -z "$ntype" ] || [ "$ntype" = "permission_prompt" ] || exit 0
    subject="権限の確認で止まっています"
    summary="$(trunc "${message:-権限の確認待ち}" 200)" ;;
  PermissionDenied)
    subject="分類器が止めました"
    what="${tool:-不明のツール}"
    if [ -n "$cmd" ]; then
      head_name="$(cmd_head "$cmd")"
      [ -z "$head_name" ] || what="${what} ${head_name}"
    fi
    summary="${what}｜$(trunc "$(redact "${reason:-理由なし}")" 80)" ;;
  StopFailure)
    subject="API エラーで止まりました（${apierr:-unknown}）"
    summary="$(trunc "${lastmsg:-本文なし}" 80)" ;;
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

notifier="$plugin_root/bin/hirai-notify"
[ -x "$notifier" ] || { echo "notify-attention: bin/hirai-notify が無い" >&2; exit 0; }
if "$notifier" waiting "$summary" --subject "$subject" >/dev/null 2>"${TMPDIR:-/tmp}/notify-attention.$$.err"; then
  mkdir -p "$state_dir" 2>/dev/null && printf '%s' "$now" > "$stamp" 2>/dev/null
else
  echo "notify-attention: 送れなかった: $(head -1 "${TMPDIR:-/tmp}/notify-attention.$$.err" 2>/dev/null)" >&2
fi
rm -f "${TMPDIR:-/tmp}/notify-attention.$$.err" 2>/dev/null
exit 0
