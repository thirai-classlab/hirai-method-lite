#!/usr/bin/env bash
# PreToolUse hook (matcher: Edit|Write|NotebookEdit|Bash): .claude/mode.yml の `worktree: block` のときだけ、
# Orca の worktree でない会話からの「リポの中の git に入るファイルの編集」と「git commit」を止める。
#
# 止める根拠: rules/_meta.md 条 5 の例外（並行の会話が同じ作業ツリーを触る事故を、編集の時点で止める）。
# 守るリポの決め方（会話の cwd ではなく、操作の対象で決める）:
#   Edit / Write / NotebookEdit … 対象ファイルの dir から git rev-parse --show-toplevel
#   Bash の git commit          … -C <dir>（--work-tree / --git-dir も）があればその dir、無ければ cwd
#                                 （cwd がリポでなければ CLAUDE_PROJECT_DIR）
#   決めたリポ（toplevel が HOME か HOME の祖先のものは「リポ」と読まず通す。対象が $HOME/.claude/ の下のときも通す）の mode.yml（項目ごとに 環境変数 HC_WORKTREE > そのリポ > ホーム > off）が block のときだけ止める。
# 止めないもの: 読み取り・リポの外（~/.claude の記憶の置き場など）・git に入らない場所（.gitignore 済み・
#   .tmp/・.claude/state/。外側のリポの下にあるときは外側の .tmp/・.claude/state/ の下だけ）・git switch / git checkout・git commit --dry-run / --help。
#   `worktree: off`（既定）と `warn` では何もしない。
# 早い exit: 環境変数 HC_WORKTREE・ホームの mode.yml・対象の dir とその祖先の mode.yml のどこにも block が無ければ、git も走査（awk）も
#   呼ばずに抜ける（git の toplevel は対象の dir かその祖先なので、git に聞かずに分かる。core.worktree でよそを指すリポと、submodule の git dir〔.git/modules/<名>〕の中からの操作は、その先の mode.yml を見ない）。
#   git -C・--git-dir・--work-tree のあるコマンドだけは、対象を知るために走査してから、同じ見方で git の前に抜ける。
# Orca の worktree の判定: 環境変数 ORCA_WORKTREE_ID があり、決めたリポの --git-dir と --git-common-dir が違い
#   （= リンクされた worktree）、ORCA_WORKTREE_ID が path を含むなら、その path の --git-common-dir が決めたリポと同じで、
#   決めたリポの toplevel が path そのもの（-ef = 同じ inode。macOS で大文字小文字だけ違う path も同じ）か
#   /.claude/worktrees/ の下（その worktree が作った subagent・Workflow の入れ子の worktree）であること。
#
# 通信しない。入力を読む道具（jq か python3）が無い・入力が読めないときは通す（fail-open。
# 止まらないことは scripts/orca-context.sh が会話の開始時に言う）。
# 制限は 30 秒（hooks.json の timeout）。超えると Claude Code が打ち切り、操作は通る（Claude Code の動き。ここでは変えない）。
set -uo pipefail
# 環境の GIT_DIR（linked worktree の git hook や rebase --exec から起きた会話）で、対象のリポを取り違えない
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_PREFIX 2>/dev/null

input=""
[ -t 0 ] || input="$(cat 2>/dev/null)" || input=""
[ -n "$input" ] || exit 0

# 環境変数が block 以外なら、どのリポでも止めない（値の決め方は環境変数が先。値の末尾の改行は落として読む）
if [ -n "${HC_WORKTREE:-}" ]; then
  HC_WORKTREE="$(printf '%s' "$HC_WORKTREE")"
  [ "$HC_WORKTREE" = block ] || exit 0
fi

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
    printf '%s' "$input" | python3 -I -c '
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

# may_block <mode.yml> -> rc 0 なら、worktree の値が block でありうる（外部コマンドを起こさない。値を決めるのは yml_val）
may_block() {
  local l
  [ -f "$1" ] && [ -r "$1" ] || return 1
  while IFS= read -r l || [ -n "$l" ]; do
    case "${l%%#*}" in *worktree:*block*) return 0 ;; esac
  done < "$1"
  return 1
}

# could_block <dir> ... -> rc 1 なら、環境変数・ホーム・<dir>（物理 path）とその祖先の mode.yml のどこにも block が無い
could_block() {
  local d
  [ "${HC_WORKTREE:-}" = block ] && return 0
  may_block "${HOME:-/nonexistent}/.claude/mode.yml" && return 0
  for d in "$@"; do
    while :; do
      may_block "$d/.claude/mode.yml" && return 0
      case "$d" in */*) d="${d%/*}" ;; *) break ;; esac
    done
  done
  return 1
}

# in_orca_wt <top> -> rc 0 なら Orca の worktree の会話（scripts/orca-context.sh に同じ判定の写しがある。直すときは両方）
in_orca_wt() {
  local top="$1" gd gc wc idpath
  [ -n "${ORCA_WORKTREE_ID:-}" ] || return 1
  gd="$(git -C "$top" rev-parse --path-format=absolute --git-dir 2>/dev/null)" || return 1
  gc="$(git -C "$top" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || return 1
  [ -n "$gd" ] && [ -n "$gc" ] && [ "$gd" != "$gc" ] || return 1
  idpath="${ORCA_WORKTREE_ID##*::}"
  case "$idpath" in
    /*)
      [ -d "$idpath" ] || return 1
      wc="$(git -C "$idpath" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || return 1
      [ -n "$wc" ] && [ "$wc" -ef "$gc" ] || return 1
      [ "$top" -ef "$idpath" ] && return 0
      case "$top" in */.claude/worktrees/*) return 0 ;; esac
      return 1 ;;
  esac
  return 0
}

emit_deny() {
  local r="$1"
  if [ "$HAVE_JQ" -eq 1 ]; then
    jq -n --arg r "$r" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  elif [ "$HAVE_PY" -eq 1 ]; then
    python3 -I -c 'import json,sys; print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":sys.argv[1]}}, ensure_ascii=False))' "$r"
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
  printf '%s' "$(CDPATH= builtin cd -- "$d" >/dev/null 2>&1 && builtin pwd -P)$rest"
}

# --- Bash: コマンド文字列から git commit を拾う ---------------------------------
# 出力: COMMIT<US>-C の列（GS 区切り）<US>--git-dir<US>--work-tree / SUB<US>中のコマンド（改行は RS）
# heredoc の本文を外し、引用符の中は区切りとして読まず、; && || | ( ) ` 改行で文を分ける。
# 文頭の then do else ! { time env VAR=.. command exec nohup xargs を読み飛ばし、/…/git・git の前置きの
# -C -c --git-dir --work-tree を読み、bash -c 'sh -c' eval の中は SUB として返す。
scan_commits() {
  LC_ALL=C awk '
  function emit_sub(t) { if (t != "") { gsub(/\n/, RS_, t); print "SUB" US t } }
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
  # buf の p 番目（"<<"の最初の <）から heredoc の区切りを読む。読めたら hd・hdstrip を決めて p を区切りの語の最後へ進める。
  # here-string（<<<）と、区切りの語が読めない << は p を 1 進めるだけ
  function try_heredoc(   j, dash, qc, w, ch) {
    if (substr(buf, p + 1, 1) != "<") return
    if (substr(buf, p + 2, 1) == "<") { p += 2; return }
    j = p + 2; dash = 0
    if (substr(buf, j, 1) == "-") { dash = 1; j++ }
    while (substr(buf, j, 1) == " " || substr(buf, j, 1) == "\t") j++
    qc = substr(buf, j, 1)
    w = ""
    if (qc == "\047" || qc == "\"") {
      j++
      while (j <= n && substr(buf, j, 1) != qc && substr(buf, j, 1) != "\n") { w = w substr(buf, j, 1); j++ }
      if (substr(buf, j, 1) == qc) j++
    } else {
      if (qc == "\\") j++
      while (j <= n) {
        ch = substr(buf, j, 1)
        if (ch == " " || ch == "\t" || ch == "\n" || ch == ";" || ch == "&" || ch == "|" || ch == "(" || ch == ")" || ch == "<" || ch == ">" || ch == "\047" || ch == "\"") break
        w = w ch; j++
      }
    }
    if (w == "") { p++; return }
    hd = w; hdstrip = dash; p = j - 1
  }
  # p が改行を指すとき、保留中の heredoc の本文を区切りの行まで読み飛ばす。p は区切りの行の末尾の改行へ進む
  function skip_body(   s, e, line, t) {
    while (1) {
      s = p + 1
      if (s > n) { hd = ""; return }
      e = index(substr(buf, s), "\n")
      if (e == 0) { line = substr(buf, s); p = n } else { line = substr(buf, s, e - 1); p = s + e - 1 }
      t = line
      if (hdstrip) sub(/^\t+/, "", t)
      if (t == hd || e == 0) { hd = ""; return }
    }
  }
  # p が算術の開きの "(" を指すとき（$(( の最初の ( か (( の最初の (）、対応する "))" まで読み飛ばして 1 を返す（p は最後の ")" へ進む）。
  # 算術の中の << は heredoc でなくシフトなので読まない。中の引用符・$'...'・$( ) は読む。式の外の ")" が "))" で閉じない
  # （例: ((a; b) 2>&1 | c)）・入力の終わりまで閉じないときは算術でないので、p を元に戻して 0 を返す（呼ぶ側が "(" として読み直す）
  function skip_arith(   st, d, c) {
    st = p; d = 0; p++
    while (p < n) {
      p++; c = substr(buf, p, 1)
      if (c == "\\") { p++; continue }
      if (c == "\047") { while (p < n) { p++; if (substr(buf, p, 1) == "\047") break } continue }
      if (c == "\"") { skip_dq(); continue }
      if (c == "$" && substr(buf, p + 1, 1) == "\047") { skip_ansi(); continue }
      if (c == "$" && substr(buf, p + 1, 1) == "(") { p++; skip_subst(); continue }
      if (c == "(") d++
      else if (c == ")") {
        if (d > 0) d--
        else if (substr(buf, p + 1, 1) == ")") { p++; return 1 }
        else break
      }
    }
    p = st
    return 0
  }
  # p が "(" を指すとき（$( の直後）、対応する ")" まで読み飛ばす。中の引用符・入れ子の $( ・heredoc の本文を数える。p は ")" へ進む。
  # 読み飛ばした中身は lastsub に残す（呼ぶ側が SUB として調べる）
  function skip_subst(   depth, c, s0, pv) {
    depth = 1; s0 = p + 1
    if (substr(buf, p + 1, 1) == "(") { if (skip_arith()) { lastsub = ""; return } }
    while (p < n) {
      p++; c = substr(buf, p, 1)
      if (c == "\\") { p++; continue }
      if (c == "\047") { while (p < n) { p++; if (substr(buf, p, 1) == "\047") break } continue }
      if (c == "\"") { skip_dq(); continue }
      if (c == "$" && substr(buf, p + 1, 1) == "\047") { skip_ansi(); continue }
      if (c == "$" && substr(buf, p + 1, 1) == "(") { p++; skip_subst(); continue }
      if (c == "#") {
        pv = substr(buf, p - 1, 1)
        if (pv == " " || pv == "\t" || pv == "\n" || pv == ";" || pv == "&" || pv == "|" || pv == "(") { while (p < n && substr(buf, p + 1, 1) != "\n") p++; continue }
      }
      if (c == "(") depth++
      else if (c == ")") { depth--; if (depth == 0) { lastsub = substr(buf, s0, p - s0); return } }
      else if (c == "<" && substr(buf, p + 1, 1) == "<") try_heredoc()
      else if (c == "\n" && hd != "") skip_body()
    }
  }
  # p が $ を指し次が \047 のとき（$'...'）、閉じの \047 まで読み飛ばす。\ の次の 1 字は閉じでない。p は閉じの \047 へ進む
  function skip_ansi(   d) {
    p++
    while (p < n) {
      p++; d = substr(buf, p, 1)
      if (d == "\\") { p++; continue }
      if (d == "\047") return
    }
  }
  # p が開きの " を指すとき、閉じの " まで読み飛ばす（中の $( ) も読む）。p は閉じの " へ進む
  function skip_dq(   c) {
    while (p < n) {
      p++; c = substr(buf, p, 1)
      if (c == "\\") { p++; continue }
      if (c == "\"") return
      if (c == "$" && substr(buf, p + 1, 1) == "(") { p++; skip_subst() }
    }
  }
  BEGIN { US = sprintf("%c", 31); GS = sprintf("%c", 29); RS_ = sprintf("%c", 30); hd = ""; hdstrip = 0; buf = "" }
  { buf = buf $0 "\n" }
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
        } else if (c == "$" && substr(buf, p + 1, 1) == "(") { word = word "$("; p++; lastsub = ""; skip_subst(); emit_sub(lastsub) }
        else word = word c
        continue
      }
      if (c == "\047") { q = 1; inword = 1 }
      else if (c == "\"") { q = 2; inword = 1 }
      else if (c == "\\") {
        d = substr(buf, p + 1, 1); p++
        if (d != "\n") { word = word d; inword = 1 }
      }
      else if (c == "$" && substr(buf, p + 1, 2) == "((") {
        st = p; p++
        if (skip_arith()) { word = word "0"; inword = 1 }
        else { p = st; word = word "$"; inword = 1 }
      }
      else if (c == "$" && substr(buf, p + 1, 1) == "\047") { skip_ansi(); word = word "x"; inword = 1 }
      else if (c == "(" && !inword && substr(buf, p + 1, 1) == "(" && (nt == 0 || tok[nt] ~ /^(if|while|until|for|then|do|else|elif|!)$/)) { st = p; if (!skip_arith()) p = st; end_seg() }
      else if (c == "#" && !inword) { while (p < n && substr(buf, p + 1, 1) != "\n") p++ }
      else if (c == "<" && substr(buf, p + 1, 1) == "<") { flush_word(); try_heredoc() }
      else if (c == "\n") { end_seg(); if (hd != "") skip_body() }
      else if (c == ";" || c == "|" || c == "&" || c == "(" || c == ")" || c == "`") end_seg()
      else if (c == " " || c == "\t") flush_word()
      else { word = word c; inword = 1 }
    }
    end_seg()
  }'
}

# outer_ignored <リポの toplevel> [<toplevel からの相対 path>] -> rc 0 なら、そのリポは外側のリポの .tmp/ か .claude/state/ の下
# にある（設計 §6。外側の .gitignore は見ない）。.tmp/ に作った worktree・clone は外側の git に入らないので止めない
outer_ignored() {
  local cur="$1" rel="${2:-}" parent otop oprefix
  while [ "$cur" != / ]; do
    parent="$(dirname "$cur")"
    otop="$(git -C "$parent" rev-parse --show-toplevel 2>/dev/null)" || return 1
    [ -n "$otop" ] && [ "$otop" != "$cur" ] || return 1   # 絶対 path の GIT_DIR があると同じ toplevel を返し続ける
    oprefix="$(git -C "$parent" rev-parse --show-prefix 2>/dev/null)" || return 1
    rel="${oprefix}$(basename "$cur")${rel:+/$rel}"
    case "$rel" in
      .tmp|.tmp/*|.claude/state|.claude/state/*) return 0 ;;
    esac
    cur="$otop"
  done
  return 1
}

# phys <dir> -> 物理 path（解けなければ <dir> のまま）
phys() {
  local d="$1" p
  p="$(CDPATH= builtin cd -P -- "$d" >/dev/null 2>&1 && builtin pwd -P)" || p="$d"   # -P: git -C と同じく、symlink の先の .. を先の親と読む
  printf '%s' "$p"
}

# home_scope <top> -> rc 0 なら、top が HOME か HOME の祖先（ホームの git を「リポ」と読まない。scripts/tasks-path.sh の harness_top と同じ規則）
home_scope() {
  local t h
  t="$(phys "$1")"
  h="${HOME:-}"; [ -n "$h" ] || return 1
  h="$(phys "$h")"
  [ "$t" = / ] && return 0
  [ "$t" = "$h" ] && return 0
  case "$h/" in "$t"/*) return 0 ;; esac
  return 1
}

# under_home_claude <path> -> rc 0 なら $HOME/.claude/ の下（記憶・計画の置き場。止めない）
under_home_claude() {
  local h
  h="${HOME:-}"; [ -n "$h" ] || return 1
  h="$(phys "$h")/.claude"
  case "$1" in "$h"|"$h"/*) return 0 ;; esac
  h="$(phys "$h")"   # ~/.claude が symlink のとき
  case "$1" in "$h"|"$h"/*) return 0 ;; esac
  return 1
}

# check_commit <-C の列> <git-dir> <work-tree> <基の dir> <既定の dir>
check_commit() {
  local cdl="$1" gdir="$2" wtree="$3" base="$4" dflt="$5" dir top c a oldifs
  dir="$dflt"
  local dirset=0
  if [ -n "$wtree" ]; then
    dir="$(abs_path "$wtree" "$base")" || return 0
    dirset=1
  elif [ -n "$gdir" ]; then
    a="$(abs_path "$gdir" "$base")" || return 0
    case "$a" in */.git) dir="$(dirname "$a")"; dirset=1 ;; esac
  fi
  # git は -C を cwd から解く。既定の dir（CLAUDE_PROJECT_DIR）は -C も --work-tree も --git-dir も無いときだけ使う
  [ -n "$cdl" ] && [ "$dirset" -eq 0 ] && dir="$base"
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
  could_block "$(phys "$dir")" || return 0
  under_home_claude "$(phys "$dir")" && return 0
  top="$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null)" || return 0
  [ -n "$top" ] || return 0
  home_scope "$top" && return 0
  [ "$(repo_mode "$top")" = "block" ] || return 0
  in_orca_wt "$top" && return 0
  outer_ignored "$top" && return 0
  deny "Orca の worktree でない会話からの git commit（${top}）は止めています。"
}

check_command() {
  local text="$1" depth="$2" kind a b c d line base seen=""
  base="$cwd"
  while IFS=$'\037' read -r kind a b c d; do
    case "$kind" in
      COMMIT) check_commit "$a" "$b" "$c" "$base" "$dflt" ;;
      SUB)
        # SUB も commit の字を含むときだけ調べる（$( ) を何百個つないでも timeout に届かない）
        if [ "$depth" -lt 3 ]; then
          case "$a" in *commit*) ;; *) continue ;; esac
          case "$seen" in *$'\037'"$a"$'\037'*) continue ;; esac   # 同じ中身は 1 回だけ調べる
          seen="${seen}"$'\037'"${a}"$'\037'
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
    could_block "$fdir" || exit 0
    top="$(git -C "$fdir" rev-parse --show-toplevel 2>/dev/null)" || exit 0
    [ -n "$top" ] || exit 0
    top="$(CDPATH= builtin cd -- "$top" >/dev/null 2>&1 && builtin pwd -P)" || exit 0
    home_scope "$top" && exit 0
    under_home_claude "$abs" && exit 0
    [ "$(repo_mode "$top")" = "block" ] || exit 0
    # リポの中かどうかと相対 path は、path の文字列の比較でなく git に聞く（macOS の既定の APFS は大文字小文字を区別しない）
    prefix="$(git -C "$fdir" rev-parse --show-prefix 2>/dev/null)" || exit 0
    rest="${abs#"$fdir"}"; rest="${rest#/}"
    rel="${prefix}${rest}"
    rel="${rel%/}"
    case "$rel" in
      .git|.git/*) exit 0 ;;            # git の内部は対象外
      .tmp|.tmp/*|.claude/state|.claude/state/*) exit 0 ;;  # .gitignore に無くても止めない（設計 §6）
    esac
    in_orca_wt "$top" && exit 0
    outer_ignored "$top" "$rel" && exit 0
    # 無視されるファイルは git に入らないので止めない。
    if [ -n "$rel" ] && git -C "$top" check-ignore -q -- "$rel" 2>/dev/null; then
      exit 0
    fi
    deny "Orca の worktree でない会話から、git に入るファイル（${rel}）は編集できません。"
    ;;
  Bash)
    cmd="$(jget tool_input.command)"
    [ -n "$cmd" ] || exit 0
    # commit の字がコマンドに無ければ git commit ではない（mode.yml も走査も引かずに抜ける。off のリポの Bash に遅れを足さない）
    case "$cmd" in *commit*) ;; *) exit 0 ;; esac
    # 既定の dir（-C・--git-dir・--work-tree の無い commit の対象）は cwd。リポでなければ CLAUDE_PROJECT_DIR
    dflt="$cwd"
    if could_block "$(phys "$cwd")" "$(phys "${CLAUDE_PROJECT_DIR:-$cwd}")"; then
      git -C "$cwd" rev-parse --show-toplevel >/dev/null 2>&1 || dflt="${CLAUDE_PROJECT_DIR:-$cwd}"
    else
      # 対象をほかの dir へ向ける字が無ければ走査もしない（引用符・バックスラッシュ・改行で割った形も拾う）。
      # LC_ALL=C: macOS の tr は locale で読めないバイトに当たると、そこで出力を切る（EUC 系の locale で -C を見落とす）
      case "$(printf '%s' "$cmd" | LC_ALL=C tr -d '"\047\\\n')" in *-C*|*git-dir*|*work-tree*) ;; *) exit 0 ;; esac
    fi
    check_command "$cmd" 0
    exit 0
    ;;
esac
exit 0
