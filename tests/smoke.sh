#!/usr/bin/env bash
# ハーネス自己検証 smoke (10 case)。1 件でも FAIL なら exit 1。
# 予算監査 (case 4-6) は不可逆操作ではないため hook にせず本 smoke で担保する (設計 §4.7)。
#
# 走らせる場所はプラグインのリポジトリ直下。
#   ROOT = $CLAUDE_PLUGIN_ROOT > このスクリプトの 1 つ上 ($BASH_SOURCE 起点)
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$ROOT" ] || [ ! -d "$ROOT" ]; then ROOT="$(cd "$here/.." && pwd)"; fi
HOOKS="$ROOT/hooks"
FAILED=0

# T0 (常時ロード = frontmatter に paths: を持たない rule) に居てよいファイルの許可リスト。
# 層を変える (T0 昇格 / T1 降格) ときはここを更新する。
T0_ALLOWLIST="_meta.md core.md"
T0_MAX=3

# T0 予算は 2 段階。WARN を超えたら PASS のまま警告を出し (余裕があるうちに降格を決める)、
# MAX を超えたら FAIL にして追加を止める。上限を上げても「既定は入れない」原則は変えない
# (_meta.md 条 2: 新規は T1 が既定、T0 にするには立証が要る)。
T0_BUDGET_WARN=6000
T0_BUDGET_MAX=10000

# smoke 自体は外部通信しない。更新検知を要する case 7/8 だけが個別に on を渡す。
export HARNESS_UPDATE_CHECK=off

pass() { echo "PASS  case $1: $2"; }
fail() { echo "FAIL  case $1: $2 -- $3"; FAILED=1; }

# frontmatter (先頭 --- から次の --- まで) の中に paths: キーがあれば exit 0、無ければ exit 1。
# 「1 行目が --- か」ではなくキーの有無で判定するため、--- fence だけ残して paths: を消した
# ケースも T0 として検出できる。
has_paths_key() {
  awk '
    NR == 1 { if ($0 != "---") exit; next }
    /^---[[:space:]]*$/ { exit }
    /^paths:/ { found = 1; exit }
    END { exit(found ? 0 : 1) }
  ' "$1" 2>/dev/null
}

# 画面下部は 2 行構成。1 行目 = いまの状態 / 2 行目 = 次にできる操作 (設定リンクは常時表示)。
SL_LINK='設定を確認・変更 → /hirai-lite:config'

# sl_shape <画面下部の出力> -> 2 行かつ 2 行目が設定リンクで始まれば rc 0、違えば理由を stdout
sl_shape() {
  local out="$1" n l2
  n="$(printf '%s\n' "$out" | grep -c . || true)"
  if [ "${n:-0}" -ne 2 ]; then printf '2 行ではない (%s 行): %s' "$n" "$out"; return 1; fi
  l2="$(printf '%s\n' "$out" | sed -n '2p')"
  case "$l2" in
    "$SL_LINK"*) return 0 ;;
    *) printf '2 行目が設定リンクで始まっていない: %s' "$l2"; return 1 ;;
  esac
}

# ---------- case 1: session-start.sh は対象ファイル不在でも exit 0 ----------
case_1() {
  local tmp out rc
  tmp="$(mktemp -d)"; mkdir -p "$tmp/hooks"
  cp "$HOOKS/session-start.sh" "$tmp/hooks/" 2>/dev/null
  out="$(CLAUDE_PLUGIN_ROOT="$tmp" CLAUDE_PROJECT_DIR="$tmp" bash "$tmp/hooks/session-start.sh" 2>&1)"; rc=$?
  local lines; lines="$(printf '%s\n' "$out" | grep -c . || true)"
  rm -rf "$tmp"
  if [ "$rc" -ne 0 ]; then fail 1 "session-start exit 0 (対象ファイル不在)" "exit=$rc"; return; fi
  if [ "${lines:-0}" -lt 1 ]; then fail 1 "session-start は 1 行以上出力" "0 行 (無出力)"; return; fi
  if [ "${lines:-0}" -gt 5 ]; then fail 1 "session-start 出力 5 行以内" "${lines} 行"; return; fi
  if ! printf '%s\n' "$out" | grep -q '\[harness\]'; then
    fail 1 "session-start 出力に [harness] prefix" "prefix 不在: $out"; return
  fi

  # statusline.sh も同じ fail-open。空 stdin / 壊れた JSON / お知らせの控えが不在・空・壊れ、
  # いずれでも 2 行 + exit 0 を返し、2 行目の設定リンクは常時出る
  # (画面下部が消えたり行数が崩れたり、設定の入口が見えなくなったりしない)。
  local sl="$ROOT/scripts/statusline.sh" std sout src why
  if [ ! -f "$sl" ]; then fail 1 "statusline.sh が存在する" "$sl が無い"; return; fi
  std="$(mktemp -d)"
  for src in '' '{"model":' 'zzz' '{"model":{"display_name":"X"},"context_window":{"used_percentage":12}}'; do
    sout="$(printf '%s' "$src" | TMPDIR="$std" NO_COLOR=1 CLAUDE_PROJECT_DIR="$std" \
          HARNESS_UPDATE_CHECK=on bash "$sl" 2>&1)"; rc=$?
    why="$(sl_shape "$sout")" || true
    if [ "$rc" -ne 0 ] || [ -n "$why" ]; then
      rm -rf "$std"
      fail 1 "statusline は常に 2 行 + 設定リンク常時 + exit 0" "入力[${src}] exit=${rc} ${why}"; return
    fi
  done
  # 色を落としても意味が読み取れる (NO_COLOR 指定時に制御文字を 1 つも出さない)
  sout="$(printf '{"model":{"display_name":"X"},"context_window":{"used_percentage":85}}' \
        | TMPDIR="$std" NO_COLOR=1 CLAUDE_PROJECT_DIR="$std" bash "$sl" 2>&1)"
  if printf '%s' "$sout" | grep -q $'\033'; then
    rm -rf "$std"; fail 1 "NO_COLOR で色を出さない" "制御文字が残っている"; return
  fi
  # 色ありでも行数と語は変わらない (色は補助であって情報を持たない)
  sout="$(printf '{"model":{"display_name":"X"},"context_window":{"used_percentage":85}}' \
        | TMPDIR="$std" CLAUDE_PROJECT_DIR="$std" bash "$sl" 2>&1)"; rc=$?
  if ! printf '%s' "$sout" | grep -q $'\033'; then
    rm -rf "$std"; fail 1 "色ありでは色を出す" "制御文字が無い"; return
  fi
  why="$(sl_shape "$(printf '%s' "$sout" | sed $'s/\033\\[[0-9;]*m//g')")" || true
  if [ "$rc" -ne 0 ] || [ -n "$why" ]; then
    rm -rf "$std"; fail 1 "色を落としても 2 行 + 設定リンク" "exit=${rc} ${why}"; return
  fi
  # 空の控え = 更新なし扱い (中身が消し損ねの空ファイルでも嘘の通知を出さない)
  mkdir -p "$std/claude-harness-lite" && : > "$std/claude-harness-lite/update-available"
  sout="$(printf '{"context_window":{"used_percentage":12}}' \
        | TMPDIR="$std" NO_COLOR=1 CLAUDE_PROJECT_DIR="$std" HARNESS_UPDATE_CHECK=on bash "$sl" 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ] || printf '%s' "$sout" | grep -q '更新あり'; then
    rm -rf "$std"; fail 1 "空の控えでは更新を知らせない" "exit=${rc}: $sout"; return
  fi
  # 壊れた控え + 壊れた JSON の同時発生でも 2 行 + exit 0
  printf '\001garbage\002' > "$std/claude-harness-lite/update-available"
  sout="$(printf 'not json' | TMPDIR="$std" NO_COLOR=1 CLAUDE_PROJECT_DIR="$std" bash "$sl" 2>&1)"; rc=$?
  why="$(sl_shape "$sout")" || true
  rm -rf "$std"
  if [ "$rc" -ne 0 ] || [ -n "$why" ]; then
    fail 1 "壊れた控え + 壊れた JSON でも 2 行 + exit 0" "exit=${rc} ${why}"; return
  fi

  # 進め方 (mode) の一致検査。セッション冒頭 (session-start.sh) と画面下部 (statusline.sh) が
  # 別々に mode.yml を探すと、片方だけホーム側を見て「冒頭は normal・下部は loop」と食い違う
  # (v1.0.0 の実害)。両者を scripts/tasks-path.sh の harness_mode 1 本に通したことを、
  # 置き場 4 通り (ホームのみ / プロジェクトのみ / 両方 / どちらも無し) で確かめる。
  # 期待値は「正式名（解説）」の表記 (v1.6.0) — 解説だけ / 正式名だけに戻すと FAIL する。
  local mw mhome mproj want got_s got_l where
  mw="$(mktemp -d)"; mkdir -p "$mw/home/.claude" "$mw/proj/.claude" "$mw/plug"
  cp -R "$ROOT/scripts" "$mw/plug/" 2>/dev/null
  mkdir -p "$mw/plug/hooks" && cp "$HOOKS/session-start.sh" "$mw/plug/hooks/" 2>/dev/null
  # <ホーム側> <プロジェクト側> <期待する進め方> ("-" は mode.yml を置かない)
  while read -r mhome mproj want where; do
    [ -n "$mhome" ] || continue
    rm -f "$mw/home/.claude/mode.yml" "$mw/proj/.claude/mode.yml"
    [ "$mhome" = "-" ] || printf 'mode: %s\n' "$mhome" > "$mw/home/.claude/mode.yml"
    [ "$mproj" = "-" ] || printf 'mode: %s\n' "$mproj" > "$mw/proj/.claude/mode.yml"
    got_s="$(HOME="$mw/home" CLAUDE_PLUGIN_ROOT="$mw/plug" CLAUDE_PROJECT_DIR="$mw/proj" \
             bash "$mw/plug/hooks/session-start.sh" 2>/dev/null | sed -n '1s/.*進め方: \([^ ]*\).*/\1/p')"
    got_l="$(printf '%s' '{"context_window":{"used_percentage":12}}' \
             | HOME="$mw/home" NO_COLOR=1 TMPDIR="$mw/tmp" CLAUDE_PROJECT_DIR="$mw/proj" \
               bash "$mw/plug/scripts/statusline.sh" 2>/dev/null | sed -n 's/.*mode: \([^ |]*\).*/\1/p')"
    if [ "$got_s" != "$want" ] || [ "$got_l" != "$want" ]; then
      rm -rf "$mw"
      fail 1 "進め方は冒頭と画面下部で一致 (${where})" \
        "期待=${want} 冒頭=${got_s:-無} 画面下部=${got_l:-無}"; return
    fi
  done <<'EOF'
loop   -      loop（自動で進む）   ホームのみ
-      loop   loop（自動で進む）   プロジェクトのみ
normal loop   loop（自動で進む）   両方あればプロジェクト側
loop   normal normal（確認あり）   両方あればプロジェクト側
-      -      normal（確認あり）   どちらも無し
EOF
  # /config の書き込み先: ホーム側だけに在るならプロジェクト側に新設しない
  rm -f "$mw/home/.claude/mode.yml" "$mw/proj/.claude/mode.yml"
  printf 'mode: normal\n' > "$mw/home/.claude/mode.yml"
  local wf
  wf="$(HOME="$mw/home" bash -c '. "$1/scripts/tasks-path.sh"; harness_mode_write_file "$2"' _ "$mw/plug" "$mw/proj" 2>/dev/null)"
  if [ "$wf" != "$mw/home/.claude/mode.yml" ]; then
    rm -rf "$mw"; fail 1 "/config はすでに在る側に書く" "書き込み先=${wf:-無} (期待: ホーム側)"; return
  fi
  rm -rf "$mw"

  # 書類の置き場は常に docs/。v1.7.0 までに導入した環境は .claude/ の下にあるので
  # /update の手順 2 が docs/ へ移す。その手順書 (commands/update.md の 2-2) の bash を
  # **逐語に取り出して**実行し、(a) 移した中身が 1 バイトも変わらない (b) 移動先に同名が在れば
  # 上書きせず両方残す (c) 空になった置き場だけ消える (d) 移行後にセッション冒頭と画面下部が
  # 移した先 (docs/) の台帳を読む、を確かめる。手順書そのものを走らせるので、
  # 文書と実挙動が離れた時点でここが落ちる。
  local mg blk out2 rc2 bad2="" f2
  blk="$(awk '/^### 2-2\./ {f=1} f && /^```bash$/ {c=1; next} c && /^```$/ {exit} c' "$ROOT/commands/update.md")"
  if ! printf '%s' "$blk" | grep -q '^mvdir .claude/tasks'; then
    fail 1 "/update 手順 2-2 の移行手順を取り出せる" "commands/update.md から取り出せない"; return
  fi
  mg="$(mktemp -d)"
  mkdir -p "$mg/proj/.claude/tasks" "$mg/proj/.claude/draft" "$mg/proj/.claude/rules-reference" \
           "$mg/proj/docs/draft" "$mg/home/.claude"
  printf '# タスク台帳\n\n| # | status | タスク |\n|---|---|---|\n| 1 | 進行中 | ログイン API |\n| 2 | 完了 | 初期設定 |\n' \
    > "$mg/proj/.claude/tasks/list.md"
  printf '# 保留タスク\n\n| 1 | 保留 | 後回しの件 |\n' > "$mg/proj/.claude/tasks/parking-lot.md"
  printf '# task-1 ログイン API\n\nゴール: ログインできる\n' > "$mg/proj/.claude/tasks/task-1-login.md"
  printf '# 設計メモ\n\napproved_at: 2026-08-28\n' > "$mg/proj/.claude/draft/foo.md"
  : > "$mg/proj/.claude/draft/.gitkeep"
  printf '# 事故記録\n\n- 2026-08-28 台帳を消した / 対処: git restore\n' > "$mg/proj/.claude/rules-reference/incidents.md"
  printf 'docs 側に先からあった中身\n' > "$mg/proj/docs/draft/foo.md"   # わざと同名衝突を作る
  cp -R "$mg/proj/.claude" "$mg/orig"
  out2="$(cd "$mg/proj" && HOME="$mg/home" CLAUDE_PLUGIN_ROOT="$ROOT" bash -c "$blk" 2>&1)"; rc2=$?
  [ "$rc2" -eq 0 ] || bad2="exit=$rc2"
  for f2 in tasks/list.md tasks/parking-lot.md tasks/task-1-login.md rules-reference/incidents.md; do
    cmp -s "$mg/orig/$f2" "$mg/proj/docs/$f2" || bad2="$bad2 ${f2}:移っていない/中身が変わった"
  done
  cmp -s "$mg/orig/draft/foo.md" "$mg/proj/.claude/draft/foo.md" || bad2="$bad2 draft/foo.md:元が消えた"
  grep -q 'docs 側に先からあった中身' "$mg/proj/docs/draft/foo.md" 2>/dev/null \
    || bad2="$bad2 docs/draft/foo.md:上書きされた"
  printf '%s' "$out2" | grep -q '移さなかった' || bad2="$bad2 出力に 移さなかった が無い"
  [ -d "$mg/proj/.claude/tasks" ] && bad2="$bad2 .claude/tasks:空なのに残った"
  [ -d "$mg/proj/.claude/rules-reference" ] && bad2="$bad2 .claude/rules-reference:空なのに残った"
  [ -d "$mg/proj/.claude/draft" ] || bad2="$bad2 .claude/draft:中身が残っているのに消えた"
  if [ -n "$bad2" ]; then rm -rf "$mg"; fail 1 "/update の移行は中身を保ち上書きしない" "$bad2"; return; fi
  # 2 回目は移す対象が無いので何も動かさない (冪等)
  out2="$(cd "$mg/proj" && HOME="$mg/home" CLAUDE_PLUGIN_ROOT="$ROOT" bash -c "$blk" 2>&1)"
  if ! printf '%s' "$out2" | grep -q '移した:'; then rm -rf "$mg"; fail 1 "移行は 2 回目も走る" "$out2"; return; fi
  local ss2 sl3
  ss2="$(HOME="$mg/home" CLAUDE_PLUGIN_ROOT="$ROOT" CLAUDE_PROJECT_DIR="$mg/proj" \
         bash "$HOOKS/session-start.sh" 2>/dev/null)"
  sl3="$(printf '%s' '{"context_window":{"used_percentage":12}}' \
         | HOME="$mg/home" NO_COLOR=1 TMPDIR="$mg/tmp" CLAUDE_PROJECT_DIR="$mg/proj" \
           bash "$ROOT/scripts/statusline.sh" 2>/dev/null | sed -n '1p')"
  rm -rf "$mg"
  if ! printf '%s' "$ss2" | grep -qF 'やること: 1 件 (docs/tasks/list.md)'; then
    fail 1 "移行後はセッション冒頭が docs/ の台帳を読む" "${ss2}"; return
  fi
  case "$sl3" in
    *"やること 1"*) ;;
    *) fail 1 "移行後は画面下部が docs/ の台帳を読む" "$sl3"; return ;;
  esac

  # /init 第 2 段階 (案件ヒアリング) の並び。v1.11.0 は grilling に**観点だけ**を渡し、事実も
  # 対象範囲も渡していなかったため、実使用で「弁護士費用パッケージの一括発注 (予算枠の確保)」という
  # このリポジトリの開発と無関係な質問が出た (調達・法務へ枝が伸びた)。ここでは
  # (a) 並びが 事実収集 → 範囲提示 → grilling 呼び出し であること (b) その事実収集の bash が
  # **中身のあるリポジトリでも空のリポジトリでも動く**こと (c) grilling へ渡す指示に範囲の制約が
  # 入っていること、を手順書から逐語に取り出して確かめる。文書と実挙動が離れた時点でここが落ちる。
  local im="$ROOT/commands/init.md" p_f p_s p_g iblk iinst iw iout irc bad4="" f4
  if [ ! -f "$im" ]; then fail 1 "commands/init.md が存在する" "$im が無い"; return; fi
  p_f="$(grep -n '== 設定ファイル ==' "$im" | head -1 | cut -d: -f1)"
  p_s="$(grep -n 'ここから伺うのは' "$im" | head -1 | cut -d: -f1)"
  p_g="$(grep -n 'ツールで `grilling` を呼び' "$im" | head -1 | cut -d: -f1)"
  if [ -z "$p_f" ] || [ -z "$p_s" ] || [ -z "$p_g" ]; then
    fail 1 "第 2 段階は 事実収集 → 範囲提示 → grilling 呼び出し の順" \
      "見つからない (事実収集=${p_f:-無} 範囲提示=${p_s:-無} grilling=${p_g:-無})"; return
  fi
  if [ "$p_f" -ge "$p_s" ] || [ "$p_s" -ge "$p_g" ]; then
    fail 1 "第 2 段階は 事実収集 → 範囲提示 → grilling 呼び出し の順" \
      "並びが違う (事実収集=${p_f} 範囲提示=${p_s} grilling=${p_g})"; return
  fi
  # grilling へ渡す指示 (呼び出し行の直後の囲み) に範囲の制約が入っている
  iinst="$(awk -v s="$p_g" 'NR >= s && /^```$/ { c++; next } c == 1 { print }' "$im")"
  for f4 in '調達' '法務' '踏み込まない' 'その質問は不要' '自分で調べる'; do
    printf '%s' "$iinst" | grep -qF "$f4" || bad4="$bad4 grilling へ渡す指示に[${f4}]が無い"
  done
  # 事実収集の bash を逐語に取り出す (見出し番号ではなく中身で選ぶ)
  iblk="$(awk '/^```bash$/ { b = ""; c = 1; next }
               c && /^```$/ { if (b ~ /== 設定ファイル ==/) { printf "%s", b; exit } c = 0; next }
               c { b = b $0 "\n" }' "$im")"
  if [ -z "$iblk" ]; then fail 1 "事実収集の bash を取り出せる" "commands/init.md に無い"; return; fi
  iw="$(mktemp -d)"; mkdir -p "$iw/full/src" "$iw/full/docs" "$iw/empty"
  printf '# demo-app\n\n買い物かごの API。\n' > "$iw/full/README.md"
  printf '{"name":"demo-app","scripts":{"dev":"next dev"},"dependencies":{"next":"^15"}}\n' \
    > "$iw/full/package.json"
  printf '# 概要\n' > "$iw/full/docs/overview.md"
  # (a) 中身のあるプロジェクト: README / 設定ファイル / 構成 / 既存の書類 が実際に出る
  iout="$(cd "$iw/full" && bash -c "$iblk" 2>&1)"; irc=$?
  [ "$irc" -eq 0 ] || bad4="$bad4 [中身あり] exit=${irc}"
  for f4 in 'demo-app' '買い物かごの API' 'あり package.json' 'scripts: dev' 'deps: next' 'src/' 'docs/overview.md'; do
    printf '%s' "$iout" | grep -qF "$f4" || bad4="$bad4 [中身あり] ${f4} が出ない"
  done
  # (b) 空のプロジェクト: 材料がゼロでもエラーにせず最後まで進む (set -e 付きでも落ちない)
  iout="$(cd "$iw/empty" && bash -c "$(printf 'set -e\n%s' "$iblk")" 2>&1)"; irc=$?
  rm -rf "$iw"
  [ "$irc" -eq 0 ] || bad4="$bad4 [空] exit=${irc}: ${iout}"
  printf '%s' "$iout" | grep -qF '== 以上 ==' || bad4="$bad4 [空] 最後まで進まない: ${iout}"
  if [ -n "$bad4" ]; then fail 1 "第 2 段階は事実を集めてから範囲を区切って伺う" "$bad4"; return; fi

  pass 1 "session-start.sh は対象ファイル不在でも exit 0 / ${lines} 行 / [harness] prefix あり / statusline も空 stdin・壊れた JSON・控え不在/空/壊れで 2 行 + 設定リンク常時 + exit 0 (色あり/NO_COLOR とも) / 進め方は置き場 5 通りで冒頭と画面下部が一致し /config は在る側に書く / /update 手順 2-2 の移行は中身を保ち同名は上書きせず両方残し、移行後は冒頭と画面下部が docs/ の台帳を読む / /init 第 2 段階は 事実収集 → 範囲提示 → grilling 呼び出し の順で、事実収集の bash は中身ありでも空でも exit 0、grilling へ渡す指示に範囲の制約 (調達・法務へ踏み込まない / 不要な質問は落とす / 事実は自分で調べる) が入っている"
}

# ---------- case 2: UserPromptSubmit の 2 本は、出してよい時だけ出す ----------
# (a) context-budget.sh は閾値未満で無出力
# (b) loop-reminder.sh は進め方が loop のときだけ出す (v1.11.0)。
#     **normal での無出力が最重要**。確認しながら進めたい利用者に毎ターン「確認を求めるな」が
#     入るのは、機能ではなく害。進め方の解決は scripts/tasks-path.sh の harness_mode 1 本に
#     通しているので、置き場 6 通り (ホーム / プロジェクト / 両方 / 無し) で出す・出さないを見る。
case_2() {
  local out rc
  out="$(TMPDIR="$(mktemp -d)" HC_CONTEXT_RATIO=0.50 bash "$HOOKS/context-budget.sh" \
        <<< '{"session_id":"smoke-under"}' 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then fail 2 "閾値未満は無出力" "exit=$rc"; return; fi
  if [ -n "$out" ]; then fail 2 "閾値未満は無出力" "出力あり: $out"; return; fi

  local lr="$HOOKS/loop-reminder.sh"
  if [ ! -f "$lr" ]; then fail 2 "loop-reminder.sh が存在する" "$lr が無い"; return; fi
  local lw h p want where bad="" n
  lw="$(mktemp -d)"; mkdir -p "$lw/home/.claude" "$lw/proj/.claude"

  # lr_run [env=値 ...] -> hook を実行し stdout+stderr を返す (rc は $lr_rc に入れる)
  lr_rc=0
  lr_run() {
    local o
    o="$(printf '%s' '{"session_id":"loop","prompt":"次を進めて"}' \
         | env "$@" HOME="$lw/home" CLAUDE_PLUGIN_ROOT="$ROOT" CLAUDE_PROJECT_DIR="$lw/proj" \
           bash "$lr" 2>&1)"; lr_rc=$?
    printf '%s' "$o"
  }

  # <ホーム側> <プロジェクト側> <出すか yes|no> <説明>   ("-" は mode.yml を置かない)
  while read -r h p want where; do
    [ -n "$h" ] || continue
    rm -f "$lw/home/.claude/mode.yml" "$lw/proj/.claude/mode.yml"
    [ "$h" = "-" ] || printf 'mode: %s\n' "$h" > "$lw/home/.claude/mode.yml"
    [ "$p" = "-" ] || printf 'mode: %s\n' "$p" > "$lw/proj/.claude/mode.yml"
    out="$(lr_run SMOKE=1)"
    [ "$lr_rc" -eq 0 ] || bad="$bad [${where}] exit=${lr_rc}"
    if [ "$want" = "yes" ]; then
      [ -n "$out" ] || bad="$bad [${where}] loop なのに無出力"
    else
      [ -z "$out" ] || bad="$bad [${where}] 出さないはずが出力: ${out}"
    fi
  done <<'EOF'
loop   -      yes ホームのみloop
-      loop   yes プロジェクトのみloop
normal loop   yes 両方あればプロジェクト側loop
loop   normal no  両方あればプロジェクト側normal
-      -      no  どちらも無し
normal -      no  ホームのみnormal
EOF
  if [ -n "$bad" ]; then rm -rf "$lw"; fail 2 "loop のときだけ出す" "$bad"; return; fi

  # loop の中身: 3〜5 行 / 全行 [harness] 始まり / 要点 4 つ (loop・stop・subagent・確認) が揃う
  rm -f "$lw/home/.claude/mode.yml"; printf 'mode: loop\n' > "$lw/proj/.claude/mode.yml"
  out="$(lr_run SMOKE=1)"
  n="$(printf '%s\n' "$out" | grep -c . || true)"
  if [ "${n:-0}" -lt 3 ] || [ "${n:-0}" -gt 5 ]; then
    rm -rf "$lw"; fail 2 "loop の再注入は 3〜5 行" "${n} 行: $out"; return
  fi
  if [ "$(printf '%s\n' "$out" | grep -c '^\[harness\] ' || true)" != "$n" ]; then
    rm -rf "$lw"; fail 2 "全行が [harness] で始まる" "$out"; return
  fi
  for h in 'loop' 'stop' 'subagent' '確認'; do
    printf '%s' "$out" | grep -qF "$h" || bad="$bad 要点[${h}]が無い"
  done
  if [ -n "$bad" ]; then rm -rf "$lw"; fail 2 "loop の要点が揃う" "$bad -- $out"; return; fi
  local lines="$n"

  # 止める手段と fail-open: off / 壊れた mode.yml / 読めない mode.yml / 共通ライブラリ不在 /
  # 空 stdin / 壊れた JSON。いずれも exit 0 で、出力は「無い」か「4 行そのまま」のどちらか。
  out="$(lr_run HC_LOOP_REMINDER=off)"
  { [ "$lr_rc" -eq 0 ] && [ -z "$out" ]; } || bad="$bad [off] exit=${lr_rc} 出力:${out}"
  printf 'mode: LOOP\n' > "$lw/proj/.claude/mode.yml"     # 大文字は loop ではない
  out="$(lr_run SMOKE=1)"
  { [ "$lr_rc" -eq 0 ] && [ -z "$out" ]; } || bad="$bad [大文字LOOP] exit=${lr_rc} 出力:${out}"
  printf '\001garbage\002 no colon\n' > "$lw/proj/.claude/mode.yml"
  out="$(lr_run SMOKE=1)"
  { [ "$lr_rc" -eq 0 ] && [ -z "$out" ]; } || bad="$bad [壊れた mode.yml] exit=${lr_rc} 出力:${out}"
  printf 'mode: loop\n' > "$lw/proj/.claude/mode.yml"; chmod 000 "$lw/proj/.claude/mode.yml"
  out="$(lr_run SMOKE=1)"
  { [ "$lr_rc" -eq 0 ] && [ -z "$out" ]; } || bad="$bad [読めない mode.yml] exit=${lr_rc} 出力:${out}"
  chmod 644 "$lw/proj/.claude/mode.yml"
  # 共通ライブラリ (scripts/tasks-path.sh) が無い置き方では、loop でも黙って通す
  mkdir -p "$lw/plug/hooks" && cp "$lr" "$lw/plug/hooks/"
  out="$(printf '%s' '{}' | HOME="$lw/home" CLAUDE_PLUGIN_ROOT="$lw/plug" \
        CLAUDE_PROJECT_DIR="$lw/proj" bash "$lw/plug/hooks/loop-reminder.sh" 2>&1)"; rc=$?
  { [ "$rc" -eq 0 ] && [ -z "$out" ]; } || bad="$bad [ライブラリ不在] exit=${rc} 出力:${out}"
  local src
  for src in '' '{"session_id":' 'zzz'; do
    out="$(printf '%s' "$src" | HOME="$lw/home" CLAUDE_PLUGIN_ROOT="$ROOT" \
          CLAUDE_PROJECT_DIR="$lw/proj" bash "$lr" 2>&1)"; rc=$?
    n="$(printf '%s\n' "$out" | grep -c . || true)"
    { [ "$rc" -eq 0 ] && [ "${n:-0}" -eq 4 ]; } || bad="$bad [異常入力 ${src:-空}] exit=${rc} ${n} 行"
  done
  rm -rf "$lw"
  if [ -n "$bad" ]; then fail 2 "止める手段と fail-open" "$bad"; return; fi

  pass 2 "context-budget.sh は閾値未満 (0.50) で無出力 / loop-reminder.sh は置き場 6 通りで loop のときだけ ${lines} 行を出し normal では 1 バイトも出さない (要点 4 つ入り・全行 [harness] 始まり) / HC_LOOP_REMINDER=off・大文字 LOOP・壊れた/読めない mode.yml・共通ライブラリ不在でも exit 0 無出力"
}

# ---------- case 3: 閾値超過で 1 度だけ発火 ----------
case_3() {
  local td first second
  td="$(mktemp -d)"
  first="$(TMPDIR="$td" HC_CONTEXT_RATIO=0.85 bash "$HOOKS/context-budget.sh" <<< '{"session_id":"smoke-over"}' 2>&1)"
  second="$(TMPDIR="$td" HC_CONTEXT_RATIO=0.85 bash "$HOOKS/context-budget.sh" <<< '{"session_id":"smoke-over"}' 2>&1)"
  rm -rf "$td"
  if ! printf '%s' "$first" | grep -q '/state save'; then fail 3 "閾値超過で 1 度だけ発火" "1 回目が無出力"; return; fi
  if [ -n "$second" ]; then fail 3 "閾値超過で 1 度だけ発火" "2 回目も出力: $second"; return; fi

  # --- 画面下部と自動処理が同じ使用率を出す (v1.9.0 の不具合の再発検査) ---------------
  # v1.9.0 は画面下部が Claude Code の済みの百分率をそのまま出し、hook は
  # 「直近のトークン数 ÷ 200,000 固定」で計算していた。窓が 1,000,000 の会話では
  # 画面下部 17% / hook 83% と同じ瞬間に矛盾する 2 つの数字が出た。
  # 同じ量 (input + cache 作成 + cache 読み + output) と同じ窓を与えて、両者の値が
  # 1 の位まで一致することを窓 2 通り × 使用率 5 通りで確かめる。
  # 窓サイズは画面下部の入力 JSON にしか無いため、画面下部 → 控え → hook の受け渡しも同時に検査する。
  local ct in_t out_t win want sl_p hk_p tr bad3=""
  ct="$(mktemp -d)"
  while read -r in_t out_t win want; do
    [ -n "$in_t" ] || continue
    tr="$ct/tr-${in_t}-${win}.jsonl"
    # usage の中に iterations[] があっても、数えるのは最初の 1 組だけ (実物と同じ形にしてある)
    printf '{"type":"assistant","message":{"usage":{"input_tokens":%s,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":%s,"server_tool_use":{"web_search_requests":0},"iterations":[{"input_tokens":999999,"output_tokens":999999}]}}}\n' \
      "$in_t" "$out_t" > "$tr"
    # 画面下部: 窓サイズを観測して控えに書く。表示の ctx は共通ライブラリで計算した値。
    sl_p="$(printf '{"session_id":"pair","context_window":{"total_input_tokens":%s,"total_output_tokens":%s,"context_window_size":%s,"used_percentage":%s}}' \
              "$in_t" "$out_t" "$win" "$want" \
            | TMPDIR="$ct" NO_COLOR=1 CLAUDE_PROJECT_DIR="$ct" HARNESS_UPDATE_CHECK=off \
              bash "$ROOT/scripts/statusline.sh" 2>/dev/null | sed -n '1s/.*ctx \([0-9]*\)%.*/\1/p')"
    # 自動処理: 控えから窓サイズを読む。閾値を最小にして使用率そのものを取り出す。
    hk_p="$(printf '{"session_id":"pair","transcript_path":"%s"}' "$tr" \
            | TMPDIR="$ct" HC_CONTEXT_THRESHOLD=0.0001 bash "$HOOKS/context-budget.sh" 2>/dev/null \
            | sed -n 's/.*使用率が \([0-9]*\)%.*/\1/p')"
    rm -f "$ct/claude-harness-lite/ctx-pair.fired"
    [ "$sl_p" = "$want" ] || bad3="$bad3 [in=${in_t} out=${out_t} 窓=${win}] 画面下部=${sl_p:-無}(期待 ${want})"
    [ "$hk_p" = "$want" ] || bad3="$bad3 [in=${in_t} out=${out_t} 窓=${win}] 自動処理=${hk_p:-無}(期待 ${want})"
  done <<'EOF'
168000 2000 1000000 17
168000 2000 200000 85
40000 0 200000 20
999999 1 1000000 100
1000 0 200000 1
EOF
  if [ -n "$bad3" ]; then rm -rf "$ct"; fail 3 "画面下部と自動処理は同じ使用率を出す" "$bad3"; return; fi

  # 窓サイズが分からないとき (控えも env も無い) は 200,000 とみなす。
  # 併せて HC_CONTEXT_WINDOW の明示指定が控えより優先されることも見る。
  local nw
  rm -rf "$ct/claude-harness-lite"
  nw="$(printf '{"session_id":"nowin","transcript_path":"%s"}' "$ct/tr-168000-1000000.jsonl" \
        | TMPDIR="$ct" HC_CONTEXT_THRESHOLD=0.0001 bash "$HOOKS/context-budget.sh" 2>/dev/null \
        | sed -n 's/.*使用率が \([0-9]*\)%.*/\1/p')"
  [ "$nw" = "85" ] || bad3="$bad3 窓不明の既定=${nw:-無}(期待 85 = 170000/200000)"
  nw="$(printf '{"session_id":"envwin","transcript_path":"%s"}' "$ct/tr-168000-1000000.jsonl" \
        | TMPDIR="$ct" HC_CONTEXT_WINDOW=1000000 HC_CONTEXT_THRESHOLD=0.0001 \
          bash "$HOOKS/context-budget.sh" 2>/dev/null \
        | sed -n 's/.*使用率が \([0-9]*\)%.*/\1/p')"
  [ "$nw" = "17" ] || bad3="$bad3 HC_CONTEXT_WINDOW 指定=${nw:-無}(期待 17)"
  # 異常入力 (空 stdin / 壊れた JSON / transcript が無い) でも黙って exit 0
  local src3 rc3 out
  for src3 in '' '{"session_id":' 'zzz' '{"session_id":"x","transcript_path":"/nope/none.jsonl"}'; do
    out="$(printf '%s' "$src3" | TMPDIR="$ct" bash "$HOOKS/context-budget.sh" 2>&1)"; rc3=$?
    [ "$rc3" -eq 0 ] || bad3="$bad3 [異常入力 ${src3}] exit=${rc3}"
    [ -z "$out" ] || bad3="$bad3 [異常入力 ${src3}] 出力あり: ${out}"
  done
  rm -rf "$ct"
  if [ -n "$bad3" ]; then fail 3 "窓サイズ不明時の既定と異常入力" "$bad3"; return; fi

  pass 3 "context-budget.sh は 0.85 で 1 度発火し 2 度目は沈黙 / 画面下部と自動処理が同じ使用率 (窓 200k・1M × 5 通りで一致) / 窓が分からなければ 200,000 とみなし HC_CONTEXT_WINDOW が優先 / 空 stdin・壊れた JSON・transcript 不在でも無出力 exit 0"
}

# ---------- case 4: T0 予算 (警告 6,000 tokens / 上限 10,000 tokens) ----------
# 配布物としての T0 は rules/ 直下の frontmatter 無し + 導入先に置く CLAUDE.md 雛形。
# 雛形は v1.7.0 で templates/CLAUDE.md へ移した (プラグイン直下に置くと plugin validate が
# 「root の CLAUDE.md は project context として読まれない」と警告するため)。/init が配る対象で
# あることは変わらないので、T0 の計測対象からは外さない。
case_4() {
  local total=0 files=() f bytes tokens warn=""
  [ -f "$ROOT/templates/CLAUDE.md" ] && files+=("$ROOT/templates/CLAUDE.md")
  if [ -d "$ROOT/rules" ]; then
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      has_paths_key "$f" || files+=("$f")
    done < <(find "$ROOT/rules" -maxdepth 1 -name '*.md' 2>/dev/null | sort)
  fi
  if [ "${#files[@]}" -eq 0 ]; then
    fail 4 "T0 予算 <= ${T0_BUDGET_MAX} tokens" "templates/CLAUDE.md / rules/*.md が未作成のため測定不可"; return
  fi
  for f in "${files[@]}"; do
    bytes="$(wc -c < "$f" 2>/dev/null | tr -d ' ')"
    total=$(( total + ${bytes:-0} ))
  done
  tokens=$(( total / 3 ))
  if [ "$tokens" -gt "$T0_BUDGET_MAX" ]; then
    fail 4 "T0 予算 <= ${T0_BUDGET_MAX} tokens" "${tokens} tokens (${total} bytes / ${#files[@]} file) -- 既存 1 件を T1/T2 へ降格するまで T0 に追加しない"; return
  fi
  if [ "$tokens" -gt "$T0_BUDGET_WARN" ]; then
    echo "WARN  case 4: T0 常時ロード ${tokens} tokens が警告線 ${T0_BUDGET_WARN} を超えた (上限 ${T0_BUDGET_MAX})。余裕があるうちに降格候補 1 件を決める"
    warn=" / WARN: ${T0_BUDGET_WARN} 超過 (上限 ${T0_BUDGET_MAX})"
  fi

  # 二重ロード検出。project scope と user scope の両方に同じ rule があると T0 は倍になり、
  # 警告線 6,000 を無言で割る。/init が使う scripts/scope-check.sh がその重なりを止める。
  local sc td out
  sc="$ROOT/scripts/scope-check.sh"
  if [ ! -f "$sc" ]; then fail 4 "scope-check.sh が存在する" "$sc が無い"; return; fi
  if [ $(( tokens * 2 )) -le "$T0_BUDGET_WARN" ]; then
    fail 4 "二重ロードは警告線に届く (検出の前提)" "倍でも $(( tokens * 2 )) <= ${T0_BUDGET_WARN}"; return
  fi
  td="$(mktemp -d)"; mkdir -p "$td/proj/rules" "$td/home/rules"
  cp "$ROOT"/rules/*.md "$td/proj/rules/" 2>/dev/null
  # (a) 片側だけなら無警告
  out="$(bash "$sc" "$td/proj" "$td/home" 2>&1)"
  if [ -n "$out" ]; then rm -rf "$td"; fail 4 "片側だけなら無警告" "出力あり: $out"; return; fi
  # (b) 両側に同名があれば警告 + 重なったファイル名 + 消し方を出す
  cp "$ROOT"/rules/*.md "$td/home/rules/" 2>/dev/null
  out="$(bash "$sc" "$td/proj" "$td/home" 2>&1)"
  # (c) 同じ場所を 2 回渡した時 (ホーム直下で開いた等) は重複扱いしない
  local same; same="$(bash "$sc" "$td/proj" "$td/proj" 2>&1)"
  rm -rf "$td"
  if ! printf '%s\n' "$out" | grep -q '同じルールが 2 か所にあります'; then
    fail 4 "二重ロードを警告する" "警告が出ない: $out"; return
  fi
  if ! printf '%s\n' "$out" | grep -q 'core.md'; then
    fail 4 "重なったファイル名を出す" "core.md が出ない: $out"; return
  fi
  if ! printf '%s\n' "$out" | grep -q '^     rm .*rules/core.md$'; then
    fail 4 "消し方を出す" "rm の行が出ない: $out"; return
  fi
  if [ -n "$same" ]; then fail 4 "同一パスは重複扱いしない" "出力あり: $same"; return; fi

  # (d) 台帳の二重存在。移行 (/update 手順 2) で 1 件だけ同名衝突が残ると、docs/ 側だけが
  # 読まれて .claude/ 側は誰にも見られないまま更新され続ける。取りこぼしをここで止める。
  local dl q1 q2
  dl="$(mktemp -d)"; mkdir -p "$dl/docs/tasks" "$dl/.claude/tasks" "$dl/home"
  : > "$dl/docs/tasks/list.md"
  q1="$(bash "$sc" "$dl/.claude" "$dl/home" "$dl" 2>&1)"
  : > "$dl/.claude/tasks/list.md"
  q2="$(bash "$sc" "$dl/.claude" "$dl/home" "$dl" 2>&1)"
  rm -rf "$dl"
  if [ -n "$q1" ]; then fail 4 "台帳が 1 か所なら無警告" "出力あり: $q1"; return; fi
  if ! printf '%s\n' "$q2" | grep -q 'タスク一覧表が 2 か所にあります'; then
    fail 4 "台帳の二重存在を警告する" "警告が出ない: $q2"; return
  fi

  # /add-rule と /rules-audit が見るルールの置き場。プロジェクト側を決め打ちすると
  # 全プロジェクト共通 (/init user) に置いた利用者に対し「既存ルール 0 件・予算 0 tokens」と
  # 誤判定し、重複ルールを素通しさせる (v1.0.0 の実害)。在る側を返すことを 4 通りで確かめる。
  local rw got want2 where2 h p
  rw="$(mktemp -d)"; mkdir -p "$rw/home" "$rw/proj"
  while read -r h p want2 where2; do
    [ -n "$h" ] || continue
    rm -rf "$rw/home/.claude" "$rw/proj/.claude"; mkdir -p "$rw/home/.claude" "$rw/proj/.claude"
    [ "$h" = "-" ] || mkdir -p "$rw/home/.claude/rules"
    [ "$p" = "-" ] || mkdir -p "$rw/proj/.claude/rules"
    got="$(HOME="$rw/home" bash -c '. "$1/scripts/tasks-path.sh"; harness_rules_dir "$2"' _ "$ROOT" "$rw/proj")"
    case "$want2" in
      home) want2="$rw/home/.claude/rules" ;;
      proj) want2="$rw/proj/.claude/rules" ;;
    esac
    if [ "$got" != "$want2" ]; then
      rm -rf "$rw" "$td"; fail 4 "ルールの置き場は在る側 (${where2})" "期待=${want2} 実測=${got:-無}"; return
    fi
  done <<'EOF'
yes -   home ホームのみ
-   yes proj プロジェクトのみ
yes yes proj 両方あればプロジェクト側
-   -   proj どちらも無ければ新規作成先
EOF
  rm -rf "$rw"
  pass 4 "T0 常時ロード ${tokens} tokens (警告 ${T0_BUDGET_WARN} / 上限 ${T0_BUDGET_MAX}, ${#files[@]} file / ${total} bytes)${warn} / 二重ロード ($(( tokens * 2 ))) は scope-check.sh が警告 / 台帳が docs と .claude の 2 か所に在れば警告 / ルールの置き場は 4 通りとも在る側を返す"
}

# ---------- case 5: 層違反検出 (T0 は許可リストのファイルだけ / 本数 <= T0_MAX) ----------
case_5() {
  local n=0 f base names="" unexpected="" missing="" want
  if [ ! -d "$ROOT/rules" ]; then
    fail 5 "T0 rule は許可リストのみ" "rules/ が未作成のため測定不可"; return
  fi
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    has_paths_key "$f" && continue
    base="$(basename "$f")"
    n=$(( n + 1 )); names="$names $base"
    case " $T0_ALLOWLIST " in *" $base "*) ;; *) unexpected="$unexpected $base" ;; esac
  done < <(find "$ROOT/rules" -maxdepth 1 -name '*.md' 2>/dev/null | sort)
  if [ "$n" -eq 0 ]; then fail 5 "T0 rule は許可リストのみ" "rules/*.md が 0 件 (未作成)"; return; fi
  if [ -n "$unexpected" ]; then
    fail 5 "T0 rule は許可リスト (${T0_ALLOWLIST}) のみ" "想定外の T0 rule:${unexpected}"; return
  fi
  for want in $T0_ALLOWLIST; do
    case "$names " in *" $want "*) ;; *) missing="$missing $want" ;; esac
  done
  if [ -n "$missing" ]; then
    fail 5 "T0 rule は許可リスト (${T0_ALLOWLIST}) のみ" "許可リストが T0 に不在:${missing}"; return
  fi
  if [ "$n" -gt "$T0_MAX" ]; then fail 5 "T0 rule <= ${T0_MAX} 本" "${n} 本:${names}"; return; fi
  pass 5 "T0 層の rule は許可リストどおり ${n} 本 <= ${T0_MAX} (${names# })"
}

# ---------- case 6: 数の予算 (hook<=5 / command<=12 / skill<=3 / smoke case<=10) ----------
# hook は hooks/*.sh だけを数える (hooks.json は宣言であって hook スクリプトではない)。
# skill は skills/<名前>/SKILL.md を数える。本体は呼ばれた時だけ読まれるが name と
# description は常に載るため、数を予算で抑える (rules/_meta.md 「数の予算」)。
case_6() {
  local hooks cmds skills cases
  hooks="$(find "$ROOT/hooks" -maxdepth 1 -name '*.sh' 2>/dev/null | wc -l | tr -d ' ')"
  cmds="$(find "$ROOT/commands" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
  skills="$(find "$ROOT/skills" -maxdepth 2 -name 'SKILL.md' 2>/dev/null | wc -l | tr -d ' ')"
  cases="$(grep -c '^case_[0-9][0-9]*()' "$here/smoke.sh" 2>/dev/null | tr -d ' ')"
  local msg="hook=${hooks}/5 command=${cmds}/12 skill=${skills}/3 smoke case=${cases}/10"
  if [ "${hooks:-0}" -gt 5 ] || [ "${cmds:-0}" -gt 12 ] || [ "${skills:-0}" -gt 3 ] \
     || [ "${cases:-0}" -gt 10 ]; then
    fail 6 "数の予算" "$msg"; return
  fi
  pass 6 "数の予算 ${msg}"
}

# 更新検知 case (7/8) 用の作業 dir を組む。プラグインと同じ配置 (hooks/ scripts/ VERSION) にする。
#   curl スタブは「通信が起きたら $tmp/curl-called が生える」ことで通信の有無を可視化する。
setup_update_env() {
  local tmp="$1"
  mkdir -p "$tmp/hooks" "$tmp/scripts" "$tmp/bin" || return 1
  cp "$HOOKS/session-start.sh" "$tmp/hooks/" || return 1
  cp "$ROOT/scripts/update-check.sh" "$tmp/scripts/" || return 1
  cp "$ROOT/scripts/tasks-path.sh" "$tmp/scripts/" 2>/dev/null
  cat > "$tmp/bin/curl" <<EOF
#!/usr/bin/env bash
: > "$tmp/curl-called"
exit 1
EOF
  chmod +x "$tmp/bin/curl"
}

# run_session_start <plugin_root> <tmpdir> <HARNESS_UPDATE_CHECK 値> -> hook を実行し stdout+stderr を返す
run_session_start() {
  local tmp="$1" td="$2" chk="$3"
  PATH="$tmp/bin:$PATH" TMPDIR="$td" CLAUDE_PLUGIN_ROOT="$tmp" CLAUDE_PROJECT_DIR="$tmp" \
    HARNESS_UPDATE_CHECK="$chk" HARNESS_UPDATE_URL="http://127.0.0.1:9/VERSION" \
    bash "$tmp/hooks/session-start.sh" 2>&1
}

# run_statusline <plugin_root> <tmpdir> <stdin JSON> [HC_STATUSLINE_NOTICE] [HARNESS_UPDATE_CHECK]
#   -> 画面下部の 1 行を返す。
# HARNESS_UPDATE_CHECK は smoke 冒頭で off に export しているので、既定 on を明示的に上書きして渡す。
# curl スタブを PATH の先頭に置いたまま呼ぶ。statusline が通信すれば $tmp/curl-called が生える。
run_statusline() {
  local tmp="$1" td="$2" json="$3" notice="${4:-on}" chk="${5:-on}"
  printf '%s' "$json" | PATH="$tmp/bin:$PATH" TMPDIR="$td" NO_COLOR=1 CLAUDE_PROJECT_DIR="$tmp" \
    HARNESS_UPDATE_URL="http://127.0.0.1:9/VERSION" HC_STATUSLINE_NOTICE="$notice" \
    HARNESS_UPDATE_CHECK="$chk" bash "$ROOT/scripts/statusline.sh" 2>&1
}

# expect_notice <出力> <期待するお知らせ (空なら「何も出さない」)> -> 一致で rc 0、違えば理由を stdout
# お知らせは 2 行目の設定リンクの**後ろ**に出る。該当なしでも設定リンクは必ず残る。
expect_notice() {
  local out="$1" want="$2" why l2
  why="$(sl_shape "$out")" || { printf '%s' "$why"; return 1; }
  l2="$(printf '%s\n' "$out" | sed -n '2p')"
  if [ -n "$want" ]; then
    case "$l2" in
      "$SL_LINK    $want") return 0 ;;
      *) printf '2 行目が [リンク + %s] でない: %s' "$want" "$l2"; return 1 ;;
    esac
  fi
  case "$out" in
    *更新あり*|*きりの良いところで*) printf 'お知らせが出ている: %s' "$out"; return 1 ;;
  esac
  # 該当なしのときは 2 行目が設定リンクだけになる (リンクは常時表示なので消えてはいけない)
  if [ "$l2" != "$SL_LINK" ]; then printf '2 行目が設定リンクだけではない: %s' "$l2"; return 1; fi
  # 1 行目は従来どおり「やること <N>」で終わる
  case "$out" in
    *"やること "*) return 0 ;;
    *) printf '1 行目が やること <N> で終わっていない: %s' "$out"; return 1 ;;
  esac
}

# ---------- case 7: VERSION の形式 / キャッシュが新しい時は通信も出力もしない ----------
case_7() {
  local tmp td dir ver out stamp_before stamp_after
  if [ ! -f "$ROOT/VERSION" ]; then fail 7 "VERSION が semver 1 行" "VERSION が存在しない"; return; fi
  if [ "$(grep -c . "$ROOT/VERSION" | tr -d ' ')" != "1" ]; then
    fail 7 "VERSION が semver 1 行" "1 行ではない"; return
  fi
  ver="$(head -1 "$ROOT/VERSION" | tr -d '\r')"
  if ! printf '%s' "$ver" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    fail 7 "VERSION が semver 1 行" "semver ではない: $ver"; return
  fi

  tmp="$(mktemp -d)"; td="$(mktemp -d)"
  if ! setup_update_env "$tmp"; then rm -rf "$tmp" "$td"; fail 7 "更新検知の作業 dir 構築" "cp 失敗"; return; fi
  . "$ROOT/scripts/update-check.sh" 2>/dev/null
  dir="$(export TMPDIR="$td"; harness_update_cache_dir "$tmp")"
  mkdir -p "$dir"
  printf '%s\n' "$ver" > "$tmp/VERSION"

  # (a) キャッシュが新しい (stamp = 現在時刻) 時は通信も出力もしない
  printf '%s' "$ver" > "$dir/latest"
  date +%s > "$dir/stamp"
  stamp_before="$(cat "$dir/stamp")"
  out="$(run_session_start "$tmp" "$td" "on")"
  sleep 0.3
  stamp_after="$(cat "$dir/stamp" 2>/dev/null)"
  if [ -e "$tmp/curl-called" ]; then rm -rf "$tmp" "$td"; fail 7 "キャッシュが新しい時は通信しない" "curl が呼ばれた"; return; fi
  if [ "$stamp_before" != "$stamp_after" ]; then rm -rf "$tmp" "$td"; fail 7 "キャッシュが新しい時は通信しない" "stamp が更新された"; return; fi
  if printf '%s' "$out" | grep -q '更新あり'; then rm -rf "$tmp" "$td"; fail 7 "同版では無出力" "更新あり が出た: $out"; return; fi

  # (b) HARNESS_UPDATE_CHECK=off なら、新版が届いていて期限切れでも通信も表示もしない
  printf '%s' "99.0.0" > "$dir/latest"
  rm -f "$dir/stamp"
  out="$(run_session_start "$tmp" "$td" "off")"
  sleep 0.3
  if [ -e "$tmp/curl-called" ]; then rm -rf "$tmp" "$td"; fail 7 "off で通信しない" "curl が呼ばれた"; return; fi
  if [ -e "$dir/stamp" ]; then rm -rf "$tmp" "$td"; fail 7 "off で通信しない" "stamp が作られた"; return; fi
  if printf '%s' "$out" | grep -q '更新あり'; then rm -rf "$tmp" "$td"; fail 7 "off で無出力" "更新あり が出た: $out"; return; fi

  rm -rf "$tmp" "$td"
  pass 7 "VERSION=${ver} は semver 1 行 / キャッシュ有効時と off 指定は通信も出力もしない"
}

# ---------- case 8: 新版キャッシュのみ通知し、semver を数値比較する ----------
case_8() {
  local tmp td dir out want failed=0 local_v cached_v expect
  tmp="$(mktemp -d)"; td="$(mktemp -d)"
  if ! setup_update_env "$tmp"; then rm -rf "$tmp" "$td"; fail 8 "更新検知の作業 dir 構築" "cp 失敗"; return; fi
  . "$ROOT/scripts/update-check.sh" 2>/dev/null
  dir="$(export TMPDIR="$td"; harness_update_cache_dir "$tmp")"
  mkdir -p "$dir"

  # local / cached / 通知を期待するか (yes|no) の 5 組
  while read -r local_v cached_v expect; do
    [ -n "$local_v" ] || continue
    printf '%s\n' "$local_v" > "$tmp/VERSION"
    printf '%s' "$cached_v" > "$dir/latest"
    date +%s > "$dir/stamp"          # 期限内にして通信を起こさない
    out="$(run_session_start "$tmp" "$td" "on")"
    want="[harness] 更新あり v${local_v} → v${cached_v} (/update で適用)"
    if [ "$expect" = "yes" ]; then
      if ! printf '%s\n' "$out" | grep -qF "$want"; then
        fail 8 "新版で 1 行通知" "local=${local_v} cached=${cached_v} で期待行が無い: $out"; failed=1; break
      fi
      if [ "$(printf '%s\n' "$out" | grep -c '更新あり')" != "1" ]; then
        fail 8 "新版で 1 行通知" "local=${local_v} cached=${cached_v} で 1 行ではない: $out"; failed=1; break
      fi
    else
      if printf '%s\n' "$out" | grep -q '更新あり'; then
        fail 8 "同版 / 旧版では無通知" "local=${local_v} cached=${cached_v} で通知が出た: $out"; failed=1; break
      fi
    fi
  done <<'EOF'
0.1.0 0.2.0 yes
0.1.0 0.1.0 no
0.2.0 0.1.0 no
0.9.0 0.10.0 yes
0.10.0 0.9.0 no
1.9.0 1.10.0 yes
1.10.0 1.9.0 no
EOF

  # 画面下部 2 行目のお知らせ。SessionStart が置いた控えを statusline が読むだけで、通信は起きない。
  # 上から順に 1 つだけ出し (1 更新あり > 2 context 高 > 何も出さない)、設定リンクは常時残る。
  local flag="$td/claude-harness-lite/update-available" why
  local up='更新あり → /hirai-lite:update' ctxmsg='きりの良いところで /hirai-lite:state save'
  local j_low='{"model":{"display_name":"X"},"context_window":{"used_percentage":12}}'
  local j_high='{"model":{"display_name":"X"},"context_window":{"used_percentage":85}}'
  while [ "$failed" -eq 0 ]; do
    # --- 新版が届いている状態を作る ---
    printf '%s\n' "0.1.0" > "$tmp/VERSION"; printf '%s' "0.2.0" > "$dir/latest"; date +%s > "$dir/stamp"
    run_session_start "$tmp" "$td" "on" >/dev/null
    if [ ! -s "$flag" ]; then fail 8 "SessionStart が更新の控えを置く" "$flag が無い"; failed=1; break; fi
    if ! why="$(expect_notice "$(run_statusline "$tmp" "$td" "$j_low")" "$up")"; then
      fail 8 "優先 1: 更新あり" "$why"; failed=1; break
    fi
    # 両方該当でも更新が勝つ
    if ! why="$(expect_notice "$(run_statusline "$tmp" "$td" "$j_high")" "$up")"; then
      fail 8 "優先 1 は context 高より強い" "$why"; failed=1; break
    fi
    # 枠ごと止める
    if ! why="$(expect_notice "$(run_statusline "$tmp" "$td" "$j_high" off)" "")"; then
      fail 8 "HC_STATUSLINE_NOTICE=off でお知らせだけ止まり設定リンクは残る" "$why"; failed=1; break
    fi
    # 更新の知らせだけ止める (context 高は残る)
    if ! why="$(expect_notice "$(run_statusline "$tmp" "$td" "$j_high" on off)" "$ctxmsg")"; then
      fail 8 "HARNESS_UPDATE_CHECK=off で更新の知らせだけ止まる" "$why"; failed=1; break
    fi

    # --- 最新版になった状態 (控えは消える) ---
    printf '%s\n' "0.2.0" > "$tmp/VERSION"; printf '%s' "0.2.0" > "$dir/latest"; date +%s > "$dir/stamp"
    run_session_start "$tmp" "$td" "on" >/dev/null
    if [ -e "$flag" ]; then fail 8 "最新版なら控えを消す" "$flag が残っている"; failed=1; break; fi
    if ! why="$(expect_notice "$(run_statusline "$tmp" "$td" "$j_high")" "$ctxmsg")"; then
      fail 8 "優先 2: context 高" "$why"; failed=1; break
    fi
    if ! why="$(expect_notice "$(run_statusline "$tmp" "$td" "$j_low")" "")"; then
      fail 8 "どちらでもなければ区切りごと出さない" "$why"; failed=1; break
    fi
    # 閾値は HC_CONTEXT_THRESHOLD で動く (割合でも百分率でも受ける)
    if ! why="$(expect_notice "$(HC_CONTEXT_THRESHOLD=0.90 run_statusline "$tmp" "$td" "$j_high")" "")"; then
      fail 8 "閾値 0.90 なら 85% では出さない" "$why"; failed=1; break
    fi
    if ! why="$(expect_notice "$(HC_CONTEXT_THRESHOLD=10 run_statusline "$tmp" "$td" "$j_low")" "$ctxmsg")"; then
      fail 8 "閾値 10 (百分率) なら 12% で出す" "$why"; failed=1; break
    fi
    break
  done

  if [ -e "$tmp/curl-called" ]; then
    fail 8 "期限内は通信しない (statusline も含む)" "curl が呼ばれた"; failed=1
  fi
  rm -rf "$tmp" "$td"
  [ "$failed" -eq 0 ] || return
  pass 8 "新版のみ 1 行通知 / 同版・旧版は無通知 / 0.9.0 < 0.10.0 と 1.9.0 < 1.10.0 を数値比較 / 画面下部 2 行目は設定リンクを常時出しつつ お知らせは 更新あり > context 高 > 無表示 の順に 1 つだけ (off で停止・閾値可変・通信なし)"
}

# ---------- case 9: マニフェストが妥当な JSON で、版が VERSION と一致する ----------
# 不一致だと更新検知 (VERSION 基準) と /plugin update (plugin.json 基準) が別の版を指し、
# 「更新あり」の通知が嘘になる。
case_9() {
  local f ver pver mver
  for f in .claude-plugin/plugin.json .claude-plugin/marketplace.json hooks/hooks.json templates/settings.json; do
    if [ ! -f "$ROOT/$f" ]; then fail 9 "マニフェストが存在する" "$f が無い"; return; fi
    if ! python3 -m json.tool "$ROOT/$f" >/dev/null 2>&1; then
      fail 9 "マニフェストが妥当な JSON" "$f が JSON として読めない"; return
    fi
  done
  ver="$(head -1 "$ROOT/VERSION" 2>/dev/null | tr -d '\r')"
  pver="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("version",""))' \
          "$ROOT/.claude-plugin/plugin.json" 2>/dev/null)"
  mver="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["plugins"][0].get("version",""))' \
          "$ROOT/.claude-plugin/marketplace.json" 2>/dev/null)"
  if [ "$pver" != "$ver" ]; then
    fail 9 "plugin.json の version が VERSION と一致" "VERSION=${ver} plugin.json=${pver}"; return
  fi
  if [ -n "$mver" ] && [ "$mver" != "$ver" ]; then
    fail 9 "marketplace.json の version が VERSION と一致" "VERSION=${ver} marketplace.json=${mver}"; return
  fi
  pass 9 "マニフェスト 4 件が妥当な JSON / version=${pver} が VERSION と一致"
}

# ---------- case 10: 同梱物 (MCP 定義 / agents) が壊れていない ----------
# .mcp.json に実キーを書いてしまう事故と、frontmatter 欠けで読み込まれない agent を止める。
case_10() {
  local f base name desc bad=""
  # (a) .mcp.json は妥当な JSON で、env の値が全て ${...} 参照 (実値の直書き禁止)
  if [ ! -f "$ROOT/.mcp.json" ]; then fail 10 ".mcp.json が存在する" "無い"; return; fi
  if ! python3 -m json.tool "$ROOT/.mcp.json" >/dev/null 2>&1; then
    fail 10 ".mcp.json が妥当な JSON" "読めない"; return
  fi
  bad="$(python3 -c '
import json, sys
d = json.load(open(sys.argv[1])).get("mcpServers", {})
bad = []
for name, cfg in d.items():
    if not (cfg.get("command") or cfg.get("url")):
        bad.append(name + ":起動方法なし")
    for k, v in list(cfg.get("env", {}).items()) + list(cfg.get("headers", {}).items()):
        if not (isinstance(v, str) and v.startswith("${")):
            bad.append(name + "." + k + ":直書き")
print(" ".join(bad))
' "$ROOT/.mcp.json" 2>&1)"
  if [ -n "$bad" ]; then fail 10 "MCP の鍵は環境変数参照のみ" "$bad"; return; fi

  # (a-2) 同梱 MCP は版を固定する。プラグイン同梱の MCP は承認を挟まずつながるため、
  # @latest や ref なしの git URL のままだと配布元の任意のコミットが利用者の環境で実行される。
  bad="$(python3 -c '
import json, re, sys
d = json.load(open(sys.argv[1])).get("mcpServers", {})
bad = []
for name, cfg in d.items():
    for a in cfg.get("args", []):
        if not isinstance(a, str):
            continue
        if a.startswith(("git+", "http://", "https://")):
            # git+URL は @<tag/sha> が要る (URL 内の user@host は除く)
            if not re.search(r"@[0-9A-Za-z._/-]+$", a.split("//", 1)[-1]):
                bad.append(name + ":" + a + " に版指定なし")
        elif a.startswith("@") or re.match(r"^[A-Za-z0-9_.-]+@", a):
            # npm パッケージ指定 (@scope/pkg@ver または pkg@ver)
            ver = a.rsplit("@", 1)[-1]
            if ver in ("latest", "next", "canary", "") or not re.match(r"^[0-9]", ver):
                bad.append(name + ":" + a + " が可変の版")
print(" ".join(bad))
' "$ROOT/.mcp.json" 2>&1)"
  if [ -n "$bad" ]; then fail 10 "同梱 MCP は版を固定する" "$bad"; return; fi

  # (b) agents/*.md は name (= ファイル名) と description を frontmatter に持つ
  if [ ! -d "$ROOT/agents" ]; then fail 10 "agents/ が存在する" "無い"; return; fi
  local n=0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    n=$(( n + 1 )); base="$(basename "$f" .md)"
    name="$(awk 'NR==1&&$0!="---"{exit} NR>1&&/^---[[:space:]]*$/{exit} sub(/^name:[[:space:]]*/,""){print;exit}' "$f")"
    desc="$(awk 'NR==1&&$0!="---"{exit} NR>1&&/^---[[:space:]]*$/{exit} /^description:[[:space:]]*./{print "ok";exit}' "$f")"
    [ "$name" = "$base" ] || bad="$bad ${base}:name=${name:-無し}"
    [ "$desc" = "ok" ] || bad="$bad ${base}:description無し"
  done < <(find "$ROOT/agents" -maxdepth 1 -name '*.md' 2>/dev/null | sort)
  if [ "$n" -eq 0 ]; then fail 10 "agents/*.md が 1 件以上" "0 件"; return; fi
  if [ -n "$bad" ]; then fail 10 "agent の frontmatter" "不備:$bad"; return; fi

  # (c) plugin.json が既定フォルダを再宣言していない。
  # commands / agents は「既定を置き換える」キーであり、hooks は既定の hooks/hooks.json と
  # 二重になると読み込み自体が失敗する。v0.6.0 はこの 3 キーを書いたため 12 command と
  # 3 agent が登録されず、プラグインが failed to load になった。既定配置に任せるのが正。
  bad="$(python3 -c '
import json, os, sys
root = sys.argv[1]
m = json.load(open(os.path.join(root, ".claude-plugin/plugin.json")))
print(" ".join(k for k in ("commands", "agents", "hooks") if k in m))
' "$ROOT" 2>&1)"
  if [ -n "$bad" ]; then
    fail 10 "plugin.json は既定フォルダを再宣言しない" "既定を上書きするキー:$bad"; return
  fi
  pass 10 "MCP 定義は鍵を直書きせず / agent ${n} 件の frontmatter が妥当 / plugin.json は既定配置に任せている"
}

case_1; case_2; case_3; case_4; case_5; case_6; case_7; case_8; case_9; case_10

echo "---"
if [ "$FAILED" -ne 0 ]; then echo "RESULT: FAIL"; exit 1; fi
echo "RESULT: PASS"
exit 0
