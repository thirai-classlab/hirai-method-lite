#!/usr/bin/env bash
# PostToolUse(Bash) の hook: コーディネーターの会話が担当からの知らせ（orca orchestration check・hirai-notify）を受けた直後に、
# 進みの表（hirai-task load --changed）を、前回から段・担当・順番が動いたときだけ会話の材料に足す。
#
# 止めない: 操作の可否を変えず、常に exit 0。失敗・対象外・動きなしのときは 1 バイトも出さない（_meta.md 条 5 の context を注ぐだけの hook）。
# GitHub を叩かない: --cached で手元の控えだけ読む（控えが無い・古いときは出ない。取り直すのは hirai-task load）。
# コーディネーターか（HC_NOTIFY=off・Orca の端末・linked worktree でない・tasks: github-project・notify: orca）の判定は
# hirai-task の --if-coordinator が持つ。担当の会話・Orca の無い人・ほかのリポでは出ない。
set -uo pipefail

# 入力は先に読み切る（読まずに終わると、呼ぶ側の書き込みが途中で切れる）。そのあとで安い分かれ道（コーディネーターの印）を見る
input="$(cat 2>/dev/null)" || exit 0
[ "${HC_NOTIFY:-}" = "off" ] && [ -n "${ORCA_TERMINAL_HANDLE:-}" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

# 知らせを受けるコマンドのときだけ。cwd は会話のもの（1 行目 = 該当したか、2 行目 = cwd）
hit="$(printf '%s' "$input" | python3 -I -c '
import json, re, sys
try:
    d = json.load(sys.stdin)
    cmd = (d.get("tool_input") or {}).get("command") or ""
    ok = d.get("tool_name") == "Bash" and re.search(r"(^|[;&|\s])(orca\s+orchestration\s+check|\S*hirai-notify)\b", cmd)
    print("1" if ok else "0")
    print(d.get("cwd") or "")
except Exception:
    print("0")
' 2>/dev/null)" || exit 0
[ "${hit%%$'\n'*}" = "1" ] || exit 0
cwd="${hit#*$'\n'}"
[ -n "$cwd" ] && [ -d "$cwd" ] && CDPATH= builtin cd -- "$cwd" >/dev/null 2>&1

task="${CLAUDE_PLUGIN_ROOT:-$(CDPATH= builtin cd -- "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && builtin pwd -P)}/bin/hirai-task"
[ -x "$task" ] || exit 0
table="$("$task" load --changed --cached --if-coordinator 2>/dev/null)" || exit 0
[ -n "$table" ] || exit 0
printf '%s' "$table" | python3 -I -c '
import json, sys
text = "進みの表（前回から動いた所があります。そのまま貼り、言い換えない）:\n" + sys.stdin.read()
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}, ensure_ascii=False))
' 2>/dev/null || true
exit 0
