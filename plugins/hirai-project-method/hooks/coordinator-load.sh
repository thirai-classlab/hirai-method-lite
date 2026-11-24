#!/usr/bin/env bash
# PostToolUse(Bash) の hook: コーディネーターの会話が `orca orchestration check` で担当からの知らせを受けたとき、
# 「hirai-task load --changed を打つ」の 1 行を会話の材料に足す。表を出すかは、その load が前回と比べて決める
# （段・担当・順番が動いていなければ 1 行も出ない）。
#
# 止めない: 操作の可否を変えず、常に exit 0。失敗・対象外・知らせが無いときは 1 バイトも出さない（_meta.md 条 5 の context を注ぐだけの hook）。
# GitHub を叩かない・控えも読まない: PR の段は取り直さないと分からず、古い控えの表を「動いた」と見せないため。
# コーディネーターか（HC_NOTIFY=off・Orca の端末・linked worktree でない・tasks: github-project・notify: orca）の判定は
# `hirai-task is-coordinator` が持つ。担当の会話・Orca の無い人・ほかのリポでは出ない。
set -uo pipefail

# 入力は先に読み切る（読まずに終わると、呼ぶ側の書き込みが途中で切れる）。そのあとで安い分かれ道を見る
input="$(cat 2>/dev/null)" || exit 0
[ "${HC_NOTIFY:-}" = "off" ] && [ -n "${ORCA_TERMINAL_HANDLE:-}" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

# 1 行目 = 知らせを受けたか、2 行目 = cwd。知らせ = `orca orchestration check` の出力に message の id（msg_…）があるか、
# コマンドが `--ack`（受けた知らせの受領）を付けているとき（出力を要約する打ち方でも、受領は知らせがあったときだけ打つ）
hit="$(printf '%s' "$input" | python3 -I -c '
import json, re, sys
try:
    d = json.load(sys.stdin)
    cmd = (d.get("tool_input") or {}).get("command") or ""
    out = json.dumps(d.get("tool_response"), ensure_ascii=False)
    got = d.get("tool_name") == "Bash" and re.search(r"(^|[;&|\s])orca\s+orchestration\s+check(\s|$)", cmd) and (re.search(r"msg_[0-9a-z]", out) or re.search(r"\s--ack\b", cmd))
    print("1" if got else "0")
    print(d.get("cwd") or "")
except Exception:
    print("0")
' 2>/dev/null)" || exit 0
[ "${hit%%$'\n'*}" = "1" ] || exit 0
cwd="${hit#*$'\n'}"
[ -n "$cwd" ] && [ -d "$cwd" ] && CDPATH= builtin cd -- "$cwd" >/dev/null 2>&1

task="${CLAUDE_PLUGIN_ROOT:-$(CDPATH= builtin cd -- "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && builtin pwd -P)}/bin/hirai-task"
[ -x "$task" ] || exit 0
"$task" is-coordinator >/dev/null 2>&1 || exit 0
python3 -I -c '
import json
text = "担当からの知らせを受けました。`hirai-task load --changed` を打ち、出力があればそのまま貼ります（段・担当・順番が動いていなければ何も出ません）。"
print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}, ensure_ascii=False))
' 2>/dev/null || true
exit 0
