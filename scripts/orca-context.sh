#!/usr/bin/env bash
# 会話の開始時に出す Orca 関連の行を標準出力に出す（hooks/session-start.sh が 1 行で呼ぶ）。
#   worktree: warn|block で Orca の worktree でないとき … 警告 1 行
#   notify: orca のとき … 知らせ方 1 行（開始時の表示を 5 行以内に収めるため 1 行にまとめる）
# どちらも off（既定）なら 1 バイトも出さない。常に exit 0（fail-open）。
# worktree: block でも jq と python3 が無いと guard は入力を読めず止まらない。そのときは「止まりません」と言う（条 9）。
set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$PWD}"

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
    in_orca_wt=0
    if [ -n "${ORCA_WORKTREE_ID:-}" ]; then
      gd="$(git -C "$root" rev-parse --path-format=absolute --git-dir 2>/dev/null)" || gd=""
      gc="$(git -C "$root" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || gc=""
      [ -n "$gd" ] && [ -n "$gc" ] && [ "$gd" != "$gc" ] && in_orca_wt=1
    fi
    if [ "$in_orca_wt" -eq 0 ]; then
      if [ "$wt" = "block" ]; then
        if command -v jq >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1; then
          echo "[harness] worktree: block — Orca の worktree ではないため、git に入るファイルの編集と git commit は止まります。orca worktree create --name <名前> で worktree を作って作業してください"
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
  echo "[harness] notify: orca — 決めてもらうことができたら問いを .tmp/ に単独で読める形で書き、hirai-notify question <絶対 path> <要約> を送ってその手番を終える。終わったら done <報告の絶対 path> <要約>、続けられないエラーは stopped <報告の絶対 path> <要約>（Orca に立ち上げられた担当は、前置きの Dispatch の id を --dispatch-id で渡す）。送る操作は検査の結果を見てから別の呼び出しで打つ"
fi
exit 0
