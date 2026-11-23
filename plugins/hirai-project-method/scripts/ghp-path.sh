#!/usr/bin/env bash
# hirai-project-method の GitHub Project 用の関数。source して使う（土台の scripts/tasks-path.sh から分けた）。
# 土台（hirai-lite）の関数（harness_tasks_file など）には依存しない。ここは gh と git remote と
# 控えのファイルだけを見る。
#
# file-top に set -e / set -o pipefail を書かない。source 元の shell flags を汚染し、
# パイプ先の早期終了で呼び出し元ごと落ちる事故を防ぐため (関数内で局所化する)。
#
# 呼び出し元: bin/hirai-task（refresh_board_counts が harness_ghp_refresh now、`hirai-task line` が
# harness_ghp_line と harness_ghp_refresh_async background）。土台の session-start・statusline は
# この関数を直接呼ばず、installed_plugins.json から引いた絶対 path で `hirai-task line` を呼ぶ（hook の PATH に
# プラグインの bin は無い）。

# --- GHP (GitHub Project) の形 -------------------------------------------------
# どの形で動くか (台帳か GitHub Project か) は、土台の `.claude/mode.yml` の `tasks:` が決める
# (土台の harness_tasks_form)。ここは自動では見分けない。この関数群が控えに書く form
# ("ghp" / "none" / "ambiguous") は、リポに紐づいた Project が項目「種別」を持つかの実測で、
# `hirai-task line` が件数を出してよいかの判定にだけ使う。紐づく Project が 2 件以上あるときは、
# どれを使うか決め打ちせず "ambiguous" にして件数を出さない。
#
# 通信する (gh を叩く) のは、次の 2 か所だけにする。
#   ・背景の取り直し (harness_ghp_refresh background。`hirai-task line` が detach して呼ぶ。
#     土台の hooks/session-start.sh と scripts/statusline.sh が `line` を呼ぶ)
#   ・書き込み用の道具 (bin/hirai-task。refresh_board_counts) が書き込んだ直後
#     (harness_ghp_refresh now)
# `line` の 1 行は、ここの「読む側」(harness_ghp_line) だけで作る (gh は呼ばない)。
#
# 控えの置き場は $CLAUDE_PLUGIN_DATA (hook・MCP・LSP にしか渡らず、Bash ツールには
# 渡らない: https://code.claude.com/docs/en/plugins-reference の
# "Where each variable resolves") を使わず、$HOME/.claude/plugins/data/<id>/ の形を
# 定数で持つ。<id> は Claude Code が entry 名とカタログ名から作るディレクトリ名
# (<entry 名>-<カタログ名>。実測: 偽の HOME に hirai-lite@hirai-lite と
# hirai-lite-v2@hirai-lite を入れると data/ に hirai-lite-hirai-lite と
# hirai-lite-v2-hirai-lite ができる)。このプラグインの entry 名 (hirai-project-method) と
# カタログ名 (hirai-lite) が変わったら、この 1 行を合わせる
# (plugins/hirai-project-method/tests/smoke.sh が marketplace.json の entry 名と突き合わせる。
# ズレていても壊れ方は「控えが前回のまま」で fail-open)。
HARNESS_GHP_ID="hirai-project-method-hirai-lite"

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
#      決め打ちせず "ambiguous" にする (どの形で動くかは土台の
#      mode.yml の tasks: が決めるので、ここでは "none"/"ambiguous" と書くだけにする)。
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
