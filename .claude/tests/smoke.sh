#!/usr/bin/env bash
# ハーネス自己検証 smoke (8 case)。1 件でも FAIL なら exit 1。
# 予算監査 (case 4-6) は不可逆操作ではないため hook にせず本 smoke で担保する (設計 §4.7)。
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$here/../.." && pwd)}"
HOOKS="$ROOT/.claude/hooks"
FAILED=0

# T0 (常時ロード = frontmatter に paths: を持たない rule) に居てよいファイルの許可リスト。
# 層を変える (T0 昇格 / T1 降格) ときはここを更新する。
T0_ALLOWLIST="_meta.md core.md"
T0_MAX=3

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

# ---------- case 1: session-start.sh は対象ファイル不在でも exit 0 ----------
case_1() {
  local tmp out rc
  tmp="$(mktemp -d)"; mkdir -p "$tmp/.claude/hooks"
  cp "$HOOKS/session-start.sh" "$tmp/.claude/hooks/" 2>/dev/null
  out="$(CLAUDE_PROJECT_DIR="$tmp" bash "$tmp/.claude/hooks/session-start.sh" 2>&1)"; rc=$?
  local lines; lines="$(printf '%s\n' "$out" | grep -c . || true)"
  rm -rf "$tmp"
  if [ "$rc" -ne 0 ]; then fail 1 "session-start exit 0 (対象ファイル不在)" "exit=$rc"; return; fi
  if [ "${lines:-0}" -lt 1 ]; then fail 1 "session-start は 1 行以上出力" "0 行 (無出力)"; return; fi
  if [ "${lines:-0}" -gt 5 ]; then fail 1 "session-start 出力 5 行以内" "${lines} 行"; return; fi
  if ! printf '%s\n' "$out" | grep -q '\[harness\]'; then
    fail 1 "session-start 出力に [harness] prefix" "prefix 不在: $out"; return
  fi
  pass 1 "session-start.sh は対象ファイル不在でも exit 0 / ${lines} 行 / [harness] prefix あり"
}

# ---------- case 2: 閾値未満では無出力 ----------
case_2() {
  local out rc
  out="$(TMPDIR="$(mktemp -d)" HC_CONTEXT_RATIO=0.50 bash "$HOOKS/context-budget.sh" \
        <<< '{"session_id":"smoke-under"}' 2>&1)"; rc=$?
  if [ "$rc" -ne 0 ]; then fail 2 "閾値未満は無出力" "exit=$rc"; return; fi
  if [ -n "$out" ]; then fail 2 "閾値未満は無出力" "出力あり: $out"; return; fi
  pass 2 "context-budget.sh は閾値未満 (0.50) で無出力"
}

# ---------- case 3: 閾値超過で 1 度だけ発火 ----------
case_3() {
  local td first second
  td="$(mktemp -d)"
  first="$(TMPDIR="$td" HC_CONTEXT_RATIO=0.85 bash "$HOOKS/context-budget.sh" <<< '{"session_id":"smoke-over"}' 2>&1)"
  second="$(TMPDIR="$td" HC_CONTEXT_RATIO=0.85 bash "$HOOKS/context-budget.sh" <<< '{"session_id":"smoke-over"}' 2>&1)"
  rm -rf "$td"
  if ! printf '%s' "$first" | grep -q 'save-state'; then fail 3 "閾値超過で 1 度だけ発火" "1 回目が無出力"; return; fi
  if [ -n "$second" ]; then fail 3 "閾値超過で 1 度だけ発火" "2 回目も出力: $second"; return; fi
  pass 3 "context-budget.sh は 0.85 で 1 度発火し 2 度目は沈黙"
}

# ---------- case 4: T0 予算 (常時ロード合計 <= 3,000 tokens) ----------
case_4() {
  local total=0 files=() f bytes tokens
  [ -f "$ROOT/CLAUDE.md" ] && files+=("$ROOT/CLAUDE.md")
  if [ -d "$ROOT/.claude/rules" ]; then
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      [ "$(head -1 "$f" 2>/dev/null)" = "---" ] || files+=("$f")
    done < <(find "$ROOT/.claude/rules" -maxdepth 1 -name '*.md' 2>/dev/null | sort)
  fi
  if [ "${#files[@]}" -eq 0 ]; then
    fail 4 "T0 予算 <= 3,000 tokens" "CLAUDE.md / .claude/rules/*.md が未作成のため測定不可"; return
  fi
  for f in "${files[@]}"; do
    bytes="$(wc -c < "$f" 2>/dev/null | tr -d ' ')"
    total=$(( total + ${bytes:-0} ))
  done
  tokens=$(( total / 3 ))
  if [ "$tokens" -gt 3000 ]; then
    fail 4 "T0 予算 <= 3,000 tokens" "${tokens} tokens (${total} bytes / ${#files[@]} file)"; return
  fi
  pass 4 "T0 常時ロード ${tokens} tokens <= 3,000 (${#files[@]} file / ${total} bytes)"
}

# ---------- case 5: 層違反検出 (T0 は許可リストのファイルだけ / 本数 <= T0_MAX) ----------
case_5() {
  local n=0 f base names="" unexpected="" missing="" want
  if [ ! -d "$ROOT/.claude/rules" ]; then
    fail 5 "T0 rule は許可リストのみ" ".claude/rules/ が未作成のため測定不可"; return
  fi
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    has_paths_key "$f" && continue
    base="$(basename "$f")"
    n=$(( n + 1 )); names="$names $base"
    case " $T0_ALLOWLIST " in *" $base "*) ;; *) unexpected="$unexpected $base" ;; esac
  done < <(find "$ROOT/.claude/rules" -maxdepth 1 -name '*.md' 2>/dev/null | sort)
  if [ "$n" -eq 0 ]; then fail 5 "T0 rule は許可リストのみ" ".claude/rules/*.md が 0 件 (未作成)"; return; fi
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

# ---------- case 6: 数の予算 (hook<=5 / command<=12 / smoke case<=10) ----------
case_6() {
  local hooks cmds cases
  hooks="$(find "$ROOT/.claude/hooks" -maxdepth 1 -name '*.sh' 2>/dev/null | wc -l | tr -d ' ')"
  cmds="$(find "$ROOT/.claude/commands" -maxdepth 1 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
  cases="$(grep -c '^case_[0-9][0-9]*()' "$here/smoke.sh" 2>/dev/null | tr -d ' ')"
  local msg="hook=${hooks}/5 command=${cmds}/12 smoke case=${cases}/10"
  if [ "${hooks:-0}" -gt 5 ] || [ "${cmds:-0}" -gt 12 ] || [ "${cases:-0}" -gt 10 ]; then
    fail 6 "数の予算" "$msg"; return
  fi
  pass 6 "数の予算 ${msg}"
}

# 更新検知 case (7/8) 用の作業 dir を組む。
#   $1 に root、$2 に TMPDIR を受け取り、hook / lib / VERSION / curl スタブを配置する。
#   curl スタブは「通信が起きたら $root/curl-called が生える」ことで通信の有無を可視化する。
setup_update_env() {
  local tmp="$1"
  mkdir -p "$tmp/.claude/hooks" "$tmp/.claude/scripts" "$tmp/bin" || return 1
  cp "$HOOKS/session-start.sh" "$tmp/.claude/hooks/" || return 1
  cp "$ROOT/.claude/scripts/update-check.sh" "$tmp/.claude/scripts/" || return 1
  cp "$ROOT/.claude/scripts/tasks-path.sh" "$tmp/.claude/scripts/" 2>/dev/null
  cat > "$tmp/bin/curl" <<EOF
#!/usr/bin/env bash
: > "$tmp/curl-called"
exit 1
EOF
  chmod +x "$tmp/bin/curl"
}

# run_session_start <root> <tmpdir> <HARNESS_UPDATE_CHECK 値> -> hook を実行し stdout+stderr を返す
run_session_start() {
  local tmp="$1" td="$2" chk="$3"
  PATH="$tmp/bin:$PATH" TMPDIR="$td" CLAUDE_PROJECT_DIR="$tmp" \
    HARNESS_UPDATE_CHECK="$chk" HARNESS_UPDATE_URL="http://127.0.0.1:9/VERSION" \
    bash "$tmp/.claude/hooks/session-start.sh" 2>&1
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
  . "$ROOT/.claude/scripts/update-check.sh" 2>/dev/null
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
  . "$ROOT/.claude/scripts/update-check.sh" 2>/dev/null
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
EOF

  if [ -e "$tmp/curl-called" ]; then
    fail 8 "期限内は通信しない" "curl が呼ばれた"; failed=1
  fi
  rm -rf "$tmp" "$td"
  [ "$failed" -eq 0 ] || return
  pass 8 "新版のみ 1 行通知 / 同版・旧版は無通知 / 0.9.0 < 0.10.0 を数値比較"
}

case_1; case_2; case_3; case_4; case_5; case_6; case_7; case_8

echo "---"
if [ "$FAILED" -ne 0 ]; then echo "RESULT: FAIL"; exit 1; fi
echo "RESULT: PASS"
exit 0
