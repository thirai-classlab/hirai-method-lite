#!/usr/bin/env bash
# 台帳 / 設計 draft / 事故記録 / 進め方 / ルールの パス解決を 1 箇所に集める共通ライブラリ。source して使う。
#
# **プロジェクトの書類は常に docs/ に置く** (v1.9.0)。.claude/ 側を見続けるのは、v1.7.0 までに
# 導入した環境が /hirai-lite:update で docs/ へ移行するまでの間、および移行しない選択をした環境で
# 台帳を見失わないため。解決順そのものは v1.8.0 から 1 バイトも変えていない。
#
# 共通の解決順: env 上書き > 既存パス (docs 側 → .claude 側) > docs/ の有無で決める
#   台帳     : HARNESS_TASKS_FILE     > docs/tasks/list.md            > .claude/tasks/list.md
#   draft    : HARNESS_DRAFT_DIR      > docs/draft/                   > .claude/draft/
#   事故記録 : HARNESS_INCIDENTS_FILE > docs/rules-reference/…        > .claude/rules-reference/…
# 台帳が 1 つも無い場合は空文字 + exit 1 を返す (エラーにせず呼び出し側で分岐する)。
# draft / 事故記録は未作成でも「これから作るべきパス」を返す (rc 0)。
#
# 進め方 / ルールは配置先が 2 通りある (プロジェクト側 = .claude/ と 全プロジェクト共通 = $HOME/.claude/)。
# どちらに置いたかを決め打ちすると、片方に置いた利用者に対して黙って外れる。**在る側**を選ぶ。
#   進め方   : HC_MODE (env) > <root>/.claude/mode.yml > $HOME/.claude/mode.yml > normal
#   入れ替え : HC_AUTO_SYNC (env) > 同じ mode.yml の auto_sync > off (既定は入れ替えない)
#   ルール   : HARNESS_RULES_DIR > <root>/.claude/rules > $HOME/.claude/rules > <root>/.claude/rules
#
# file-top に set -e / set -o pipefail を書かない。source 元の shell flags を汚染し、
# パイプ先の早期終了で呼び出し元ごと落ちる事故を防ぐため (関数内で局所化する)。

# harness_tasks_file [root] -> 台帳パスを stdout、無ければ空 + rc 1
harness_tasks_file() {
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" p
  if [ -n "${HARNESS_TASKS_FILE:-}" ]; then
    printf '%s' "$HARNESS_TASKS_FILE"
    return 0
  fi
  for p in "$root/docs/tasks/list.md" "$root/.claude/tasks/list.md"; do
    if [ -f "$p" ]; then
      printf '%s' "$p"
      return 0
    fi
  done
  return 1
}

# harness_draft_dir [root] -> 設計 draft の置き場を stdout (末尾スラッシュなし)
harness_draft_dir() {
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" p
  if [ -n "${HARNESS_DRAFT_DIR:-}" ]; then
    printf '%s' "$HARNESS_DRAFT_DIR"
    return 0
  fi
  for p in "$root/docs/draft" "$root/.claude/draft"; do
    if [ -d "$p" ]; then
      printf '%s' "$p"
      return 0
    fi
  done
  if [ -d "$root/docs" ]; then printf '%s' "$root/docs/draft"; else printf '%s' "$root/.claude/draft"; fi
}

# harness_incidents_file [root] -> 事故記録 (T2) のパスを stdout
harness_incidents_file() {
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" p
  if [ -n "${HARNESS_INCIDENTS_FILE:-}" ]; then
    printf '%s' "$HARNESS_INCIDENTS_FILE"
    return 0
  fi
  for p in "$root/docs/rules-reference/incidents.md" "$root/.claude/rules-reference/incidents.md"; do
    if [ -f "$p" ]; then
      printf '%s' "$p"
      return 0
    fi
  done
  if [ -d "$root/docs" ]; then
    printf '%s' "$root/docs/rules-reference/incidents.md"
  else
    printf '%s' "$root/.claude/rules-reference/incidents.md"
  fi
}

# --- 進め方 (mode) ------------------------------------------------------------
# 読む側 (SessionStart / 画面下部) と書く側 (/config) が別々の順で解決すると、
# 「セッション冒頭は normal・画面下部は loop」のように食い違う。3 箇所ともここを通す。

# harness_mode_file [root] -> すでに在る mode.yml のパスを stdout。
# プロジェクト側 → ホーム側の順で探し、どちらにも無ければ空 + rc 1。
harness_mode_file() {
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" p
  for p in "$root/.claude/mode.yml" "${HOME:+$HOME/.claude/mode.yml}"; do
    [ -n "$p" ] || continue
    if [ -f "$p" ]; then
      printf '%s' "$p"
      return 0
    fi
  done
  return 1
}

# harness_mode_write_file [root] -> /config が書き込むべきパスを stdout (常に rc 0)。
# **すでに在る側に書く。** 両方に無いときだけプロジェクト側に作る。
# (ホーム側に置いた人のプロジェクトへ mode.yml を新設すると、ホーム側を黙って覆い隠す)
harness_mode_write_file() {
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" p
  if p="$(harness_mode_file "$root")"; then
    printf '%s' "$p"
    return 0
  fi
  printf '%s' "$root/.claude/mode.yml"
}

# harness_mode [root] -> いまの進め方 (normal / loop / 未知の値) を stdout。常に rc 0。
# env HC_MODE > 在る側の mode.yml > normal。読めない・空・壊れている場合も normal。
harness_mode() {
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" f m=""
  if [ -n "${HC_MODE:-}" ]; then
    printf '%s' "$HC_MODE"
    return 0
  fi
  if f="$(harness_mode_file "$root")"; then
    m="$(sed -n 's/^[[:space:]]*mode:[[:space:]]*\([a-z]*\).*/\1/p' "$f" 2>/dev/null | head -1)"
  fi
  [ -n "$m" ] || m="normal"
  printf '%s' "$m"
}

# --- 更新後の入れ替え (auto_sync) ---------------------------------------------
# プラグイン所有の 3 ファイル (statusline.sh / tasks-path.sh / context-usage.sh) を、
# プラグインが新しくなった後に自動で入れ替えるかどうか。**既定は off (入れ替えない)。**
# 更新は挙動の変更なので、黙って書き換わると「昨日と違う動きをする理由」を追えなくなる。
# 解決順: env HC_AUTO_SYNC > 在る側の mode.yml の auto_sync > off
# 進め方 (mode) と同じ 1 本を通す (置き場を自分で組み立てない)。

# harness_auto_sync [root] -> on / off (未知の値はそのまま) を stdout。常に rc 0。
harness_auto_sync() {
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" f v=""
  if [ -n "${HC_AUTO_SYNC:-}" ]; then
    printf '%s' "$HC_AUTO_SYNC"
    return 0
  fi
  if f="$(harness_mode_file "$root")"; then
    v="$(sed -n 's/^[[:space:]]*auto_sync:[[:space:]]*\([A-Za-z]*\).*/\1/p' "$f" 2>/dev/null | head -1)"
  fi
  [ -n "$v" ] || v="off"
  printf '%s' "$v"
}

# harness_yml_set <file> <キー> <値> -> その 1 行だけを書き換える (他の行は 1 バイトも触らない)。
# キーの行が無ければ末尾に足し、file が無ければ作る。書けたら rc 0。
# mode.yml に 2 つ以上のキーが載るようになったため、丸ごと書き直すともう片方が消える。
harness_yml_set() (
  set -uo pipefail
  local f="${1:-}" k="${2:-}" v="${3:-}" tmp
  [ -n "$f" ] && [ -n "$k" ] || return 1
  mkdir -p "$(dirname "$f")" 2>/dev/null || return 1
  [ -f "$f" ] || : > "$f" 2>/dev/null || return 1
  tmp="$f.tmp.$$"
  # awk は 1 行ずつ print するので、元が改行で終わっていなくても行が繋がらない。
  awk -v k="$k" -v v="$v" '
    $0 ~ "^[[:space:]]*" k ":" && !d { print k ": " v; d = 1; next }
    { print }
    END { if (!d) print k ": " v }
  ' "$f" > "$tmp" 2>/dev/null || { rm -f "$tmp" 2>/dev/null; return 1; }
  mv -f "$tmp" "$f" 2>/dev/null || { rm -f "$tmp" 2>/dev/null; return 1; }
)

# --- ルール (rules) -----------------------------------------------------------
# /add-rule の予算計算と /rules-audit の棚卸しが見る置き場。プロジェクト側を決め打ちすると、
# 全プロジェクト共通 (/init user) に置いた利用者に対して「既存ルール 0 件」と誤判定する。

# harness_rules_dir [root] -> ルールの置き場を stdout (末尾スラッシュなし、常に rc 0)。
# 両方に在る場合はプロジェクト側を返すが、それは二重ロード状態なので
# scripts/scope-check.sh の警告に従って先に片方を消す (予算は 2 か所の合計で効いている)。
harness_rules_dir() {
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" p
  if [ -n "${HARNESS_RULES_DIR:-}" ]; then
    printf '%s' "$HARNESS_RULES_DIR"
    return 0
  fi
  for p in "$root/.claude/rules" "${HOME:+$HOME/.claude/rules}"; do
    [ -n "$p" ] || continue
    if [ -d "$p" ]; then
      printf '%s' "$p"
      return 0
    fi
  done
  printf '%s' "$root/.claude/rules"
}

# harness_open_tasks <list.md> -> 未完了 (完了 / done / ✅ 以外) の行数を stdout
harness_open_tasks() {
  local f="${1:-}" total done_n n
  [ -f "$f" ] || { printf '0'; return 0; }
  # grep -c は 0 件のとき "0" を出しつつ exit 1 を返す。数字以外を捨てて必ず整数にする。
  total="$(grep -c '^|[[:space:]]*[0-9]' "$f" 2>/dev/null | tr -cd '0-9')"
  done_n="$(grep '^|[[:space:]]*[0-9]' "$f" 2>/dev/null | grep -c -e '✅' -e '完了' -e '[Dd]one' | tr -cd '0-9')"
  n=$(( ${total:-0} - ${done_n:-0} ))
  [ "$n" -ge 0 ] 2>/dev/null || n=0
  printf '%s' "$n"
}

# --- GHP (GitHub Project) の形 -------------------------------------------------
# 台帳の形 (harness_tasks_file / harness_open_tasks、上) とは別に、リポに紐づいた
# GitHub Project を使う形を持つ。**両者は排他ではなく、どちらの形で動くかを
# リポごとに見分けるだけ** — harness_tasks_file・harness_open_tasks の名前も意味も
# 変えない。台帳の有無では見分けられない (台帳を凍結しつつ Project も持つリポが
# ある。台帳を消す判定にすると、1.x 由来の /new-task 等が台帳を再生成して判定が
# ひっくり返る)。見分ける手がかりは、リポに紐づいた Project が項目「種別」を
# 持つかどうかだけにする (プロジェクトごとの設定ファイルは作らない、という既存の
# 方針に合わせる)。紐づく Project が 2 件以上あるときは、どれを使うか決め打ちせず
# "ambiguous" として GHP 扱いにしない (呼び出し側は台帳の形にフォールバックする)。
#
# 通信する (gh を叩く) のは、次の 2 か所だけにする。
#   ・SessionStart の背景処理 (harness_ghp_refresh background。hooks/session-start.sh から
#     detach して呼ぶ)
#   ・書き込み用の道具 (bin/hirai-task。refresh_board_counts) が書き込んだ直後
#     (harness_ghp_refresh now)
# session-start.sh と statusline.sh はここの「読む側」(harness_ghp_line 系) だけを呼び、
# 控えを読むだけで gh は 1 回も呼ばない。
#
# 控えの置き場は $CLAUDE_PLUGIN_DATA (hook・MCP・LSP にしか渡らず、Bash ツールには
# 渡らない: https://code.claude.com/docs/en/plugins-reference の
# "Where each variable resolves") を使わず、$HOME/.claude/plugins/data/<id>/ の形を
# 定数で持つ。<id> は将来この GHP の形を持つ配布系列 (エントリ) の名前を仮に置いた
# もの — 実際のエントリ名が決まったら、この 1 行を合わせる (ズレていても壊れ方は
# 「控えが前回のまま」で fail-open)。
HARNESS_GHP_ID="hirai-lite-v2"

# 見分け (このリポが GHP の形かどうか自体) の取り直しの間隔。変わることが稀なので
# 間隔を空ける (既定 24h。update-check.sh の間隔と同じ考え方)。
HARNESS_GHP_PROBE_INTERVAL_DEFAULT=86400
# 件数 (a-d) の取り直しの間隔。**background (SessionStart) のときだけ**この間隔を守る —
# /clear・/compact・並べて開いた会話のたびに毎回 gh を叩くと、共有の GraphQL 枠を
# 削る (前回の枯渇は 1 時間に 2 回)。書き込み用の道具の直後 (now) は、その場の最新値が
# 要るので間隔を空けずに毎回取る。
HARNESS_GHP_COUNTS_STALE_DEFAULT=120

# harness_ghp_repo_slug [root] -> "<owner>/<repo>" を stdout、無ければ空 + rc 1。
# git remote (origin) から読むだけで、gh は呼ばない (ここは通信しない)。
# git@host:owner/repo (SCP 形) ・ ssh://[user@]host/owner/repo ・ https://[user@]host/owner/repo
# のどれでも、"github.com" の直後の区切り (: か /) までを削れば owner/repo だけが残る。
# github.com 以外のホストや、owner/repo が 1 対に決まらない値は解決できずに rc 1 を返す。
harness_ghp_repo_slug() (
  set -uo pipefail
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" url slug
  url="$(git -C "$root" remote get-url origin 2>/dev/null)" || return 1
  [ -n "$url" ] || return 1
  case "$url" in *github.com*) ;; *) return 1 ;; esac
  slug="$(printf '%s' "$url" | sed -E 's#^.*github\.com[:/]##; s#\.git$##; s#/+$##')"
  case "$slug" in
    */*) case "${slug#*/}" in */*) return 1 ;; esac ;;
    *) return 1 ;;
  esac
  printf '%s' "$slug"
)

# harness_ghp_cache_file [root] -> 控えのパスを stdout (作成はしない、常に rc 0)。
# 定数の置き場 + リポの slug で鍵を作る。env に依存しないため、env を unset しても
# 書く側 (harness_ghp_refresh) と読む側 (harness_ghp_line 系) が同じパスを指す。
harness_ghp_cache_file() (
  set -uo pipefail
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" slug
  slug="$(harness_ghp_repo_slug "$root" 2>/dev/null || true)"
  [ -n "$slug" ] || slug="unknown"
  printf '%s/.claude/plugins/data/%s/tasks-%s.json' "$HOME" "$HARNESS_GHP_ID" "${slug//\//-}"
)

# harness_ghp_cache_get <file> <key> -> 値を stdout、無ければ空 + rc 1。
# 控えは我々が書く単純な 1 行 1 key の JSON なので、jq を要らず sed で足りる
# (jq 不在でも読める。gh 自身の --jq は gh 内蔵で system の jq を要らないが、
# ここは gh を呼ばない側なので、system の jq にすら依存させない)。
harness_ghp_cache_get() {
  local f="${1:-}" k="${2:-}" v
  [ -f "$f" ] && [ -n "$k" ] || return 1
  v="$(sed -n "s/^[[:space:]]*\"$k\"[[:space:]]*:[[:space:]]*\"\\{0,1\\}\\([^\",]*\\)\"\\{0,1\\},\\{0,1\\}[[:space:]]*\$/\\1/p" "$f" 2>/dev/null | head -1)"
  [ -n "$v" ] || return 1
  printf '%s' "$v"
}

# harness_ghp_form [root] -> "ghp" / "ledger" / "none" のいずれかを stdout、控えが
# 無ければ空 + rc 1 (呼び出し側は「まだ見分けていない」として台帳の形にフォールバックする)。
harness_ghp_form() {
  harness_ghp_cache_get "$(harness_ghp_cache_file "${1:-}")" form
}

# harness_ghp_line [root] -> あなたの番 の行に埋め込む件数の中身 (見出し語は付けない)。
# 形式: "N（承認 a・裁定 b・取り込み c）／進行中 d／待ち解け e（HH:MM 時点）"
# form が ghp でない・控えが無い・件数 (a-d) が欠けている場合は空 + rc 1 を返す
# (呼び出し側は台帳の形にフォールバックする)。gh は呼ばない (控えを読むだけ)。
#
# **待ち解け (e) は常に「—」**。正しい定義 (依存待ちのうち、止めていた依存が全部
# 閉じたもの) を、安全な GraphQL 点数・5 秒の hook 枠に収まる形で取れるかがまだ
# 実測できていないため、harness_ghp_refresh は e を書き込まない (今後の差し替え先は
# 同関数のコメントを参照)。時刻 (HH:MM) は件数 (a-d) を取得した時点のもので、
# fetched_hm に書き込み時点の**手元のローカル時刻**をそのまま文字列で持つ
# (UTC の値を表示直前に切り出すと、日本時間の利用者には 9 時間ずれて見えるため)。
harness_ghp_line() {
  local root="${1:-}" f a b c d e hm n
  f="$(harness_ghp_cache_file "$root")"
  [ "$(harness_ghp_cache_get "$f" form)" = "ghp" ] || return 1
  a="$(harness_ghp_cache_get "$f" approve)" || return 1
  b="$(harness_ghp_cache_get "$f" arbitrate)" || return 1
  c="$(harness_ghp_cache_get "$f" ingest)" || return 1
  d="$(harness_ghp_cache_get "$f" in_progress)" || return 1
  e="$(harness_ghp_cache_get "$f" unblocked)" || e="—"
  hm="$(harness_ghp_cache_get "$f" fetched_hm)" || hm="—"
  n=$(( ${a:-0} + ${b:-0} + ${c:-0} )) 2>/dev/null || n="$a"
  printf '%s（承認 %s・裁定 %s・取り込み %s）／進行中 %s／待ち解け %s（%s 時点）' \
    "$n" "$a" "$b" "$c" "$d" "$e" "$hm"
}

# harness_ghp_write_probe <file> <form> [project_id] [project_number] -> 見分けの結果を
# 書く (form は "ghp" / "none" / "ambiguous" のいずれか)。counts (a-d とその取得時刻) は
# 既存の値をそのまま残す (probe だけでは消さない)。
# 連想配列 (bash 4+) は使わない — macOS の既定 /bin/bash は 3.2 で使えないため、
# 個々のフィールドを都度 harness_ghp_cache_get で読み直す (やや冗長だが確実)。
harness_ghp_write_probe() (
  set -uo pipefail
  local f="${1:?}" form="${2:?}" pid="${3:-}" pn="${4:-}"
  local o_a o_b o_c o_d o_fe o_hm
  mkdir -p "$(dirname "$f")" 2>/dev/null || return 0
  o_a="$(harness_ghp_cache_get "$f" approve 2>/dev/null || true)"
  o_b="$(harness_ghp_cache_get "$f" arbitrate 2>/dev/null || true)"
  o_c="$(harness_ghp_cache_get "$f" ingest 2>/dev/null || true)"
  o_d="$(harness_ghp_cache_get "$f" in_progress 2>/dev/null || true)"
  o_fe="$(harness_ghp_cache_get "$f" fetched_epoch 2>/dev/null || true)"
  o_hm="$(harness_ghp_cache_get "$f" fetched_hm 2>/dev/null || true)"
  [ -n "$pid" ] || pid="$(harness_ghp_cache_get "$f" project_id 2>/dev/null || true)"
  [ -n "$pn" ] || pn="$(harness_ghp_cache_get "$f" project_number 2>/dev/null || true)"
  harness_ghp_write_raw "$f" "$form" "$pid" "$pn" "$o_a" "$o_b" "$o_c" "$o_d" "$o_fe" "$o_hm" \
    "$(date -u +%s 2>/dev/null || echo 0)"
)

# harness_ghp_write_counts <file> <approve> <arbitrate> <ingest> <in_progress> [now_epoch] ->
# 件数 (a-d) と、その取得時刻 (間隔判定用の UNIX epoch + 表示用のローカル HH:MM 文字列) を
# 書く。form・project_id・project_number・probed_epoch は既存の値を残す。
harness_ghp_write_counts() (
  set -uo pipefail
  local f="${1:?}" a="${2:-0}" b="${3:-0}" c="${4:-0}" d="${5:-0}" now_epoch="${6:-}"
  local form pid pn o_pe hm
  form="$(harness_ghp_cache_get "$f" form 2>/dev/null || echo ghp)"
  pid="$(harness_ghp_cache_get "$f" project_id 2>/dev/null || true)"
  pn="$(harness_ghp_cache_get "$f" project_number 2>/dev/null || true)"
  o_pe="$(harness_ghp_cache_get "$f" probed_epoch 2>/dev/null || echo 0)"
  [ -n "$now_epoch" ] || now_epoch="$(date -u +%s 2>/dev/null || echo 0)"
  hm="$(date +%H:%M 2>/dev/null)"
  mkdir -p "$(dirname "$f")" 2>/dev/null || return 0
  harness_ghp_write_raw "$f" "$form" "$pid" "$pn" "$a" "$b" "$c" "$d" "$now_epoch" "$hm" "$o_pe"
)

# harness_ghp_write_raw <file> <form> <pid> <pn> <a> <b> <c> <d> <fetched_epoch> <fetched_hm>
#   <probed_epoch> -> 上の 2 つが共有する実際の書き込み。空の値はその key を書かない
# (呼び出し側が「まだ無い」と「0」を区別できるようにする)。*_epoch は UNIX 時刻の整数
# (間隔の計算専用。日時の文字列を逆算しない — GNU date の -d と BSD date の -jf は書式が
# 違い、両対応は事故のもとになるため)。fetched_hm は書き込み時点の**手元のローカル時刻**を
# そのまま文字列で持つ (epoch から表示直前に逆算しない。同じ理由)。
harness_ghp_write_raw() (
  set -uo pipefail
  local f="${1:?}" form="${2:?}" pid="${3:-}" pn="${4:-}" \
        a="${5:-}" b="${6:-}" c="${7:-}" d="${8:-}" fe="${9:-}" hm="${10:-}" pe="${11:-0}" tmp
  tmp="$f.tmp.$$"
  {
    printf '{\n  "form": "%s",\n' "$form"
    [ -n "$pid" ] && printf '  "project_id": "%s",\n' "$pid"
    [ -n "$pn" ] && printf '  "project_number": %s,\n' "$pn"
    [ -n "$a" ] && printf '  "approve": %s,\n' "$a"
    [ -n "$b" ] && printf '  "arbitrate": %s,\n' "$b"
    [ -n "$c" ] && printf '  "ingest": %s,\n' "$c"
    [ -n "$d" ] && printf '  "in_progress": %s,\n' "$d"
    [ -n "$fe" ] && printf '  "fetched_epoch": %s,\n' "$fe"
    [ -n "$hm" ] && printf '  "fetched_hm": "%s",\n' "$hm"
    printf '  "probed_epoch": %s\n}\n' "${pe:-0}"
  } > "$tmp" 2>/dev/null && mv -f "$tmp" "$f" 2>/dev/null
)

# harness_ghp_refresh <background|now> [root] -> 常に rc 0 (fail-open)。
# gh を叩く唯一の入り口。gh 不在・git remote 不在・GHP でないリポでは、静かに抜ける。
#
#   1. 見分け (form): 前回の probed_epoch から HARNESS_GHP_PROBE_INTERVAL 秒 (既定 24h)
#      経っていなければ飛ばす。経っていれば、リポに紐づく Project (Repository.projectsV2。
#      この向き — リポからの紐づけ — は未検証。owner の型 (organization/user) を
#      問わない node(id:) 経由で数える側は別に確かめている) のうち、項目「種別」を
#      持つものを数える。0 件なら "none"、1 件なら "ghp"、2 件以上ならどれを使うか
#      決め打ちせず "ambiguous" にする (台帳の形かどうかは呼び出し側 —
#      session-start.sh — が harness_tasks_file の有無で判定するので、ここでは
#      "none"/"ambiguous" と書くだけにする)。
#      **gh の失敗 (オフライン・枠切れ・scope 不足など) では、前回の見分けを変えない** —
#      「成功して 0 件」のときだけ none を書く。失敗を「無い」と混同しない
#      (core.md「否定は肯定を出せると確かめてから報告する」と同じ理由)。
#   2. counts (a-d): form が ghp のときだけ、totalCount を 1 回の GraphQL 呼び出しで
#      別名で並べて取る。mode=background のときは、前回の fetched_epoch から
#      HARNESS_GHP_COUNTS_STALE 秒 (既定 2 分) 経っていなければ飛ばす (SessionStart の
#      たびに毎回叩かない)。mode=now は間隔を空けずに毎回取る。ここも gh の失敗や、
#      応答が数字 4 つの形でなかった場合は、前回の counts をそのまま残す。
#   3. 待ち解け (e): **書かない。** 正しい定義 (依存待ちのうち、止めていた依存が
#      全部閉じたもの) を得るには、依存待ちの各行の blocked-by を突き合わせる必要があり、
#      Project の items(query:) と組み合わせたときの GraphQL 点数が安全な範囲に
#      収まるかがまだ実測できていない。
#      以前はここで status:依存待ち の totalCount (= 依存待ちの全件数) を代用していたが、
#      それは「解けた」件数ではなく「まだ解けていない依存待ち」の件数で、値として
#      間違っていた (依存が 1 件も解けていなくても大きな数が出る)。間違った数を見せる
#      より、harness_ghp_line の「—」フォールバックに任せる方が安全と判断した
#      (要判断。実装するならこの 1 か所に q3 を足す)。
harness_ghp_refresh() (
  set -uo pipefail
  command -v gh >/dev/null 2>&1 || return 0
  local mode="${1:?}" root="${2:-${CLAUDE_PROJECT_DIR:-$PWD}}" slug owner repo f now
  slug="$(harness_ghp_repo_slug "$root" 2>/dev/null)" || return 0
  owner="${slug%%/*}"; repo="${slug#*/}"
  f="$(harness_ghp_cache_file "$root")"
  now="$(date -u +%s 2>/dev/null)"; [ -n "$now" ] || now=0

  local probed_epoch interval="${HARNESS_GHP_PROBE_INTERVAL:-$HARNESS_GHP_PROBE_INTERVAL_DEFAULT}"
  probed_epoch="$(harness_ghp_cache_get "$f" probed_epoch 2>/dev/null || echo 0)"
  [ -n "$probed_epoch" ] 2>/dev/null || probed_epoch=0
  local form proj_id
  if [ "$probed_epoch" -eq 0 ] 2>/dev/null || [ "$(( now - probed_epoch ))" -ge "$interval" ] 2>/dev/null; then
    local q1 q1_out q1_rc n_match proj_number
    q1='query($o:String!,$r:String!){repository(owner:$o,name:$r){projectsV2(first:20){nodes{id number fields(first:50){nodes{... on ProjectV2FieldCommon{name}}}}}}}'
    q1_out="$(gh api graphql -f query="$q1" -f o="$owner" -f r="$repo" \
          --jq '.data.repository.projectsV2.nodes[] | select([.fields.nodes[]?.name] | index("種別")) | [.id,.number] | @tsv' \
          2>/dev/null)"
    q1_rc=$?
    if [ "$q1_rc" -ne 0 ]; then
      return 0
    fi
    n_match="$(printf '%s\n' "$q1_out" | grep -c . || true)"
    case "${n_match:-0}" in
      0)
        form="none"
        harness_ghp_write_probe "$f" "$form"
        ;;
      1)
        IFS=$'\t' read -r proj_id proj_number <<<"$q1_out"
        case "$proj_id" in ''|*[!A-Za-z0-9_]*) proj_id="" ;; esac
        case "$proj_number" in ''|*[!0-9]*) proj_number="" ;; esac
        if [ -n "$proj_id" ] && [ -n "$proj_number" ]; then
          form="ghp"
          harness_ghp_write_probe "$f" "$form" "$proj_id" "$proj_number"
        else
          return 0
        fi
        ;;
      *)
        form="ambiguous"
        harness_ghp_write_probe "$f" "$form"
        ;;
    esac
  else
    form="$(harness_ghp_cache_get "$f" form 2>/dev/null || echo none)"
    proj_id="$(harness_ghp_cache_get "$f" project_id 2>/dev/null || true)"
  fi
  [ "$form" = "ghp" ] && [ -n "${proj_id:-}" ] || return 0

  local counts_interval="${HARNESS_GHP_COUNTS_STALE:-$HARNESS_GHP_COUNTS_STALE_DEFAULT}"
  local fetched_epoch=0 skip_counts=0
  if [ "$mode" = "background" ]; then
    fetched_epoch="$(harness_ghp_cache_get "$f" fetched_epoch 2>/dev/null || echo 0)"
    [ -n "$fetched_epoch" ] 2>/dev/null || fetched_epoch=0
    if [ "$fetched_epoch" -gt 0 ] 2>/dev/null && [ "$(( now - fetched_epoch ))" -lt "$counts_interval" ] 2>/dev/null; then
      skip_counts=1
    fi
  fi
  if [ "$skip_counts" != 1 ]; then
    local q2 q2_out q2_rc a b c d
    q2='query($id:ID!){node(id:$id){... on ProjectV2{
      a: items(first:1, query:"種別:feature status:承認待ち"){totalCount}
      b: items(first:1, query:"status:判断待ち"){totalCount}
      c: items(first:1, query:"is:pr is:open"){totalCount}
      d: items(first:1, query:"status:進行中"){totalCount}
    }}}'
    q2_out="$(gh api graphql -f query="$q2" -f id="$proj_id" \
          --jq '[.data.node.a.totalCount,.data.node.b.totalCount,.data.node.c.totalCount,.data.node.d.totalCount] | @tsv' \
          2>/dev/null)"
    q2_rc=$?
    if [ "$q2_rc" -eq 0 ] && [ -n "$q2_out" ]; then
      IFS=$'\t' read -r a b c d <<<"$q2_out"
      case "$a" in ''|*[!0-9]*) a="" ;; esac
      case "$b" in ''|*[!0-9]*) b="" ;; esac
      case "$c" in ''|*[!0-9]*) c="" ;; esac
      case "$d" in ''|*[!0-9]*) d="" ;; esac
      if [ -n "$a" ] && [ -n "$b" ] && [ -n "$c" ] && [ -n "$d" ]; then
        harness_ghp_write_counts "$f" "$a" "$b" "$c" "$d" "$now"
      fi
    fi
    # 失敗 (gh 非 0 終了・応答が数字 4 つの形でない) はここで既存の counts を書き換えずに
    # 抜ける (fail-open)。
  fi
  return 0
)

# harness_ghp_refresh_async <mode> [root] -> harness_ghp_refresh を detach して呼ぶ。
# SessionStart の 5 秒の hook timeout を、gh の通信で使い切らないようにする
# (scripts/update-check.sh の harness_update_fetch_async と同じ detach の仕方 — fd を
# 全部閉じ、hook 本体の exit を待たずに動かす)。
harness_ghp_refresh_async() (
  set -uo pipefail
  local mode="${1:?}" root="${2:-${CLAUDE_PROJECT_DIR:-$PWD}}"
  { harness_ghp_refresh "$mode" "$root" >/dev/null 2>&1 || true; } >/dev/null 2>&1 </dev/null &
  return 0
)
