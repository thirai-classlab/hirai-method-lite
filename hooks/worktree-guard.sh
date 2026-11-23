#!/usr/bin/env bash
# PreToolUse hook (matcher: Edit|Write|NotebookEdit|Bash): .claude/mode.yml の `worktree: block` のときだけ、
# Orca の worktree でない会話からの「リポの中の git に入るファイルの編集」と「git commit」を止める。
#
# 止める根拠: rules/_meta.md 条 5 の例外（並行の会話が同じ作業ツリーを触る事故を、編集の時点で止める）。
# 守るリポの決め方（会話の cwd ではなく、操作の対象で決める）:
#   Edit / Write / NotebookEdit … 対象ファイルの dir から git rev-parse --show-toplevel
#   Bash の git commit          … -C <dir>（--work-tree / --git-dir も）があればその dir、無ければ cwd
#                                 （cwd がリポでなければ CLAUDE_PROJECT_DIR）
#   決めたリポの mode.yml（項目ごとに 環境変数 HC_WORKTREE > そのリポ > ホーム > off）が block のときだけ止める。
# 止めないもの: 読み取り・リポの外（~/.claude の記憶の置き場など）・git に入らない場所（.gitignore 済み・
#   .tmp/・.claude/state/）・git switch / git checkout・git commit --dry-run / --help。
#   `worktree: off`（既定）と `warn` では何もしない。
# Orca の worktree の判定: 環境変数 ORCA_WORKTREE_ID があり、決めたリポの --git-dir と --git-common-dir が違い
#   （= リンクされた worktree）、ORCA_WORKTREE_ID が path を含むならそれがそのリポの中を指すこと。
#
# 通信しない。入力を読む道具（jq か python3）が無い・入力が読めないときは通す（fail-open。
# 止まらないことは scripts/orca-context.sh が会話の開始時に言う）。
set -uo pipefail

input=""
[ -t 0 ] || input="$(cat 2>/dev/null)" || input=""
[ -n "$input" ] || exit 0

HAVE_JQ=0; HAVE_PY=0
command -v jq >/dev/null 2>&1 && HAVE_JQ=1
command -v python3 >/dev/null 2>&1 && HAVE_PY=1
[ "$HAVE_JQ" -eq 1 ] || [ "$HAVE_PY" -eq 1 ] || exit 0

# jget <a.b> [<c.d> ...] -> 最初に空でない値（jq が無ければ python3）。読めなければ空。
jget() {
  if [ "$HAVE_JQ" -eq 1 ]; then
    local expr="" p
    for p in "$@"; do expr="${expr}.${p} // "; done
    printf '%s' "$input" | jq -r "(${expr}empty) | strings" 2>/dev/null
  else
    printf '%s' "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for p in sys.argv[1:]:
    v = d
    for k in p.split("."):
        v = v.get(k) if isinstance(v, dict) else None
    if isinstance(v, str) and v:
        print(v, end="")
        break
' "$@" 2>/dev/null
  fi
}

tool="$(jget tool_name)"
cwd="$(jget cwd)"
[ -n "$cwd" ] && [ -d "$cwd" ] || cwd="${CLAUDE_PROJECT_DIR:-$PWD}"

# yml_val <file> <キー> -> 値（引用符と行末のコメントを外す）。無ければ空。
yml_val() {
  [ -f "$1" ] || return 0
  sed -n "s/^[[:space:]]*${2}:[[:space:]]*//p" "$1" 2>/dev/null | head -1 \
    | sed -e 's/[[:space:]]*#.*$//' -e "s/^[\"']//" -e "s/[\"'][[:space:]]*\$//" -e 's/[[:space:]]*$//'
}

# repo_mode <top> -> worktree の値。環境変数 > そのリポの mode.yml > ホームの mode.yml > off（空）
repo_mode() {
  local v="${HC_WORKTREE:-}"
  [ -n "$v" ] || v="$(yml_val "$1/.claude/mode.yml" worktree)"
  [ -n "$v" ] || v="$(yml_val "${HOME:-/nonexistent}/.claude/mode.yml" worktree)"
  printf '%s' "$v"
}

# in_orca_wt <top> -> rc 0 なら Orca の worktree の会話
in_orca_wt() {
  local top="$1" gd gc idpath real
  [ -n "${ORCA_WORKTREE_ID:-}" ] || return 1
  gd="$(git -C "$top" rev-parse --path-format=absolute --git-dir 2>/dev/null)" || return 1
  gc="$(git -C "$top" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || return 1
  [ -n "$gd" ] && [ -n "$gc" ] && [ "$gd" != "$gc" ] || return 1
  idpath="${ORCA_WORKTREE_ID##*::}"
  case "$idpath" in
    /*)
      real="$(cd "$idpath" 2>/dev/null && pwd -P)" || return 1
      case "$real" in "$top"|"$top"/*) return 0 ;; esac
      return 1 ;;
  esac
  return 0
}

emit_deny() {
  local r="$1"
  if [ "$HAVE_JQ" -eq 1 ]; then
    jq -n --arg r "$r" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  elif [ "$HAVE_PY" -eq 1 ]; then
    python3 -c 'import json,sys; print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":sys.argv[1]}}, ensure_ascii=False))' "$r"
  fi
}

deny() {
  emit_deny "$1 このリポは .claude/mode.yml で worktree: block です。Orca の worktree で作業してください: orca worktree create --name <名前> --base-branch <基の branch> （作った worktree の会話で同じ操作をする）。別のリポへの commit は git -C <dir> commit で（cd では追えません）"
  exit 0
}

# abs_path <path> <基の dir> [literal] -> 絶対 path（~ は HOME に）。
# Bash の -C の値など、シェルが展開しうる path は変数・コマンド置換を含むなら rc 1。
# literal を渡すと（Edit・Write の file_path は字義どおりの path）`$` や `` ` `` を含んでも読む（users.$id.tsx）。
abs_path() {
  local p="$1" base="$2"
  if [ "${3:-}" != "literal" ]; then
    case "$p" in *'$'*|*'`'*) return 1 ;; esac
  fi
  case "$p" in "~") p="${HOME:-/}" ;; "~/"*) p="${HOME:-}${p#"~"}" ;; esac
  case "$p" in /*) ;; *) p="$base/$p" ;; esac
  printf '%s' "$p"
}

# 実在する祖先まで物理 path に直す（macOS の /tmp → /private/tmp などの食い違いを無くす）
resolve_path() {
  local p="$1" rest="" d
  d="$p"
  while [ ! -d "$d" ]; do
    rest="/$(basename "$d")$rest"
    d="$(dirname "$d")"
  done
  printf '%s' "$(cd "$d" 2>/dev/null && pwd -P)$rest"
}

# --- Bash: コマンド文字列から git commit を拾う ---------------------------------
# 出力: COMMIT<US>-C の列（GS 区切り）<US>--git-dir<US>--work-tree / SUB<US>中のコマンド（改行は RS）
# heredoc の本文を外し、引用符の中は区切りとして読まず、; && || | ( ) ` 改行で文を分ける。
# 文頭の then do else ! { time env VAR=.. command exec nohup xargs を読み飛ばし、/…/git・git の前置きの
# -C -c --git-dir --work-tree を読み、bash -c 'sh -c' eval の中は SUB として返す。
scan_commits() {
  awk '
  function flush_word() { if (inword) { nt++; tok[nt] = word; word = ""; inword = 0 } }
  function end_seg() { flush_word(); if (nt > 0) analyze(); nt = 0 }
  function base_of(s) { sub(/.*\//, "", s); return s }
  function analyze(   i, a, b, j, nc, cdl, gd, wt, k, dry, rest, sc) {
    i = 1
    while (i <= nt) {
      a = tok[i]
      if (a == "!" || a == "then" || a == "do" || a == "else" || a == "elif" || a == "if" || a == "while" || a == "until" || a == "{" || a == "time" || a == "command" || a == "builtin" || a == "exec" || a == "nohup" || a == "env" || a == "xargs") {
        i++
        if (a == "env" || a == "xargs" || a == "time" || a == "command") { while (i <= nt && substr(tok[i], 1, 1) == "-") i++ }
        continue
      }
      if (a ~ /^[A-Za-z_][A-Za-z0-9_]*=/) { i++; continue }
      break
    }
    if (i > nt) return
    b = base_of(tok[i])
    if (b == "git") {
      j = i + 1; cdl = ""; gd = ""; wt = ""
      while (j <= nt) {
        a = tok[j]
        if (a == "-C") { cdl = (cdl == "" ? tok[j+1] : cdl GS tok[j+1]); j += 2 }
        else if (a == "-c" || a == "--namespace" || a == "--exec-path") { j += 2 }
        else if (a == "--git-dir") { gd = tok[j+1]; j += 2 }
        else if (a ~ /^--git-dir=/) { gd = substr(a, 11); j++ }
        else if (a == "--work-tree") { wt = tok[j+1]; j += 2 }
        else if (a ~ /^--work-tree=/) { wt = substr(a, 13); j++ }
        else if (substr(a, 1, 1) == "-") { j++ }
        else break
      }
      if (tok[j] == "commit") {
        dry = 0
        for (k = j + 1; k <= nt; k++) if (tok[k] == "--dry-run" || tok[k] == "--help" || tok[k] == "-h") dry = 1
        if (!dry) print "COMMIT" US cdl US gd US wt
      }
    } else if (b == "bash" || b == "sh" || b == "zsh" || b == "dash" || b == "ksh") {
      for (j = i + 1; j <= nt; j++) {
        if (tok[j] ~ /^-[A-Za-z]*c[A-Za-z]*$/ && j < nt) { sc = tok[j+1]; gsub(/\n/, RS_, sc); print "SUB" US sc; break }
      }
    } else if (b == "eval") {
      rest = ""
      for (j = i + 1; j <= nt; j++) rest = rest (rest == "" ? "" : " ") tok[j]
      gsub(/\n/, RS_, rest); print "SUB" US rest
    }
  }
  # 行の中で、引用符の外・$(( )) の外にある << の区切りの語を返す（先頭 - は <<- の印）。無ければ空
  function heredoc_delim(line,   n, i, c, d, q, ar, j, w, dash, qc) {
    n = length(line); q = 0; ar = 0
    for (i = 1; i <= n; i++) {
      c = substr(line, i, 1)
      if (q == 1) { if (c == "\047") q = 0; continue }
      if (q == 2) { if (c == "\\") i++; else if (c == "\"") q = 0; continue }
      if (c == "\\") { i++; continue }
      if (c == "\047") { q = 1; continue }
      if (c == "\"") { q = 2; continue }
      if (c == "$" && substr(line, i + 1, 2) == "((") { ar = 2; i += 2; continue }
      if (ar > 0) { if (c == "(") ar++; else if (c == ")") ar--; continue }
      if (c == "<" && substr(line, i + 1, 1) == "<") {
        if (substr(line, i + 2, 1) == "<") { i += 2; continue }
        j = i + 2; dash = ""
        if (substr(line, j, 1) == "-") { dash = "-"; j++ }
        while (substr(line, j, 1) == " " || substr(line, j, 1) == "\t") j++
        qc = substr(line, j, 1)
        if (qc == "\047" || qc == "\"") j++
        w = ""
        while (j <= n && substr(line, j, 1) ~ /[A-Za-z0-9_]/) { w = w substr(line, j, 1); j++ }
        if (w ~ /^[A-Za-z_]/) return dash w
        i++
      }
    }
    return ""
  }
  BEGIN { US = sprintf("%c", 31); GS = sprintf("%c", 29); RS_ = sprintf("%c", 30); hd = "" }
  {
    line = $0
    if (hd != "") {
      t = line
      if (hdstrip) sub(/^\t+/, "", t)
      if (t == hd) hd = ""
      next
    }
    buf = buf line "\n"
    m = heredoc_delim(line)
    if (m != "") { hdstrip = (m ~ /^-/); sub(/^-/, "", m); hd = m }
  }
  END {
    n = length(buf); q = 0; word = ""; inword = 0; nt = 0
    for (p = 1; p <= n; p++) {
      c = substr(buf, p, 1)
      if (q == 1) { if (c == "\047") q = 0; else word = word c; continue }
      if (q == 2) {
        if (c == "\"") q = 0
        else if (c == "\\") {
          d = substr(buf, p + 1, 1)
          if (d == "\n") { p++ }
          else if (d == "\"" || d == "\\" || d == "$" || d == "`") { word = word d; p++ }
          else word = word c
        } else word = word c
        continue
      }
      if (c == "\047") { q = 1; inword = 1 }
      else if (c == "\"") { q = 2; inword = 1 }
      else if (c == "\\") {
        d = substr(buf, p + 1, 1); p++
        if (d != "\n") { word = word d; inword = 1 }
      }
      else if (c == "#" && !inword) { while (p < n && substr(buf, p + 1, 1) != "\n") p++ }
      else if (c == ";" || c == "\n" || c == "|" || c == "&" || c == "(" || c == ")" || c == "`") end_seg()
      else if (c == " " || c == "\t") flush_word()
      else { word = word c; inword = 1 }
    }
    end_seg()
  }'
}

# check_commit <-C の列> <git-dir> <work-tree> <基の dir> <既定の dir>
check_commit() {
  local cdl="$1" gdir="$2" wtree="$3" base="$4" dflt="$5" dir top c a oldifs
  dir="$dflt"
  if [ -n "$wtree" ]; then
    dir="$(abs_path "$wtree" "$base")" || return 0
  elif [ -n "$gdir" ]; then
    a="$(abs_path "$gdir" "$base")" || return 0
    case "$a" in */.git) dir="$(dirname "$a")" ;; esac
  fi
  if [ -n "$cdl" ]; then
    oldifs="$IFS"; IFS=$'\035'
    for c in $cdl; do
      IFS="$oldifs"
      dir="$(abs_path "$c" "$dir")" || return 0
      IFS=$'\035'
    done
    IFS="$oldifs"
  fi
  [ -d "$dir" ] || return 0
  top="$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null)" || return 0
  [ -n "$top" ] || return 0
  [ "$(repo_mode "$top")" = "block" ] || return 0
  in_orca_wt "$top" && return 0
  deny "Orca の worktree でない会話からの git commit（${top}）は止めています。"
}

check_command() {
  local text="$1" depth="$2" kind a b c d line base dflt
  base="$cwd"
  dflt="$cwd"
  git -C "$cwd" rev-parse --show-toplevel >/dev/null 2>&1 || dflt="${CLAUDE_PROJECT_DIR:-$cwd}"
  while IFS=$'\037' read -r kind a b c d; do
    case "$kind" in
      COMMIT) check_commit "$a" "$b" "$c" "$base" "$dflt" ;;
      SUB)
        if [ "$depth" -lt 3 ]; then
          line="$(printf '%s' "$a" | tr '\036' '\n')"
          check_command "$line" $((depth + 1))
        fi ;;
    esac
  done <<EOF_SCAN
$(printf '%s\n' "$text" | scan_commits)
EOF_SCAN
}

case "$tool" in
  Edit|Write|NotebookEdit)
    f="$(jget tool_input.file_path tool_input.notebook_path)"
    [ -n "$f" ] || exit 0
    abs="$(abs_path "$f" "$cwd" literal)" || exit 0
    abs="$(resolve_path "$abs")"
    fdir="$abs"
    while [ ! -d "$fdir" ]; do fdir="$(dirname "$fdir")"; done
    top="$(git -C "$fdir" rev-parse --show-toplevel 2>/dev/null)" || exit 0
    [ -n "$top" ] || exit 0
    top="$(cd "$top" 2>/dev/null && pwd -P)" || exit 0
    [ "$(repo_mode "$top")" = "block" ] || exit 0
    case "$abs" in
      "$top"/.git|"$top"/.git/*) exit 0 ;;            # git の内部は対象外
      "$top"/.tmp/*|"$top"/.claude/state/*) exit 0 ;;  # .gitignore に無くても止めない（設計 §6）
      "$top"/*) ;;
      *) exit 0 ;;
    esac
    in_orca_wt "$top" && exit 0
    # 無視されるファイルは git に入らないので止めない。
    if git -C "$top" check-ignore -q -- "$abs" 2>/dev/null; then
      exit 0
    fi
    deny "Orca の worktree でない会話から、git に入るファイル（${abs#"$top"/}）は編集できません。"
    ;;
  Bash)
    cmd="$(jget tool_input.command)"
    [ -n "$cmd" ] || exit 0
    check_command "$cmd" 0
    exit 0
    ;;
esac
exit 0
