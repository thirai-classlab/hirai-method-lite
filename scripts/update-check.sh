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

# --- 画面下部 (statusline) へ更新の有無を渡すフラグ -------------------------
# statusline はプラグインの置き場所を知れない (settings.json では ${CLAUDE_PLUGIN_ROOT} が
# 展開されないため、導入先へ複製された .claude/statusline.sh として動く)。VERSION もキャッシュ dir も
# プラグインのパス起点なので、版の比較はここ (SessionStart 側) で済ませ、結果だけを
# パスに依存しない固定の 1 ファイルへ書き写す。statusline はその 1 ファイルの有無を見るだけで、
# 通信もバージョン比較もしない。

# harness_update_flag_file -> フラグのパスを stdout (作成はしない)
harness_update_flag_file() (
  set -uo pipefail
  printf '%s' "${TMPDIR:-/tmp}/claude-harness-lite/update-available"
)

# harness_update_flag_sync [root] -> 新版があれば "<現版> <新版>" を書き、無ければ消す。常に rc 0。
# HARNESS_UPDATE_CHECK=off のときも消す (止めた指定が古いフラグで無効化されないようにする)。
harness_update_flag_sync() (
  set -uo pipefail
  local root="${1:-${CLAUDE_PLUGIN_ROOT:-$PWD}}" flag cur new
  flag="$(harness_update_flag_file)"
  if harness_update_enabled \
    && cur="$(harness_local_version "$root")" \
    && new="$(harness_cached_version "$root")" \
    && harness_semver_gt "$new" "$cur"; then
    mkdir -p "${flag%/*}" 2>/dev/null || return 0
    printf '%s %s' "$cur" "$new" > "$flag.tmp" 2>/dev/null \
      && mv -f "$flag.tmp" "$flag" 2>/dev/null
    return 0
  fi
  rm -f "$flag" 2>/dev/null
  return 0
)

# --- 更新後のスクリプト入れ替え ------------------------------------------------
# プラグイン本体が新しくなっても、導入先 (.claude/ または $HOME/.claude/) へ**複製された**
# 3 ファイルは古いまま残る。ここはその 1 点だけを機械的に揃える。
#
#   対象     : statusline.sh / tasks-path.sh / context-usage.sh (プラグイン所有)
#   触らない : rules/ settings.json mode.yml CLAUDE.md 台帳 (すべて利用者所有)
#   既定     : off。opt-in (harness_auto_sync = on) のときだけ動く
#   きっかけ : プラグインの版が前回入れ替えた版と違うときだけ (同じ版なら比較すらしない)
#   退避     : 中身が配布版と違うファイルは .bak に控えてから入れ替える
#   反映     : 画面下部は次の描き直しから、共通ライブラリは次回起動から
#
# マーケットプレイスとプラグイン本体の更新はここでは行わない。Claude Code 自身が
# 「マーケットプレイス単位の自動更新」を持っており (既定 off / /plugin の Marketplaces から
# 切り替え)、そちらが起動後に背景で済ませる。hook から `claude plugin update` を叩くのは
# 二重実装なうえ、セッション開始を通信で待たせることになるので行わない。

HARNESS_OWNED_SCRIPTS_DEFAULT="statusline.sh tasks-path.sh context-usage.sh"

# harness_sync_stamp_file [plugin_root] -> 前回入れ替えた版を控えるパスを stdout (作成はしない)
harness_sync_stamp_file() (
  set -uo pipefail
  printf '%s/synced' "$(harness_update_cache_dir "${1:-}")"
)

# harness_sync_owned_scripts <plugin_root> <project_root> [force]
#   -> 入れ替えたら報告を stdout。常に rc 0 (失敗してもセッションを壊さない)。
#   force を渡すと opt-in と版の控えを両方とばし、/update の手順 4 と同じ 1 行ずつの
#   作業ログ (same / updated / placed) を出す。省略時は opt-in のときだけ動き、
#   変わったときだけ 1 行にまとめて報告する。
harness_sync_owned_scripts() (
  set -uo pipefail
  local plug="${1:-${CLAUDE_PLUGIN_ROOT:-}}" root="${2:-${CLAUDE_PROJECT_DIR:-$PWD}}" force="${3:-}"
  [ -n "$plug" ] && [ -d "$plug/scripts" ] || return 0

  local cur stamp prev=""
  cur="$(harness_local_version "$plug" 2>/dev/null)" || cur=""
  if [ "$force" != "force" ]; then
    # opt-in。既定 off。共通ライブラリが読めない置き方でも off に落ちる (勝手に入れ替えない)。
    case "$(harness_auto_sync "$root" 2>/dev/null || printf 'off')" in
      on|true|yes) ;;
      *) return 0 ;;
    esac
    [ -n "$cur" ] || return 0
    stamp="$(harness_sync_stamp_file "$plug")"
    [ -f "$stamp" ] && prev="$(head -1 "$stamp" 2>/dev/null | tr -d '\r\n')"
    # 版が同じ = やることなし。比較も I/O もせずに抜ける。
    [ "$prev" = "$cur" ] && return 0
  fi

  local d s src dst n=0 b=0 placed=0
  for d in "$root/.claude" "${HOME:+$HOME/.claude}"; do
    [ -n "$d" ] || continue
    [ -d "$d" ] || continue
    # v1.10.0 で足した相棒は、statusline.sh を置いている側にだけ新しく置く
    # (無いと画面下部と自動処理が別々の使用率を出す。v1.9.0 の不具合)。
    if [ -e "$d/statusline.sh" ] && [ ! -e "$d/context-usage.sh" ] \
       && [ -f "$plug/scripts/context-usage.sh" ]; then
      if cp "$plug/scripts/context-usage.sh" "$d/context-usage.sh" 2>/dev/null; then
        chmod +x "$d/context-usage.sh" 2>/dev/null
        placed=$(( placed + 1 ))
        [ "$force" = "force" ] && printf 'placed  %s\n' "$d/context-usage.sh"
      fi
    fi
    for s in ${HARNESS_OWNED_SCRIPTS:-$HARNESS_OWNED_SCRIPTS_DEFAULT}; do
      src="$plug/scripts/$s"; dst="$d/$s"
      [ -f "$src" ] || continue
      [ -e "$dst" ] || continue          # 置いていない場所に新しく作らない
      if cmp -s "$src" "$dst"; then
        [ "$force" = "force" ] && printf 'same    %s\n' "$dst"
        continue
      fi
      # **控えを取れなければ入れ替えない。** 手を入れていた場合の戻り道を必ず残す。
      cp "$dst" "$dst.bak" 2>/dev/null || continue
      b=$(( b + 1 ))
      if cp "$src" "$dst" 2>/dev/null; then
        chmod +x "$dst" 2>/dev/null
        n=$(( n + 1 ))
        [ "$force" = "force" ] && printf 'updated %s (backup: %s.bak)\n' "$dst" "$dst"
      fi
    done
  done

  if [ "$force" != "force" ]; then
    stamp="$(harness_sync_stamp_file "$plug")"
    mkdir -p "${stamp%/*}" 2>/dev/null && printf '%s' "$cur" > "$stamp" 2>/dev/null
    [ "$(( n + placed ))" -gt 0 ] || return 0
    printf '[harness] v%s に合わせてスクリプト %s 件を入れ替えました' "$cur" "$(( n + placed ))"
    [ "$b" -gt 0 ] && printf ' (元の内容は .bak に保存)'
    printf ' — 反映は次回起動から\n'
  fi
  return 0
)
