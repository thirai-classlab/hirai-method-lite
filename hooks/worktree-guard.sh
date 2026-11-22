#!/usr/bin/env bash
# PreToolUse hook (matcher: Edit|Write|NotebookEdit|Bash): .claude/mode.yml の `worktree: block` のときだけ、
# Orca の worktree でない会話からの「リポの中の git に入るファイルの編集」と「git commit」を止める。
#
# 止める根拠: rules/_meta.md 条 5 の例外（並行の会話が同じ作業ツリーを触る事故を、編集の時点で止める）。
# 止めるもの : Edit / Write / NotebookEdit の対象が、リポの中にあり git に無視されないファイル。
#              Bash の `git commit`。
# 止めないもの: 読み取り・リポの外（~/.claude の記憶の置き場など）・git に入らない場所（.tmp/ など）・
#              git switch / git checkout。`worktree: off`（既定）と `warn` では何もしない。
# Orca の worktree の判定: 環境変数 ORCA_WORKTREE_ID があり、かつ
#              git rev-parse の --git-dir と --git-common-dir が違う（= リンクされた worktree）。
#
# 通信しない。判定に使う道具（jq・git）が無い・入力が読めないときは通す（fail-open）。
set -uo pipefail

input=""
[ -t 0 ] || input="$(cat 2>/dev/null)" || input=""
[ -n "$input" ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

tool="$(printf '%s' "$input" | jq -r '.tool_name // empty' 2>/dev/null)"
cwd="$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)"
[ -n "$cwd" ] && [ -d "$cwd" ] || cwd="${CLAUDE_PROJECT_DIR:-$PWD}"

# 導入先リポの root（mode.yml を読む場所）。git のリポでなければ何もしない。
top="$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null)" || exit 0
[ -n "$top" ] || exit 0

# worktree の値: env HC_WORKTREE > プロジェクトの mode.yml > ホームの mode.yml > off
# 値の読み方は土台の harness_yml_value（tasks-path.sh）に寄せる。読めなければ空（= off）
yml_get() {
  local lib; lib="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)/scripts/tasks-path.sh"
  [ -f "$lib" ] || return 0
  ( . "$lib" 2>/dev/null && harness_yml_value "${CLAUDE_PROJECT_DIR:-$top}" "$1" ) 2>/dev/null || true
}
wt="${HC_WORKTREE:-$(yml_get worktree)}"
[ "$wt" = "block" ] || exit 0

# Orca の worktree の会話なら通す。
if [ -n "${ORCA_WORKTREE_ID:-}" ]; then
  gd="$(git -C "$cwd" rev-parse --path-format=absolute --git-dir 2>/dev/null)" || gd=""
  gc="$(git -C "$cwd" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || gc=""
  if [ -n "$gd" ] && [ -n "$gc" ] && [ "$gd" != "$gc" ]; then
    exit 0
  fi
fi

deny() {
  local why="$1" reason
  reason="$why このリポは .claude/mode.yml で worktree: block です。Orca の worktree で作業してください: orca worktree create --name <名前> --base-branch <基の branch> （作った worktree の会話で同じ操作をする）"
  jq -n --arg r "$reason" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
}

# path を実在する祖先まで物理 path に直す（macOS の /tmp → /private/tmp などの食い違いを無くす）。
resolve_path() {
  local p="$1" rest="" d
  case "$p" in /*) ;; *) p="$cwd/$p" ;; esac
  d="$p"
  while [ ! -d "$d" ]; do
    rest="/$(basename "$d")$rest"
    d="$(dirname "$d")"
  done
  printf '%s' "$(cd "$d" 2>/dev/null && pwd -P)$rest"
}

case "$tool" in
  Edit|Write|NotebookEdit)
    f="$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' 2>/dev/null)"
    [ -n "$f" ] || exit 0
    abs="$(resolve_path "$f")"
    real_top="$(cd "$top" 2>/dev/null && pwd -P)"
    case "$abs" in
      "$real_top"/.git|"$real_top"/.git/*) exit 0 ;;   # git の内部は対象外
      "$real_top"/*) ;;
      *) exit 0 ;;                                      # リポの外は止めない
    esac
    # 無視されるファイル（.tmp/ など）は git に入らないので止めない。
    if git -C "$real_top" check-ignore -q -- "$abs" 2>/dev/null; then
      exit 0
    fi
    deny "Orca の worktree でない会話から、git に入るファイル（${abs#"$real_top"/}）は編集できません。"
    ;;
  Bash)
    cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)"
    [ -n "$cmd" ] || exit 0
    if printf '%s' "$cmd" | grep -Eq '(^|[;&|(`]|&&)[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]+[[:space:]]+)*git([[:space:]]+(-C|-c)[[:space:]]+[^[:space:]]+|[[:space:]]+--[a-z-]+(=[^[:space:]]+)?)*[[:space:]]+commit([[:space:]]|$)'; then
      deny "Orca の worktree でない会話からの git commit は止めています。"
    fi
    exit 0
    ;;
esac
exit 0
