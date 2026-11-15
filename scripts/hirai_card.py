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

会話では目印なし・太字なしの同じ行（to_plain）。行は `**ラベル**: 値`・`**ラベル:** 値`・`ラベル: 値`
（コロンは全角も可）のどれでも読む。1 行目は種類ごとに、決めることと同じ行に「推奨」（承認カード）・
「期限」（判断カード）を持つ（同じ行に 2 回出たら最後のもの）。

目印の位置: カードの目印（`<!-- card:… -->`・`<!-- /card -->`）は行頭（前の空白は可）にあるものだけを読み、
フェンス（``` / ~~~）の中と引用（`>`）の行は読まない。本文は `\n` だけで行に分ける（U+2028 などで割らない）。

字数の数え方（approval-template.md・smoke と同じ定義。line_lengths と total_length が数える）: 値はラベルと「: 」を
除いた部分を Python の len（コードポイント）で数える。2 行目からは 60 字まで。1 行目は行全体の値（「決めること」の文と
「。推奨: …」「。期限: …」を含む）で 80 字まで。カード全体は会話の形（ラベルと「: 」を含み、改行を除く）で 400 字まで。

型の決まり: 承認カードの推奨は 承認する／承認しない／条件つき（<条件の文>）で、条件つきは括弧の中が要る。
「承認すると」は「戻せる」か「戻せない」の語を含む。判断カードの選択肢と人の作業カードの手順は 3 つまで。
制御文字（Unicode の分類 C。\t を除く）と改行の文字（Zl・Zp）は値に入れてはいけない（問題として出し、表示から除く）。
"""
from __future__ import annotations

import re
import unicodedata

KINDS = {
    'approval': {'name': '承認カード', 'labels': ('決めること', '目的', '位置', '承認すると', 'しないと', '注意', '詳しく'),
                 'inline': '推奨'},
    'decision': {'name': '判断カード', 'labels': ('決めること', '目的', '選択肢', '推奨', '決めないと', '誰が決める', '詳しく'),
                 'inline': '期限'},
    'work': {'name': '人の作業カード', 'labels': ('やること', '誰が', '手順', '終わったら', 'これで動くもの'), 'inline': None},
}
RECOMMENDATIONS = ('承認する', '条件つき', '承認しない')
VALUE_MAX = 60
FIRST_LINE_MAX = 80
CARD_MAX = 400
END_MARK = '<!-- /card -->'
_START_RE = re.compile(r'^[ \t]*<!--\s*card:([A-Za-z]+)\s*-->[ \t\r]*$')
_END_RE = re.compile(r'^[ \t]*<!--\s*/card\s*-->[ \t\r]*$')
_FENCE_RE = re.compile(r'^[ \t]{0,3}(`{3,}|~{3,})')
# 未記入の印: `<…>` か、`<` の直後が空白・…・型の雛形に実際に出る語（approval-template.md の型と、この道具の雛形）。
# `Array<string>`・`<10 件>`・`<img …>` は未記入ではない。コードスパンの中は見ない。
_PLACEHOLDER_HEADS = ('…', '何を', '誰の', '誰が', '全体', '始まる', 'いちばん', 'リンク', '問い', 'YYYY', '止まる',
                      'A か', '理由', '人・', '手を', '分>', '日付', 'どこに', '件数', '条件', '承認する／', '1 行', '1 文',
                      '決まる', '額', '誰が', '計画の', '番号・', 'この判断', 'この提案')
_PLACEHOLDER_RE = re.compile(r'<(?:\s|' + '|'.join(re.escape(h) for h in _PLACEHOLDER_HEADS) + r')[^<>\n]*>|<分>')
_CODE_SPAN_RE = re.compile(r'`[^`\n]*`')
_DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')


def _has_placeholder(value: str) -> bool:
    return bool(_PLACEHOLDER_RE.search(_CODE_SPAN_RE.sub('', value or '')))


def _invisible(ch: str) -> bool:
    """値に入れてはいけない文字: 制御文字（分類 C。\\t と、絵文字をつなぐ ZWJ を除く）と改行の文字（Zl・Zp）。"""
    category = unicodedata.category(ch)
    return (category.startswith('C') and ch not in ('\t', '\u200d')) or category in ('Zl', 'Zp')


def visible(text: str) -> str:
    """端末・会話に出す前に、入れてはいけない文字を除く（ESC などを端末に出さない）。"""
    return ''.join(ch for ch in (text or '') if ch == '\n' or not _invisible(ch))


def start_mark(kind: str) -> str:
    return f'<!-- card:{kind} -->'


def _label_re(label: str) -> re.Pattern:
    # `**ラベル**: 値`・`**ラベル:** 値`（コロンが太字の内側）・`ラベル: 値`。太字の閉じ（コロンの後の **）は値に入れない。
    return re.compile(rf'^[ \t]*(?:\*\*)?{re.escape(label)}(?:\*\*)?[ \t]*[:：](?:\*\*(?=\s|$))?[ \t]*(.*?)\s*$')


def _split_inline(value: str, inline: str) -> tuple[str, str | None]:
    """1 行目の「決めること」から、同じ行の推奨・期限を切り出す（無ければ None）。決めることの文に同じ語が
    出ることがあるので、最後の「推奨:」（「期限:」）で切る。"""
    matches = list(re.finditer(rf'(?:\*\*)?{re.escape(inline)}(?:\*\*)?[ \t]*[:：](?:\*\*(?=\s|$))?[ \t]*', value))
    if not matches:
        return value.strip(), None
    match = matches[-1]
    return value[:match.start()].strip().rstrip('。'), value[match.end():].strip()


def _fence_flags(lines: list[str]) -> list[bool]:
    """行ごとに「フェンスの中（開き・閉じの行を含む）」か。閉じは開きと同じ記号で、同じ長さ以上。"""
    flags, opener = [], None
    for line in lines:
        match = _FENCE_RE.match(line)
        if opener is None:
            if match:
                opener = match.group(1)
            flags.append(opener is not None)
            continue
        flags.append(True)
        if match and match.group(1)[0] == opener[0] and len(match.group(1)) >= len(opener) \
                and not line.strip().lstrip(opener[0]):
            opener = None
    return flags


def find_blocks(body: str) -> tuple[list[dict], list[str]]:
    """本文の中のカードの塊（種類・中の行）と、目印の形の問題を返す。"""
    blocks, problems = [], []
    lines = [line.rstrip('\r') for line in (body or '').split('\n')]
    fenced = _fence_flags(lines)
    i = 0
    while i < len(lines):
        start = None if fenced[i] else _START_RE.match(lines[i])
        if start is None:
            if not fenced[i] and _END_RE.match(lines[i]):
                problems.append(f'{i + 1} 行目に終わりの目印 {END_MARK} だけがある（始まりの <!-- card:… --> が無い）')
            i += 1
            continue
        kind = start.group(1)
        end = next((j for j in range(i + 1, len(lines))
                    if not fenced[j] and (_END_RE.match(lines[j]) or _START_RE.match(lines[j]))), None)
        if end is None or _START_RE.match(lines[end]):
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
            problems.append(f'ラベルの無い行・知らないラベル: {visible(raw.strip())[:30]}')
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
        elif _has_placeholder(inline):
            problems.append(f'「{spec["inline"]}」が <…> のまま')
        elif card['kind'] == 'approval' and normalize_recommendation(inline) is None:
            problems.append(f'推奨は {"・".join(RECOMMENDATIONS)} のどれか（今「{visible(inline)[:20]}」）')
        elif card['kind'] == 'approval' and normalize_recommendation(inline) == '条件つき' \
                and not re.match(r'^条件つき[（(]\s*[^）)\s][^）)]*[）)]', inline.strip()):
            problems.append('条件つきは括弧の中に条件の文を書く（例: 条件つき（2026-11-30 までに戻せる形で））')
        elif card['kind'] == 'decision' and not (_DATE_RE.search(inline) or inline.startswith('未定')):
            problems.append('期限は YYYY-MM-DD か「未定（〜が決まり次第）」で書く')
    texts = list(card['fields'].items()) + ([(spec['inline'], card['inline'])] if spec['inline'] and card.get('inline') else [])
    for label, value in texts:
        if any(_invisible(ch) for ch in value):
            problems.append(f'「{label}」に制御文字か改行の文字がある（見えない文字を消す）')
        if value.startswith('**') and value.count('**') % 2:
            problems.append(f'「{label}」の値の先頭に閉じていない ** がある（ラベルの太字の閉じる位置を直す）')
    for label, value in card['fields'].items():
        if not value.strip():
            problems.append(f'「{label}」が空')
        elif _has_placeholder(value):
            problems.append(f'「{label}」が <…> のまま')
    for label, length in line_lengths(card):
        limit = FIRST_LINE_MAX if label == first else VALUE_MAX
        if length > limit:
            problems.append(f'「{label}」の行が {length} 字（{limit} 字まで。超えるなら詳しい版へ）')
    fields = card['fields']
    if card['kind'] == 'approval' and fields.get('承認すると') and not re.search('戻せ(?:る|ない)', fields['承認すると']):
        problems.append('「承認すると」に「戻せる」か「戻せない」を書く')
    if card['kind'] == 'decision' and len([x for x in re.split('[／/]', fields.get('選択肢') or '') if x.strip()]) > 3:
        problems.append('選択肢は 3 つまで（それ以上は「推奨の 1 つ」と「それ以外」に分ける）')
    if card['kind'] == 'work' and len(re.findall(r'(?:^|\s)\d+\.', fields.get('手順') or '')) > 3:
        problems.append('手順は 3 つまで（それ以上はリンク先の手順書へ）')
    total = total_length(card)
    if total > CARD_MAX:
        problems.append(f'カード全体が {total} 字（{CARD_MAX} 字まで）')
    return problems


def line_lengths(card: dict) -> list[tuple[str, int]]:
    """行ごとの (ラベル, 字数)。字数は会話の形の値（ラベルと「: 」を除く）の len。1 行目は推奨・期限を含む行全体の値。"""
    out = []
    for line in _plain_lines(card).split('\n'):
        label, _sep, value = line.partition(': ')
        out.append((label, len(value)))
    return out


def total_length(card: dict) -> int:
    """カード全体の字数（会話の形。ラベルと「: 」を含み、改行を除く）。"""
    return len(_plain_lines(card).replace('\n', ''))


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
    """会話の形（目印なし・太字なし）。入れてはいけない文字は除く（端末に ESC などを出さない）。"""
    return visible(_plain_lines(card))


def _plain_lines(card: dict) -> str:
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
承認すると: AI が2画面を直し、変更1本で出す。戻せる
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
    t('60 字を超える値は問題', any('「目的」の行が 61 字' in p for p in problems), str(problems))
    for rec, ok in (('条件つき（2026-11-30 まで）', True), ('条件つき', False), ('条件つき（）', False)):
        _c, problems = read_card(_body_of('\n'.join([lines[0].replace('承認しない', rec)] + lines[1:]), 'approval'), 'approval')
        t(f'推奨「{rec}」は{"通る" if ok else "問題（括弧の中の条件が要る）"}', (not problems) == ok, str(problems))
    no_undo = [x if not x.startswith('承認すると') else '承認すると: AI が2画面を直す' for x in lines]
    _c, problems = read_card(_body_of('\n'.join(no_undo), 'approval'), 'approval')
    t('「承認すると」に戻せる・戻せないが無ければ問題', any('戻せる' in p for p in problems), str(problems))
    bad_rec = lines[0].replace('承認しない', '今は始めない')
    _c, problems = read_card(_body_of('\n'.join([bad_rec] + lines[1:]), 'approval'), 'approval')
    t('推奨は 3 つの選択肢のどれか', any('推奨は' in p for p in problems), str(problems))
    t('推奨を項目の選択肢に揃える', [normalize_recommendation(x) for x in ('承認する', '条件つき（11/30 まで）', '承認しない', '保留')]
      == ['承認する', '条件つき', '承認しない', None])
    decision = ('決めること: 退会した人のチャットを何日残すか。期限: 未定（法務の確認が済み次第）\n目的: 漏れたときの害を小さくする\n'
                '選択肢: A 30日（害が小さい・問い合わせに足りないことがある） ／ B 1年\n'
                '推奨: A — 害が小さい\n決めないと: 退会の作業3件が止まる\n誰が決める: 事業の責任者\n詳しく: #207')
    card, problems = read_card(_body_of(decision, 'decision'), 'decision')
    t('判断カードの期限は「未定」でも通る', card and not problems, str(problems))
    _c, problems = read_card(_body_of(decision.replace('期限: 未定（法務の確認が済み次第）', '期限: 来月'), 'decision'), 'decision')
    t('判断カードの期限は日付か未定', any('期限は' in p for p in problems), str(problems))
    _c, problems = read_card(_body_of(decision.replace('／ B 1年', '／ B 1年 ／ C 3年 ／ D 消さない'), 'decision'), 'decision')
    t('選択肢は 3 つまで', any('選択肢は 3 つまで' in p for p in problems), str(problems))
    work = ('やること: 本番のLINE公式アカウントを申し込む（所要20分・期限2026-11-30）\n誰が: 事業の責任者\n'
            '手順: 1. 管理画面で作る 2. 会社情報を入れる 3. 審査に出す\n終わったら: IDを #697 に貼る\nこれで動くもの: 本番の通知（2件）')
    card, problems = read_card(_body_of(work, 'work'), 'work')
    t('人の作業カード（誰が・手順 3 つ）は通る', card and not problems, str(problems))
    _c, problems = read_card(_body_of(work.replace('3. 審査に出す', '3. 審査に出す 4. 待つ'), 'work'), 'work')
    t('手順は 3 つまで', any('手順は 3 つまで' in p for p in problems), str(problems))
    _c, problems = read_card(_body_of(_EXAMPLE_729, 'approval'), 'decision')
    t('種類が違えば「判断カードが無い（あるのは承認カード）」', any('判断カードが無い（あるのは承認カード' in p for p in problems),
      str(problems))
    # カードの目印は行頭だけ・フェンスの中は読まない（説明文の引用・写しを本物と取り違えない）
    real = _body_of(_EXAMPLE_729.replace('承認しない', '承認する'), 'approval')
    _c, problems = read_card('説明で `<!-- card:approval -->` と書く\n' + real, 'approval')
    t('説明文の中の目印（行頭でない）は読まない', not problems, str(problems))
    fenced = '前の例:\n```\n' + _body_of(_EXAMPLE_729, 'approval') + '\n```\n'
    card, problems = read_card(fenced + real, 'approval')
    t('フェンスの中の写しは読まず、本物だけを読む', card and card['inline'] == '承認する' and not problems, str(problems))
    _c, problems = read_card(fenced, 'approval')
    t('フェンスの中だけなら「承認カードが無い」', problems == ['承認カードが無い'], str(problems))
    _c, problems = read_card('> ' + _body_of(_EXAMPLE_729, 'approval').replace('\n', '\n> '), 'approval')
    t('引用（>）の中のカードは読まない', problems == ['承認カードが無い'], str(problems))
    # コロンが太字の内側（**目的:** 値）
    bold_in = '\n'.join(['**決めること:** 始めるか。**推奨:** 承認する'] + [
        f'**{line.split(": ", 1)[0]}:** {line.split(": ", 1)[1]}' for line in lines[1:]])
    card, problems = read_card(_body_of(bold_in, 'approval'), 'approval')
    t('コロンが太字の内側でも値に ** を残さない', card and headline(card) == ('始めるか', '承認する')
      and not card['fields']['目的'].startswith('*') and not problems, str(card and card['fields']) + str(problems))
    _c, problems = read_card(_body_of('\n'.join([lines[0], '目的: ** 太字の閉じ忘れ'] + lines[2:]), 'approval'), 'approval')
    t('値の先頭に閉じていない ** が残る形は問題', any('**' in p for p in problems), str(problems))
    # 未記入（<…>）の見分け
    for text in ('Array<string> を渡す', '値が <10 件> のとき', '<img src=x> を出す', '`<…>` と書く'):
        _c, problems = read_card(_body_of('\n'.join(lines[:5] + ['注意: ' + text] + lines[6:]), 'approval'), 'approval')
        t(f'未記入と取り違えない: {text}', not problems, str(problems))
    for text in ('<…>', '<何を・どうするか、を 1 文>', '< 未記入 >'):
        _c, problems = read_card(_body_of('\n'.join(lines[:5] + ['注意: ' + text] + lines[6:]), 'approval'), 'approval')
        t(f'未記入を見つける: {text}', any('<…> のまま' in p for p in problems), str(problems))
    # 制御文字・改行の文字
    card, problems = read_card(_body_of('\n'.join([lines[0] + '\x1b[31m'] + lines[1:]), 'approval'), 'approval')
    t('制御文字（ESC）は問題にし、会話の形に出さない', any('制御文字' in p for p in problems)
      and card and '\x1b' not in to_plain(card) and not any('\x1b' in p for p in problems), repr(problems))
    card, problems = read_card(_body_of('\n'.join([lines[0], '目的: 前\u2028後'] + lines[2:]), 'approval'), 'approval')
    t('値の中の改行の文字（U+2028）は行を割らず問題にする', card and '後' in card['fields']['目的']
      and any('制御文字' in p for p in problems), repr(problems))
    # 1 行目 80 字・全体 400 字の境界
    for n, ok in ((71, True), (72, False)):
        line = '決めること: ' + 'あ' * n + '。推奨: 承認する'
        card, problems = read_card(_body_of('\n'.join([line] + lines[1:]), 'approval'), 'approval')
        t(f'1 行目は行全体の値（「。推奨: 承認する」を含む）{n + 9} 字で{"通る" if ok else "問題"}',
          (not problems) == ok and card and line_lengths(card)[0] == ('決めること', n + 9), str(problems))
    for total, ok in ((400, True), (401, False)):  # 値で書く（定数を使うと上限を変えても検査が通ってしまう）
        card = {'kind': 'approval', 'inline': '承認する', 'fields': {lb: 'い' for lb in KINDS['approval']['labels']}}
        card['fields']['承認すると'] = '戻せる'
        short = len(to_plain(card).replace('\n', ''))
        need, labels = total - short, list(KINDS['approval']['labels'])[1:]
        for lb in labels:
            add = min(need, VALUE_MAX - len(card['fields'][lb]))
            card['fields'][lb] += 'う' * add
            need -= add
        built = len(to_plain(card).replace('\n', ''))
        t(f'全体 {total} 字で{"通る" if ok else "問題"}（作った字数 {built}）', built == total and (not check(card)) == ok,
          str(check(card)))
    # 決めることの中の「推奨:」は 1 行目の推奨と取り違えない（最後の「推奨:」で切る）
    card, problems = read_card(_body_of('\n'.join(['決めること: 推奨: 案Aを始めるか。推奨: 承認する'] + lines[1:]), 'approval'),
                               'approval')
    t('決めることの中の「推奨:」は最後のものを 1 行目の推奨とみなす', card and headline(card) == ('推奨: 案Aを始めるか', '承認する')
      and not problems, str(problems))
    if template_text is not None:
        blocks = re.findall(r'```\n(.*?)\n```', template_text, re.DOTALL)
        holes = [h for b in blocks if b.split('\n', 1)[0].startswith(('決めること', 'やること'))
                 for h in re.findall(r'<[^<>\n]+>', b)]
        missed = [h for h in holes if not _has_placeholder(h)]
        t('正本の型の <…> はすべて未記入として見つける', holes and not missed, str(missed))
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
