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

HARNESS_UPDATE_URL_DEFAULT="https://raw.githubusercontent.com/thirai-classlab/hirai-method-lite/v2/VERSION"

# 2.x の配布系列 (marketplace のエントリ名) を仮に置いたもの。配布先の
# marketplace.json に実際に足すエントリ名が決まったら、この 1 行と commands/*.md の
# 素材行の同じ文字列を合わせる (ズレていても壊れ方は fail-open — 解決できずに空を返す
# だけで、旧い版を掴んだりはしない)。scripts/tasks-path.sh の HARNESS_GHP_ID と同じ
# 仮置きの考え方 (あちらは控えの置き場、こちらは本体の置き場)。
HARNESS_V2_ENTRY_NAME="hirai-lite-v2"

# --- プラグイン本体の置き場所 --------------------------------------------------
# $CLAUDE_PLUGIN_ROOT は**空で渡ることがある**。渡らない実行経路があるため、これを直に
# パスの前に置いた行は「/VERSION」を読みに行って失敗する (v1.14.0 の /update が実環境で
# 動かなかった原因)。空・不在なら 3 段で探す — 環境変数 → installed_plugins.json の
# 2.x の行のうち版が最新の installPath → キャッシュ (2.x の entry 名で、版が最新のもの)。
# 4 段目 (marketplaces/hirai-lite = main = 1.x) には落とさない — 1.x の案件が誤って
# 2.x のスクリプトを読む向きの事故を、その逆 (2.x の案件が 1.x の置き場へ落ちる)
# でも起こさないため。commands/*.md 冒頭の「素材行」と同じ 3 段で、tests/smoke.sh
# case 10 (f) が「素材行の結果」と「この関数の結果」の一致を検査する。
# シェルから使えるのはこの関数だが、**コマンド手順書は素材行のほうを使う** —
# 関数を読むには先にこのファイルの場所が要る (それを解決するのが素材行の仕事)。
#
# installed_plugins.json は projectPath を見ない (どの checkout から呼ばれても同じ実体を
# 指す最大版に揃える — 一時的な worktree のような checkout でも解決が外れないようにするため)。
harness_plugin_root_from_installed() (
  set -uo pipefail
  local entry="${1:?}" f="$HOME/.claude/plugins/installed_plugins.json" p
  [ -f "$f" ] || return 1
  command -v python3 >/dev/null 2>&1 || return 1
  p="$(python3 -c 'import json,re,sys
d = json.load(open(sys.argv[1]))
rows = [x for k, v in d.get("plugins", {}).items() if k.split("@", 1)[0] == sys.argv[2]
        for x in v if x.get("installPath")]
rows.sort(key=lambda x: [int(n) if n.isdigit() else 0
                          for n in re.split(r"[.]", str(x.get("version", "0")))])
print(rows[-1]["installPath"] if rows else "")' "$f" "$entry" 2>/dev/null)" || return 1
  [ -n "$p" ] || return 1
  printf '%s' "$p"
)

harness_plugin_root() (
  set -uo pipefail
  local p="${1:-${CLAUDE_PLUGIN_ROOT:-}}"
  if [ ! -d "$p" ]; then
    p="$(harness_plugin_root_from_installed "$HARNESS_V2_ENTRY_NAME" 2>/dev/null)"
  fi
  if [ ! -d "$p" ]; then
    p="$(ls -d "$HOME"/.claude/plugins/cache/hirai-lite/"$HARNESS_V2_ENTRY_NAME"/*/ 2>/dev/null | sort -V | tail -1)"
    p="${p%/}"
  fi
  printf '%s' "$p"
)

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
# 導入先ごとに分けた 1 ファイルへ書き写す。statusline はその 1 ファイルの有無を見るだけで、
# 通信もバージョン比較もしない。
#
# **鍵はプロジェクトのパス (CLAUDE_PROJECT_DIR) の cksum にする。** プラグインのパスでは
# 分けられない — statusline はプラグインの置き場所を知れないため、書く側 (ここ) と読む側
# (statusline.sh) の双方が資格として持っている値でなければ、同じ鍵を導けない。プロジェクトの
# パスなら両方が知っている (session-start.sh も statusline.sh も CLAUDE_PROJECT_DIR を読む)。
# これが無いと、1.x と 2.x を併用する機械で、無関係な案件どうしの「更新あり」表示が
# 入れ替わる (v1.14.2 の案件を開くと v1.16.0 の案件の画面下にも出る、という実害があった)。
HARNESS_UPDATE_FLAG_DIR_NAME="claude-harness-lite"

# harness_update_flag_key [project_root] -> 鍵 (cksum) を stdout。常に rc 0 (空にはしない)。
harness_update_flag_key() (
  set -uo pipefail
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" key
  key="$(printf '%s' "$root" | cksum 2>/dev/null | awk '{print $1}')"
  [ -n "$key" ] || key="default"
  printf '%s' "$key"
)

# harness_update_flag_file [project_root] -> フラグのパスを stdout (作成はしない)
harness_update_flag_file() (
  set -uo pipefail
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}"
  printf '%s/%s/update-available-%s' "${TMPDIR:-/tmp}" "$HARNESS_UPDATE_FLAG_DIR_NAME" \
    "$(harness_update_flag_key "$root")"
)

# harness_update_flag_sync <plugin_root> [project_root] -> 新版があれば "<現版> <新版>" を書き、
# 無ければ消す。常に rc 0。HARNESS_UPDATE_CHECK=off のときも消す (止めた指定が古いフラグで
# 無効化されないようにする)。plugin_root は版の比較に使い、project_root はフラグの鍵に使う
# (両者は別物 — 1 台の機械で複数案件を開くと project_root は毎回変わるが、plugin_root は
# 同じキャッシュを指すことがある)。
harness_update_flag_sync() (
  set -uo pipefail
  local plugin_root="${1:-${CLAUDE_PLUGIN_ROOT:-$PWD}}" \
        project_root="${2:-${CLAUDE_PROJECT_DIR:-$PWD}}" flag cur new
  flag="$(harness_update_flag_file "$project_root")"
  if harness_update_enabled \
    && cur="$(harness_local_version "$plugin_root")" \
    && new="$(harness_cached_version "$plugin_root")" \
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
  # 呼び出し側が $CLAUDE_PLUGIN_ROOT をそのまま渡し、それが空だった場合でも黙って
  # 何もしない (= 更新されていないのに更新できたように見える) 事故を避ける。
  [ -n "$plug" ] && [ -d "$plug/scripts" ] || plug="$(harness_plugin_root)"
  [ -d "$plug/scripts" ] || return 0

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
