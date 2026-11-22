#!/usr/bin/env bash
# SessionStart hook: 現在の mode と効いている設定 / 未完了タスク数 / 直近 state を 5 行以内で出力する。
# 更新の合図と「更新後の入れ替え」の報告は、該当する回だけ末尾に 1 行ずつ足す。
# 対象ファイルが 1 つも無くても正常終了する (fail-open)。
#
# パス解決は 2 段構え。
#   plugin_root : $CLAUDE_PLUGIN_ROOT > このスクリプトの 1 つ上 ($BASH_SOURCE 起点)
#   root        : $CLAUDE_PROJECT_DIR > $PWD   (導入先リポジトリ = ユーザーの資産)
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)" || here="."
plugin_root="${CLAUDE_PLUGIN_ROOT:-}"
if [ -z "$plugin_root" ] || [ ! -d "$plugin_root" ]; then
  plugin_root="$(cd "$here/.." 2>/dev/null && pwd)" || plugin_root="."
fi
root="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$root" ] || [ ! -d "$root" ]; then
  root="$PWD"
fi

# --- 共通ライブラリ: 進め方 (mode) と台帳のパス解決をここに集約している ---
if [ -f "$plugin_root/scripts/tasks-path.sh" ]; then
  # shellcheck source=../scripts/tasks-path.sh
  . "$plugin_root/scripts/tasks-path.sh" 2>/dev/null || true
fi

# --- mode: 解決順は harness_mode (env HC_MODE > プロジェクト > ホーム > normal) ---
# 画面下部 (scripts/statusline.sh) と /config も同じ関数を通す。ここで独自に解決しない。
# 表示は「正式名（短い解説）」(normal（確認あり）/ loop（自動で進む）)。未知の値はそのまま出す。
if command -v harness_mode >/dev/null 2>&1; then
  mode="$(harness_mode "$root")"
else
  mode="${HC_MODE:-normal}"
fi
[ -n "$mode" ] || mode="normal"
case "$mode" in
  normal) mode_line="normal（確認あり） — 重要な分かれ道で確認します (自動で進めるなら /hirai-lite:config)" ;;
  loop)   mode_line="loop（自動で進む） — 確認を求めず進みます (止めるときは「stop」)" ;;
  *)      mode_line="$mode" ;;
esac

# --- タスク管理の形: .claude/mode.yml の tasks: が決める (自動では見分けない) ---
# ledger (既定) は台帳の件数 (1.x と同じ。通信しない)。github-project のときだけ、足すプラグイン
# hirai-project-method の hirai-task を PATH で呼ぶ (土台は GitHub の関数を直接呼ばない)。
tasks_form="ledger"
if command -v harness_tasks_form >/dev/null 2>&1; then
  tasks_form="$(harness_tasks_form "$root" 2>/dev/null || echo ledger)"
fi
if [ "$tasks_form" = "github-project" ]; then
  # hook の PATH にプラグインの bin/ は入らない (Bash ツールだけに入る)。PATH に頼らず
  # harness_pm_task_bin (installed_plugins.json の最大版 → cache の最大版 → PATH) で絶対 path を引く。
  pm_task=""
  if command -v harness_pm_task_bin >/dev/null 2>&1; then
    pm_task="$(harness_pm_task_bin 2>/dev/null || true)"
  elif command -v hirai-task >/dev/null 2>&1; then
    pm_task="$(command -v hirai-task)"
  fi
  if [ -n "$pm_task" ]; then
    # 件数は控えを読むだけ (通信しない)。取り直しは別に切り離して起こす。
    # **取り直しを $(...) の中で呼ばない。** hirai-task line --refresh は背景の子が出力の
    # パイプを持ったまま走るので、$(...) が子の終了まで戻らず、hook の 5 秒の timeout を食う。
    # 出力を捨て、stdin も閉じて、この shell の直下で切り離す。
    ghp_line="$("$pm_task" line 2>/dev/null || true)"
    "$pm_task" line --refresh >/dev/null 2>&1 </dev/null &
    if [ -n "$ghp_line" ]; then
      task_line="Project: あなたの番 ${ghp_line}"
    else
      task_line="Project: 件数を取得中です (hirai-task today で見られます)"
    fi
  else
    task_line="tasks: github-project ですが hirai-task が見つかりません → /plugin install hirai-project-method@hirai-lite"
  fi
else
  list=""
  if command -v harness_tasks_file >/dev/null 2>&1; then
    list="$(harness_tasks_file "$root" 2>/dev/null || true)"
  fi
  if [ -n "$list" ] && [ -f "$list" ]; then
    task_line="やること: $(harness_open_tasks "$list") 件 (${list#"$root"/})"
  else
    task_line="やること一覧はまだありません (/hirai-lite:new-task で作れます)"
  fi
fi

# --- 更新検知: 取得は背景 + 24h に 1 回、表示は前回キャッシュ値 (通信を待たない) ---
# 版を比べる VERSION はプラグイン側にあるので plugin_root を渡す。
update_line=""
sync_line=""
if [ -f "$plugin_root/scripts/update-check.sh" ]; then
  # shellcheck source=../scripts/update-check.sh
  . "$plugin_root/scripts/update-check.sh" 2>/dev/null || true
  if command -v harness_update_notice >/dev/null 2>&1; then
    # 同じ理由で外側に >/dev/null 2>&1 を付けない (このすぐ上のコメント参照)。
    harness_update_fetch_async "$plugin_root" || true
    update_line="$(harness_update_notice "$plugin_root" 2>/dev/null || true)"
    # 画面下部のお知らせ枠へ結果を渡す (statusline はプラグインのパスを知れないため)。
    # フラグの鍵はプロジェクト側のパス (root) にする (plugin_root では 1.x/2.x や
    # 別案件どうしの「更新あり」表示が入れ替わる)。
    harness_update_flag_sync "$plugin_root" "$root" >/dev/null 2>&1 || true
  fi
  # --- 更新後の入れ替え: **既定 off**。/config で on にした人だけ、プラグインが
  # 新しくなった回に限り、複製された 3 ファイル (statusline.sh / tasks-path.sh /
  # context-usage.sh) を配布版に揃える。ルール・設定・CLAUDE.md・台帳には触らない。
  if command -v harness_sync_owned_scripts >/dev/null 2>&1; then
    sync_line="$(harness_sync_owned_scripts "$plugin_root" "$root" 2>/dev/null || true)"
  fi
fi

# --- 直近 state (導入先リポジトリ側) ---
state=""
for d in "$root/.claude/state" "$root/docs/state"; do
  [ -d "$d" ] || continue
  f="$(ls -t "$d" 2>/dev/null | head -1)"
  [ -n "$f" ] && state="${d#"$root"/}/$f" && break
done

# --- 効いている設定: 版と tasks / worktree / notify を 1 行で (何が効いているかを 1 か所で見る) ---
plugin_version=""
command -v harness_local_version >/dev/null 2>&1 && plugin_version="$(harness_local_version "$plugin_root" 2>/dev/null || true)"
cfg_worktree="${HC_WORKTREE:-}"; cfg_notify="${HC_NOTIFY:-}"
if command -v harness_yml_value >/dev/null 2>&1; then
  [ -n "$cfg_worktree" ] || cfg_worktree="$(harness_yml_value "$root" worktree 2>/dev/null || true)"
  [ -n "$cfg_notify" ] || cfg_notify="$(harness_yml_value "$root" notify 2>/dev/null || true)"
fi
settings_line="hirai-lite ${plugin_version:+v${plugin_version}・}tasks: ${tasks_form}・worktree: ${cfg_worktree:-off}・notify: ${cfg_notify:-off}"

# 5 行以内を守るため、効いている設定は進め方の行の後ろに足す (行を増やさない)
echo "[harness] 進め方: ${mode_line} ／ ${settings_line}"
echo "[harness] ${task_line}"
if [ -n "$state" ]; then
  echo "[harness] 前回の続き: ${state} (/hirai-lite:state resume で読み込めます)"
else
  echo "[harness] 前回の続き: なし"
fi
# 更新の合図と入れ替えの報告は、重なっても 1 行にまとめる
extra_line="$update_line"
if [ -n "$sync_line" ]; then
  if [ -n "$extra_line" ]; then extra_line="${extra_line} ／ ${sync_line#\[harness\] }"; else extra_line="$sync_line"; fi
fi
[ -n "$extra_line" ] && echo "$extra_line"
# Orca の worktree の警告・知らせ方 (worktree / notify が off なら何も出ない)。
# 何行出ても 1 行にまとめる (開始時の表示は 5 行以内: 設定 / タスク / 前回 / 更新 / Orca)。
if [ -f "$plugin_root/scripts/orca-context.sh" ]; then
  orca_out="$(CLAUDE_PROJECT_DIR="$root" bash "$plugin_root/scripts/orca-context.sh" 2>/dev/null || true)"
  if [ -n "$orca_out" ]; then
    printf '%s\n' "$orca_out" | awk 'NR==1{printf "%s", $0; next} {sub(/^\[harness\] /, ""); printf " ／ %s", $0} END{printf "\n"}'
  fi
fi

exit 0
