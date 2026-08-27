#!/usr/bin/env bash
# ハーネス更新検知の共通ライブラリ。source して使う (専用 hook は作らない)。
#
# 方針: セッション起動を通信で待たせない。表示は前回キャッシュ値、取得は背景 + 24h に 1 回まで。
#   取得先   : HARNESS_UPDATE_URL (既定は公開リポジトリの VERSION)
#   無効化   : HARNESS_UPDATE_CHECK=off で通信も表示もしない
#   間隔     : HARNESS_UPDATE_INTERVAL 秒 (既定 86400)
#   キャッシュ: ${TMPDIR:-/tmp}/claude-harness-lite/update-<key>/ (リポジトリ外・インストール単位)
#   引数の root にはプラグインのルート ($CLAUDE_PLUGIN_ROOT) を渡す。
#   オフライン / 404 / curl 不在 / 壊れた応答は全て沈黙し rc 0 を返す。
#
# file-top に set -e / set -o pipefail を書かない。source 元の shell flags を汚染し、
# パイプ先の早期終了で呼び出し元ごと落ちる事故を防ぐため (関数内で局所化する)。

HARNESS_UPDATE_URL_DEFAULT="https://raw.githubusercontent.com/thirai-classlab/hirai-method-lite/main/VERSION"

# harness_update_enabled -> 有効なら rc 0 (HARNESS_UPDATE_CHECK=off で rc 1)
harness_update_enabled() {
  [ "${HARNESS_UPDATE_CHECK:-on}" != "off" ]
}

# harness_update_cache_dir [root] -> キャッシュ dir を stdout (作成はしない)
# root ごとに key を分けるため、同じマシンの複数プロジェクトが干渉しない。
harness_update_cache_dir() (
  set -uo pipefail
  local root="${1:-${CLAUDE_PLUGIN_ROOT:-$PWD}}" key
  key="$(printf '%s' "$root" | cksum 2>/dev/null | awk '{print $1}')"
  [ -n "$key" ] || key="default"
  printf '%s' "${TMPDIR:-/tmp}/claude-harness-lite/update-${key}"
)

# harness_semver_norm <文字列> -> semver 部分だけを stdout (例 "v1.2.3" -> "1.2.3")、無ければ空
harness_semver_norm() (
  set -uo pipefail
  printf '%s' "${1:-}" | tr -d '\r' \
    | sed -n 's/^[[:space:]]*[vV]\{0,1\}\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\).*$/\1/p' | head -1
)

# harness_semver_gt <a> <b> -> a > b なら rc 0。数値比較なので 0.10.0 > 0.9.0 が真になる。
harness_semver_gt() (
  set -uo pipefail
  local a b
  a="$(harness_semver_norm "${1:-}")"
  b="$(harness_semver_norm "${2:-}")"
  [ -n "$a" ] && [ -n "$b" ] || return 1
  awk -v a="$a" -v b="$b" 'BEGIN {
    na = split(a, A, "."); nb = split(b, B, ".")
    for (i = 1; i <= 3; i++) {
      x = (i <= na ? A[i] + 0 : 0); y = (i <= nb ? B[i] + 0 : 0)
      if (x > y) exit 0
      if (x < y) exit 1
    }
    exit 1
  }'
)

# harness_local_version [dir] -> dir 直下 VERSION の semver、無ければ空 + rc 1
# dir にはプラグインのルート ($CLAUDE_PLUGIN_ROOT) を渡す。VERSION はプラグイン側の資産で、
# 導入先リポジトリには置かれない。
harness_local_version() (
  set -uo pipefail
  local root="${1:-${CLAUDE_PLUGIN_ROOT:-$PWD}}" v
  [ -f "$root/VERSION" ] || return 1
  v="$(harness_semver_norm "$(head -1 "$root/VERSION" 2>/dev/null)")"
  [ -n "$v" ] || return 1
  printf '%s' "$v"
)

# harness_cached_version [root] -> 前回取得した版、無ければ空 + rc 1
harness_cached_version() (
  set -uo pipefail
  local dir v
  dir="$(harness_update_cache_dir "${1:-}")"
  [ -f "$dir/latest" ] || return 1
  v="$(harness_semver_norm "$(head -1 "$dir/latest" 2>/dev/null)")"
  [ -n "$v" ] || return 1
  printf '%s' "$v"
)

# harness_update_fetch_async [root] -> 前回から間隔を過ぎていれば背景で取得を投げる。
# 常に無出力・rc 0。呼び出し元は curl の完了を待たない (子の fd は全て閉じる)。
harness_update_fetch_async() (
  set -uo pipefail
  harness_update_enabled || return 0
  command -v curl >/dev/null 2>&1 || return 0
  local root="${1:-${CLAUDE_PLUGIN_ROOT:-$PWD}}" dir url now last interval
  interval="${HARNESS_UPDATE_INTERVAL:-86400}"
  dir="$(harness_update_cache_dir "$root")"
  mkdir -p "$dir" 2>/dev/null || return 0
  now="$(date +%s 2>/dev/null)"
  [ -n "$now" ] || return 0
  last="0"
  [ -f "$dir/stamp" ] && last="$(tr -cd '0-9' < "$dir/stamp" 2>/dev/null)"
  [ -n "$last" ] || last="0"
  [ "$(( now - last ))" -ge "$interval" ] 2>/dev/null || return 0
  # 取得の成否に関わらず間隔を守るため、投げる前に時刻を記録する。
  printf '%s' "$now" > "$dir/stamp" 2>/dev/null || return 0
  url="${HARNESS_UPDATE_URL:-$HARNESS_UPDATE_URL_DEFAULT}"
  {
    body="$(curl -fsSL --max-time 2 "$url" 2>/dev/null)" || exit 0
    v="$(harness_semver_norm "$body")"
    [ -n "$v" ] || exit 0
    printf '%s' "$v" > "$dir/latest.tmp" 2>/dev/null \
      && mv -f "$dir/latest.tmp" "$dir/latest" 2>/dev/null
    exit 0
  } >/dev/null 2>&1 </dev/null &
  return 0
)

# harness_update_notice [root] -> キャッシュ値が自分より新しい時だけ 1 行出力。他は無出力 rc 0。
harness_update_notice() (
  set -uo pipefail
  harness_update_enabled || return 0
  local root="${1:-${CLAUDE_PLUGIN_ROOT:-$PWD}}" cur new
  cur="$(harness_local_version "$root")" || return 0
  new="$(harness_cached_version "$root")" || return 0
  harness_semver_gt "$new" "$cur" || return 0
  printf '[harness] 更新あり v%s → v%s (/update で適用)\n' "$cur" "$new"
)
