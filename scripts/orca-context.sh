#!/usr/bin/env bash
# 会話の開始時に出す Orca 関連の行を標準出力に出す（hooks/session-start.sh が 1 行で呼ぶ）。
#   worktree: warn|block で Orca の worktree でないとき … 警告 1 行
#   notify: orca のとき … 知らせ方の 3 行
# どちらも off（既定）なら 1 バイトも出さない。常に exit 0（fail-open）。
set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$PWD}"

yml_get() {
  local lib; lib="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)/tasks-path.sh"
  [ -f "$lib" ] || return 0
  ( . "$lib" 2>/dev/null && harness_yml_value "$root" "$1" ) 2>/dev/null || true
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
        echo "[harness] worktree: block — Orca の worktree ではないため、git に入るファイルの編集と git commit は止まります。orca worktree create --name <名前> で worktree を作って作業してください"
      else
        echo "[harness] worktree: warn — Orca の worktree ではありません。並行の会話と作業ツリーが重なる恐れがあります（orca worktree create --name <名前>）"
      fi
    fi
    ;;
esac

if [ "$notify" = "orca" ]; then
  echo "[harness] notify: orca — 決めてもらうことができたら、問いを .tmp/ に単独で読める形で書き、hirai-notify question <file> <要約> を送ってその手番を終えます"
  echo "[harness] 終わったら hirai-notify done <報告> <要約>、続けられないエラーで止まったら hirai-notify stopped <報告> <要約> を送ります（Orca に立ち上げられた担当は、最初の前置きの文にある Dispatch の id を --dispatch-id で渡します）"
  echo "[harness] 送る操作は、検査の結果を見てから別の呼び出しで打ちます。答えはコーディネーターがこの会話の端末へ中継します"
fi
exit 0
