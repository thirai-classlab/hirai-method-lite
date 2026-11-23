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

# 承認を求めるときに本文へ出す承認カードの語 (v2.8.0。それまでの「判断材料 5 項目」を置き換えた)。
# SSoT は T2 の docs/rules-reference/approval-template.md (T0 rules/core.md にはカードの名前と
# 1 行目の形だけを置く)。承認はルール追加に限らず、タスク・設計・設定変更・元に戻せない操作にも
# 効く汎用規範なので、本体は skill ではなく T2 に置いてある。語を変えると「どれが欠けているか」を
# 数えられなくなるので、この語のまま検査する。
APPROVAL_ITEMS='決めること 推奨 目的 位置 承認すると しないと 注意'
APPROVAL_TEMPLATE='docs/rules-reference/approval-template.md'
# 承認を求める箇所 (commands/ を全部 grep して洗い出した)。ここに載るコマンドは T2 の型を
# 参照していなければならない。テンプレートは丸写ししない (2 か所に書くと片方が陳腐化する)。
#   init.md は手順 5 の settings.json 差分承認が該当する。v1.14.0 は行数の都合で対象外にし、
#   その除外理由に「手順 8」と書いていた (実際の差分承認は手順 5、手順 8 は二重ロード検査)。
#   v1.14.2 で誤記ごと解消し、検査対象に入れた。
#   update.md / new-task.md は承認を求める箇所を持たない (報告して止まるだけ)。
APPROVAL_SITES='init.md update.md add-rule.md state.md config.md new-draft.md start-task.md finish-task.md commit.md rules-audit.md verify.md'

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

# update_flag_path <tmpdir> <project_root> -> 更新ありのフラグのパスを stdout。
# scripts/update-check.sh の harness_update_flag_file と同じ式 (cksum の鍵) を、
# source せずに再現する — case 1/8 はプラグインを source しない生の TMPDIR 操作で
# フラグを仕込む/読むので、鍵の式がここと 2 か所 (update-check.sh・statusline.sh) の
# 計 3 か所でずれると、この smoke 自体が壊れた式を検出できずに緑になる。
update_flag_path() {
  local td="$1" root="$2" key
  key="$(printf '%s' "$root" | cksum 2>/dev/null | awk '{print $1}')"
  [ -n "$key" ] || key="default"
  printf '%s/claude-harness-lite/update-available-%s' "$td" "$key"
}

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
  # フラグの鍵は CLAUDE_PROJECT_DIR ($std) の cksum。
  local flag1; flag1="$(update_flag_path "$std" "$std")"
  mkdir -p "$(dirname "$flag1")" && : > "$flag1"
  sout="$(printf '{"context_window":{"used_percentage":12}}' \
        | TMPDIR="$std" NO_COLOR=1 CLAUDE_PROJECT_DIR="$std" HARNESS_UPDATE_CHECK=on bash "$sl" 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ] || printf '%s' "$sout" | grep -q '更新あり'; then
    rm -rf "$std"; fail 1 "空の控えでは更新を知らせない" "exit=${rc}: $sout"; return
  fi
  # 壊れた控え + 壊れた JSON の同時発生でも 2 行 + exit 0
  printf '\001garbage\002' > "$flag1"
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

  # --- タスク管理の形: tasks: (mode.yml) が決める。自動では見分けない ---
  # 台帳の形 5 場合 (remote 無し・GitHub 以外・gh が失敗・Project 0 件・tasks: github-project で
  # hirai-task 無し) で、session-start と statusline が尋ねず・止まらず・GraphQL を打たない。
  # gh は偽物 (PATH の先頭) で、呼ばれたら引数を記録する。台帳の形では 1 回も呼ばれてはならない。
  local gw gwbin gwlog gwhome bad5="" sc scr sc_out sc_rc sc_sl sc_lines
  gw="$(mktemp -d)"; gwbin="$gw/bin"; gwlog="$gw/gh.log"; gwhome="$gw/home"
  mkdir -p "$gwbin" "$gwhome"; : > "$gwlog"
  # <名前> <remote の URL か -> <gh の挙動: fail|empty|ok> <mode.yml の中身か ->
  while read -r sc scr sc_gh sc_yml; do
    [ -n "$sc" ] || continue
    local srepo="$gw/$sc"
    mkdir -p "$srepo/.claude"; git -C "$srepo" init -q 2>/dev/null
    [ "$scr" = "-" ] || git -C "$srepo" remote add origin "$scr" 2>/dev/null
    [ "$sc_yml" = "-" ] || printf 'tasks: %s\n' "$sc_yml" > "$srepo/.claude/mode.yml"
    case "$sc_gh" in
      fail)  printf '#!/usr/bin/env bash\necho "$*" >> "%s"\nexit 1\n' "$gwlog" > "$gwbin/gh" ;;
      empty) printf '#!/usr/bin/env bash\necho "$*" >> "%s"\nexit 0\n' "$gwlog" > "$gwbin/gh" ;;
      *)     printf '#!/usr/bin/env bash\necho "$*" >> "%s"\nprintf "PVT_x\\t1\\n"\n' "$gwlog" > "$gwbin/gh" ;;
    esac
    chmod +x "$gwbin/gh"; : > "$gwlog"
    sc_out="$(PATH="$gwbin:/usr/bin:/bin" HOME="$gwhome" CLAUDE_PLUGIN_ROOT="$ROOT" CLAUDE_PROJECT_DIR="$srepo" \
              bash "$HOOKS/session-start.sh" 2>&1 </dev/null)"; sc_rc=$?
    sc_sl="$(printf '{"context_window":{"used_percentage":12}}' \
             | PATH="$gwbin:/usr/bin:/bin" HOME="$gwhome" TMPDIR="$gw" NO_COLOR=1 CLAUDE_PROJECT_DIR="$srepo" \
               bash "$ROOT/scripts/statusline.sh" 2>&1)"
    sc_lines="$(printf '%s\n' "$sc_out" | grep -c . || true)"
    [ "$sc_rc" -eq 0 ] || bad5="$bad5 [${sc}] session-start exit=${sc_rc}"
    [ "${sc_lines:-0}" -ge 1 ] && [ "${sc_lines:-0}" -le 5 ] || bad5="$bad5 [${sc}] session-start が ${sc_lines} 行"
    [ -s "$gwlog" ] && bad5="$bad5 [${sc}] gh が呼ばれた (GraphQL を打たない形のはず): $(head -c 200 "$gwlog")"
    if [ "$sc" = "no-hirai-task" ]; then
      # tasks: github-project で hirai-task が PATH に無い: 台帳へ落とさず、入れ方を 1 行で示す
      printf '%s' "$sc_out" | grep -qF '/plugin install hirai-project-method@hirai-lite' \
        || bad5="$bad5 [${sc}] 入れ方の 1 行が出ない: $sc_out"
      printf '%s' "$sc_out" | grep -qF 'やること一覧はまだありません' \
        && bad5="$bad5 [${sc}] github-project なのに台帳の形へ落ちた"
      printf '%s' "$sc_sl" | grep -qF 'hirai-project-method が未導入' \
        || bad5="$bad5 [${sc}] statusline が未導入を示さない: $sc_sl"
    else
      printf '%s' "$sc_out" | grep -qF 'やること一覧はまだありません' \
        || bad5="$bad5 [${sc}] 台帳の形の やること が出ない: $sc_out"
      printf '%s' "$sc_out" | grep -qF 'tasks: ledger' || bad5="$bad5 [${sc}] 設定行に tasks: ledger が無い"
      printf '%s' "$sc_sl" | grep -qF 'やること' || bad5="$bad5 [${sc}] statusline が台帳の形でない: $sc_sl"
    fi
    why="$(sl_shape "$sc_sl")" || bad5="$bad5 [${sc}] statusline 2 行 + 設定リンク: $why"
  done <<'EOF5'
no-remote      -                                        fail  -
not-github     git@gitlab.com:acme/widgets.git          fail  -
gh-fails       https://github.com/acme/widgets.git      fail  -
project-zero   https://github.com/acme/widgets.git      empty -
no-hirai-task  https://github.com/acme/widgets.git      ok    github-project
EOF5
  # tasks: が無い・未知の値でも尋ねて止まらず台帳の形 (typo は設定行に値が出る)
  local trepo="$gw/typo" tout
  mkdir -p "$trepo/.claude"; git -C "$trepo" init -q 2>/dev/null
  printf 'tasks: gh\n' > "$trepo/.claude/mode.yml"
  tout="$(PATH="$gwbin:/usr/bin:/bin" HOME="$gwhome" CLAUDE_PLUGIN_ROOT="$ROOT" CLAUDE_PROJECT_DIR="$trepo" \
          bash "$HOOKS/session-start.sh" 2>&1 </dev/null)"
  printf '%s' "$tout" | grep -qF 'やること一覧はまだありません' || bad5="$bad5 [typo] 未知の tasks: が台帳の形にならない: $tout"

  # tasks: github-project + 偽の hirai-task: line を読み、取り直し (--refresh) を待たない。
  # statusline は --refresh を付けない (gh を打たない)。
  local grepo="$gw/ghp" ghpbin="$gw/ghpbin" ghplog="$gw/hirai-task.log" gout gstart gelapsed gsl
  mkdir -p "$grepo/.claude" "$ghpbin"; git -C "$grepo" init -q 2>/dev/null
  printf 'tasks: github-project\n' > "$grepo/.claude/mode.yml"
  cat > "$ghpbin/hirai-task" <<EOF6
#!/usr/bin/env bash
echo "\$*" >> "$ghplog"
if [ "\$1" = line ] && [ "\${2:-}" = --refresh ]; then sleep 3; exit 0; fi
[ "\$1" = line ] && echo "6（承認 3・裁定 1・取り込み 2）／進行中 5／待ち解け —"
exit 0
EOF6
  chmod +x "$ghpbin/hirai-task"; : > "$ghplog"
  gstart="$(date +%s)"
  gout="$(PATH="$ghpbin:/usr/bin:/bin" HOME="$gwhome" CLAUDE_PLUGIN_ROOT="$ROOT" CLAUDE_PROJECT_DIR="$grepo" \
          bash "$HOOKS/session-start.sh" 2>&1 </dev/null | cat)"
  gelapsed=$(( $(date +%s) - gstart ))
  printf '%s' "$gout" | grep -qF 'Project: あなたの番 6（承認 3・裁定 1・取り込み 2）／進行中 5／待ち解け —' \
    || bad5="$bad5 [ghp] session-start が Project の行を出さない: $gout"
  [ "$gelapsed" -le 1 ] || bad5="$bad5 [ghp] session-start が取り直しを ${gelapsed} 秒待った"
  [ "$(printf '%s\n' "$gout" | grep -c . || true)" -le 5 ] || bad5="$bad5 [ghp] session-start が 5 行を超えた"
  printf '%s' "$gout" | grep -qF 'tasks: github-project' || bad5="$bad5 [ghp] 設定行に tasks: github-project が無い"
  : > "$ghplog"
  gsl="$(printf '{"context_window":{"used_percentage":12}}' \
         | PATH="$ghpbin:/usr/bin:/bin" HOME="$gwhome" TMPDIR="$gw" NO_COLOR=1 CLAUDE_PROJECT_DIR="$grepo" \
           bash "$ROOT/scripts/statusline.sh" 2>&1)"
  printf '%s' "$gsl" | grep -qF 'あなたの番 6（承認 3・裁定 1・取り込み 2）' || bad5="$bad5 [ghp] statusline が あなたの番 を出さない: $gsl"
  printf '%s' "$gsl" | grep -q 'やること' && bad5="$bad5 [ghp] statusline に旧見出し やること が残った"
  grep -qF -- '--refresh' "$ghplog" && bad5="$bad5 [ghp] statusline が --refresh を付けた (gh を打つ)"
  why="$(sl_shape "$gsl")" || bad5="$bad5 [ghp] statusline 2 行 + 設定リンク: $why"
  rm -rf "$gw"
  if [ -n "$bad5" ]; then fail 1 "tasks: の形で やること が出る (台帳の形 5 場合は尋ねず・GraphQL を打たない)" "$bad5"; return; fi

  # --- 足すプラグインの道具の場所・mode.yml の読み方・2.x からの移行・台帳の作り分け (1 巡目の直し) ---
  # hook と画面下では足すプラグインの bin/ は PATH に入らない。PATH に hirai-task が無くても、
  # installed_plugins.json の版が最大の行 (先頭でも末尾でもない並びで置く) から見つけること。
  # 値の引用符・行末コメント・ホームとプロジェクトの順・末尾 / の remote は /bin/bash (3.2) で見る。
  local mw mhome mpm mrepo mout msl mbad="" mblk mu mo
  mw="$(mktemp -d)"; mhome="$mw/home"; mpm="$mw/pm/1.0.0"; mrepo="$mw/repo"
  mkdir -p "$mhome/.claude/plugins" "$mpm/bin" "$mrepo/.claude"; git -C "$mrepo" init -q 2>/dev/null
  printf '#!/usr/bin/env bash\n[ "$1" = line ] && echo "7（承認 3・裁定 1・取り込み 3）／進行中 2／待ち解け —"\nexit 0\n' > "$mpm/bin/hirai-task"
  chmod +x "$mpm/bin/hirai-task"
  printf '{"plugins":{"hirai-project-method@hirai-lite":[{"version":"0.9.0","installPath":"%s/n1"},{"version":"1.0.0","installPath":"%s"},{"version":"0.1.0","installPath":"%s/n2"}]}}\n' \
    "$mw" "$mw/pm/1.0.0" "$mw" > "$mhome/.claude/plugins/installed_plugins.json"
  printf 'tasks: "github-project"  # c\nnotify: '"'orca'"'\nworktree: "block" # x\n' > "$mrepo/.claude/mode.yml"
  mout="$(env -i HOME="$mhome" PATH=/usr/bin:/bin CLAUDE_PLUGIN_ROOT="$ROOT" CLAUDE_PROJECT_DIR="$mrepo" /bin/bash "$HOOKS/session-start.sh" 2>&1 </dev/null)"
  printf '%s' "$mout" | grep -qF 'Project: あなたの番 7' || mbad="$mbad [PATH に hirai-task 無し] 開始時が足すプラグインを見つけない: $mout"
  printf '%s' "$mout" | grep -qF 'tasks: github-project' || mbad="$mbad [引用符・行末コメント] tasks: が読めない: $mout"
  [ "$(printf '%s\n' "$mout" | grep -c . || true)" -le 5 ] || mbad="$mbad [notify: orca] 開始時が 5 行を超えた"
  printf '%s' "$mout" | grep -qF 'notify: orca' || mbad="$mbad [notify: 'orca'] 引用符つきの値が読めない"
  msl="$(printf '{"context_window":{"used_percentage":12}}' | env -i HOME="$mhome" PATH=/usr/bin:/bin TMPDIR="$mw" NO_COLOR=1 \
         CLAUDE_PROJECT_DIR="$mrepo" /bin/bash "$ROOT/scripts/statusline.sh" 2>&1)"
  printf '%s' "$msl" | grep -qF 'あなたの番 7' || mbad="$mbad [PATH に hirai-task 無し] 画面下が足すプラグインを見つけない: $msl"
  # ホームとプロジェクトの順: 項目ごとにプロジェクト > ホーム。プロジェクトに無い項目はホームを読む
  printf 'tasks: github-project\nnotify: orca\n' > "$mhome/.claude/mode.yml"
  rm -f "$mrepo/.claude/mode.yml"
  mu="$(cd "$mrepo" && HOME="$mhome" /bin/bash -c ". \"$ROOT/scripts/tasks-path.sh\"; harness_tasks_form \"\$PWD\"")"
  [ "$mu" = github-project ] || mbad="$mbad [ホームだけ] tasks: がホームから読めない: ${mu}"
  printf 'tasks: ledger\nworktree: block\n' > "$mrepo/.claude/mode.yml"
  mu="$(cd "$mrepo" && HOME="$mhome" /bin/bash -c ". \"$ROOT/scripts/tasks-path.sh\"; harness_tasks_form \"\$PWD\"")"
  [ "$mu" = ledger ] || mbad="$mbad [両方] プロジェクトの tasks: がホームに負けた: ${mu}"
  mo="$(cd "$mrepo" && HOME="$mhome" /bin/bash -c ". \"$ROOT/scripts/tasks-path.sh\"; harness_yml_value \"\$PWD\" notify")"
  [ "$mo" = orca ] || mbad="$mbad [項目ごと] プロジェクトに無い notify: をホームから読まない: ${mo}"
  # /update 手順 2b を逐語に取り出して実行する。2.x の控え (末尾 / の remote) があれば github-project を書き、
  # 痕跡が無ければ推定で書かず、どちらもホームの mode.yml は作らない。
  mblk="$(awk '/^## 手順 2b/ {s=1} s && /^```bash$/ {c=1; next} c && /^```$/ {exit} c' "$ROOT/commands/update.md")"
  if [ -z "$mblk" ]; then mbad="$mbad [2b] update.md から手順 2b の bash を取り出せない"; else
    rm -rf "$mhome/.claude/mode.yml" "$mrepo/.claude/mode.yml"
    git -C "$mrepo" remote add origin https://github.com/acme/widgets/ 2>/dev/null
    mout="$(cd "$mrepo" && env HOME="$mhome" CLAUDE_PLUGIN_ROOT="$ROOT" /bin/bash -c "$mblk" 2>&1)"
    printf '%s' "$mout" | grep -qF '2.x の痕跡なし' || mbad="$mbad [2b] 2.x の痕跡が無いのに推定で書いた/案内しない: $mout"
    [ -e "$mrepo/.claude/mode.yml" ] && mbad="$mbad [2b] 2.x の痕跡が無いのに tasks: を書いた"
    mkdir -p "$mhome/.claude/plugins/data/hirai-lite-v2-hirai-lite"
    printf '{"form": "ghp"}\n' > "$mhome/.claude/plugins/data/hirai-lite-v2-hirai-lite/tasks-acme-widgets.json"
    mout="$(cd "$mrepo" && env HOME="$mhome" CLAUDE_PLUGIN_ROOT="$ROOT" /bin/bash -c "$mblk" 2>&1)"
    grep -qx 'tasks: github-project' "$mrepo/.claude/mode.yml" 2>/dev/null \
      || mbad="$mbad [2b] 末尾 / の remote で 2.x の控えを見つけて github-project を書かない: $mout"
    [ -e "$mhome/.claude/mode.yml" ] && mbad="$mbad [2b] ホームの mode.yml を作った"
  fi
  # /init 手順 7: tasks: github-project のリポには台帳 (list.md・parking-lot.md) を作らず、ledger (既定) では作る
  mblk="$(awk '/^## 7\. / {s=1} s && /^```bash$/ {c=1; next} c && /^```$/ {exit} c' "$ROOT/commands/init.md")"
  if [ -z "$mblk" ]; then mbad="$mbad [init 7] init.md から手順 7 の bash を取り出せない"; else
    mkdir -p "$mw/g/.claude" "$mw/l"
    printf 'tasks: github-project\n' > "$mw/g/.claude/mode.yml"
    (cd "$mw/g" && env HOME="$mhome" CLAUDE_PLUGIN_ROOT="$ROOT" /bin/bash -c "$mblk") >/dev/null 2>&1
    { [ -e "$mw/g/docs/tasks/list.md" ] || [ -e "$mw/g/docs/tasks/parking-lot.md" ]; } && mbad="$mbad [init 7] github-project のリポに台帳を作った"
    [ -e "$mw/g/docs/rules-reference/incidents.md" ] || mbad="$mbad [init 7] github-project のリポに事故記録が無い"
    rm -f "$mhome/.claude/mode.yml"
    (cd "$mw/l" && env HOME="$mhome" CLAUDE_PLUGIN_ROOT="$ROOT" /bin/bash -c "$mblk") >/dev/null 2>&1
    { [ -e "$mw/l/docs/tasks/list.md" ] && [ -e "$mw/l/docs/tasks/parking-lot.md" ]; } || mbad="$mbad [init 7] ledger のリポに台帳を作らない"
  fi
  rm -rf "$mw"
  if [ -n "$mbad" ]; then fail 1 "足すプラグインの道具は PATH 無しで見つかり、mode.yml は引用符・順を守って読まれ、移行と init は形に従う" "$mbad"; return; fi

  # --- new-task / start-task / finish-task: 形の見分け (harness_tasks_form) を先に行い、
  # GitHub Project の形の節は hirai-task を呼ぶだけで台帳 (list.md 系) を読み書きしない。
  # 土台は足すプラグインの関数 (harness_ghp_*) を直接呼ばない。
  local ghpcmd bad6="" sec fseesec gline tline
  for ghpcmd in new-task.md start-task.md finish-task.md; do
    sec="$(awk '/^## GitHub Project の形の場合$/ {f=1; next} f && /^## / {exit} f' "$ROOT/commands/$ghpcmd")"
    if [ -z "$sec" ]; then bad6="$bad6 ${ghpcmd}:GitHub Project の形の節が無い"; continue; fi
    printf '%s' "$sec" | grep -qF 'hirai-task' \
      || bad6="$bad6 ${ghpcmd}:GitHub Project の形の節が hirai-task を呼ばない"
    printf '%s' "$sec" | grep -qF '/plugin install hirai-project-method@hirai-lite' \
      || bad6="$bad6 ${ghpcmd}:hirai-task が無いときの入れ方が無い"
    printf '%s' "$sec" | grep -qE 'list\.md|\$LIST|docs/tasks|harness_tasks_file' \
      && bad6="$bad6 ${ghpcmd}:GitHub Project の形の節が台帳 (list.md 系) を参照する行を持つ"
    fseesec="$(awk '/^## 形の見分け/ {f=1; next} f && /^## / {exit} f' "$ROOT/commands/$ghpcmd")"
    printf '%s' "$fseesec" | grep -qF 'harness_tasks_form' \
      || bad6="$bad6 ${ghpcmd}:形の見分けの節が harness_tasks_form を呼ばない"
    gline="$(grep -n 'harness_tasks_form' "$ROOT/commands/$ghpcmd" | head -1 | cut -d: -f1)"
    tline="$(grep -n 'harness_tasks_file' "$ROOT/commands/$ghpcmd" | head -1 | cut -d: -f1)"
    if [ -n "$gline" ] && [ -n "$tline" ] && [ "$gline" -ge "$tline" ]; then
      bad6="$bad6 ${ghpcmd}:harness_tasks_form の呼び出しが harness_tasks_file より後"
    fi
  done
  if grep -rqE 'harness_ghp_' "$ROOT/commands" "$ROOT/hooks" "$ROOT/scripts" 2>/dev/null; then
    bad6="$bad6 土台が足すプラグインの関数 (harness_ghp_*) を直接呼んでいる: $(grep -rlE 'harness_ghp_' "$ROOT/commands" "$ROOT/hooks" "$ROOT/scripts" | head -3 | tr '\n' ' ')"
  fi
  if [ -n "$bad6" ]; then fail 1 "new-task・start-task・finish-task は形の見分けを先に行い、github-project の形で hirai-task を呼び、台帳を書かない" "$bad6"; return; fi

  pass 1 "session-start.sh は対象ファイル不在でも exit 0 / ${lines} 行 / [harness] prefix あり / statusline も空 stdin・壊れた JSON・控え不在/空/壊れで 2 行 + 設定リンク常時 + exit 0 (色あり/NO_COLOR とも) / 進め方は置き場 5 通りで冒頭と画面下部が一致し /config は在る側に書く / /update 手順 2-2 の移行は中身を保ち同名は上書きせず両方残し、移行後は冒頭と画面下部が docs/ の台帳を読む / /init 第 2 段階は 事実収集 → 範囲提示 → grilling 呼び出し の順で、事実収集の bash は中身ありでも空でも exit 0、grilling へ渡す指示に範囲の制約 (調達・法務へ踏み込まない / 不要な質問は落とす / 事実は自分で調べる) が入っている / tasks: の形は mode.yml が決め (自動で見分けない)、台帳の形 5 場合 (remote 無し・GitHub 以外・gh が失敗・Project 0 件・tasks: github-project で hirai-task 無し) で冒頭と画面下部が尋ねず exit 0・5 行以内・gh を 1 回も呼ばず、hirai-task 無しは入れ方を 1 行示し、tasks: github-project + hirai-task は冒頭が取り直しを待たず画面下部が --refresh を付けずに あなたの番 を出す / PATH に hirai-task が無くても開始時と画面下が installed_plugins.json の版が最大の行から足すプラグインを見つけ、mode.yml の引用符・行末コメントを外して読み、項目ごとにプロジェクト > ホームの順で読み、notify: orca でも開始時は 5 行以内、/update 手順 2b は末尾 / の remote でも 2.x の控えを見つけて github-project を書き痕跡が無ければ書かずホームに書かず、/init 手順 7 は ledger のときだけ台帳を作る (/bin/bash 3.2) / new-task・start-task・finish-task は形の見分けを先に行い、GitHub Project の形の節は hirai-task を呼び入れ方を示し台帳を書かず、土台は harness_ghp_* を直接呼ばない"
}

# ---------- case 2: UserPromptSubmit の 2 本は、出してよい時だけ出す ----------
# (a) context-budget.sh は閾値未満で無出力
# (b) loop-reminder.sh は進め方が loop のときだけ出す (v1.11.0)。
#     **normal での無出力が最重要**。確認しながら進めたい利用者に毎ターン「確認を求めるな」が
#     入るのは、機能ではなく害。進め方の解決は scripts/tasks-path.sh の harness_mode 1 本に
#     通しているので、置き場 6 通り (ホーム / プロジェクト / 両方 / 無し) で出す・出さないを見る。
case_2() {
  local out rc
  # 既定の閾値は 50% (v1.15.0、80% → 50% に変更)。HC_CONTEXT_THRESHOLD を指定せず境界を見る:
  # 49% は無出力、50% ちょうどで発火する。
  out="$(TMPDIR="$(mktemp -d)" HC_CONTEXT_RATIO=0.49 bash "$HOOKS/context-budget.sh" \
        <<< '{"session_id":"smoke-under-49"}' 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then fail 2 "閾値未満 (49%) は無出力" "exit=$rc"; return; fi
  if [ -n "$out" ]; then fail 2 "閾値未満 (49%) は無出力" "出力あり: $out"; return; fi
  out="$(TMPDIR="$(mktemp -d)" HC_CONTEXT_RATIO=0.50 bash "$HOOKS/context-budget.sh" \
        <<< '{"session_id":"smoke-at-50"}' 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then fail 2 "既定の閾値 50% ちょうどで発火" "exit=$rc"; return; fi
  if ! printf '%s' "$out" | grep -q '使用率が 50%'; then
    fail 2 "既定の閾値 50% ちょうどで発火" "出力: ${out:-無}"; return
  fi

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

  # (c) worktree-guard.sh (PreToolUse・v3.0.0。_meta.md 条 5 の唯一の例外)。`worktree: block` のとき
  # Orca の worktree でない会話からの、リポの中の git に入るファイルの編集と git commit だけを止める。
  # 止めない側 (読み取り・リポの外・git に入らない場所・git switch / checkout・worktree の会話・off / warn)
  # が崩れると、無関係な作業まで止まる (止める範囲が条 5 の例外を超える)。使い捨ての repo と
  # linked worktree で、止める 6 場合と止めない 9 場合を実挙動で見る。
  local wg="$ROOT/hooks/worktree-guard.sh" gw gm gl gout gname gwant gcase gjson gcwd gwt_env gmode
  if ! command -v jq >/dev/null 2>&1; then
    fail 2 "worktree-guard の確かめに jq が要る" "jq が無い (hook は fail-open で通すため、確かめられない)"; return
  fi
  gw="$(mktemp -d)"; gm="$gw/main"; gl="$gw/wt"
  mkdir -p "$gm/.claude" "$gw/home" "$gw/outside"
  git -C "$gm" init -q 2>/dev/null
  printf '.tmp/\n' > "$gm/.gitignore"; printf 'x\n' > "$gm/a.txt"
  printf 'worktree: block\n' > "$gm/.claude/mode.yml"
  git -C "$gm" add -A 2>/dev/null
  git -C "$gm" -c user.name=t -c user.email=t@example.com commit -q -m init 2>/dev/null
  git -C "$gm" worktree add -q "$gl" -b smoke-wt 2>/dev/null
  mkdir -p "$gm/.tmp"
  # <名前> <期待: deny|pass> <cwd の種別: main|wt> <ORCA_WORKTREE_ID: yes|no> <worktree の値: block|off|warn> <JSON>
  while IFS='|' read -r gname gwant gcwd gwt_env gmode gjson; do
    [ -n "$gname" ] || continue
    local gdir="$gm"; [ "$gcwd" = wt ] && gdir="$gl"
    gjson="${gjson//@D@/$gdir}"; gjson="${gjson//@O@/$gw/outside}"
    if [ "$gwt_env" = yes ]; then
      gout="$(printf '%s' "$gjson" | env HOME="$gw/home" ORCA_WORKTREE_ID=wt-1 CLAUDE_PROJECT_DIR="$gdir" HC_WORKTREE="$gmode" bash "$wg" 2>&1)"; rc=$?
    else
      gout="$(printf '%s' "$gjson" | env -u ORCA_WORKTREE_ID HOME="$gw/home" CLAUDE_PROJECT_DIR="$gdir" HC_WORKTREE="$gmode" bash "$wg" 2>&1)"; rc=$?
    fi
    if [ "$rc" -ne 0 ]; then bad="$bad [guard:${gname}] exit=${rc}"; continue; fi
    if printf '%s' "$gout" | grep -q '"permissionDecision": *"deny"'; then gcase=deny; else gcase=pass; fi
    [ "$gcase" = "$gwant" ] || bad="$bad [guard:${gname}] 期待=${gwant} 実際=${gcase}: ${gout}"
    if [ "$gwant" = deny ]; then
      printf '%s' "$gout" | grep -q 'orca worktree create' || bad="$bad [guard:${gname}] worktree の作り方が出ない"
    elif [ -n "$gout" ]; then bad="$bad [guard:${gname}] 通すのに出力がある: ${gout}"; fi
  done <<'EOF_GUARD'
追跡ファイルの Edit|deny|main|no|block|{"tool_name":"Edit","cwd":"@D@","tool_input":{"file_path":"@D@/a.txt"}}
git に入る新規ファイルの Write|deny|main|no|block|{"tool_name":"Write","cwd":"@D@","tool_input":{"file_path":"@D@/docs/new.md"}}
git commit|deny|main|no|block|{"tool_name":"Bash","cwd":"@D@","tool_input":{"command":"git commit -m x"}}
add の後ろの git commit|deny|main|no|block|{"tool_name":"Bash","cwd":"@D@","tool_input":{"command":"git add -A && git commit -m x"}}
ORCA_WORKTREE_ID があっても本体の checkout|deny|main|yes|block|{"tool_name":"Edit","cwd":"@D@","tool_input":{"file_path":"@D@/a.txt"}}
worktree でも ORCA_WORKTREE_ID が無い|deny|wt|no|block|{"tool_name":"Edit","cwd":"@D@","tool_input":{"file_path":"@D@/a.txt"}}
git に入らない .tmp への Write|pass|main|no|block|{"tool_name":"Write","cwd":"@D@","tool_input":{"file_path":"@D@/.tmp/r.md"}}
リポの外への Write|pass|main|no|block|{"tool_name":"Write","cwd":"@D@","tool_input":{"file_path":"@O@/memo.md"}}
git switch|pass|main|no|block|{"tool_name":"Bash","cwd":"@D@","tool_input":{"command":"git switch -c feat/x"}}
git checkout -b|pass|main|no|block|{"tool_name":"Bash","cwd":"@D@","tool_input":{"command":"git checkout -b feat/y"}}
読み取り (git log --grep commit)|pass|main|no|block|{"tool_name":"Bash","cwd":"@D@","tool_input":{"command":"git log --grep commit"}}
Orca の worktree の Edit|pass|wt|yes|block|{"tool_name":"Edit","cwd":"@D@","tool_input":{"file_path":"@D@/a.txt"}}
Orca の worktree の git commit|pass|wt|yes|block|{"tool_name":"Bash","cwd":"@D@","tool_input":{"command":"git commit -m x"}}
worktree: off|pass|main|no|off|{"tool_name":"Edit","cwd":"@D@","tool_input":{"file_path":"@D@/a.txt"}}
worktree: warn|pass|main|no|warn|{"tool_name":"Bash","cwd":"@D@","tool_input":{"command":"git commit -m x"}}
EOF_GUARD
  # 壊れた入力・空の入力でも落ちず 1 バイトも出さない (fail-open)
  for gjson in '' 'zzz' '{"tool_name":'; do
    gout="$(printf '%s' "$gjson" | env -u ORCA_WORKTREE_ID HOME="$gw/home" CLAUDE_PROJECT_DIR="$gm" HC_WORKTREE=block bash "$wg" 2>&1)"; rc=$?
    { [ "$rc" -eq 0 ] && [ -z "$gout" ]; } || bad="$bad [guard:壊れた入力 ${gjson:-空}] exit=${rc} 出力:${gout}"
  done
  # mode.yml の値を読む (env を使わない経路): block のときだけ止め、項目が無ければ通す
  gout="$(printf '%s' "{\"tool_name\":\"Edit\",\"cwd\":\"$gm\",\"tool_input\":{\"file_path\":\"$gm/a.txt\"}}" \
        | env -u ORCA_WORKTREE_ID -u HC_WORKTREE HOME="$gw/home" CLAUDE_PROJECT_DIR="$gm" bash "$wg" 2>&1)"
  printf '%s' "$gout" | grep -q '"permissionDecision": *"deny"' || bad="$bad [guard:mode.yml の worktree: block を読まない] ${gout}"
  printf 'mode: normal\n' > "$gm/.claude/mode.yml"
  gout="$(printf '%s' "{\"tool_name\":\"Edit\",\"cwd\":\"$gm\",\"tool_input\":{\"file_path\":\"$gm/a.txt\"}}" \
        | env -u ORCA_WORKTREE_ID -u HC_WORKTREE HOME="$gw/home" CLAUDE_PROJECT_DIR="$gm" bash "$wg" 2>&1)"
  [ -z "$gout" ] || bad="$bad [guard:worktree の項目が無いのに止めた] ${gout}"
  git -C "$gm" worktree remove --force "$gl" 2>/dev/null
  rm -rf "$gw"
  # (c2) 守るリポの決め方・コマンド形の読み取り・jq 無し (1 巡目の直し)。block のリポ P と無印のリポ Q を置き、
  # cwd ではなく**操作の対象**のリポで決めること、`git commit` の形が崩れても落とさないこと、heredoc の本文と
  # --dry-run を止めないこと、.tmp/ と .claude/state/ を止めないこと、jq が無くても python3 で読むことを見る。
  local g2w g2p g2q g2n g2bin g2t g2i=0 g2c g2out g2got
  g2w="$(mktemp -d)"; g2p="$g2w/P"; g2q="$g2w/Q"; g2n="$g2w/NR"
  mkdir -p "$g2p/.claude" "$g2q" "$g2n" "$g2w/home" "$g2w/bin"
  for g2c in "$g2p" "$g2q"; do
    git -C "$g2c" init -q 2>/dev/null; printf 'x\n' > "$g2c/a.txt"; git -C "$g2c" add -A 2>/dev/null
    git -C "$g2c" -c user.name=t -c user.email=t@example.com commit -q -m init 2>/dev/null
  done
  printf 'worktree: "block"  # c\n' > "$g2p/.claude/mode.yml"
  # g2 <名前> <deny|pass> <JSON> [bash の実行ファイル] [PATH]
  g2() {
    g2out="$(printf '%s' "$3" | env -u ORCA_WORKTREE_ID -u HC_WORKTREE HOME="$g2w/home" CLAUDE_PROJECT_DIR="${G2_PROJ:-$g2p}" \
             PATH="${5:-$PATH}" "${4:-bash}" "$wg" 2>&1)"; g2got=$?
    [ "$g2got" -eq 0 ] || { bad="$bad [guard2:$1] exit=${g2got}"; return; }
    if printf '%s' "$g2out" | grep -q '"permissionDecision": *"deny"'; then g2got=deny; else g2got=pass; fi
    [ "$g2got" = "$2" ] || bad="$bad [guard2:$1] 期待=$2 実際=${g2got}: ${g2out}"
  }
  g2b() { jq -nc --arg c "$1" --arg d "$2" '{tool_name:"Bash",cwd:$d,tool_input:{command:$c}}'; }
  g2e() { jq -nc --arg f "$1" --arg d "$2" '{tool_name:"Edit",cwd:$d,tool_input:{file_path:$f}}'; }
  # 守るリポは操作の対象で決める (cwd ではない)
  g2 "別リポへの git -C commit (P から Q)" pass "$(g2b "git -C $g2q commit -m x" "$g2p")"
  G2_PROJ="$g2q" g2 "別リポへの git -C commit (Q から P)" deny "$(g2b "git -C $g2p commit -m x" "$g2q")"
  g2 "別リポの Edit (cwd は P)" pass "$(g2e "$g2q/a.txt" "$g2p")"
  G2_PROJ="$g2q" g2 "P の Edit (cwd は Q)" deny "$(g2e "$g2p/a.txt" "$g2q")"
  g2 "P の Edit (cwd が非リポ)" deny "$(g2e "$g2p/a.txt" "$g2n")"
  g2 "cwd が非リポの git commit" deny "$(g2b 'git commit -m x' "$g2n")"
  G2_PROJ="$g2q" g2 "cwd が非リポの git -C P commit" deny "$(g2b "git -C $g2p commit -m x" "$g2n")"
  # 止めない場所
  g2 ".tmp/ は .gitignore に無くても通す" pass "$(g2e "$g2p/.tmp/x.md" "$g2p")"
  g2 ".claude/state/ は通す" pass "$(g2e "$g2p/.claude/state/latest.md" "$g2p")"
  g2 "docs/ の新規は止める" deny "$(g2e "$g2p/docs/n.md" "$g2p")"
  g2 "--dry-run は通す" pass "$(g2b 'git commit --dry-run' "$g2p")"
  g2 "--help は通す" pass "$(g2b 'git commit --help' "$g2p")"
  g2 "heredoc の本文の git commit は通す" pass "$(g2b $'cat > .tmp/s.md <<\'EOF\'\ngit commit -m "feat: x"\nEOF' "$g2p")"
  g2 "heredoc の後ろの本物は止める" deny "$(g2b $'cat <<EOF >/dev/null\nhi\nEOF\ngit commit -m x' "$g2p")"
  # commit の形 12 + 引用符つきの空白 path の -C + バックスラッシュ改行 + &&
  while IFS= read -r g2c; do
    [ -n "$g2c" ] || continue; g2i=$((g2i + 1))
    g2 "M1-${g2i}: ${g2c}" deny "$(g2b "$g2c" "$g2p")"
  done <<'EOF_M1'
if true; then git commit -m x; fi
{ git commit -m x; }
for i in 1; do git commit -m x; done
! git commit -m x
time git commit -m x
env GIT_EDITOR=true git commit -m x
echo a | xargs git commit -m
bash -c 'git commit -m x'
/usr/bin/git commit -m x
GIT_AUTHOR_NAME="a b" git commit -m x
git --git-dir=.git --work-tree=. commit -m x
pnpm ci:local && git commit -m x
EOF_M1
  mkdir -p "$g2w/sp dir/.claude"; git -C "$g2w/sp dir" init -q 2>/dev/null; printf 'worktree: block\n' > "$g2w/sp dir/.claude/mode.yml"
  G2_PROJ="$g2q" g2 "-C の引用符つき空白 path" deny "$(g2b "git -C \"$g2w/sp dir\" commit -m x" "$g2q")"
  g2 "バックスラッシュ改行" deny "$(g2b $'git \\\ncommit -m x' "$g2p")"
  g2 "git log --grep commit は通す" pass "$(g2b 'git log --grep commit' "$g2p")"
  g2 "bash 3.2 でも止める" deny "$(g2b 'git commit -m x' "$g2p")" /bin/bash
  # jq が無いとき: python3 で読んで止める。jq も python3 も無いときは止めず (fail-open) 無出力
  for g2t in bash sh cat sed awk head git env dirname basename tr python3 mktemp grep ls uname; do
    command -v "$g2t" >/dev/null 2>&1 && ln -sf "$(command -v "$g2t")" "$g2w/bin/$g2t"
  done
  g2 "jq 無し (python3 あり) の git commit" deny "$(g2b 'git commit -m x' "$g2p")" /bin/bash "$g2w/bin"
  g2 "jq 無し (python3 あり) の Edit" deny "$(g2e "$g2p/a.txt" "$g2p")" /bin/bash "$g2w/bin"
  rm -f "$g2w/bin/python3"
  g2 "jq も python3 も無いときは止めない" pass "$(g2b 'git commit -m x' "$g2p")" /bin/bash "$g2w/bin"
  g2out="$(env -u ORCA_WORKTREE_ID -u HC_WORKTREE PATH="$g2w/bin" CLAUDE_PROJECT_DIR="$g2p" HOME="$g2w/home" /bin/bash "$ROOT/scripts/orca-context.sh" 2>&1)"
  printf '%s' "$g2out" | grep -qF '止まりません' || bad="$bad [orca-context:jq も python3 も無いのに止まると言う] ${g2out}"
  rm -rf "$g2w"
  # hooks.json が PreToolUse を worktree-guard.sh に結んでいる (hook 本体があっても結ばれていなければ働かない)
  python3 - "$ROOT/hooks/hooks.json" <<'PYEOF' || bad="$bad [hooks.json に PreToolUse の worktree-guard.sh が結ばれていない]"
import json, sys
h = json.load(open(sys.argv[1]))["hooks"].get("PreToolUse", [])
ok = any("Edit" in e.get("matcher", "") and "Bash" in e.get("matcher", "")
         and any("worktree-guard.sh" in x.get("command", "") for x in e.get("hooks", [])) for e in h)
sys.exit(0 if ok else 1)
PYEOF
  # hooks.json が Notification (matcher permission_prompt) と PermissionDenied を notify-attention.sh に結んでいる
  python3 - "$ROOT/hooks/hooks.json" <<'PYEOF' || bad="$bad [hooks.json に Notification(permission_prompt) と PermissionDenied の notify-attention.sh が結ばれていない]"
import json, sys
h = json.load(open(sys.argv[1]))["hooks"]
def wired(ev, matcher):
    return any(e.get("matcher", "") == matcher
               and any("notify-attention.sh" in x.get("command", "") for x in e.get("hooks", [])) for e in h.get(ev, []))
sys.exit(0 if wired("Notification", "permission_prompt") and wired("PermissionDenied", "") else 1)
PYEOF
  if [ -n "$bad" ]; then fail 2 "止める手段と fail-open" "$bad"; return; fi

  pass 2 "context-budget.sh は既定の閾値 50% (v1.15.0) を境に 49% 無出力・50% ちょうどで発火 / loop-reminder.sh は置き場 6 通りで loop のときだけ ${lines} 行を出し normal では 1 バイトも出さない (要点 4 つ入り・全行 [harness] 始まり) / HC_LOOP_REMINDER=off・大文字 LOOP・壊れた/読めない mode.yml・共通ライブラリ不在でも exit 0 無出力 / worktree-guard.sh は worktree: block のとき、Orca の worktree でない会話からの git に入るファイルの Edit・Write と git commit を止めて worktree の作り方を出し (6 場合)、.tmp・リポの外・git switch・git checkout -b・読み取り・Orca の worktree の編集と commit・off・warn は通し (9 場合)、壊れた入力は fail-open、mode.yml の項目で働き、hooks.json の PreToolUse に結ばれている / 守るリポは cwd ではなく操作の対象 (git -C・Edit の file_path) で決め (別リポ・cwd が非リポ 7 場合)、git commit の形 12 と引用符つき -C・バックスラッシュ改行を止め、heredoc の本文・--dry-run・--help・.tmp/・.claude/state/ は止めず、/bin/bash 3.2 でも止め、jq 無しは python3 で読み、どちらも無ければ止めずに orca-context が「止まりません」と言う"
}

# ---------- case 3: 閾値超過で 1 度だけ発火 ----------
case_3() {
  local td first second
  td="$(mktemp -d)"
  first="$(TMPDIR="$td" HC_CONTEXT_RATIO=0.85 bash "$HOOKS/context-budget.sh" <<< '{"session_id":"smoke-over"}' 2>&1)"
  second="$(TMPDIR="$td" HC_CONTEXT_RATIO=0.85 bash "$HOOKS/context-budget.sh" <<< '{"session_id":"smoke-over"}' 2>&1)"
  rm -rf "$td"
  if ! printf '%s' "$first" | grep -q '/hirai-lite:state save'; then fail 3 "閾値超過で 1 度だけ発火" "1 回目が無出力"; return; fi
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

  # --- 窓推定 (v1.15.0): 控えも env も無く、使用トークンが 200,000 を超えるときは
  # 窓を 1,000,000 と推定し、表示に「（推定）」を添える。推定してもなお超える (1,000,000 超) ときは
  # 窓サイズ不明として発火しない (誤発火より沈黙)。HC_CONTEXT_WINDOW の明示は推定より優先する。
  rm -rf "$ct/claude-harness-lite"
  local tr_est="$ct/tr-est-300000.jsonl" tr_unk="$ct/tr-est-1200000.jsonl" est
  printf '{"type":"assistant","message":{"usage":{"input_tokens":300000,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":0,"server_tool_use":{"web_search_requests":0},"iterations":[{"input_tokens":999999,"output_tokens":999999}]}}}\n' > "$tr_est"
  printf '{"type":"assistant","message":{"usage":{"input_tokens":1200000,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":0,"server_tool_use":{"web_search_requests":0},"iterations":[{"input_tokens":999999,"output_tokens":999999}]}}}\n' > "$tr_unk"

  est="$(printf '{"session_id":"est-300k","transcript_path":"%s"}' "$tr_est" \
        | TMPDIR="$ct" HC_CONTEXT_THRESHOLD=0.0001 bash "$HOOKS/context-budget.sh" 2>/dev/null)"
  printf '%s' "$est" | grep -q '使用率が 30%' || bad3="$bad3 窓推定 (300000/1000000)=${est:-無}(期待 使用率が 30%)"
  printf '%s' "$est" | grep -q '窓 1000000 tokens（推定）' || bad3="$bad3 窓推定の表示=${est:-無}(期待 窓 1000000 tokens（推定）)"

  est="$(printf '{"session_id":"est-1200k","transcript_path":"%s"}' "$tr_unk" \
        | TMPDIR="$ct" HC_CONTEXT_THRESHOLD=0.0001 bash "$HOOKS/context-budget.sh" 2>/dev/null)"
  [ -z "$est" ] || bad3="$bad3 推定してもなお超過 (1200000)=出力あり(期待 無出力): $est"

  est="$(printf '{"session_id":"est-explicit","transcript_path":"%s"}' "$tr_est" \
        | TMPDIR="$ct" HC_CONTEXT_WINDOW=200000 HC_CONTEXT_THRESHOLD=0.0001 \
          bash "$HOOKS/context-budget.sh" 2>/dev/null)"
  printf '%s' "$est" | grep -q '使用率が 150%' || bad3="$bad3 HC_CONTEXT_WINDOW 明示時は推定しない=${est:-無}(期待 使用率が 150%)"
  printf '%s' "$est" | grep -q '（推定）' && bad3="$bad3 明示指定なのに（推定）が付いた: $est"

  # 異常入力 (空 stdin / 壊れた JSON / transcript が無い) でも黙って exit 0
  local src3 rc3 out
  for src3 in '' '{"session_id":' 'zzz' '{"session_id":"x","transcript_path":"/nope/none.jsonl"}'; do
    out="$(printf '%s' "$src3" | TMPDIR="$ct" bash "$HOOKS/context-budget.sh" 2>&1)"; rc3=$?
    [ "$rc3" -eq 0 ] || bad3="$bad3 [異常入力 ${src3}] exit=${rc3}"
    [ -z "$out" ] || bad3="$bad3 [異常入力 ${src3}] 出力あり: ${out}"
  done
  rm -rf "$ct"
  if [ -n "$bad3" ]; then fail 3 "窓サイズ不明時の既定 / 推定 / 異常入力" "$bad3"; return; fi

  pass 3 "context-budget.sh は 0.85 で 1 度発火し 2 度目は沈黙 / 画面下部と自動処理が同じ使用率 (窓 200k・1M × 5 通りで一致) / 窓が分からず 200,000 以下なら 200,000 とみなし HC_CONTEXT_WINDOW が優先 / 200,000 超なら 1,000,000 と推定し（推定）を表示 (v1.15.0) / 推定してもなお超えれば窓サイズ不明として無出力 / 空 stdin・壊れた JSON・transcript 不在でも無出力 exit 0"
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

  # 承認の規範は 3 点セットで成り立つ — T0 にカードの語 (ここ) / T1 からポインタ (ここ) /
  # T2 に本体と記入例 (case 10)。T0 側だけ消えると、コマンドを経由しない承認
  # (会話の中でのタスク着手や仕様変更の提案) が素通りする。承認は全作業に起きるので T0 に置く。
  local core="$ROOT/rules/core.md" it bad5="" nline
  if [ ! -f "$core" ]; then fail 5 "rules/core.md が存在する" "無い"; return; fi
  nline="$(grep -c '承認はカードで求める' "$core" | tr -d ' ')"
  if [ "${nline:-0}" -eq 0 ]; then
    bad5="承認の 1 行が core.md に無い"
  else
    # T0 に置いてよいのはカードの語と 1 行目の形まで。本体を書き写して T0 を太らせない (2 行以内)。
    # その 1 件が占める物理行数 = 見出し行 + 次の箇条書き/空行/見出しに当たるまでの続き行。
    local own
    own="$(awk '
      f && (/^- / || /^[[:space:]]*$/ || /^#/) { exit }
      f { n++ }
      /承認はカードで求める/ { f = 1; n = 1 }
      END { print n + 0 }
    ' "$core")"
    if [ "${own:-0}" -gt 2 ]; then
      bad5="$bad5 core.md:承認の記述が ${own} 行 (2 行以内。本体は T2 へ)"
    fi
    for it in $APPROVAL_ITEMS; do
      grep -qF "$it" "$core" || bad5="$bad5 core.md:[${it}]が無い"
    done
  fi
  # _meta.md 条 5 は承認された全文 (2026-11-23。例外は worktree: block の 1 つだけ) のまま。
  # 例外の範囲 (編集と git commit まで・読み取り / リポの外 / git に入らない場所 / branch の切り替えは止めない)
  # と失効条件が欠けると、止める hook が条 5 の許す範囲を超える。語を 1 つ変えても落ちるよう全文で比べる。
  local meta5_want meta5_got
  meta5_want='5. **機械強制は不可逆操作のみ**: `settings.json` の `deny` / `ask` と hook で止めてよいのは「間違えたら戻せない」操作だけ。本条が禁じているのは**止める**仕組みなので、context を注ぐだけの hook（reminder / 表示）は対象外。例外は 1 つ — `.claude/mode.yml` に `worktree: block` を置いたリポでは、Orca の worktree でない会話からの、リポの中の git に入るファイルの編集と `git commit` を止めてよい（並行の会話が同じ作業ツリーを触る事故を、編集の時点で止める）。読み取り・リポの外（`~/.claude` の記憶の置き場など）と git に入らない場所への書き込み・branch の切り替えは止めない。例外の失効: そのリポが `worktree: block` を外したとき'
  meta5_got="$(grep -m1 '^5\. \*\*機械強制は不可逆操作のみ' "$ROOT/rules/_meta.md" 2>/dev/null)"
  [ "$meta5_got" = "$meta5_want" ] || bad5="$bad5 _meta.md 条 5 が承認された全文と違う: ${meta5_got:-無}"
  # T1 (タスク・設計の承認を扱う層) から T2 へのポインタ
  local tk="$ROOT/rules/tasks.md"
  if [ ! -f "$tk" ]; then bad5="$bad5 rules/tasks.md が無い"
  elif ! grep -qF "$APPROVAL_TEMPLATE" "$tk"; then
    bad5="$bad5 tasks.md:承認テンプレートへのポインタが無い"
  fi
  # GitHub Project の形の立ち上げ手順 (足すプラグイン hirai-project-method の T2): 4 手順・自動化 4 本 (設定値つき)・ビュー 8 枚・画面でしか付けられない 3 つ
  local ps="$ROOT/plugins/hirai-project-method/docs/rules-reference/project-setup.md" it badps=""
  if [ ! -f "$ps" ]; then badps="project-setup.md が無い"
  else
    for it in 'is:pr' '階層表示' '並べ替え' 'グループ化' '## 1. 立ち上げの 4 手順' '## 6. ビュー 8 枚'; do
      grep -qF -- "$it" "$ps" || badps="$badps [${it}]が無い"
    done
    # 章ごとに区切って数える (別の章に同じ語があっても通さない)
    sec() { awk -v h="$1" '$0 ~ "^## "h"\\." {f=1;next} /^## /{f=0} f' "$ps"; }
    [ "$(sec 1 | grep -cE '^[1-4]\. ')" -eq 4 ] || badps="$badps 1章:番号つきの手順が 4 本でない"
    [ "$(sec 3 | grep -cE '^\| (Item added to project|Pull request linked to issue|Item closed|Auto-add to project) ')" -eq 4 ] || badps="$badps 3章:自動化の表が 4 本でない"
    sec 3 | grep -E '^\| Item added to project ' | grep -qF 'Set Status = 承認待ち' && sec 3 | grep -E '^\| Item added to project ' | grep -q 'issue だけ' || badps="$badps 3章:Item added の設定値(issue だけ・承認待ち)が無い"
    sec 3 | grep -E '^\| Pull request linked to issue ' | grep -qF 'Set Status = レビュー中' || badps="$badps 3章:Pull request linked の設定値(レビュー中)が無い"
    sec 3 | grep -E '^\| Item closed ' | grep -qF 'Set Status = 完了' && sec 3 | grep -E '^\| Item closed ' | grep -q 'issue だけ' || badps="$badps 3章:Item closed の設定値(issue だけ・完了)が無い"
    sec 3 | grep -E '^\| Auto-add to project ' | grep -qF 'is:pr' || badps="$badps 3章:Auto-add の設定値(is:pr)が無い"
    [ "$(sec 6 | grep -E '^\| ' | grep -v '^|---' | grep -vc '^| ビュー')" -eq 8 ] || badps="$badps 6章:ビューの表が 8 行でない"
  fi
  if [ -n "$bad5" ]; then fail 5 "承認は T0 に名前 / T1 からポインタ" "$bad5"; return; fi
  if [ -n "$badps" ]; then fail 5 "project-setup.md の立ち上げ手順・自動化・ビュー" "$badps"; return; fi
  # T2 は形を区別して書く (台帳が既定、GitHub Project は足すプラグイン): 承認の型の記入例は台帳 (list.md) を指さず、task-ledger.md は 2 つの形の区別を冒頭に持つ
  local rr="$ROOT/docs/rules-reference" badt2=""
  grep -qE 'list\.md|docs/tasks/|task-[0-9<]' "$rr/approval-template.md" && badt2="$badt2 approval-template.md が list.md を指す"
  grep -E 'list\.md|docs/tasks/|task-[0-9<]' "$rr/git-and-pr.md" | grep -vF '台帳の形' | grep -q . && badt2="$badt2 git-and-pr.md が形の区別なく list.md を指す"
  grep -n 'list.md' "$ROOT/docs/draft/README.md" | grep -vF '台帳の形' | grep -vF '一覧表を持つ形' | grep -q . && badt2="$badt2 docs/draft/README.md が形の区別なく list.md を指す行を持つ"
  grep -qF '2 つの形の区別' "$rr/task-ledger.md" || badt2="$badt2 task-ledger.md に 2 つの形の区別が無い"
  if [ -n "$badt2" ]; then fail 5 "T2 は形を区別して書く (台帳の形が既定・GitHub Project は足すプラグイン)" "$badt2"; return; fi

  pass 5 "T0 層の rule は許可リストどおり ${n} 本 <= ${T0_MAX} (${names# }) / core.md に承認の 1 行 (カードの 7 語入り・2 行以内) / _meta.md 条 5 は承認された全文 (例外は worktree: block の 1 つ) / tasks.md から T2 テンプレートへのポインタ / 足すプラグインの project-setup.md に 4 手順・自動化 4 本・ビュー 8 枚・画面でしか付けられない 3 つ / T2 は 2 つの形を区別して書く"
}

# ---------- case 6: 数の予算 (hook<=5 / skill<=3 / smoke case<=10。command は v2.7.0 で上限を外し、数だけ出す) ----------
# hook は hooks/*.sh だけを数える (hooks.json は宣言であって hook スクリプトではない)。
# skill は skills/<名前>/SKILL.md を数える。本体は呼ばれた時だけ読まれるが name と
# description は常に載るため、数を予算で抑える (rules/_meta.md 「数の予算」)。
case_6() {
  local hooks cmds skills cases
  hooks="$(find "$ROOT/hooks" -maxdepth 1 -name '*.sh' 2>/dev/null | wc -l | tr -d ' ')"
  cmds="$(find "$ROOT/commands" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
  skills="$(find "$ROOT/skills" -maxdepth 2 -name 'SKILL.md' 2>/dev/null | wc -l | tr -d ' ')"
  cases="$(grep -c '^case_[0-9][0-9]*()' "$here/smoke.sh" 2>/dev/null | tr -d ' ')"
  local msg="hook=${hooks}/5 command=${cmds} skill=${skills}/3 smoke case=${cases}/10"
  local pcmds pskills
  pcmds="$(find "$ROOT/plugins/hirai-project-method/commands" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
  pskills="$(find "$ROOT/plugins/hirai-project-method/skills" -maxdepth 2 -name 'SKILL.md' 2>/dev/null | wc -l | tr -d ' ')"
  msg="$msg / 足すプラグイン command=${pcmds}/2 skill=${pskills}/1"
  if [ "${hooks:-0}" -gt 5 ] || [ "${skills:-0}" -gt 3 ] \
     || [ "${cases:-0}" -gt 10 ] || [ "${pcmds:-0}" -gt 2 ] || [ "${pskills:-0}" -gt 1 ]; then
    fail 6 "数の予算" "$msg"; return
  fi

  # 数えるだけでは「消えた」「壊れた」に気づけない。同梱する skill が実在し、
  # frontmatter の name がフォルダ名と一致し、description を持つことまで見る。
  # 説明文は毎セッション載る (rules/_meta.md 「数の予算」) ので、
  # 壊れた skill は予算だけ食って何もしない状態になる。
  local want sf nm ds bad6=""
  # 土台の skill は 2 件 (github-project は足すプラグイン hirai-project-method へ移した)。
  # 足すプラグインの skill は plugins/hirai-project-method/skills/ を同じ形で見る。
  [ ! -e "$ROOT/skills/github-project" ] || bad6="$bad6 github-project が土台に残っている (足すプラグインへ移したはず)"
  for want in grilling context-engineering plugins/hirai-project-method/skills/github-project; do
    sf="$ROOT/skills/$want/SKILL.md"
    case "$want" in plugins/*) sf="$ROOT/$want/SKILL.md"; want="github-project" ;; esac
    if [ ! -f "$sf" ]; then bad6="$bad6 ${want}:SKILL.md が無い"; continue; fi
    nm="$(awk 'NR==1&&$0!="---"{exit} NR>1&&/^---[[:space:]]*$/{exit} sub(/^name:[[:space:]]*/,""){print;exit}' "$sf")"
    ds="$(awk 'NR==1&&$0!="---"{exit} NR>1&&/^---[[:space:]]*$/{exit} /^description:[[:space:]]*./{print "ok";exit}' "$sf")"
    [ "$nm" = "$want" ] || bad6="$bad6 ${want}:name=${nm:-無し}"
    [ "$ds" = "ok" ] || bad6="$bad6 ${want}:description 無し"
  done
  # context-engineering は「公式を調べて書く」ことが存在意義なので、出典 URL が消えたら意味が無い。
  local ce="$ROOT/skills/context-engineering/references/official-sources.md" u
  if [ ! -f "$ce" ]; then
    bad6="$bad6 context-engineering:references/official-sources.md が無い"
  else
    for u in 'anthropic.com/engineering/effective-context-engineering-for-ai-agents' \
             'code.claude.com/docs/en/memory' 'code.claude.com/docs/en/skills' \
             'code.claude.com/docs/en/context-window'; do
      grep -qF "$u" "$ce" || bad6="$bad6 出典[${u}]が無い"
    done
  fi
  if [ -n "$bad6" ]; then fail 6 "同梱 skill が実在し出典を持つ" "不備:$bad6"; return; fi

  pass 6 "数の予算 ${msg} / 同梱 skill 3 件 (土台 2 + 足すプラグイン 1) の name はフォルダ名と一致し description を持つ / 出典 URL 4 件が残っている"
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

  # (c) 更新後の入れ替え (v1.13.0)。**既定 off が最重要** — opt-in していない利用者の
  # 導入先が、セッションを開いただけで 1 バイトでも変わってはいけない。そのうえで
  # opt-in したときは「版が変わった回だけ」「プラグイン所有の 3 本だけ」を入れ替え、
  # 利用者所有 (rules / settings.json / CLAUDE.md / 台帳) には触らないことを見る。
  local sw sp out7 bad7="" f7
  sw="$(mktemp -d)"; sp="$sw/plug"
  mkdir -p "$sp/hooks" "$sw/proj/.claude/rules" "$sw/proj/docs/tasks" "$sw/home/.claude" "$sw/td"
  cp -R "$ROOT/scripts" "$sp/" 2>/dev/null
  cp "$HOOKS/session-start.sh" "$sp/hooks/" 2>/dev/null
  printf '9.9.0\n' > "$sp/VERSION"
  # 導入先: プラグイン所有の複製が古い状態 + 利用者所有のファイル一式
  printf '#!/usr/bin/env bash\necho OLD-statusline\n' > "$sw/proj/.claude/statusline.sh"
  printf '# OLD tasks-path\n'                         > "$sw/proj/.claude/tasks-path.sh"
  printf '# 決まりごと\n'                             > "$sw/proj/.claude/rules/core.md"
  printf '{"statusLine":{"command":"x"}}\n'           > "$sw/proj/.claude/settings.json"
  printf '# CLAUDE\n'                                 > "$sw/proj/CLAUDE.md"
  printf '| 1 | 未着手 | やること |\n'                > "$sw/proj/docs/tasks/list.md"
  printf 'mode: normal\n'                             > "$sw/proj/.claude/mode.yml"
  cp -R "$sw/proj" "$sw/orig"
  # run_sync <mode.yml の中身> -> セッション冒頭を 1 回動かして出力を返す (通信はしない)
  run_sync() {
    printf '%s' "$1" > "$sw/proj/.claude/mode.yml"
    HOME="$sw/home" TMPDIR="$sw/td" HARNESS_UPDATE_CHECK=off \
      CLAUDE_PLUGIN_ROOT="$sp" CLAUDE_PROJECT_DIR="$sw/proj" \
      bash "$sp/hooks/session-start.sh" 2>&1
  }
  # 1) 既定 (auto_sync を書いていない) では何も起きない
  out7="$(run_sync 'mode: normal
')"
  printf '%s' "$out7" | grep -q '入れ替えました' && bad7="$bad7 既定で入れ替えの報告が出た"
  for f7 in .claude/statusline.sh .claude/tasks-path.sh; do
    cmp -s "$sw/orig/$f7" "$sw/proj/$f7" || bad7="$bad7 既定で ${f7} が書き換わった"
  done
  [ -e "$sw/proj/.claude/context-usage.sh" ] && bad7="$bad7 既定で context-usage.sh が新設された"
  ls "$sw/proj/.claude"/*.bak >/dev/null 2>&1 && bad7="$bad7 既定で .bak が作られた"
  [ -d "$sw/td/claude-harness-lite" ] && bad7="$bad7 既定で版の控えが作られた"
  # 2) opt-in すると入れ替わる。中身が違うものは .bak に控えてから。
  out7="$(run_sync 'mode: normal
auto_sync: on
')"
  printf '%s' "$out7" | grep -q '入れ替えました' || bad7="$bad7 opt-in で報告が出ない: $out7"
  for f7 in statusline.sh tasks-path.sh context-usage.sh; do
    cmp -s "$sp/scripts/$f7" "$sw/proj/.claude/$f7" || bad7="$bad7 opt-in で ${f7} が配布版になっていない"
  done
  grep -q 'OLD-statusline' "$sw/proj/.claude/statusline.sh.bak" 2>/dev/null \
    || bad7="$bad7 元の statusline.sh が .bak に控えられていない"
  [ -x "$sw/proj/.claude/statusline.sh" ] || bad7="$bad7 入れ替え後に実行できない"
  # 3) 利用者所有は 1 バイトも変わらない (mode.yml は検査側で書き換えているので対象外)
  for f7 in .claude/rules/core.md .claude/settings.json CLAUDE.md docs/tasks/list.md; do
    cmp -s "$sw/orig/$f7" "$sw/proj/$f7" || bad7="$bad7 利用者所有の ${f7} が書き換わった"
  done
  # 4) 版が同じ回は何もしない (手を入れた複製もその版のうちは上書きしない)
  printf '#!/usr/bin/env bash\necho USER-EDIT\n' > "$sw/proj/.claude/statusline.sh"
  out7="$(run_sync 'mode: normal
auto_sync: on
')"
  printf '%s' "$out7" | grep -q '入れ替えました' && bad7="$bad7 同じ版で 2 度目の入れ替えが走った"
  grep -q 'USER-EDIT' "$sw/proj/.claude/statusline.sh" || bad7="$bad7 同じ版なのに上書きされた"
  # 5) 版が上がった回だけ、また入れ替わる
  printf '9.9.1\n' > "$sp/VERSION"
  out7="$(run_sync 'mode: normal
auto_sync: on
')"
  printf '%s' "$out7" | grep -q '入れ替えました' || bad7="$bad7 新しい版で入れ替えが走らない: $out7"
  cmp -s "$sp/scripts/statusline.sh" "$sw/proj/.claude/statusline.sh" \
    || bad7="$bad7 新しい版で配布版に戻っていない"
  grep -q 'USER-EDIT' "$sw/proj/.claude/statusline.sh.bak" 2>/dev/null \
    || bad7="$bad7 直前の内容が .bak に残っていない"
  # 6) HC_AUTO_SYNC=off は mode.yml より優先 / 壊れた環境でも exit 0
  printf '%s' 'x' > "$sw/proj/.claude/statusline.sh"
  printf 'mode: normal\nauto_sync: on\n' > "$sw/proj/.claude/mode.yml"
  printf '9.9.2\n' > "$sp/VERSION"
  HC_AUTO_SYNC=off HOME="$sw/home" TMPDIR="$sw/td" HARNESS_UPDATE_CHECK=off \
    CLAUDE_PLUGIN_ROOT="$sp" CLAUDE_PROJECT_DIR="$sw/proj" \
    bash "$sp/hooks/session-start.sh" >/dev/null 2>&1
  grep -q '^x$' "$sw/proj/.claude/statusline.sh" || bad7="$bad7 HC_AUTO_SYNC=off が効かない"
  printf 'not a semver\n' > "$sp/VERSION"
  run_sync 'mode: normal
auto_sync: on
' >/dev/null 2>&1 || bad7="$bad7 VERSION が壊れていると exit 0 で抜けない"
  # 7) 控えを取れないときは入れ替えない (戻り道が無いまま書き換えない)。
  #    導入先を書き込み禁止にして .bak を作れなくする。root は権限を素通りするので飛ばす。
  if [ "$(id -u 2>/dev/null || printf 0)" != 0 ]; then
    mkdir -p "$sw/ro/.claude"
    printf 'RO-SENTINEL\n'                  > "$sw/ro/.claude/statusline.sh"
    printf 'mode: normal\nauto_sync: on\n'  > "$sw/ro/.claude/mode.yml"
    printf '9.9.3\n' > "$sp/VERSION"
    chmod 555 "$sw/ro/.claude"
    HOME="$sw/home" TMPDIR="$sw/td2" HARNESS_UPDATE_CHECK=off \
      CLAUDE_PLUGIN_ROOT="$sp" CLAUDE_PROJECT_DIR="$sw/ro" \
      bash "$sp/hooks/session-start.sh" >/dev/null 2>&1 \
      || bad7="$bad7 控えを作れない環境で exit 0 にならない"
    chmod 755 "$sw/ro/.claude"
    grep -q 'RO-SENTINEL' "$sw/ro/.claude/statusline.sh" \
      || bad7="$bad7 控えを作れないのに入れ替えた"
    [ -e "$sw/ro/.claude/statusline.sh.bak" ] && bad7="$bad7 控えが無いのに .bak ができた"
  fi
  unset -f run_sync
  rm -rf "$sw"
  if [ -n "$bad7" ]; then fail 7 "更新後の入れ替えは既定 off で、版が変わった回だけ 3 本を揃える" "$bad7"; return; fi

  pass 7 "VERSION=${ver} は semver 1 行 / キャッシュ有効時と off 指定は通信も出力もしない / 更新後の入れ替えは既定 off (opt-in しなければ導入先は 1 バイトも変わらず .bak も版の控えも作られない)、opt-in 時はプラグイン所有の 3 本だけを版が変わった回に揃えて .bak に控え、rules・settings.json・CLAUDE.md・台帳には触らず、同じ版では何もせず、控えを作れないときは入れ替えず、HC_AUTO_SYNC=off と壊れた VERSION でも exit 0"
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
    want="[harness] 更新あり v${local_v} → v${cached_v} (/hirai-lite:update で適用)"
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
  local flag why; flag="$(update_flag_path "$td" "$tmp")"
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
    # 既定の閾値は 50% (v1.15.0、80% → 50% に変更)。HC_CONTEXT_THRESHOLD 未指定のまま境界を見る。
    local j_49='{"model":{"display_name":"X"},"context_window":{"used_percentage":49}}'
    local j_50='{"model":{"display_name":"X"},"context_window":{"used_percentage":50}}'
    if ! why="$(expect_notice "$(run_statusline "$tmp" "$td" "$j_49")" "")"; then
      fail 8 "既定の閾値 50%: 49% ではお知らせを出さない" "$why"; failed=1; break
    fi
    if ! why="$(expect_notice "$(run_statusline "$tmp" "$td" "$j_50")" "$ctxmsg")"; then
      fail 8 "既定の閾値 50%: 50% ちょうどでお知らせを出す" "$why"; failed=1; break
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

  # 更新あり控えの鍵分けの回帰: 同じ TMPDIR (機械 1 台) を共有する 2 つの案件で、片方にだけ更新ありの控えを
  # 作っても、もう片方の画面下には出ない (鍵がプロジェクトのパスで分かれているため)。
  # v1.14.2/v1.16.0 のような版違いの併用で「無関係な案件の更新あり」が出た実害の再現形。
  if [ "$failed" -eq 0 ]; then
    local projB flagA flagB
    projB="$(mktemp -d)"
    printf '%s\n' "0.2.0" > "$tmp/VERSION"; printf '%s' "0.2.0" > "$dir/latest"; date +%s > "$dir/stamp"
    run_session_start "$tmp" "$td" "on" >/dev/null   # $tmp は最新版 = 控えは作らない
    flagA="$(update_flag_path "$td" "$tmp")"
    flagB="$(update_flag_path "$td" "$projB")"
    if [ "$flagA" = "$flagB" ]; then
      fail 8 "案件ごとにフラグの鍵が分かれる" "$tmp と $projB が同じパスになった: $flagA"
      failed=1
    else
      mkdir -p "$(dirname "$flagB")" && : > "$flagB"   # 別案件 (projB) だけに更新ありを装う
      if printf '%s\n' "$(run_statusline "$tmp" "$td" "$j_low")" | grep -q '更新あり'; then
        fail 8 "他案件の控えを自分の更新ありと読まない" "$tmp の画面下に $projB 分の通知が出た"
        failed=1
      fi
    fi
    rm -rf "$projB"
  fi

  # plugin_root と project_root を実際に別のパスにして session-start.sh を走らせる回帰。
  # run_session_start は両方を同じ $tmp に揃えるため、この 1 回だけは手で分ける —
  # 揃えたままだと「project_root で鍵を作る」と「plugin_root で鍵を作る」のどちらの実装でも
  # 同じ結果になり、退行を検出できない。
  if [ "$failed" -eq 0 ]; then
    local plugD projD tdD flagD_want flagD_wrong plugDdir
    plugD="$(mktemp -d)"; projD="$(mktemp -d)"; tdD="$(mktemp -d)"
    mkdir -p "$plugD/hooks" "$plugD/scripts"
    cp "$HOOKS/session-start.sh" "$plugD/hooks/" 2>/dev/null
    cp "$ROOT/scripts/update-check.sh" "$ROOT/scripts/tasks-path.sh" "$plugD/scripts/" 2>/dev/null
    printf '0.1.0\n' > "$plugD/VERSION"
    plugDdir="$(TMPDIR="$tdD" bash -c ". \"$ROOT/scripts/update-check.sh\"; harness_update_cache_dir \"$plugD\"")"
    mkdir -p "$plugDdir"
    printf '0.2.0' > "$plugDdir/latest"
    date +%s > "$plugDdir/stamp"
    PATH="$tmp/bin:$PATH" TMPDIR="$tdD" CLAUDE_PLUGIN_ROOT="$plugD" CLAUDE_PROJECT_DIR="$projD" \
      HARNESS_UPDATE_CHECK=on HARNESS_UPDATE_URL="http://127.0.0.1:9/VERSION" \
      bash "$plugD/hooks/session-start.sh" >/dev/null 2>&1
    flagD_want="$(update_flag_path "$tdD" "$projD")"   # 期待: project_root で鍵を作る
    flagD_wrong="$(update_flag_path "$tdD" "$plugD")"  # 退行: plugin_root で鍵を作る
    if [ ! -s "$flagD_want" ]; then
      fail 8 "更新ありの控えは project_root で鍵を作る (plugin_root != project_root)" \
        "plugin_root=${plugD} project_root=${projD} で ${flagD_want} が無い"; failed=1
    elif [ "$flagD_want" != "$flagD_wrong" ] && [ -s "$flagD_wrong" ]; then
      fail 8 "更新ありの控えは project_root だけに置かれる" \
        "plugin_root 側の鍵 (${flagD_wrong}) にも控えができた"; failed=1
    fi
    rm -rf "$plugD" "$projD" "$tdD"
  fi

  if [ -e "$tmp/curl-called" ]; then
    fail 8 "期限内は通信しない (statusline も含む)" "curl が呼ばれた"; failed=1
  fi
  rm -rf "$tmp" "$td"
  [ "$failed" -eq 0 ] || return

  # tasks: github-project と、更新あり・入れ替えの通知が同時に出る最悪の場合でも 5 行以内。
  # case 1 は形の単体、case 7/8 は更新検知単体しか見ていないので、ここで組み合わせる。
  # 偽の hirai-task (PATH の先頭) が line で 1 行を返す。
  local wtmp wtd wbin wout wlines badw=""
  wtmp="$(mktemp -d)"; wtd="$(mktemp -d)"; wbin="$wtmp/bin"
  mkdir -p "$wtmp/hooks" "$wtmp/scripts" "$wbin"
  cp "$HOOKS/session-start.sh" "$wtmp/hooks/" 2>/dev/null
  cp "$ROOT/scripts/update-check.sh" "$ROOT/scripts/tasks-path.sh" "$wtmp/scripts/" 2>/dev/null
  git -C "$wtmp" init -q 2>/dev/null
  printf '0.1.0\n' > "$wtmp/VERSION"
  printf '#!/usr/bin/env bash\n[ "$1" = line ] && [ -z "${2:-}" ] && echo "1（承認 1・裁定 0・取り込み 0）／進行中 1／待ち解け —"\nexit 0\n' > "$wbin/hirai-task"
  chmod +x "$wbin/hirai-task"
  local wudir; wudir="$(TMPDIR="$wtd" bash -c ". \"$wtmp/scripts/update-check.sh\"; harness_update_cache_dir \"$wtmp\"")"
  mkdir -p "$wudir"
  printf '0.2.0' > "$wudir/latest"
  date +%s > "$wudir/stamp"
  # 入れ替え (sync) の行も一緒に出るようにする (auto_sync: on + 導入先の複製が旧いまま) —
  # これで 3 つの常時行 + 更新あり + 入れ替え = 条件つきの行が全部出る真の最悪 (5 行) になる。
  mkdir -p "$wtmp/.claude"
  printf 'mode: normal\nauto_sync: on\ntasks: github-project\n' > "$wtmp/.claude/mode.yml"
  printf '#!/usr/bin/env bash\necho OLD\n' > "$wtmp/.claude/statusline.sh"
  printf '# OLD\n' > "$wtmp/.claude/tasks-path.sh"
  wout="$(HOME="$wtmp/home" PATH="$wbin:$PATH" TMPDIR="$wtd" CLAUDE_PLUGIN_ROOT="$wtmp" \
        CLAUDE_PROJECT_DIR="$wtmp" HARNESS_UPDATE_CHECK=on bash "$wtmp/hooks/session-start.sh" 2>&1 </dev/null | cat)"
  wlines="$(printf '%s\n' "$wout" | grep -c . || true)"
  printf '%s' "$wout" | grep -q '入れ替えました' || badw="$badw 入れ替えの行が出ていない (真の最悪を作れていない): $wout"
  [ "${wlines:-0}" -le 5 ] || badw="$badw github-project + 更新あり + 入れ替え を同時に出すと 5 行を超えた: ${wlines} 行 -- $wout"
  printf '%s' "$wout" | grep -qF 'Project: あなたの番' || badw="$badw Project の行が出ていない: $wout"
  printf '%s' "$wout" | grep -q '更新あり' || badw="$badw 更新ありの行が出ていない: $wout"
  rm -rf "$wtmp" "$wtd"
  if [ -n "$badw" ]; then fail 8 "github-project と更新あり・入れ替えの行が全部出ても 5 行以内" "$badw"; return; fi

  pass 8 "新版のみ 1 行通知 / 同版・旧版は無通知 / 0.9.0 < 0.10.0 と 1.9.0 < 1.10.0 を数値比較 / 画面下部 2 行目は設定リンクを常時出しつつ お知らせは 更新あり > context 高 > 無表示 の順に 1 つだけ (off で停止・閾値可変・通信なし) / 既定の閾値 50% (v1.15.0) を境に 49% 無出力・50% でお知らせを出す / フラグの鍵は案件 (CLAUDE_PROJECT_DIR) ごとに分かれ、plugin_root と project_root が別のパスでも project_root 側だけに置かれ、他案件の更新ありは漏れない / tasks: github-project の行と更新あり・入れ替えの行が同時に出ても 5 行以内"
}

# ---------- case 9: マニフェストが妥当な JSON で、版が VERSION と一致する ----------
# 不一致だと更新検知 (VERSION 基準) と /plugin update (plugin.json 基準) が別の版を指し、
# 「更新あり」の通知が嘘になる。
case_9() {
  local f ver pver mver PM="$ROOT/plugins/hirai-project-method"
  for f in .claude-plugin/plugin.json .claude-plugin/marketplace.json hooks/hooks.json templates/settings.json \
           plugins/hirai-project-method/.claude-plugin/plugin.json; do
    if [ ! -f "$ROOT/$f" ]; then fail 9 "マニフェストが存在する" "$f が無い"; return; fi
    if ! python3 -m json.tool "$ROOT/$f" >/dev/null 2>&1; then
      fail 9 "マニフェストが妥当な JSON" "$f が JSON として読めない"; return
    fi
  done
  ver="$(head -1 "$ROOT/VERSION" 2>/dev/null | tr -d '\r')"
  pver="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("version",""))' \
          "$ROOT/.claude-plugin/plugin.json" 2>/dev/null)"
  if [ "$pver" != "$ver" ]; then
    fail 9 "plugin.json の version が VERSION と一致" "VERSION=${ver} plugin.json=${pver}"; return
  fi

  # 既定の更新 URL の ref (github.com/thirai-classlab/hirai-method-lite/<ref>/VERSION) は、
  # 配る系列の branch と一致する。3.0.0 から配る系列は main 1 本 (v2 は凍結)。
  # ずれると、この branch の VERSION が別の branch の VERSION と比べ続け、「更新あり」が
  # 一生出ない (または退役した 2.x の版と比べる)。3 か所の一致と、それが main であることを見る。
  local uref umd urm
  uref="$(sed -n 's#.*hirai-method-lite/\([^/]*\)/VERSION.*#\1#p' "$ROOT/scripts/update-check.sh" | head -1)"
  umd="$(sed -n 's#.*hirai-method-lite/\([^/]*\)/VERSION.*#\1#p' "$ROOT/commands/update.md" | head -1)"
  urm="$(sed -n 's#.*hirai-method-lite/\([^/]*\)/VERSION.*#\1#p' "$ROOT/README.md" | head -1)"
  if [ -z "$uref" ] || [ "$umd" != "$uref" ] || [ "$urm" != "$uref" ]; then
    fail 9 "既定の更新 URL の ref が 3 か所で一致する" \
      "update-check.sh=${uref:-無} update.md=${umd:-無} README.md=${urm:-無}"; return
  fi
  if [ "$uref" != "main" ]; then
    fail 9 "既定の更新 URL の ref が配る系列 (main) を指す" "ref=${uref} (v2 は凍結。main 1 本から配る)"; return
  fi

  # カタログ (marketplace.json) は 3 行: hirai-lite (土台・source "./")・hirai-project-method
  # (足すプラグイン・source ./plugins/hirai-project-method)・hirai-lite-v2 (退役・ref v2 のまま)。
  # 版は VERSION / plugin.json と一致し、足すプラグインは自分の plugin.json・VERSION と一致する。
  # 土台の entry 名は update-check.sh の HARNESS_ENTRY_NAME と同じ。控えの置き場 (ghp-path.sh の
  # HARNESS_GHP_ID) は Claude Code が entry 名とカタログ名から作るディレクトリ名
  # (<entry 名>-<カタログ名>) と同じ。ずれると、控えの置き場が実際の data の置き場と別になる。
  local cat pmver pmpver want_id ename_const ghp_id mname
  cat="$(python3 - "$ROOT/.claude-plugin/marketplace.json" "$PM/.claude-plugin/plugin.json" "$PM/VERSION" "$ROOT/.claude-plugin/plugin.json" <<'PYEOF' 2>&1
import json, sys
d = json.load(open(sys.argv[1]))
pm = json.load(open(sys.argv[2]))
pmv = open(sys.argv[3]).read().strip()
base = json.load(open(sys.argv[4]))
errs = []
names = [e.get("name") for e in d.get("plugins", [])]
if sorted(names) != ["hirai-lite", "hirai-lite-v2", "hirai-project-method"]:
    errs.append("entry が 3 行でない: %s" % names)
by = {e.get("name"): e for e in d.get("plugins", [])}
b = by.get("hirai-lite", {})
if b.get("source") != "./": errs.append("hirai-lite の source が ./ でない: %r" % (b.get("source"),))
if b.get("version") != base.get("version"): errs.append("hirai-lite の版 %s が plugin.json %s と違う" % (b.get("version"), base.get("version")))
p = by.get("hirai-project-method", {})
if p.get("source") != "./plugins/hirai-project-method": errs.append("hirai-project-method の source が違う: %r" % (p.get("source"),))
if not (p.get("version") == pm.get("version") == pmv): errs.append("hirai-project-method の版がそろわない: catalog=%s plugin.json=%s VERSION=%s" % (p.get("version"), pm.get("version"), pmv))
if pm.get("name") != "hirai-project-method": errs.append("足すプラグインの plugin.json の name が違う")
deps = pm.get("dependencies") or []
ok = [x for x in deps if isinstance(x, dict) and x.get("name") == "hirai-lite" and str(x.get("version", "")).startswith(">=3.")]
if not ok: errs.append("足すプラグインの dependencies に hirai-lite >=3.x が無い: %r" % (deps,))
v = by.get("hirai-lite-v2", {})
src = v.get("source") if isinstance(v.get("source"), dict) else {}
if src.get("ref") != "v2": errs.append("hirai-lite-v2 の ref が v2 でない: %r" % (src,))
if v.get("version") != "2.9.0": errs.append("hirai-lite-v2 の版が 2.9.0 でない: %s" % v.get("version"))
if "退役" not in (v.get("description") or ""): errs.append("hirai-lite-v2 の description に 退役 が無い")
print("ERR " + " / ".join(errs) if errs else "OK\t%s\t%s" % (d.get("name", ""), pmv))
PYEOF
)"
  case "$cat" in
    OK*) ;;
    *) fail 9 "カタログ 3 行 (hirai-lite 3.x・hirai-project-method 1.x・退役の hirai-lite-v2) と plugin.json の版・依存が一致する" "$cat"; return ;;
  esac
  mname="$(printf '%s' "$cat" | cut -f2)"; pmver="$(printf '%s' "$cat" | cut -f3)"
  ename_const="$(sed -n 's/^HARNESS_ENTRY_NAME="\(.*\)"$/\1/p' "$ROOT/scripts/update-check.sh" | head -1)"
  if [ "$ename_const" != "hirai-lite" ]; then
    fail 9 "entry 名が update-check.sh の HARNESS_ENTRY_NAME と一致 (hirai-lite)" "update-check.sh=${ename_const:-無}"; return
  fi
  want_id="hirai-project-method-${mname}"
  ghp_id="$(sed -n 's/^HARNESS_GHP_ID="\(.*\)"$/\1/p' "$PM/scripts/ghp-path.sh" | head -1)"
  if [ "$ghp_id" != "$want_id" ]; then
    fail 9 "ghp-path.sh の HARNESS_GHP_ID が <entry 名>-<カタログ名> と一致" "want=${want_id} ghp-path.sh=${ghp_id:-無}"; return
  fi
  # 退役した 2.x の entry 名 (hirai-lite-v2) の決め打ちが、土台と足すプラグインの動く部品に残っていない。
  # 残してよいのは、2.x から移る手順の説明 (update.md・init.md の「退役」の行・tasks-path.sh の
  # 2.x の控えを読む 1 か所・ghp-path.sh のコメント) だけ。ほかに出たら、本体探しが退役した版へ落ちる。
  local v2hits
  v2hits="$(grep -rn 'hirai-lite-v2\|HARNESS_V2_ENTRY_NAME' "$ROOT/hooks" "$ROOT/scripts" "$ROOT/bin" "$ROOT/templates" \
            "$PM/bin" "$PM/scripts" "$PM/commands" "$PM/skills" "$ROOT/commands" "$ROOT/rules" 2>/dev/null \
            | grep -v 'scripts/tasks-path\.sh:\|scripts/update-check\.sh:\|plugins/hirai-project-method/scripts/ghp-path\.sh:' \
            | grep -v 'commands/update\.md:\|commands/init\.md:' | head -3)"
  if [ -n "$v2hits" ]; then
    fail 9 "hirai-lite-v2 の決め打ちが動く部品に残っていない" "$v2hits"; return
  fi
  # 2.x の控え (hirai-lite-v2-hirai-lite) を読む場所は tasks-path.sh の移行 (harness_tasks_migrate) の 1 つだけ。
  if grep -n 'hirai-lite-v2-hirai-lite' "$ROOT/scripts/update-check.sh" "$PM/scripts/ghp-path.sh" "$PM/bin/hirai-task" 2>/dev/null \
     | grep -v ':[0-9]*:[[:space:]]*#' | grep -q .; then
    fail 9 "2.x の控え (hirai-lite-v2-hirai-lite) を読むのは tasks-path.sh の移行だけ" "$(grep -n 'hirai-lite-v2-hirai-lite' "$ROOT/scripts/update-check.sh" "$PM/scripts/ghp-path.sh" "$PM/bin/hirai-task" | head -2)"; return
  fi
  # 手順書と README の install / update / uninstall は、土台 (hirai-lite@hirai-lite) と足すプラグイン
  # (hirai-project-method@hirai-lite) を指す。hirai-lite-v2@ は 2.x から移る説明の中だけに在る。
  local ent_hits
  ent_hits="$(grep -nE 'plugin (install|update) hirai-lite-v2@' "$ROOT/README.md" "$ROOT"/commands/*.md 2>/dev/null \
              | grep -v '2\.x' | grep -v '退役' | grep -v '移' | head -3)"
  if [ -n "$ent_hits" ]; then
    fail 9 "README と commands/ の install・update が hirai-lite@hirai-lite を指す (退役した hirai-lite-v2@ へ案内しない)" "$ent_hits"; return
  fi
  # CLAUDE_PLUGIN_DATA / CLAUDE_PLUGIN_ROOT が別の値でも、空でも、書く側と読む側は同じ控えを指す。
  local c9tmp c9a c9b c9c
  c9tmp="$(mktemp -d)"; git init -q "$c9tmp/r" 2>/dev/null
  git -C "$c9tmp/r" remote add origin "https://github.com/example-org/example-repo.git" 2>/dev/null
  c9a="$(env -i HOME="$c9tmp/h" PATH="$PATH" bash -c ". \"$PM/scripts/ghp-path.sh\"; harness_ghp_cache_file \"$c9tmp/r\"")"
  c9b="$(env -i HOME="$c9tmp/h" PATH="$PATH" CLAUDE_PLUGIN_DATA="$c9tmp/decoy-data" CLAUDE_PLUGIN_ROOT="$c9tmp/decoy-root" \
        bash -c ". \"$PM/scripts/ghp-path.sh\"; harness_ghp_cache_file \"$c9tmp/r\"")"
  c9c="$c9tmp/h/.claude/plugins/data/${want_id}/tasks-example-org-example-repo.json"
  rm -rf "$c9tmp"
  if [ "$c9a" != "$c9b" ] || [ "$c9a" != "$c9c" ]; then
    fail 9 "env の有無に関わらず控えのパスが <HOME>/.claude/plugins/data/<entry 名>-<カタログ名>/ を指す" \
      "unset=${c9a} decoy=${c9b} want=${c9c}"; return
  fi

  pass 9 "マニフェスト 5 件が妥当な JSON / version=${pver} が VERSION と一致 / 既定の更新 URL の ref (${uref}) が 3 か所で一致し main (配る系列は 1 本) / カタログは 3 行 (hirai-lite ${ver}・source ./ / hirai-project-method ${pmver}・source ./plugins/hirai-project-method・依存 hirai-lite >=3 / hirai-lite-v2 2.9.0・ref v2・退役) で版が plugin.json・VERSION と一致し、土台の entry 名が HARNESS_ENTRY_NAME と、控えの置き場が <entry 名>-<カタログ名> と一致 / hirai-lite-v2 の決め打ちが動く部品に無く、install の案内は hirai-lite@hirai-lite / env の有無で控えのパスが変わらない"
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

  # (d) /state save の「次回に効くもの」工程。手順書そのものを検査する。
  # 承認の要否を取り違えると 2 方向に壊れる — (1) ルールが承認なしに増え、毎セッションの
  # 予算が黙って尽きる (2) 逆に T2 への追記まで止まり、何も残らない。並びと語で両方を止める。
  # 位置は見出し番号ではなくバイト位置で見るので、番号を振り直しても壊れない。
  local sm="$ROOT/commands/state.md" n_sm marker off prev=-1 key
  if [ ! -f "$sm" ]; then fail 10 "commands/state.md が存在する" "無い"; return; fi
  n_sm="$(grep -c '' "$sm" | tr -d ' ')"
  if [ "${n_sm:-0}" -gt 150 ]; then
    fail 10 "commands/state.md <= 150 行" "${n_sm} 行 -- 詳細は skill 側へ出す"; return
  fi
  # 並び: 節の見出し → 0 件なら書かない → 承認を取る → /add-rule へ渡す
  for marker in '次回に効くものを置く' '0 件なら' 'AskUserQuestion' 'hirai-lite:add-rule'; do
    off="$(grep -obF -m1 "$marker" "$sm" 2>/dev/null | head -n 1 | cut -d: -f1)"  # -m1 は 1 行の中の一致をすべて出す
    if [ -z "$off" ]; then bad="$bad state.md:[${marker}]が無い"; continue; fi
    if [ "$off" -le "$prev" ]; then bad="$bad state.md:[${marker}]の順序が逆"; fi
    prev="$off"
  done
  # 自動で書く側 (承認不要・追記のみ) と、承認が要る側の切り分けが本文に残っている
  for key in 'harness_incidents_file' '追記のみ' '承認不要' 'Documents index' \
             'hirai-lite:context-engineering'; do
    grep -qF "$key" "$sm" || bad="$bad state.md:[${key}]が無い"
  done
  if [ -n "$bad" ]; then fail 10 "/state save が次回へ効かせる工程を持つ" "$bad"; return; fi

  # (e) 承認テンプレート (T2) の本体と、承認を求める全コマンドからのポインタ。
  # 「〜してよいですか」だけでは承認する側が判断できない (rules/core.md 「承認はカードで
  # 求める」)。本体は T2 の 1 か所に置き、各コマンドはポインタだけを持つ
  # (丸写しすると片方が陳腐化する)。適用先はルール追加に限らず、タスク着手・完了・設計 draft・
  # 設定変更・元に戻せない操作まで含む。
  local at="$ROOT/$APPROVAL_TEMPLATE" it
  if [ ! -f "$at" ]; then fail 10 "承認テンプレート (T2) が存在する" "$APPROVAL_TEMPLATE が無い"; return; fi
  for it in $APPROVAL_ITEMS; do
    grep -qF "$it" "$at" || bad="$bad 承認テンプレート:[${it}]が無い"
  done
  grep -qF 'AskUserQuestion' "$at" || bad="$bad 承認テンプレート:[AskUserQuestion]が無い"
  # 記入例は 2 つ以上 (ルール追加だけの型にしない = 汎用であることの担保)
  local n_ex; n_ex="$(grep -c '^## 記入例' "$at" | tr -d ' ')"
  [ "${n_ex:-0}" -ge 2 ] || bad="$bad 承認テンプレート:記入例が ${n_ex:-0} 件 (2 件以上要る)"
  grep -q '悪い例' "$at" || bad="$bad 承認テンプレート:悪い例と良い例が無い"
  # v2.8.0: カードは 3 種 (承認・判断・人の作業) と issue の本文の目印を持ち、記入例のカード自身が
  # 長さの決まり (値は 1 行 60 字・1 行目は 80 字・全体 400 字) を守る。型の見本が決まりを破ると、
  # AI はそちらを真似る。進め方の用語集も同梱し、/init が導入先へ配る。
  for it in '判断カード' '人の作業カード' '<!-- card:approval -->' '<!-- card:decision -->' '<!-- card:work -->' '<!-- /card -->'; do
    grep -qF -- "$it" "$at" || bad="$bad 承認テンプレート:[${it}]が無い"
  done
  local cardbad
  cardbad="$(python3 - "$at" <<'PYCARD'
import re, sys
s = open(sys.argv[1], encoding="utf-8").read()
out = []
for m in re.finditer(r"## (記入例 [0-9]+)[^\n]*\n\n```\n(.*?)```", s, re.S):
    rows = m.group(2).strip("\n").split("\n")
    if sum(len(r) for r in rows) > 400:
        out.append(m.group(1) + ":400字超")
    for i, r in enumerate(rows):
        val = r.partition(": ")[2]
        if len(val) > (80 if i == 0 else 60):
            out.append(m.group(1) + ":" + r.partition(":")[0] + "が長い")
    if any(r.startswith("承認すると") for r in rows) and not any(("戻せる" in r or "戻せない" in r) for r in rows if r.startswith("承認すると")):
        out.append(m.group(1) + ":承認すると に戻せるか が無い")
print(" ".join(out))
PYCARD
)"
  [ -z "$cardbad" ] || bad="$bad 承認テンプレート:記入例のカードが決まりを破る(${cardbad})"
  # コマンドの中のカードの例も同じ決まりで見る (AI はコマンドの例も真似る)。
  # 「決めること:」で始まる行から 7 行 (字下げは外す) を 1 枚とみなす。
  local cmdbad
  cmdbad="$(python3 - "$ROOT/commands" <<'PYCMD'
import pathlib, sys
out = []
for f in sorted(pathlib.Path(sys.argv[1]).glob("*.md")):
    rows = f.read_text(encoding="utf-8").split("\n")
    for i, r in enumerate(rows):
        if not r.strip().startswith("決めること: "):
            continue
        card = [x.strip() for x in rows[i:i + 7]]
        if sum(len(x) for x in card) > 400:
            out.append(f.name + ":400字超")
        for j, x in enumerate(card):
            if len(x.partition(": ")[2]) > (80 if j == 0 else 60):
                out.append(f.name + ":" + x.partition(":")[0] + "が長い")
        if not any(("戻せる" in x or "戻せない" in x) for x in card if x.startswith("承認すると")):
            out.append(f.name + ":承認すると に戻せるか が無い")
print(" ".join(out))
PYCMD
)"
  [ -z "$cmdbad" ] || bad="$bad コマンドの中のカードの例が決まりを破る(${cmdbad})"
  # 進め方の用語集 (wave・feature・8 状態) は GitHub Project の形の用語なので足すプラグインに在り、土台の /init は配らない。
  [ -f "$ROOT/plugins/hirai-project-method/docs/rules-reference/glossary.md" ] || bad="$bad 進め方の用語集 (plugins/hirai-project-method/docs/rules-reference/glossary.md) が無い"
  [ ! -e "$ROOT/docs/rules-reference/glossary.md" ] || bad="$bad 用語集が土台に残っている (足すプラグインへ移したはず)"
  # ファイルのどこかに path が在るだけでは足りない。承認の場面と結びついていない行
  # (置き場の説明・配置手順など) でも grep は通ってしまい、v1.14.2 で init.md を検査対象に
  # 入れた際に「承認のポインタを消しても、配置手順に同じパスが残っていて PASS する」ことが
  # 実測で分かった。**ポインタは AskUserQuestion と同じ 1 行に在る**ことまで見る。
  local site sp n_site=0 aline
  for site in $APPROVAL_SITES; do
    sp="$ROOT/commands/$site"
    if [ ! -f "$sp" ]; then bad="$bad commands/${site} が無い"; continue; fi
    n_site=$(( n_site + 1 ))
    aline="$(grep -F "$APPROVAL_TEMPLATE" "$sp" 2>/dev/null | grep -cF 'AskUserQuestion' | tr -d ' ')"
    if [ "${aline:-0}" -eq 0 ]; then
      bad="$bad ${site}:型へのポインタが AskUserQuestion と同じ行に無い"; continue
    fi
    # カードの語は同じ行のこともあれば直後の箇条書きのこともある (add-rule.md)。行は問わず、
    # ファイル内に 7 語すべてが在ることを見る。
    for it in $APPROVAL_ITEMS; do
      grep -qF "$it" "$sp" || bad="$bad ${site}:[${it}]が無い"
    done
  done
  if [ -n "$bad" ]; then fail 10 "承認を求める箇所は承認カードを出す" "$bad"; return; fi

  # 承認の型は**導入先にも要る**。ポインタは「導入先の docs/rules-reference/ (無ければプラグイン
  # 同梱の同名ファイル)」の 2 段書きで必ず解決するが、v1.14.1 まで導入先に実体が無く、1 段目を
  # 開いた利用者は空振りしていた。/init の手順 7 と /update の手順 4 を**逐語に取り出して**実行し、
  # (a) 無ければ配布版と 1 バイト違わず置く (b) 在れば触らない (c) 全プロジェクト共通 (user) と
  # docs/ の無い環境には作らない、を実挙動で確かめる。手順書そのものを走らせるので、
  # 文書と実挙動が離れた時点でここが落ちる。
  local at_blk ab ub aw abad=""
  at_blk='/^```bash$/ { b = ""; c = 1; next }
          c && /^```$/ { if (b ~ /rules-reference\/approval-template\.md/) { printf "%s", b; exit } c = 0; next }
          c { b = b $0 "\n" }'
  ab="$(awk "$at_blk" "$ROOT/commands/init.md")"
  ub="$(awk "$at_blk" "$ROOT/commands/update.md")"
  [ -n "$ab" ] || abad="$abad /init に承認の型を置く手順が無い"
  [ -n "$ub" ] || abad="$abad /update に承認の型を足す手順が無い"
  if [ -z "$abad" ]; then
    aw="$(mktemp -d)"; mkdir -p "$aw/proj" "$aw/home" "$aw/u" "$aw/up/docs/rules-reference" "$aw/nod"
    # (a) /init 手順 7: 何も無いところに、配布版と同じ中身で置く
    ( cd "$aw/proj" && env CLAUDE_PLUGIN_ROOT="$ROOT" HOME="$aw/home" bash -c "$ab" ) >/dev/null 2>&1 \
      || abad="$abad /init 手順 7 が exit 0 で終わらない"
    cmp -s "$at" "$aw/proj/docs/rules-reference/approval-template.md" \
      || abad="$abad /init が承認の型を置かない (または中身が配布版と違う)"
    # (b) 2 回目は上書きしない (利用者が書き足した中身が消えない)
    printf 'USER-EDIT\n' >> "$aw/proj/docs/rules-reference/approval-template.md"
    ( cd "$aw/proj" && env CLAUDE_PLUGIN_ROOT="$ROOT" HOME="$aw/home" bash -c "$ab" ) >/dev/null 2>&1
    grep -q 'USER-EDIT' "$aw/proj/docs/rules-reference/approval-template.md" \
      || abad="$abad /init の 2 回目が承認の型を上書きした"
    # (b-2) PR の本文の雛形: 無ければ .github/ に配布版と 1 バイト違わず置き、在れば触らない (1 回目の実行で置かれている)
    cmp -s "$ROOT/templates/pull_request_template.md" "$aw/proj/.github/pull_request_template.md" \
      || abad="$abad /init が PR の雛形を置かない (または中身が配布版と違う)"
    printf 'USER-PR\n' >> "$aw/proj/.github/pull_request_template.md"
    ( cd "$aw/proj" && env CLAUDE_PLUGIN_ROOT="$ROOT" HOME="$aw/home" bash -c "$ab" ) >/dev/null 2>&1
    grep -q 'USER-PR' "$aw/proj/.github/pull_request_template.md" \
      || abad="$abad /init の 2 回目が PR の雛形を上書きした"
    # docs/ や リポ直下に別の置き場で在れば .github/ に重ねて置かない
    mkdir -p "$aw/prd/docs" "$aw/prr"; printf 'MINE\n' > "$aw/prd/docs/pull_request_template.md"; printf 'MINE\n' > "$aw/prr/PULL_REQUEST_TEMPLATE.md"
    ( cd "$aw/prd" && env CLAUDE_PLUGIN_ROOT="$ROOT" HOME="$aw/home" bash -c "$ab" ) >/dev/null 2>&1
    ( cd "$aw/prr" && env CLAUDE_PLUGIN_ROOT="$ROOT" HOME="$aw/home" bash -c "$ab" ) >/dev/null 2>&1
    { [ ! -e "$aw/prd/.github/pull_request_template.md" ] && [ "$(cat "$aw/prd/docs/pull_request_template.md")" = MINE ]; } \
      || abad="$abad /init が docs/ の PR の雛形があるのに .github/ へ置いた (または触った)"
    { [ ! -e "$aw/prr/.github/pull_request_template.md" ] && [ "$(cat "$aw/prr/PULL_REQUEST_TEMPLATE.md")" = MINE ]; } \
      || abad="$abad /init がリポ直下の PR の雛形があるのに .github/ へ置いた (または触った)"
    # (c) 全プロジェクト共通 (user) では docs/ ごと作らない (PR の雛形も置かない)
    ( cd "$aw/u" && env CLAUDE_PLUGIN_ROOT="$ROOT" HOME="$aw/home" bash -c "${ab/SCOPE=;/SCOPE=user;}" ) >/dev/null 2>&1
    [ -e "$aw/u/docs" ] && abad="$abad /init user が docs/ を作っている"
    [ -e "$aw/u/.github" ] && abad="$abad /init user が .github/ を作っている"
    # (d) /update 手順 4: docs/rules-reference が在って型が無ければ足す / 在れば触らない
    ( cd "$aw/up" && env CLAUDE_PLUGIN_ROOT="$ROOT" HOME="$aw/home" bash -c "$ub" ) >/dev/null 2>&1
    cmp -s "$at" "$aw/up/docs/rules-reference/approval-template.md" \
      || abad="$abad /update が承認の型を足さない"
    printf 'USER-EDIT\n' >> "$aw/up/docs/rules-reference/approval-template.md"
    ( cd "$aw/up" && env CLAUDE_PLUGIN_ROOT="$ROOT" HOME="$aw/home" bash -c "$ub" ) >/dev/null 2>&1
    grep -q 'USER-EDIT' "$aw/up/docs/rules-reference/approval-template.md" \
      || abad="$abad /update が既存の承認の型を上書きした"
    # (e) docs/rules-reference が無い環境 (全プロジェクト共通で入れた場合) には新設しない
    ( cd "$aw/nod" && env CLAUDE_PLUGIN_ROOT="$ROOT" HOME="$aw/home" bash -c "$ub" ) >/dev/null 2>&1
    [ -e "$aw/nod/docs" ] && abad="$abad /update が docs/ を新設している"
    rm -rf "$aw"
  fi
  if [ -n "$abad" ]; then fail 10 "承認の型は導入先にも置かれる" "$abad"; return; fi

  # (f) プラグイン本体の場所の解決 (素材行)。$CLAUDE_PLUGIN_ROOT は**空で渡ることがある**ため、
  # これを直にパスの前へ置いた行は実環境で失敗する。v1.4.0 に /init で直したのに /update には
  # 取り残され、v1.14.0 の /update が手順 0 の冒頭で落ちた。**同じクラスの欠陥を横に残さない**ため、
  # commands/ 全体を機械で見る — (1) 無防備な使用が 0 件 (2) 素材行は 1 種類だけ (2 か所で
  # 書き方が割れると片方だけ直る) (3) 未設定でも実際に最新の版を解決できる (4) 共通ライブラリの
  # harness_plugin_root と同じ答えを返す (解決の作法が離れたらここが落ちる)。
  local pr_bad="" boot n_boot n_uniq unguarded pw out_boot out_fn n_up
  # 除外は素材行 (cache の fallback `cache/hirai-lite/hirai-lite/` を持つ行) だけに絞る。
  # 末尾の / までを含めるので、退役した旧系列 (`cache/hirai-lite/hirai-lite-v2/`) へ落ちる行が
  # 紛れ込んでも「無防備な使用」として引っかかる。
  unguarded="$(grep -n 'CLAUDE_PLUGIN_ROOT' "$ROOT"/commands/*.md \
               | grep -v 'plugins/cache/hirai-lite/hirai-lite/' | head -3)"
  [ -z "$unguarded" ] || pr_bad="$pr_bad 無防備な使用:[${unguarded}]"
  n_boot="$(grep -h '^P="${CLAUDE_PLUGIN_ROOT' "$ROOT"/commands/*.md | grep -c . | tr -d ' ')"
  n_uniq="$(grep -h '^P="${CLAUDE_PLUGIN_ROOT' "$ROOT"/commands/*.md | sort -u | grep -c . | tr -d ' ')"
  [ "${n_boot:-0}" -ge 2 ] || pr_bad="$pr_bad 素材行が ${n_boot:-0} 本 (init と update の両方に要る)"
  [ "${n_uniq:-0}" -eq 1 ] || pr_bad="$pr_bad 素材行の書き方が ${n_uniq:-0} 通りに割れている"
  for f in init.md update.md; do
    grep -q '^P="${CLAUDE_PLUGIN_ROOT' "$ROOT/commands/$f" || pr_bad="$pr_bad ${f}:素材行が無い"
  done
  boot="$(grep -h -m1 '^P="${CLAUDE_PLUGIN_ROOT' "$ROOT/commands/update.md")"
  if [ -z "$boot" ]; then
    fail 10 "/update の素材行" "commands/update.md から取り出せない"; return
  fi
  # 未設定 + 偽 HOME で逐語実行する。installed_plugins.json に hirai-lite の entry を 2 版
  # (3.0.0 / 3.10.0。辞書順だと "3.10.0" < "3.0.0" になるので、単純な文字列比較では古い版を
  # 選んでしまう) 置き、**退役した旧系列 hirai-lite-v2 の entry を、より大きい版 (9.9.0・DECOY) で**
  # 置く。cache にも hirai-lite と hirai-lite-v2 の両方を置く。hirai-lite の最大版 (3.10.0) が勝ち、
  # hirai-lite-v2 には落ちない (3.0.0 の決め打ち撤去の退行を拾う)。
  pw="$(mktemp -d)"; mkdir -p "$pw/proj" "$pw/td"
  local v3a="$pw/home/.claude/plugins/inst3/3.0.0" v3b="$pw/home/.claude/plugins/inst3/3.10.0" v2d="$pw/home/.claude/plugins/inst2/9.9.0"
  mkdir -p "$v3a" "$v3b" "$v2d"
  printf 'OLD\n' > "$v3a/VERSION"
  printf 'NEW\n' > "$v3b/VERSION"
  printf 'DECOY\n' > "$v2d/VERSION"
  mkdir -p "$pw/home/.claude/plugins"
  cat > "$pw/home/.claude/plugins/installed_plugins.json" <<JSONEOF
{"version":2,"plugins":{
  "hirai-lite@hirai-lite":[
    {"scope":"project","projectPath":"/a","installPath":"$v3a","version":"3.0.0"},
    {"scope":"project","projectPath":"/b","installPath":"$v3b","version":"3.10.0"}
  ],
  "hirai-lite-v2@hirai-lite":[
    {"scope":"project","projectPath":"/c","installPath":"$v2d","version":"9.9.0"}
  ]
}}
JSONEOF
  mkdir -p "$pw/home/.claude/plugins/cache/hirai-lite/hirai-lite/3.0.0" \
           "$pw/home/.claude/plugins/cache/hirai-lite/hirai-lite-v2/9.9.0"
  printf 'OLD\n' > "$pw/home/.claude/plugins/cache/hirai-lite/hirai-lite/3.0.0/VERSION"
  printf 'DECOY\n' > "$pw/home/.claude/plugins/cache/hirai-lite/hirai-lite-v2/9.9.0/VERSION"
  out_boot="$(cd "$pw/proj" && env -u CLAUDE_PLUGIN_ROOT HOME="$pw/home" TMPDIR="$pw/td" \
              bash -c "$boot"'; cat "$P/VERSION"' 2>&1)"
  [ "$out_boot" = NEW ] \
    || pr_bad="$pr_bad installed_plugins.json の hirai-lite の最大版 (辞書順では負ける 3.10.0) に解決しない (退役した hirai-lite-v2 へ落ちていないか):[${out_boot}]"
  out_boot="$(cd "$pw/proj" && env -u CLAUDE_PLUGIN_ROOT HOME="$pw/home" TMPDIR="$pw/td" \
              bash -c "$boot"'; printf %s "$P"' 2>&1)"
  out_fn="$(cd "$pw/proj" && env -u CLAUDE_PLUGIN_ROOT HOME="$pw/home" TMPDIR="$pw/td" \
            bash -c ". \"$ROOT/scripts/update-check.sh\"; harness_plugin_root" 2>&1)"
  [ "$out_boot" = "$out_fn" ] || pr_bad="$pr_bad 素材行と harness_plugin_root の答えが違う:[${out_boot}] [${out_fn}]"
  # installed_plugins.json が無い (または hirai-lite の行が無い) ときは、hirai-lite の
  # キャッシュ (cache/hirai-lite/hirai-lite/) の最大版へ fallback する (退役した
  # cache/hirai-lite/hirai-lite-v2/ には落ちない)。既存の 3.0.0 (OLD) に加えて 3.10.0 (NEW) を置く —
  # 辞書順では "3.10.0" < "3.0.0" になるため、`sort -V` を落とすと古い方 (3.0.0) を
  # 拾ってしまう (`tail -1` が入れ替わる)。この状態を以降の「手順 0」検査にも
  # 引き継ぐ (最終的に有効な版が NEW になる)。
  rm -f "$pw/home/.claude/plugins/installed_plugins.json"
  mkdir -p "$pw/home/.claude/plugins/cache/hirai-lite/hirai-lite/3.10.0"
  printf 'NEW\n' > "$pw/home/.claude/plugins/cache/hirai-lite/hirai-lite/3.10.0/VERSION"
  out_boot="$(cd "$pw/proj" && env -u CLAUDE_PLUGIN_ROOT HOME="$pw/home" TMPDIR="$pw/td" \
              bash -c "$boot"'; cat "$P/VERSION"' 2>&1)"
  [ "$out_boot" = NEW ] \
    || pr_bad="$pr_bad installed_plugins.json 無しで hirai-lite のキャッシュの最大版に fallback しない:[${out_boot}]"
  out_boot="$(cd "$pw/proj" && env -u CLAUDE_PLUGIN_ROOT HOME="$pw/home" TMPDIR="$pw/td" \
              bash -c "$boot"'; printf %s "$P"' 2>&1)"
  out_fn="$(cd "$pw/proj" && env -u CLAUDE_PLUGIN_ROOT HOME="$pw/home" TMPDIR="$pw/td" \
            bash -c ". \"$ROOT/scripts/update-check.sh\"; harness_plugin_root" 2>&1)"
  [ "$out_boot" = "$out_fn" ] \
    || pr_bad="$pr_bad 素材行と harness_plugin_root の答えが違う (installed_plugins.json 無し):[${out_boot}] [${out_fn}]"
  # 手順 0 を逐語実行する。**控えはコピーであって移動ではない** — 元の rules が残ること、控えが
  # /tmp 直下ではなく一時領域の専用フォルダに出来ること、いつ消えるかを画面に出していること、の
  # 3 点を実挙動で見る (v1.14.0 は「退避」と表示し、利用者は自分のルールが /tmp へ移されたと
  # 受け取った)。文言だけを grep すると、別の場所に同じ語が残っているだけで素通りする。
  local s0 out_s0
  s0="$(awk '/^## 手順 0:/ {f=1} f && /^```bash$/ {c=1; next} c && /^```$/ {exit} c' \
        "$ROOT/commands/update.md")"
  if [ -z "$s0" ]; then rm -rf "$pw"; fail 10 "/update 手順 0 を取り出せる" "取り出せない"; return; fi
  mkdir -p "$pw/proj/.claude/rules" "$pw/home/.claude/rules"
  printf 'PROJ-SENTINEL\n' > "$pw/proj/.claude/rules/core.md"
  printf 'HOME-SENTINEL\n' > "$pw/home/.claude/rules/core.md"
  out_s0="$(cd "$pw/proj" && env -u CLAUDE_PLUGIN_ROOT HOME="$pw/home" TMPDIR="$pw/td" \
            bash -c "$s0" 2>&1)"
  printf '%s' "$out_s0" | grep -q 'NEW' || pr_bad="$pr_bad 手順 0 が更新前の版を出さない:[${out_s0}]"
  printf '%s' "$out_s0" | grep -q '控え' || pr_bad="$pr_bad 手順 0 が控えをコピーと呼んでいない"
  printf '%s' "$out_s0" | grep -q '再起動' || pr_bad="$pr_bad 手順 0 が控えの消えるタイミングを出していない"
  printf '%s' "$out_s0" | grep -q '退避' && pr_bad="$pr_bad 手順 0 がコピーを 退避 と表示している"
  grep -q 'PROJ-SENTINEL' "$pw/proj/.claude/rules/core.md" 2>/dev/null \
    || pr_bad="$pr_bad 控えを取ったあと元の .claude/rules が残っていない (移動になっている)"
  grep -q 'HOME-SENTINEL' "$pw/home/.claude/rules/core.md" 2>/dev/null \
    || pr_bad="$pr_bad 控えを取ったあと元の ~/.claude/rules が残っていない (移動になっている)"
  grep -rq 'PROJ-SENTINEL' "$pw/td/claude-harness-lite"/rules-backup-*/ 2>/dev/null \
    || pr_bad="$pr_bad 控えが 一時領域/claude-harness-lite/rules-backup-*/ に出来ていない"
  grep -rq 'HOME-SENTINEL' "$pw/td/claude-harness-lite"/rules-backup-*/ 2>/dev/null \
    || pr_bad="$pr_bad ホーム側の控えが取れていない"
  rm -rf "$pw"
  # 素材を読む bash ブロックは**必ず素材行から始まる**。ブロックごとに新しいシェルで動くので、
  # 別ブロックで解決した $P は持ち越されない。素材行を落としたブロックは空の $P で走り、
  # v1.14.0 の /update と同じ失敗 (パスの先頭が消えて読めない) になる。
  local blk_bad
  blk_bad="$(awk -v boot="$boot" '
    FILENAME != prev { prev = FILENAME; inb = 0 }
    /^```bash[[:space:]]*$/ { inb = 1; hasBoot = 0; usesP = 0; start = FNR; next }
    inb && /^```[[:space:]]*$/ { if (usesP && !hasBoot) printf "%s:%d ", FILENAME, start; inb = 0; next }
    inb { if ($0 == boot) { hasBoot = 1; next }
          if ($0 ~ /\$P[^A-Za-z0-9_]/ || $0 ~ /\$P$/) usesP = 1 }
  ' "$ROOT"/commands/*.md)"
  [ -z "$blk_bad" ] || pr_bad="$pr_bad 素材行なしで \$P を使うブロック:[${blk_bad}]"

  # hirai-task (足すプラグインの bin/): 実行でき、偽の HOME・gh 無しで --selftest が exit 0、引数なしは exit 2、
  # git の外 (リポを決められない) では読む側も exit 2 で gh を呼ばない、公開リポなので
  # 導入先の内部の名前を持ち込まない (R12 の語)。
  local ht_home ht_rc ht_out PM="$ROOT/plugins/hirai-project-method"
  ht_home="$(mktemp -d)"; mkdir -p "$ht_home/nogh"
  printf '#!/bin/sh\necho "$*" >> "%s/gh.log"\nexit 1\n' "$ht_home" > "$ht_home/nogh/gh"; chmod +x "$ht_home/nogh/gh"
  [ -x "$PM/bin/hirai-task" ] || pr_bad="$pr_bad plugins/hirai-project-method/bin/hirai-task が実行できない"
  [ -x "$ROOT/bin/hirai-notify" ] || pr_bad="$pr_bad bin/hirai-notify が実行できない"
  ht_out="$(cd "$ht_home" && env HOME="$ht_home" PATH="$ht_home/nogh:$PATH" HIRAI_LITE_ROOT="$ROOT" python3 "$PM/bin/hirai-task" --selftest 2>&1)"; ht_rc=$?
  [ "$ht_rc" -eq 0 ] || pr_bad="$pr_bad hirai-task --selftest が exit ${ht_rc}: $(printf '%s' "$ht_out" | grep FAIL | head -3)"
  (cd "$ht_home" && env HOME="$ht_home" PATH="$ht_home/nogh:$PATH" python3 "$PM/bin/hirai-task" >/dev/null 2>&1); ht_rc=$?
  [ "$ht_rc" -eq 2 ] || pr_bad="$pr_bad hirai-task を引数なしで呼んだ exit が 2 でない: ${ht_rc}"
  ht_out="$(cd "$ht_home" && env HOME="$ht_home" PATH="$ht_home/nogh:$PATH" python3 "$PM/bin/hirai-task" ready 2>&1)"; ht_rc=$?
  { [ "$ht_rc" -eq 2 ] && printf '%s' "$ht_out" | grep -q 'リポを決められない'; } \
    || pr_bad="$pr_bad git の外の hirai-task ready が exit 2 と理由を出さない: exit ${ht_rc} [${ht_out}]"
  [ ! -e "$ht_home/gh.log" ] || pr_bad="$pr_bad hirai-task の selftest・リポ未解決で gh が呼ばれた: $(cat "$ht_home/gh.log")"
  find "$ROOT/scripts" "$ROOT/bin" "$PM/scripts" "$PM/bin" -name __pycache__ 2>/dev/null | grep -q . \
    && pr_bad="$pr_bad hirai-task --selftest がプラグインの置き場所に __pycache__ を作った"
  # design-merge は一時ディレクトリの写しにだけ当たり、gh を 1 回も呼ばない (偽の gh を PATH の先頭に置いて呼ばれたら gh.log に残す)。
  # 使い方の誤り (coverage に引数・impact に引数なし) は gh を呼ぶ前に exit 2。
  mkdir -p "$ht_home/dmtree/docs/draft" "$ht_home/dmtree/docs/4-domains/chat" "$ht_home/fakegh"
  printf '#!/bin/sh\necho "$@" >> "%s/gh.log"\nexit 1\n' "$ht_home" > "$ht_home/fakegh/gh"; chmod +x "$ht_home/fakegh/gh"
  printf '# c\n\nid_prefix: CHAT\ndomain: chat\nstatus: 現在形\nrev: 1\n\n## 7. 要件と受入\n\n### 要件 CHAT-R1: 一つ\n- CHAT-R1.1 Given a When b Then c\n\n## 8. 上の層との差分\n' > "$ht_home/dmtree/docs/4-domains/chat/README.md"
  printf '# d\n\nid_prefix: ATT\ndomain: chat\nstatus: 承認\napproved_at: 2026-10-01（PR #9 の merge で承認）\nmerged_into:\n\n## 2. 目指す状態\n\n### 追加された要件\n\n### 要件 ATT-R1: 二つ\n- ATT-R1.1 Given a When b Then c\n\n## 3. 変える\n' > "$ht_home/dmtree/docs/draft/att.md"
  ht_out="$(cd "$ht_home" && env HOME="$ht_home" PATH="$ht_home/fakegh:$PATH" python3 "$PM/bin/hirai-task" design-merge "$ht_home/dmtree/docs/draft/att.md" 2>&1)"; ht_rc=$?
  { [ "$ht_rc" -eq 0 ] && grep -q '^status: 取り込み済み' "$ht_home/dmtree/docs/draft/att.md" \
      && grep -q '^rev: 2' "$ht_home/dmtree/docs/4-domains/chat/README.md" \
      && grep -q '### 要件 ATT-R1: 二つ' "$ht_home/dmtree/docs/4-domains/chat/README.md"; } \
    || pr_bad="$pr_bad hirai-task design-merge が写しの木に当たらない: exit ${ht_rc} [${ht_out}]"
  (cd "$ht_home" && env HOME="$ht_home" PATH="$ht_home/fakegh:$PATH" HIRAI_TASK_REPO=o/r python3 "$PM/bin/hirai-task" design-merge "$ht_home/dmtree/docs/draft/att.md" >/dev/null 2>&1); ht_rc=$?
  [ "$ht_rc" -eq 2 ] || pr_bad="$pr_bad 取り込み済みの提案への design-merge が exit 2 でない: ${ht_rc}"
  (cd "$ht_home" && env HOME="$ht_home" PATH="$ht_home/fakegh:$PATH" HIRAI_TASK_REPO=o/r python3 "$PM/bin/hirai-task" coverage extra >/dev/null 2>&1); ht_rc=$?
  [ "$ht_rc" -eq 2 ] || pr_bad="$pr_bad hirai-task coverage に引数を渡したときの exit が 2 でない: ${ht_rc}"
  (cd "$ht_home" && env HOME="$ht_home" PATH="$ht_home/fakegh:$PATH" HIRAI_TASK_REPO=o/r python3 "$PM/bin/hirai-task" impact >/dev/null 2>&1); ht_rc=$?
  [ "$ht_rc" -eq 2 ] || pr_bad="$pr_bad hirai-task impact を引数なしで呼んだ exit が 2 でない: ${ht_rc}"
  [ ! -e "$ht_home/gh.log" ] || pr_bad="$pr_bad design-merge・使い方の誤りで gh が呼ばれた: $(cat "$ht_home/gh.log")"
  rm -rf "$ht_home"
  # 導入先の内部の名前の一覧は公開リポに置かない。手元の一覧を HIRAI_INTERNAL_WORDS
  # (grep -E の式) で渡したときだけ検査する。渡さなければ一般の検査 (利用者の home 以下の絶対パス) だけを見る。
  # issue 番号の例は、push 前の目視の grep ('#[0-9]+' を commands/ で) に任せる。
  if [ -n "${HIRAI_INTERNAL_WORDS:-}" ]; then
    grep -nE "$HIRAI_INTERNAL_WORDS" "$PM/bin/hirai-task" "$PM/scripts/hirai_task_selftest.py" "$ROOT"/commands/*.md "$PM"/commands/*.md >/dev/null 2>&1 \
      && pr_bad="$pr_bad bin・selftest・commands に導入先の内部の名前が入っている"
  fi
  grep -nE '/Use''rs/' "$PM/bin/hirai-task" "$PM/scripts/hirai_task_selftest.py" >/dev/null 2>&1 \
    && pr_bad="$pr_bad bin/hirai-task か selftest に絶対パスが入っている"

  # /update の分量と、控え (コピー) の作法。「退避」はコピーを移動と誤解させるので使わない。
  n_up="$(grep -c '' "$ROOT/commands/update.md" | tr -d ' ')"
  [ "${n_up:-0}" -le 220 ] || pr_bad="$pr_bad update.md ${n_up} 行 (<=220)"
  n_in="$(grep -c '' "$ROOT/commands/init.md" | tr -d ' ')"
  [ "${n_in:-0}" -le 310 ] || pr_bad="$pr_bad init.md ${n_in} 行 (<=310)"
  # 「退避」はコピーを移動と誤解させる語。禁止を述べている 1 行 (…と書かない) 以外に出たら落とす。
  if grep -n '退避' "$ROOT/commands/update.md" | grep -qv 'と書かない'; then
    pr_bad="$pr_bad update.md にコピーを移動と誤解させる語 (退避) が残っている"
  fi
  grep -q '/tmp/rules' "$ROOT/commands/update.md" \
    && pr_bad="$pr_bad 控えが /tmp 直下に置かれている (再起動で消えるうえ他の利用者と混ざる)"

  # (g) hirai-notify の 6 経路 (1 巡目の直し)。偽の orca が引数を記録する。/bin/bash (3.2)・UTF-8・サブ dir・相対 path で打つ:
  #   H1 サブ dir から打っても root の mode.yml を読む (値は引用符つき) / H2 <file> を絶対 path に直し無ければ exit 2 /
  #   DC-03 本文は <絶対 path>｜<要約> (波括弧なしの変数は bash 3.2 の全角の区切りで壊れる) / M4 値の無い --to・--dispatch-id は exit 2 /
  #   M6 引数が環境変数より先・両方の引数なら --dispatch-id / notify: off は何もしない。
  local nw nbin nlog nrepo nsub nabs nrc nline nb=""
  nw="$(mktemp -d)"; nbin="$nw/bin"; nlog="$nw/orca.log"; nrepo="$nw/repo"; nsub="$nrepo/apps/api"
  mkdir -p "$nbin" "$nsub" "$nrepo/.claude" "$nw/home"; git -C "$nrepo" init -q 2>/dev/null
  printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$*" >> "%s"\n' "$nlog" > "$nbin/orca"; chmod +x "$nbin/orca"
  printf 'notify: "orca"  # c\n' > "$nrepo/.claude/mode.yml"
  printf 'q\n' > "$nrepo/.tmp-q.md"; nabs="$(cd "$nrepo" && pwd -P)/.tmp-q.md"
  # nrun <引数...> -> サブ dir から /bin/bash で打つ。exit は nrc、記録は nlog
  nrun() {
    : > "$nlog"
    ( cd "$nsub" && env -i HOME="$nw/home" PATH="$nbin:/usr/bin:/bin" LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 ${NENV:-NOP=1} \
        /bin/bash "$ROOT/bin/hirai-notify" "$@" ) >/dev/null 2>&1
    nrc=$?
  }
  nrun question ../../.tmp-q.md 要約A --to run:R1
  nline="$(cat "$nlog")"
  { [ "$nrc" -eq 0 ] && printf '%s' "$nline" | grep -qF -- "--body ${nabs}｜要約A" && printf '%s' "$nline" | grep -qF -- '--to run:R1'; } \
    || nb="$nb [サブ dir・相対 path・引用符つき notify から question] exit=${nrc} 記録=[${nline}] (期待: --body ${nabs}｜要約A)"
  nrun done ../../.tmp-q.md 要約B --to run:R1
  nline="$(cat "$nlog")"
  { [ "$nrc" -eq 0 ] && printf '%s' "$nline" | grep -qF -- "--body ${nabs}｜要約B" && printf '%s' "$nline" | grep -qF -- '--subject 完了: 要約B'; } \
    || nb="$nb [done --to] exit=${nrc} 記録=[${nline}]"
  nrun stopped ../../.tmp-q.md 要約C --dispatch-id d1
  nline="$(cat "$nlog")"
  { [ "$nrc" -eq 0 ] && printf '%s' "$nline" | grep -qF -- "--report-path ${nabs}" && printf '%s' "$nline" | grep -qF -- '--outcome failed' \
      && printf '%s' "$nline" | grep -qF -- '--dispatch-id d1'; } || nb="$nb [stopped --dispatch-id] exit=${nrc} 記録=[${nline}]"
  nrun done ../../.tmp-q.md 要約D --to run:X --dispatch-id d2
  nline="$(cat "$nlog")"
  { [ "$nrc" -eq 0 ] && printf '%s' "$nline" | grep -qF -- '--dispatch-id d2' && ! printf '%s' "$nline" | grep -qF -- '--to run:X'; } \
    || nb="$nb [--to と --dispatch-id の両方] --dispatch-id を採らない exit=${nrc} 記録=[${nline}]"
  NENV="HIRAI_DISPATCH_ID=d-OLD" nrun question ../../.tmp-q.md 要約E --to run:NEW
  nline="$(cat "$nlog")"
  { [ "$nrc" -eq 0 ] && printf '%s' "$nline" | grep -qF -- '--to run:NEW' && ! printf '%s' "$nline" | grep -qF 'd-OLD'; } \
    || nb="$nb [環境変数の Dispatch が明示の --to に勝った] exit=${nrc} 記録=[${nline}]"
  nrun done ../../.tmp-q.md 要約F --to
  { [ "$nrc" -eq 2 ] && [ ! -s "$nlog" ]; } || nb="$nb [値の無い --to] exit=${nrc} (期待 2・送らない)"
  nrun done ../../.tmp-q.md 要約F --dispatch-id
  { [ "$nrc" -eq 2 ] && [ ! -s "$nlog" ]; } || nb="$nb [値の無い --dispatch-id] exit=${nrc} (期待 2・送らない)"
  nrun done 要約G ../../.tmp-q.md --to run:R1
  { [ "$nrc" -eq 2 ] && [ ! -s "$nlog" ]; } || nb="$nb [<file> と <要約> の取り違え] exit=${nrc} (期待 2・送らない)"
  # (g-2) hirai-notify waiting: --type escalation・件名は既定「権限の確認で止まっています」か --subject・本文は <git の root>｜<要約>。
  # --subject は waiting だけ (exit 2)・宛先が無ければ exit 1 で送らない。
  local nroot; nroot="$(cd "$nrepo" && pwd -P)"
  nrun waiting 要約W --to run:R1
  nline="$(cat "$nlog")"
  { [ "$nrc" -eq 0 ] && printf '%s' "$nline" | grep -qF -- '--type escalation' && printf '%s' "$nline" | grep -qF -- '--subject 権限の確認で止まっています' \
      && printf '%s' "$nline" | grep -qF -- "--body ${nroot}｜要約W" && printf '%s' "$nline" | grep -qF -- '--to run:R1'; } \
    || nb="$nb [waiting --to] exit=${nrc} 記録=[${nline}]"
  nrun waiting 要約W --subject 分類器が止めました --dispatch-id d9
  nline="$(cat "$nlog")"
  { [ "$nrc" -eq 0 ] && printf '%s' "$nline" | grep -qF -- '--subject 分類器が止めました' && printf '%s' "$nline" | grep -qF -- '--dispatch-id d9'; } \
    || nb="$nb [waiting --subject] exit=${nrc} 記録=[${nline}]"
  nrun waiting 要約W
  { [ "$nrc" -eq 1 ] && [ ! -s "$nlog" ]; } || nb="$nb [waiting 宛先なし] exit=${nrc} (期待 1・送らない)"
  nrun question ../../.tmp-q.md 要約Q --subject X --to run:R1
  { [ "$nrc" -eq 2 ] && [ ! -s "$nlog" ]; } || nb="$nb [waiting 以外の --subject] exit=${nrc} (期待 2・送らない)"

  # (g-3) hooks/notify-attention.sh: 偽の orca・使い捨てのリポ・/bin/bash 3.2。判断を変えない (標準出力なし・exit 0)。
  local na_out na_err na_rc
  na_out="$nw/na.out"; na_err="$nw/na.err"
  # na_run <HC_NOTIFY の値> <stdin の JSON> -> nlog を空にして hook を打つ。exit は na_rc、標準出力は na_out、標準エラーは na_err
  na_run() {
    : > "$nlog"
    printf '%s' "$2" | env -i HOME="$nw/home" PATH="$nbin:/usr/bin:/bin" LANG=en_US.UTF-8 HC_NOTIFY="$1" HIRAI_COORDINATOR="${NA_TO-run:R1}" \
      CLAUDE_PLUGIN_DATA="$nw/data" /bin/bash "$ROOT/hooks/notify-attention.sh" >"$na_out" 2>"$na_err"
    na_rc=$?
  }
  local long cmd70 j_perm j_deny
  cmd70="$(printf 'a%.0s' $(seq 1 60))TOPSECRET-TAIL"
  j_perm="{\"hook_event_name\":\"Notification\",\"notification_type\":\"permission_prompt\",\"message\":\"Claude needs your permission to use Bash\",\"cwd\":\"$nrepo\",\"session_id\":\"s1\"}"
  na_run off "$j_perm"
  { [ "$na_rc" -eq 0 ] && [ ! -s "$nlog" ] && [ ! -s "$na_out" ]; } || nb="$nb [notify-attention: notify off] exit=${na_rc} 送った=[$(cat "$nlog")]"
  na_run orca "$j_perm"
  nline="$(cat "$nlog")"
  { [ "$na_rc" -eq 0 ] && [ ! -s "$na_out" ] && [ "$(grep -c . "$nlog")" -eq 1 ] && printf '%s' "$nline" | grep -qF -- '--type escalation' \
      && printf '%s' "$nline" | grep -qF -- '権限の確認で止まっています' && printf '%s' "$nline" | grep -qF -- "${nroot}｜Claude needs your permission to use Bash"; } \
    || nb="$nb [notify-attention: permission_prompt が 1 通] exit=${na_rc} 記録=[${nline}]"
  na_run orca "$j_perm"
  { [ "$na_rc" -eq 0 ] && [ ! -s "$nlog" ] && [ ! -s "$na_out" ]; } || nb="$nb [notify-attention: 同じ会話の 1 分以内の 2 通目を送った] 記録=[$(cat "$nlog")]"
  na_run orca "{\"hook_event_name\":\"Notification\",\"notification_type\":\"idle_prompt\",\"message\":\"idle\",\"cwd\":\"$nrepo\",\"session_id\":\"s2\"}"
  { [ "$na_rc" -eq 0 ] && [ ! -s "$nlog" ]; } || nb="$nb [notify-attention: permission_prompt 以外の通知を送った] 記録=[$(cat "$nlog")]"
  j_deny="{\"hook_event_name\":\"PermissionDenied\",\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"${cmd70}\",\"env\":{\"K\":\"TOPSECRET-ENV\"}},\"reason\":\"classifier blocked\",\"cwd\":\"$nrepo\",\"session_id\":\"s3\"}"
  na_run orca "$j_deny"
  nline="$(cat "$nlog")"
  { [ "$na_rc" -eq 0 ] && [ ! -s "$na_out" ] && [ "$(grep -c . "$nlog")" -eq 1 ] && printf '%s' "$nline" | grep -qF -- '--type escalation' \
      && printf '%s' "$nline" | grep -qF -- '分類器が止めました' && printf '%s' "$nline" | grep -qF -- 'classifier blocked' \
      && printf '%s' "$nline" | grep -qF -- "$(printf 'a%.0s' $(seq 1 60))"; } \
    || nb="$nb [notify-attention: PermissionDenied が 1 通] exit=${na_rc} 記録=[${nline}]"
  printf '%s' "$nline" | grep -q 'TOPSECRET' && nb="$nb [notify-attention: tool_input の中身 (コマンドの 60 字より後ろか env) を送った] 記録=[${nline}]"
  na_run orca '{broken json'
  { [ "$na_rc" -eq 0 ] && [ ! -s "$nlog" ] && [ ! -s "$na_out" ]; } || nb="$nb [notify-attention: 壊れた入力] exit=${na_rc}"
  NA_TO= na_run orca "{\"hook_event_name\":\"PermissionDenied\",\"tool_name\":\"Edit\",\"reason\":\"r\",\"cwd\":\"$nrepo\",\"session_id\":\"s4\"}"
  { [ "$na_rc" -eq 0 ] && [ ! -s "$na_out" ] && [ "$(grep -c . "$na_err")" -eq 1 ]; } \
    || nb="$nb [notify-attention: 送れないときは stderr 1 行・出力なし・exit 0] exit=${na_rc} stderr 行=$(grep -c . "$na_err") 出力=$(wc -c < "$na_out")"
  # StopFailure (API エラーで手番が終わった): 件名「API エラーで止まりました（<error>）」・本文 <root>｜<本文の先頭 80 字> を 1 通・同じ会話の 1 分以内の 2 通目は送らない・notify off は送らない
  local j_sf
  j_sf="{\"hook_event_name\":\"StopFailure\",\"error\":\"server_error\",\"last_assistant_message\":\"Request timed out\",\"cwd\":\"$nrepo\",\"session_id\":\"sf1\"}"
  na_run off "$j_sf"
  { [ "$na_rc" -eq 0 ] && [ ! -s "$nlog" ] && [ ! -s "$na_out" ]; } || nb="$nb [notify-attention: StopFailure で notify off が送った] 記録=[$(cat "$nlog")]"
  na_run orca "$j_sf"
  nline="$(cat "$nlog")"
  { [ "$na_rc" -eq 0 ] && [ ! -s "$na_out" ] && [ "$(grep -c . "$nlog")" -eq 1 ] && printf '%s' "$nline" | grep -qF -- '--type escalation' \
      && printf '%s' "$nline" | grep -qF -- 'API エラーで止まりました（server_error）' && printf '%s' "$nline" | grep -qF -- "${nroot}｜Request timed out"; } \
    || nb="$nb [notify-attention: StopFailure が 1 通] exit=${na_rc} 記録=[${nline}]"
  na_run orca "$j_sf"
  { [ "$na_rc" -eq 0 ] && [ ! -s "$nlog" ] && [ ! -s "$na_out" ]; } || nb="$nb [notify-attention: StopFailure の 1 分以内の 2 通目を送った] 記録=[$(cat "$nlog")]"
  printf 'notify: off\n' > "$nrepo/.claude/mode.yml"
  nrun done ../../.tmp-q.md 要約H --to run:R1
  { [ "$nrc" -eq 0 ] && [ ! -s "$nlog" ]; } || nb="$nb [notify: off] exit=${nrc} 送った: $(cat "$nlog")"
  # (g-4) hirai-pr-asset: 使い捨ての bare リポへ。branch pr-assets を作る・積み増す・作業ツリーと HEAD を動かさない・
  # remote を読めない / 無いと exit 1・/bin/bash 3.2。
  local pw pa_rc pa_bad="" pa_head pa_st pa_out
  pw="$(mktemp -d)"; mkdir -p "$pw/img" "$pw/work" "$pw/bare.git"
  git init -q --bare "$pw/bare.git" 2>/dev/null
  printf 'x' > "$pw/img/a.png"; printf 'y' > "$pw/img/b.png"
  ( cd "$pw/work" && git init -q 2>/dev/null && printf 'f\n' > f.txt && git add f.txt \
    && git -c user.name=t -c user.email=t@e commit -q -m init && git remote add origin "$pw/bare.git" ) >/dev/null 2>&1
  pa_head="$(git -C "$pw/work" rev-parse HEAD 2>/dev/null)"
  pa_st="$(git -C "$pw/work" status --porcelain 2>&1)$(git -C "$pw/work" symbolic-ref HEAD 2>&1)"
  # pa_run <dir> <引数...> -> exit は pa_rc、標準出力は pa_out
  pa_run() {
    local d="$1"; shift
    pa_out="$( cd "$d" && env -i HOME="$pw" PATH="/usr/bin:/bin" GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@e GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@e \
      /bin/bash "$ROOT/bin/hirai-pr-asset" "$@" 2>"$pw/pa.err" )"
    pa_rc=$?
  }
  pa_run "$pw/work" 5 "$pw/img/a.png"
  { [ "$pa_rc" -eq 0 ] && git -C "$pw/bare.git" rev-parse -q --verify refs/heads/pr-assets >/dev/null 2>&1 \
      && git -C "$pw/bare.git" ls-tree -r --name-only pr-assets 2>/dev/null | grep -qx '5/a.png' && printf '%s' "$pa_out" | grep -qF '![a]('; } \
    || pa_bad="$pa_bad [1 回目: branch を作り 5/a.png を置き貼る行を出す] exit=${pa_rc} $(cat "$pw/pa.err")"
  pa_run "$pw/work" 5 "$pw/img/b.png"
  { [ "$pa_rc" -eq 0 ] && [ "$(git -C "$pw/bare.git" rev-list --count pr-assets 2>/dev/null)" = 2 ] \
      && git -C "$pw/bare.git" ls-tree -r --name-only pr-assets 2>/dev/null | grep -qx '5/a.png' \
      && git -C "$pw/bare.git" ls-tree -r --name-only pr-assets 2>/dev/null | grep -qx '5/b.png'; } \
    || pa_bad="$pa_bad [2 回目: 積み増す (2 commit・a と b が残る)] exit=${pa_rc} $(cat "$pw/pa.err")"
  { [ "$(git -C "$pw/work" rev-parse HEAD 2>&1)" = "$pa_head" ] && [ "$(git -C "$pw/work" status --porcelain 2>&1)$(git -C "$pw/work" symbolic-ref HEAD 2>&1)" = "$pa_st" ] \
      && [ -z "$(git -C "$pw/work" branch --list pr-assets)" ]; } \
    || pa_bad="$pa_bad [作業ツリー・HEAD・branch が動いた]"
  git -C "$pw/work" remote set-url origin "$pw/missing.git" 2>/dev/null
  pa_run "$pw/work" 5 "$pw/img/a.png"
  [ "$pa_rc" -eq 1 ] || pa_bad="$pa_bad [remote を読めない] exit=${pa_rc} (期待 1)"
  git -C "$pw/work" remote remove origin 2>/dev/null
  pa_run "$pw/work" 5 "$pw/img/a.png"
  [ "$pa_rc" -eq 1 ] || pa_bad="$pa_bad [remote が無い] exit=${pa_rc} (期待 1)"
  pa_run "$pw/work" abc "$pw/img/a.png"
  [ "$pa_rc" -eq 2 ] || pa_bad="$pa_bad [PR 番号が数字でない] exit=${pa_rc} (期待 2)"
  rm -rf "$pw"
  [ -z "$pa_bad" ] || nb="$nb hirai-pr-asset:${pa_bad}"

  # (g-5) hirai-watch: 偽の記録 5 場合 (API エラー終わり=出す・api-request 古い=出す・api-request 新しい=出さない・user 終わり古い=出す・end_turn 古い=出さない)
  # と 記録の dir 無し (「記録が無い」・止まりに数えず exit 0)・--orca (偽の orca・別リポと archived は見ない・orca 無しは exit 2)・/bin/bash でなく python3 の実行。
  local wb wb_bad="" wb_rc wb_out
  wb="$(mktemp -d)"; mkdir -p "$wb/cfg/projects" "$wb/home" "$wb/obin" "$wb/repo"
  # wb_mk <path> <touch -t の値 or 空> -> 標準入力を <path> の記録 (dir 名は / と . を - にしたもの) にする
  wb_mk() {
    local d="$wb/cfg/projects/$(printf '%s' "$1" | sed 's#[/.]#-#g')"
    mkdir -p "$d"; cat > "$d/s.jsonl"; [ -z "${2:-}" ] || touch -t "$2" "$d/s.jsonl"; return 0
  }
  wb_mk /w/a <<'WE'
{"type":"user","message":{"content":"hi"}}
{"type":"assistant","isApiErrorMessage":true,"timestamp":"2026-11-23T01:00:00Z","message":{"content":[{"type":"text","text":"Request timed out"}]}}
{"type":"system","subtype":"turn_duration"}
WE
  wb_mk /w/b 202601010000 <<'WE'
{"type":"user","message":{"content":"hi"}}
{"type":"api-request"}
WE
  wb_mk /w/c <<'WE'
{"type":"user","message":{"content":"hi"}}
{"type":"api-request"}
WE
  wb_mk /w/d 202601010000 <<'WE'
{"type":"assistant","message":{"stop_reason":"tool_use","content":[]}}
{"type":"user","message":{"content":[{"type":"tool_result"}]}}
WE
  wb_mk /w/e 202601010000 <<'WE'
{"type":"user","message":{"content":"hi"}}
{"type":"assistant","message":{"stop_reason":"end_turn","content":[{"type":"text","text":"ok"}]}}
WE
  wb_mk /w/x <<'WE'
{"type":"assistant","isApiErrorMessage":true,"message":{"content":[{"type":"text","text":"Request timed out"}]}}
WE
  # wb_run <引数...> -> exit は wb_rc、標準出力は wb_out (標準エラーは混ぜる)
  wb_run() {
    wb_out="$( cd "$wb/repo" && env -i HOME="$wb/home" PATH="${WB_PATH:-/usr/bin:/bin}" CLAUDE_CONFIG_DIR="$wb/cfg" LANG=en_US.UTF-8 \
      /usr/bin/python3 "$ROOT/bin/hirai-watch" "$@" 2>&1 )"
    wb_rc=$?
  }
  wb_run /w/a
  { [ "$wb_rc" -eq 1 ] && printf '%s' "$wb_out" | grep -qF 'API エラーで止まった' && printf '%s' "$wb_out" | grep -qF 'Request timed out'; } || wb_bad="$wb_bad [API エラーで終わり] exit=${wb_rc} 出力=[${wb_out}]"
  wb_run /w/b
  { [ "$wb_rc" -eq 1 ] && printf '%s' "$wb_out" | grep -qF '問い合わせの途中で'; } || wb_bad="$wb_bad [api-request のまま古い] exit=${wb_rc} 出力=[${wb_out}]"
  wb_run /w/c
  { [ "$wb_rc" -eq 0 ] && [ -z "$wb_out" ]; } || wb_bad="$wb_bad [api-request のまま新しい (止まりでない)] exit=${wb_rc} 出力=[${wb_out}]"
  wb_run /w/d
  { [ "$wb_rc" -eq 1 ] && printf '%s' "$wb_out" | grep -qF '問い合わせの途中で'; } || wb_bad="$wb_bad [tool_result の user で終わって古い] exit=${wb_rc} 出力=[${wb_out}]"
  wb_run /w/e
  { [ "$wb_rc" -eq 0 ] && [ -z "$wb_out" ]; } || wb_bad="$wb_bad [end_turn で終わって古い (普通の待ち)] exit=${wb_rc} 出力=[${wb_out}]"
  wb_run --minutes 100000000 /w/b
  { [ "$wb_rc" -eq 0 ] && [ -z "$wb_out" ]; } || wb_bad="$wb_bad [--minutes を大きくしても出した] exit=${wb_rc}"
  wb_run /w/none
  { [ "$wb_rc" -eq 0 ] && printf '%s' "$wb_out" | grep -qF '記録が無い'; } || wb_bad="$wb_bad [記録の dir が無い] exit=${wb_rc} 出力=[${wb_out}] (期待 記録が無い・exit 0)"
  wb_run /w/e /w/none /w/a
  { [ "$wb_rc" -eq 1 ] && [ "$(printf '%s\n' "$wb_out" | grep -c .)" -eq 2 ]; } || wb_bad="$wb_bad [複数 path で a だけが止まり] exit=${wb_rc} 出力=[${wb_out}]"
  # --orca: 偽の orca が 同じ repo の /w/a・/w/e と 別 repo の /w/x と archived の /w/b を返す。cwd の origin が o/r
  git -C "$wb/repo" init -q 2>/dev/null; git -C "$wb/repo" remote add origin git@github.com:o/r.git 2>/dev/null
  cat > "$wb/obin/orca" <<'WE'
#!/bin/sh
echo '{"result":{"worktrees":[{"path":"/w/a","projectId":"github:o/r"},{"path":"/w/e","projectId":"github:o/r"},{"path":"/w/x","projectId":"github:other/r"},{"path":"/w/b","projectId":"github:o/r","isArchived":true}]}}'
WE
  chmod +x "$wb/obin/orca"
  WB_PATH="$wb/obin:/usr/bin:/bin" wb_run --orca
  { [ "$wb_rc" -eq 1 ] && printf '%s' "$wb_out" | grep -qF '/w/a: ' && ! printf '%s' "$wb_out" | grep -qF '/w/x' && ! printf '%s' "$wb_out" | grep -qF '/w/b'; } \
    || wb_bad="$wb_bad [--orca は同じ repo の worktree だけを見て、別 repo と archived は見ない] exit=${wb_rc} 出力=[${wb_out}]"
  wb_run --orca
  { [ "$wb_rc" -eq 2 ] && [ -n "$wb_out" ]; } || wb_bad="$wb_bad [orca が無い --orca] exit=${wb_rc} (期待 2 と理由)"
  wb_run --bogus
  [ "$wb_rc" -eq 2 ] || wb_bad="$wb_bad [知らない引数] exit=${wb_rc} (期待 2)"
  rm -rf "$wb"
  [ -z "$wb_bad" ] || nb="$nb hirai-watch:${wb_bad}"

  # (g-6) PR の雛形: mermaid の例は HTML の注の中だけにある。注を除いた可視部に出ると PR の本文に描かれてしまう
  # (注の中に -- と > を続けた矢印を書くと注が途中で閉じ、例の残りが可視部に出る。例は = の太い矢印で書く。可視部に ``` と ==> も無いことを見る)
  python3 - "$ROOT/templates/pull_request_template.md" <<'PYEOF' || nb="$nb [pull_request_template: mermaid の例が注の中に無い か 注を除いた可視部に出ている]"
import re, sys
t = open(sys.argv[1], encoding="utf-8").read()
visible = re.sub(r"<!--.*?-->", "", t, flags=re.S)
if any(w in visible for w in ("mermaid", "flowchart", "```", "==>")):
    sys.exit(1)
if not re.search(r"<!--.*?```mermaid.*?-->", t, flags=re.S):
    sys.exit(1)
PYEOF

  rm -rf "$nw"
  [ -z "$nb" ] || pr_bad="$pr_bad hirai-notify・notify-attention・hirai-pr-asset:${nb}"

  # (h) 3.0.0 の直しが残っている: pr-retarget は bin/ にあり scripts/ に無い (Bash ツールでは土台の bin/ が PATH に入る) /
  # 承認ビューの節の本体は足すプラグインにあり土台の approval-template には指しだけ / 設計の起点は 3 行以内
  [ -x "$ROOT/bin/hirai-pr-retarget" ] || pr_bad="$pr_bad bin/hirai-pr-retarget が実行できない"
  [ ! -e "$ROOT/scripts/pr-retarget.sh" ] || pr_bad="$pr_bad scripts/pr-retarget.sh が残っている (bin/hirai-pr-retarget へ移したはず)"
  grep -rn 'pr-retarget\.sh' "$ROOT/rules" "$ROOT/commands" "$ROOT/docs" "$ROOT/README.md" "$ROOT/templates" 2>/dev/null | grep -q . \
    && pr_bad="$pr_bad 旧い pr-retarget.sh の名前が残っている: $(grep -rn 'pr-retarget\.sh' "$ROOT/rules" "$ROOT/commands" "$ROOT/docs" "$ROOT/README.md" "$ROOT/templates" | head -1)"
  grep -qF '| 答え | ボードですること' "$PM/docs/rules-reference/approval-view.md" 2>/dev/null || pr_bad="$pr_bad 足すプラグインの docs/rules-reference/approval-view.md に承認ビューの節の本体が無い"
  grep -qF '| 答え | ボードですること' "$ROOT/$APPROVAL_TEMPLATE" \
    && pr_bad="$pr_bad approval-template.md に承認ビューの節の本体が残っている (足すプラグインへ移したはず)"
  local n_core
  n_core="$(awk '/^- \*\*設計の起点\*\*/ {f=1; n=0} f && /^- \*\*/ && !/設計の起点/ {exit} f {n++} END {print n+0}' "$ROOT/rules/core.md")"
  { [ "${n_core:-0}" -ge 1 ] && [ "${n_core:-0}" -le 3 ]; } || pr_bad="$pr_bad core.md の 設計の起点 が ${n_core} 行 (1〜3 行)"
  grep -q 'docs/adr/' "$ROOT/templates/CLAUDE.md" || pr_bad="$pr_bad templates/CLAUDE.md の書類の表に ADR の置き場の行が無い"
  grep -q 'CLAUDE.md' "$ROOT/commands/new-draft.md" || pr_bad="$pr_bad new-draft.md の分かれ道 B が導入先の CLAUDE.md の表を指さない"
  if [ -n "$pr_bad" ]; then fail 10 "commands はプラグイン本体の場所を素材行で解決する" "$pr_bad"; return; fi

  pass 10 "MCP 定義は鍵を直書きせず / agent ${n} 件の frontmatter が妥当 / plugin.json は既定配置に任せている / state.md ${n_sm} 行 (<=150) に 仕分け→0 件なら書かない→承認→/add-rule 委譲 の工程がこの順で在る / 承認テンプレート (T2) にカード 3 種と目印 + カードの 7 語 + AskUserQuestion + 記入例 ${n_ex} 件 (どれも長さの決まりの内) + 悪い例/良い例 + 進め方の用語集 / 承認を求める ${n_site} コマンドすべてが AskUserQuestion と同じ行にポインタを持ちカードの 7 語を備える / 手順書の逐語実行で /init は承認の型を導入先へ置き 2 回目は上書きせず user では docs/ を作らず、/update は無いときだけ足し在れば触らず docs/ を新設しない / commands の CLAUDE_PLUGIN_ROOT 無防備使用 0 件・素材行 ${n_boot} 本が 1 種類で \$P を使う全ブロックに在り、未設定でも installed_plugins.json の hirai-lite の最大版 (辞書順では負ける 3.10.0 で確認。退役した hirai-lite-v2 の大きい版には落ちない) → hirai-lite キャッシュの最大版の順で解決し harness_plugin_root と一致 / update.md ${n_up} 行 (<=220) / init.md ${n_in} 行 (<=310) / 手順 0 の逐語実行で 控えはコピー (project 側も home 側も元が残る)・置き場は一時領域の rules-backup-*・消えるタイミングを表示 を実挙動で確認 / hirai-notify は サブ dir・相対 path・引用符つき notify・/bin/bash 3.2・UTF-8 で <絶対 path>｜<要約> を送り、値の無い --to・--dispatch-id と取り違えは exit 2、引数が環境変数より先、notify: off は何も送らない / pr-retarget は bin/ にあり旧名が無く、承認ビューの節は足すプラグインにあり、設計の起点は 3 行以内で、ADR の置き場の行がある / hirai-task は偽の HOME・gh 無しで --selftest が通り、引数なしと git の外では exit 2、gh を呼ばず、絶対パスを持たない (内部の名前は HIRAI_INTERNAL_WORDS を渡したときだけ見る)"
}

case_1; case_2; case_3; case_4; case_5; case_6; case_7; case_8; case_9; case_10

echo "---"
if [ "$FAILED" -ne 0 ]; then echo "RESULT: FAIL"; exit 1; fi
echo "RESULT: PASS"
exit 0
