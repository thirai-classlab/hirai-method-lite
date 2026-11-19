#!/usr/bin/env python3
"""
hirai_board.py — `hirai-task board` が描く、GitHub Project の全体像（1 枚の HTML と文字の木）。

入口は bin/hirai-task の board（gh で取り、ready と同じ判定をそこで済ませる）。ここは渡された
形を描くだけで、ネットワークにも gh にも出ない。標準ライブラリだけで動き、外部 CDN は読まない。

渡される形（bin/hirai-task の board_view）:
  repo・project・fetched_at・how（fetched / cached / from）・age_minutes・rows_total・skipped
  issues: [{number, title, state, url, parent_number, status, kind}]（Project の並び順）
  blockers: {番号: [open の blocked by の番号]} ／ open_prs: {番号: [open の PR の番号]}
  wave_blockers: {wave: [その wave を止める wave]} ／ wave_exit: {wave: {met, line, human}}
  not_ready: {番号: ready に出ない理由}（着手可の open な task だけ）／ ready: [番号]

木は種別と親だけで決める: wave → feature（親が wave）→ task（親が feature。種別が空の行も
task に数える）。そこに入らない行は「木に入らない行」に理由つきで出す。

止まっている task: open で、Status が 承認待ち・判断待ち・依存待ち・保留・未設定のもの、または
着手可なのに ready に出ないもの（理由は hirai-task の ready_block_reason と同じ）。進行中と
レビュー中は止まっているに数えない（レビュー中は「merge 待ち」として別に数える）。

失効: タスクの正本を GitHub Projects 以外へ移したとき。
"""
from __future__ import annotations

import datetime
import html
import re
from collections import Counter

STATUS_ORDER = ('完了', 'レビュー中', '進行中', '着手可', '依存待ち', '判断待ち', '承認待ち', '保留')
NO_STATUS = '(未設定)'
STUCK_STATUSES = ('承認待ち', '判断待ち', '依存待ち', '保留', '')
STATUS_LABELS = {'承認待ち': '承認待ち', '判断待ち': '判断待ち（裁定を待つ）', '依存待ち': '依存待ち',
                 '保留': '保留', '': 'Status 未設定'}
# 隣り合う状態が区別できる色。色だけで区別せず、Status 名を必ず文字で併記する。
STATUS_COLORS = {
    '完了': '#008300', 'レビュー中': '#4a3aa7', '進行中': '#2a78d6', '着手可': '#1baf7a',
    '依存待ち': '#e34948', '判断待ち': '#eda100', '承認待ち': '#e87ba4', '保留': '#a8a69f',
}
OTHER_COLOR = '#52514e'
# hirai-task の NOT_READY_* と同じ文言（要約の内訳の並び）。知らない理由は後ろに足す。
NOT_READY_ORDER = ('自分に未完了の blocked by', '親の feature に未完了の blocked by', '親の feature が着手可でない',
                   '[User]（人の作業）', '親が feature でない・無い',
                   '種別が task でない（空を含む。ready に出ない）')
USER_MARK = '[User]'
OPERATION_MARK = '[操作]'  # 人の資格・権限が要るが AI が行う操作。要るのは承認カード
NON_TASK_KINDS = ('wave', 'feature', '設計メモ')
ISSUE_URL_RE = re.compile(r'^https://github\.com/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+/(?:issues|pull)/\d+\Z')
MARK_HERE = ' ←'
READY_NOTE = '着手できるかは `hirai-task ready` が正（この表は Status と blocked by から数えた全体像）。'


class ScopeError(Exception):
    """--wave・--feature・--task の番号から木を決められない（hirai-task が exit 2 にする）。"""


def e(value) -> str:
    return html.escape(str(value), quote=True)


def one_line(text) -> str:
    return ' '.join(str(text or '').split())


def is_task(issue: dict) -> bool:
    return (issue.get('kind') or '') not in NON_TASK_KINDS


def is_open(issue: dict) -> bool:
    return issue.get('state') != 'CLOSED'


def status_of(issue: dict) -> str:
    return issue.get('status') or NO_STATUS


# ── 木を組む ────────────────────────────────────────────────────
def build(data: dict) -> dict:
    issues = data['issues']
    by_number = {i['number']: i for i in issues}
    waves = [i for i in issues if i.get('kind') == 'wave']
    feats_of = {w['number']: [] for w in waves}
    tasks_of: dict[int, list] = {}
    wave_of_feature: dict[int, int] = {}
    orphan_feats, untreed = [], []
    for i in issues:
        if i.get('kind') != 'feature':
            continue
        tasks_of.setdefault(i['number'], [])
        parent = by_number.get(i.get('parent_number'))
        if parent and parent.get('kind') == 'wave':
            feats_of[parent['number']].append(i)
            wave_of_feature[i['number']] = parent['number']
        else:
            orphan_feats.append(i)
            untreed.append((i, '親が wave でない feature' if parent else '親の無い feature'))
    for i in issues:
        if not is_task(i):
            continue
        parent = by_number.get(i.get('parent_number'))
        if parent and parent.get('kind') == 'feature':
            tasks_of[parent['number']].append(i)
        elif i.get('parent_number') is None:
            untreed.append((i, '親の無い task'))
        elif parent is None:
            untreed.append((i, f"親 #{i['parent_number']} が Project に無い"))
        else:
            untreed.append((i, f"親 #{parent['number']} が feature でない（{parent.get('kind') or '種別なし'}）"))
    model = {'data': data, 'by_number': by_number, 'waves': waves, 'feats_of': feats_of, 'tasks_of': tasks_of,
             'wave_of_feature': wave_of_feature, 'orphan_feats': orphan_feats, 'untreed': untreed,
             'ready': set(data['ready']), 'not_ready': data['not_ready']}
    model['level'], model['cyclic'] = wave_levels(model)
    return model


def wave_levels(model: dict) -> tuple[dict, set]:
    """wave の段（止める wave の段 + 1）。循環とその下流は並べられないので最後の段に置き、印を付ける。"""
    numbers = [w['number'] for w in model['waves']]
    known = set(numbers)
    preds = {n: [b for b in model['data']['wave_blockers'].get(n, []) if b in known and b != n] for n in numbers}
    level: dict[int, int] = {}
    remaining = list(numbers)
    progressed = True
    while remaining and progressed:
        progressed = False
        for n in list(remaining):
            if all(p in level for p in preds[n]):
                level[n] = 1 + max((level[p] for p in preds[n]), default=-1)
                remaining.remove(n)
                progressed = True
    last = 1 + max(level.values(), default=-1)
    for n in remaining:
        level[n] = last
    return level, set(remaining)


def wave_tasks(model: dict, wave: int) -> list:
    return [t for f in model['feats_of'].get(wave, []) for t in model['tasks_of'][f['number']]]


def locate(model: dict, number: int) -> tuple:
    """(wave, feature) の番号。木に入らない行は (None, None)。"""
    issue = model['by_number'].get(number)
    if issue is None:
        return None, None
    if issue.get('kind') == 'wave':
        return number, None
    if issue.get('kind') == 'feature':
        return model['wave_of_feature'].get(number), number
    parent = model['by_number'].get(issue.get('parent_number'))
    if is_task(issue) and parent and parent.get('kind') == 'feature':
        return model['wave_of_feature'].get(parent['number']), parent['number']
    return None, None


def has_exited(model: dict, wave: int) -> bool:
    state = model['data']['wave_exit'].get(wave) or {}
    return bool(state.get('met') and state.get('line'))


def exit_text(model: dict, wave: int) -> str:
    state = model['data']['wave_exit'].get(wave) or {}
    if state.get('met') and state.get('line'):
        text = '出た'
    elif state.get('human'):
        text = '出る条件は人の判断'
    elif state.get('met'):
        text = '子は済み・出る条件の行なし'
    else:
        text = '未'
    return text + ('・循環' if wave in model['cyclic'] else '')


# ── 止まっているか ──────────────────────────────────────────────
def is_stuck(model: dict, task: dict) -> bool:
    if not is_open(task) or not is_task(task):
        return False
    status = task.get('status') or ''
    return status in STUCK_STATUSES or (status == '着手可' and task['number'] in model['not_ready'])


def blocker_info(model: dict, number: int, blockers: list) -> list:
    """止めているもの（open）に印を付ける: Project 外・wave をまたぐ・feature をまたぐ・判断待ち。"""
    mine = locate(model, number)
    subject_is_wave = (model['by_number'].get(number) or {}).get('kind') == 'wave'
    out = []
    for b in blockers:
        target = model['by_number'].get(b)
        marks = []
        if target is None:
            marks.append('Project 外')
        else:
            theirs = locate(model, b)
            if subject_is_wave:
                pass  # wave 同士の依存は図の矢印そのもの。「またぐ」は task と feature の印
            elif mine[0] is None or theirs[0] is None:
                marks.append('wave 不明')
            elif mine[0] != theirs[0]:
                marks.append('wave をまたぐ')
            elif mine[1] != theirs[1]:
                marks.append('feature をまたぐ')
            if target.get('status') == '判断待ち':
                marks.append('判断待ち')
        out.append({'number': b, 'title': one_line((target or {}).get('title')), 'marks': marks})
    return out


def stuck_reason(model: dict, task: dict) -> tuple[str, list]:
    """(理由, 止めているもの)。止めているものは blocker_info の形。"""
    data, number = model['data'], task['number']
    status = task.get('status') or ''
    parent = model['by_number'].get(task.get('parent_number'))
    own = blocker_info(model, number, data['blockers'].get(number, []))
    if status != '着手可':
        label = STATUS_LABELS.get(status, status)
        if status == '承認待ち' and parent and parent.get('kind') == 'feature' and parent.get('status') == '承認待ち':
            label += f"（親の feature #{parent['number']} も承認待ち）"
        return label, own
    reason = model['not_ready'].get(number, '')
    if reason == '親の feature が着手可でない' and parent:
        return f"{reason}（#{parent['number']} は {status_of(parent)}）", own
    if reason == '親の feature に未完了の blocked by' and parent:
        return reason, blocker_info(model, parent['number'], data['blockers'].get(parent['number'], []))
    return reason, own


def stuck_rows(model: dict) -> list:
    """止まっている task を木の順で: (wave, feature, task, 理由, 止めているもの)。木に入らない task は最後。"""
    rows = []
    for w in model['waves']:
        for f in model['feats_of'][w['number']]:
            for t in model['tasks_of'][f['number']]:
                if is_stuck(model, t):
                    rows.append((w, f, t, *stuck_reason(model, t)))
    for i, _why in model['untreed']:
        if is_task(i) and is_stuck(model, i):
            rows.append((None, None, i, *stuck_reason(model, i)))
    for f in model['orphan_feats']:
        for t in model['tasks_of'][f['number']]:
            if is_stuck(model, t):
                rows.append((None, f, t, *stuck_reason(model, t)))
    return rows


def wave_row(model: dict, wave: int) -> dict:
    tasks = wave_tasks(model, wave)
    open_tasks = [t for t in tasks if is_open(t)]
    return {'counts': Counter(status_of(t) for t in tasks), 'total': len(tasks), 'open': len(open_tasks),
            'stuck': sum(1 for t in open_tasks if is_stuck(model, t)),
            'not_ready': sum(1 for t in open_tasks if t.get('status') == '着手可' and t['number'] in model['not_ready'])}


def summary_rows(model: dict) -> list:
    """「どこで何件止まっているか」の行: (区分, 件数, 定義・内訳, 字下げ)。"""
    data = model['data']
    issues = data['issues']
    open_tasks = [t for t in issues if is_task(t) and is_open(t)]
    by_status = Counter(t.get('status') or '' for t in open_tasks)
    review = [t for t in open_tasks if t.get('status') == 'レビュー中']
    no_pr = sum(1 for t in review if not data['open_prs'].get(t['number']))
    dep = [t for t in open_tasks if t.get('status') == '依存待ち']
    marks = Counter(m for t in dep for b in blocker_info(model, t['number'], data['blockers'].get(t['number'], []))
                    for m in b['marks'])
    dep_with = sum(1 for t in dep if data['blockers'].get(t['number']))
    reasons = Counter(model['not_ready'][t['number']] for t in open_tasks
                      if t.get('status') == '着手可' and t['number'] in model['not_ready'])
    order = list(NOT_READY_ORDER) + sorted(set(reasons) - set(NOT_READY_ORDER))
    pending_feats = sum(1 for i in issues if i.get('kind') == 'feature' and is_open(i) and i.get('status') == '承認待ち')
    rows = [
        ('着手できる（hirai-task ready が出す）', len(data['ready']), '種別 task・着手可・親の feature が着手可・'
         '自分と親に未完了の blocked by なし・[User] でない', 0),
        ('進行中', by_status['進行中'], '', 0),
        ('レビュー中（merge 待ち）', by_status['レビュー中'], f'うち open の PR が無い {no_pr}', 0),
        ('承認待ちの feature（人がボードで着手可にする）', pending_feats, '子の task はこの feature が着手可になるまで ready に出ない', 0),
        ('うち承認しても動かない', len(data.get('stalls') or {}), 'blocked by・子が人の作業と保留だけ・子が無い', 1),
        ('うちカード無し・形の問題', sum(1 for c in (data.get('cards') or {}).values() if c['kind'] == 'approval' and c['problems']),
         '承認カード（hirai-task card --lint）', 1),
        ('承認待ちの task', by_status['承認待ち'], '', 0),
        ('判断待ち（裁定を待つ）', by_status['判断待ち'], '', 0),
        ('依存待ち', by_status['依存待ち'], f"open の blocked by あり {dep_with}（wave をまたぐ {marks['wave をまたぐ']}・"
         f"feature をまたぐ {marks['feature をまたぐ']}・Project 外 {marks['Project 外']}）", 0),
        ('保留', by_status['保留'], '', 0),
        ('Status 未設定', by_status[''], '', 0),
        ('着手可なのに着手できない', sum(reasons.values()), 'ready と同じ判定で、出ない理由ごとの内訳', 0),
    ]
    rows += [(reason, reasons[reason], '', 1) for reason in order if reasons.get(reason)]
    rows += [
        ('[User] の人の作業（open）', sum(1 for t in open_tasks if USER_MARK in (t.get('title') or '')),
         'ready・align の外（today の user-actions と同じ）', 0),
        ('閉じたのに完了でない', sum(1 for t in issues if is_task(t) and not is_open(t) and t.get('status') != '完了'), '', 0),
        ('止まっている task（合計）', sum(1 for t in open_tasks if is_stuck(model, t)),
         '承認待ち・判断待ち・依存待ち・保留・Status 未設定、と着手可なのに着手できない open の task', 0),
    ]
    return rows


def kind_counts(model: dict) -> Counter:
    return Counter(('task' if is_task(i) and (i.get('kind') or '') else
                    '種別なし' if is_task(i) else i.get('kind')) for i in model['data']['issues'])


def source_note(data: dict) -> str:
    if data['how'] == 'fetched':
        return '取り直した'
    if data['how'] == 'cached':
        return f"残した JSON を使用（{data['age_minutes']} 分前）"
    return '--from の JSON'


def summary_line(data: dict) -> str:
    """HTML を書いたときに端末へ出す 1 行（スラッシュコマンドがそのまま利用者に見せる）。"""
    rows = {label: count for label, count, _note, _indent in summary_rows(build(data))}
    return (f"止まっている task {rows['止まっている task（合計）']} 件（承認待ち {rows['承認待ちの task']}・"
            f"判断待ち {rows['判断待ち（裁定を待つ）']}・依存待ち {rows['依存待ち']}・保留 {rows['保留']}・"
            f"Status 未設定 {rows['Status 未設定']}・着手可なのに着手できない {rows['着手可なのに着手できない']}）／ "
            f"着手できる {rows['着手できる（hirai-task ready が出す）']}・進行中 {rows['進行中']}・"
            f"レビュー中 {rows['レビュー中（merge 待ち）']}・承認待ちの feature {rows['承認待ちの feature（人がボードで着手可にする）']}")


# ── 文字の木 ────────────────────────────────────────────────────
def fmt_counts(counts: Counter) -> str:
    order = list(STATUS_ORDER) + sorted(set(counts) - set(STATUS_ORDER))
    return '・'.join(f'{s} {counts[s]}' for s in order if counts.get(s)) or 'なし'


def blockers_text(blockers: list) -> str:
    if not blockers:
        return 'なし'
    return ', '.join(f"#{b['number']}" + (f" {b['title'][:30]}" if b['title'] else '')
                     + (f"（{'・'.join(b['marks'])}）" if b['marks'] else '') for b in blockers)


def task_line(model: dict, task: dict, here: int | None) -> str:
    n = task['number']
    if is_stuck(model, task):
        reason, blockers = stuck_reason(model, task)
        note = reason + (f' | 止めている: {blockers_text(blockers)}' if blockers else '')
    else:
        note = '着手できる' if n in model['ready'] else '-'
    mark = MARK_HERE if here == n else ''
    return f"    - task #{n} {one_line(task.get('title'))} | {status_of(task)} | {note}{card_text(model, n)}{mark}"


def card_text(model: dict, number: int) -> str:
    """--text の行に足すカードの印（要るカードがある行だけ）。"""
    info = (model['data'].get('cards') or {}).get(number)
    if info is None:
        return ''
    stall = (model['data'].get('stalls') or {}).get(number)
    if not info['has_card']:
        text = ' | カード無し'
    else:
        rec = f"（推奨 {one_line(info['recommend'])}）" if info['recommend'] and info['kind'] != 'work' else ''
        text = f" | カード: {one_line(info['decide'])}{rec}" + (' | カードの形に問題' if info['problems'] else '')
    return text + (f' | 承認しても動かない: {stall}' if stall else '')


def feature_lines(model: dict, feat: dict, here: int | None) -> list:
    kids = model['tasks_of'][feat['number']]
    closed = sum(1 for t in kids if not is_open(t))
    blockers = blocker_info(model, feat['number'], model['data']['blockers'].get(feat['number'], []))
    mark = MARK_HERE if here == feat['number'] else ''
    lines = [f"  - feature #{feat['number']} {one_line(feat.get('title'))} | {status_of(feat)} | "
             f"子 task {len(kids)}（open {len(kids) - closed}・閉 {closed}） | blocked by: {blockers_text(blockers)}"
             f"{card_text(model, feat['number'])}{mark}"]
    lines += [task_line(model, t, here) for t in kids if is_open(t)]
    return lines


def wave_line(model: dict, wave: dict, here: int | None) -> str:
    n = wave['number']
    row = wave_row(model, n)
    blockers = blocker_info(model, n, model['data']['wave_blockers'].get(n, []))
    mark = MARK_HERE if here == n else ''
    return (f"- #{n} {one_line(wave.get('title'))} | {exit_text(model, n)} | blocked by: {blockers_text(blockers)} | "
            f"task {row['total']}: {fmt_counts(row['counts'])}（止まっている {row['stuck']}）{mark}")


def resolve_scope(model: dict, scope: tuple) -> tuple:
    """(wave, 絞る feature, 印を付ける番号)。決められなければ ScopeError。"""
    kind, number = scope
    issue = model['by_number'].get(number)
    if issue is None:
        raise ScopeError(f'#{number} は Project に無い')
    if kind in ('wave', 'feature') and issue.get('kind') != kind:
        raise ScopeError(f"#{number} は {kind} でない（今の種別: {issue.get('kind') or '空'}）")
    wave, feature = locate(model, number)
    if wave is None:
        raise ScopeError(f'#{number} の入っている wave を決められない（木に入らない行。--text だけで全体を見る）')
    if kind == 'wave':
        return wave, None, None
    if kind == 'feature':
        return wave, number, None
    return wave, None, number


def render_text(data: dict, scope: tuple | None = None) -> str:
    model = build(data)
    kinds = kind_counts(model)
    lines = [f"# 全体像（{source_note(data)}・取得 {data['fetched_at']}・行 {data['rows_total']}・"
             f"wave {kinds['wave']} / feature {kinds['feature']} / task {kinds['task']}"
             + (f" / 種別なし {kinds['種別なし']}" if kinds['種別なし'] else '') + '）', READY_NOTE]
    if model['cyclic']:
        lines.append('注意: wave の依存が循環している（またはその下流）: '
                     + ' '.join(f'#{n}' for n in sorted(model['cyclic'])))
    if scope is not None:
        wave, feature, here = resolve_scope(model, scope)
        target = model['by_number'][wave]
        lines.append(wave_line(model, target, here))
        for f in model['feats_of'][wave]:
            if feature is None or f['number'] == feature:
                lines += feature_lines(model, f, here)
        return '\n'.join(lines) + '\n'
    lines.append('## どこで何件止まっているか')
    for label, count, note, indent in summary_rows(model):
        lines.append(f"{'  ' * indent}- {label}: {count}" + (f'（{note}）' if note else ''))
    lines.append('## wave ごとの件数（合計は子の task。閉じたものも含む）')
    for w in model['waves']:
        row = wave_row(model, w['number'])
        lines.append(f"- #{w['number']} {one_line(w.get('title'))} | {exit_text(model, w['number'])} | "
                     f"合計 {row['total']}・open {row['open']}・止まっている {row['stuck']} | {fmt_counts(row['counts'])}")
    lines.append('## 木（wave → feature → task。閉じた task は件数だけ）')
    for w in model['waves']:
        lines.append(wave_line(model, w, None))
        for f in model['feats_of'][w['number']]:
            lines += feature_lines(model, f, None)
    if model['untreed']:
        lines.append(f"## 木に入らない行（{len(model['untreed'])} 件）")
        lines += [f"- #{i['number']} {one_line(i.get('title'))} | {status_of(i)} | {why}" for i, why in model['untreed']]
    return '\n'.join(lines) + '\n'


# ── 要約（スマートフォンで読む Markdown。会話に出す・issue の本文に載せる） ─────────
# 1 行 40 字前後・表は 2 列まで。題名は短く切り、`<` `>` は全角にする（本文の目印や HTML を作らせない）。
MD_TITLE_WIDTH = 22
MD_TOP = 5
SHORT_REASONS = {'自分に未完了の blocked by': '自分の待ち', '親の feature に未完了の blocked by': '親の待ち',
                 '親の feature が着手可でない': '親が未承認',
                 '[User]（人の作業）': 'User', '親が feature でない・無い': '親なし',
                 '種別が task でない（空を含む。ready に出ない）': '種別なし'}
# 要約は issue の本文にも載る（--publish）。題名から通知（@）・リンクと画像（[ ] !）・表の区切り（|）・
# コード（`）・目印や HTML（< >）を作らせないよう、全角に置き換える。文字そのものは残す。
MD_NEUTRAL = str.maketrans({'<': '＜', '>': '＞', '@': '＠', '[': '［', ']': '］', '|': '｜', '`': '｀'})


def short(text, width: int = MD_TITLE_WIDTH) -> str:
    text = one_line(text).translate(MD_NEUTRAL)
    return text if len(text) <= width else text[:width - 1] + '…'


def ordered_tasks(model: dict) -> list:
    """task を木の順（wave → feature）で。木に入らない task は最後。"""
    tasks = [t for w in model['waves'] for t in wave_tasks(model, w['number'])]
    tasks += [t for f in model['orphan_feats'] for t in model['tasks_of'][f['number']]]
    return tasks + [i for i, _why in model['untreed'] if is_task(i)]


def md_list(rows: list, suffix=None) -> list:
    lines = [f"- #{r['number']} {short(r.get('title'))}" + (suffix(r) if suffix else '') for r in rows[:MD_TOP]]
    return lines + ([f'- ほか {len(rows) - MD_TOP} 件'] if len(rows) > MD_TOP else [])


def card_list(model: dict, rows: list) -> list:
    """あなたの番の行: 1 行目にカードの決めること（無ければ題名）、2 行目に推奨・期限・カード無し・動かない。"""
    cards, stalls = model['data'].get('cards') or {}, model['data'].get('stalls') or {}
    stall_short = model['data'].get('stall_short') or {}  # 短い言い方は bin/hirai-task の STALL_SHORT が決める
    lines = []
    for r in rows[:MD_TOP]:
        info = cards.get(r['number']) or {'has_card': False}
        notes = [] if info['has_card'] else ['カード無し']
        if info['has_card']:
            notes += [f"推奨 {short(info['recommend'], 12)}"] if info['recommend'] and info['kind'] != 'work' else []
            notes += [f"期限 {short(info['deadline'], 12)}"] if info.get('deadline') else []
            notes += ['形の問題あり'] if info['problems'] else []
        stall = stalls.get(r['number'])
        notes += [f"動かない（{stall_short.get(r['number']) or short(stall, 12)}）"] if stall else []
        lines += [f"- #{r['number']} {short(info['decide'] if info['has_card'] else r.get('title'))}",
                  '  ' + '・'.join(notes or ['—'])]
    missing = sum(1 for r in rows if not (cards.get(r['number']) or {}).get('has_card'))
    moving = sum(1 for r in rows if r['number'] in stalls)
    head = [f'うちカード無し {missing}' + (f'・承認しても動かない {moving}' if moving else '')] if missing or moving else []
    return head + lines + ([f'- ほか {len(rows) - MD_TOP} 件'] if len(rows) > MD_TOP else [])


def your_turn(model: dict, open_tasks: list) -> list:
    """あなたの番（人が動かすもの）: (見出し, 行, 末尾の注記)。"""
    data = model['data']
    feats = [i for i in data['issues'] if i.get('kind') == 'feature' and is_open(i) and i.get('status') == '承認待ち']

    def pr_of(t: dict) -> str:
        prs = data['open_prs'].get(t['number']) or []
        return f' → PR #{prs[0]}' if prs else '（PR なし）'
    return [
        ('承認待ちの feature（ボードで着手可に）', feats, 'card'),
        ('判断待ち（裁定する）', [t for t in open_tasks if t.get('status') == '判断待ち'], 'card'),
        ('[User] の作業', [t for t in open_tasks if USER_MARK in (t.get('title') or '')], 'card'),
        ('操作の承認', [t for t in open_tasks if OPERATION_MARK in (t.get('title') or '') and t.get('status') == '承認待ち'], 'card'),
        ('レビュー中（PR の merge）', [t for t in open_tasks if t.get('status') == 'レビュー中'], pr_of),
    ]


def render_summary_md(data: dict) -> str:
    model = build(data)
    tasks = ordered_tasks(model)
    open_tasks = [t for t in tasks if is_open(t)]
    kinds = kind_counts(model)
    by_status = Counter(t.get('status') or '' for t in open_tasks)
    stuck = [t for t in open_tasks if is_stuck(model, t)]
    not_ready = [t for t in stuck if t.get('status') == '着手可']
    lines = [f"## 進捗 Project #{data['project']}", f"取得 {data['fetched_at'][:16]}",
             f"task {len(tasks)}（open {len(open_tasks)}）・wave {kinds['wave']}・feature {kinds['feature']}",
             f"着手できる {len(data['ready'])}・進行中 {by_status['進行中']}・レビュー中 {by_status['レビュー中']}", '',
             '### あなたの番']
    turn = [(label, rows, suffix) for label, rows, suffix in your_turn(model, open_tasks) if rows]
    for label, rows, suffix in turn:
        lines += [f'{label} {len(rows)}', *(card_list(model, rows) if suffix == 'card' else md_list(rows, suffix))]
    if not turn:
        lines.append('なし')
    groups = [('承認待ちの task', [t for t in stuck if t.get('status') == '承認待ち'], True),
              ('判断待ち', [t for t in stuck if t.get('status') == '判断待ち'], False),
              ('依存待ち', [t for t in stuck if t.get('status') == '依存待ち'], True),
              ('保留', [t for t in stuck if t.get('status') == '保留'], True),
              ('Status 未設定', [t for t in stuck if not t.get('status')], True),
              ('着手可だが着手できない', not_ready, True)]
    groups = [g for g in groups if g[1]]
    lines += ['', f'### 止まっている {len(stuck)}']
    if groups:
        lines += ['| 区分 | 件数 |', '|---|--:|'] + [f'| {label} | {len(rows)} |' for label, rows, _ in groups]

    def why(t: dict) -> str:
        if t.get('status') == '着手可':
            return f"（{SHORT_REASONS.get(model['not_ready'].get(t['number']), '理由不明')}）"
        blockers = data['blockers'].get(t['number']) or []
        return f" ← #{blockers[0]}" + (f' ほか {len(blockers) - 1}' if len(blockers) > 1 else '') if blockers else ''
    for label, rows, detail in groups:
        if detail:
            lines += ['', f'#### {label} {len(rows)}', *md_list(rows, why)]
    broken = sum(1 for t in tasks if not is_open(t) and t.get('status') != '完了')
    if broken:
        lines += ['', f'閉じたのに完了でない task {broken}']
    lines += ['', '着手できるかは hirai-task ready が正']
    return '\n'.join(lines) + '\n'


# ── HTML ───────────────────────────────────────────────────────
def issue_link(model: dict, number: int) -> str:
    """Project に居て URL が https の github.com の issue・PR のときだけリンクにする。"""
    url = (model['by_number'].get(number) or {}).get('url') or ''
    if ISSUE_URL_RE.match(url):
        return f'<a href="{e(url)}">#{e(number)}</a>'
    return f'#{e(number)}'


def scroll(inner: str) -> str:
    """幅の広い表・図を横スクロールの箱に入れる（スマートフォンで本文の幅を崩さない）。"""
    return f'<div class="scroll">{inner}</div>'


def swatch(status: str) -> str:
    return f'<span class="swatch" style="background:{STATUS_COLORS.get(status, OTHER_COLOR)}"></span>{e(status)}'


def render_bar(counts: Counter, width: int = 240) -> str:
    total = sum(counts.values())
    if not total:
        return '<span class="muted">task 0 件</span>'
    parts, x = [], 0.0
    order = list(STATUS_ORDER) + sorted(set(counts) - set(STATUS_ORDER))
    for status in order:
        n = counts.get(status, 0)
        if n:
            w = max(n / total * width - 2, 1.5)
            parts.append(f'<rect x="{x:.1f}" y="0" width="{w:.1f}" height="12" rx="2" '
                         f'fill="{STATUS_COLORS.get(status, OTHER_COLOR)}"><title>{e(status)}: {n} 件</title></rect>')
            x += w + 2
    return (f'<svg width="{width}" height="12" role="img" aria-label="{e(fmt_counts(counts))}">{"".join(parts)}</svg>'
            f'<div class="breakdown">{e(fmt_counts(counts))}</div>')


def blocker_chips(model: dict, blockers: list) -> str:
    if not blockers:
        return '<span class="muted">なし</span>'
    return ''.join(f'<div class="chip">{issue_link(model, b["number"])} {e(b["title"][:40])}'
                   + ''.join(f'<span class="mark">{e(m)}</span>' for m in b['marks']) + '</div>' for b in blockers)


def render_header(model: dict) -> str:
    data = model['data']
    kinds = kind_counts(model)
    skipped = '・'.join(f'{k} {n}' for k, n in data['skipped'].items() if n) or 'なし'
    rows = [('データ', source_note(data)), ('取得日時', data['fetched_at']),
            ('件数', f"{data['rows_total']} 行（issue {len(data['issues'])}: "
                     + ' / '.join(f'{k} {n}' for k, n in sorted(kinds.items())) + '）'),
            ('読み飛ばした行', skipped), ('生成日時', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))]
    body = ''.join(f'<tr><th>{e(k)}</th><td>{e(v)}</td></tr>' for k, v in rows)
    warn = ''
    if model['cyclic']:
        warn = ('<p class="warn">注意: wave の依存が循環している（またはその下流）: '
                + ' '.join(issue_link(model, n) for n in sorted(model['cyclic'])) + '</p>')
    return (f'<h1>Project #{e(data["project"])} の全体像 — {e(data["repo"])}</h1>'
            f'<table class="meta">{body}</table>{warn}<p class="note">{e(READY_NOTE)}</p>')


def render_summary(model: dict) -> str:
    rows = ''.join(f'<tr class="lv{indent}"><th>{e(label)}</th><td class="num">{count}</td><td>{e(note)}</td></tr>'
                   for label, count, note, indent in summary_rows(model))
    return ('<section><h2>どこで何件止まっているか</h2><div class="scroll"><table class="summary"><thead><tr><th>区分</th><th>件数</th>'
            f'<th>定義・内訳</th></tr></thead><tbody>{rows}</tbody></table></div></section>')


def render_queue(model: dict) -> str:
    """承認と判断の待ち（あなたの番）: カードの決めること・推奨・期限・動かない理由・形の問題。"""
    data = model['data']
    cards, stalls = data.get('cards') or {}, data.get('stalls') or {}
    names = {'approval': '承認', 'decision': '判断', 'work': '人の作業'}
    rows = ''.join(
        f'<tr><td>{issue_link(model, n)}</td><td>{e(names[c["kind"]])}</td>'
        f'<td>{e(one_line(c["decide"]) if c["has_card"] else "カード無し")}</td><td>{e(c["recommend"])}</td>'
        f'<td>{e(c.get("deadline") or "")}</td><td>{e(stalls.get(n, ""))}</td><td>{e(" / ".join(c["problems"]))}</td></tr>'
        for n, c in sorted(cards.items(), key=lambda kv: (list(names).index(kv[1]['kind']), kv[0])))
    table = scroll('<table><thead><tr><th>#</th><th>種類</th><th>決めること（カード）</th><th>推奨</th><th>期限</th>'
                   f'<th>承認しても動かない</th><th>カードの問題</th></tr></thead><tbody>{rows}</tbody></table>') \
        if rows else '<p class="muted">0 件</p>'
    return (f'<section><h2>承認と判断の待ち（あなたの番・{len(cards)} 件）</h2>{table}<p class="note">カードの型は '
            'docs/rules-reference/approval-template.md。直したら hirai-task card &lt;番号&gt; --sync。</p></section>')


def render_wave_counts(model: dict) -> str:
    statuses = list(STATUS_ORDER) + [NO_STATUS]
    head = ''.join(f'<th>{swatch(s)}</th>' for s in statuses)
    rows = []
    for w in model['waves']:
        row = wave_row(model, w['number'])
        cells = ''.join(f'<td class="num">{row["counts"].get(s, 0) or ""}</td>' for s in statuses)
        rows.append(f'<tr><td>{issue_link(model, w["number"])} {e(one_line(w.get("title")))}</td>'
                    f'<td>{e(exit_text(model, w["number"]))}</td>{cells}<td class="num">{row["total"]}</td>'
                    f'<td class="num">{row["open"]}</td><td class="num">{row["not_ready"]}</td>'
                    f'<td class="num stuck">{row["stuck"]}</td></tr>')
    return ('<section><h2>wave ごとの件数</h2><p class="note">数えるのは子の task（閉じたものも含む）。'
            '「着手できない」は着手可なのに ready に出ない task、「止まっている」は上の表の合計と同じ定義。</p>'
            f'<div class="scroll"><table><thead><tr><th>wave</th><th>出たか</th>{head}<th>合計</th><th>open</th>'
            f'<th>着手できない</th><th>止まっている</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></section>')


BOX_W, BOX_H, GAP_X, GAP_Y, MARGIN = 236, 96, 34, 56, 16


def render_graph(model: dict) -> str:
    if not model['waves']:
        return '<section><h2>wave の依存図</h2><p class="muted">wave なし</p></section>'
    columns: dict[int, int] = {}
    boxes = {}
    for w in model['waves']:
        lv = model['level'][w['number']]
        boxes[w['number']] = (MARGIN + columns.get(lv, 0) * (BOX_W + GAP_X), MARGIN + lv * (BOX_H + GAP_Y))
        columns[lv] = columns.get(lv, 0) + 1
    width = MARGIN * 2 + max(columns.values()) * (BOX_W + GAP_X)
    height = MARGIN * 2 + (max(columns) + 1) * (BOX_H + GAP_Y)
    edges = []
    for n, (dx, dy) in boxes.items():
        for b in model['data']['wave_blockers'].get(n, []):
            if b in boxes and b != n:
                sx, sy = boxes[b]
                cls = 'edge cycle' if n in model['cyclic'] and b in model['cyclic'] else 'edge'
                x1, y1, x2, y2 = sx + BOX_W / 2, sy + BOX_H, dx + BOX_W / 2, dy
                edges.append(f'<path class="{cls}" d="M{x1:.1f},{y1:.1f} C{x1:.1f},{y1 + GAP_Y:.1f} '
                             f'{x2:.1f},{y2 - GAP_Y:.1f} {x2:.1f},{y2:.1f}" fill="none" marker-end="url(#arrow)"/>')
    nodes = [_node_svg(model, w, boxes[w['number']]) for w in model['waves']]
    defs = ('<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
            'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#52514e"/></marker></defs>')
    legend = '<div class="legend">Status の色: ' + ''.join(f'<span class="kv">{swatch(s)}</span>' for s in STATUS_ORDER) + '</div>'
    note = ('<p class="note">箱 = wave、矢印 = 止めている wave から止められている wave へ。箱の下の帯 = 子 task の Status の内訳。'
            '赤い破線 = 依存が循環している wave（またはその下流）。「出た」は子の task が完了・保留だけで、'
            '本文に「出る条件のコマンド: exit 0」の行がある wave。</p>')
    return (f'<section><h2>wave の依存図</h2>{legend}<div class="scroll"><svg class="graph" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="wave の依存の図">{defs}'
            f'{"".join(edges)}{"".join(nodes)}</svg></div>{note}</section>')


def _node_svg(model: dict, wave: dict, xy: tuple) -> str:
    x, y = xy
    n = wave['number']
    row = wave_row(model, n)
    band, bx = [], 0.0
    for status in list(STATUS_ORDER) + [NO_STATUS]:
        c = row['counts'].get(status, 0)
        if c:
            w = max(c / row['total'] * (BOX_W - 16), 1.0)
            band.append(f'<rect x="{x + 8 + bx:.1f}" y="{y + BOX_H - 18}" width="{w:.1f}" height="10" '
                        f'fill="{STATUS_COLORS.get(status, OTHER_COLOR)}"><title>{e(status)}: {c} 件</title></rect>')
            bx += w
    cls = 'node cycle' if n in model['cyclic'] else 'node'
    return (f'<g><rect class="{cls}" x="{x}" y="{y}" width="{BOX_W}" height="{BOX_H}" rx="6">'
            f'<title>{e(wave.get("title"))}</title></rect>'
            f'<text x="{x + 8}" y="{y + 18}" class="nid">#{n} {e(exit_text(model, n))}</text>'
            f'<text x="{x + 8}" y="{y + 36}" class="nname">{e(one_line(wave.get("title"))[:24])}</text>'
            f'<text x="{x + 8}" y="{y + 56}" class="nstat">task {row["total"]}・open {row["open"]}・'
            f'止まっている {row["stuck"]}</text>{"".join(band)}</g>')


def _feature_row(model: dict, feat: dict) -> str:
    kids = model['tasks_of'][feat['number']]
    open_n = sum(1 for t in kids if is_open(t))
    blockers = blocker_info(model, feat['number'], model['data']['blockers'].get(feat['number'], [])) if is_open(feat) else []
    return (f'<tr><td>{issue_link(model, feat["number"])}</td><td>{e(one_line(feat.get("title")))}</td>'
            f'<td>{swatch(status_of(feat))}</td><td class="num">{len(kids)}（open {open_n}）</td>'
            f'<td>{render_bar(Counter(status_of(t) for t in kids))}</td><td>{blocker_chips(model, blockers)}</td></tr>')


def render_features(model: dict) -> str:
    head = ('<thead><tr><th>#</th><th>feature</th><th>Status</th><th>子 task</th><th>Status の内訳</th>'
            '<th>feature の blocked by（open）</th></tr></thead>')
    out = []
    for w in model['waves']:
        rows = ''.join(_feature_row(model, f) for f in model['feats_of'][w['number']])
        body = scroll(f'<table>{head}<tbody>{rows}</tbody></table>') if rows else '<p class="muted">feature なし</p>'
        out.append(f'<h3>{issue_link(model, w["number"])} {e(one_line(w.get("title")))}</h3>{body}')
    if model['orphan_feats']:
        rows = ''.join(_feature_row(model, f) for f in model['orphan_feats'])
        out.append('<h3>親が wave でない feature</h3>' + scroll(f'<table>{head}<tbody>{rows}</tbody></table>'))
    return f'<section><h2>wave ごとの feature</h2>{"".join(out)}</section>'


def render_stuck(model: dict) -> str:
    rows = []
    for w, f, t, reason, blockers in stuck_rows(model):
        where = ' / '.join(x for x in ((issue_link(model, w['number']) if w else ''),
                                        (issue_link(model, f['number']) if f else '')) if x) or '木の外'
        rows.append(f'<tr><td>{issue_link(model, t["number"])}</td><td>{e(one_line(t.get("title")))}</td>'
                    f'<td>{swatch(status_of(t))}</td><td>{where}</td><td>{e(reason)}</td>'
                    f'<td>{blocker_chips(model, blockers)}</td></tr>')
    table = scroll('<table><thead><tr><th>#</th><th>task</th><th>Status</th><th>wave / feature</th><th>理由</th>'
                   f'<th>止めているもの（open）</th></tr></thead><tbody>{"".join(rows)}</tbody></table>') if rows \
        else '<p class="muted">0 件</p>'
    return (f'<section><h2>止まっている task（{len(rows)} 件）</h2>{table}<p class="note">閉じた blocker は止めていないので出さない。'
            '印: wave・feature をまたぐ依存／判断待ちの issue に止められている／Project 外。</p></section>')


def render_untreed(model: dict) -> str:
    if not model['untreed']:
        return ''
    rows = ''.join(f'<tr><td>{issue_link(model, i["number"])}</td><td>{e(one_line(i.get("title")))}</td>'
                   f'<td>{e(i.get("state") or "")}</td><td>{swatch(status_of(i))}</td><td>{e(why)}</td></tr>'
                   for i, why in model['untreed'])
    return (f'<section><h2>木に入らない行（{len(model["untreed"])} 件）</h2>' + scroll(
        '<table><thead><tr><th>#</th><th>題名</th><th>state</th><th>Status</th><th>理由</th></tr></thead>'
        f'<tbody>{rows}</tbody></table>') + '</section>')


CSS = """
body{font:14px/1.5 -apple-system,"Hiragino Sans",sans-serif;margin:24px;color:#1f1e1c;background:#fff}
h1{font-size:20px}h2{font-size:17px;margin-top:32px;border-bottom:1px solid #ddd;padding-bottom:4px}h3{font-size:14px;margin:18px 0 6px}
table{border-collapse:collapse;margin:6px 0}th,td{border:1px solid #ddd;padding:4px 8px;vertical-align:top;text-align:left}
th{background:#f5f4f0}.meta th{width:9em}.num{text-align:right}.muted{color:#6b6a66}.note{color:#52514e;font-size:12px}
.summary .lv1 th{padding-left:2em;font-weight:normal}.stuck{font-weight:bold;color:#b3261e}
.warn{color:#b3261e}.swatch{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px}
.kv{margin-right:8px;white-space:nowrap}.breakdown{font-size:12px;margin-top:2px}
.node{fill:#faf9f6;stroke:#52514e}.node.cycle{stroke:#e34948;stroke-dasharray:5 3;stroke-width:2}
.edge{stroke:#52514e;stroke-width:1.5}.edge.cycle{stroke:#e34948;stroke-dasharray:5 3}
.nid{font-size:12px;font-weight:bold;fill:#1f1e1c}.nname{font-size:13px;fill:#1f1e1c}.nstat{font-size:11px;fill:#52514e}
.chip{font-size:12px;margin:1px 0}.mark{background:#fff0c2;border:1px solid #eda100;border-radius:3px;padding:0 4px;margin-left:4px;font-size:11px}
a{color:#2a78d6}.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%}
@media (max-width:600px){body{margin:12px;font-size:13px}th,td{padding:3px 6px}}
"""


def render_html(data: dict) -> str:
    model = build(data)
    body = (render_header(model) + render_summary(model) + render_queue(model) + render_wave_counts(model) + render_graph(model)
            + render_stuck(model) + render_features(model) + render_untreed(model))
    return ('<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>全体像 — Project #{e(data["project"])}</title>'
            f'<style>{CSS}</style></head><body>{body}</body></html>\n')
