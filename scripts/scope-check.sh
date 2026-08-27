#!/usr/bin/env bash
# 同じルールが「このプロジェクト」と「全プロジェクト共通 (ホーム)」の両方にあると、
# まったく同じ文章が 2 回読み込まれ、常時ロードの予算 (3,000 tokens) を無言で割る。
# その重なりだけを検出して、平易な日本語で警告を出す。
#
#   使い方: scope-check.sh <プロジェクト側の .claude> <ホーム側の .claude>
#   引数の順番は固定 (どちらの scope に配置した場合でも同じ順で渡す)。
#   重なりが無ければ何も出さない。どの場合も exit 0 (検査で /init を止めない)。
set -uo pipefail

proj="${1:-.claude}"
home_dir="${2:-$HOME/.claude}"

abspath() { (cd "$1" 2>/dev/null && pwd -P) || printf '%s' "$1"; }

[ -d "$proj/rules" ] || exit 0
[ -d "$home_dir/rules" ] || exit 0
# 同じ場所を 2 回渡された場合 (ホーム直下でセッションを開いた等) は重複ではない。
[ "$(abspath "$proj")" != "$(abspath "$home_dir")" ] || exit 0

dup=""
for f in "$proj"/rules/*.md; do
  [ -e "$f" ] || continue
  n="$(basename "$f")"
  [ -e "$home_dir/rules/$n" ] && dup="$dup $n"
done
[ -n "$dup" ] || exit 0

printf '⚠️ 同じルールが 2 か所にあります\n'
printf '   ・このプロジェクト: %s/rules/\n' "$proj"
printf '   ・全プロジェクト共通: %s/rules/\n' "$home_dir"
printf '   重なっているもの:%s\n' "$dup"
printf '   両方あると同じ内容が二重に読み込まれ、AI が使える容量を無駄に消費します。\n'
printf '   どちらか一方を残してください（消すのは このプロジェクト 側が簡単です）。\n'
printf '   このプロジェクト側を消すなら、次を実行します。\n'
for n in $dup; do printf '     rm %s/rules/%s\n' "$proj" "$n"; done
exit 0
