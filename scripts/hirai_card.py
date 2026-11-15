#!/usr/bin/env python3
"""
hirai_card.py — 承認カード・判断カード・人の作業カードを、issue の本文から取り出して形を確かめる。

正本は docs/rules-reference/approval-template.md。ここはその「形の決まり」を機械で確かめるだけで、
GitHub にもネットワークにも出ない（標準ライブラリだけ）。bin/hirai-task の card・board・new が使う。

issue の本文では目印で囲み、ラベルを太字にする:

    <!-- card:approval -->
    **決めること**: <1 文>。**推奨**: 承認する
    **目的**: …
    …
    <!-- /card -->

会話では目印なし・太字なしの同じ行（to_plain）。行は `**ラベル**: 値` と `ラベル: 値` のどちらでも読む。
1 行目は種類ごとに、決めることと同じ行に「推奨」（承認カード）・「期限」（判断カード）を持つ。

数え方: 字数は文字（コードポイント）で数える。値は 1 行 60 字まで（ラベルを除く。1 行目は同じ行の
推奨・期限と合わせて 80 字まで）、カード全体は会話の形（to_plain）の改行を除いた字数で 400 字まで。
"""
from __future__ import annotations

import re

KINDS = {
    'approval': {'name': '承認カード', 'labels': ('決めること', '目的', '位置', '承認すると', 'しないと', '注意', '詳しく'),
                 'inline': '推奨'},
    'decision': {'name': '判断カード', 'labels': ('決めること', '選択肢', '推奨', '決めないと', '誰が決める', '詳しく'),
                 'inline': '期限'},
    'work': {'name': '人の作業カード', 'labels': ('やること', '手順', '終わったら', 'これで動くもの'), 'inline': None},
}
RECOMMENDATIONS = ('承認する', '条件つき', '承認しない')
VALUE_MAX = 60
FIRST_LINE_MAX = 80
CARD_MAX = 400
END_MARK = '<!-- /card -->'
_START_RE = re.compile(r'<!--\s*card:([A-Za-z]+)\s*-->')
_END_RE = re.compile(r'<!--\s*/card\s*-->')
_PLACEHOLDER_RE = re.compile(r'<[^<>\n]*>')
_DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')


def start_mark(kind: str) -> str:
    return f'<!-- card:{kind} -->'


def _label_re(label: str) -> re.Pattern:
    return re.compile(rf'^\s*(?:\*\*)?{re.escape(label)}(?:\*\*)?\s*[:：]\s*(.*?)\s*$')


def _split_inline(value: str, inline: str) -> tuple[str, str | None]:
    """1 行目の「決めること」から、同じ行の推奨・期限を切り出す（無ければ None）。"""
    match = re.search(rf'(?:\*\*)?{re.escape(inline)}(?:\*\*)?\s*[:：]\s*', value)
    if not match:
        return value.strip(), None
    return value[:match.start()].strip().rstrip('。'), value[match.end():].strip()


def find_blocks(body: str) -> tuple[list[dict], list[str]]:
    """本文の中のカードの塊（種類・中の行）と、目印の形の問題を返す。"""
    blocks, problems = [], []
    lines = (body or '').splitlines()
    i = 0
    while i < len(lines):
        start = _START_RE.search(lines[i])
        if start is None:
            if _END_RE.search(lines[i]):
                problems.append(f'{i + 1} 行目に終わりの目印 {END_MARK} だけがある（始まりの <!-- card:… --> が無い）')
            i += 1
            continue
        kind = start.group(1)
        end = next((j for j in range(i + 1, len(lines)) if _END_RE.search(lines[j]) or _START_RE.search(lines[j])), None)
        if end is None or _START_RE.search(lines[end]):
            problems.append(f'{KINDS.get(kind, {}).get("name", kind)}の終わりの目印 {END_MARK} が無い')
            i = end if end is not None else len(lines)
            continue
        blocks.append({'kind': kind, 'lines': lines[i + 1:end]})
        i = end + 1
    return blocks, problems


def parse_block(kind: str, lines: list[str]) -> tuple[dict, list[str]]:
    """塊の行をラベル → 値に読む。順序・欠け・知らない行は問題として返す。"""
    spec = KINDS[kind]
    fields: dict[str, str] = {}
    problems: list[str] = []
    order: list[str] = []
    for raw in lines:
        if not raw.strip():
            continue
        label = next((lb for lb in spec['labels'] if _label_re(lb).match(raw)), None)
        if label is None:
            problems.append(f'ラベルの無い行・知らないラベル: {raw.strip()[:30]}')
            continue
        if label in fields:
            problems.append(f'「{label}」が 2 回ある')
            continue
        fields[label] = _label_re(label).match(raw).group(1)
        order.append(label)
    inline = None
    first = spec['labels'][0]
    if spec['inline'] and first in fields:
        fields[first], inline = _split_inline(fields[first], spec['inline'])
    missing = [lb for lb in spec['labels'] if lb not in fields]
    if missing:
        problems.append('欠けている行: ' + '・'.join(missing))
    expected = [lb for lb in spec['labels'] if lb in fields]
    if order != expected:
        problems.append('行の順が違う（正: ' + '→'.join(spec['labels']) + '）')
    card = {'kind': kind, 'fields': fields, 'inline': inline}
    return card, problems + check(card)


def check(card: dict) -> list[str]:
    """値の中身の決まり（空・<…> のまま・字数・推奨と期限の形）を確かめる。"""
    spec = KINDS[card['kind']]
    problems = []
    first = spec['labels'][0]
    if spec['inline']:
        inline = card.get('inline')
        if inline is None or not inline.strip():
            problems.append(f'1 行目に「{spec["inline"]}」が無い（{first}と同じ行に書く）')
        elif _PLACEHOLDER_RE.search(inline):
            problems.append(f'「{spec["inline"]}」が <…> のまま')
        elif card['kind'] == 'approval' and normalize_recommendation(inline) is None:
            problems.append(f'推奨は {"・".join(RECOMMENDATIONS)} のどれか（今「{inline[:20]}」）')
        elif card['kind'] == 'decision' and not (_DATE_RE.search(inline) or inline.startswith('未定')):
            problems.append('期限は YYYY-MM-DD か「未定（〜が決まり次第）」で書く')
    for label, value in card['fields'].items():
        if not value.strip():
            problems.append(f'「{label}」が空')
        elif _PLACEHOLDER_RE.search(value):
            problems.append(f'「{label}」が <…> のまま')
        limit, length = VALUE_MAX, len(value)
        if label == first:
            limit, length = FIRST_LINE_MAX, length + len(card.get('inline') or '')
        if length > limit:
            problems.append(f'「{label}」が {length} 字（{limit} 字まで。超えるなら詳しい版へ）')
    total = len(to_plain(card).replace('\n', ''))
    if total > CARD_MAX:
        problems.append(f'カード全体が {total} 字（{CARD_MAX} 字まで）')
    return problems


def read_card(body: str, kind: str | None = None) -> tuple[dict | None, list[str]]:
    """本文から kind のカードを 1 枚読む（kind が None なら、あるカードのうち最初の 1 枚）。
    返り値: (カード か None, 問題の一覧)。問題が空なら形は正しい。"""
    blocks, problems = find_blocks(body)
    wanted = [b for b in blocks if kind is None or b['kind'] == kind]
    unknown = [b['kind'] for b in blocks if b['kind'] not in KINDS]
    problems += [f'知らない種類のカード: card:{k}' for k in unknown]
    wanted = [b for b in wanted if b['kind'] in KINDS]
    if not wanted:
        others = sorted({KINDS[b['kind']]['name'] for b in blocks if b['kind'] in KINDS})
        name = KINDS[kind]['name'] if kind else 'カード'
        hint = f'（あるのは{"・".join(others)}。この行に要るのは{name}）' if others else ''
        return None, problems + [f'{name}が無い{hint}']
    if len(wanted) > 1:
        problems.append(f'{KINDS[wanted[0]["kind"]]["name"]}が {len(wanted)} 枚ある（1 枚にする）')
    card, card_problems = parse_block(wanted[0]['kind'], wanted[0]['lines'])
    return card, problems + card_problems


def normalize_recommendation(text: str | None) -> str | None:
    """承認カードの推奨を、項目「推奨」の選択肢（承認する・条件つき・承認しない）に揃える。"""
    text = (text or '').strip()
    if text.startswith('承認しない'):
        return '承認しない'
    if text.startswith('条件つき'):
        return '条件つき'
    if text.startswith('承認する'):
        return '承認する'
    return None


def headline(card: dict) -> tuple[str, str]:
    """1 行目の「決めること（やること）」と、同じ行の推奨・期限（判断カードは推奨の行）。"""
    first = KINDS[card['kind']]['labels'][0]
    if card['kind'] == 'decision':
        return card['fields'].get(first, ''), card['fields'].get('推奨', '')
    return card['fields'].get(first, ''), card.get('inline') or ''


def to_plain(card: dict) -> str:
    """会話の形（目印なし・太字なし）。"""
    spec = KINDS[card['kind']]
    lines = []
    for i, label in enumerate(spec['labels']):
        if label not in card['fields']:
            continue
        value = card['fields'][label]
        if i == 0 and spec['inline'] and card.get('inline') is not None:
            value = f"{value.rstrip('。')}。{spec['inline']}: {card['inline']}"
        lines.append(f'{label}: {value}')
    return '\n'.join(lines)


def to_body(kind: str, fields: dict[str, str], inline: str | None = None) -> str:
    """issue の本文の形（目印つき・太字のラベル）。無い値は <…> にする（雛形）。"""
    spec = KINDS[kind]
    lines = [start_mark(kind)]
    for i, label in enumerate(spec['labels']):
        value = (fields.get(label) or '').strip() or '<…>'
        if i == 0 and spec['inline']:
            value = f"{value.rstrip('。')}。**{spec['inline']}**: {(inline or '').strip() or '<…>'}"
        lines.append(f'**{label}**: {value}')
    return '\n'.join(lines + [END_MARK])


def skeleton(kind: str, fields: dict[str, str] | None = None, inline: str | None = None) -> str:
    return to_body(kind, fields or {}, inline)


def has_card(body: str, kind: str) -> bool:
    return any(b['kind'] == kind for b in find_blocks(body)[0])


# ── 自己検査（gh を使わない） ─────────────────────────────────────────
_EXAMPLE_729 = """決めること: 入居者向け画面2つの見た目直しを、今始めるか。推奨: 承認しない
目的: 入居者が担当者を探して選ぶ画面を、デザインの原本どおりにそろえる
位置: 公開（14段目）へ向けた段のうち4段目「画面の見本」の残り2件
承認すると: AI が2画面を直し、変更1本で出す。サーバーとデータは触らない
しないと: 2画面は今のまま。4段目が閉じない
注意: 同じ画面は11月に直し済みで、やり直すと崩すおそれ（推測）
詳しく: #729（作業 #82・#83）"""


def _body_of(plain: str, kind: str) -> str:
    return '前の文\n\n' + start_mark(kind) + '\n' + plain + '\n' + END_MARK + '\n\n後ろの文'


def selftest(template_text: str | None = None) -> list[tuple[str, bool, str]]:
    """(名前, 通ったか, 詳細) の一覧。template_text を渡すと、正本の記入例がすべて通るかも見る。"""
    out = []

    def t(name, ok, detail=''):
        out.append((name, bool(ok), detail))

    card, problems = read_card(_body_of(_EXAMPLE_729, 'approval'), 'approval')
    t('太字なしの承認カードを読み、形の問題が無い', card and not problems, str(problems))
    t('1 行目から推奨を切り出す', card and headline(card) == ('入居者向け画面2つの見た目直しを、今始めるか', '承認しない'),
      str(card and headline(card)))
    bold = to_body('approval', card['fields'], card['inline']) if card else ''
    again, problems = read_card('x\n' + bold, 'approval')
    t('本文の形（太字・目印）に書いて読み直すと同じ', again == card and not problems, str(problems))
    t('会話の形に戻すと元の行と同じ', card and to_plain(card) == _EXAMPLE_729, to_plain(card) if card else '')
    _none, problems = read_card('本文だけ', 'approval')
    t('カードが無ければ「承認カードが無い」', problems == ['承認カードが無い'], str(problems))
    _c, problems = read_card(start_mark('approval') + '\n' + _EXAMPLE_729, 'approval')
    t('終わりの目印が無ければ問題', any('終わりの目印' in p for p in problems), str(problems))
    _c, problems = read_card(_EXAMPLE_729 + '\n' + END_MARK, 'approval')
    t('終わりの目印だけなら問題（カードも無い）', any('だけがある' in p for p in problems) and any('無い' in p for p in problems),
      str(problems))
    two = _body_of(_EXAMPLE_729, 'approval') + '\n' + _body_of(_EXAMPLE_729, 'approval')
    _c, problems = read_card(two, 'approval')
    t('同じ種類のカードが 2 枚なら問題', any('2 枚' in p for p in problems), str(problems))
    lines = _EXAMPLE_729.splitlines()
    _c, problems = read_card(_body_of('\n'.join(lines[:2] + lines[3:]), 'approval'), 'approval')
    t('欠けた行を名指しする', any('欠けている行: 位置' in p for p in problems), str(problems))
    _c, problems = read_card(_body_of('\n'.join([lines[0], lines[2], lines[1]] + lines[3:]), 'approval'), 'approval')
    t('順の違いを見つける', any('順が違う' in p for p in problems), str(problems))
    _c, problems = read_card(skeleton('approval'), 'approval')
    t('雛形のまま（<…>）は問題', any('<…> のまま' in p for p in problems) and any('推奨' in p for p in problems),
      str(problems))
    long_line = '目的: ' + 'あ' * 61
    _c, problems = read_card(_body_of('\n'.join([lines[0], long_line] + lines[2:]), 'approval'), 'approval')
    t('60 字を超える値は問題', any('「目的」が 61 字' in p for p in problems), str(problems))
    bad_rec = lines[0].replace('承認しない', '今は始めない')
    _c, problems = read_card(_body_of('\n'.join([bad_rec] + lines[1:]), 'approval'), 'approval')
    t('推奨は 3 つの選択肢のどれか', any('推奨は' in p for p in problems), str(problems))
    t('推奨を項目の選択肢に揃える', [normalize_recommendation(x) for x in ('承認する', '条件つき（11/30 まで）', '承認しない', '保留')]
      == ['承認する', '条件つき', '承認しない', None])
    decision = ('決めること: 退会した人のチャットを何日残すか。期限: 未定\n選択肢: A 30日 ／ B 1年\n'
                '推奨: A — 害が小さい\n決めないと: 退会の作業3件が止まる\n誰が決める: 事業の責任者\n詳しく: #207')
    card, problems = read_card(_body_of(decision, 'decision'), 'decision')
    t('判断カードの期限は「未定」でも通る', card and not problems, str(problems))
    _c, problems = read_card(_body_of(decision.replace('期限: 未定', '期限: 来月'), 'decision'), 'decision')
    t('判断カードの期限は日付か未定', any('期限は' in p for p in problems), str(problems))
    _c, problems = read_card(_body_of(_EXAMPLE_729, 'approval'), 'decision')
    t('種類が違えば「判断カードが無い（あるのは承認カード）」', any('判断カードが無い（あるのは承認カード' in p for p in problems),
      str(problems))
    if template_text is not None:
        examples = re.findall(r'```\n(.*?)\n```', template_text, re.DOTALL)
        firsts = {'決めること': None, 'やること': 'work'}
        checked = 0
        for ex in examples:
            head = ex.split('\n', 1)[0]
            if not head.startswith(tuple(firsts)) or '<' in ex:
                continue
            kind = 'work' if head.startswith('やること') else 'decision' if '期限:' in head else 'approval'
            card, problems = read_card(_body_of(ex, kind), kind)
            t(f'正本の記入例（{KINDS[kind]["name"]}: {head[:20]}…）は形の問題が無い', card and not problems, str(problems))
            checked += 1
        t('正本の記入例を 1 枚以上見た', checked >= 3, str(checked))
    return out
