#!/usr/bin/env bash
# 同じルールが「このプロジェクト」と「全プロジェクト共通 (ホーム)」の両方にあると、
# まったく同じ文章が 2 回読み込まれ、常時ロードの予算 (警告 6,000 / 上限 10,000 tokens) を無言で割る。
# その重なりだけを検出して、平易な日本語で警告を出す。
#
#   使い方: scope-check.sh <プロジェクト側の .claude> <ホーム側の .claude>
#   引数の順番は固定 (どちらの scope に配置した場合でも同じ順で渡す)。
#   重なりが無ければ何も出さない。どの場合も exit 0 (検査で /init を止めない)。
#
# あわせて**台帳の二重存在**も見る。書類の置き場は常に `docs/` だが、v1.7.0 までに導入した環境は
# `.claude/` の下に台帳がある。両方に在るとパス解決は `docs/` 側だけを返し、`.claude/` 側は
# 誰にも読まれないまま残る (更新しても誰も見ない = 二重管理の始まり)。移行の取りこぼしをここで止める。
set -uo pipefail

proj="${1:-.claude}"
home_dir="${2:-$HOME/.claude}"
root="${3:-$(dirname "$proj")}"

abspath() { (cd "$1" 2>/dev/null && pwd -P) || printf '%s' "$1"; }

if [ -f "$root/docs/tasks/list.md" ] && [ -f "$root/.claude/tasks/list.md" ]; then
  printf '⚠️ タスク一覧表が 2 か所にあります\n'
  printf '   ・%s\n' "$root/docs/tasks/list.md"
  printf '   ・%s\n' "$root/.claude/tasks/list.md"
  printf '   読まれるのは docs/ 側だけです。.claude/ 側に書いても誰も見ません。\n'
  printf '   中身を見比べて、残すほうを docs/tasks/list.md に 1 本化してください。\n'
  printf '   (/hirai-lite:update の移行手順は、移動先に同名のファイルがあると移さずに両方残します)\n'
fi

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
