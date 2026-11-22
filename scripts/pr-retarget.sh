#!/usr/bin/env bash
#
# pr-retarget.sh — PR の base を付け替え、CI とレビューを新しい base で走らせ直す。
#
# なぜ script にするか:
#   base の付け替え（`gh pr edit --base`）が起こすのは pull_request の `edited` だけで、
#   多くのリポの CI は `edited` では起動しない。付け替えた PR の検査は古い base で測った結果のまま残る。
#   `edited` を起動条件に足すと、タイトルや本文を直すたびに実行中の CI が取り消される。
#   だから足さずに、閉じて開き直し、`reopened` で全部を起動する。
#   閉じる・開くは利用者の gh の token で行うので workflow が起動する
#   （GITHUB_TOKEN が起こしたイベントは workflow を起動しない）。
#
# 使い方:
#   bash scripts/pr-retarget.sh <PR 番号> <新しい base>   # 例: bash scripts/pr-retarget.sh 389 main
#   bash scripts/pr-retarget.sh --help
#   対象のリポは、環境変数 PR_RETARGET_REPO（owner/name）が無ければ、いまの checkout の gh の既定のリポ。
#
# 注意: Projects の組込 workflow「Item closed」を有効にしていると、閉じた時点でこの PR の
#   Status が 完了 に変わる。付け替えたあとで Status を見直す。
#
# 最後に closingIssuesReferences（PR に紐づく閉じる issue）を出す。
#   積み上げ PR（base が既定の branch 以外）は紐づけが切れていることがあるので、空なら
#   本文の閉じるキーワードと Refs から task の番号を拾って出す。
#
# 落ちる条件:
#   呼び出し方の誤り（引数の数 / PR 番号が数字でない）            → exit 2
#   PR が OPEN でない / base が origin に無い / gh が失敗した        → exit 1
#   closingIssuesReferences・本文の取得に失敗した                    → 警告だけ・exit 0
#   それ以外                                                          → exit 0
#
# 積み上げ PR の下の PR が squash で入ったら: `git fetch origin` →
#   `git rebase --onto origin/<既定の branch> <下の PR の最後の commit> <上の branch>` →
#   `git push --force-with-lease` → このスクリプト。ci の結果が一時的に cancelled に見えるので、
#   新しい実行は `gh pr checks <n>` の繰り返しで待つ（run ID 無しの `gh run watch` は TTY でないと落ちる）。
#   下書きの PR は merge できないので、merge の前に `gh pr ready <n>`。
# 止めない: 人と AI が手で叩くだけ（_meta.md 条 5）。
# 失効: base の付け替えで CI が起動するよう GitHub の仕様が変わったとき。
set -uo pipefail

die()   { echo "$1" >&2; exit "${2:-1}"; }
usage() { awk 'NR < 3 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "$0"; }

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
esac
[ "$#" -eq 2 ] || { usage >&2; exit 2; }

pr="$1"
base="$2"
case "$pr" in
  ''|*[!0-9]*) die "PR 番号は数字で渡す（渡された値: ${pr}）" 2 ;;
esac

REPO="${PR_RETARGET_REPO:-}"
if [ -z "$REPO" ]; then
  REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)" \
    || die "対象のリポを引けなかった（gh auth と remote を確認するか、PR_RETARGET_REPO=owner/name を渡す）" 1
fi

state_and_base="$(gh pr view "$pr" --repo "$REPO" --json state,baseRefName --jq '.state + " " + .baseRefName')" \
  || die "PR #${pr} を読めなかった（gh auth と番号を確認）" 1
state="${state_and_base%% *}"
old_base="${state_and_base#* }"
[ "$state" = "OPEN" ] || die "PR #${pr} は ${state}。付け替えられるのは OPEN の PR だけ" 1

gh api "repos/${REPO}/branches/${base}" --silent 2>/dev/null \
  || die "base に指定した ${base} が origin に無い" 1

if [ "$old_base" = "$base" ]; then
  echo "PR #${pr} の base は既に ${base}。閉じて開き直して CI を起動する"
else
  gh pr edit "$pr" --repo "$REPO" --base "$base" >/dev/null \
    || die "base の付け替えに失敗した（#${pr}: ${old_base} → ${base}）" 1
  echo "PR #${pr} の base を ${old_base} → ${base} に付け替えた"
fi

gh pr close "$pr" --repo "$REPO" >/dev/null || die "PR #${pr} を閉じられなかった" 1
if ! gh pr reopen "$pr" --repo "$REPO" >/dev/null; then
  die "PR #${pr} を開き直せなかった。閉じたままなので gh pr reopen ${pr} を手で叩く" 1
fi
echo "PR #${pr} を閉じて開き直した（reopened で CI とレビューの workflow が起動する）"
echo "確かめ方: gh pr checks ${pr} --repo ${REPO}"
echo "Projects の Status: 組込 workflow の Item closed が有効なら 完了 に変わっているので、レビュー中へ戻す"

# stdout（JSON）と stderr（gh の警告・エラー）を混ぜない。混ぜると、成功時に
# gh が stderr へ何か出しただけで refs が空でなくなる（案内が出ない事故）。
# gh 自身の --jq だけを使い、外部の jq コマンドには依存しない。
refs_err="$(mktemp)"
refs="$(gh pr view "$pr" --repo "$REPO" --json closingIssuesReferences \
    --jq '[.closingIssuesReferences[].number] | map("#\(.)") | join(" ")' 2>"$refs_err")"
refs_status=$?
refs_stderr="$(cat "$refs_err")"
rm -f "$refs_err"

if [ "$refs_status" -ne 0 ]; then
  echo "closingIssuesReferences の取得に失敗した（${refs_stderr}）" >&2
elif [ -n "$refs" ]; then
  echo "closingIssuesReferences: ${refs}"
else
  # 無いのは、本文に閉じるキーワードが無いか base が既定の branch でないから。
  # 既定の branch へ付け替えれば紐づく。付け替え直後は反映まで数十秒かかることがある。
  echo "closingIssuesReferences: 無し（本文に閉じるキーワードが無いか、base が既定の branch でない。付け替え直後は反映に数十秒かかることがある）"

  body_err="$(mktemp)"
  body="$(gh pr view "$pr" --repo "$REPO" --json body --jq '.body // ""' 2>"$body_err")"
  body_status=$?
  body_stderr="$(cat "$body_err")"
  rm -f "$body_err"

  if [ "$body_status" -ne 0 ]; then
    echo "本文の取得に失敗した（${body_stderr}）" >&2
  else
    # 本文の閉じるキーワードと Refs から、task の候補番号を拾う（PR 自身の番号は使わない）。
    candidates="$(printf '%s' "$body" \
      | grep -oiE '(^|[^[:alnum:]_])(closes|close|closed|fixes|fix|fixed|resolves|resolve|resolved|refs?):?[[:space:]]+#[0-9]+' \
      | grep -oE '[0-9]+$' | sort -u || true)"
    if [ -n "$candidates" ]; then
      while IFS= read -r n; do
        [ -n "$n" ] || continue
        echo "案内: PR 本文の #${n} が対応する task。Status を レビュー中 にしてよいか確かめる"
      done <<< "$candidates"
    else
      echo "案内: 本文に閉じる task の番号（Closes #<n>）が無い。足してから、その task の Status を確かめる"
    fi
  fi
fi
