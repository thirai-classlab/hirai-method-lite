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
#   進め方   : HC_MODE (env) > <root>/.claude/mode.yml の mode > $HOME/.claude/mode.yml の mode > normal (項目ごとに引く)
#   入れ替え : HC_AUTO_SYNC (env) > 項目ごとに プロジェクト > ホーム の auto_sync > off (既定は入れ替えない)
#   形       : HC_TASKS (env) > 項目ごとに プロジェクト > ホーム の tasks (ledger / github-project) > ledger
#   ルール   : HARNESS_RULES_DIR > <root>/.claude/rules > $HOME/.claude/rules > <root>/.claude/rules
#
# file-top に set -e / set -o pipefail を書かない。source 元の shell flags を汚染し、
# パイプ先の早期終了で呼び出し元ごと落ちる事故を防ぐため (関数内で局所化する)。

# harness_root [dir] -> dir を含む git の toplevel を stdout。git でなければ dir のまま。常に rc 0。
# .claude/mode.yml を読む・書く関数は全部これを通す (サブディレクトリの .claude/mode.yml は読まない。
# worktree-guard・hirai-notify・orca-context と同じ root)。dir 直下に .git があれば toplevel なので
# git を打たない (解いた root を渡し直しても 2 回目は git を呼ばない)。
harness_root() {
  local d="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" t
  if [ -e "$d/.git" ]; then
    printf '%s' "${d%/}"
    return 0
  fi
  t="$(git -C "$d" rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "$t" ]; then printf '%s' "$t"; else printf '%s' "$d"; fi
  return 0
}

# harness_tasks_file [dir] -> 台帳パスを stdout、無ければ空 + rc 1
# 渡された dir に既にあればそれ、無ければ harness_root の下で探す。
harness_tasks_file() {
  local d="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" r p
  if [ -n "${HARNESS_TASKS_FILE:-}" ]; then
    printf '%s' "$HARNESS_TASKS_FILE"
    return 0
  fi
  r="$(harness_root "$d")"
  for p in "$d/docs/tasks/list.md" "$d/.claude/tasks/list.md" "$r/docs/tasks/list.md" "$r/.claude/tasks/list.md"; do
    if [ -f "$p" ]; then
      printf '%s' "$p"
      return 0
    fi
  done
  return 1
}

# harness_draft_dir [dir] -> 設計 draft の置き場を stdout (末尾スラッシュなし)
# 既にある dir (渡された dir → harness_root の順)。無ければ harness_root の下の作るべき場所。
harness_draft_dir() {
  local d="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" r p
  if [ -n "${HARNESS_DRAFT_DIR:-}" ]; then
    printf '%s' "$HARNESS_DRAFT_DIR"
    return 0
  fi
  r="$(harness_root "$d")"
  for p in "$d/docs/draft" "$d/.claude/draft" "$r/docs/draft" "$r/.claude/draft"; do
    if [ -d "$p" ]; then
      printf '%s' "$p"
      return 0
    fi
  done
  if [ -d "$r/docs" ]; then printf '%s' "$r/docs/draft"; else printf '%s' "$r/.claude/draft"; fi
}

# harness_incidents_file [dir] -> 事故記録 (T2) のパスを stdout
harness_incidents_file() {
  local d="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" r p
  if [ -n "${HARNESS_INCIDENTS_FILE:-}" ]; then
    printf '%s' "$HARNESS_INCIDENTS_FILE"
    return 0
  fi
  r="$(harness_root "$d")"
  for p in "$d/docs/rules-reference/incidents.md" "$d/.claude/rules-reference/incidents.md" "$r/docs/rules-reference/incidents.md" "$r/.claude/rules-reference/incidents.md"; do
    if [ -f "$p" ]; then
      printf '%s' "$p"
      return 0
    fi
  done
  if [ -d "$r/docs" ]; then
    printf '%s' "$r/docs/rules-reference/incidents.md"
  else
    printf '%s' "$r/.claude/rules-reference/incidents.md"
  fi
}

# --- 進め方 (mode) ------------------------------------------------------------
# 読む側 (SessionStart / 画面下部) と書く側 (/config) が別々の順で解決すると、
# 「セッション冒頭は normal・画面下部は loop」のように食い違う。3 箇所ともここを通す。

# harness_mode_file [root] -> すでに在る mode.yml のパスを stdout。
# プロジェクト側 → ホーム側の順で探し、どちらにも無ければ空 + rc 1。
harness_mode_file() {
  local root p
  root="$(harness_root "${1:-${CLAUDE_PROJECT_DIR:-$PWD}}")"
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
  local root p
  root="$(harness_root "${1:-${CLAUDE_PROJECT_DIR:-$PWD}}")"
  if p="$(harness_mode_file "$root")"; then
    printf '%s' "$p"
    return 0
  fi
  printf '%s' "$root/.claude/mode.yml"
}

# harness_mode [root] -> いまの進め方 (normal / loop / 未知の値) を stdout。常に rc 0。
# env HC_MODE > プロジェクトの mode.yml の mode: > ホームの mode.yml の mode: > normal。
# 項目ごとに引く (プロジェクト側に mode: が無ければホーム側の値を使う)。読めない・空・壊れている場合も normal。
harness_mode() {
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" m=""
  if [ -n "${HC_MODE:-}" ]; then
    printf '%s' "$HC_MODE"
    return 0
  fi
  m="$(harness_yml_value "$root" mode)"
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
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" v=""
  if [ -n "${HC_AUTO_SYNC:-}" ]; then
    printf '%s' "$HC_AUTO_SYNC"
    return 0
  fi
  v="$(harness_yml_value "$root" auto_sync)"
  [ -n "$v" ] || v="off"
  printf '%s' "$v"
}

# --- タスク管理の形 (tasks) ---------------------------------------------------
# 台帳 (ledger) と GitHub Project (github-project) のどちらで回すかは、リポごとに
# .claude/mode.yml の tasks: で**宣言する**。Project の有無・remote・gh の成否からは見分けない
# (見分けに失敗して尋ねて止まる道を無くすため)。GraphQL を打つのは github-project のときだけ。

# harness_yml_file_value <file> <キー> -> その file の <キー>: の値を stdout。無ければ空。常に rc 0。
# 値の前後の空白と引用符 (" と ') と、行末のコメント (空白のあとの # から) を外す。
harness_yml_file_value() {
  local f="${1:-}" k="${2:-}"
  [ -n "$k" ] && [ -f "$f" ] || return 0
  sed -nE "s/^[[:space:]]*${k}:[[:space:]]*(.*)\$/\\1/p" "$f" 2>/dev/null | head -1 \
    | sed -E 's/(^|[[:space:]]+)#.*$//; s/[[:space:]]+$//; s/^"(.*)"$/\1/; s/^'"'"'(.*)'"'"'$/\1/'
}

# harness_yml_value <root> <キー> -> <キー>: の値を stdout。無ければ空。常に rc 0。
# 項目ごとに「プロジェクトの .claude/mode.yml → ホームの ~/.claude/mode.yml」の順で引く
# (片方のファイルだけを読まない。env の上書きと既定は呼び出し側で扱う)。
harness_yml_value() {
  local root k="${2:-}" v="" p
  [ -n "$k" ] || return 0
  root="$(harness_root "${1:-${CLAUDE_PROJECT_DIR:-$PWD}}")"
  for p in "$root/.claude/mode.yml" "${HOME:+$HOME/.claude/mode.yml}"; do
    [ -n "$p" ] || continue
    v="$(harness_yml_file_value "$p" "$k")"
    [ -z "$v" ] || break
  done
  printf '%s' "$v"
}

# harness_tasks_form [root] -> ledger / github-project を stdout。常に rc 0。
# 解決順は HC_TASKS (env) > mode.yml の tasks: > ledger。
# 項目が無い・空・未知の値は ledger (台帳。1.x と同じ動き)。
harness_tasks_form() {
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" v
  v="${HC_TASKS:-}"
  [ -n "$v" ] || v="$(harness_yml_value "$root" tasks)"
  case "$v" in
    github-project) printf 'github-project' ;;
    *) printf 'ledger' ;;
  esac
  return 0
}

# harness_tasks_slug [root] -> origin の github.com の owner/repo から末尾の .git と / を外し、/ を - にした名前を stdout。
# 2.x の控えの名前と同じ作り方。github.com 以外・remote 無しは空。常に rc 0。
harness_tasks_slug() {
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" url
  url="$(git -C "$root" remote get-url origin 2>/dev/null || true)"
  case "$url" in
    *github.com*) printf '%s' "$url" | sed -E 's#^.*github\.com[:/]##; s#\.git$##; s#/+$##; s#/#-#g' 2>/dev/null ;;
  esac
  return 0
}

# harness_tasks_migrate [root] -> プロジェクトの .claude/mode.yml に tasks: が無いときだけ、1 度だけ書き込む
# (/hirai-lite:update の手順 2b)。tasks: はプロジェクト側にだけ書く (ホームには書かない。ホームの値は他のリポにも効くため)。
# 2.x (hirai-lite-v2) の痕跡は、このリポの slug の控え (~/.claude/plugins/data/hirai-lite-v2-hirai-lite/
# tasks-<slug>.json) だけで見る (機械全体で見ない。別のリポの控えで書かない)。
#   控えの form が ghp                 -> github-project を書く
#   控えが在り form が ghp 以外        -> ledger を書く。ただしプロジェクト側に mode.yml が無いときは書かない
#                                         (ledger は既定と同じ。新しい .claude/ を作ると mode の書き込み先がそこへ移る)
#   控えが無い                          -> 書かない
# 出力は 1 行 (書いたら "tasks: <値> を <パス> に書きました (<理由>)"、書かなければ "tasks: 書きませんでした (<理由>)")。
# プロジェクト側にすでに tasks: があれば何もしない (無出力・rc 0)。書けなかったら rc 1。以後は自動で見分けない。
harness_tasks_migrate() {
  local root cur f slug cache val why
  root="$(harness_root "${1:-${CLAUDE_PROJECT_DIR:-$PWD}}")"
  f="$root/.claude/mode.yml"
  cur="$(harness_yml_file_value "$f" tasks)"
  [ -z "$cur" ] || return 0
  slug="$(harness_tasks_slug "$root")"
  cache=""
  [ -z "$slug" ] || cache="$HOME/.claude/plugins/data/hirai-lite-v2-hirai-lite/tasks-${slug}.json"
  if [ -z "$cache" ] || [ ! -f "$cache" ]; then
    printf 'tasks: 書きませんでした (2.x の Project の控えが無い。tasks: が無ければ ledger で動く。GitHub Project にするなら /hirai-lite:config の項目 8)\n'
    return 0
  fi
  if grep -Eq '"form"[[:space:]]*:[[:space:]]*"ghp"' "$cache" 2>/dev/null; then
    val="github-project"; why="2.x の Project の控え ($cache) が ghp のため"
  else
    val="ledger"; why="2.x の控え ($cache) が ghp ではないため"
    if [ ! -f "$f" ]; then
      printf 'tasks: 書きませんでした (ledger は既定と同じで、このリポに .claude/mode.yml が無い。新しく作らない)\n'
      return 0
    fi
  fi
  harness_yml_set "$f" tasks "$val" || return 1
  printf 'tasks: %s を %s に書きました (%s)\n' "$val" "$f" "$why"
}

# harness_pm_install_dir [root] -> 足すプラグイン hirai-project-method の、このリポの行のうち版が最大の installPath を stdout。
# 無ければ空 + rc 1 (python3 か installed_plugins.json が無いときも rc 1)。
# このリポの enabledPlugins (settings.local.json → settings.json → ~/.claude/settings.json の順) で false なら「無い」とみなす。
# 「このリポの行」= scope が user・managed の行、または projectPath がこのリポと同じ git のリポの行。
# 同じ git のリポかは `git rev-parse --git-common-dir` (両方) が同じかで見る。worktree W1 で project の範囲に入れた行は、
# 本体の checkout・ほかの worktree からも同じリポとして当たる。projectPath が無い・git でないとき (消えた worktree など) だけ
# root との前方一致に落とす。行の絞りはここ 1 か所 (hirai-task の path・更新の知らせ・/update の見分けが使う)。
harness_pm_install_dir() {
  local root f="${HOME:-}/.claude/plugins/installed_plugins.json" p common
  root="$(harness_root "${1:-${CLAUDE_PROJECT_DIR:-$PWD}}")"
  [ -f "$f" ] && command -v python3 >/dev/null 2>&1 || return 1
  common="$(git -C "$root" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
  p="$(python3 -c 'import json,os,re,subprocess,sys
d = json.load(open(sys.argv[1]))
root = os.path.realpath(sys.argv[3]).rstrip("/")
common = os.path.realpath(sys.argv[4]) if sys.argv[4] else ""
def gc(path):
    try:
        o = subprocess.run(["git", "-C", path, "rev-parse", "--path-format=absolute", "--git-common-dir"], capture_output=True, text=True, timeout=5)
        return os.path.realpath(o.stdout.strip()) if o.returncode == 0 and o.stdout.strip() else ""
    except Exception:
        return ""
def disabled():
    # enabledPlugins で false なら「無い」とみなす。優先は local -> project -> user (最初に載っている値が決める)。
    for sp in (os.path.join(root, ".claude", "settings.local.json"), os.path.join(root, ".claude", "settings.json"), os.path.join(os.path.expanduser("~"), ".claude", "settings.json")):
        try:
            ep = json.load(open(sp)).get("enabledPlugins") or {}
        except Exception:
            continue
        for k, v in ep.items():
            if k.split("@", 1)[0] == sys.argv[2] and isinstance(v, bool):
                return v is False
    return False
def mine(x):
    if x.get("scope") in ("user", "managed"):
        return True
    pp = str(x.get("projectPath") or "").rstrip("/")
    if not pp:
        return False
    g = gc(pp) if os.path.isdir(pp) else ""
    if g and common:
        return g == common
    ppr = os.path.realpath(pp).rstrip("/")
    return root == ppr or root.startswith(ppr + "/")
rows = [] if disabled() else [x for k, v in d.get("plugins", {}).items() if k.split("@", 1)[0] == sys.argv[2] for x in v if x.get("installPath") and mine(x)]
rows.sort(key=lambda x: [int(n) if n.isdigit() else 0 for n in re.split(r"[.]", str(x.get("version", "0")).split("-", 1)[0])])
print(rows[-1]["installPath"] if rows else "")' "$f" hirai-project-method "$root" "$common" 2>/dev/null)"
  [ -n "$p" ] || return 1
  printf '%s' "$p"
}

# harness_pm_task_bin [root] -> 足すプラグイン hirai-project-method の hirai-task の絶対 path を stdout。無ければ空 + rc 1。
# hook と画面下では、プラグインの bin/ は PATH に入らない (Bash ツールだけに入る)。PATH に頼らず探す:
#   1. harness_pm_install_dir (installed_plugins.json のこのリポの行の最大版) の bin/hirai-task
#   2. python3 が無いとき・installed_plugins.json が無いときだけ ~/.claude/plugins/cache/hirai-lite/hirai-project-method/ の最大版
#      (installed に行があるのに該当が無い = 外した・別のリポの install、のときは cache へ落ちない。入れ方を示して止まる側へ倒す)
#   3. PATH の hirai-task
harness_pm_task_bin() {
  local root="${1:-${CLAUDE_PROJECT_DIR:-$PWD}}" f="${HOME:-}/.claude/plugins/installed_plugins.json" p="" c
  if [ -f "$f" ] && command -v python3 >/dev/null 2>&1; then
    p="$(harness_pm_install_dir "$root" 2>/dev/null || true)"
    if [ -n "$p" ] && [ -x "$p/bin/hirai-task" ]; then
      printf '%s' "$p/bin/hirai-task"
      return 0
    fi
  else
    c="$(ls -d "${HOME:-}"/.claude/plugins/cache/hirai-lite/hirai-project-method/*/ 2>/dev/null | sort -V | tail -1)"
    c="${c%/}"
    if [ -n "$c" ] && [ -x "$c/bin/hirai-task" ]; then
      printf '%s' "$c/bin/hirai-task"
      return 0
    fi
  fi
  c="$(command -v hirai-task 2>/dev/null || true)"
  if [ -n "$c" ]; then
    printf '%s' "$c"
    return 0
  fi
  return 1
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
  local root p
  root="$(harness_root "${1:-${CLAUDE_PROJECT_DIR:-$PWD}}")"
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
