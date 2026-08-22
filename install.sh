#!/usr/bin/env bash
# hirai-method-lite installer — copy .claude/ into a target repo.
# Usage: ./install.sh <target-repo-path> [--update]
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET=""
UPDATE=0
FAILED=0

for arg in "$@"; do
  case "$arg" in
    --update) UPDATE=1 ;;
    -h|--help) TARGET="__help__" ;;
    -*) echo "unknown option: $arg" >&2; exit 2 ;;
    *) TARGET="$arg" ;;
  esac
done

usage() {
  cat <<'EOF'
Usage: ./install.sh <target-repo-path> [--update]

  (no option)  .claude/ をコピーし、CLAUDE.md と docs/ の雛形を配置する。
               既存の CLAUDE.md / docs/ / mode.yml / settings.local.json は上書きしない。
  --update     .claude/rules .claude/hooks .claude/commands のみ更新する。
               CLAUDE.md と docs/ には触れない。
EOF
}

if [ -z "$TARGET" ] || [ "$TARGET" = "__help__" ]; then
  usage; [ -z "$TARGET" ] && exit 2 || exit 0
fi

[ -d "$TARGET" ] || { echo "ERROR: target directory not found: $TARGET" >&2; exit 1; }
TARGET="$(cd "$TARGET" && pwd)"
[ "$TARGET" != "$SRC" ] || { echo "ERROR: target is the harness repo itself" >&2; exit 1; }

# --- helpers ---------------------------------------------------------------
say()  { printf '  %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1" >&2; FAILED=1; }

sync_dir() {   # copy a directory tree, overwriting files inside it
  local from="$1" to="$2"
  [ -d "$from" ] || { say "skip (no source): ${from#$SRC/}"; return 0; }
  mkdir -p "$to" || { fail "mkdir $to"; return 1; }
  cp -R "$from/." "$to/" || { fail "cp $from"; return 1; }
  say "synced ${to#$TARGET/}"
}

place_file() {   # copy one file only when the destination is absent
  local from="$1" to="$2"
  if [ -e "$to" ]; then say "kept   ${to#$TARGET/}"; return 0; fi
  mkdir -p "$(dirname "$to")" || { fail "mkdir $(dirname "$to")"; return 1; }
  cp "$from" "$to" || { fail "cp $from"; return 1; }
  say "placed ${to#$TARGET/}"
}

write_if_absent() {   # write a heredoc file only when the destination is absent
  local to="$1"
  if [ -e "$to" ]; then cat >/dev/null; say "kept   ${to#$TARGET/}"; return 0; fi
  mkdir -p "$(dirname "$to")" || { fail "mkdir $(dirname "$to")"; cat >/dev/null; return 1; }
  cat > "$to" || { fail "write $to"; return 1; }
  say "placed ${to#$TARGET/}"
}

# --- update mode -----------------------------------------------------------
if [ "$UPDATE" -eq 1 ]; then
  echo "update: $TARGET"
  for d in rules hooks commands; do
    sync_dir "$SRC/.claude/$d" "$TARGET/.claude/$d"
  done
  chmod +x "$TARGET"/.claude/hooks/*.sh 2>/dev/null
  [ "$FAILED" -eq 0 ] && echo "done (update)" || echo "done with errors" >&2
  exit "$FAILED"
fi

# --- full install ----------------------------------------------------------
echo "install: $TARGET"
mkdir -p "$TARGET/.claude" || { echo "ERROR: cannot create .claude" >&2; exit 1; }

for entry in "$SRC/.claude"/*; do
  [ -e "$entry" ] || continue
  name="$(basename "$entry")"
  case "$name" in
    mode.yml|settings.local.json) place_file "$entry" "$TARGET/.claude/$name" ;;
    state) : ;;
    *)
      if [ -d "$entry" ]; then sync_dir "$entry" "$TARGET/.claude/$name"
      else cp "$entry" "$TARGET/.claude/$name" && say "synced .claude/$name" || fail "cp $name"
      fi ;;
  esac
done

chmod +x "$TARGET"/.claude/hooks/*.sh "$TARGET"/.claude/tests/*.sh 2>/dev/null
[ -e "$TARGET/.claude/mode.yml" ] || { echo "mode: normal" > "$TARGET/.claude/mode.yml"; say "placed .claude/mode.yml"; }
if [ -f "$SRC/.claude/templates/CLAUDE.md" ]; then
  place_file "$SRC/.claude/templates/CLAUDE.md" "$TARGET/CLAUDE.md"
else
  write_if_absent "$TARGET/CLAUDE.md" <<'EOF'
# CLAUDE.md

## このリポジトリ
- 役割: <1 行>
- 言語 / フレームワーク: <1 行>

## コマンド
- build: <command>
- test:  <command>
- lint:  <command>

## ルール
- 常時: `.claude/rules/_meta.md` `.claude/rules/core.md`
- 条件: `.claude/rules/*.md` (paths: 一致時)
- 参照: `docs/rules-reference/` (明示 Read のみ)
EOF
fi

write_if_absent "$TARGET/docs/tasks/list.md" <<'EOF'
# タスク台帳

保留タスクは [parking-lot.md](parking-lot.md)。status は 未着手 / 進行中 / 完了 の 3 種。

| # | status | タスク | 概要 | 依存先 | 詳細 |
|---|--------|-------|------|-------|------|
EOF

write_if_absent "$TARGET/docs/tasks/parking-lot.md" <<'EOF'
# Parking Lot

着手しないタスクの置き場。1 件につき 起案日 / 保留理由 / 設計書 / 再検討トリガー を書く。

| 起案日 | タスク | 保留理由 | 設計書 | 再検討トリガー |
|-------|-------|---------|-------|--------------|
EOF

write_if_absent "$TARGET/docs/draft/.gitkeep" </dev/null
write_if_absent "$TARGET/docs/rules-reference/incidents.md" <<'EOF'
# incidents

事故 1 回目の記録先。2 回目が起きたら `/add-rule` でルール化する。

| 日付 | 事象 | 対処 | 回数 |
|-----|------|------|------|
EOF

[ "$FAILED" -eq 0 ] && echo "done (install)" || echo "done with errors" >&2
exit "$FAILED"
