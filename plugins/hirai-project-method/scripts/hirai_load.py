#!/usr/bin/env python3
"""
hirai_load.py — `hirai-task load` が描く、全体の進みと、振っているタスクの順番・進捗率。

入口は bin/hirai-task の load（gh で取り、設定と割り振りを読んで渡す）。ここは渡された形を描くだけで、
ネットワークにも gh にも出ない。標準ライブラリだけで動く。

進捗率は担当の申告でなく、PR と issue の実物で決める:
  0 着手前 ／ 20 進行中（PR なし） ／ 50 draft の PR ／ 60 ready で CI が走っているか赤 ／ 70 ready で CI が緑
  90 merge 済みで issue が開いている ／ 100 issue が閉じた

渡される形:
  view: bin/hirai-task の board_view（issues・open_prs など。木の組み方は hirai_board.build と同じ）
  prs: {'open': [PR], 'merged': [PR], 'me': 自分の login, 'assignees': {番号: [login]}}（PR は bin の fetch_load_prs の形）
  assign: {番号: {'owner': 自分の作業のセッションの名前, 'order': 順（数値か None）}}（手元の控え）
  settings: {'deadline_label': …, 'deadline_date': …, 'deadline_open': 件数か None, 'mainline': …, 'mainline_label': …}
            （無い設定は '' で、その行・印を出さない）

失効: タスクの正本を GitHub Projects 以外へ移したとき。
"""
from __future__ import annotations

import re

import hirai_board

STAGE_SENTENCE = '進捗は申告でなく、PR と CI の実物から出しています（20 着手、50 draft、60 ready、70 CI 緑、90 merge 済み）。'
NO_OWNER_STATUSES = ('進行中', 'レビュー中')
HELD_STATUS = '保留'
CLOSED_SHOWN = 3  # 担当の行に出す、閉じた task の数（割り振りの順番の前のものから畳む）
DONE_STATUS = '完了'
CI_GREEN = ('SUCCESS',)
CI_RED = ('FAILURE', 'ERROR')


def one_line(text) -> str:
    return ' '.join(str(text or '').split())


def cell(text) -> str:
    """表のセルに入れる字（改行・制御文字を空白に、縦棒と角かっこを全角に、バッククォートを ' に。崩れと埋め込みを防ぐ）。"""
    plain = ''.join(c if c.isprintable() else ' ' for c in str(text or ''))
    return one_line(plain).replace('|', '｜').replace('<', '&lt;').replace('`', "'").replace('[', '［').replace(']', '］')


def ci_state(pr: dict) -> str:
    """PR の CI の状態（緑・赤・実行中・検査なし）。検査の無いリポは 検査なし（70 に上げない）。"""
    checks = (pr.get('checks') or '').upper()
    if checks in CI_GREEN:
        return '緑'
    if checks in CI_RED:
        return '赤'
    return '実行中' if checks else '検査なし'


def stage_of(number: int, ctx: dict) -> tuple[int, str, str]:
    """(率, 注, 止まりの印)。控えに無い（Project に載っていない・新しい）issue は 0% で、完了に数えない。
    止まりの印は、止まっている理由（CI 赤・衝突）。無ければ空。"""
    task = ctx['tasks'].get(number)
    if task is None:
        return 0, '控えに無い（新しい）', ''
    if task.get('state') == 'CLOSED':
        return 100, '完了', ''
    prs = ctx['prs_of'].get(number, [])
    if prs:
        best = max(prs, key=lambda p: (not p['draft'], p['number']))
        stuck = '衝突' if best.get('conflict') else ''
        tail = f'・{stuck}' if stuck else ''
        if best['draft']:
            return 50, f"PR #{best['number']} draft{tail}", stuck
        ci = ci_state(best)
        if ci == '赤':
            stuck = 'CI 赤' + ('・衝突' if stuck else '')
        return (70 if ci == '緑' else 60), f"PR #{best['number']} ready・CI {ci}{tail}", stuck
    if number in ctx['merged_of']:
        nums = '・'.join(f'#{n}' for n in ctx['merged_of'][number])
        return 90, f'PR {nums} merge 済み（issue が開いている）', ''
    status = task.get('status') or ''
    if status == DONE_STATUS:
        return 90, 'Status 完了（issue が開いている）', ''
    if status in NO_OWNER_STATUSES:
        return 20, f'{status}・PR なし', ''
    return 0, status or 'Status 未設定', ''


def _pr_index(prs: list, repo: str) -> dict:
    out: dict[int, list] = {}
    for pr in prs:
        for n in pr.get('closes') or []:
            out.setdefault(int(n), []).append(pr)
    return out


def section_name(model: dict, number: int) -> str:
    wave, _feat = hirai_board.locate(model, number)
    title = (model['by_number'].get(wave) or {}).get('title') if wave else ''
    return re.sub(r'^\d+\.\s+', '', one_line(title)) or '—'


def build(view: dict, prs: dict, assign: dict, settings: dict) -> dict:
    """表の材料（JSON にできる形）を組む。"""
    model = hirai_board.build(view)
    tasks = {i['number']: i for i in view['issues'] if hirai_board.is_task(i)}
    ctx = {'tasks': tasks, 'prs_of': _pr_index(prs['open'], view['repo']),
           'merged_of': {n: [p['number'] for p in ps] for n, ps in _pr_index(prs['merged'], view['repo']).items()}}
    sections = []
    for wave in model['waves']:
        rows = hirai_board.wave_tasks(model, wave['number'])
        if not rows:
            continue
        done = sum(1 for t in rows if not hirai_board.is_open(t))
        held = sum(1 for t in rows if hirai_board.is_open(t) and t.get('status') == HELD_STATUS)
        sections.append({'name': section_name(model, wave['number']), 'total': len(rows), 'done': done, 'held': held})
    total, done, held = (sum(s[k] for s in sections) for k in ('total', 'done', 'held'))
    me, assignees = prs.get('me') or '', prs.get('assignees') or {}
    named = dict(assign)
    others_of: dict[str, str] = {}
    for t in tasks.values():
        n = t['number']
        if n in named or not hirai_board.is_open(t) or t.get('status') not in NO_OWNER_STATUSES:
            continue
        people_of = [x for x in assignees.get(str(n), []) if x]
        if people_of and me not in people_of:
            others_of[n] = '・'.join(people_of)
            named[n] = {'owner': others_of[n], 'order': None}
    owners: dict[str, list[int]] = {}
    for n in sorted(named, key=lambda x: (x in others_of, named[x].get('order') is None, named[x].get('order') or 0, x)):
        owners.setdefault(named[n]['owner'], []).append(n)
    people = []
    for owner in sorted(owners, key=lambda o: (any(n in others_of for n in owners[o]),
                                               min((named[n].get('order') if named[n].get('order') is not None else 1e9)
                                                   for n in owners[o]), o)):
        entries = []
        for n in owners[owner]:
            pct, note, stuck = stage_of(n, ctx)
            mine = ctx['prs_of'].get(n, [])
            pr = max(mine, key=lambda p: (not p['draft'], p['number']))['number'] if mine else None
            entries.append({'number': n, 'pct': pct, 'note': note, 'pr': pr, 'stuck': stuck, 'section': section_name(model, n)})
        if all(x['pct'] == 100 for x in entries):
            continue  # 全部閉じた担当は、古い割り振りの控えが残っているだけ。出さない
        closed = [x for x in entries if x['pct'] == 100]
        folded = closed[:-CLOSED_SHOWN] if len(closed) > CLOSED_SHOWN else []
        entries = [x for x in entries if x not in folded]  # 閉じた行は新しいほうだけ（古いものは畳む）
        people.append({'owner': owner, 'tasks': entries})
    stray = [t['number'] for t in tasks.values()
             if hirai_board.is_open(t) and t.get('status') in NO_OWNER_STATUSES and t['number'] not in named]
    others = []
    for pr in prs['open']:
        author = pr.get('author') or ''
        if me and author and author != me:
            for n in pr.get('closes') or []:
                if int(n) not in named and int(n) in tasks and hirai_board.is_open(tasks[int(n)]):
                    others.append({'number': int(n), 'pr': pr['number'], 'author': author})
    others.sort(key=lambda o: (o['pr'], o['number']))
    other_numbers = {o['number'] for o in others}
    stray = [n for n in stray if n not in other_numbers]  # ほかの開発者の PR がある行は、担当の居ない行に出さない
    stuck_tasks = [{'number': t['number'], 'stuck': t['stuck']} for p in people for t in p['tasks'] if t['stuck']]
    stray_rows = [(n, stage_of(n, ctx)[2]) for n in sorted(stray)]  # 担当の無い行の CI 赤・衝突も止まりに出す
    stuck_tasks += [{'number': n, 'stuck': mark} for n, mark in stray_rows if mark]
    open_total = prs.get('open_total')
    return {'total': total, 'done': done, 'held': held, 'sections': sections, 'people': people,
            'stray': sorted(stray), 'others': others, 'stuck': stuck_tasks, 'settings': settings,
            'truncated': open_total if isinstance(open_total, int) and open_total > len(prs['open']) else 0,
            'unknown_assignees': prs.get('unknown_assignees') or 0,
            'signature': signature(people), 'fetched_at': view.get('fetched_at', ''), 'how': view.get('how', '')}


def signature(people: list) -> dict:
    """段・担当・順番の控え（--changed が前回と比べる）。"""
    out = {}
    for person in people:
        for i, t in enumerate(person['tasks']):
            out[str(t['number'])] = [t['pct'], person['owner'], i, t['stuck']]
    return out


def pct_of(done: int, total: int) -> int:
    return 100 * done // total if total > 0 else 0


def deadline_sentence(settings: dict) -> str:
    label = one_line(settings.get('deadline_label') or '')
    if not settings.get('deadline_date') or not label:
        return ''
    n = settings.get('deadline_open')
    if n is None:
        return f'{label}の件数は引けませんでした。'
    return f'{label}に要ると本文に書かれた task は、開いているものが {n} 件あります。'


def group_rows(entries: list) -> list[list[dict]]:
    """同じ PR の隣り合う task を 1 つにまとめ、セクションが変わる所で行を分ける。"""
    groups: list[dict] = []
    for e in entries:
        last = groups[-1] if groups else None
        if last and e['pr'] is not None and last['pr'] == e['pr'] and last['section'] == e['section']:
            last['numbers'].append(e['number'])
        else:
            groups.append({'numbers': [e['number']], 'pr': e['pr'], 'pct': e['pct'], 'section': e['section']})
    runs: list[list[dict]] = []
    for g in groups:
        if runs and runs[-1][0]['section'] == g['section']:
            runs[-1].append(g)
        else:
            runs.append([g])
    return runs


def render(model: dict) -> str:
    """4 部構成の Markdown（1 行目・セクションの表・進行中のタスクの表・実物と合っていない行）。"""
    total, done, held = model['total'], model['done'], model['held']
    s = model['settings']
    first = f"{done} / {total} 完了（{pct_of(done, total)}%）。"
    if held:
        first += f'保留の {held} 件を除くと {pct_of(done, total - held)}% です。'
    first += deadline_sentence(s)
    out = [first, '']
    mainline = s.get('mainline') or ''
    cells = [(x['name'] + (f"（{one_line(s.get('mainline_label') or '本線')}）" if mainline and mainline in x['name'] else ''),
              f"{pct_of(x['done'], x['total'])}%")
             for x in model['sections'] if x['done'] < x['total']]
    if cells:
        out += ['| セクション | 進み | セクション | 進み |', '|---|---|---|---|']
    half = (len(cells) + 1) // 2
    for i in range(half):
        right = cells[half + i] if half + i < len(cells) else ('', '')
        out.append(f'| {cell(cells[i][0])} | {cells[i][1]} | {cell(right[0])} | {right[1]} |')
    out += ['', '**進行中のタスク**', '', STAGE_SENTENCE, '', '| 担当 | セクション | 順番 | 進捗 |', '|---|---|---|---|']
    for person in model['people']:
        runs = group_rows(person['tasks'])
        for i, run in enumerate(runs):
            chain = ' → '.join('・'.join(f'#{n}' for n in g['numbers']) + (f"（PR #{g['pr']}）" if g['pr'] else '') for g in run)
            pcts = ' → '.join(f"{g['pct']}%" for g in run)
            out.append(f"| {cell(person['owner']) if i == 0 else ''} | {cell(run[0]['section'])} | {chain} | {pcts} |")
    if not model['people']:
        out.append('| — | — | 割り振りがありません | — |')
    if model['stuck']:
        out += ['', '止まっているもの: ' + ', '.join(f"#{t['number']}（{t['stuck']}）" for t in model['stuck'])]
    if model['stray']:
        out += ['', '進行中・レビュー中なのに担当の居ないもの: ' + ', '.join(f'#{n}' for n in model['stray'])]
    if model['others']:
        out += ['', 'ほかの開発者の PR: ' + ', '.join(f"#{o['number']}（PR #{o['pr']}・{cell(o['author'])}）" for o in model['others'])]
    if model['truncated']:
        out += ['', f"開いている PR が {model['truncated']} 本あり、新しいほうだけで数えています。"]
    if model['unknown_assignees']:
        out += ['', f"Assignees を見ていない 進行中・レビュー中 の task が {model['unknown_assignees']} 件あります。"]
    return '\n'.join(out) + '\n'


def changed(model: dict, previous: dict | None) -> bool:
    """前回の控えと比べて、どれかの段・担当・順番が動いたか（初回は控えが無いので True）。"""
    return (previous or {}).get('signature') != model['signature']
