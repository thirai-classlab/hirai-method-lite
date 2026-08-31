#!/usr/bin/env bash
# UserPromptSubmit hook: 進め方が loop のときだけ、loop の要点を毎ターン再注入する。
#
# なぜ要るか: loop の規範は `rules/core.md` にあるが、あれはセッション冒頭に 1 度読まれるだけで、
# 会話が伸びるほど効きが薄れる。実使用で「よく止まる」と報告された。毎ターン 4 行を注ぎ直す。
#
# **止めない。** 出力するのは context だけで、BLOCK も ask もしない。`_meta.md` 条 5
# (機械強制は不可逆操作のみ) が禁じているのは無害な操作を止める guard であって、
# context を注ぐだけの reminder は対象外 (条 5 に明記してある)。
#
#   発火条件: 進め方 (mode) が loop のときだけ。normal では 1 バイトも出さず exit 0
#   進め方の解決: scripts/tasks-path.sh の harness_mode (env HC_MODE > プロジェクト > ホーム > normal)
#                 ここで独自に解決しない (セッション冒頭・画面下部と食い違わせない)
#   無効化: HC_LOOP_REMINDER=off
#
# 通信しない。内部エラーでも常に exit 0 (fail-open)。
set -uo pipefail

[ "${HC_LOOP_REMINDER:-on}" = "off" ] && exit 0

# 渡される JSON は使わないが、読まずに終わると書き込み側が EPIPE を踏むことがあるので捨てて読み切る。
# 端末から手で実行したときに待ち続けないよう、端末のときは読まない。
[ -t 0 ] || cat >/dev/null 2>&1 || true

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || here="."
plugin_root="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$plugin_root" ] || [ ! -d "$plugin_root" ]; then
  plugin_root="$(cd "$here/.." 2>/dev/null && pwd)" || plugin_root="."
fi
root="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$root" ] || [ ! -d "$root" ]; then
  root="$PWD"
fi

# shellcheck source=../scripts/tasks-path.sh
[ -f "$plugin_root/scripts/tasks-path.sh" ] \
  && . "$plugin_root/scripts/tasks-path.sh" 2>/dev/null || true
command -v harness_mode >/dev/null 2>&1 || exit 0   # 共通ライブラリ不在なら黙って通す

mode="$(harness_mode "$root" 2>/dev/null)" || mode=""
[ "$mode" = "loop" ] || exit 0

echo "[harness] 進め方: loop（自動で進む）— 確認を求めず作業を続けます。"
echo "[harness] 止まるのは 3 つだけ: 「stop」と言われた / やることが終わった / 続けられないエラー。"
echo "[harness] subagent の完了待ちは停止理由になりません。待つ間も別の作業を進めます。"
echo "[harness] ただし「新しい設計の追加」「決めた内容の変更」「元に戻せない操作」は loop でも確認します。"
exit 0
