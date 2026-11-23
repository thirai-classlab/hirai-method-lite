#!/usr/bin/env bash
# 会話の開始時に出す Orca 関連の行を標準出力に出す（hooks/session-start.sh が 1 行で呼ぶ）。
#   worktree: warn|block で Orca の worktree でないとき … 警告 1 行
#   notify: orca のとき … 知らせ方 1 行（開始時の表示を 5 行以内に収めるため 1 行にまとめる）
# どちらも off（既定）なら 1 バイトも出さない。常に exit 0（fail-open）。
# worktree: block でも jq と python3 が無いと guard は入力を読めず止まらない。そのときは「止まりません」と言う（条 9）。
set -uo pipefail

# phys <dir> -> 物理 path（解けなければ <dir> のまま）
phys() {
  local p
  p="$(CDPATH= builtin cd -- "$1" >/dev/null 2>&1 && builtin pwd -P)" || p="$1"
  printf '%s' "$p"
}

# root は会話のリポの toplevel（サブディレクトリで開いても hooks/worktree-guard.sh・bin/hirai-notify と同じ mode.yml を読む）。
# toplevel が HOME か HOME の祖先なら git でないものとして dir のまま（scripts/tasks-path.sh の harness_top と同じ規則）。
# in_repo=1 は「guard が守るリポの中」（toplevel があり HOME か HOME の祖先でない）。
root="$(phys "${CLAUDE_PROJECT_DIR:-$PWD}")"
in_repo=0
if top="$(git -C "$root" rev-parse --show-toplevel 2>/dev/null)" && [ -n "$top" ]; then
  top="$(phys "$top")"
  home="$(phys "${HOME:-/nonexistent}")"
  case "$home/" in
    "$top"/*) ;;
    *) [ "$top" = / ] || { root="$top"; in_repo=1; } ;;
  esac
fi

# outer_ignored <リポの toplevel> -> rc 0 なら、外側のリポの .tmp/ か .claude/state/ の下にある（外側が無くなるまで上へ。
# hooks/worktree-guard.sh の outer_ignored と同じ判定。直すときは両方）。guard が止めない場所では「止まります」と言わない
outer_ignored() {
  local cur="$1" rel="" parent otop oprefix
  while :; do
    parent="$(dirname "$cur")"
    otop="$(git -C "$parent" rev-parse --show-toplevel 2>/dev/null)" || return 1
    [ -n "$otop" ] || return 1
    oprefix="$(git -C "$parent" rev-parse --show-prefix 2>/dev/null)" || return 1
    rel="${oprefix}$(basename "$cur")${rel:+/$rel}"
    case "$rel" in
      .tmp|.tmp/*|.claude/state|.claude/state/*) return 0 ;;
    esac
    cur="$otop"
  done
}

# in_orca_wt <top> -> rc 0 なら Orca の worktree の会話（hooks/worktree-guard.sh の in_orca_wt と同じ判定。直すときは両方）
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

# yml_val <file> <キー> -> 値（引用符と行末のコメントを外す）。無ければ空。
yml_val() {
  [ -f "$1" ] || return 0
  sed -n "s/^[[:space:]]*${2}:[[:space:]]*//p" "$1" 2>/dev/null | head -1 \
    | sed -e 's/[[:space:]]*#.*$//' -e "s/^[\"']//" -e "s/[\"'][[:space:]]*\$//" -e 's/[[:space:]]*$//'
}

# yml_get <キー> -> 項目ごとに プロジェクト > ホーム の順
yml_get() {
  local v
  v="$(yml_val "$root/.claude/mode.yml" "$1")"
  [ -n "$v" ] || v="$(yml_val "${HOME:-/nonexistent}/.claude/mode.yml" "$1")"
  printf '%s' "$v"
}

wt="${HC_WORKTREE:-$(yml_get worktree)}"
notify="${HC_NOTIFY:-$(yml_get notify)}"

case "$wt" in
  warn|block)
    if ! in_orca_wt "$root"; then
      if [ "$wt" = "block" ] && { [ "$in_repo" -eq 0 ] || outer_ignored "$root"; }; then
        :   # guard は止めない場所（リポの外・HOME の git・外側の .tmp/ の下）。言わない（条 9）
      elif [ "$wt" = "block" ]; then
        if command -v jq >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1; then
          echo "[harness] worktree: block — Orca の worktree ではないため、Edit・Write・NotebookEdit での git に入るファイルの編集と git commit は止まります（MCP の書き込みの道具は止めません）。orca worktree create --name <名前> で worktree を作って作業してください"
        else
          echo "[harness] worktree: block ですが、jq も python3 も無いので止まりません。Orca の worktree ではないため、並行の会話と作業ツリーが重なる恐れがあります（jq か python3 を入れると止まります）"
        fi
      else
        echo "[harness] worktree: warn — Orca の worktree ではありません。並行の会話と作業ツリーが重なる恐れがあります（orca worktree create --name <名前>）"
      fi
    fi
    ;;
esac

if [ "$notify" = "orca" ]; then
  echo "[harness] notify: orca — 決めてもらうことができたら問いを .tmp/ に単独で読める形で書き、hirai-notify question <絶対 path> <要約> を送ってその手番を終える。終わったら done <報告の絶対 path> <要約>（終わる前に、報告の頭に worktree の残りの作業（なし／あり: 内容）を書く。done は残りの数も要約に足す）、続けられないエラーは stopped <報告の絶対 path> <要約>（宛先は --dispatch-id（前置きの Dispatch の id）> --to > 環境変数。依頼文で宛先を渡されたら最初に .claude/state/coordinator へ 1 行 run:<id> で書く。24 時間で失効し、done で消える）。送る操作は検査の結果を見てから別の呼び出しで打つ。API エラーで手番が終わったときは StopFailure の hook が自動で知らせる"
fi
exit 0
