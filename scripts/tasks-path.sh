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
# GitHub Project を使う形を持つ (F17)。**両者は排他ではなく、どちらの形で動くかを
# リポごとに見分けるだけ** — harness_tasks_file・harness_open_tasks の名前も意味も
# 変えない (A-3)。台帳の有無では見分けられない (台帳を凍結しつつ Project も持つリポが
# ある。台帳を消す判定にすると、1.x 由来の /new-task 等が台帳を再生成して判定が
# ひっくり返る)。見分ける手がかりは、リポに紐づいた Project が項目「種別」を
# 持つかどうかだけにする (ファイルで切り替えると「設定のファイルは作らない」に触れる)。
#
# 通信する (gh を叩く) のは、次の 2 か所だけ (F19)。
#   ・SessionStart の背景処理 (harness_ghp_refresh background。hooks/session-start.sh から
#     detach して呼ぶ)
#   ・道具 (gh-task 相当。H-4 で実装) が書き込んだ直後 (harness_ghp_refresh now)
# session-start.sh と statusline.sh はここの「読む側」(harness_ghp_line 系) だけを呼び、
# 控えを読むだけで gh は 1 回も呼ばない。
#
# 控えの置き場は $CLAUDE_PLUGIN_DATA (hook・MCP・LSP にしか渡らず、Bash ツールには
# 渡らない: https://code.claude.com/docs/en/plugins-reference の
# "Where each variable resolves") を使わず、$HOME/.claude/plugins/data/<id>/ の形を
# 定数で持つ。<id> は 2.x のマーケットプレイス entry 名 (H-6 で main の marketplace.json
# に足す) を仮に置いたもの — H-6 で実際の entry 名が決まったら、この 1 行を合わせる
# (H-6 の完了条件に含める。ズレていても壊れ方は「控えが前回のまま」で fail-open)。
HARNESS_GHP_ID="hirai-lite-v2"

# 見分けと件数の取り直しの間隔。件数 (a-d) と依存待ちの件数 (e) は毎回の背景処理で
# 取り直す (会話の最初ごと・decision 21)。見分け (このリポが GHP の形かどうか自体) は
# 変わることが稀なので、間隔を空ける (既定 24h。update-check.sh の間隔と同じ考え方)。
HARNESS_GHP_PROBE_INTERVAL_DEFAULT=86400
# 「書いた直後」(now) が e (依存が解けた件数) を取り直すのは、前回の e からこれ以上
# 空いたときだけ (B-22)。背景処理 (background) は毎回取り直す。
HARNESS_GHP_UNBLOCKED_STALE_DEFAULT=600

# harness_ghp_repo_slug [root] -> "<owner>/<repo>" を stdout、無ければ空 + rc 1。
# git remote (origin) から読むだけで、gh は呼ばない (ここは通信しない)。
harness_ghp_repo_slug() (
  set -uo pipefail
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" url
  url="$(git -C "$root" remote get-url origin 2>/dev/null)" || return 1
  [ -n "$url" ] || return 1
  printf '%s' "$url" | sed -E 's#^git@github\.com:##; s#^https?://github\.com/##; s#\.git$##'
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

# harness_ghp_line [root] -> F78/C12 の件数の中身 (見出し語は付けない)。
# 形式: "N（承認 a・裁定 b・取り込み c）／進行中 d／依存が解けた e 件（HH:MM 時点）"
# form が ghp でない・控えが無い・件数が欠けている場合は空 + rc 1 を返す (呼び出し側は
# 台帳の形にフォールバックする)。gh は呼ばない (控えを読むだけ)。
harness_ghp_line() {
  local root="${1:-}" f a b c d e t1 t2 t n
  f="$(harness_ghp_cache_file "$root")"
  [ "$(harness_ghp_cache_get "$f" form)" = "ghp" ] || return 1
  a="$(harness_ghp_cache_get "$f" approve)" || return 1
  b="$(harness_ghp_cache_get "$f" arbitrate)" || return 1
  c="$(harness_ghp_cache_get "$f" ingest)" || return 1
  d="$(harness_ghp_cache_get "$f" in_progress)" || return 1
  e="$(harness_ghp_cache_get "$f" unblocked)" || e="-"
  n=$(( ${a:-0} + ${b:-0} + ${c:-0} )) 2>/dev/null || n="$a"
  t1="$(harness_ghp_cache_get "$f" fetched_at)"
  t2="$(harness_ghp_cache_get "$f" unblocked_fetched_at)"
  # 表示は 2 つの取得時刻のうち古い方 (この行の内容がその時点までしか保証されないため)。
  # bash 3.2 (macOS 既定) には文字列の大小比較演算子が [ ] に無いので、sort で決める
  # (ISO8601 の "YYYY-MM-DDTHH:MM:SSZ" は固定長で、辞書順 = 時刻順になる)。
  if [ -n "$t1" ] && [ -n "$t2" ]; then
    t="$(printf '%s\n%s\n' "$t1" "$t2" | sort | head -1)"
  else
    t="${t1:-$t2}"
  fi
  printf '%s（承認 %s・裁定 %s・取り込み %s）／進行中 %s／依存が解けた %s 件（%s 時点）' \
    "$n" "$a" "$b" "$c" "$d" "$e" "${t:11:5}"
}

# harness_ghp_write_probe <file> <form> [project_id] [project_number] -> 見分けの結果を
# 書く。counts (a-d・e とその取得時刻) は既存の値をそのまま残す (probe だけでは消さない)。
# 連想配列 (bash 4+) は使わない — macOS の既定 /bin/bash は 3.2 で使えないため、
# 個々のフィールドを都度 harness_ghp_cache_get で読み直す (やや冗長だが確実)。
harness_ghp_write_probe() (
  set -uo pipefail
  local f="${1:?}" form="${2:?}" pid="${3:-}" pn="${4:-}"
  local o_a o_b o_c o_d o_e o_fa o_ue o_ue_epoch
  mkdir -p "$(dirname "$f")" 2>/dev/null || return 0
  o_a="$(harness_ghp_cache_get "$f" approve 2>/dev/null || true)"
  o_b="$(harness_ghp_cache_get "$f" arbitrate 2>/dev/null || true)"
  o_c="$(harness_ghp_cache_get "$f" ingest 2>/dev/null || true)"
  o_d="$(harness_ghp_cache_get "$f" in_progress 2>/dev/null || true)"
  o_e="$(harness_ghp_cache_get "$f" unblocked 2>/dev/null || true)"
  o_fa="$(harness_ghp_cache_get "$f" fetched_at 2>/dev/null || true)"
  o_ue="$(harness_ghp_cache_get "$f" unblocked_fetched_at 2>/dev/null || true)"
  o_ue_epoch="$(harness_ghp_cache_get "$f" unblocked_epoch 2>/dev/null || true)"
  [ -n "$pid" ] || pid="$(harness_ghp_cache_get "$f" project_id 2>/dev/null || true)"
  [ -n "$pn" ] || pn="$(harness_ghp_cache_get "$f" project_number 2>/dev/null || true)"
  harness_ghp_write_raw "$f" "$form" "$pid" "$pn" "$o_fa" "$o_a" "$o_b" "$o_c" "$o_d" "$o_e" \
    "$o_ue" "$o_ue_epoch" "$(date -u +%s 2>/dev/null || echo 0)"
)

# harness_ghp_write_counts <file> <approve> <arbitrate> <ingest> <in_progress> -> 件数
# (a-d) と fetched_at を書く。form・project_id・project_number・probed_epoch・
# unblocked 系は既存の値を残す。
harness_ghp_write_counts() (
  set -uo pipefail
  local f="${1:?}" a="${2:-0}" b="${3:-0}" c="${4:-0}" d="${5:-0}"
  local form pid pn o_e o_ue o_ue_epoch o_pe
  form="$(harness_ghp_cache_get "$f" form 2>/dev/null || echo ghp)"
  pid="$(harness_ghp_cache_get "$f" project_id 2>/dev/null || true)"
  pn="$(harness_ghp_cache_get "$f" project_number 2>/dev/null || true)"
  o_e="$(harness_ghp_cache_get "$f" unblocked 2>/dev/null || true)"
  o_ue="$(harness_ghp_cache_get "$f" unblocked_fetched_at 2>/dev/null || true)"
  o_ue_epoch="$(harness_ghp_cache_get "$f" unblocked_epoch 2>/dev/null || true)"
  o_pe="$(harness_ghp_cache_get "$f" probed_epoch 2>/dev/null || echo 0)"
  mkdir -p "$(dirname "$f")" 2>/dev/null || return 0
  harness_ghp_write_raw "$f" "$form" "$pid" "$pn" "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)" \
    "$a" "$b" "$c" "$d" "$o_e" "$o_ue" "$o_ue_epoch" "$o_pe"
)

# harness_ghp_write_unblocked <file> <e> -> 依存が解けた件数と、その取得時刻 (表示用の
# 文字列と、間隔判定用の epoch の両方) を書く。他は既存の値を残す。
harness_ghp_write_unblocked() (
  set -uo pipefail
  local f="${1:?}" e="${2:-0}"
  local form pid pn a b c d fa o_pe
  form="$(harness_ghp_cache_get "$f" form 2>/dev/null || echo ghp)"
  pid="$(harness_ghp_cache_get "$f" project_id 2>/dev/null || true)"
  pn="$(harness_ghp_cache_get "$f" project_number 2>/dev/null || true)"
  a="$(harness_ghp_cache_get "$f" approve 2>/dev/null || true)"
  b="$(harness_ghp_cache_get "$f" arbitrate 2>/dev/null || true)"
  c="$(harness_ghp_cache_get "$f" ingest 2>/dev/null || true)"
  d="$(harness_ghp_cache_get "$f" in_progress 2>/dev/null || true)"
  fa="$(harness_ghp_cache_get "$f" fetched_at 2>/dev/null || true)"
  o_pe="$(harness_ghp_cache_get "$f" probed_epoch 2>/dev/null || echo 0)"
  mkdir -p "$(dirname "$f")" 2>/dev/null || return 0
  harness_ghp_write_raw "$f" "$form" "$pid" "$pn" "$fa" "$a" "$b" "$c" "$d" "$e" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)" "$(date -u +%s 2>/dev/null || echo 0)" "$o_pe"
)

# harness_ghp_write_raw <file> <form> <pid> <pn> <fetched_at> <a> <b> <c> <d> <e>
#   <unblocked_fetched_at> <unblocked_epoch> <probed_epoch> -> 上の 3 つが共有する実際の
# 書き込み。空の値はその key を書かない (呼び出し側が「まだ無い」と「0」を区別できる
# ようにする)。*_epoch は UNIX 時刻の整数 (間隔の計算専用。日時の文字列を逆算しない —
# GNU date の -d と BSD date の -jf は書式が違い、両対応は事故のもとになるため)。
harness_ghp_write_raw() (
  set -uo pipefail
  local f="${1:?}" form="${2:?}" pid="${3:-}" pn="${4:-}" fa="${5:-}" \
        a="${6:-}" b="${7:-}" c="${8:-}" d="${9:-}" e="${10:-}" ue="${11:-}" \
        ue_epoch="${12:-}" pe="${13:-0}" tmp
  tmp="$f.tmp.$$"
  {
    printf '{\n  "form": "%s",\n' "$form"
    [ -n "$pid" ] && printf '  "project_id": "%s",\n' "$pid"
    [ -n "$pn" ] && printf '  "project_number": %s,\n' "$pn"
    [ -n "$fa" ] && printf '  "fetched_at": "%s",\n' "$fa"
    [ -n "$a" ] && printf '  "approve": %s,\n' "$a"
    [ -n "$b" ] && printf '  "arbitrate": %s,\n' "$b"
    [ -n "$c" ] && printf '  "ingest": %s,\n' "$c"
    [ -n "$d" ] && printf '  "in_progress": %s,\n' "$d"
    [ -n "$e" ] && printf '  "unblocked": %s,\n' "$e"
    [ -n "$ue" ] && printf '  "unblocked_fetched_at": "%s",\n' "$ue"
    [ -n "$ue_epoch" ] && printf '  "unblocked_epoch": %s,\n' "$ue_epoch"
    printf '  "probed_epoch": %s\n}\n' "${pe:-0}"
  } > "$tmp" 2>/dev/null && mv -f "$tmp" "$f" 2>/dev/null
)

# harness_ghp_refresh <background|now> [root] -> 常に rc 0 (fail-open)。
# gh を叩く唯一の入り口。gh 不在・git remote 不在・GHP でないリポでは、静かに抜ける。
#
#   1. 見分け (form): 前回の probed_epoch から HARNESS_GHP_PROBE_INTERVAL 秒 (既定 24h)
#      経っていなければ飛ばす。経っていれば、リポに紐づく Project (Repository.projectsV2。
#      この向き — リポからの紐づけ — は未検証: F18 が別に指摘している) のうち、項目
#      「種別」を持つ最初の 1 件を採用する (無ければ "none"。台帳の形かどうかは呼び出し側
#      — session-start.sh — が harness_tasks_file の有無で判定するので、ここでは
#      "none" と書くだけにする)。
#   2. counts (a-d): form が ghp のときだけ、totalCount を 1 回の GraphQL 呼び出しで
#      別名で並べて取る (F19)。
#   3. unblocked (e): background のときは毎回。now のときは、前回の
#      unblocked_epoch から HARNESS_GHP_UNBLOCKED_STALE 秒 (既定 10 分) より
#      古いときだけ取る (B-22)。
#      **注記 (未検証・簡略化)**: 「依存が解けた」件数の厳密な定義 (decision 21 — 依存待ちの
#      うち、止めていた依存が閉じたもの) は、各件の blocked-by を突き合わせる専用の
#      一覧スクリプトの仕事で、それは H-4 (道具) 以降に作る。ここでは同じ枠に載せる
#      ため、当面 status:依存待ち の totalCount を代用する (上振れの近似)。突き合わせの
#      道具ができたら、この 1 か所を差し替える。
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
    local q1 tsv proj_number
    q1='query($o:String!,$r:String!){repository(owner:$o,name:$r){projectsV2(first:20){nodes{id number fields(first:30){nodes{... on ProjectV2FieldCommon{name}}}}}}}'
    tsv="$(gh api graphql -f query="$q1" -F o="$owner" -F r="$repo" \
          --jq '.data.repository.projectsV2.nodes[] | select([.fields.nodes[]?.name] | index("種別")) | [.id,.number] | @tsv' \
          2>/dev/null | head -1)"
    if [ -n "$tsv" ]; then
      IFS=$'\t' read -r proj_id proj_number <<<"$tsv"
      form="ghp"
      harness_ghp_write_probe "$f" "$form" "$proj_id" "$proj_number"
    else
      form="none"
      harness_ghp_write_probe "$f" "$form"
    fi
  else
    form="$(harness_ghp_cache_get "$f" form 2>/dev/null || echo none)"
    proj_id="$(harness_ghp_cache_get "$f" project_id 2>/dev/null || true)"
  fi
  [ "$form" = "ghp" ] && [ -n "${proj_id:-}" ] || return 0

  local q2 tsv2 a b c d
  q2='query($id:ID!){node(id:$id){... on ProjectV2{
    a: items(first:1, query:"種別:feature status:承認待ち"){totalCount}
    b: items(first:1, query:"status:判断待ち"){totalCount}
    c: items(first:1, query:"is:pr is:open"){totalCount}
    d: items(first:1, query:"status:進行中"){totalCount}
  }}}'
  tsv2="$(gh api graphql -f query="$q2" -F id="$proj_id" \
        --jq '[.data.node.a.totalCount,.data.node.b.totalCount,.data.node.c.totalCount,.data.node.d.totalCount] | @tsv' \
        2>/dev/null)"
  if [ -n "$tsv2" ]; then
    IFS=$'\t' read -r a b c d <<<"$tsv2"
    harness_ghp_write_counts "$f" "${a:-0}" "${b:-0}" "${c:-0}" "${d:-0}"
  fi

  local do_e=0
  if [ "$mode" = "background" ]; then
    do_e=1
  else
    local ue_epoch stale="${HARNESS_GHP_UNBLOCKED_STALE:-$HARNESS_GHP_UNBLOCKED_STALE_DEFAULT}"
    ue_epoch="$(harness_ghp_cache_get "$f" unblocked_epoch 2>/dev/null || echo 0)"
    [ -n "$ue_epoch" ] 2>/dev/null || ue_epoch=0
    if [ "$ue_epoch" -eq 0 ] 2>/dev/null || [ "$(( now - ue_epoch ))" -ge "$stale" ] 2>/dev/null; then
      do_e=1
    fi
  fi
  if [ "$do_e" = 1 ]; then
    local q3 e
    q3='query($id:ID!){node(id:$id){... on ProjectV2{ e: items(first:1, query:"status:依存待ち"){totalCount} }}}'
    e="$(gh api graphql -f query="$q3" -F id="$proj_id" --jq '.data.node.e.totalCount' 2>/dev/null)"
    [ -n "$e" ] && harness_ghp_write_unblocked "$f" "$e"
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
