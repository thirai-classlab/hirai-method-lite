#!/usr/bin/env python3
"""
hirai_task_selftest.py — bin/hirai-task の自己検査（`hirai-task --selftest` が呼ぶ）。

gh を実行しない。`gh_task.run_gh` を差し替えて、偽の GraphQL・REST の応答を返す。
検査の前後で、控えの置き場所（field の id・align の基準・journal など）を一時
ディレクトリへ差し替え、実際の作業ツリー・git ディレクトリに触れない。

見るもの:
  1. 偽の 800 行（8 頁）で ready が全件を読む（items(first:100) の頁送りが 1 頁で
     止まらないこと）
  2. 偽の PR 行と feature 行（種別）が一覧に出ない。task_items() だけでなく、
     cmd_ready・cmd_pending・cmd_blocked の実際の出力で見る
  3. PR の番号でも show が落ちない。
     PR にも Projects の Status が出ること・Projects に載っていない番号は show が
     落ちること（exit 1 の理由付き）も見る
  4. ready の警告 3 種（未完了の blocked by・閉じたのに完了でない・レビュー中なのに
     open の PR が無い）は、出る入力と出ない入力を 1 つずつ見る
  5. discover_project_number の環境変数（HIRAI_TASK_PROJECT）は selftest の外に漏れない
  6. 既存の行への書き込み（set・start・done・reopen・review・add 後の値・
     align）は REST（`?q=#<番号>` で item id を引く → PATCH）で行い、GraphQL の
     `updateProjectV2ItemFieldValue` を呼ばない。`rest_item_id`
     の 0 件（Project に居ない）・2 件以上（repo: で絞る・それでも複数なら候補を
     出す）の扱いも見る
  7. 書き込みのあとの件数の取り直し（refresh_board_counts）と `line` は、このプラグインの
     scripts/ghp-path.sh を偽物に差し替えて見る（書いたときだけ呼ぶ・失敗しても結果を
     変えない）。gh は呼ばない

落ちる条件: 検査が 1 件でも FAIL → exit 1
失効: タスクの正本を GitHub Projects 以外へ移したとき。
"""
from __future__ import annotations

import datetime
import io
import json
import os
import re
import sys

# 利用者の手元にも、プラグインの置き場所にも .pyc（__pycache__）を作らない。
# 以降の import（自己検査・bin/hirai-task の読み込み）にも効かせるため import の直後に置く。
sys.dont_write_bytecode = True
import tempfile
import urllib.parse
from contextlib import redirect_stdout
from importlib import machinery, util


def _base_plugin_root() -> str:
    """土台（hirai-lite）のルート。approval-template.md と templates/draft.md を読むために探す。
    HIRAI_LITE_ROOT > このリポの配置（plugins/hirai-project-method の 2 つ上）> installed_plugins.json の
    entry `hirai-lite`。見つからなければ AssertionError（検査を飛ばさず落とす）。"""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    marker = os.path.join('docs', 'rules-reference', 'approval-template.md')
    candidates = [os.environ.get('HIRAI_LITE_ROOT', '').strip(), os.path.dirname(os.path.dirname(here))]
    try:
        with open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'), encoding='utf-8') as f:
            entries = json.load(f).get('plugins', {}).get('hirai-lite@hirai-lite', [])
        # 版が最大の行を先にする（古い 1.x の行が先に並んでいても、その approval-template.md を読まない）。
        # 「-」から後ろ（commit の接尾。3.0.2-8713c5b11005 など）は落としてから比べる。
        entries = sorted(entries, key=lambda e: [int(n) if n.isdigit() else 0
                                                 for n in re.split(r'[.]', str(e.get('version', '0')).split('-', 1)[0])],
                         reverse=True)
        candidates += [e.get('installPath', '') for e in entries]
    except (OSError, ValueError, AttributeError):
        pass
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, marker)):
            return c
    raise AssertionError(f'土台（hirai-lite）が見つからない: HIRAI_LITE_ROOT を指す（候補: {candidates}）')


def _load_tool():
    """bin/hirai-task（拡張子なし）を `gh_task` という名前のモジュールとして読む。"""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin', 'hirai-task')
    loader = machinery.SourceFileLoader('gh_task', path)
    spec = util.spec_from_loader('gh_task', loader)
    module = util.module_from_spec(spec)
    sys.modules['gh_task'] = module
    loader.exec_module(module)
    # 検査は呼び出し元のリポに依らない（git remote が無くても、別のリポでも同じ結果）。
    module.REPO = 'example-org/example-repo'
    module.OWNER, _, module.REPO_NAME = module.REPO.partition('/')
    return module


gh_task = _load_tool()


def _extract_flag(args: list[str], name: str) -> str | None:
    prefix = f'{name}='
    prev = None
    for a in args:
        if prev in ('-f', '-F') and a.startswith(prefix):
            return a[len(prefix):]
        prev = a
    return None


def _fake_row(
    number: int, *, status: str = '', kind: str = '', state: str = 'OPEN',
    typename: str = 'Issue', title: str | None = None, parent_number: int | None = None,
    order: float | None = None,
) -> dict:
    field_values = []
    if order is not None:
        field_values.append({
            '__typename': 'ProjectV2ItemFieldNumberValue', 'number': order,
            'field': {'name': gh_task.ORDER_FIELD},
        })
    if status:
        field_values.append({
            '__typename': 'ProjectV2ItemFieldSingleSelectValue', 'name': status,
            'field': {'name': 'Status'},
        })
    if kind:
        field_values.append({
            '__typename': 'ProjectV2ItemFieldSingleSelectValue', 'name': kind,
            'field': {'name': gh_task.KIND_FIELD},
        })
    return {
        'id': f'ITEM_{number}',
        'content': {
            '__typename': typename,
            'number': number,
            'title': title or f'row {number}',
            'state': state,
            'url': '',
            'parent': {'number': parent_number} if parent_number is not None else None,
        },
        'fieldValues': {'nodes': field_values},
    }


def _discovery_response(project_number: int = 7) -> tuple[int, str, str]:
    body = {
        'data': {
            'repository': {
                'projectsV2': {
                    'nodes': [
                        {'number': project_number, 'title': 'サンプルのプロジェクト',
                         'fields': {'nodes': [{'name': gh_task.KIND_FIELD}]}},
                    ]
                }
            }
        }
    }
    return 0, json.dumps(body), ''


PAGINATED_FEATURE = 80000


def make_paginated_gh(total_items: int, page_size: int = 100, *, extra_pr=0, extra_feature=0):
    """items(first:100) を頁送りで返す偽 gh。ready の頁送りが 1 頁で止まらないことを見る。
    fetch_extras（alias `i0:` ...）にも空の結果で答えるので、cmd_ready を直接 main(['ready'])
    で走らせて確かめられる（task_items() だけでなく実際の出力を見る）。"""

    def fake_run_gh(args: list[str]) -> tuple[int, str, str]:
        joined = ' '.join(args)
        if 'rateLimit' in joined:
            return 0, json.dumps({'data': {'rateLimit': {'remaining': 4321}}}), ''
        if re.search(r'\bi0:', joined):
            numbers = [int(n) for n in re.findall(r'issue\(number:\s*(\d+)\)', joined)]
            data = {
                f'i{i}': {
                    'issue': {
                        'number': number,
                        'blockedBy': {'totalCount': 0, 'nodes': []},
                        'closedByPullRequestsReferences': {'nodes': []},
                    }
                }
                for i, number in enumerate(numbers)
            }
            return 0, json.dumps({'data': data}), ''
        if 'projectsV2' in joined:
            return _discovery_response()
        if 'items(first:' in joined:
            after = _extract_flag(args, 'after')
            offset = int(after) if after else 0
            nodes = []
            for i in range(offset, min(offset + page_size, total_items)):
                nodes.append(_fake_row(i + 1, status='着手可', kind='task', parent_number=PAGINATED_FEATURE))
            # 最終頁にだけ、親の feature（着手可）と混ぜ物（PR・種別 feature）を足す
            # 。
            if offset + page_size >= total_items:
                nodes.append(_fake_row(PAGINATED_FEATURE, status='着手可', kind='feature'))
                for j in range(extra_pr):
                    nodes.append(_fake_row(90000 + j, status='承認待ち', typename='PullRequest'))
                for j in range(extra_feature):
                    nodes.append(_fake_row(91000 + j, status='承認待ち', kind='feature'))
            has_next = (offset + page_size) < total_items
            end_cursor = str(offset + page_size) if has_next else None
            body = {
                'data': {
                    'repository': {
                        'projectV2': {
                            'items': {
                                'pageInfo': {'hasNextPage': has_next, 'endCursor': end_cursor},
                                'nodes': nodes,
                            }
                        }
                    }
                }
            }
            return 0, json.dumps(body), ''
        return 1, '', f'unhandled fake gh call: {joined[:120]}'

    return fake_run_gh


def make_board_gh(rows: list[dict], extras: dict[int, dict] | None = None, *, project_number: int = 7):
    """discover + items(頁送り) + fetch_extras の 3 種の問い合わせすべてに答える偽 gh。
    cmd_ready・cmd_pending・cmd_blocked を実際に走らせて出力を見る検査に使う
    （task_items() だけを見ない）。

    extras の値は {number: {'blockers': [(番号, state), ...], 'blocked_by_total': N,
    'open_pr_numbers': [番号, ...]}}。
    """
    extras = extras or {}

    def fake_run_gh(args: list[str]) -> tuple[int, str, str]:
        joined = ' '.join(args)
        if 'rateLimit' in joined:
            return 0, json.dumps({'data': {'rateLimit': {'remaining': 4321}}}), ''
        if re.search(r'\bi0:', joined):
            numbers = [int(n) for n in re.findall(r'issue\(number:\s*(\d+)\)', joined)]
            data: dict[str, dict] = {}
            for i, number in enumerate(numbers):
                extra = extras.get(number, {})
                blockers = extra.get('blockers', [])
                total = extra.get('blocked_by_total', len(blockers))
                open_prs = extra.get('open_pr_numbers', [])
                data[f'i{i}'] = {
                    'issue': {
                        'number': number,
                        'blockedBy': {
                            'totalCount': total,
                            # (番号, 状態) か (番号, 状態, 'owner/repo')。repo は本物の応答と同じく repository.nameWithOwner に載る
            'nodes': [
                {'number': b[0], 'state': b[1],
                 'repository': {'nameWithOwner': b[2] if len(b) > 2 else gh_task.REPO}}
                for b in blockers
            ],
                        },
                        'closedByPullRequestsReferences': {
                            'nodes': [{'number': n, 'state': 'OPEN'} for n in open_prs],
                        },
                    }
                }
            return 0, json.dumps({'data': data}), ''
        if 'projectsV2' in joined:
            return _discovery_response(project_number)
        if 'items(first:' in joined:
            after = _extract_flag(args, 'after')
            offset = int(after) if after else 0
            page = rows[offset:offset + 100]
            has_next = offset + 100 < len(rows)
            end_cursor = str(offset + 100) if has_next else None
            body = {
                'data': {
                    'repository': {
                        'projectV2': {
                            'items': {
                                'pageInfo': {'hasNextPage': has_next, 'endCursor': end_cursor},
                                'nodes': page,
                            }
                        }
                    }
                }
            }
            return 0, json.dumps(body), ''
        return 1, '', f'unhandled fake gh call: {joined[:160]}'

    return fake_run_gh


def make_show_gh(*, as_pr: bool, number: int, linked: bool = True, status: str = '完了'):
    def fake_run_gh(args: list[str]) -> tuple[int, str, str]:
        joined = ' '.join(args)
        if 'projectsV2' in joined:
            return _discovery_response()
        if 'issueOrPullRequest' in joined:
            project_items = {'nodes': []}
            if linked:
                project_items = {'nodes': [{
                    'project': {'number': 7},
                    'fieldValues': {'nodes': [
                        {'__typename': 'ProjectV2ItemFieldSingleSelectValue', 'name': status,
                         'field': {'name': 'Status'}},
                    ]},
                }]}
            if as_pr:
                node = {
                    '__typename': 'PullRequest',
                    'number': number,
                    'title': 'fake pr',
                    'state': 'OPEN',
                    'url': 'https://example.invalid/pr',
                    'projectItems': project_items,
                }
            else:
                node = {
                    '__typename': 'Issue',
                    'number': number,
                    'title': 'fake issue',
                    'state': 'OPEN',
                    'url': 'https://example.invalid/issue',
                    'parent': None,
                    'blockedBy': {'totalCount': 0, 'nodes': []},
                    'projectItems': project_items,
                }
            body = {'data': {'repository': {'issueOrPullRequest': node}}}
            return 0, json.dumps(body), ''
        return 1, '', f'unhandled fake gh call: {joined[:120]}'

    return fake_run_gh


def make_erroring_gh(message: str = 'boom'):
    def fake_run_gh(args: list[str]) -> tuple[int, str, str]:
        return 1, '', message

    return fake_run_gh


# ═════════════════════════════════════════════════════════════════════
# 書く側（new / add / approve / set / start / review / done / reopen）
# の検査。gh_task.run_gh を差し替える点は上と同じ。
# ═════════════════════════════════════════════════════════════════════

_STATUS_OPTIONS = (
    '承認待ち', '判断待ち', '依存待ち', '着手可', '進行中', 'レビュー中', '完了', '保留',
)
_KIND_OPTIONS = ('wave', 'feature', 'task', '設計メモ')
# 古い 6 軸の項目（stream・wave・gate・deps_before・blocked_by_decision・trace）は、
# 偽の Project にも持たせない（この道具はそれらを読まず・書かない）。


def _fake_field_defs(*, include_kind: bool = True) -> list[dict]:
    defs = [
        {'id': 'F_Status', 'name': 'Status',
         'options': [{'id': f'O_Status_{o}', 'name': o} for o in _STATUS_OPTIONS]},
    ]
    if include_kind:
        defs.append({
            'id': f'F_{gh_task.KIND_FIELD}', 'name': gh_task.KIND_FIELD,
            'options': [{'id': f'O_kind_{o}', 'name': o} for o in _KIND_OPTIONS],
        })
    return defs


_SINGLE_SELECT_KEY_TO_FIELD = {'status': 'Status', 'kind': gh_task.KIND_FIELD}


def _write_item_body(
    *, found: bool = True, title: str = 'task', body: str = '', state: str = 'OPEN',
    parent_number: int | None = None, blockers: list[tuple[int, str]] | None = None,
    project_number: int = 7, **field_kwargs,
) -> dict:
    if not found:
        return {'data': {'repository': {'issue': None}}}
    field_values = []
    for key, field_name in _SINGLE_SELECT_KEY_TO_FIELD.items():
        value = field_kwargs.get(key)
        if value:
            field_values.append({
                '__typename': 'ProjectV2ItemFieldSingleSelectValue', 'name': value,
                'field': {'name': field_name},
            })
    blockers = blockers or []
    issue = {
        'title': title,
        'body': body,
        'state': state,
        'parent': {'number': parent_number} if parent_number is not None else None,
        'blockedBy': {
            'totalCount': len(blockers),
            # (番号, 状態) か (番号, 状態, 'owner/repo')。repo は本物の応答と同じく repository.nameWithOwner に載る
            'nodes': [
                {'number': b[0], 'state': b[1],
                 'repository': {'nameWithOwner': b[2] if len(b) > 2 else gh_task.REPO}}
                for b in blockers
            ],
        },
        'projectItems': {'nodes': [{
            'id': f'ITEM_{title}',
            'project': {'number': project_number},
            'fieldValues': {'nodes': field_values},
        }]},
    }
    return {'data': {'repository': {'issue': issue}}}


def _fake_rest_field_defs(field_defs: list[dict]) -> list[dict]:
    """REST の GET .../fields の偽の答え。field の id は整数（9000+n）、option の id は
    'R_' 始まりで、GraphQL 側（F_...・O_...）とは別の形にする。書き込みが GraphQL の id を
    PATCH に渡す取り違えを、偽の PATCH が 422 相当で落として捕まえるため。"""
    out = []
    for i, d in enumerate(field_defs):
        out.append({
            'id': 9000 + i, 'name': d['name'],
            # 本番の実物の形（2026-09-29 実測）: 選択肢の name は {html, raw} の dict
            'options': [{'id': f"R_{o['id']}", 'color': 'GRAY',
                         'description': {'html': '', 'raw': ''},
                         'name': {'html': o['name'], 'raw': o['name']}} for o in d.get('options', [])],
        })
    return out


def _rest_patch_to_graphql_ids(field_defs: list[dict], fields: list[dict]) -> list[tuple] | None:
    """PATCH の fields[].id / value が REST の id なら、記録用に GraphQL の id へ戻す。
    REST の id でなければ None（偽の PATCH は失敗を返す）。"""
    by_rest = {9000 + i: d for i, d in enumerate(field_defs)}
    out = []
    for f in fields:
        d = by_rest.get(f['id'])
        if d is None:
            return None
        value = f['value']
        if d.get('options'):
            back = {f"R_{o['id']}": o['id'] for o in d['options']}
            if value not in back:
                return None
            value = back[value]
        out.append((d['id'], value))
    return out


def _reset_rest_fields_cache() -> None:
    """REST の field id のキャッシュ（gh-fields-rest.json）を case 間で持ち越さない。"""
    try:
        os.remove(gh_task.REST_FIELDS_CACHE)
    except OSError:
        pass


def _fake_rest_project_call(
    method, path, body, item_specs, field_defs, rest_items, record, rest_log,
):
    """Project の REST（items の ?q=・fields・PATCH items/<id>）の偽の答え。
    対象外の path は None（呼び出し側が rest_handler へ回す）。"""
    m = re.match(r'^(?:orgs|users)/[^/]+/projectsV2/\d+/(items|fields)(?:/(\d+))?(?:\?(.*))?$', path)
    if not m:
        return None
    kind, item_id, query = m.group(1), m.group(2), m.group(3) or ''
    if rest_log is not None:
        rest_log.append((method, path))
    if kind == 'fields' and method == 'GET':
        return _fake_rest_field_defs(field_defs)
    if kind == 'items' and method == 'GET':
        q = re.search(r'(?:^|&)q=([^&]*)', query)
        if not q:
            return None
        num = re.search(r'#(\d+)', urllib.parse.unquote(q.group(1)))
        if not num:
            return []
        number = int(num.group(1))
        if rest_items is not None and number in rest_items:
            got = rest_items[number]
            return got(urllib.parse.unquote(q.group(1))) if callable(got) else got
        if number in item_specs:
            return [{'id': 1000 + number, 'content': {'number': number}}]
        return []
    if kind == 'items' and method == 'PATCH' and item_id:
        converted = _rest_patch_to_graphql_ids(field_defs, (body or {}).get('fields', []))
        if converted is None:
            return None  # REST の id でない（GraphQL の id を渡した）→ 失敗させる
        if record is not None:
            record.extend(converted)
        return {}
    return None


def make_write_gh(
    item_specs: dict[int, dict], *, field_defs: list[dict] | None = None,
    record: list[tuple[str, str]] | None = None,
    rest_handler=None, project_number: int = 7, owner_typename: str = 'Organization',
    rest_items: dict[int, list[dict]] | None = None, rest_log: list[tuple] | None = None,
    graphql_writes: list[tuple] | None = None, strict_missing: bool = False,
):
    """approve/set/start/done/reopen/add/new の 1 件引き・field-list・
    updateProjectV2ItemFieldValue・REST を検査する偽 gh。
    item_specs: {issue番号: _write_item_body へ渡す kwargs}。
    record: 書き込みを (field id, option id または text) で追記する list。
    rest_handler(method, path, body) -> レスポンス dict（None なら未対応として失敗）。
    owner_typename: repositoryOwner.__typename の偽の答え（'Organization'/'User'。
    project_items_rest_path が orgs/・users/ を切り替えるための問い合わせ）。"""
    field_defs = field_defs if field_defs is not None else _fake_field_defs()
    # 前の case が書いたキャッシュ（gh_task.FIELDS_CACHE）を持ち越さない。
    # 持ち越すと、この case の field_defs（例: include_kind=False）を無視して
    # 前の case の種別つきキャッシュを読み、種別を書かない検査が汚染される
    # （実装前に確認済みの穴。テストは壊して確かめる・core.md）。
    try:
        os.remove(gh_task.FIELDS_CACHE)
    except OSError:
        pass
    # owner_type() のキャッシュも同じ理由で持ち越さない。
    gh_task._owner_type_cache = None
    _reset_rest_fields_cache()

    def fake_run_gh(args: list[str], input_text: str | None = None) -> tuple[int, str, str]:
        joined = ' '.join(args)
        if '--paginate' in args:
            page_path = args[args.index('--paginate') + 1]
            if re.search(r'projectsV2/\d+/fields', page_path):
                if rest_log is not None:
                    rest_log.append(('GET', page_path))
                return 0, json.dumps(_fake_rest_field_defs(field_defs)), ''
        if 'repositoryOwner' in joined:
            body = {'data': {'repositoryOwner': {'__typename': owner_typename}}}
            return 0, json.dumps(body), ''
        if 'project field-list' in joined:
            return 0, json.dumps({'fields': field_defs}), ''
        if 'projectV2(number:$projectNumber) { id }' in joined:
            return 0, json.dumps({'data': {'repository': {'projectV2': {'id': 'PVT_FAKE'}}}}), ''
        if 'clearProjectV2ItemFieldValue' in joined:
            fid = _extract_flag(args, 'field')
            if graphql_writes is not None:
                graphql_writes.append((fid, None))
            if record is not None:
                record.append((fid, None))
            return 0, json.dumps({
                'data': {'clearProjectV2ItemFieldValue': {'projectV2Item': {'id': 'ITEM_FAKE'}}},
            }), ''
        if 'updateProjectV2ItemFieldValue' in joined:
            # $item が変数に乗らなければ（値が None で graphql() が黙って落とした場合）、
            # 本番の GitHub と同じくエラーにする（H1 の再発防止。write_single_select/
            # write_text_field 自身の item_id 検査で通常はここに来ないが、防御を重ねる）。
            item_val = _extract_flag(args, 'item')
            if item_val is None:
                return 1, '', 'Variable $item of type ID! was provided invalid value'
            fid = _extract_flag(args, 'field')
            opt = _extract_flag(args, 'optionId')
            text = _extract_flag(args, 'text')
            if graphql_writes is not None:
                graphql_writes.append((fid, opt if opt is not None else text))
            if record is not None:
                record.append((fid, opt if opt is not None else text))
            return 0, json.dumps({
                'data': {'updateProjectV2ItemFieldValue': {'projectV2Item': {'id': 'ITEM_FAKE'}}},
            }), ''
        if 'issue(number:$number) {' in joined:
            number_raw = _extract_flag(args, 'number')
            number = int(number_raw) if number_raw is not None else None
            spec = item_specs.get(number)
            if spec is None:
                if strict_missing:
                    # 本物の形（2026-11 実測の型）: この repo の issue として引けない番号（PR・存在しない番号）は
                    # data.repository.issue=null に errors（NOT_FOUND）がつき、gh は exit 1 で返す。
                    return 1, json.dumps({
                        'data': {'repository': {'issue': None}},
                        'errors': [{'type': 'NOT_FOUND', 'path': ['repository', 'issue'],
                                    'message': f'Could not resolve to an Issue with the number of {number}.'}],
                    }), ''
                return 0, json.dumps(_write_item_body(found=False)), ''
            return 0, json.dumps(_write_item_body(project_number=project_number, **spec)), ''
        # REST（`rest()` の呼び出し）は必ず ['api', '-X', method, path, ...] の形なので、
        # discover の 'projectsV2' 判定より先に見る。REST のパス自体に
        # 'orgs/.../projectsV2/7/items' のような文字列 projectsV2 を含むことがあり、
        # 順番を逆にすると discover の判定に誤って吸われる（実装前に確認済みの穴・
        # broke_to_confirm）。
        if len(args) >= 2 and args[0] == 'api' and args[1] == '-X':
            method, path = args[2], args[3]
            body = json.loads(input_text) if input_text else None
            builtin = _fake_rest_project_call(
                method, path, body, item_specs, field_defs, rest_items, record, rest_log,
            )
            if builtin is not None:
                return 0, json.dumps(builtin), ''
            if rest_handler is not None:
                result = rest_handler(method, path, body)
                if result is not None:
                    return 0, json.dumps(result), ''
            return 1, '', f'unhandled REST call: {method} {path}'
        if 'projectsV2' in joined:
            return _discovery_response(project_number)
        return 1, '', f'unhandled fake gh call: {joined[:160]}'

    return fake_run_gh


# ═════════════════════════════════════════════════════════════════════
# ── 会話の最初と merge の直後の仕事の検査が使う偽 gh ──────────
# comments / close-parents / align / unblocked / today / after-merge を main([...])
# 経由で実際に走らせて確かめる。頁送りは 1 頁で返す（頁送り自体は別の case で
# 見ている）。
# ═════════════════════════════════════════════════════════════════════
def _command_row(i: dict) -> dict:
    field_values = []
    if i.get('status'):
        field_values.append({
            '__typename': 'ProjectV2ItemFieldSingleSelectValue', 'name': i['status'],
            'field': {'name': 'Status'},
        })
    if i.get('kind'):
        field_values.append({
            '__typename': 'ProjectV2ItemFieldSingleSelectValue', 'name': i['kind'],
            'field': {'name': gh_task.KIND_FIELD},
        })
    if i.get('headline'):
        field_values.append({'__typename': 'ProjectV2ItemFieldTextValue', 'text': i['headline'],
                             'field': {'name': gh_task.CARD_HEADLINE_FIELD}})
    if i.get('recommend'):
        field_values.append({'__typename': 'ProjectV2ItemFieldSingleSelectValue', 'name': i['recommend'],
                             'field': {'name': gh_task.CARD_RECOMMEND_FIELD}})
    return {
        'id': f"ITEM_{i['number']}",
        'content': {
            '__typename': i.get('type', 'Issue'), 'number': i['number'],
            'title': i.get('title', f"row {i['number']}"), 'state': i.get('state', 'OPEN'),
            # 本物の形: url は issue の URL（別 repo の行は i['url'] で渡す）。
            'url': i.get('url') or f"https://github.com/{gh_task.REPO}/issues/{i['number']}",
            'parent': ({'number': i['parent_number']} if i.get('parent_number') is not None else None),
        },
        'fieldValues': {'nodes': field_values},
    }


def make_command_gh(
    items: list[dict], *, bodies: dict[int, str] | None = None,
    summaries: dict[int, dict] | None = None, extras: dict[int, dict] | None = None,
    closing_refs: dict[int, list[int]] | None = None, project_number: int = 7,
    write_log: list[tuple] | None = None, paginate: dict[str, list] | None = None,
    children: dict[int, list[dict]] | None = None, field_defs: list[dict] | None = None,
    graphql_log: list[str] | None = None,
):
    """close-parents・align・unblocked・after-merge・today を main([...]) 経由で走らせる
    ための、まとまった偽 gh。write_log には、実際に書き込みが起きたときだけ 1 行ずつ積む
    （GraphQL の更新は ('graphql-update', field_id, option_id_or_text)、REST の項目の値の
    更新は ('item-update', field_id, value)、それ以外の REST は
    (method, path, body) の 3 要素）。paginate は `--paginate` の応答を、path に含まれる
    部分文字列で切り分ける（comments・repo_only_issue_numbers・merged-designs のテストが
    使う。既定はどれも []）。children は `issues/{親}/sub_issues` の応答（各要素 state・
    state_reason）で、無ければ summaries の total・completed から completed で閉じた子を並べる。"""
    bodies = bodies or {}
    summaries = summaries or {}
    children = children or {}
    extras = extras or {}
    closing_refs = closing_refs or {}
    paginate = paginate or {}
    field_defs = field_defs if field_defs is not None else _fake_field_defs()
    # 同じ番号が別 repo の行にもあるとき、番号で引く偽の答え（issue・REST の item）はこの repo の行だけにする。
    items_by_number = {
        i['number']: i for i in items
        if not i.get('url') or i['url'].startswith(f'https://github.com/{gh_task.REPO}/')
    }
    _reset_rest_fields_cache()
    gh_task._owner_type_cache = None

    def fake_run_gh(args: list[str], input_text: str | None = None) -> tuple[int, str, str]:
        joined = ' '.join(args)
        if graphql_log is not None and args[:2] == ['api', 'graphql']:
            graphql_log.append(joined)
        if 'repositoryOwner' in joined:
            return 0, json.dumps({'data': {'repositoryOwner': {'__typename': 'Organization'}}}), ''
        if '--paginate' in args:
            idx = args.index('--paginate')
            path = args[idx + 1] if len(args) > idx + 1 else ''
            sub_match = re.search(r'/issues/(\d+)/sub_issues$', path)
            if sub_match:
                parent = int(sub_match.group(1))
                if parent in children:
                    return 0, json.dumps(children[parent]), ''
                summary = summaries.get(parent, {'total': 0, 'completed': 0})
                total, completed = summary.get('total', 0), summary.get('completed', 0)
                return 0, json.dumps([
                    {'number': parent * 100 + k, 'state': 'closed' if k < completed else 'open',
                     'state_reason': 'completed' if k < completed else None}
                    for k in range(total)
                ]), ''
            if re.search(r'projectsV2/\d+/fields', path):
                return 0, json.dumps(_fake_rest_field_defs(field_defs)), ''
            for key, value in paginate.items():
                if key in path:
                    return 0, json.dumps(value), ''
            return 0, json.dumps([]), ''
        if 'rateLimit' in joined:
            return 0, json.dumps({'data': {'rateLimit': {'remaining': 4321}}}), ''
        if 'pullRequest(number:' in joined:
            number = int(_extract_flag(args, 'number'))
            nodes = [{'number': n} for n in closing_refs.get(number, [])]
            return 0, json.dumps({
                'data': {'repository': {'pullRequest': {
                    'closingIssuesReferences': {'nodes': nodes},
                }}},
            }), ''
        if re.search(r'\bi\d+:', joined) and 'issue(number:' in joined:
            numbers = [int(n) for n in re.findall(r'issue\(number:\s*(\d+)\)', joined)]
            if 'blockedBy' in joined:
                data = {}
                for i, number in enumerate(numbers):
                    blocker_numbers = (extras.get(number) or {}).get('blocked_by_open_numbers', [])
                    closed_numbers = (extras.get(number) or {}).get('blocked_by_closed_numbers', [])
                    data[f'i{i}'] = {
                        'issue': {
                            'number': number,
                            'blockedBy': {
                                'totalCount': len(blocker_numbers) + len(closed_numbers),
                                'nodes': (
                                    [{'number': n, 'state': 'OPEN'} for n in blocker_numbers]
                                    + [{'number': n, 'state': 'CLOSED'} for n in closed_numbers]
                                ),
                            },
                            'closedByPullRequestsReferences': {'nodes': []},
                        },
                    }
                return 0, json.dumps({'data': data}), ''
            data = {
                f'i{i}': {'issue': {'number': n, 'body': bodies.get(n, '')}}
                for i, n in enumerate(numbers)
            }
            return 0, json.dumps({'data': data}), ''
        if 'items(first:' in joined:
            nodes = [_command_row(i) for i in items]
            body = {'data': {'repository': {'projectV2': {
                'items': {'pageInfo': {'hasNextPage': False, 'endCursor': None}, 'nodes': nodes},
            }}}}
            return 0, json.dumps(body), ''
        if 'projectV2(number:$projectNumber) { id }' in joined:
            return 0, json.dumps({'data': {'repository': {'projectV2': {'id': 'PVT_FAKE'}}}}), ''
        if 'updateProjectV2ItemFieldValue' in joined:
            fid = _extract_flag(args, 'field')
            opt = _extract_flag(args, 'optionId')
            text = _extract_flag(args, 'text')
            if write_log is not None:
                write_log.append(('graphql-update', fid, opt if opt is not None else text))
            return 0, json.dumps({
                'data': {'updateProjectV2ItemFieldValue': {'projectV2Item': {'id': 'ITEM_FAKE'}}},
            }), ''
        if 'issue(number:$number) {' in joined:
            number_raw = _extract_flag(args, 'number')
            number = int(number_raw) if number_raw is not None else None
            item = items_by_number.get(number)
            if item is None:
                return 0, json.dumps(_write_item_body(found=False)), ''
            return 0, json.dumps(_write_item_body(
                project_number=project_number, title=item.get('title', ''),
                body=bodies.get(number, ''),
                state=item.get('state', 'OPEN'), parent_number=item.get('parent_number'),
                status=item.get('status', ''), kind=item.get('kind', ''),
                blockers=(
                    [(n, 'OPEN') for n in (extras.get(number) or {}).get('blocked_by_open_numbers', [])]
                    + [(n, 'CLOSED') for n in (extras.get(number) or {}).get('blocked_by_closed_numbers', [])]
                ),
            )), ''
        if 'project field-list' in joined:
            return 0, json.dumps({'fields': field_defs}), ''
        if len(args) >= 2 and args[0] == 'api' and args[1] == '-X':
            method, path = args[2], args[3]
            body = json.loads(input_text) if input_text else None
            builtin = _fake_rest_project_call(
                method, path, body, items_by_number, field_defs, None, None, None,
            )
            if builtin is not None:
                if method == 'PATCH' and write_log is not None:
                    for fid_back, value_back in _rest_patch_to_graphql_ids(
                        field_defs, (body or {}).get('fields', []),
                    ) or []:
                        write_log.append(('item-update', fid_back, value_back))
                return 0, json.dumps(builtin), ''
            m = re.match(r'^repos/[^/]+/[^/]+/issues/(\d+)$', path)
            if method == 'GET' and m:
                number = int(m.group(1))
                row = items_by_number.get(number) or {}
                return 0, json.dumps({
                    'number': number, 'state': str(row.get('state', 'OPEN')).lower(),
                    'sub_issues_summary': summaries.get(number, {'total': 0, 'completed': 0}),
                }), ''
            if write_log is not None:
                write_log.append((method, path, body))
            return 0, json.dumps({}), ''
        if 'projectsV2' in joined:
            return _discovery_response(project_number)
        return 1, '', f'unhandled fake gh call (command): {joined[:160]}'

    return fake_run_gh


def make_new_board_gh(
    item_specs: dict[int, dict], board_rows: list[dict], bodies: dict[int, str], *,
    rest_handler=None, record: list | None = None,
):
    """new が wave を作るとき（wave の本文の節を読むため、Project の全件と wave の本文を
    引く）用の偽 gh。書き込み側は make_write_gh に任せ、items(first:) と本文の alias
    問い合わせだけをここで答える。"""
    base = make_write_gh(item_specs, record=record, rest_handler=rest_handler)

    def fake_run_gh(args: list[str], input_text: str | None = None) -> tuple[int, str, str]:
        joined = ' '.join(args)
        if 'items(first:' in joined:
            nodes = [_fake_row(**row) for row in board_rows]
            body = {'data': {'repository': {'projectV2': {
                'items': {'pageInfo': {'hasNextPage': False, 'endCursor': None}, 'nodes': nodes},
            }}}}
            return 0, json.dumps(body), ''
        if re.search(r'\bi0:', joined) and 'issue(number:' in joined and 'blockedBy' not in joined:
            numbers = [int(n) for n in re.findall(r'issue\(number:\s*(\d+)\)', joined)]
            data = {
                f'i{i}': {'issue': {'number': n, 'body': bodies.get(n, '')}}
                for i, n in enumerate(numbers)
            }
            return 0, json.dumps({'data': data}), ''
        return base(args, input_text)

    return fake_run_gh


# ── board（全体像のコンソール）の検査 ───────────────────────────
_BOARD_URL = 'https://github.com/example-org/example-repo/issues/{}'
_BOARD_XSS_TITLE = '<script>alert(1)</script>'


def _board_rows() -> list[dict]:
    """wave 4（うち 2 本は循環）・feature 3・task 15（種別なし 1 を含む）・PR 1 の偽の板。
    期待する件数は _board_checks の EXPECTED_SUMMARY に書く。"""
    def row(number, kind, status='', parent=None, title=None, state='OPEN', url=None, typename='Issue'):
        return {'number': number, 'kind': kind, 'status': status, 'parent_number': parent,
                'title': title or f'row {number}', 'state': state, 'type': typename,
                'url': _BOARD_URL.format(number) if url is None else url}
    return [
        row(1, 'wave', '完了', title='W1 はじまり'),
        row(2, 'wave', '着手可', title='W2 つづき'),
        row(3, 'wave', '承認待ち', title='W3 循環の片方'),
        row(4, 'wave', '承認待ち', title='W4 循環のもう片方'),
        row(10, 'feature', '完了', 1, 'F1 済み', state='CLOSED'),
        row(11, 'task', '完了', 10, state='CLOSED'),
        row(12, 'task', '完了', 10, state='CLOSED'),
        row(20, 'feature', '着手可', 2, 'F2 進める'),
        row(21, 'feature', '承認待ち', 2, 'F3 承認待ち'),
        row(30, 'task', '着手可', 20, 'T30 着手できる'),
        row(31, 'task', '着手可', 20, 'T31 自分が止められている'),
        row(32, 'task', '着手可', 20, '[User] T32 申込'),
        row(33, 'task', '進行中', 20),
        row(34, 'task', 'レビュー中', 20),
        row(35, 'task', '依存待ち', 20, 'T35 feature をまたいで待つ'),
        row(36, 'task', '判断待ち', 20),
        row(37, 'task', '保留', 20, 'T37 Project 外を待つ'),
        row(70, 'task', '進行中', 20, 'T70 閉じたのに完了でない', state='CLOSED'),
        row(40, 'task', '承認待ち', 21, _BOARD_XSS_TITLE, url='javascript:alert(1)'),
        row(41, 'task', '着手可', 21, 'T41 親が承認待ち'),
        row(52, 'task', '', 21, 'T52 Status 未設定'),
        row(50, 'task', '着手可', None, 'T50 親なし'),
        row(51, '', '承認待ち', None, 'T51 種別なし'),
        row(60, '', '', None, 'PR 60', typename='PullRequest'),
    ]


# 番号 → [(blocker, state)]
_BOARD_BLOCKERS = {2: [(1, 'OPEN')], 3: [(4, 'OPEN')], 4: [(3, 'OPEN')],
                   31: [(33, 'OPEN')], 35: [(40, 'OPEN')], 37: [(999, 'OPEN')], 12: [(11, 'CLOSED')]}
_BOARD_CARD_21 = ('<!-- card:approval -->\n**決めること**: 画面をそろえる作業を始めるか。**推奨**: 承認する\n'
                  '**目的**: 入居者が迷わず担当者を選べる\n**位置**: 段「つづき」の残り3件\n'
                  '**承認すると**: AI が画面を2つ直す。戻せる\n**しないと**: 画面は今のまま\n'
                  '**注意**: 同じ画面の直しと重なるおそれ（推測）\n**詳しく**: #21\n<!-- /card -->\n\n<!-- ai -->\n')
_BOARD_BODIES = {1: '- 出る条件のコマンド: exit 0（2026-11-01・abc1234）', 21: _BOARD_CARD_21}


def make_console_gh(calls: list, *, mode: str = 'ok', blockers: dict | None = None, issues: dict | None = None):
    """board が引く 4 種（discover・items・blockedBy の束・本文の束）に答える偽 gh。
    呼ばれた引数を calls に積む（2 回目に gh を叩いていないことを数で見る）。
    mode: ok / fail（exit 1）/ errors（errors 入りの JSON）/ truncated（blockedBy の totalCount > nodes）。
    issues は --publish が読み書きする issue（REST の GET・PATCH。PATCH は body を書き換える。無い番号は 404）。"""
    rows = _board_rows()
    blockers = _BOARD_BLOCKERS if blockers is None else blockers

    def node_of(r: dict) -> dict:
        values = [{'__typename': 'ProjectV2ItemFieldSingleSelectValue', 'name': v, 'field': {'name': f}}
                  for f, v in (('Status', r['status']), (gh_task.KIND_FIELD, r['kind'])) if v]
        return {'id': f"ITEM_{r['number']}", 'fieldValues': {'nodes': values}, 'content': {
            '__typename': r['type'], 'number': r['number'], 'title': r['title'], 'state': r['state'],
            'url': r['url'], 'parent': {'number': r['parent_number']} if r['parent_number'] else None}}

    def fake_run_gh(args: list[str], input_text: str | None = None) -> tuple[int, str, str]:
        joined = ' '.join(args)
        calls.append(joined)
        if mode == 'fail':
            return 1, '', 'HTTP 502: boom'
        if mode == 'errors':
            return 0, json.dumps({'errors': [{'message': 'something went wrong'}]}), ''
        if len(args) >= 4 and args[:2] == ['api', '-X']:
            match = re.match(r'^repos/example-org/example-repo/issues/(\d+)$', args[3])
            issue = (issues or {}).get(int(match.group(1))) if match else None
            if issue is None:
                return 1, '', 'gh: Not Found (HTTP 404)'
            if args[2] == 'PATCH':
                issue['body'] = json.loads(input_text)['body']
            return 0, json.dumps(issue), ''
        if re.search(r'\bi0:', joined):
            numbers = [int(x) for x in re.findall(r'issue\(number:\s*(\d+)\)', joined)]
            data = {}
            for k, number in enumerate(numbers):
                if 'blockedBy' in joined:
                    nodes = [{'number': b, 'state': s} for b, s in blockers.get(number, [])]
                    total = len(nodes) + (40 if mode == 'truncated' and number == 31 else 0)
                    data[f'i{k}'] = {'issue': {'number': number,
                                               'blockedBy': {'totalCount': total, 'nodes': nodes},
                                               'closedByPullRequestsReferences': {'nodes': []}}}
                else:
                    data[f'i{k}'] = {'issue': {'number': number, 'body': _BOARD_BODIES.get(number, '')}}
            return 0, json.dumps({'data': data}), ''
        if 'projectsV2' in joined:
            return _discovery_response(7)
        if 'items(first:' in joined:
            return 0, json.dumps({'data': {'repository': {'projectV2': {'items': {
                'pageInfo': {'hasNextPage': False, 'endCursor': None},
                'nodes': [node_of(r) for r in rows]}}}}}), ''
        return 1, '', f'unhandled fake gh call (board): {joined[:160]}'

    return fake_run_gh


def _run_main(argv: list[str]) -> tuple[int, str]:
    """main を _entry と同じ exit code の決め方で走らせ、(exit code, 標準出力) を返す。"""
    out = io.StringIO()
    try:
        with redirect_stdout(out):
            rc = gh_task.main(argv)
    except gh_task.GhError as exc:
        return exc.code, out.getvalue() + str(exc)
    return rc, out.getvalue()


def _board_checks(t, tmp_dir: str) -> None:
    """board の検査一式。控えと HTML の置き場を一時ディレクトリへ差し替えて走らせる。"""
    orig = (gh_task.run_gh, gh_task.BOARD_CACHE, gh_task.BOARD_HTML, gh_task.PROJECT_NUMBER_OVERRIDE)
    base = tempfile.mkdtemp(dir=tmp_dir)
    gh_task.BOARD_CACHE = os.path.join(base, 'state', 'gh-board-cache.json')
    gh_task.BOARD_HTML = os.path.join(base, 'state', 'board.html')
    calls: list[str] = []

    store: dict[int, dict] = {}

    def use(mode: str = 'ok', blockers: dict | None = None) -> None:
        gh_task.run_gh = make_console_gh(calls, mode=mode, blockers=blockers, issues=store)

    def writes() -> list:
        return [c for c in calls if 'mutation' in c or re.search(r'-X (?!GET)', c)]

    def fresh() -> None:
        for path in (gh_task.BOARD_CACHE, gh_task.BOARD_HTML):
            if os.path.exists(path):
                os.remove(path)
        calls.clear()
        use()

    expected_summary = {
        '着手できる（hirai-task ready が出す）': 1, '進行中': 1, 'レビュー中（merge 待ち）': 1,
        '承認待ちの feature（人がボードで着手可にする）': 1, '承認待ちの task': 2, '判断待ち（裁定を待つ）': 1,
        '依存待ち': 1, '保留': 1, 'Status 未設定': 1, '着手可なのに着手できない': 3,
        '[User] の人の作業（open）': 1, '閉じたのに完了でない': 1, '止まっている task（合計）': 9,
    }
    expected_not_ready = {
        '自分に未完了の blocked by': 1, '親の feature が着手可でない': 1,
        '親が feature でない・無い': 1,
    }

    try:
        def _first_fetch_then_cache() -> None:
            fresh()
            rc, out = _run_main(['board'])
            assert rc == 0, f'exit {rc}: {out}'
            first = len(calls)
            assert first > 0, '1 回目に gh を叩いていない'
            assert os.path.isfile(gh_task.BOARD_HTML), 'HTML を書いていない'
            assert gh_task.BOARD_HTML in out and '取り直した' in out, f'出力にパスか出どころが無い: {out}'
            rc, out = _run_main(['board'])
            assert (rc, len(calls)) == (0, first), f'10 分以内の 2 回目で gh を叩いた（{first} → {len(calls)}）'
            assert '残した JSON を使用（0 分前）' in out, f'残した JSON を使ったと出ていない: {out}'
            rc, out = _run_main(['board', '--text'])
            assert (rc, len(calls)) == (0, first), '--text の 2 回目で gh を叩いた'
            assert '残した JSON を使用（0 分前）' in out.splitlines()[0], f'1 行目に出どころが無い: {out[:200]}'
            rc, _ = _run_main(['board', '--refresh'])
            assert rc == 0 and len(calls) > first, '--refresh で取り直していない'
            again = len(calls)
            other = os.path.join(base, 'from', 'b.html')
            rc, out = _run_main(['board', '--from', gh_task.BOARD_CACHE, '--out', other])
            assert (rc, len(calls)) == (0, again) and os.path.isfile(other), '--from が gh を叩いたか HTML を書かない'
            gh_task.PROJECT_NUMBER_OVERRIDE = '7'
            rc, _ = _run_main(['board'])
            gh_task.PROJECT_NUMBER_OVERRIDE = ''
            assert rc == 0 and len(calls) > again, 'Project の指定が変わったのに残した JSON を使った'
            with open(gh_task.BOARD_CACHE, encoding='utf-8') as f:
                snap = json.load(f)
            snap['fetched_epoch'] -= 11 * 60
            with open(gh_task.BOARD_CACHE, 'w', encoding='utf-8') as f:
                json.dump(snap, f)
            before = len(calls)
            rc, _ = _run_main(['board'])
            assert rc == 0 and len(calls) > before, '11 分前の残した JSON を使った'

        t('board: 1 回目は gh を叩き、10 分以内の 2 回目と --from は叩かず、--refresh・Project の違い・11 分前は取り直す',
          _first_fetch_then_cache)

        def _summary_counts() -> None:
            fresh()
            rc, out = _run_main(['board', '--text'])
            assert rc == 0, f'exit {rc}: {out}'
            for label, count in {**expected_summary, **expected_not_ready}.items():
                assert re.search(rf'^\s*- {re.escape(label)}: {count}(?:\D|$)', out, re.MULTILINE), (
                    f'要約の「{label}: {count}」が無い:\n{out[:1500]}'
                )
            wave2 = [line for line in out.splitlines() if line.startswith('- #2 ') and '合計' in line]
            assert wave2 and '合計 12・open 11・止まっている 7' in wave2[0], f'wave #2 の行の件数が違う: {wave2}'
            assert not re.search(r'^\s*- \[User\]（人の作業）: ', out, re.MULTILINE), \
                '[User] の着手可を「着手可なのに着手できない」の理由に数えた（人の作業で AI が着手するものではない）'
            assert '循環' in out, '循環している wave の印が無い'
            rc, ready_out = _run_main(['ready'])
            assert rc == 0 and '着手可 1 件' in ready_out and '#30' in ready_out, (
                f'ready と board の「着手できる」がずれた: {ready_out}'
            )

        t('board: 要約の件数（止まっている区分・着手できない理由）と wave ごとの件数が偽の板と一致し、ready と同じ数',
          _summary_counts)

        def _html_escapes_and_links() -> None:
            fresh()
            rc, _ = _run_main(['board'])
            assert rc == 0
            with open(gh_task.BOARD_HTML, encoding='utf-8') as f:
                page = f.read()
            assert _BOARD_XSS_TITLE not in page and '&lt;script&gt;alert(1)&lt;/script&gt;' in page, '題名をエスケープしていない'
            assert 'javascript:' not in page, 'https の github.com 以外の URL をリンクにした'
            assert f'href="{_BOARD_URL.format(31)}"' in page, 'github.com の issue をリンクにしていない'
            for heading in ('どこで何件止まっているか', 'wave ごとの件数', 'wave の依存図', '止まっている task（9 件）'):
                assert heading in page, f'HTML に「{heading}」が無い'
            assert 'class="node cycle"' in page, '循環している wave の箱に印が無い'
            assert all('mutation' not in c and '-X' not in c for c in calls), f'読むだけのはずが書き込みを呼んだ: {calls}'
            assert 'name="viewport" content="width=device-width,initial-scale=1"' in page, 'viewport の meta が無い'
            assert '<div class="scroll"><svg' in page and '<div class="scroll"><table' in page, '図と表を横スクロールの箱に入れていない'

        t('board: HTML は題名をエスケープし、https の github.com だけをリンクにし、書き込みを呼ばない', _html_escapes_and_links)

        def _failures_keep_good_cache() -> None:
            fresh()
            assert _run_main(['board'])[0] == 0
            with open(gh_task.BOARD_CACHE, 'rb') as f:
                good = f.read()
            for mode in ('fail', 'errors', 'truncated'):
                use(mode)
                out_path = os.path.join(base, f'bad-{mode}', 'b.html')
                rc, out = _run_main(['board', '--refresh', '--out', out_path])
                assert rc == 1, f'{mode}: exit {rc}（期待 1）: {out}'
                with open(gh_task.BOARD_CACHE, 'rb') as f:
                    assert f.read() == good, f'{mode}: 良い残した JSON を上書きした'
                assert not os.path.exists(out_path), f'{mode}: 落ちたのに HTML を書いた'
            use()

        t('board: gh の失敗・errors・blocked by の打ち切りは exit 1 で、良い残した JSON を上書きせず HTML も書かない',
          _failures_keep_good_cache)

        def _bad_args_exit_2_without_gh() -> None:
            fresh()
            present = os.path.join(base, 'present.json')  # 在るファイル（無いファイルの exit 2 で偶然通らないように）
            with open(present, 'w', encoding='utf-8') as f:
                f.write('{}')
            for argv in (['--wave', '0'], ['--wave', 'abc'], ['--wave', '2'], ['--text', '--wave', '2', '--task', '30'],
                         ['--from', present, '--refresh'], ['--bogus'], ['--out'], ['--text', '--out', 'x.html'],
                         ['--text', '--text'], ['--task', '٣', '--text'], ['--summary', '--text'],
                         ['--summary', '--out', 'x.html'], ['--publish', '0'], ['--publish', '90', '--from', present],
                         ['--publish', '90', '--text'], ['--publish', '90', '--out', 'x.html'],
                         ['--text', '--summary', '--publish', '90']):
                rc, out = _run_main(['board', *argv])
                assert rc == 2, f'{argv}: exit {rc}（期待 2）: {out}'
            assert calls == [], f'不正な引数で gh を叩いた: {calls}'
            rc, _ = _run_main(['board', '--from', os.path.join(base, 'no-such.json')])
            assert rc == 2 and calls == [], '--from の無いファイルが exit 2 でない'
            broken = os.path.join(base, 'broken.json')
            with open(broken, 'w', encoding='utf-8') as f:
                f.write('{"items": 3}')
            rc, _ = _run_main(['board', '--from', broken])
            assert rc == 1 and calls == [], '--from の壊れた JSON が exit 1 でない'

        t('board: 不正な引数と無い --from は exit 2、壊れた --from は exit 1 で、どれも gh を叩かない', _bad_args_exit_2_without_gh)

        def _text_scopes() -> None:
            fresh()
            rc, out = _run_main(['board', '--text', '--task', '35'])
            marked = [line for line in out.splitlines() if '←' in line]
            assert rc == 0 and len(marked) == 1 and '#35' in marked[0], f'--task の印が 1 行でない: {marked}'
            assert not any(line.startswith('- #1 ') for line in out.splitlines()), '--task の木に別の wave が混ざった'
            rc, out = _run_main(['board', '--text', '--wave', '1'])
            assert rc == 0 and 'F1 済み' in out and 'F2 進める' not in out, '--wave がその wave に絞っていない'
            rc, out = _run_main(['board', '--text', '--feature', '21'])
            assert rc == 0 and 'T41 親が承認待ち' in out and 'T30 着手できる' not in out, '--feature がその feature に絞っていない'
            for argv in (['--task', '999'], ['--task', '50'], ['--wave', '20'], ['--feature', '2']):
                rc, out = _run_main(['board', '--text', *argv])
                assert rc == 2, f'{argv}: 木を決められない番号が exit {rc}（期待 2）: {out}'

        t('board: --text の --task は印を 1 行に付け、--wave・--feature はその下に絞り、決められない番号は exit 2', _text_scopes)

        def _summary_markdown() -> None:
            fresh()
            rc, out = _run_main(['board', '--summary'])
            assert rc == 0, f'exit {rc}: {out}'
            lines = out.splitlines()
            assert max(len(line) for line in lines) <= 44, f'1 行が長い: {max(lines, key=len)!r}'
            assert all(line.count('|') <= 4 for line in lines), '表が 3 列を超えた'
            for want in ('### あなたの番', '承認待ちの feature（ボードで着手可に） 1', '- #21 画面をそろえる作業を始めるか', '  推奨 承認する', '判断待ち（裁定する） 1',
                         '[User] の作業 1', 'レビュー中（PR の merge） 1', '### 止まっている 9', '| 着手可だが着手できない | 3 |',
                         '- #31 T31 自分が止められている（自分の待ち）', '- #35 T35 feature をまたいで待つ ← #40'):
                assert want in out, f'要約に「{want}」が無い:\n{out}'
            assert '<script>' not in out and '＜script＞' in out, '題名の < > を全角にしていない'
            with open(gh_task.BOARD_CACHE, encoding='utf-8') as f:
                snap = json.load(f)
            for item in snap['items']:
                if item['number'] == 37:
                    item['status'] = '進行中'
            snap['items'] += [dict(snap['items'][0], number=80 + k, title=f'待ち {k}', kind='task', status='依存待ち',
                                   parent_number=20, url=_BOARD_URL.format(80 + k)) for k in range(7)]
            alt = os.path.join(base, 'alt.json')
            with open(alt, 'w', encoding='utf-8') as f:
                json.dump(snap, f, ensure_ascii=False)
            rc, out = _run_main(['board', '--summary', '--from', alt])
            assert rc == 0 and '| 保留 |' not in out, f'0 件の区分を省いていない:\n{out}'
            assert '#### 依存待ち 8' in out and '- ほか 3 件' in out, f'上位 5 件と残りの件数になっていない:\n{out}'
            assert writes() == [], f'--publish なしで書き込みを呼んだ: {writes()}'

        t('board: --summary は 1 行 44 字以内・表 2 列で、あなたの番・止まっている区分（0 件は省く）・上位 5 件を出し、書き込まない',
          _summary_markdown)

        def _publish_only_between_markers() -> None:
            fresh()
            api = 'https://api.github.com/repos/example-org/example-repo'
            store.clear()
            store.update({
                90: {'state': 'open', 'repository_url': api, 'html_url': _BOARD_URL.format(90),
                     'body': f'前の文\r\n{gh_task.BOARD_START}\n古い\n{gh_task.BOARD_END}\n後ろの文'},
                91: {'state': 'open', 'repository_url': api, 'body': '本文だけ'},
                92: {'state': 'closed', 'repository_url': api, 'body': 'x'},
                93: {'state': 'open', 'repository_url': api, 'body': 'x', 'pull_request': {}},
                94: {'state': 'open', 'repository_url': 'https://api.github.com/repos/other/repo', 'body': 'x'},
                95: {'state': 'open', 'repository_url': api, 'body': f'x\n{gh_task.BOARD_START}\ny'},
            })
            rc, out = _run_main(['board', '--publish', '90'])
            body = store[90]['body']
            assert rc == 0 and '## 進捗 Project #7' in body and '古い' not in body, f'差し替わっていない: {body!r} {out}'
            assert body.startswith(f'前の文\r\n{gh_task.BOARD_START}\n') and body.endswith(f'{gh_task.BOARD_END}\n後ろの文'), (
                f'目印の外が変わった: {body!r}'
            )
            assert len(writes()) == 1, f'PATCH が {len(writes())} 回'
            assert _run_main(['board', '--publish', '90'])[0] == 0 and store[90]['body'] == body and len(writes()) == 1, (
                '2 回目で本文が変わったか、同じ中身を書き直した'
            )
            assert _run_main(['board', '--publish', '91'])[0] == 0, '目印の無い issue に書けない'
            first = store[91]['body']
            assert first.startswith(f'本文だけ\n\n{gh_task.BOARD_START}\n') and first.endswith(f'{gh_task.BOARD_END}\n'), (
                f'目印を末尾に足していない: {first!r}'
            )
            rc, _ = _run_main(['board', '--publish', '91', '--refresh'])
            assert rc == 0 and len(store[91]['body']) == len(first), '2 回目（取り直し）で本文が増えた'
            before = {k: dict(v) for k, v in store.items()}
            done = len(writes())
            for number, code in ((92, 2), (93, 2), (94, 2), (95, 2), (999, 1)):
                rc, out = _run_main(['board', '--publish', str(number)])
                assert rc == code, f'#{number}: exit {rc}（期待 {code}）: {out}'
            assert len(writes()) == done and store == before, '書いてはいけない issue に書いた'

        t('board: --publish は目印の間だけを差し替え（外は 1 バイトも変えず・2 回目で増えず）、閉じた・PR・別 repo・片方の目印・'
          '取れない issue には書かない', _publish_only_between_markers)

        def _summary_titles_make_no_mentions_or_links() -> None:
            board_mod = gh_task._load_board_module()
            got = board_mod.short('@octocat ![x](http://e.invalid/x.png) [a](http://e.invalid) |b| `c` <!-- x -->', 200)
            for ch in ('@', '[', ']', '|', '`', '<', '>'):
                assert ch not in got, f'要約の題名に {ch!r} が残った（通知・リンク・表の崩れ・目印を作れる）: {got!r}'
            assert 'octocat' in got and 'http://e.invalid' in got, f'題名の中身まで消した: {got!r}'

        t('board: 要約の題名は @ の通知・リンク・画像・表の区切り・コード・目印を作らない（文字は残す）',
          _summary_titles_make_no_mentions_or_links)

        def _publish_always_refetches() -> None:
            fresh()
            api = 'https://api.github.com/repos/example-org/example-repo'
            store.clear()
            store.update({90: {'state': 'open', 'repository_url': api, 'html_url': _BOARD_URL.format(90), 'body': '本文'}})
            assert _run_main(['board', '--summary'])[0] == 0
            seen = len(calls)
            rc, out = _run_main(['board', '--publish', '90'])
            assert rc == 0, f'exit {rc}: {out}'
            assert any('graphql' in c for c in calls[seen:]), '控えが新しくても --publish は取り直す（古い Status を本文に載せない）'

        t('board: --publish は 10 分以内の控えがあっても取り直してから書く', _publish_always_refetches)
    finally:
        gh_task.run_gh, gh_task.BOARD_CACHE, gh_task.BOARD_HTML, gh_task.PROJECT_NUMBER_OVERRIDE = orig


# ── カード（承認・判断・人の作業）の検査 ─────────────────────────
_CARD_APPROVAL = ('<!-- card:approval -->\n**決めること**: 画面をそろえる作業を始めるか。**推奨**: 承認する\n'
                  '**目的**: 入居者が迷わず担当者を選べる\n**位置**: 段「画面」の残り2件\n'
                  '**承認すると**: AI が画面を2つ直す。戻せる\n**しないと**: 画面は今のまま\n'
                  '**注意**: 同じ画面の直しと重なるおそれ（推測）\n**詳しく**: #800\n<!-- /card -->\n\n本文')
_CARD_DECISION = ('<!-- card:decision -->\n**決めること**: チャットを何日残すか。**期限**: 2026-12-10（過ぎると3件が止まる）\n'
                  '**目的**: 漏れたときの害を小さくする\n**選択肢**: A 30日 ／ B 1年\n**推奨**: A — 害が小さい\n'
                  '**決めないと**: 退会の作業3件が止まる\n**誰が決める**: 事業の責任者\n**詳しく**: #802\n<!-- /card -->\n')
_CARD_RECOMMEND = ('承認する', '条件つき', '承認しない')


def _card_field_defs(*, with_card_fields: bool = True) -> list[dict]:
    defs = _fake_field_defs()
    if with_card_fields:
        defs += [{'id': 'F_ひとこと', 'name': 'ひとこと'},
                 {'id': 'F_推奨', 'name': '推奨', 'options': [{'id': f'O_推奨_{o}', 'name': o} for o in _CARD_RECOMMEND]}]
    return defs


def _card_items() -> list[dict]:
    return [
        {'number': 800, 'title': '画面（モック）', 'status': '承認待ち', 'kind': 'feature'},
        {'number': 801, 'title': 'カードの無い feature', 'status': '承認待ち', 'kind': 'feature'},
        {'number': 802, 'title': '[Decision] 何日残すか', 'status': '判断待ち', 'kind': 'task', 'parent_number': 804},
        {'number': 803, 'title': '[User] 本番の申込', 'status': '承認待ち', 'kind': 'task', 'parent_number': 804},
        {'number': 804, 'title': '着手可の feature', 'status': '着手可', 'kind': 'feature'},
        {'number': 805, 'title': '判断待ちなのに承認カード', 'status': '判断待ち', 'kind': 'task', 'parent_number': 804},
        {'number': 806, 'title': '閉じた feature', 'status': '承認待ち', 'kind': 'feature', 'state': 'CLOSED'},
        {'number': 811, 'title': '画面の作業', 'status': '承認待ち', 'kind': 'task', 'parent_number': 800},
        {'number': 809, 'title': '子の無い feature', 'status': '承認待ち', 'kind': 'feature'},
        {'number': 810, 'title': '[操作] 本番の確認', 'status': '承認待ち', 'kind': 'task', 'parent_number': 804},
        {'number': 813, 'title': '[Decision] 期限の近い問い', 'status': '判断待ち', 'kind': 'task', 'parent_number': 804},
        {'number': 814, 'title': '項目が古い feature', 'status': '承認待ち', 'kind': 'feature',
         'headline': '前の決めること', 'recommend': '承認する'},
        {'number': 815, 'title': '項目の作業', 'status': '承認待ち', 'kind': 'task', 'parent_number': 814},
        {'number': 816, 'title': '[操作] 保留中の操作', 'status': '保留', 'kind': 'task', 'parent_number': 804},
    ]


def _card_checks(t, tmp_dir: str) -> None:
    """card・card --lint・board のカードの行・new の雛形・start --approved の門。"""
    bodies = {800: _CARD_APPROVAL, 801: 'カードが無い本文', 802: _CARD_DECISION, 803: '手順だけ',
              805: _CARD_APPROVAL.replace('#800', '#805'), 809: _CARD_APPROVAL.replace('#800', '#809'),
              813: _CARD_DECISION.replace('2026-12-10', '2026-11-20').replace('**誰が決める**: 事業の責任者\n', ''),
              814: _CARD_APPROVAL.replace('#800', '#814')}

    def use(items=None, *, with_card_fields=True, log=None):
        for path in (gh_task.FIELDS_CACHE,):
            if os.path.exists(path):
                os.remove(path)
        gh_task.run_gh = make_command_gh(items if items is not None else _card_items(), bodies=bodies,
                                         field_defs=_card_field_defs(with_card_fields=with_card_fields), write_log=log)

    def _module_selftest() -> None:
        cards = gh_task._load_card_module()
        root = _base_plugin_root()
        with open(os.path.join(root, 'docs', 'rules-reference', 'approval-template.md'), encoding='utf-8') as f:
            results = cards.selftest(f.read())
        failed = [f'{name}: {detail}' for name, ok, detail in results if not ok]
        assert not failed, '\n'.join(failed)

    t('card: 取り出し・形の検査・正本の記入例（hirai_card の自己検査）', _module_selftest)

    def _card_reads_and_checks() -> None:
        use()
        rc, out = _run_main(['card', '800'])
        assert rc == 0 and '決めること: 画面をそろえる作業を始めるか。推奨: 承認する' in out, f'exit {rc}: {out}'
        assert '**' not in out and '<!--' not in out, f'会話の形（太字・目印なし）で出していない: {out}'
        rc, out = _run_main(['card', '801'])
        assert rc == 1 and '承認カードが無い' in out, f'exit {rc}: {out}'
        rc, out = _run_main(['card', '805'])
        assert rc == 1 and '判断カードが無い（あるのは承認カード' in out, f'判断待ちに要るカードを見ていない: {out}'
        rc, out = _run_main(['card', '810'])
        assert rc == 1 and '承認カードが無い' in out, f'[操作] に要るのは承認カード: {out}'
        bodies[807] = _CARD_APPROVAL.replace('画面をそろえる', '画面を\x1bそろえる')
        use(_card_items() + [{'number': 807, 'title': 'ESC\x1b[31m入り', 'status': '承認待ち', 'kind': 'feature'}])
        rc, out = _run_main(['card', '807'])
        assert rc == 1 and '\x1b' not in out and '制御文字' in out, f'制御文字を端末に出した: {out!r}'
        rc, out = _run_main(['card', '--lint'])
        assert '\x1b' not in out, f'--lint が制御文字を端末に出した: {out!r}'
        del bodies[807]

    t('card <n>: カードを会話の形で出し、無い・種類違いは理由つきで exit 1', _card_reads_and_checks)

    def _card_sync_writes_two_fields() -> None:
        log: list = []
        use(log=log)
        rc, out = _run_main(['card', '800', '--sync'])
        assert rc == 0, f'exit {rc}: {out}'
        writes = [w for w in log if w[0] == 'item-update']
        assert ('item-update', 'F_ひとこと', '画面をそろえる作業を始めるか') in writes, writes
        assert ('item-update', 'F_推奨', 'O_推奨_承認する') in writes, writes
        assert not [w for w in log if w[0] == 'graphql-update'], f'GraphQL で書いた: {log}'

    t('card <n> --sync: 決めることを「ひとこと」、推奨を「推奨」へ REST で書く', _card_sync_writes_two_fields)

    def _card_sync_marks_stalled() -> None:
        log: list = []
        use(log=log)
        rc, out = _run_main(['card', '809', '--sync'])
        assert rc == 0, f'exit {rc}: {out}'
        assert ('item-update', 'F_ひとこと', '画面をそろえる作業を始めるか（今は動かない: 子の作業が無い）') in log, log

    t('card --sync: 承認しても動かない feature は「ひとこと」の末尾に今は動かない理由を付ける', _card_sync_marks_stalled)

    def _card_sync_refuses() -> None:
        for number, with_fields, code, why in ((800, False, 2, 'hirai-task setup'), (801, True, 1, '承認カードが無い'),
                                               (802, True, 2, '承認カードだけ')):
            log: list = []
            use(with_card_fields=with_fields, log=log)
            rc, out = _run_main(['card', str(number), '--sync'])
            assert rc == code and why in out, f'#{number}: exit {rc}（期待 {code}・「{why}」）: {out}'
            assert not [w for w in log if w[0] in ('item-update', 'graphql-update')], f'#{number}: 書いた: {log}'

    t('card --sync: 項目が無い（exit 2・setup の案内）・カードの形が悪い（exit 1）・判断カード（exit 2）は書かない',
      _card_sync_refuses)

    def _card_lint_classifies() -> None:
        use()
        rc, out = _run_main(['card', '--lint'])
        assert rc == 1, f'問題があるのに exit {rc}: {out}'
        for needle in ('#801', '#803', '#805', '#810', '#813', '#814', '人の作業カードが無い', '項目「ひとこと」が本文のカードと違う'):
            assert needle in out, f'「{needle}」が無い: {out}'
        for absent in ('#800 ', '#802 ', '#804', '#806', '#811', '#815', '#816'):
            assert absent not in out, f'問題の無い・対象外の行が出た（{absent}）: {out}'
        assert out.splitlines()[1].startswith('要約: '), f'先頭に要約が無い: {out}'
        assert '承認カード 5 件中 3 件に問題' in out and '判断カード 3 件中 2 件に問題' in out, out
        assert '警告' in out and '#809' in out and '承認しても動かない' in out, f'動かないのに推奨が承認するの警告が無い: {out}'
        assert out.index('#813') < out.index('#801'), f'期限の近い判断から並べていない: {out}'
        use([i for i in _card_items() if i['number'] in (800, 802, 804, 811)])
        rc, out = _run_main(['card', '--lint'])
        assert rc == 0, f'問題が無いのに exit {rc}: {out}'
        assert not [c for c in out.splitlines() if 'mutation' in c], out

    t('card --lint: 承認待ちの feature・判断待ち・[User] と [操作] の要るカードを確かめ、問題があれば exit 1', _card_lint_classifies)

    def _stall_reasons() -> None:
        def it(number, kind, status, parent=None, title=None, state='OPEN'):
            return {'number': number, 'kind': kind, 'status': status, 'parent_number': parent,
                    'title': title or f'row {number}', 'state': state}
        items = [it(1, 'wave', '', title='W1'), it(2, 'wave', '', title='W2'),
                 it(10, 'feature', '承認待ち', 2), it(11, 'task', '承認待ち', 10),
                 it(20, 'feature', '承認待ち', 1), it(21, 'task', '保留', 20), it(22, 'task', '承認待ち', 20, '[User] 申込'),
                 it(30, 'feature', '承認待ち', 1), it(31, 'task', '承認待ち', 30),
                 it(40, 'feature', '承認待ち', 1), it(41, 'task', '完了', 40, state='CLOSED')]
        by_number, children = gh_task._board_index(items)
        extras = {2: {'blocked_by_numbers': [1]}}
        reasons = {n: gh_task.approval_stall_reason(by_number[n], by_number, children, extras) for n in (10, 20, 30, 40)}
        assert reasons[10] == '', f'先の wave が未了でも承認すれば子は動くので止まる理由にしない: {reasons}'
        assert '人の作業' in reasons[20] and '保留' in reasons[20], reasons
        assert reasons[30] == '', reasons
        assert '子の open の task が無い' in reasons[40], reasons
        assert [gh_task.STALL_SHORT[r] for r in (reasons[20], reasons[40])] == \
            ['子が人の作業だけ', '子の作業が無い'], '短い言い方が理由と合っていない'
        assert not hasattr(gh_task, 'STALL_WAVE'), '止まる理由から外した STALL_WAVE が残っている'

    t('board: 承認しても動かない feature の理由（子が保留と人の作業だけ・子が無い。先の wave は理由にしない）', _stall_reasons)

    def _board_shows_cards() -> None:
        calls: list = []
        for path in (gh_task.BOARD_CACHE, gh_task.BOARD_HTML):
            if os.path.exists(path):
                os.remove(path)
        gh_task.run_gh = make_console_gh(calls)
        rc, summary = _run_main(['board', '--summary'])
        assert rc == 0, summary
        assert '画面をそろえる作業を始めるか' in summary and '推奨 承認する' in summary, f'#21 のカードが無い: {summary}'
        assert 'カード無し' in summary, f'#36（判断待ち・カード無し）の印が無い: {summary}'
        rc, text = _run_main(['board', '--text'])
        line21 = next((x for x in text.splitlines() if x.startswith('  - feature #21 ')), '')
        assert 'カード: 画面をそろえる作業を始めるか（推奨 承認する）' in line21, f'--text の feature の行: {line21}'
        rc, _out = _run_main(['board'])
        with open(gh_task.BOARD_HTML, encoding='utf-8') as f:
            page = f.read()
        assert '承認と判断の待ち' in page and '画面をそろえる作業を始めるか' in page and 'カード無し' in page, page[:400]

    t('board: あなたの番・--text・HTML に、カードの決めることと推奨（無ければ「カード無し」）を出す', _board_shows_cards)

    def _board_lists_operation_approvals() -> None:
        def it(number, kind, status, parent=None, title=None):
            return {'number': number, 'type': 'Issue', 'kind': kind, 'status': status, 'parent_number': parent,
                    'title': title or f'row {number}', 'state': 'OPEN', 'url': _BOARD_URL.format(number)}
        snap = {'repo': gh_task.REPO, 'project': 7, 'fetched_at': '2026-11-15 10:00:00 +0900', 'fetched_epoch': 0,
                'items': [it(1, 'wave', ''), it(2, 'feature', '着手可', 1), it(3, 'task', '承認待ち', 2, '[操作] 本番で確かめる')],
                'extras': {}, 'bodies': {}}
        summary = gh_task._load_board_module().render_summary_md(gh_task.board_view(snap, 'from'))
        assert '操作の承認 1' in summary and '- #3 ' in summary, f'承認待ちの [操作] が あなたの番 に無い: {summary}'

    t('board: 承認待ちの [操作] を、あなたの番の「操作の承認」に出す', _board_lists_operation_approvals)

    def _new_feature_writes_card_first() -> None:
        calls: list = []
        out = io.StringIO()
        gh_task.run_gh = make_write_gh(
            {950: dict(title='新しい feature', status=gh_task.PENDING_STATUS, kind=''),
             900: dict(title='基盤（P1）', status='', kind='wave')},
            rest_handler=lambda m, p, b: (calls.append((m, p, b)) or (
                {'number': 950, 'id': 950950} if (m, p) == ('POST', f'repos/{gh_task.REPO}/issues') else
                {'sub_issues_summary': {'total': 1}} if (m, p) == ('GET', f'repos/{gh_task.REPO}/issues/900') else
                {'milestone': None, 'body': ''} if (m, p) == ('GET', f'repos/{gh_task.REPO}/issues/950') else {})),
        )
        with redirect_stdout(out):
            gh_task.cmd_new(['新しい feature', '--kind', 'feature', '--parent', '900',
                             '--body', '<!-- ai -->\n## 範囲\n画面の直し'])
        body = next(b for m, p, b in calls if (m, p) == ('POST', f'repos/{gh_task.REPO}/issues'))['body']
        assert body.startswith('<!-- card:approval -->\n**決めること**: '), body
        assert '**位置**: 段「基盤（P1）」の一部' in body, body
        assert body.rstrip().endswith('<!-- ai -->') and '## 範囲\n画面の直し' in body, f'機械向けの行を末尾へ回していない: {body}'
        assert 'hirai-task card 950 --sync' in out.getvalue(), out.getvalue()

    t('new --kind feature: 本文の先頭に承認カードの雛形（位置は親の wave）、機械向けの行は末尾、--sync の案内', _new_feature_writes_card_first)

    def _marks_are_read_anywhere() -> None:
        body = '<!-- ai -->\n' + _CARD_APPROVAL + '\n\n<!-- rmp-task: id=TBL-01 rev=chat:3 stream=Infra src=tbl@PR9 -->\n'
        mark = gh_task.parse_task_mark(body)
        assert mark and mark.get('id') == 'TBL-01' and mark.get('rev') == 'chat:3', mark
        assert 'rev=chat:4' in gh_task.rewrite_task_mark(body, rev='chat:4'), '末尾の目印を書き直せない'
        assert gh_task.parse_task_mark('<!-- rmp-task: id=X stream=a -->\n本文') == {'id': 'X', 'stream': 'a'}
        bodies = {501: '<!-- rmp-task: id=TBL-01 stream=a src=tbl@PR9 -->\n本文',
                  502: _CARD_APPROVAL + '\n\n<!-- rmp-task: id=TBL-F1 stream=— src=tbl@PR9 -->\n',
                  503: '<!-- rmp-task: id=TBL-02 stream=a src=other@PR9 -->'}
        assert gh_task.table_mark_ids(bodies, 'tbl') == {'TBL-01': 501, 'TBL-F1': 502}, gh_task.table_mark_ids(bodies, 'tbl')

    t('目印（rmp-task）は本文の先頭でも末尾でも読み、書き直せる', _marks_are_read_anywhere)

    def _marks_follow_position_rule() -> None:
        real = '<!-- rmp-task: id=F1 rev=a:1 stream=x src=slug@PR5 -->'
        quoted = '<!-- rmp-task: id=F9 rev=a:9 stream=y src=other@PR1 -->'
        fenced = 'カード\n\n前の issue の例:\n```\n' + quoted + '\n```\n\n' + real + '\n'
        mark = gh_task.parse_task_mark(fenced)
        assert mark and mark['id'] == 'F1', f'フェンスの中の引用を本物として読んだ: {mark}'
        rewritten = gh_task.rewrite_task_mark(fenced, rev='a:2')
        assert quoted in rewritten and 'id=F1 rev=a:2 ' in rewritten, f'引用を書き換えたか、本物を書き換えていない: {rewritten}'
        only_quote = 'x\n```\n' + quoted + '\n```\n'
        assert gh_task.parse_task_mark(only_quote) is None, 'フェンスの中だけの目印を本物として読んだ'
        assert gh_task.rewrite_task_mark(only_quote, rev='a:2') == only_quote, 'フェンスの中の目印を書き換えた'
        top = real + '\n\n説明: 前の issue は次の形だった\n> ' + quoted + '\n' + quoted + '\n\n続き'
        assert gh_task.parse_task_mark(top)['id'] == 'F1'
        assert gh_task.rewrite_task_mark(top, rev='a:2').count(quoted) == 2, '途中の引用を書き換えた'
        middle = '本文\n' + quoted + '\n本文の続き'
        assert gh_task.parse_task_mark(middle) is None, '本文の途中の目印を本物として読んだ'
        crlf = real.replace('-->', '-->\r') + '\n\r\n本文\r\n'
        assert (gh_task.parse_task_mark(crlf) or {}).get('id') == 'F1', 'CRLF の本文の目印を読めない'
        assert gh_task.table_mark_ids({1: fenced}, 'other') == {}, '引用の写しを起票済みとして採った'
        assert gh_task.table_mark_ids({1: fenced}, 'slug') == {'F1': 1}
        assert gh_task.body_doc_paths('```\n' + quoted + '\n```\ndocs/a.md') == ['docs/a.md']

    t('目印の位置の規則: 先頭か末尾の連続した機械向けの行だけが本物。フェンス・引用・途中は読まず書き換えない（照合も同じ）',
      _marks_follow_position_rule)

    def _with_card_first_keeps_fences() -> None:
        out = gh_task.with_card_first('説明\n```html\n<!-- ai -->\n```\n', 'CARD')
        assert '```html\n<!-- ai -->\n```' in out and not out.rstrip().endswith('```\n<!-- ai -->'), f'フェンスの中を動かした: {out!r}'
        assert out.startswith('CARD\n\n説明'), out
        lead = '<!-- ai -->\n<!-- rmp-task: id=X stream=a -->\n\n本文\n```\n<!-- ai -->\n```\n'
        out = gh_task.with_card_first(lead, 'CARD')
        assert out.endswith('```\n\n<!-- ai -->\n<!-- rmp-task: id=X stream=a -->\n'), f'先頭の機械向けの行だけを末尾へ回していない: {out!r}'
        assert out.count('<!-- ai -->') == 2 and '```\n<!-- ai -->\n```' in out, out

    t('with_card_first: 先頭の連続した機械向けの行だけを末尾へ回し、フェンスの中は動かさない', _with_card_first_keeps_fences)

    def _old_cache_version_refetches() -> None:
        calls: list = []
        for path in (gh_task.BOARD_CACHE, gh_task.BOARD_HTML):
            if os.path.exists(path):
                os.remove(path)
        gh_task.run_gh = make_console_gh(calls)
        assert _run_main(['board', '--summary'])[0] == 0
        with open(gh_task.BOARD_CACHE, encoding='utf-8') as f:
            snap = json.load(f)
        snap['version'] = 1
        with open(gh_task.BOARD_CACHE, 'w', encoding='utf-8') as f:
            json.dump(snap, f)
        before = len(calls)
        assert _run_main(['board', '--summary'])[0] == 0
        assert len(calls) > before, '版 1 の控え（カードの本文を持たない）を使った'

    t('board: 版 1 の控えは使わずに取り直す（カードの本文を持たないため）', _old_cache_version_refetches)

    def _start_approved_checks_the_gate() -> None:
        for parent_status, code in ((gh_task.PENDING_STATUS, 2), (gh_task.READY_STATUS, 0)):
            record: list = []
            gh_task.run_gh = make_write_gh({
                880: dict(title=f'{gh_task.OPERATION_MARK} 本番の確認', status=gh_task.PENDING_STATUS, kind='task',
                          parent_number=881, body='本文'),
                881: dict(title='feature', status=parent_status, kind='feature'),
            }, record=record, rest_handler=lambda m, p, b: {})
            try:
                with redirect_stdout(io.StringIO()):
                    rc = gh_task.cmd_start(880, '2026-11-15 チャット')
            except gh_task.GhError as exc:
                rc = exc.code
                assert '親' in str(exc) and '着手可' in str(exc), str(exc)
            assert rc == code, f'親の feature が{parent_status}: exit {rc}（期待 {code}）'
            if code:
                assert record == [], f'断ったのに書いた: {record}'

    t('start --approved: [操作] の目印の止めは通すが、親の feature が着手可でなければ断る（門は迂回させない）',
      _start_approved_checks_the_gate)


def _expect_exit(fn, expected_code: int) -> None:
    try:
        fn()
    except gh_task.GhError as exc:
        assert exc.code == expected_code, f'exit {exc.code}（期待 {expected_code}）: {exc}'
        return
    raise AssertionError('落ちるべきなのに通った')


def main() -> int:
    fail = 0
    results: list[str] = []

    def t(label: str, fn) -> None:
        nonlocal fail
        try:
            fn()
            results.append(f'  PASS {label}')
        except AssertionError as exc:
            fail += 1
            results.append(f'  FAIL {label}: {exc}')
        except Exception as exc:  # noqa: BLE001 - selftest は落ちた理由を見せたい
            fail += 1
            results.append(f'  FAIL {label}: 例外 {type(exc).__name__}: {exc}')

    def n(label: str, fn) -> None:
        """落ちるべき呼び出しが本当に落ちることを見る（bash 版 selftest の n() と同じ形）。"""
        nonlocal fail
        try:
            fn()
        except (gh_task.GhError, AssertionError):
            results.append(f'  PASS {label}')
            return
        fail += 1
        results.append(f'  FAIL {label}（落ちるべきなのに通った）')

    print('gh_task_selftest.py')

    orig_run_gh = gh_task.run_gh
    # HIRAI_TASK_PROJECT がシェルに残っていると discover の 3 case が空振りで PASS/FAIL する
    # （selftest の結果が呼び出し環境に左右される穴。呼び出し元の環境を書き換えず、
    #  selftest の間だけ上書きする）。
    orig_override = gh_task.PROJECT_NUMBER_OVERRIDE
    gh_task.PROJECT_NUMBER_OVERRIDE = ''
    # 書く側の検査は field/option の id キャッシュを使う。実物の gh-fields.json に
    # 触れると、テストの偽の id が実運用のキャッシュに残ってしまう（同時に道具を回す
    # 別の会話を壊す）。
    orig_cache_path = gh_task.FIELDS_CACHE
    orig_sleep_fn = gh_task.sleep_fn
    orig_project_node_id_cache = dict(gh_task._project_node_id_cache)
    orig_owner_type_cache = gh_task._owner_type_cache
    cache_tmp_dir = tempfile.mkdtemp()
    gh_task.FIELDS_CACHE = f'{cache_tmp_dir}/gh-fields.json'
    orig_rest_cache_path = gh_task.REST_FIELDS_CACHE
    gh_task.REST_FIELDS_CACHE = f'{cache_tmp_dir}/gh-fields-rest.json'
    gh_task.sleep_fn = lambda _seconds: None
    # align 以下が使うキャッシュ（journal・since の 2 つ）も、実ファイルに触れず
    # 隔離する（同じ考え方。汚染すると次に道具を回す会話の状態を書き換えてしまう）。
    orig_journal_path = gh_task.JOURNAL_PATH
    orig_comments_since_cache = gh_task.COMMENTS_SINCE_CACHE
    orig_merged_designs_since_cache = gh_task.MERGED_DESIGNS_SINCE_CACHE
    gh_task.JOURNAL_PATH = f'{cache_tmp_dir}/gh-task-journal.jsonl'
    gh_task.COMMENTS_SINCE_CACHE = f'{cache_tmp_dir}/gh-comments-since.json'
    gh_task.MERGED_DESIGNS_SINCE_CACHE = f'{cache_tmp_dir}/gh-merged-designs-since.json'
    try:
        # 1) 偽の 800 行（8 頁）で ready が全件を読む。
        def _paginates_800() -> None:
            gh_task.run_gh = make_paginated_gh(800)
            items = gh_task.fetch_all_items(7)
            assert len(items) == 801, f'800 件 + 親の feature 1 件のはずが {len(items)} 件しか読めていない'
            rows = gh_task.ready_rows(items, {})
            assert len(rows) == 800, f'ready の行数が {len(rows)}（着手可 800 件のはず）'
            # fetch_all_items() を直接呼ぶだけでなく、cmd_ready の経路（main(['ready'])。
            # fetch_extras の 16 チャンク分も含む）でも 1 頁で止まらず全件を読めることを見る
            # （800 行の case が cmd_ready を通さず fetch_all_items を
            #  直接呼ぶだけでは足りない）。
            gh_task.run_gh = make_paginated_gh(800)
            out = io.StringIO()
            with redirect_stdout(out):
                rc = gh_task.main(['ready'])
            text = out.getvalue()
            assert rc == 0, f'main(["ready"]) が exit {rc}'
            assert '着手可 800 件' in text, f'800 件と出ていない: {text[:120]!r}'
            assert '#800' in text, f'最後の #800 が出ていない: {text[-200:]!r}'

        t('偽の 800 行（8 頁）で ready が全件を読む', _paginates_800)

        # 2) 偽の PR 行と feature 行が一覧に出ない。
        def _excludes_pr_and_feature() -> None:
            gh_task.run_gh = make_paginated_gh(150, page_size=100, extra_pr=2, extra_feature=3)
            items = gh_task.fetch_all_items(7)
            assert len(items) == 156, f'150 issue + 親の feature 1 + PR2 + feature3 = 156 のはずが {len(items)}'
            tasks = gh_task.task_items(items)
            assert len(tasks) == 150, f'task に絞ると 150 のはずが {len(tasks)}'
            assert all(i['type'] == 'Issue' for i in tasks), 'PR が task_items に混ざっている'
            assert all((i.get('kind') or '') not in gh_task.EXCLUDE_KINDS for i in tasks), (
                'wave/feature/設計メモ が task_items に混ざっている'
            )

        t('偽の PR 行と feature 行が一覧に出ない', _excludes_pr_and_feature)

        # 陰性の対照: 種別で絞っていなければ、feature 行も task_items に混ざる
        # （フィルタを外すと FAIL することを、実装前に確かめた・core.md「テストは壊して確かめる」）。
        def _feature_would_leak_without_filter() -> None:
            gh_task.run_gh = make_paginated_gh(10, page_size=100, extra_feature=1)
            items = gh_task.fetch_all_items(7)
            unfiltered = [i for i in items if i.get('type') == 'Issue']
            assert any((i.get('kind') or '') in gh_task.EXCLUDE_KINDS for i in unfiltered), (
                '対照が効いていない（feature 行が混ざっていない）'
            )

        t('種別で絞る前は feature 行が混ざる（フィルタの陰性対照）', _feature_would_leak_without_filter)

        # 2b) task_items() だけでなく、cmd_ready・cmd_pending・cmd_blocked の実際の出力で
        # PR・feature・wave・設計メモの行が出ないことを見る。
        def _real_commands_hide_non_tasks() -> None:
            rows = [
                _fake_row(500, status='着手可', kind='feature', parent_number=501),
                _fake_row(501, kind='wave'),
                _fake_row(1, status='着手可', kind='task', parent_number=500),
                _fake_row(2, status='承認待ち', kind='task', parent_number=200),
                _fake_row(3, status='判断待ち', kind='task', parent_number=500),
                _fake_row(4, status='依存待ち', kind='task', parent_number=500),
                _fake_row(5, status='保留', kind='task', parent_number=500),
                _fake_row(6, status='レビュー中', kind='task', parent_number=500),
                _fake_row(7, status='完了', state='CLOSED', kind='task', parent_number=500),
                _fake_row(100, status='着手可', kind='wave'),
                _fake_row(200, status='承認待ち', kind='feature', parent_number=501),
                _fake_row(300, status='保留', kind='設計メモ'),
                _fake_row(400, status='承認待ち', typename='PullRequest'),
            ]
            gh_task.run_gh = make_board_gh(rows, extras={6: {'open_pr_numbers': [999]}})

            out = io.StringIO()
            with redirect_stdout(out):
                rc = gh_task.main(['ready'])
            text = out.getvalue()
            assert rc == 0
            assert '#1 ' in text or '#1\n' in text or '#1  ' in text, f'着手可の #1 が出ていない: {text!r}'
            for n_ in (100, 200, 300, 400, 500, 501):
                assert f'#{n_} ' not in text, f'wave/feature/設計メモ/PR の #{n_} が ready に出た'

            out2 = io.StringIO()
            with redirect_stdout(out2):
                rc2 = gh_task.main(['pending'])
            text2 = out2.getvalue()
            assert rc2 == 0
            assert '#200' in text2, f'承認待ちの feature #200 が pending に出ていない: {text2!r}'
            for n_ in (1, 2, 100, 300, 400, 500):
                assert f'#{n_} ' not in text2, f'#{n_} が pending に出た（承認待ちの feature だけのはず）'

            out3 = io.StringIO()
            with redirect_stdout(out3):
                rc3 = gh_task.main(['blocked'])
            text3 = out3.getvalue()
            assert rc3 == 0
            for n_ in (2, 3, 4, 5):
                assert f'#{n_}' in text3, f'#{n_} が blocked に出ていない'
            for n_ in (100, 200, 300, 400):
                assert f'#{n_}' not in text3, f'wave/feature/設計メモ/PR の #{n_} が blocked に出た'

        t(
            '偽の PR 行・wave・feature・設計メモが ready・blocked に出ない。pending は承認待ちの feature だけを出す',
            _real_commands_hide_non_tasks,
        )

        # 3) ready の警告 3 種。出る入力と出ない入力を 1 つずつ（core.md「テストは壊して確かめる」:
        #    ready_warnings の該当行を消すと、それぞれ最初の t() が FAIL することを実装前に見た）。
        def _warning_blocked_by() -> None:
            rows = [_fake_row(11, status='着手可'), _fake_row(12, status='着手可')]
            extras = {
                11: {'blockers': [(999, 'OPEN')], 'blocked_by_total': 1},
                12: {'blockers': [], 'blocked_by_total': 0},
            }
            gh_task.run_gh = make_board_gh(rows, extras=extras)
            out = io.StringIO()
            with redirect_stdout(out):
                gh_task.main(['ready'])
            text = out.getvalue()
            assert '着手可なのに未完了の blocked by がある: #11' in text
            assert '着手可なのに未完了の blocked by がある: #12' not in text

        t('警告: 着手可なのに未完了の blocked by がある（出る/出ない）', _warning_blocked_by)

        def _warning_closed_not_done() -> None:
            rows = [
                _fake_row(21, status='進行中', state='CLOSED'),
                _fake_row(22, status='完了', state='CLOSED'),
            ]
            gh_task.run_gh = make_board_gh(rows, extras={})
            out = io.StringIO()
            with redirect_stdout(out):
                gh_task.main(['ready'])
            text = out.getvalue()
            assert '閉じたのに完了でない: #21' in text
            assert '閉じたのに完了でない: #22' not in text

        t('警告: 閉じたのに完了でない（出る/出ない）', _warning_closed_not_done)

        def _warning_review_without_pr() -> None:
            rows = [_fake_row(31, status='レビュー中'), _fake_row(32, status='レビュー中')]
            extras = {31: {'open_pr_numbers': []}, 32: {'open_pr_numbers': [500]}}
            gh_task.run_gh = make_board_gh(rows, extras=extras)
            out = io.StringIO()
            with redirect_stdout(out):
                gh_task.main(['ready'])
            text = out.getvalue()
            assert 'レビュー中なのに open の PR が無い: #31' in text
            assert 'レビュー中なのに open の PR が無い: #32' not in text

        t(
            '警告: レビュー中なのに open の PR が無い（出る/出ない・Project に居ない PR でも判定できる）',
            _warning_review_without_pr,
        )

        # 4) PR の番号でも show が落ちない。PR にも Projects の Status が出る。
        def _show_pr_reports_project_status() -> None:
            gh_task.run_gh = make_show_gh(as_pr=True, number=244, linked=True, status='完了')
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = gh_task.cmd_show(244)
            assert rc == 0, f'show がエラー終了した（exit {rc}）'
            text = buf.getvalue()
            assert 'PR' in text, f'PR だと分かる表示が無い: {text!r}'
            assert '完了' in text, f'PR の Projects Status が出ていない: {text!r}'

        t('PR の番号でも show が落ちない。Projects の Status も出る', _show_pr_reports_project_status)

        def _show_issue_still_works() -> None:
            gh_task.run_gh = make_show_gh(as_pr=False, number=1, linked=True, status='着手可')
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = gh_task.cmd_show(1)
            assert rc == 0, f'show がエラー終了した（exit {rc}）'
            assert '#1' in buf.getvalue()

        t('issue の show は今までどおり動く', _show_issue_still_works)

        def _show_issue_not_linked_dies() -> None:
            gh_task.run_gh = make_show_gh(as_pr=False, number=2, linked=False)
            with redirect_stdout(io.StringIO()):
                gh_task.cmd_show(2)

        n('Projects に載っていない issue の show は落ちる', _show_issue_not_linked_dies)

        def _show_pr_not_linked_dies() -> None:
            gh_task.run_gh = make_show_gh(as_pr=True, number=245, linked=False)
            with redirect_stdout(io.StringIO()):
                gh_task.cmd_show(245)

        n('Projects に載っていない PR の show も落ちる', _show_pr_not_linked_dies)

        # Project の在り処。
        def _discover_zero() -> None:
            def zero_projects(args):
                joined = ' '.join(args)
                if 'projectsV2' in joined:
                    body = {'data': {'repository': {'projectsV2': {'nodes': []}}}}
                    return 0, json.dumps(body), ''
                return 1, '', 'unhandled'

            gh_task.run_gh = zero_projects
            gh_task.discover_project_number()

        n('紐づく Project が 0 件なら落ちる', _discover_zero)

        def _discover_two_without_kind() -> None:
            def two_projects(args):
                joined = ' '.join(args)
                if 'projectsV2' in joined:
                    body = {'data': {'repository': {'projectsV2': {'nodes': [
                        {'number': 7, 'title': 'A', 'fields': {'nodes': []}},
                        {'number': 8, 'title': 'B', 'fields': {'nodes': []}},
                    ]}}}}
                    return 0, json.dumps(body), ''
                return 1, '', 'unhandled'

            gh_task.run_gh = two_projects
            gh_task.discover_project_number()

        n('紐づく Project が 2 件で「種別」を持つものが無ければ落ちる', _discover_two_without_kind)

        def _discover_two_one_with_kind() -> None:
            def two_projects_one_kind(args):
                joined = ' '.join(args)
                if 'projectsV2' in joined:
                    body = {'data': {'repository': {'projectsV2': {'nodes': [
                        {'number': 7, 'title': 'A',
                         'fields': {'nodes': [{'name': gh_task.KIND_FIELD}]}},
                        {'number': 8, 'title': 'B', 'fields': {'nodes': []}},
                    ]}}}}
                    return 0, json.dumps(body), ''
                return 1, '', 'unhandled'

            gh_task.run_gh = two_projects_one_kind
            number = gh_task.discover_project_number()
            assert number == 7, f'「種別」を持つ #7 を選ぶはずが #{number} になった'

        t('紐づく Project が 2 件でも「種別」を持つものが 1 つなら選べる', _discover_two_one_with_kind)

        # gh の失敗を握り潰さない。
        def _gh_failure_does_not_lie() -> None:
            gh_task.run_gh = make_erroring_gh('rate limit')
            gh_task.discover_project_number()

        n('gh の失敗はそのまま落とす（握り潰さない）', _gh_failure_does_not_lie)

        # 書く側の 1 件引きが失敗したときも「載っていない」と言わない（exit 1・
        # 「載っていない」と「取れなかった」を取り違えない）。
        def _write_path_fetch_failure_is_exit1_not_not_found() -> None:
            gh_task.run_gh = make_erroring_gh('rate limit exceeded')
            try:
                gh_task.cmd_start(999, None)
            except gh_task.GhError as exc:
                assert exc.code == 1, f'exit {exc.code}（期待 1）'
                assert '載っていない' not in str(exc), f'「載っていない」と言っている: {exc}'
                return
            raise AssertionError('落ちるべきなのに通った')

        t(
            '書く側の 1 件引きの失敗は exit 1 で、「載っていない」とは言わない',
            _write_path_fetch_failure_is_exit1_not_not_found,
        )

        # projectItems の断片が id を要求すること（H1 の再発防止）。updateProjectV2ItemFieldValue
        # は $item 無しで送ると本番で必ず exit 1 になる。id が要ることを直接見れば、断片から
        # id を消すだけで即座に FAIL する（壊して確かめた: broke_to_confirm に記録）。
        def _write_item_fragment_requests_id() -> None:
            assert re.search(r'nodes\s*\{\s*id\b', gh_task._PROJECT_ITEM_FRAGMENT), (
                'projectItems.nodes に id が無い（$item 無しで送られ、本番で exit 1 になる）'
            )

        t('projectItems の断片が id を要求する（H1 の再発防止）', _write_item_fragment_requests_id)

        # field_exists は field_id と同じく 1 回 resync してやり直す（H2 の再発防止）。
        def _field_exists_resyncs_when_missing_from_cache() -> None:
            fake = make_write_gh({}, field_defs=_fake_field_defs(include_kind=True))
            stale = {'fields': _fake_field_defs(include_kind=False)}
            with open(gh_task.FIELDS_CACHE, 'w', encoding='utf-8') as f:
                json.dump(stale, f)
            gh_task.run_gh = fake
            assert gh_task.field_exists(7, gh_task.KIND_FIELD) is True, (
                '古いキャッシュ（種別なし）に見つからなくても、resync すれば見つかるはず'
            )

        t(
            'field_exists は古いキャッシュに無い項目を 1 回 resync して見つける（種別が後から増えた checkout）',
            _field_exists_resyncs_when_missing_from_cache,
        )

        # sync 失敗でもキャッシュは壊れない。
        def _sync_failure_preserves_cache() -> None:
            gh_task.run_gh = make_write_gh({}, field_defs=_fake_field_defs(include_kind=True))
            gh_task.sync_fields(7)
            with open(gh_task.FIELDS_CACHE, 'rb') as f:
                before = f.read()
            gh_task.run_gh = make_erroring_gh('rate limit')
            _expect_exit(lambda: gh_task.sync_fields(7), 1)
            with open(gh_task.FIELDS_CACHE, 'rb') as f:
                after = f.read()
            assert before == after, 'sync の失敗でキャッシュの中身が変わった'

        t('sync の失敗はキャッシュを壊さない', _sync_failure_preserves_cache)

        # 5) 一覧の問い合わせ回数が少ないこと（ready --cost の実測は main_todo。ここでは
        # 頁数 + discover 1 + extras 1 の範囲に収まることだけを、呼び出し回数で見る）。
        def _ready_makes_few_graphql_calls() -> None:
            rows = [_fake_row(n_, status='着手可') for n_ in range(1, 31)]  # 1 頁・30 件
            board_gh = make_board_gh(rows, extras={})
            calls = {'n': 0}

            def counting_gh(args):
                calls['n'] += 1
                return board_gh(args)

            gh_task.run_gh = counting_gh
            with redirect_stdout(io.StringIO()):
                gh_task.main(['ready'])
            # discover 1 回 + items 1 頁 + extras 1 回（30 件は 1 チャンクに収まる）= 3 回
            assert calls['n'] == 3, f'graphql の呼び出しが {calls["n"]} 回（想定 3 回）'

        t('ready の問い合わせは discover + 頁 + extras の 3 回で済む（30 件・1 頁）', _ready_makes_few_graphql_calls)

        # ── approve は廃止 ──────────────────────────
        def _approve_is_abolished() -> None:
            # 承認待ちの task（親付き・親なし）と feature のどれに対しても、理由を出して
            # exit 2 で落ち、何も書かない。呼ぶ側が読む文言（「approve は廃止。feature を
            # ボードで着手可に」）も見る。
            record: list = []
            gh_task.run_gh = make_write_gh({
                601: dict(title='task', status=gh_task.PENDING_STATUS, kind='task', parent_number=999),
                602: dict(title='feature 行', status=gh_task.PENDING_STATUS, kind='feature'),
                603: dict(title='task', status=gh_task.PENDING_STATUS, kind='task'),
            }, record=record, rest_log=record)
            for number in (601, 602, 603):
                try:
                    gh_task.cmd_approve(number)
                except gh_task.GhError as exc:
                    assert exc.code == 2, f'exit {exc.code}（期待 2）'
                    assert 'approve は廃止' in str(exc), f'廃止の案内が無い: {exc}'
                    assert 'feature をボードで着手可に' in str(exc), f'ボードの案内が無い: {exc}'
                    continue
                raise AssertionError(f'#{number}: approve が通った（廃止のはず）')
            assert record == [], f'gh が呼ばれた: {record}'

        t('approve は廃止（親付き・親なしの task も feature も exit 2・gh を呼ばない）', _approve_is_abolished)

        def _approve_via_main_is_exit2() -> None:
            gh_task.run_gh = make_write_gh({})
            try:
                gh_task.main(['approve', '601'])
            except gh_task.GhError as exc:
                assert exc.code == 2 and 'approve は廃止' in str(exc), f'exit {exc.code}: {exc}'
                return
            raise AssertionError('main(["approve", ...]) が通った')

        t('main の approve も廃止の案内で exit 2', _approve_via_main_is_exit2)

        # ── set ──────
        def _set_rejects_feature_status() -> None:
            # target を着手可以外にして、承認待ち→着手可の別の守りと
            # 混同しないようにする（種別=wave のケースと対称に揃える）。
            record: list = []
            gh_task.run_gh = make_write_gh(
                {606: dict(title='feature 行', status=gh_task.READY_STATUS, kind='feature')}, record=record,
            )
            _expect_exit(lambda: gh_task.cmd_set(606, 'Status', gh_task.DONE_STATUS), 2)
            assert record == []

        t('set は種別=feature への Status の書き込みを断る', _set_rejects_feature_status)

        def _set_rejects_wave_status() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh(
                {607: dict(title='wave 行', status='着手可', kind='wave')}, record=record,
            )
            _expect_exit(lambda: gh_task.cmd_set(607, 'Status', gh_task.DONE_STATUS), 2)
            assert record == []

        t('set は種別=wave への Status の書き込みを断る', _set_rejects_wave_status)

        def _set_rejects_pending_to_ready() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh(
                {608: dict(title='task', status=gh_task.PENDING_STATUS, kind='task')}, record=record,
            )
            _expect_exit(lambda: gh_task.cmd_set(608, 'Status', gh_task.READY_STATUS), 2)
            assert record == []

        t('set は親の無い承認待ちの task を着手可にしない', _set_rejects_pending_to_ready)

        def _set_allows_pending_child_of_ready_feature() -> None:
            # 親の feature が着手可で目印の無い承認待ちの子は、set で着手可にできる。
            record: list = []
            gh_task.run_gh = make_write_gh({
                640: dict(title='task', status=gh_task.PENDING_STATUS, kind='task', parent_number=641),
                641: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
            }, record=record)
            rc = gh_task.cmd_set(640, 'Status', gh_task.READY_STATUS)
            assert rc == 0
            assert record == [('F_Status', 'O_Status_着手可')], f'着手可を書いていない: {record}'

        t(
            'set は親が着手可の feature の、目印の無い承認待ちの子を着手可にできる',
            _set_allows_pending_child_of_ready_feature,
        )

        def _set_rejects_pending_child_of_pending_feature() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh({
                642: dict(title='task', status=gh_task.PENDING_STATUS, kind='task', parent_number=643),
                643: dict(title='feature', status=gh_task.PENDING_STATUS, kind='feature'),
            }, record=record)
            _expect_exit(lambda: gh_task.cmd_set(642, 'Status', gh_task.READY_STATUS), 2)
            assert record == [], f'書き込みが起きた: {record}'

        t(
            'set は親の feature が承認待ちなら、承認待ちの子を着手可にしない（exit 2）',
            _set_rejects_pending_child_of_pending_feature,
        )

        def _set_rejects_marked_pending_child_of_ready_feature() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh({
                656: dict(
                    title=f'{gh_task.OPERATION_MARK} task', status=gh_task.PENDING_STATUS,
                    kind='task', parent_number=657,
                ),
                657: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
            }, record=record)
            _expect_exit(lambda: gh_task.cmd_set(656, 'Status', gh_task.READY_STATUS), 2)
            assert record == [], f'書き込みが起きた: {record}'

        t(
            'set は親が着手可でも、目印つきで承認待ちの task を着手可にしない（exit 2）',
            _set_rejects_marked_pending_child_of_ready_feature,
        )

        def _set_rejects_marked_title_to_ready() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh({609: dict(
                title=f'{gh_task.OPERATION_MARK} task', status=gh_task.DEP_STATUS, kind='task',
            )}, record=record)
            _expect_exit(lambda: gh_task.cmd_set(609, 'Status', gh_task.READY_STATUS), 2)
            assert record == []

        t('set は目印つき task の着手可を断る（start --approved を使うこと）', _set_rejects_marked_title_to_ready)

        def _set_rejects_ready_without_parent() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh(
                {610: dict(title='task', status=gh_task.DEP_STATUS, kind='task')}, record=record,
            )
            _expect_exit(lambda: gh_task.cmd_set(610, 'Status', gh_task.READY_STATUS), 2)
            assert record == []

        t('set は親の無い task を依存待ちから着手可にしない', _set_rejects_ready_without_parent)

        def _set_allows_ready_when_parent_ready() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh({
                611: dict(title='task', status=gh_task.HOLD_STATUS, kind='task', parent_number=700),
                700: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
            }, record=record)
            rc = gh_task.cmd_set(611, 'Status', gh_task.READY_STATUS)
            assert rc == 0
            assert record == [('F_Status', 'O_Status_着手可')]

        t('set は親の feature が着手可なら、保留から着手可にできる', _set_allows_ready_when_parent_ready)

        def _set_rejects_ready_when_parent_not_ready() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh({
                612: dict(title='task', status=gh_task.JUDGMENT_STATUS, kind='task', parent_number=701),
                701: dict(title='feature', status=gh_task.PENDING_STATUS, kind='feature'),
            }, record=record)
            _expect_exit(lambda: gh_task.cmd_set(612, 'Status', gh_task.READY_STATUS), 2)
            assert record == []

        t('set は親の feature が着手可でなければ着手可にしない', _set_rejects_ready_when_parent_not_ready)

        def _set_rejects_the_six_axes() -> None:
            # Status・種別だけを受け付ける。6 軸は名前を渡しても書かず、
            # gh も呼ばない（許す側の一覧に無いものは断る）。
            record: list = []
            gh_task.run_gh = make_write_gh(
                {613: dict(title='task', status=gh_task.PENDING_STATUS, kind='task')}, record=record,
                rest_log=record,
            )
            for axis in ('stream', 'wave', 'gate', 'deps_before', 'blocked_by_decision', 'trace'):
                _expect_exit(lambda axis=axis: gh_task.cmd_set(613, axis, 'なし'), 2)
            assert record == [], f'gh が呼ばれた: {record}'

        t('この道具では 6 軸の set を断る（exit 2・gh を呼ばない）', _set_rejects_the_six_axes)

        def _set_writes_kind() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh(
                {615: dict(title='task', status=gh_task.PENDING_STATUS, kind='task')}, record=record,
            )
            rc = gh_task.cmd_set(615, gh_task.KIND_FIELD, 'feature')
            assert rc == 0
            assert record == [(f'F_{gh_task.KIND_FIELD}', 'O_kind_feature')], record

        t('set は種別を書ける', _set_writes_kind)

        def _set_rejects_unknown_field() -> None:
            gh_task.run_gh = make_write_gh({})
            _expect_exit(lambda: gh_task.cmd_set(614, 'nosuchfield', 'x'), 2)

        t('set の未知のフィールドは exit 2 で落ちる', _set_rejects_unknown_field)

        # ── start（着手可から。目印なしで親の feature が着手可なら承認待ちからも。
        #    [操作] は --approved で承認待ちからも） ──
        def _start_rejects_unresolved_blockers_default() -> None:
            gh_task.run_gh = make_write_gh({
                620: dict(
                    title='task', status=gh_task.READY_STATUS, kind='task',
                    blockers=[(621, 'OPEN')],
                ),
            })
            _expect_exit(lambda: gh_task.cmd_start(620, None), 2)

        t('start は未完了の blocked by があれば断る（既定の形）', _start_rejects_unresolved_blockers_default)

        def _start_rejects_wave_kind() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh(
                {644: dict(title='wave 行', status=gh_task.READY_STATUS, kind='wave')}, record=record,
            )
            _expect_exit(lambda: gh_task.cmd_start(644, None), 2)
            assert record == []

        t('start は種別=wave を断る（着手可でも動かさない）', _start_rejects_wave_kind)

        def _start_rejects_feature_kind() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh(
                {645: dict(title='feature 行', status=gh_task.READY_STATUS, kind='feature')}, record=record,
            )
            _expect_exit(lambda: gh_task.cmd_start(645, None), 2)
            assert record == []

        t('start は種別=feature を断る', _start_rejects_feature_kind)

        def _start_rejects_unresolved_blockers_approved() -> None:
            gh_task.run_gh = make_write_gh({
                622: dict(
                    title=f'{gh_task.OPERATION_MARK} task', status=gh_task.PENDING_STATUS,
                    kind='task', blockers=[(623, 'OPEN')],
                ),
            })
            _expect_exit(lambda: gh_task.cmd_start(622, '2026-09-28 チャット'), 2)

        t('start --approved も未完了の blocked by があれば断る', _start_rejects_unresolved_blockers_approved)

        def _start_default_requires_ready() -> None:
            # 親の feature が着手可で、自分の blocked by も無い形で見る（親が無い・親が着手可でない
            # といった別の理由で exit 2 になって、Status の分岐の緩みを隠さないため）。
            for status in (
                gh_task.DEP_STATUS, gh_task.JUDGMENT_STATUS, gh_task.HOLD_STATUS,
                gh_task.IN_PROGRESS_STATUS, gh_task.REVIEW_STATUS, gh_task.DONE_STATUS, '',
            ):
                record: list = []
                gh_task.run_gh = make_write_gh({
                    624: dict(title='task', status=status, kind='task', parent_number=699),
                    699: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
                }, record=record)
                _expect_exit(lambda: gh_task.cmd_start(624, None), 2)
                assert record == [], (status, record)

        t(
            'start（既定の形）は親の feature が着手可でも、着手可・承認待ち以外の Status からは進めない',
            _start_default_requires_ready,
        )

        def _start_pending_child_of_ready_feature_ok() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh({
                660: dict(title='task', status=gh_task.PENDING_STATUS, kind='task', parent_number=661),
                661: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
            }, record=record)
            rc = gh_task.cmd_start(660, None)
            assert rc == 0
            assert record == [('F_Status', 'O_Status_進行中')], record

        t(
            'start（既定の形）は承認待ち・目印なし・親の feature が着手可なら進行中に進む',
            _start_pending_child_of_ready_feature_ok,
        )

        def _start_pending_child_rejects_pending_parent() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh({
                662: dict(title='task', status=gh_task.PENDING_STATUS, kind='task', parent_number=663),
                663: dict(title='feature', status=gh_task.PENDING_STATUS, kind='feature'),
            }, record=record)
            try:
                gh_task.cmd_start(662, None)
            except gh_task.GhError as exc:
                assert exc.code == 2, f'exit {exc.code}（期待 2）'
                assert '#663' in str(exc) and '今「承認待ち」' in str(exc), f'親の番号と Status が理由に無い: {exc}'
            else:
                raise AssertionError('親の feature が承認待ちなのに start が通った')
            assert record == [], f'書き込みが起きた: {record}'

        t(
            'start は親の feature が承認待ちなら、承認待ちの子を断る（理由に親の番号と今の Status）',
            _start_pending_child_rejects_pending_parent,
        )

        def _start_pending_child_rejects_no_parent() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh({
                664: dict(title='task', status=gh_task.PENDING_STATUS, kind='task'),
            }, record=record)
            _expect_exit(lambda: gh_task.cmd_start(664, None), 2)
            assert record == [], f'書き込みが起きた: {record}'

        t('start は親の無い承認待ちの task を断る（exit 2）', _start_pending_child_rejects_no_parent)

        def _start_pending_child_rejects_non_feature_parent() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh({
                665: dict(title='task', status=gh_task.PENDING_STATUS, kind='task', parent_number=666),
                666: dict(title='wave', status=gh_task.READY_STATUS, kind='wave'),  # Status は満たし、種別だけで断る
            }, record=record)
            _expect_exit(lambda: gh_task.cmd_start(665, None), 2)
            assert record == [], f'書き込みが起きた: {record}'

        t('start は親の種別が feature でない承認待ちの task を断る（exit 2）', _start_pending_child_rejects_non_feature_parent)

        def _start_pending_child_rejects_blocked_parent() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh({
                667: dict(title='task', status=gh_task.PENDING_STATUS, kind='task', parent_number=668),
                668: dict(
                    title='feature', status=gh_task.READY_STATUS, kind='feature',
                    blockers=[(669, 'OPEN')],
                ),
            }, record=record)
            try:
                gh_task.cmd_start(667, None)
            except gh_task.GhError as exc:
                assert exc.code == 2, f'exit {exc.code}（期待 2）'
                assert '#668' in str(exc) and '#669' in str(exc), f'親と blocked by の番号が理由に無い: {exc}'
            else:
                raise AssertionError('親の feature に未完了の blocked by があるのに start が通った')
            assert record == [], f'書き込みが起きた: {record}'

        t(
            'start は親の feature に未完了の blocked by があれば、承認待ちの子を断る（exit 2）',
            _start_pending_child_rejects_blocked_parent,
        )

        def _start_marked_pending_requires_approved() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh({
                670: dict(
                    title=f'{gh_task.OPERATION_MARK} task', status=gh_task.PENDING_STATUS,
                    kind='task', parent_number=671,
                ),
                671: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
            }, record=record)
            try:
                gh_task.cmd_start(670, None)
            except gh_task.GhError as exc:
                assert exc.code == 2, f'exit {exc.code}（期待 2）'
                assert '--approved' in str(exc), f'start --approved の案内が無い: {exc}'
            else:
                raise AssertionError('[操作] の承認待ちが --approved なしで進んだ')
            assert record == [], f'書き込みが起きた: {record}'

        t(
            'start は [操作] で承認待ちの task を、親が着手可でも --approved なしでは断る（exit 2）',
            _start_marked_pending_requires_approved,
        )

        def _start_user_marked_pending_is_rejected() -> None:
            gh_task.run_gh = make_write_gh({
                672: dict(
                    title=f'{gh_task.USER_MARK} task', status=gh_task.PENDING_STATUS,
                    kind='task', parent_number=673,
                ),
                673: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
            })
            _expect_exit(lambda: gh_task.cmd_start(672, None), 2)

        t('start は [User] で承認待ちの task を、親が着手可でも断る（exit 2）', _start_user_marked_pending_is_rejected)

        def _start_approved_requires_mark() -> None:
            gh_task.run_gh = make_write_gh({
                625: dict(title='task（目印なし）', status=gh_task.PENDING_STATUS, kind='task'),
            })
            _expect_exit(lambda: gh_task.cmd_start(625, '出どころ'), 2)

        t(f'start --approved は {gh_task.OPERATION_MARK} の目印が無ければ断る', _start_approved_requires_mark)

        def _start_approved_writes_and_appends_body() -> None:
            record: list = []
            rest_calls: list = []

            def rest_handler(method, path, body):
                rest_calls.append((method, path, body))
                return {}

            gh_task.run_gh = make_write_gh(
                {626: dict(
                    title=f'{gh_task.OPERATION_MARK} task', status=gh_task.PENDING_STATUS,
                    kind='task', body='元の本文', parent_number=627,
                ), 627: dict(title='feature', status=gh_task.READY_STATUS, kind='feature')},
                record=record, rest_handler=rest_handler,
            )
            rc = gh_task.cmd_start(626, '2026-09-28 チャット #1')
            assert rc == 0
            assert record == [('F_Status', 'O_Status_進行中')]
            patches = [c for c in rest_calls if c[0] == 'PATCH']
            assert len(patches) == 1, f'本文の PATCH が 1 回のはず: {rest_calls}'
            assert '出どころ: 2026-09-28 チャット #1' in patches[0][2]['body']
            assert '元の本文' in patches[0][2]['body']

        t(
            'start --approved は [操作] の task を進行中にし、本文に出どころを書く',
            _start_approved_writes_and_appends_body,
        )

        def _start_approved_rejects_non_ready_pending_status() -> None:
            # --approved が許すのは着手可・承認待ちからだけ。
            record: list = []
            rest_calls: list = []
            gh_task.run_gh = make_write_gh(
                {646: dict(
                    title=f'{gh_task.OPERATION_MARK} task', status=gh_task.JUDGMENT_STATUS,
                    kind='task',
                )},
                record=record, rest_handler=lambda m, p, b: rest_calls.append((m, p, b)) or {},
            )
            _expect_exit(lambda: gh_task.cmd_start(646, '出どころ'), 2)
            assert record == []
            assert rest_calls == [], f'本文への PATCH まで進んでしまった: {rest_calls}'

        t(
            'start --approved は判断待ちからは進めない（着手可・承認待ちだけ）',
            _start_approved_rejects_non_ready_pending_status,
        )

        def _start_default_ready_ok() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh(
                {627: dict(title='task', status=gh_task.READY_STATUS, kind='task')}, record=record,
            )
            rc = gh_task.cmd_start(627, None)
            assert rc == 0
            assert record == [('F_Status', 'O_Status_進行中')]

        t('start（既定の形）は着手可から進行中に進む（親を見ない）', _start_default_ready_ok)

        def _start_rejects_closed_issue() -> None:
            # CLOSED の issue は start で進めない（既定の形も --approved も。reopen を案内する）。
            record: list = []
            gh_task.run_gh = make_write_gh({
                671: dict(
                    title='task', status=gh_task.PENDING_STATUS, kind='task', state='CLOSED',
                    parent_number=672,
                ),
                672: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
                673: dict(title='task', status=gh_task.READY_STATUS, kind='task', state='CLOSED'),
                674: dict(
                    title=f'{gh_task.OPERATION_MARK} task', status=gh_task.PENDING_STATUS,
                    kind='task', state='CLOSED',
                ),
            }, record=record)
            for number, approved in ((671, None), (673, None), (674, '出どころ')):
                try:
                    gh_task.cmd_start(number, approved)
                except gh_task.GhError as exc:
                    assert exc.code == 2 and 'reopen' in str(exc), f'#{number}: {exc}'
                else:
                    raise AssertionError(f'#{number}: 閉じている issue を start が進めた')
            assert record == [], f'書き込みが起きた: {record}'

        t('start は閉じている issue を断る（既定の形も --approved も・reopen を案内）', _start_rejects_closed_issue)

        def _set_rejects_closed_issue_to_ready_or_in_progress() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh({
                675: dict(
                    title='task', status=gh_task.PENDING_STATUS, kind='task', state='CLOSED',
                    parent_number=676,
                ),
                676: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
                677: dict(title='task', status=gh_task.REVIEW_STATUS, kind='task', state='CLOSED'),
            }, record=record)
            _expect_exit(lambda: gh_task.cmd_set(675, 'Status', gh_task.READY_STATUS), 2)
            _expect_exit(lambda: gh_task.cmd_set(677, 'Status', gh_task.IN_PROGRESS_STATUS), 2)
            assert record == [], f'書き込みが起きた: {record}'
            # 着手可・進行中以外の値は、閉じていても書ける（完了へ直すなど）。
            assert gh_task.cmd_set(677, 'Status', gh_task.DONE_STATUS) == 0
            assert record == [('F_Status', 'O_Status_完了')], record

        t('set は閉じている issue を着手可・進行中にしない（それ以外の値は書ける）', _set_rejects_closed_issue_to_ready_or_in_progress)

        def _set_ready_rejects_blockers_and_non_feature_parent() -> None:
            # start の承認待ちからの経路と同じ判定を通る（set → start の 2 手で抜けない）。
            cases = {
                'own blocked by': {
                    681: dict(title='task', status=gh_task.DEP_STATUS, kind='task', parent_number=682,
                              blockers=[(689, 'OPEN')]),
                    682: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
                },
                'feature blocked by': {
                    681: dict(title='task', status=gh_task.PENDING_STATUS, kind='task', parent_number=682),
                    682: dict(title='feature', status=gh_task.READY_STATUS, kind='feature',
                              blockers=[(689, 'OPEN')]),
                },
                'parent is a wave': {
                    681: dict(title='task', status=gh_task.PENDING_STATUS, kind='task', parent_number=682),
                    682: dict(title='wave', status=gh_task.READY_STATUS, kind='wave'),
                },
            }
            for label, specs in cases.items():
                record: list = []
                gh_task.run_gh = make_write_gh(specs, record=record)
                _expect_exit(lambda: gh_task.cmd_set(681, 'Status', gh_task.READY_STATUS), 2)
                assert record == [], (label, record)
            # 閉じた blocker は止めない。
            record = []
            gh_task.run_gh = make_write_gh({
                681: dict(title='task', status=gh_task.PENDING_STATUS, kind='task', parent_number=682,
                          blockers=[(689, 'CLOSED')]),
                682: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
            }, record=record)
            assert gh_task.cmd_set(681, 'Status', gh_task.READY_STATUS) == 0
            assert record == [('F_Status', 'O_Status_着手可')], record

        t(
            'set は着手可へ、自分・親の feature の未完了の blocked by と、親の種別が feature でないことを断る',
            _set_ready_rejects_blockers_and_non_feature_parent,
        )

        def _set_in_progress_only_from_review_or_later() -> None:
            # 進行中へ set で書けるのは、レビュー中・進行中・完了からだけ（それ以外は start）。
            for status in (
                gh_task.PENDING_STATUS, gh_task.JUDGMENT_STATUS, gh_task.DEP_STATUS,
                gh_task.HOLD_STATUS, gh_task.READY_STATUS, '',
            ):
                record: list = []
                gh_task.run_gh = make_write_gh({
                    683: dict(title='task', status=status, kind='task', parent_number=684),
                    684: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
                }, record=record)
                try:
                    gh_task.cmd_set(683, 'Status', gh_task.IN_PROGRESS_STATUS)
                except gh_task.GhError as exc:
                    assert exc.code == 2 and 'start' in str(exc), (status, str(exc))
                else:
                    raise AssertionError(f'{status} から set で進行中になった')
                assert record == [], (status, record)
            # 目印つき・親が承認待ち・自分に open の blocked by がある承認待ちの task も同じ。
            record = []
            gh_task.run_gh = make_write_gh({
                685: dict(title='[User] task', status=gh_task.PENDING_STATUS, kind='task',
                          parent_number=686, blockers=[(689, 'OPEN')]),
                686: dict(title='feature', status=gh_task.PENDING_STATUS, kind='feature'),
            }, record=record)
            _expect_exit(lambda: gh_task.cmd_set(685, 'Status', gh_task.IN_PROGRESS_STATUS), 2)
            assert record == [], record
            for status in (gh_task.REVIEW_STATUS, gh_task.IN_PROGRESS_STATUS, gh_task.DONE_STATUS):
                record = []
                gh_task.run_gh = make_write_gh(
                    {687: dict(title='task', status=status, kind='task')}, record=record,
                )
                assert gh_task.cmd_set(687, 'Status', gh_task.IN_PROGRESS_STATUS) == 0, status
                assert record == [('F_Status', 'O_Status_進行中')], (status, record)

        t(
            'set は承認待ち・判断待ち・依存待ち・保留・着手可から進行中を書かない（start を案内）。レビュー中・進行中・完了からは書ける',
            _set_in_progress_only_from_review_or_later,
        )

        NOT_IN_PROGRESS_STATUSES = (
            gh_task.PENDING_STATUS, gh_task.JUDGMENT_STATUS, gh_task.DEP_STATUS,
            gh_task.HOLD_STATUS, gh_task.READY_STATUS, '',
        )

        def _expect_refused_without_write(fn, record: list, label: str) -> str:
            try:
                fn()
            except gh_task.GhError as exc:
                assert exc.code == 2, f'{label}: exit {exc.code}（期待 2）: {exc}'
                assert record == [], f'{label}: 断ったのに書いた: {record}'
                return str(exc)
            raise AssertionError(f'{label}: 断るべきなのに通った')

        def _set_review_or_done_only_from_in_progress_or_later() -> None:
            # (a) set レビュー中・完了は、承認待ち・判断待ち・依存待ち・保留・着手可・空から exit 2。
            for status in NOT_IN_PROGRESS_STATUSES:
                for value in (gh_task.REVIEW_STATUS, gh_task.DONE_STATUS):
                    record: list = []
                    gh_task.run_gh = make_write_gh(
                        {801: dict(title='task', status=status, kind='task', parent_number=802),
                         802: dict(title='feature', status=gh_task.READY_STATUS, kind='feature')},
                        record=record,
                    )
                    message = _expect_refused_without_write(
                        lambda: gh_task.cmd_set(801, 'Status', value), record, f'{status}→{value}',
                    )
                    assert '進行中の task からだけ書ける' in message and 'start を使う' in message, message
            # (d) 進行中・レビュー中・完了からは、レビュー中・完了を書ける。
            for status in (gh_task.IN_PROGRESS_STATUS, gh_task.REVIEW_STATUS, gh_task.DONE_STATUS):
                for value in (gh_task.REVIEW_STATUS, gh_task.DONE_STATUS):
                    record = []
                    gh_task.run_gh = make_write_gh(
                        {803: dict(title='task', status=status, kind='task')}, record=record,
                    )
                    with redirect_stdout(io.StringIO()):
                        assert gh_task.cmd_set(803, 'Status', value) == 0, (status, value)
                    assert record == [('F_Status', f'O_Status_{value}')], (status, value, record)

        t(
            'set は承認待ち・判断待ち・依存待ち・保留・着手可・空から、レビュー中・完了を書かない。進行中・レビュー中・完了からは書ける',
            _set_review_or_done_only_from_in_progress_or_later,
        )

        def _review_only_from_in_progress_or_later() -> None:
            # (b) review も承認待ちなどから exit 2。(c) 進行中からは通る。
            for status in NOT_IN_PROGRESS_STATUSES:
                record: list = []
                gh_task.run_gh = make_write_gh(
                    {804: dict(title='task', status=status, kind='task')}, record=record,
                )
                _expect_refused_without_write(lambda: gh_task.cmd_review(804), record, f'review（{status}）')
            for status in (gh_task.IN_PROGRESS_STATUS, gh_task.REVIEW_STATUS, gh_task.DONE_STATUS):
                record = []
                gh_task.run_gh = make_write_gh(
                    {805: dict(title='task', status=status, kind='task')}, record=record,
                )
                with redirect_stdout(io.StringIO()):
                    assert gh_task.cmd_review(805) == 0, status
                assert record == [('F_Status', 'O_Status_レビュー中')], (status, record)

        t('review は承認待ち・判断待ち・依存待ち・保留・着手可・空から exit 2。進行中からは通る', _review_only_from_in_progress_or_later)

        def _operation_mark_cannot_reach_in_progress_in_two_steps() -> None:
            # (e) [操作] の承認待ち → set レビュー中 → set 進行中 の 2 手は、1 手目で止まる
            # （2 手目は Status が変わらないので、同じく止まる）。done・reopen は今のまま。
            record: list = []
            gh_task.run_gh = make_write_gh(
                {806: dict(title=f'{gh_task.OPERATION_MARK} task', status=gh_task.PENDING_STATUS,
                           kind='task', parent_number=807),
                 807: dict(title='feature', status=gh_task.READY_STATUS, kind='feature')},
                record=record,
            )
            _expect_refused_without_write(
                lambda: gh_task.cmd_set(806, 'Status', gh_task.REVIEW_STATUS), record, '1 手目',
            )
            message = _expect_refused_without_write(
                lambda: gh_task.cmd_set(806, 'Status', gh_task.IN_PROGRESS_STATUS), record, '2 手目',
            )
            assert 'start --approved' in message, message
            record = []
            gh_task.run_gh = make_write_gh(
                {808: dict(title='task', status=gh_task.PENDING_STATUS, kind='task')}, record=record,
                rest_handler=lambda m, p, b: {},
            )
            with redirect_stdout(io.StringIO()):
                assert gh_task.cmd_done(808, None) == 0  # done は今の Status を問わない
            assert record == [('F_Status', 'O_Status_完了')], record
            for target in (gh_task.REVIEW_STATUS, gh_task.DONE_STATUS):
                record = []
                gh_task.run_gh = make_write_gh(
                    {809: dict(title='task', status=gh_task.DEP_STATUS, kind='task', state='CLOSED')},
                    record=record, rest_handler=lambda m, p, b: {},
                )
                with redirect_stdout(io.StringIO()):
                    assert gh_task.cmd_reopen(809, target) == 0, target  # reopen も今のまま
                assert record == [('F_Status', f'O_Status_{target}')], (target, record)

        t(
            '[操作] の承認待ちから、set レビュー中 → set 進行中 の 2 手で進行中にできない（1 手目で止まる）。done・reopen は変わらない',
            _operation_mark_cannot_reach_in_progress_in_two_steps,
        )

        def _user_mark_in_progress_message_does_not_point_to_start() -> None:
            # (4) [User] の task へ set 進行中: start を案内せず、道具では進行中にしないと出す。
            for status in (gh_task.PENDING_STATUS, gh_task.READY_STATUS):
                record: list = []
                gh_task.run_gh = make_write_gh(
                    {810: dict(title=f'{gh_task.USER_MARK} 手作業', status=status, kind='task')},
                    record=record,
                )
                message = _expect_refused_without_write(
                    lambda: gh_task.cmd_set(810, 'Status', gh_task.IN_PROGRESS_STATUS), record, status,
                )
                assert '道具では進行中にしない（ユーザーの手作業の task）' in message, message
                assert 'start' not in message, message

        t('set は [User] の task を進行中にせず、start ではなく「道具では進行中にしない」と案内する', _user_mark_in_progress_message_does_not_point_to_start)

        def _decision_rejects_non_task_kind_child() -> None:
            # 種別が設計メモの子は、align が動かさないので、start・set も通さない。
            for status in (gh_task.PENDING_STATUS, gh_task.HOLD_STATUS):
                record: list = []
                gh_task.run_gh = make_write_gh({
                    695: dict(title='memo', status=status, kind=gh_task.DESIGN_MEMO_KIND, parent_number=696),
                    696: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
                }, record=record)
                _expect_exit(lambda: gh_task.cmd_set(695, 'Status', gh_task.READY_STATUS), 2)
                if status == gh_task.PENDING_STATUS:
                    _expect_exit(lambda: gh_task.cmd_start(695, None), 2)
                assert record == [], (status, record)

        t('set（→ 着手可）・start は、種別が設計メモの子を通さない（align と同じ）', _decision_rejects_non_task_kind_child)

        def _reopen_rejects_open_blockers() -> None:
            # reopen で着手可・進行中にするとき、自分の未完了の blocked by があれば断る。
            for target in (gh_task.READY_STATUS, gh_task.IN_PROGRESS_STATUS):
                record: list = []
                gh_task.run_gh = make_write_gh({
                    691: dict(
                        title='task', status=gh_task.DONE_STATUS, kind='task', state='CLOSED',
                        parent_number=692, blockers=[(699, 'OPEN')],
                    ),
                    692: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
                }, record=record)
                _expect_exit(lambda: gh_task.cmd_reopen(691, target), 2)
                assert record == [], (target, record)

        t('reopen は着手可・進行中へ、自分の未完了の blocked by があれば断る', _reopen_rejects_open_blockers)

        def _new_announcement_matches_start() -> None:
            # 案内が出てはいけない形（start が断る形）では出さず、断られる理由を出す。
            def run(title: str, specs: dict, extra_args: list[str] | None = None) -> str:
                created = {'number': 931, 'id': 931931, 'node_id': 'X931'}

                def rest_handler(method, path, body):
                    if method == 'POST' and path == f'repos/{gh_task.REPO}/issues':
                        return created
                    if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/931':
                        return {'milestone': None, 'body': ''}
                    if method == 'GET' and re.search(r'/issues/\d+$', path):
                        return {'sub_issues_summary': {'total': 1}}
                    return {}

                gh_task.run_gh = make_write_gh(specs, rest_handler=rest_handler)
                out = io.StringIO()
                with redirect_stdout(out):
                    assert gh_task.cmd_new([title, '--parent', '932'] + (extra_args or [])) == 0
                return out.getvalue()

            feature_ok = dict(title='feature', status=gh_task.READY_STATUS, kind='feature')
            plain = dict(title='t', status=gh_task.PENDING_STATUS, kind='')
            hint = '`hirai-task start 931` で着手できる'
            out = run('t', {931: plain, 932: feature_ok})
            assert hint in out, f'通る形で案内が出ない: {out!r}'
            for label, specs, title in (
                ('blocked by つき', {931: dict(plain, blockers=[(940, 'OPEN')]), 932: feature_ok}, 't'),
                ('親の feature に blocked by', {
                    931: plain, 932: dict(feature_ok, blockers=[(940, 'OPEN')])}, 't'),
                ('親が承認待ち', {
                    931: plain, 932: dict(feature_ok, status=gh_task.PENDING_STATUS)}, 't'),
                ('[User]', {931: plain, 932: feature_ok}, '[User] t'),
                ('[操作]', {931: plain, 932: feature_ok}, f'{gh_task.OPERATION_MARK} t'),
            ):
                out = run(title, specs)
                assert 'で着手できる' not in out, (label, out)
                if label in ('blocked by つき', '親の feature に blocked by'):
                    assert 'いまは着手できない' in out and '#940' in out, (label, out)

        t(
            'new の着手の案内は、start が断る形（blocked by・親が承認待ち・目印つき）では出さず、断られる理由を出す',
            _new_announcement_matches_start,
        )

        # ── done / reopen / review ───────────────────────────────────
        def _done_writes_and_closes() -> None:
            record: list = []
            rest_calls: list = []

            def rest_handler(method, path, body):
                rest_calls.append((method, path, body))
                return {}

            gh_task.run_gh = make_write_gh(
                {630: dict(title='task', status=gh_task.REVIEW_STATUS)},
                record=record, rest_handler=rest_handler,
            )
            rc = gh_task.cmd_done(630, None)
            assert rc == 0
            assert record == [('F_Status', 'O_Status_完了')]
            patches = [c for c in rest_calls if c[0] == 'PATCH']
            assert patches and patches[0][2].get('state_reason') == 'completed'

        t('done は Status=完了 を書き、completed で close する', _done_writes_and_closes)

        def _done_rejects_wave_kind() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh(
                {647: dict(title='wave 行', status=gh_task.REVIEW_STATUS, kind='wave')}, record=record,
            )
            _expect_exit(lambda: gh_task.cmd_done(647, None), 2)
            assert record == []

        t('done は種別=wave を断る（親を閉じるのは close-parents の役目）', _done_rejects_wave_kind)

        def _done_not_planned() -> None:
            rest_calls: list = []

            def rest_handler(method, path, body):
                rest_calls.append((method, path, body))
                return {}

            gh_task.run_gh = make_write_gh(
                {631: dict(title='task', status=gh_task.READY_STATUS)}, rest_handler=rest_handler,
            )
            rc = gh_task.cmd_done(631, '不採用と決定（2026-09-28）')
            assert rc == 0
            patches = [c for c in rest_calls if c[0] == 'PATCH']
            comments = [c for c in rest_calls if c[0] == 'POST' and 'comments' in c[1]]
            assert patches and patches[0][2].get('state_reason') == 'not_planned'
            assert comments, 'コメントが投稿されていない'
            assert '<!-- ai -->' in comments[0][2]['body'], (
                'AI の印（<!-- ai -->）が無い。comments がユーザー発言と誤認する'
            )

        t('done --not-planned は理由をコメントし、not_planned で close する', _done_not_planned)

        def _reopen_reopens_and_writes_status() -> None:
            record: list = []
            rest_calls: list = []

            def rest_handler(method, path, body):
                rest_calls.append((method, path, body))
                return {}

            gh_task.run_gh = make_write_gh(
                {632: dict(title='task', status=gh_task.DONE_STATUS, state='CLOSED')},
                record=record, rest_handler=rest_handler,
            )
            rc = gh_task.cmd_reopen(632, gh_task.IN_PROGRESS_STATUS)
            assert rc == 0
            assert record == [('F_Status', 'O_Status_進行中')]
            patches = [c for c in rest_calls if c[0] == 'PATCH']
            assert patches and patches[0][2].get('state') == 'open'

        t('reopen は issue を開き直し、同じ操作で Status も書く', _reopen_reopens_and_writes_status)

        def _reopen_rejects_unknown_status() -> None:
            gh_task.run_gh = make_write_gh({633: dict(title='task', status=gh_task.DONE_STATUS)})
            _expect_exit(lambda: gh_task.cmd_reopen(633, 'そんな Status'), 2)

        t('reopen は未知の Status を断る', _reopen_rejects_unknown_status)

        # reopen は set の守りを回避する経路になって
        # いた。開いている issue への reopen・種別=feature への reopen・承認待ち→着手可の
        # reopen を断ることを見る（守りを外すと FAIL することを実装前に確認済み・broke_to_confirm）。
        def _reopen_rejects_already_open_item() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh(
                {653: dict(
                    title='承認待ち task', status=gh_task.PENDING_STATUS, kind='task', state='OPEN',
                )},
                record=record,
            )
            _expect_exit(lambda: gh_task.cmd_reopen(653, gh_task.READY_STATUS), 2)
            assert record == [], f'開いている issue に書き込んでしまった: {record}'

        t(
            'reopen は既に開いている issue を断る（開いた承認待ちへの reopen 着手可を断る）',
            _reopen_rejects_already_open_item,
        )

        def _reopen_rejects_feature_kind() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh(
                {654: dict(
                    title='feature 行', status=gh_task.PENDING_STATUS, kind='feature', state='CLOSED',
                )},
                record=record,
            )
            _expect_exit(lambda: gh_task.cmd_reopen(654, gh_task.READY_STATUS), 2)
            assert record == []

        t('reopen は種別=feature への着手可を断る', _reopen_rejects_feature_kind)

        def _reopen_rejects_pending_to_ready_even_when_closed() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh(
                {655: dict(
                    title='task', status=gh_task.PENDING_STATUS, kind='task', state='CLOSED',
                )},
                record=record,
            )
            _expect_exit(lambda: gh_task.cmd_reopen(655, gh_task.READY_STATUS), 2)
            assert record == []

        t(
            'reopen は親の無い承認待ちの task を着手可で開き直せない（set と同じ守りを通す）',
            _reopen_rejects_pending_to_ready_even_when_closed,
        )

        def _reopen_allows_pending_child_of_ready_feature() -> None:
            # reopen は set と同じ守りを通る。親が着手可で目印の無い承認待ちの子は、
            # set と同じく着手可で開き直せる。
            record: list = []
            rest_calls: list = []
            gh_task.run_gh = make_write_gh({
                658: dict(
                    title='task', status=gh_task.PENDING_STATUS, kind='task', state='CLOSED',
                    parent_number=659,
                ),
                659: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
            }, record=record, rest_handler=lambda m, p, b: rest_calls.append((m, p, b)) or {})
            rc = gh_task.cmd_reopen(658, gh_task.READY_STATUS)
            assert rc == 0
            assert record == [('F_Status', 'O_Status_着手可')], record
            assert [c for c in rest_calls if c[0] == 'PATCH' and c[2].get('state') == 'open'], rest_calls

        t(
            'reopen は set と同じ守りで、親が着手可の feature の承認待ちの子を着手可で開き直せる',
            _reopen_allows_pending_child_of_ready_feature,
        )

        def _review_writes_status() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh(
                {634: dict(title='task', status=gh_task.IN_PROGRESS_STATUS)}, record=record,
            )
            rc = gh_task.cmd_review(634)
            assert rc == 0
            assert record == [('F_Status', 'O_Status_レビュー中')]

        t('review は Status=レビュー中 を書く（予備）', _review_writes_status)

        def _review_rejects_wave_kind() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh(
                {648: dict(title='wave 行', status=gh_task.IN_PROGRESS_STATUS, kind='wave')},
                record=record,
            )
            _expect_exit(lambda: gh_task.cmd_review(648), 2)
            assert record == []

        t('review は種別=wave を断る', _review_rejects_wave_kind)

        # ── add（既存の issue を Projects に載せる・冪等） ─────
        def _add_noop_when_already_has_status() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh(
                {635: dict(title='task', status=gh_task.READY_STATUS)}, record=record,
            )
            rc = gh_task.cmd_add(635)
            assert rc == 0
            assert record == [], f'既に載っているのに書き込んだ: {record}'

        t('add は既に Status がある issue には何もしない（冪等）', _add_noop_when_already_has_status)

        def _add_creates_item_for_not_found_issue() -> None:
            record: list = []
            rest_calls: list = []

            def rest_handler(method, path, body):
                rest_calls.append((method, path, body))
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/636':
                    return {'id': 424242}
                if method == 'POST' and 'projectsV2/7/items' in path:
                    return {'id': 5001}
                return {}

            gh_task.run_gh = make_write_gh(
                {}, record=record, rest_handler=rest_handler,
                rest_items={636: [{'id': 1636, 'content': {'number': 636}}]},
            )
            # add() は 2 回 fetch_write_item を呼ぶ（見つからない→REST で入れる→もう一度読む）ので、
            # 2 回目の呼び出しでは載っている前提で答える偽 gh に切り替える必要がある。
            calls = {'n': 0}
            base_gh = gh_task.run_gh

            def sequenced_gh(args, input_text=None):
                joined = ' '.join(args)
                if 'issue(number:$number) {' in joined:
                    calls['n'] += 1
                    if calls['n'] == 1:
                        return 0, json.dumps(_write_item_body(found=False)), ''
                    return 0, json.dumps(_write_item_body(title='task', status='')), ''
                return base_gh(args, input_text)

            gh_task.run_gh = sequenced_gh
            rc = gh_task.cmd_add(636)
            assert rc == 0
            item_add_calls = [c for c in rest_calls if c[0] == 'POST' and 'projectsV2/7/items' in c[1]]
            assert item_add_calls, 'REST の item-add が呼ばれていない'
            assert record == [('F_Status', 'O_Status_承認待ち')], f'承認待ちを書いていない: {record}'

        t('add は載っていない issue を REST で Project に入れ、承認待ちを書く', _add_creates_item_for_not_found_issue)

        # ── 既存の行への書き込みは REST ─────────────
        def _existing_row_writes_never_use_graphql_mutation() -> None:
            specs = {
                701: dict(title='task', status=gh_task.PENDING_STATUS, kind='task'),
                702: dict(title='task', status=gh_task.READY_STATUS, kind='task'),
                703: dict(title='task', status=gh_task.IN_PROGRESS_STATUS, kind='task'),
                704: dict(title='task', status=gh_task.READY_STATUS, kind='task'),
                705: dict(title='task', status=gh_task.IN_PROGRESS_STATUS, kind='task', state='CLOSED'),
            }
            record: list = []
            gql: list = []
            rest_log: list = []
            gh_task.run_gh = make_write_gh(
                specs, record=record, graphql_writes=gql, rest_log=rest_log,
                rest_handler=lambda m, p, b: {},
            )
            with redirect_stdout(io.StringIO()):
                assert gh_task.cmd_set(701, 'Status', gh_task.DEP_STATUS) == 0
                assert gh_task.cmd_set(702, gh_task.KIND_FIELD, 'task') == 0
                assert gh_task.cmd_set(702, 'Status', gh_task.DEP_STATUS) == 0
                assert gh_task.cmd_start(702, None) == 0
                assert gh_task.cmd_review(703) == 0
                assert gh_task.cmd_done(704, None) == 0
                assert gh_task.cmd_reopen(705, gh_task.IN_PROGRESS_STATUS) == 0
            assert gql == [], f'GraphQL の updateProjectV2ItemFieldValue を呼んだ: {gql}'
            assert len(record) == 7, f'REST の PATCH が 7 回でない: {record}'
            lookups = [c for c in rest_log if c[0] == 'GET' and '?q=%23' in c[1]]
            assert len(lookups) == 7, f'issue 番号から item id を引いていない: {rest_log}'

        t(
            'set・start・review・done・reopen は REST（?q=#<番号> → PATCH）で書き、GraphQL の mutation を呼ばない',
            _existing_row_writes_never_use_graphql_mutation,
        )

        def _existing_row_write_uses_users_path_for_user_owner() -> None:
            rest_log: list = []
            record: list = []
            gh_task.run_gh = make_write_gh(
                {706: dict(title='task', status=gh_task.PENDING_STATUS, kind='task')},
                record=record, rest_log=rest_log, owner_typename='User',
            )
            with redirect_stdout(io.StringIO()):
                assert gh_task.cmd_set(706, 'Status', gh_task.DEP_STATUS) == 0
            assert rest_log and all(p.startswith('users/') for _m, p in rest_log), rest_log
            assert record == [('F_Status', 'O_Status_依存待ち')], record

        t('owner が user なら REST の URL は users/ になる', _existing_row_write_uses_users_path_for_user_owner)

        def _rest_item_id_zero_items_exits_1() -> None:
            record: list = []
            gh_task.run_gh = make_write_gh(
                {707: dict(title='task', status=gh_task.PENDING_STATUS, kind='task')},
                record=record, rest_items={707: []},
            )
            _expect_exit(lambda: gh_task.cmd_set(707, 'Status', gh_task.DEP_STATUS), 1)
            assert record == [], f'居ない行へ書いた: {record}'

        t('REST の検索が 0 件なら「Project に居ない」で exit 1（書かない）', _rest_item_id_zero_items_exits_1)

        def _rest_item_id_two_items_narrows_by_repo_or_exits_2() -> None:
            spec = {708: dict(title='task', status=gh_task.PENDING_STATUS, kind='task')}
            two = [{'id': 11, 'content': {'number': 708}}, {'id': 12, 'content': {'number': 708}}]
            # repo: で 1 件に絞れるなら、その 1 件へ書く
            rest_log: list = []
            gh_task.run_gh = make_write_gh(
                spec, rest_items={708: lambda q: [two[1]] if q.startswith('repo:') else two},
                rest_log=rest_log,
            )
            with redirect_stdout(io.StringIO()):
                assert gh_task.cmd_set(708, 'Status', gh_task.DEP_STATUS) == 0
            assert [c for c in rest_log if c[0] == 'PATCH' and c[1].split('?')[0].endswith('/items/12')], rest_log
            # 絞っても 2 件なら書かず exit 2
            record: list = []
            gh_task.run_gh = make_write_gh(spec, record=record, rest_items={708: two})
            _expect_exit(lambda: gh_task.cmd_set(708, 'Status', gh_task.DEP_STATUS), 2)
            assert record == [], f'複数候補なのに書いた: {record}'

        t(
            'REST の検索が 2 件以上なら repo: で絞り、それでも複数なら候補を出して exit 2（書かない）',
            _rest_item_id_two_items_narrows_by_repo_or_exits_2,
        )

        def _rest_item_id_retries_when_search_lags() -> None:
            # GraphQL では居るのに、1 回目の ?q= が 0 件（検索への反映の遅れ）。2 回目で出る
            calls = {'n': 0}
            sleeps: list = []

            def lagging(_q):
                calls['n'] += 1
                return [] if calls['n'] == 1 else [{'id': 4711, 'content': {'number': 709}}]

            record: list = []
            rest_log: list = []
            gh_task.run_gh = make_write_gh(
                {709: dict(title='task', status=gh_task.PENDING_STATUS, kind='task')},
                record=record, rest_items={709: lagging}, rest_log=rest_log,
            )
            orig = gh_task.sleep_fn
            gh_task.sleep_fn = sleeps.append
            try:
                with redirect_stdout(io.StringIO()):
                    assert gh_task.cmd_set(709, 'Status', gh_task.DEP_STATUS) == 0
            finally:
                gh_task.sleep_fn = orig
            assert sleeps == [gh_task._ITEM_LOOKUP_DELAY_SECONDS], f'待っていない: {sleeps}'
            assert record == [('F_Status', 'O_Status_依存待ち')], record
            assert any(m == 'PATCH' and p.endswith('/items/4711') for m, p in rest_log), rest_log

        t('REST の検索が 1 回 0 件でも、引き直して 2 回目で出れば書く（反映の遅れ）', _rest_item_id_retries_when_search_lags)

        def _rest_item_id_ignores_other_repo_single_hit() -> None:
            record: list = []
            other = [{'id': 31, 'content': {
                'number': 710, 'repository_url': 'https://api.github.com/repos/someone/else',
            }}]
            gh_task.run_gh = make_write_gh(
                {710: dict(title='task', status=gh_task.PENDING_STATUS, kind='task')},
                record=record, rest_items={710: other},
            )
            _expect_exit(lambda: gh_task.cmd_set(710, 'Status', gh_task.DEP_STATUS), 1)
            assert record == [], f'他リポの行へ書いた: {record}'

        t('REST の検索が他リポの同じ番号を 1 件だけ返しても、その行へは書かない', _rest_item_id_ignores_other_repo_single_hit)

        def _rest_write_uses_rest_field_and_option_ids() -> None:
            # PATCH に渡る id は REST の整数の field id と REST の option id（GraphQL の
            # F_Status・O_Status_… を渡すと偽の PATCH が失敗する）
            patches: list = []
            gh_task.run_gh = make_write_gh(
                {711: dict(title='task', status=gh_task.PENDING_STATUS, kind='task')},
                rest_handler=lambda m, p, b: patches.append(b) or ({} if m == 'PATCH' else None),
            )
            captured: list = []
            base = gh_task.write_project_item_fields_rest
            gh_task.write_project_item_fields_rest = lambda pn, iid, fields: (captured.append(fields), base(pn, iid, fields))[1]
            try:
                with redirect_stdout(io.StringIO()):
                    assert gh_task.cmd_set(711, 'Status', gh_task.DEP_STATUS) == 0
            finally:
                gh_task.write_project_item_fields_rest = base
            fid, value = captured[0][0]['id'], captured[0][0]['value']
            assert isinstance(fid, int) and fid >= 9000, f'REST の field id でない: {fid!r}'
            assert isinstance(value, str) and value.startswith('R_'), f'REST の option id でない: {value!r}'

        t('書き込みは REST の field id（整数）と REST の option id を PATCH に渡す', _rest_write_uses_rest_field_and_option_ids)

        def _add_writes_with_post_response_id_when_search_is_empty() -> None:
            record: list = []
            rest_log: list = []

            def rest_handler(method, path, body):
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/637':
                    return {'id': 424243}
                if method == 'POST' and 'projectsV2/7/items' in path:
                    return {'id': 5002}
                return {}

            base_gh = make_write_gh(
                {}, record=record, rest_handler=rest_handler, rest_items={637: []}, rest_log=rest_log,
            )
            calls = {'n': 0}

            def sequenced_gh(args, input_text=None):
                if 'issue(number:$number) {' in ' '.join(args):
                    calls['n'] += 1
                    if calls['n'] == 1:
                        return 0, json.dumps(_write_item_body(found=False)), ''
                    return 0, json.dumps(_write_item_body(title='task', status='')), ''
                return base_gh(args, input_text)

            gh_task.run_gh = sequenced_gh
            assert gh_task.cmd_add(637) == 0
            assert record == [('F_Status', 'O_Status_承認待ち')], record
            assert any(m == 'PATCH' and p.endswith('/items/5002') for m, p in rest_log), rest_log
            assert not any('?q=' in p for _m, p in rest_log), f'?q= を引いた: {rest_log}'

        t('add は ?q= が 0 件でも、POST の応答の id で書いて exit 0', _add_writes_with_post_response_id_when_search_is_empty)

        def _start_approved_and_reopen_do_not_half_write_when_item_missing() -> None:
            calls: list = []

            def rest_handler(method, path, body):
                calls.append((method, path))
                return {}

            gh_task.run_gh = make_write_gh(
                {712: dict(title=f'{gh_task.OPERATION_MARK} task', status=gh_task.PENDING_STATUS,
                           kind='task', body='本文', parent_number=713),
                 713: dict(title='feature', status=gh_task.READY_STATUS, kind='feature')},
                rest_handler=rest_handler, rest_items={712: []},
            )
            _expect_exit(lambda: gh_task.cmd_start(712, 'チャット'), 1)
            gh_task.run_gh = make_write_gh(
                {713: dict(title='task', status=gh_task.DONE_STATUS, state='CLOSED')},
                rest_handler=rest_handler, rest_items={713: []},
            )
            _expect_exit(lambda: gh_task.cmd_reopen(713, gh_task.IN_PROGRESS_STATUS), 1)
            assert not [c for c in calls if c[0] == 'PATCH' and c[1].startswith('repos/')], \
                f'item id が引けないのに issue を書き換えた: {calls}'

        t(
            'start --approved・reopen は item id が引けないとき、本文・state を書き換えない',
            _start_approved_and_reopen_do_not_half_write_when_item_missing,
        )

        # ── new ────────────────────────────────────────
        def _new_requires_parent_for_task_and_feature() -> None:
            # 種別 task（既定）・feature は --parent が要る。REST を 1 回も呼ばずに
            # exit 2 で落ちる（作ってから気づくと、親なしの issue が残る）。
            calls: list = []

            def rest_handler(method, path, body):
                calls.append((method, path, body))
                return {}

            gh_task.run_gh = make_write_gh({}, rest_handler=rest_handler)
            _expect_exit(lambda: gh_task.cmd_new(['新しい task']), 2)
            _expect_exit(lambda: gh_task.cmd_new(['新しい task', '--kind', 'task']), 2)
            _expect_exit(lambda: gh_task.cmd_new(['新しい feature', '--kind', 'feature']), 2)
            _expect_exit(lambda: gh_task.cmd_new(['bug', '--label-bug']), 2)
            assert calls == [], f'REST が呼ばれた（親の検査より前に create してしまっている）: {calls}'

        t('親の無い task・feature の new は exit 2（REST を呼ぶ前に落ちる）', _new_requires_parent_for_task_and_feature)

        def _new_rejects_parent_for_wave_and_design_memo() -> None:
            calls: list = []

            def rest_handler(method, path, body):
                calls.append((method, path, body))
                return {}

            gh_task.run_gh = make_write_gh({}, rest_handler=rest_handler)
            _expect_exit(lambda: gh_task.cmd_new(['w', '--kind', 'wave', '--parent', '1']), 2)
            _expect_exit(lambda: gh_task.cmd_new(['m', '--kind', '設計メモ', '--parent', '1']), 2)
            assert calls == [], f'REST が呼ばれた: {calls}'

        t('wave・設計メモは親を持たない（--parent を渡すと exit 2）', _new_rejects_parent_for_wave_and_design_memo)

        # 値・親を確かめる前に issue を作ってしまうと、
        # やり直すたびに二重に起票される。REST が 1 回も呼ばれないことを見る。
        def _new_rejects_unknown_kind_before_rest() -> None:
            calls: list = []

            def rest_handler(method, path, body):
                calls.append((method, path, body))
                return {}

            gh_task.run_gh = make_write_gh({}, rest_handler=rest_handler)
            _expect_exit(lambda: gh_task.cmd_new(['t', '--kind', 'feture', '--parent', '1']), 2)
            assert calls == [], f'REST が呼ばれた: {calls}'

        t('未知の --kind の値は REST を呼ぶ前に exit 2', _new_rejects_unknown_kind_before_rest)

        def _new_rejects_unknown_kind_even_when_kind_field_missing() -> None:
            # option_id は項目「種別」が無ければ検査自体を飛ばすので、_NEW_KIND_OPTIONS の
            # 検査を外すと、種別の項目がまだ無い checkoutでは打ち間違いの
            # --kind が素通りしてしまう（壊して確かめた: broke_to_confirm に記録）。
            calls: list = []

            def rest_handler(method, path, body):
                calls.append((method, path, body))
                return {}

            gh_task.run_gh = make_write_gh(
                {}, field_defs=_fake_field_defs(include_kind=False), rest_handler=rest_handler,
            )
            _expect_exit(lambda: gh_task.cmd_new(['t', '--kind', 'feture', '--parent', '1']), 2)
            assert calls == [], f'REST が呼ばれた: {calls}'

        t(
            '未知の --kind の値は、項目「種別」が無い checkout でも exit 2（option_id 任せにしない）',
            _new_rejects_unknown_kind_even_when_kind_field_missing,
        )

        def _new_rejects_gate_option() -> None:
            # --gate は無い。REST を呼ぶ前に exit 2（古い呼び方が黙って通らない）。
            calls: list = []

            def rest_handler(method, path, body):
                calls.append((method, path, body))
                return {}

            gh_task.run_gh = make_write_gh({}, rest_handler=rest_handler)
            _expect_exit(lambda: gh_task.cmd_new(['t', '--parent', '1', '--gate', 'なし']), 2)
            assert calls == [], f'REST が呼ばれた: {calls}'

        t('--gate は外した（渡すと REST を呼ぶ前に exit 2）', _new_rejects_gate_option)

        def _new_rejects_nonexistent_parent_before_rest() -> None:
            calls: list = []

            def rest_handler(method, path, body):
                calls.append((method, path, body))
                return {}

            gh_task.run_gh = make_write_gh({}, rest_handler=rest_handler)
            _expect_exit(lambda: gh_task.cmd_new(['t', '--parent', '99999']), 1)
            assert calls == [], f'REST が呼ばれた: {calls}'

        t('実在しない --parent は REST を呼ぶ前に落ちる', _new_rejects_nonexistent_parent_before_rest)

        # ── new の親子関係の検査 ──
        def _new_rejects_task_parent_not_feature() -> None:
            calls: list = []

            def rest_handler(method, path, body):
                calls.append((method, path, body))
                return {}

            gh_task.run_gh = make_write_gh(
                {720: dict(title='wave 行', status=gh_task.READY_STATUS, kind='wave')},
                rest_handler=rest_handler,
            )
            _expect_exit(lambda: gh_task.cmd_new(['t', '--parent', '720']), 2)
            assert calls == [], f'REST が呼ばれた: {calls}'

        t('task の親が feature でない（wave）ときは断る（子 issue には割らない）', _new_rejects_task_parent_not_feature)

        def _new_rejects_feature_parent_not_wave() -> None:
            calls: list = []

            def rest_handler(method, path, body):
                calls.append((method, path, body))
                return {}

            gh_task.run_gh = make_write_gh(
                {721: dict(title='feature 行', status=gh_task.READY_STATUS, kind='feature')},
                rest_handler=rest_handler,
            )
            _expect_exit(
                lambda: gh_task.cmd_new(['新しい feature', '--kind', 'feature', '--parent', '721']), 2,
            )
            assert calls == [], f'REST が呼ばれた: {calls}'

        t('feature の親が wave でない（feature）ときは断る', _new_rejects_feature_parent_not_wave)

        def _new_skips_parent_kind_check_when_kind_field_missing() -> None:
            rest_calls: list = []
            created = {'number': 906, 'id': 606606, 'node_id': 'X906'}

            def rest_handler(method, path, body):
                rest_calls.append((method, path, body))
                if method == 'POST' and path == f'repos/{gh_task.REPO}/issues':
                    return created
                if method == 'POST' and path == f'repos/{gh_task.REPO}/issues/722/sub_issues':
                    return {}
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/722':
                    return {'sub_issues_summary': {'total': 1}}
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/906':
                    return {'milestone': None, 'body': ''}
                return {}

            gh_task.run_gh = make_write_gh(
                {
                    # 種別=task の親（本来なら feature 以外は断るはずの組み合わせ）でも、
                    # 項目「種別」がまだ無いときは検査を飛ばして通す。
                    722: dict(title='何か', status=gh_task.READY_STATUS, kind='task'),
                    906: dict(title='新しい task', status=gh_task.PENDING_STATUS, kind=''),
                },
                field_defs=_fake_field_defs(include_kind=False),
                rest_handler=rest_handler,
            )
            rc = gh_task.cmd_new(['新しい task', '--parent', '722'])
            assert rc == 0

        t(
            '項目「種別」が無い Project では親子関係の検査を飛ばす',
            _new_skips_parent_kind_check_when_kind_field_missing,
        )

        # ── new の --milestone ──
        def _new_rejects_milestone_for_non_feature() -> None:
            calls: list = []

            def rest_handler(method, path, body):
                calls.append((method, path, body))
                return {}

            gh_task.run_gh = make_write_gh({}, rest_handler=rest_handler)
            _expect_exit(
                lambda: gh_task.cmd_new(['t', '--parent', '1', '--milestone', '3']), 2,
            )
            assert calls == [], f'REST が呼ばれた: {calls}'

        t('--milestone は種別 feature 以外では断る', _new_rejects_milestone_for_non_feature)

        def _new_creates_and_wires_up_with_parent() -> None:
            record: list = []
            rest_calls: list = []
            created = {'number': 900, 'id': 555555, 'node_id': 'ISSUE_900'}

            def rest_handler(method, path, body):
                rest_calls.append((method, path, body))
                if method == 'POST' and path == f'repos/{gh_task.REPO}/issues':
                    return created
                if method == 'POST' and path == f'repos/{gh_task.REPO}/issues/700/sub_issues':
                    return {}
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/700':
                    return {'sub_issues_summary': {'total': 3}}
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/900':
                    return {'milestone': None, 'body': ''}
                return {}

            gh_task.run_gh = make_write_gh(
                {
                    900: dict(title='新しい task', status=gh_task.PENDING_STATUS, kind=''),
                    700: dict(title='feature', status=gh_task.PENDING_STATUS, kind='feature'),
                },
                record=record, rest_handler=rest_handler,
            )
            rc = gh_task.cmd_new(['新しい task', '--parent', '700', '--kind', 'task'])
            assert rc == 0
            assert (f'F_{gh_task.KIND_FIELD}', 'O_kind_task') in record
            sub_issue_calls = [
                c for c in rest_calls if c[1] == f'repos/{gh_task.REPO}/issues/700/sub_issues'
            ]
            assert sub_issue_calls, 'sub_issues の POST が呼ばれていない'
            assert sub_issue_calls[0][2] == {'sub_issue_id': 555555}

        t(
            'new は親があれば REST で作って sub_issues で付け、種別を書く',
            _new_creates_and_wires_up_with_parent,
        )

        def _new_tolerates_already_a_sub_issue() -> None:
            # sub_issues の重複応答は "already exists"（item-add の応答）ではなく、
            # "sub-issue" と "already" を含む文言で来る。
            def rest_handler(method, path, body):
                if method == 'POST' and path == f'repos/{gh_task.REPO}/issues':
                    return {'number': 904, 'id': 1, 'node_id': 'X'}
                if method == 'POST' and path == f'repos/{gh_task.REPO}/issues/705/sub_issues':
                    return None  # 呼び出し元は ok_fail=True を見るので、ここには来ない
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/705':
                    return {'sub_issues_summary': {'total': 1}}
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/904':
                    return {'milestone': None, 'body': ''}
                return {}

            def fake_run_gh(args, input_text=None):
                joined = ' '.join(args)
                if len(args) >= 4 and args[0] == 'api' and args[1] == '-X' \
                        and args[2] == 'POST' and args[3].endswith('/705/sub_issues'):
                    return 1, '', '422: sub-issue is already a sub-issue of this issue'
                base = make_write_gh(
                    {
                        904: dict(title='t', status=gh_task.PENDING_STATUS, kind=''),
                        705: dict(title='feature', status=gh_task.PENDING_STATUS, kind='feature'),
                    },
                    rest_handler=rest_handler,
                )
                return base(args, input_text)

            gh_task.run_gh = fake_run_gh
            rc = gh_task.cmd_new(['t', '--parent', '705'])
            assert rc == 0

        t(
            'new は sub_issues の「既に同じ親の子」応答を成功として扱う',
            _new_tolerates_already_a_sub_issue,
        )

        def _attach_sub_issue_does_not_swallow_unrelated_errors() -> None:
            def fake_run_gh(args, input_text=None):
                if len(args) >= 4 and args[0] == 'api' and args[1] == '-X' \
                        and args[2] == 'POST' and args[3].endswith('/705/sub_issues'):
                    return 1, '', 'already closed and cannot accept new sub-issues'
                return 1, '', f'unhandled: {" ".join(args)[:120]}'

            gh_task.run_gh = fake_run_gh
            try:
                gh_task.attach_sub_issue(705, 1)
            except gh_task.GhError as exc:
                assert exc.code == 1
                return
            raise AssertionError('無関係な失敗まで成功扱いにした（部分一致が緩すぎる）')

        t(
            'attach_sub_issue は "already a sub-issue" という句が無い失敗を握り潰さない',
            _attach_sub_issue_does_not_swallow_unrelated_errors,
        )

        def _add_item_to_project_tolerates_content_already_exists() -> None:
            gh_task._owner_type_cache = None

            def fake_run_gh(args, input_text=None):
                joined = ' '.join(args)
                if 'repositoryOwner' in joined:
                    body = {'data': {'repositoryOwner': {'__typename': 'Organization'}}}
                    return 0, json.dumps(body), ''
                if len(args) >= 4 and args[0] == 'api' and args[1] == '-X' \
                        and args[2] == 'POST' and 'projectsV2/7/items' in args[3]:
                    return 1, '', 'Content already exists in this project'
                return 1, '', f'unhandled: {joined[:120]}'

            gh_task.run_gh = fake_run_gh
            result = gh_task.add_item_to_project_rest(7, 424242)
            assert result.get('_error'), (
                f'"Content already exists" を成功として通していない: {result}'
            )

        t(
            'add_item_to_project_rest は item-add の "Content already exists" を成功として扱う',
            _add_item_to_project_tolerates_content_already_exists,
        )

        def _new_uses_users_path_when_owner_is_user() -> None:
            rest_calls: list = []
            created = {'number': 950, 'id': 111222, 'node_id': 'X950'}

            def rest_handler(method, path, body):
                rest_calls.append((method, path, body))
                if method == 'POST' and path == f'repos/{gh_task.REPO}/issues':
                    return created
                if method == 'POST' and path == f'users/{gh_task.OWNER}/projectsV2/7/items':
                    return {'id': 5}
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/950':
                    return {'milestone': None, 'body': ''}
                return {}

            gh_task.run_gh = make_write_gh(
                {950: dict(title='t', status=gh_task.PENDING_STATUS, kind='')},
                rest_handler=rest_handler, owner_typename='User',
            )
            rc = gh_task.cmd_new(['t', '--kind', '設計メモ'])
            assert rc == 0
            item_posts = [c for c in rest_calls if c[0] == 'POST' and 'projectsV2/7/items' in c[1]]
            assert item_posts and item_posts[0][1].startswith('users/'), (
                f'owner が User なのに users/ パスを使っていない: {rest_calls}'
            )

        t(
            'owner が User（個人所有の Project）なら users/ パスで Project に入れる',
            _new_uses_users_path_when_owner_is_user,
        )

        def _new_announces_start_and_writes_no_late_addition_when_parent_ready() -> None:
            rest_calls: list = []
            created = {'number': 901, 'id': 777777, 'node_id': 'ISSUE_901'}

            def rest_handler(method, path, body):
                rest_calls.append((method, path, body))
                if method == 'POST' and path == f'repos/{gh_task.REPO}/issues':
                    return created
                if method == 'POST' and path == f'repos/{gh_task.REPO}/issues/702/sub_issues':
                    return {}
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/702':
                    return {'sub_issues_summary': {'total': 1}}
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/901':
                    return {'milestone': None, 'body': ''}
                if method == 'PATCH' and path == f'repos/{gh_task.REPO}/issues/901':
                    return {}
                return {}

            gh_task.run_gh = make_write_gh(
                {
                    901: dict(title='新しい task', status=gh_task.PENDING_STATUS, kind=''),
                    702: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
                },
                rest_handler=rest_handler,
            )
            out = io.StringIO()
            with redirect_stdout(out):
                rc = gh_task.cmd_new(['新しい task', '--parent', '702'])
            assert rc == 0
            # 親の feature が着手可でも、本文に「後から追加」を書かない（着手可の feature の
            # 子は、いつ足したものでも start で着手できる）。
            creates = [
                c for c in rest_calls
                if c[0] == 'POST' and c[1] == f'repos/{gh_task.REPO}/issues'
            ]
            assert creates, 'issue の作成が呼ばれていない'
            assert '後から追加' not in creates[0][2]['body'], creates[0][2]['body']
            hint = '親 #702 は着手可。`hirai-task start 901` で着手できる'
            assert out.getvalue().count(hint) == 1, f'着手の案内が 1 行出ていない: {out.getvalue()!r}'
            # 目印つきの task には、start で着手できる案内を出さない（start --approved の task）。
            marked_out = io.StringIO()
            with redirect_stdout(marked_out):
                gh_task.cmd_new(['[操作] 新しい task', '--parent', '702'])
            assert 'で着手できる' not in marked_out.getvalue(), marked_out.getvalue()
            patches = [
                c for c in rest_calls
                if c[0] == 'PATCH' and c[1] == f'repos/{gh_task.REPO}/issues/901'
            ]
            assert patches == [], f'作成後に本文の PATCH が要らないはず: {patches}'

        t(
            'new は親の feature が着手可でも本文に「後から追加」を書かず、目印の無い task には着手の案内を 1 行出す',
            _new_announces_start_and_writes_no_late_addition_when_parent_ready,
        )

        def _new_clears_inherited_milestone() -> None:
            rest_calls: list = []
            created = {'number': 902, 'id': 888888, 'node_id': 'ISSUE_902'}

            def rest_handler(method, path, body):
                rest_calls.append((method, path, body))
                if method == 'POST' and path == f'repos/{gh_task.REPO}/issues':
                    return created
                if method == 'POST' and path == f'repos/{gh_task.REPO}/issues/703/sub_issues':
                    return {}
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/703':
                    return {'sub_issues_summary': {'total': 1}}
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/902':
                    return {'milestone': {'number': 5, 'title': 'R1'}, 'body': ''}
                if method == 'PATCH' and path == f'repos/{gh_task.REPO}/issues/902':
                    return {}
                return {}

            gh_task.run_gh = make_write_gh(
                {
                    902: dict(title='新しい task', status=gh_task.PENDING_STATUS, kind=''),
                    703: dict(title='feature', status=gh_task.PENDING_STATUS, kind='feature'),
                },
                rest_handler=rest_handler,
            )
            rc = gh_task.cmd_new(['新しい task', '--parent', '703'])
            assert rc == 0
            milestone_patches = [
                c for c in rest_calls
                if c[0] == 'PATCH' and c[1] == f'repos/{gh_task.REPO}/issues/902'
                and (c[2] or {}).get('milestone', '__absent__') is None
            ]
            assert milestone_patches, 'milestone を外す PATCH が呼ばれていない'

        t(
            'new は親から継いだ Milestone を外す',
            _new_clears_inherited_milestone,
        )

        def _new_parentless_design_memo_goes_on_hold() -> None:
            record: list = []
            rest_calls: list = []
            created = {'number': 903, 'id': 999999, 'node_id': 'ISSUE_903'}

            def rest_handler(method, path, body):
                rest_calls.append((method, path, body))
                if method == 'POST' and path == f'repos/{gh_task.REPO}/issues':
                    return created
                if method == 'POST' and path == f'orgs/{gh_task.OWNER}/projectsV2/7/items':
                    return {'id': 111}
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/903':
                    return {'milestone': None, 'body': ''}
                return {}

            gh_task.run_gh = make_write_gh(
                {903: dict(title='止めた設計メモ', status=gh_task.PENDING_STATUS, kind='')},
                record=record, rest_handler=rest_handler,
            )
            rc = gh_task.cmd_new(['止めた設計メモ', '--kind', '設計メモ'])
            assert rc == 0
            assert ('F_Status', 'O_Status_保留') in record, f'保留を書いていない: {record}'
            items_posts = [c for c in rest_calls if c[0] == 'POST' and 'projectsV2/7/items' in c[1]]
            assert items_posts, 'item-add の POST が呼ばれていない（親なしなので Project に直接入れる）'

        t('親なしの設計メモが Project に入って保留になる', _new_parentless_design_memo_goes_on_hold)

        # ── new が親を作るとき ─────────
        _WAVE_ONE_BODY = (
            '- 出る条件のコマンド: 未記入\n'
            '## まだ作っていない wave\n'
            '- P3 基盤の部品・着手順 4・blocked by P1・目的と条件\n'
            '- P4 別の wave・blocked by #12, P1\n'
            '## つぎの節\n'
            '- P9 節の外・blocked by P1\n'
        )
        _WAVE_BOARD = [
            dict(number=900, status='', kind='wave', title='基盤（P1）'),
            dict(number=901, status='', kind='wave', title='部品（P2）'),
        ]

        def _wave_rest_handler(calls: list):
            def rest_handler(method, path, body):
                calls.append((method, path, body))
                if method == 'POST' and path == f'repos/{gh_task.REPO}/issues':
                    return {'number': 950, 'id': 950950, 'node_id': 'X950'}
                if method == 'POST' and path == f'orgs/{gh_task.OWNER}/projectsV2/7/items':
                    return {'id': 5}
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/900':
                    return {'id': 900900}
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/12':
                    return {'id': 121212}
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/950':
                    return {'milestone': None, 'body': ''}
                return {}
            return rest_handler

        def _new_wave_from_unbuilt_section_creates_with_blocked_by() -> None:
            calls: list = []
            record: list = []
            gh_task.run_gh = make_new_board_gh(
                {950: dict(title='P3 基盤の部品', status=gh_task.PENDING_STATUS, kind='')},
                _WAVE_BOARD, {900: _WAVE_ONE_BODY}, rest_handler=_wave_rest_handler(calls), record=record,
            )
            out = io.StringIO()
            with redirect_stdout(out):
                rc = gh_task.cmd_new(['P3 基盤の部品', '--kind', 'wave'])
            assert rc == 0
            assert (f'F_{gh_task.KIND_FIELD}', 'O_kind_wave') in record, record
            deps = [c for c in calls if c[1] == f'repos/{gh_task.REPO}/issues/950/dependencies/blocked_by']
            assert [d[2] for d in deps] == [{'issue_id': 900900}], f'P1 への blocked by が張られていない: {calls}'
            assert not [c for c in calls if 'sub_issues' in c[1]], '親なしの wave に sub_issues を付けた'
            assert '並び順をボードで直してください' in out.getvalue(), out.getvalue()
            # wave は Status を使わない。Item added の承認待ちを消し、書き直さない。
            assert ('F_Status', None) in record, f'wave の Status を消していない: {record}'
            assert not [r for r in record if r[0] == 'F_Status' and r[1]], f'Status を書いた: {record}'

        t(
            'new は「まだ作っていない wave」の節にある wave を作り、節の blocked by を張って並び順を頼む',
            _new_wave_from_unbuilt_section_creates_with_blocked_by,
        )

        def _new_wave_matches_by_short_code_and_resolves_hash_and_code() -> None:
            calls: list = []
            gh_task.run_gh = make_new_board_gh(
                {950: dict(title='別の wave（P4）', status=gh_task.PENDING_STATUS, kind='')},
                _WAVE_BOARD, {900: _WAVE_ONE_BODY}, rest_handler=_wave_rest_handler(calls),
            )
            with redirect_stdout(io.StringIO()):
                rc = gh_task.cmd_new(['別の wave（P4）', '--kind', 'wave'])
            assert rc == 0
            deps = sorted(
                d[2]['issue_id'] for d in calls
                if d[1] == f'repos/{gh_task.REPO}/issues/950/dependencies/blocked_by'
            )
            assert deps == [121212, 900900], f'#12 と P1 の両方が張られていない: {deps}'

        t(
            'new の wave は題名の短い ID でも節に当たり、blocked by の `#番号` と短い ID を番号へ解決する',
            _new_wave_matches_by_short_code_and_resolves_hash_and_code,
        )

        def _new_wave_not_in_section_is_refused_before_rest() -> None:
            calls: list = []
            gh_task.run_gh = make_new_board_gh(
                {}, _WAVE_BOARD, {900: _WAVE_ONE_BODY}, rest_handler=_wave_rest_handler(calls),
            )
            # P9 は次の節（つぎの節）にあるので、「まだ作っていない wave」の節には無い
            for title in ('P9 節の外', 'P5 どこにも無い'):
                try:
                    gh_task.cmd_new([title, '--kind', 'wave'])
                except gh_task.GhError as exc:
                    assert exc.code == 2 and 'まだ作っていない wave' in str(exc), f'{exc.code}: {exc}'
                    continue
                raise AssertionError(f'節に無い wave「{title}」を作った')
            assert [c for c in calls if c[0] == 'POST'] == [], f'REST の POST が呼ばれた: {calls}'

        t('new は節に無い wave を作らず exit 2（REST を呼ぶ前に落ちる）', _new_wave_not_in_section_is_refused_before_rest)

        def _new_wave_already_built_is_refused_before_rest() -> None:
            # 節は作ったあとも P1 の本文に残る。同じ名前・同じ短い ID の wave が既にあれば作らない。
            for title, existing in (
                ('P3 基盤の部品', dict(number=909, status='', kind='wave', title='P3 基盤の部品')),
                ('P3 基盤の部品', dict(number=909, status='', kind='wave', title='部品の土台（P3）')),
            ):
                calls: list = []
                gh_task.run_gh = make_new_board_gh(
                    {}, _WAVE_BOARD + [existing], {900: _WAVE_ONE_BODY}, rest_handler=_wave_rest_handler(calls),
                )
                try:
                    gh_task.cmd_new([title, '--kind', 'wave'])
                except gh_task.GhError as exc:
                    assert exc.code == 2 and '#909' in str(exc) and '作成済み' in str(exc), f'{exc.code}: {exc}'
                else:
                    raise AssertionError(f'作成済みの wave「{title}」をもう 1 本作った')
                assert [c for c in calls if c[0] == 'POST'] == [], f'REST の POST が呼ばれた: {calls}'

        t('new は作成済みの wave（同名・同じ短い ID）を 2 本目として作らず exit 2', _new_wave_already_built_is_refused_before_rest)

        def _new_wave_unresolvable_blocker_is_refused_before_rest() -> None:
            calls: list = []
            body = '## まだ作っていない wave\n- P3 基盤の部品・blocked by P7\n'
            gh_task.run_gh = make_new_board_gh(
                {}, _WAVE_BOARD, {900: body}, rest_handler=_wave_rest_handler(calls),
            )
            _expect_exit(lambda: gh_task.cmd_new(['P3 基盤の部品', '--kind', 'wave']), 2)
            assert [c for c in calls if c[0] == 'POST'] == [], f'REST の POST が呼ばれた: {calls}'

        t('new の wave は blocked by の相手が無ければ、作る前に exit 2', _new_wave_unresolvable_blocker_is_refused_before_rest)

        def _parse_unbuilt_waves_reads_only_that_section() -> None:
            entries = gh_task.parse_unbuilt_waves(_WAVE_ONE_BODY)
            assert [e['name'] for e in entries] == ['P3 基盤の部品', 'P4 別の wave'], entries
            assert entries[0]['blockers'] == ['P1'] and entries[1]['blockers'] == ['#12', 'P1'], entries
            assert gh_task.parse_unbuilt_waves('') == [] and gh_task.parse_unbuilt_waves('- P3 x') == []

        t('「まだ作っていない wave」の節の読み取りは、その節の箇条書きだけを拾う', _parse_unbuilt_waves_reads_only_that_section)

        def _new_feature_is_created_pending_and_announced() -> None:
            calls: list = []
            out = io.StringIO()
            record: list = []
            gh_task.run_gh = make_write_gh(
                {
                    950: dict(title='新しい feature', status=gh_task.PENDING_STATUS, kind=''),
                    900: dict(title='基盤（P1）', status='', kind='wave'),
                },
                record=record, rest_handler=lambda m, p, b: (
                    calls.append((m, p, b)) or (
                        {'number': 950, 'id': 950950} if (m, p) == ('POST', f'repos/{gh_task.REPO}/issues') else
                        {'sub_issues_summary': {'total': 1}} if (m, p) == ('GET', f'repos/{gh_task.REPO}/issues/900') else
                        {'milestone': None, 'body': ''} if (m, p) == ('GET', f'repos/{gh_task.REPO}/issues/950') else {}
                    )
                ),
            )
            with redirect_stdout(out):
                rc = gh_task.cmd_new(['新しい feature', '--kind', 'feature', '--parent', '900'])
            assert rc == 0
            assert (f'F_{gh_task.KIND_FIELD}', 'O_kind_feature') in record, record
            assert '承認待ちで作った' in out.getvalue(), out.getvalue()
            assert any(c[1] == f'repos/{gh_task.REPO}/issues/900/sub_issues' for c in calls), calls

        t('new は feature を wave の子として承認待ちで作り、1 行で知らせる', _new_feature_is_created_pending_and_announced)

        def _fake_projects_have_no_old_six_axes() -> None:
            names = {d['name'] for d in _fake_field_defs()}
            assert names == {'Status', gh_task.KIND_FIELD}, (
                f'偽の Project に古い 6 軸の項目が残っている: {names}'
            )

        t('selftest の偽の Project は 6 軸の項目を持たない', _fake_projects_have_no_old_six_axes)

        def _new_skips_kind_write_when_field_missing() -> None:
            record: list = []
            rest_calls: list = []
            created = {'number': 905, 'id': 222, 'node_id': 'X905'}

            def rest_handler(method, path, body):
                rest_calls.append((method, path, body))
                if method == 'POST' and path == f'repos/{gh_task.REPO}/issues':
                    return created
                if method == 'POST' and path == f'orgs/{gh_task.OWNER}/projectsV2/7/items':
                    return {'id': 3}
                if method == 'GET' and path == f'repos/{gh_task.REPO}/issues/905':
                    return {'milestone': None, 'body': ''}
                return {}

            gh_task.run_gh = make_write_gh(
                {905: dict(title='task', status=gh_task.PENDING_STATUS, kind='')},
                field_defs=_fake_field_defs(include_kind=False),
                record=record, rest_handler=rest_handler,
            )
            rc = gh_task.cmd_new(['メモ', '--kind', '設計メモ'])
            assert rc == 0
            kind_writes = [r for r in record if r[0].startswith('F_') and r[0].endswith(gh_task.KIND_FIELD)]
            assert kind_writes == [], f'種別の項目が無いのに書いた: {kind_writes}'

        t(
            '項目「種別」が無い Project でも new は動く（種別を書かずに orphans に出す）',
            _new_skips_kind_write_when_field_missing,
        )

        # draft は一時ディレクトリに作る（実リポの docs/draft に依らない。読めない
        # ときの OSError → exit 2 が「未承認」と同じ exit code で誤魔化されて PASS
        # してしまうのを、メッセージまで見て防ぐ）。
        def _draft_path(name: str, text: str) -> str:
            path = os.path.join(cache_tmp_dir, name)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
            return path

        _UNAPPROVED_TABLE = '# 設計\n\n| item | value |\n|---|---|\n| approved | |\n'

        def _new_from_draft_requires_approval() -> None:
            unapproved = _draft_path('unapproved-table.md', _UNAPPROVED_TABLE)
            gh_task.run_gh = make_write_gh({})
            try:
                gh_task.cmd_new(['x', '--parent', '1', '--from-draft', unapproved])
            except gh_task.GhError as exc:
                assert exc.code == 2, f'exit {exc.code}（期待 2）'
                assert '未承認' in str(exc), f'「未承認」と言っていない（読めなかった、と混同していないか）: {exc}'
                return
            raise AssertionError('落ちるべきなのに通った')

        t('未承認の draft を読む（new --from-draft が断る。メッセージも見る）', _new_from_draft_requires_approval)

        # ── new --from-table（設計の task の表から起票する） ──
        def _table_draft(name: str, *, status: str = '承認', approvals: str = '要件=PR #9 設計=PR #9 task=PR #9') -> str:
            text = (
                '# 表の試験\n\n'
                'id_prefix: TBL\nkind: ハーネス・進め方\ndomain: —\nstatus: ' + status + '\n'
                'approvals: ' + approvals + '\napproved_at: 2026-10-01（PR #9 の merge で承認）\n\n'
                '## 1. 問題\n\n## 10. 完了条件\n\n## 11. task\n\n### 11-1. 位置と前後\n\n### 11-3. 表\n\n'
                '| id | kind | stream | 題名 | 親 | 止める依存 | 要件 | 完了条件 |\n|---|---|---|---|---|---|---|---|\n'
                '| TBL-01 | task | Infra | 土台を書く | feature #900 | — | TBL-R1 | テストが通る |\n'
                '| TBL-02 | task | Infra | 命名を決める [要判断: TBL-Q1] | feature #900 | — | TBL-R2 | — |\n'
                '| TBL-03 | task | Infra | [操作] 本番へ出す | feature #900 | TBL-01, この draft の承認 | TBL-R1 | exit 0 |\n\n'
                '## 12. 履歴\n'
            )
            return _draft_path(name, text)

        def _from_table(path: str, *extra: str) -> tuple[int, str]:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = gh_task.cmd_new(['--from-table', path, *extra])
            return rc, buf.getvalue()

        def _from_table_dry_run_lists_rows() -> None:
            rc, out = _from_table(_table_draft('tbl-ok.md'), '--dry-run')
            assert rc == 0, f'exit {rc}\n{out}'
            assert '起票する 2 件' in out, out
            assert 'TBL-01' in out and 'TBL-03' in out, out
            assert '親=#900' in out, f'親が出ていない: {out}'
            assert '目印=[操作]' in out, f'目印が出ていない: {out}'
            assert 'blocked by=TBL-01' in out, f'blocked by が出ていない: {out}'
            assert '起票しない 1 件' in out and 'TBL-02' in out and '[要判断]' in out, f'飛ばした理由が出ていない: {out}'

        t('new --from-table --dry-run: 表 3 行（[要判断] 1・blocked by 1）→ 起票 2 件と、飛ばした理由', _from_table_dry_run_lists_rows)

        def _from_table_files_in_order_with_blockers() -> None:
            calls: list[dict] = []
            orig_new_issue, orig_existing = gh_task.new_issue, gh_task.existing_table_marks

            def fake_new_issue(opts: dict) -> int:
                calls.append(opts)
                return 500 + len(calls)

            gh_task.new_issue = fake_new_issue
            gh_task.existing_table_marks = lambda slug: {}
            try:
                rc, out = _from_table(_table_draft('tbl-run.md'))
            finally:
                gh_task.new_issue, gh_task.existing_table_marks = orig_new_issue, orig_existing
            assert rc == 0, f'exit {rc}\n{out}'
            assert [c['title'] for c in calls] == ['土台を書く', '[操作] 本番へ出す'], [c['title'] for c in calls]
            assert calls[0]['parent'] == 900 and calls[0].get('blocked_by') in (None, []), calls[0]
            assert calls[1]['blocked_by'] == [501], f'blocked by が起票した番号になっていない: {calls[1]}'
            assert calls[0]['body'].startswith('<!-- rmp-task: id=TBL-01 '), calls[0]['body']
            assert 'src=tbl-run@PR9' in calls[0]['body'] and 'reqs=TBL-R1' in calls[0]['body'], calls[0]['body']

        t('new --from-table: 起票は 2 件・blocked by は起票した番号・本文の先頭に目印', _from_table_files_in_order_with_blockers)

        def _from_table_skips_existing_marks() -> None:
            calls: list[dict] = []
            orig_new_issue, orig_existing = gh_task.new_issue, gh_task.existing_table_marks
            gh_task.new_issue = lambda opts: calls.append(opts) or 600 + len(calls)
            gh_task.existing_table_marks = lambda slug: {'TBL-01': 321}
            try:
                rc, out = _from_table(_table_draft('tbl-dup.md'))
            finally:
                gh_task.new_issue, gh_task.existing_table_marks = orig_new_issue, orig_existing
            assert rc == 0 and [c['title'] for c in calls] == ['[操作] 本番へ出す'], (rc, calls, out)
            assert calls[0]['blocked_by'] == [321], f'既にある行の番号を blocked by に使っていない: {calls[0]}'
            assert '#321' in out, out

        t('new --from-table: 同じ slug と id の目印が既にある行は飛ばし、その番号を blocked by に使う', _from_table_skips_existing_marks)

        def _from_table_feature_card_first() -> None:
            text = (
                '# 表の試験\n\nid_prefix: TBF\nkind: 製品の機能\ndomain: —\nwave: 6 入居者の登録\nstatus: 承認\n'
                'approvals: 要件=PR #9 設計=PR #9 task=PR #9\napproved_at: 2026-10-01（PR #9 の merge で承認）\n\n'
                '## 1. 問題\n\n### 提案: 登録をやさしくする\n\n**何をしたいか**: 入居者が 3 分で登録を終えられる\n\n'
                '**しないとどうなる**:\n- 登録の途中で半数が離れる\n\n## 8. リスク\n\n- 既存の登録者の再ログインが要る（推測）\n\n'
                '## 10. 完了条件\n\n## 11. task\n\n### 11-3. 表\n\n'
                '| id | kind | stream | 題名 | 親 | 止める依存 | 要件 | 完了条件 |\n|---|---|---|---|---|---|---|---|\n'
                '| TBF-F1 | feature | — | 登録の画面 | wave #704 | — | — | — |\n'
                '| TBF-01 | task | FE | 入力欄を減らす | TBF-F1 | — | — | テストが通る |\n'
                '| TBF-02 | task | FE | 確認の画面を消す | TBF-F1 | — | — | テストが通る |\n'
                '| TBF-03 | task | FE | 文言を直す | TBF-F1 | — | — | テストが通る |\n\n## 12. 履歴\n'
            )
            calls: list[dict] = []
            orig_new_issue, orig_existing = gh_task.new_issue, gh_task.existing_table_marks
            orig_open = getattr(gh_task, 'table_unresolved_waves', None)  # 差し替えより前に読む（落ちても差し替えを漏らさない）
            gh_task.new_issue = lambda opts: calls.append(opts) or 700 + len(calls)
            gh_task.existing_table_marks = lambda slug: {'TBF-03': 777}
            try:
                gh_task.table_unresolved_waves = lambda wave, cache: []
                rc, out = _from_table(_draft_path('tbf-run.md', text))
                new_text = (text.replace('**何をしたいか**: 入居者が 3 分で登録を終えられる',
                                         '**決めること**: 登録の画面を作り直すか。**推奨**: 承認する\n\n**目的**: 登録を 3 分にする\n\n'
                                         '**位置**: 入居者の登録の残り\n\n**注意**: 外部の審査が要る')
                            .replace('**しないとどうなる**:', '**しないと**:').replace('tbf-run', 'tbf-new'))
                gh_task.table_unresolved_waves = lambda wave, cache: [600, 601]
                rc2, out2 = _from_table(_draft_path('tbf-new.md', new_text))
            finally:
                gh_task.new_issue, gh_task.existing_table_marks = orig_new_issue, orig_existing
                gh_task.table_unresolved_waves = orig_open
            new_card = calls[3]['body']
            for needle in ('**推奨**: 承認する', '**目的**: 登録を 3 分にする', '**位置**: 入居者の登録の残り',
                           '**注意**: 外部の審査が要る。承認すると先の wave を待たずに着手できる', '**しないと**: 登録の途中で半数が離れる'):
                assert needle in new_card, f'新しい見出しの「{needle}」が無い: {new_card}'
            assert rc2 == 0 and 'task' not in new_card.split('<!-- /card -->')[0], f'カードに内部の語 task が出た: {new_card}'
            assert '今は承認しても動かない' not in new_card, f'先の wave を止まる理由に書いた: {new_card}'
            assert '先の wave' not in calls[0]['body'], f'先の wave が出ているのに無いときの注意が出た: {calls[0]["body"]}'
            assert rc == 0 and [c['title'] for c in calls[:3]] == ['登録の画面', '入力欄を減らす', '確認の画面を消す'], (rc, out)
            feature = calls[0]['body']
            assert feature.startswith('<!-- card:approval -->\n**決めること**: 「登録の画面」を始めるか。**推奨**: <…>'), feature
            for needle in ('**目的**: 入居者が 3 分で登録を終えられる', '**位置**: 段「6 入居者の登録」の一部',
                           '**承認すると**: 作成済みの作業 3 件が着手できる状態になる。戻せる', '**しないと**: 登録の途中で半数が離れる',
                           '**注意**: 既存の登録者の再ログインが要る（推測）', '**詳しく**: docs/draft/tbf-run.md'):
                assert needle in feature, f'「{needle}」が無い: {feature}'
            assert feature.rstrip().splitlines()[-1].startswith('<!-- rmp-task: id=TBF-F1 '), f'目印が末尾に無い: {feature}'
            assert gh_task.parse_task_mark(feature)['id'] == 'TBF-F1'
            assert calls[1]['body'].startswith('<!-- rmp-task: id=TBF-01 '), 'task の本文は今の形（目印が先頭）のまま'
            assert 'hirai-task card 701 --sync' in out, out
            assert '#600' not in new_card, f'wave の番号は注意に入れない（詳しい版に置く）: {new_card}'
            problems = gh_task._load_card_module().read_card(new_card, 'approval')[1]
            assert problems == [], f'先の wave の注意を足したカードが card --lint の問題になる: {problems}'

        t('new --from-table: feature の行は本文の先頭に承認カード（draft の目的・位置・しないと・注意・子の数）、目印は末尾',
          _from_table_feature_card_first)

        def _feature_card_waves_open_note_only_without_stall() -> None:
            # 注意は 1 つだけ: 承認しても動かない理由（stall）があれば先の wave の文は足さない（矛盾する 2 文を並べない）。
            header, lines, cards = {'wave': '6 入居者の登録'}, ['**決めること**: x'], gh_task._load_card_module()
            row = {'title': '登録の画面'}
            both = gh_task.table_feature_card(row, header, 'tbf', lines, 3, gh_task.STALL_BLOCKED, [600, 601])
            assert gh_task.WAVE_WAIVED_CARD_NOTE not in both, f'stall があるのに先の wave の文を足した: {both}'
            assert '今は承認しても動かない（blocked by あり）' in both, both
            assert not [x for x in cards.read_card(both, 'approval')[1] if '注意' in x], cards.read_card(both, 'approval')[1]
            only = gh_task.table_feature_card(row, header, 'tbf', lines, 3, '', [600, 601])
            assert gh_task.WAVE_WAIVED_CARD_NOTE in only and '動かない' not in only, only
            assert not [x for x in cards.read_card(only, 'approval')[1] if '注意' in x], cards.read_card(only, 'approval')[1]
            assert len(gh_task.WAVE_WAIVED_CARD_NOTE) <= 60 and '#' not in gh_task.WAVE_WAIVED_CARD_NOTE
            none = gh_task.table_feature_card(row, header, 'tbf', lines, 3, '', [])
            assert gh_task.WAVE_WAIVED_CARD_NOTE not in none, none

        def _feature_card_waves_open_long_note_moves_to_effect() -> None:
            # draft の注意が長く、つないだ結果が 60 字を超えるときは、注意に足さず「承認すると」の末尾へ回す
            header, cards = {'wave': '6 入居者の登録'}, gh_task._load_card_module()
            long_note = '外部の審査（LINE の公式アカウントの認証）が要り、通るまで 2 週間ほどかかる'
            lines = ['## 1. 概要', '**決めること**: x', f'**注意**: {long_note}']
            card = gh_task.table_feature_card({'title': '登録の画面'}, header, 'tbf', lines, 3, '', [600])
            assert f'**注意**: {long_note}\n' in card and gh_task.WAVE_WAIVED_CARD_NOTE not in card, card
            assert f'**承認すると**: 作成済みの作業 3 件が着手できる状態になる。戻せる。{gh_task.WAVE_WAIVED_EFFECT}' in card, card
            # 空欄（目的・推奨・しないと）は <…> のままなので、見るのは「注意」「承認すると」の行の問題が無いことだけ
            assert not [x for x in cards.read_card(card, 'approval')[1] if '注意' in x or '承認すると' in x], cards.read_card(card, 'approval')[1]
            no_child = gh_task.table_feature_card({'title': '登録の画面'}, header, 'tbf', lines, 0, '', [600])
            assert f'**承認すると**: {gh_task.WAVE_WAIVED_EFFECT}' in no_child, no_child

        t('起票カード: 注意が長く wave の文をつなぐと 60 字を超えるときは「承認すると」の末尾へ回す',
          _feature_card_waves_open_long_note_moves_to_effect)

        t('起票カード: 先の wave の注意は stall が空のときだけ足し、60 字に収まり read_card の問題にならない',
          _feature_card_waves_open_note_only_without_stall)

        def _from_table_refuses_unapproved_stage() -> None:
            for label, path in (
                ('status が起案', _table_draft('tbl-draft.md', status='起案')),
                ('approvals に task の段が無い', _table_draft('tbl-nostage.md', approvals='要件=PR #9 設計=PR #9')),
            ):
                calls: list[dict] = []
                orig_new_issue = gh_task.new_issue
                gh_task.new_issue = lambda opts: calls.append(opts) or 1
                try:
                    rc, out = _from_table(path)
                finally:
                    gh_task.new_issue = orig_new_issue
                assert rc == 2 and not calls, f'{label}: exit {rc}・起票 {len(calls)} 件\n{out}'
                assert '起票 0 件' in out and 'task の段' in out and '「完了条件」「task」' in out, f'{label}: 理由が出ていない: {out}'

        t('new --from-table: task の段が未承認なら 0 件で、段と節の名前つきの理由', _from_table_refuses_unapproved_stage)

        def _from_table_refuses_old_form() -> None:
            old = _draft_path('tbl-old.md', '# 旧\n\nstatus: 承認\napproved_at: 2026-09-01\n\n## 8. タスク分解\n')
            rc, out = _from_table(old, '--dry-run')
            assert rc == 2 and '新しい形' in out, f'exit {rc}\n{out}'

        t('new --from-table: 新しい形（id_prefix: と 11-3 の表）でない draft は断る', _from_table_refuses_old_form)

        # ── start・show の読む束 / coverage / impact / design-merge（#816〜#818） ──
        def _ds_tree(files: dict[str, str]) -> str:
            root = os.path.realpath(tempfile.mkdtemp(dir=cache_tmp_dir))
            for rel, text in files.items():
                full = os.path.join(root, rel)
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, 'w', encoding='utf-8') as f:
                    f.write(text)
            return root

        def _read(path: str) -> str:
            with open(path, encoding='utf-8') as f:
                return f.read()

        def make_ds_board_gh(rows: list[dict], bodies: dict[int, str], extras: dict[int, list[int]] | None = None, *, calls: list):
            """Project の全件・本文の alias・blockedBy の alias に答える偽 gh。呼び出しを calls に控える。"""
            extras = extras or {}

            def fake_run_gh(args: list[str], input_text: str | None = None) -> tuple[int, str, str]:
                joined = ' '.join(args)
                calls.append(joined[:80])
                if 'projectsV2' in joined and 'items(first:' not in joined:
                    return _discovery_response()
                if 'items(first:' in joined:
                    nodes = [_fake_row(**row) for row in rows]
                    body = {'data': {'repository': {'projectV2': {
                        'items': {'pageInfo': {'hasNextPage': False, 'endCursor': None}, 'nodes': nodes}}}}}
                    return 0, json.dumps(body), ''
                numbers = [int(x) for x in re.findall(r'issue\(number:\s*(\d+)\)', joined)]
                if re.search(r'\bi0:', joined) and 'blockedBy' in joined:
                    data = {f'i{i}': {'issue': {'number': n, 'blockedBy': {
                        'totalCount': len(extras.get(n, [])),
                        'nodes': [{'number': b, 'state': 'OPEN'} for b in extras.get(n, [])]},
                        'closedByPullRequestsReferences': {'nodes': []}}} for i, n in enumerate(numbers)}
                    return 0, json.dumps({'data': data}), ''
                if re.search(r'\bi0:', joined):
                    # 問い合わせに body が無ければ body を返さない（本文を取り忘れた回帰を捕まえるため）
                    with_body = re.search(r'\bbody\b', joined) is not None
                    data = {f'i{i}': {'issue': {'number': n, **({'body': bodies.get(n, '')} if with_body else {})}}
                            for i, n in enumerate(numbers)}
                    return 0, json.dumps({'data': data}), ''
                return 1, '', f'unhandled fake gh call: {joined[:120]}'

            return fake_run_gh

        def _mark(row_id: str, src: str, reads: str = '') -> str:
            reads_part = f' reads={reads}' if reads else ''
            return f'<!-- rmp-task: id={row_id} rev=1 stream=Infra src={src} reqs=TBL-R1{reads_part} -->\n\n## 完了条件\nx\n'

        # -- 読む束（#816・DS-R1.1） --
        READS = 'docs/4-domains/chat/README.md#7.-要件と受入,docs/3-shared/auth.md#境界'

        def _bundle_lines_from_mark() -> None:
            lines = gh_task.reading_bundle_lines(_mark('TBL-01', 'tbl@PR9', READS))
            assert lines[0].startswith('読む束（2 件'), lines
            assert lines[1].strip() == '1. docs/4-domains/chat/README.md#7.-要件と受入', lines
            assert lines[2].strip() == '2. docs/3-shared/auth.md#境界', lines
            assert gh_task.reading_bundle_lines('旧い本文\n') == ['読む束なし（旧い形）']
            assert gh_task.reading_bundle_lines(_mark('TBL-01', 'tbl@PR9'))[0].startswith('読む束なし（目印に reads=')

        t('読む束: 目印の reads= を 1 件 1 行で出し、目印が無ければ「読む束なし（旧い形）」', _bundle_lines_from_mark)

        BODY_WITH_PATHS = (
            '## 参照\n- docs/4-domains/chat/README.md:411-423 を読む\n- `docs/harness/doc-formats.md`（形式）\n'
            '- 再掲 docs/4-domains/chat/README.md:411-423 と docs/4-domains/chat/README.md#7.-要件と受入\n'
            '- ../other/docs/not-this.md と apps/docs/x.md は拾わない\n')

        def _bundle_lists_body_paths_without_reads() -> None:
            expect = ['docs/4-domains/chat/README.md:411-423', 'docs/harness/doc-formats.md', 'docs/4-domains/chat/README.md#7.-要件と受入']
            tree = _ds_tree({'docs/4-domains/chat/README.md': 'x\n', 'docs/harness/doc-formats.md': 'x\n'})
            for body in (_mark('TBL-01', 'tbl@PR9') + BODY_WITH_PATHS, '旧い本文\n' + BODY_WITH_PATHS):
                lines = gh_task.reading_bundle_lines(body, tree)
                assert lines[0].startswith('読む束なし') and '3 件' in lines[0], lines
                assert [x.strip().lstrip('- ').strip() for x in lines[1:]] == expect, lines
            # 指摘 2: 作業ツリーの根に無い path は「まだ無い」として分けて出す
            lines = gh_task.reading_bundle_lines('旧い\ndocs/draft/new.md と docs/harness/doc-formats.md\n', tree)
            assert lines[-1] == '  - docs/draft/new.md（まだ無い）' and '  - docs/harness/doc-formats.md' in lines, lines
            # reads= があれば本文の path は出さない
            with_reads = gh_task.reading_bundle_lines(_mark('TBL-01', 'tbl@PR9', READS) + BODY_WITH_PATHS)
            assert with_reads[0].startswith('読む束（2 件') and not any('doc-formats' in x for x in with_reads), with_reads
            # 本文に path が無ければ今の 1 行のまま
            assert gh_task.reading_bundle_lines(_mark('TBL-01', 'tbl@PR9') + 'path なし\n') == ['読む束なし（目印に reads= が無い）']

        t('読む束: reads= が無い issue（目印あり・なし）は本文の docs/ の path（path:line を含む）を重複なく一覧で出す', _bundle_lists_body_paths_without_reads)

        def _start_prints_body_paths_without_reads() -> None:
            gh_task.run_gh = make_write_gh(
                {723: dict(title='task', status=gh_task.READY_STATUS, kind='task', body=_mark('T', 's@PR1') + BODY_WITH_PATHS)}, record=[])
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = gh_task.cmd_start(723, None)
            assert rc == 0 and 'docs/4-domains/chat/README.md:411-423' in buf.getvalue(), buf.getvalue()

        t('start: reads= が無い issue は本文の path の一覧を読む束として出す', _start_prints_body_paths_without_reads)

        def _start_prints_bundle() -> None:
            record: list = []
            for body, expect in ((_mark('TBL-01', 'tbl@PR9', READS), '1. docs/4-domains/chat/README.md'), ('旧い', '読む束なし（旧い形）')):
                gh_task.run_gh = make_write_gh(
                    {720: dict(title='task', status=gh_task.READY_STATUS, kind='task', body=body)}, record=record)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = gh_task.cmd_start(720, None)
                assert rc == 0 and expect in buf.getvalue(), buf.getvalue()
                assert f'Status={gh_task.IN_PROGRESS_STATUS}' in buf.getvalue()

        t('start: 着手したあとに読む束を出す（目印なしは「読む束なし（旧い形）」）', _start_prints_bundle)

        def _start_refused_prints_no_bundle() -> None:
            gh_task.run_gh = make_write_gh(
                {721: dict(title='task', status=gh_task.PENDING_STATUS, kind='task', body=_mark('T', 's@PR1', READS))})
            buf = io.StringIO()
            with redirect_stdout(buf):
                _expect_exit(lambda: gh_task.cmd_start(721, None), 2)
            assert '読む束' not in buf.getvalue(), buf.getvalue()

        t('start: 断った task には読む束を出さない', _start_refused_prints_no_bundle)

        def _show_prints_bundle() -> None:
            inner = make_show_gh(as_pr=False, number=722)

            def with_body(args, *rest):
                rc, out, err = inner(args)
                payload = json.loads(out) if out else None
                # 本物の GitHub は問い合わせた field だけ返す。Issue の枝に body を求めていなければ付けない。
                asks_body = re.search(r'url\s+body\b', ' '.join(args)) is not None
                if asks_body and payload and 'issueOrPullRequest' in payload.get('data', {}).get('repository', {}):
                    payload['data']['repository']['issueOrPullRequest']['body'] = _mark('TBL-01', 'tbl@PR9', READS)
                    out = json.dumps(payload)
                return rc, out, err

            gh_task.run_gh = with_body
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = gh_task.cmd_show(722)
            assert rc == 0 and '2. docs/3-shared/auth.md#境界' in buf.getvalue(), buf.getvalue()

        t('show: 本文の目印の reads= を読む束として出す', _show_prints_bundle)

        # -- 目印の rev と読む束が古い task（#829・DS-R8.2・DS-R9.3・ADR-0696） --
        def _readme(rev: int) -> str:  # rmp-app の docs/4-domains/*/README.md の先頭の形
            return f'# チャット（chat）\n\nid_prefix: CHAT\nkind: 製品の機能\ndomain: chat\nstatus: 現在形\nrev: {rev}\n\n## 1. 概要\nrev: 99\n'

        def _rev_tree(chat: int, proposal: int = 5) -> str:
            return _ds_tree({
                'docs/4-domains/chat/README.md': _readme(chat),
                'docs/4-domains/proposal/README.md': _readme(proposal).replace('chat', 'proposal'),
            })

        def _with_root(root: str, fn):
            saved = os.environ.get('HIRAI_TASK_ROOT')
            os.environ['HIRAI_TASK_ROOT'] = root
            try:
                return fn()
            finally:
                if saved is None:
                    os.environ.pop('HIRAI_TASK_ROOT', None)
                else:
                    os.environ['HIRAI_TASK_ROOT'] = saved

        def _table_body_writes_readme_rev() -> None:
            row = dict(id='TBL-01', stream='Infra', reqs='TBL-R1', done='ok')
            root = _rev_tree(3)
            body = _with_root(root, lambda: gh_task.table_issue_body(row, 'tbl', 'PR9', 'chat, proposal'))
            mark = gh_task.parse_task_mark(body)
            assert mark['rev'] == 'chat:3,proposal:5', body
            assert mark['domain'] == 'chat, proposal', body
            for domain in ('—', ''):
                mark = gh_task.parse_task_mark(_with_root(root, lambda: gh_task.table_issue_body(row, 'tbl', 'PR9', domain)))
                assert 'rev' not in mark, mark
            # README が無い領域は書かない（比べられない）。節の中の rev: は読まない
            mark = gh_task.parse_task_mark(_with_root(root, lambda: gh_task.table_issue_body(row, 'tbl', 'PR9', 'auth（注）, chat（注）')))
            assert mark['rev'] == 'chat:3', mark

        t('table_issue_body: 目印の rev= に domain ごとの現在形 README の rev を書く（—・README なしは書かない）', _table_body_writes_readme_rev)

        # -- 読む束を作る（#1617・DS-R2.1。偽の文書は rmp-app の実物の見出し・表・リンクの形を写す） --
        BUNDLE_README = (
            '# チャット（chat）\n\nid_prefix: CHAT\nkind: 製品の機能\ndomain: chat\nstatus: 現在形\nrev: 3\n\n'
            '## 1. 目的\n\n語は [`glossary.md` の「募集」](../../1-requirements/glossary.md#募集提案マッチ相談する)。'
            'データは [data.md](../../2-architecture/data.md)（節なしのリンクは拾わない）。\n\n'
            '## 2. 概念と規則\n\n不変条件と状態遷移。\n\n'
            '## 3. 境界\n\n### 使う層 3 の部品\n\n| 部品 | 使うもの |\n|---|---|\n'
            '| [`auth-and-permissions.md`](../../3-shared/auth-and-permissions.md) | ACC-06（認証の関門） |\n'
            '| [`jobs-and-files.md`](../../3-shared/jobs-and-files.md) | JOB-25〜JOB-39 |\n'
            '| [`envelope-and-errors.md`](../../3-shared/envelope-and-errors.md) | ERR-01〜ERR-07・ERR-12 |\n\n'
            '## 5. 非機能\n\n監査は [ログと監査](../../2-architecture/ops.md#ログと監査)、'
            '分離は [多テナントの分離](../../2-architecture/security.md#多テナントの分離)。'
            '再掲 [ログと監査](../../2-architecture/ops.md#ログと監査)。\n\n'
            '## 7. 要件と受入\n\n'
            '### 要件 CHAT-R1: 入居者が送るとき、システムは本文を保存する（FR-CHT-001・UC-06）\n\n'
            '- CHAT-R1.1 Given 認証済み When 送る Then 保存する（ACC-06）\n\n'
            '### 要件 CHAT-R2: 入居者が開くとき、システムは一覧を出す（FR-CHT-002）\n\n'
            '- CHAT-R2.1 Given 部屋 When 開く Then 出す\n\n'
            '### 要件 CHAT-R3・CHAT-R4: 届いた通知と取り消し\n\n'
            '- CHAT-R3.1 Given 届いた When 開く Then 既読にする（JOB-30）\n'
        )
        BUNDLE_FILES = {
            'docs/4-domains/chat/README.md': BUNDLE_README,
            'docs/1-requirements/features.md': '# 機能一覧\n\n| FR | 内容 |\n|---|---|\n| FR-CHT-001 | 送る |\n| FR-CHT-002 | 開く |\n',
            'docs/1-requirements/use-cases/UC-06-consult.md': '# UC-06\n',
        }
        CHAT_R1 = 'docs/4-domains/chat/README.md#要件-chat-r1'
        CHAT_CONCEPT = 'docs/4-domains/chat/README.md#2-概念と規則'
        CHAT_BOUNDARY = 'docs/4-domains/chat/README.md#3-境界'
        L2_OPS = 'docs/2-architecture/ops.md#ログと監査'
        L2_SEC = 'docs/2-architecture/security.md#多テナントの分離'
        GLOSSARY = 'docs/1-requirements/glossary.md#募集提案マッチ相談する'

        def _build(reqs: str, domain: str = 'chat', files: dict[str, str] | None = None) -> list[str]:
            root = _ds_tree(BUNDLE_FILES if files is None else files)
            return gh_task.build_reads(reqs, domain, root)

        def _bundle_five_stage_order_without_duplicates() -> None:
            reads = _build('CHAT-R1')
            assert reads == [
                CHAT_R1, CHAT_CONCEPT, CHAT_BOUNDARY,
                'docs/3-shared/auth-and-permissions.md',
                L2_OPS, L2_SEC,
                'docs/1-requirements/features.md:5',
                'docs/1-requirements/use-cases/UC-06-consult.md',
                GLOSSARY,
            ], reads
            assert len(reads) == len(set(reads)), reads  # 再掲のリンクは 1 件

        t('reads: 束の 5 段の順（要件の節 → 部品 → 層 2 → FR と UC → 用語集）で、同じ path は 1 件', _bundle_five_stage_order_without_duplicates)

        def _bundle_layer2_only_sectioned_links() -> None:
            reads = _build('CHAT-R2')
            assert [r for r in reads if r.startswith('docs/2-architecture/')] == [L2_OPS, L2_SEC], reads
            assert not any(r.endswith('/data.md') for r in reads), reads

        t('reads: 層 2 は README の節付きリンクだけ（file だけのリンクは入れない）', _bundle_layer2_only_sectioned_links)

        def _bundle_parts_narrowed_by_id_prefix() -> None:
            parts = lambda reads: [r for r in reads if r.startswith('docs/3-shared/')]
            assert parts(_build('CHAT-R1')) == ['docs/3-shared/auth-and-permissions.md']  # 本文の ACC-06
            assert parts(_build('CHAT-R3')) == ['docs/3-shared/jobs-and-files.md']  # 見出しを共有する R3・R4 の節の JOB-30
            assert parts(_build('CHAT-R4')) == ['docs/3-shared/jobs-and-files.md']
            # 層 3 の ID が 1 つも無い要件・節の見つからない要件は表の全行
            all_rows = ['docs/3-shared/auth-and-permissions.md', 'docs/3-shared/jobs-and-files.md', 'docs/3-shared/envelope-and-errors.md']
            assert parts(_build('CHAT-R2')) == all_rows
            assert parts(_build('CHAT-R99')) == all_rows
            # 複数の要件は ID の頭の和集合
            assert parts(_build('CHAT-R1,CHAT-R3')) == ['docs/3-shared/auth-and-permissions.md', 'docs/3-shared/jobs-and-files.md']

        t('reads: 部品は要件の節に出る層 3 の ID の頭で表の行を絞る（ID が無ければ全行）', _bundle_parts_narrowed_by_id_prefix)

        # 指摘 1〜4（#1617）: 受入の ID の reqs・見出しの [要判断]・領域が複数・境界と概念と規則
        JUDGE_README = BUNDLE_README.replace(
            '### 要件 CHAT-R2: 入居者が開くとき、システムは一覧を出す（FR-CHT-002）',
            '### 要件 CHAT-R2: 入居者が開くとき、システムは一覧を出す（FR-CHT-002）[要判断: D15-B1]')

        def _bundle_acceptance_id_reqs_behaves_like_requirement() -> None:
            by_req, by_acc = _build('CHAT-R1'), _build('CHAT-R1.1')
            assert by_acc == by_req, (by_acc, by_req)  # 節・部品（ACC のみ）・FR・UC が同じ
            assert _build('CHAT-R1.1,CHAT-R1.2') == by_req
            # 受入の ID の reqs でも、要件の見出し行の [要判断] で止まる
            files = {**BUNDLE_FILES, 'docs/4-domains/chat/README.md': JUDGE_README}
            root = _ds_tree(files)
            for reqs in ('CHAT-R2', 'CHAT-R2.1'):
                mark = {'reqs': reqs, 'reads': ','.join(gh_task.build_reads(reqs, 'chat', root))}
                stops = gh_task.bundle_stops(mark, root)
                assert [k for k, _ in stops] == ['judgment'], (reqs, stops)

        t('reads: reqs が受入の ID（A-R1.1）でも要件の節・部品・FR を束に入れ、要件の見出し行の [要判断] で止まる', _bundle_acceptance_id_reqs_behaves_like_requirement)

        def _bundle_anchor_survives_heading_edits() -> None:
            root = _ds_tree({**BUNDLE_FILES, 'docs/4-domains/chat/README.md': JUDGE_README})
            reads = gh_task.build_reads('CHAT-R2', 'chat', root)
            assert reads[0] == 'docs/4-domains/chat/README.md#要件-chat-r2', reads
            mark = {'reqs': 'CHAT-R2', 'reads': ','.join(reads)}
            assert [k for k, _ in gh_task.bundle_stops(mark, root)] == ['judgment']
            # 人が裁定して見出しの印を外し、文言も直す: 見出しは見つかり、束は通る（--reread でも抜けられない 'heading' にならない）
            settled = JUDGE_README.replace(' [要判断: D15-B1]', '').replace('システムは一覧を出す', 'システムは一覧を返す').replace('[要判断: D15-B1]', '')
            root2 = _ds_tree({**BUNDLE_FILES, 'docs/4-domains/chat/README.md': settled})
            assert gh_task.bundle_stops(mark, root2) == [], gh_task.bundle_stops(mark, root2)
            # 並べた見出し（要件 A-R3・A-R4）の後ろの ID の anchor も当たる
            two = gh_task.build_reads('CHAT-R4', 'chat', root2)
            assert two[0] == 'docs/4-domains/chat/README.md#要件-chat-r4', two
            assert gh_task.bundle_stops({'reqs': 'CHAT-R4', 'reads': ','.join(two)}, root2) == []

        t('reads: 要件の anchor は見出しの文に依らない（見出しの [要判断] を外しても文言を直しても start が通る）', _bundle_anchor_survives_heading_edits)

        def _bundle_parts_fallback_is_decided_once_across_domains() -> None:
            other = BUNDLE_README.replace('domain: chat', 'domain: other').replace('CHAT', 'OTHR').replace(
                'JOB-25〜JOB-39', 'COL-01').replace('ACC-06（認証の関門）', 'COL-02')
            files = {**BUNDLE_FILES, 'docs/4-domains/other/README.md': other}
            reads = _build('CHAT-R3', 'other, chat', files)
            parts = [r for r in reads if r.startswith('docs/3-shared/')]
            # 要件の JOB は chat の表にだけある。別の領域の表の全行へ戻さず、JOB の行だけ入れる
            assert parts == ['docs/3-shared/jobs-and-files.md'], parts
            # 層 3 の ID がどの表にも無い要件だけ、全領域の表の全行
            assert len([r for r in _build('CHAT-R2', 'other, chat', files) if r.startswith('docs/3-shared/')]) == 3

        t('reads: 部品を全行に戻すかは領域ごとでなく要件全体で 1 回決める（別の領域の表の全行を混ぜない）', _bundle_parts_fallback_is_decided_once_across_domains)

        def _bundle_includes_concept_and_boundary_sections() -> None:
            reads = _build('CHAT-R2')
            assert reads[:3] == ['docs/4-domains/chat/README.md#要件-chat-r2', CHAT_CONCEPT, CHAT_BOUNDARY], reads
            # 境界の中の [要判断] は、その task の要件を含む行だけが止める
            readme = BUNDLE_README.replace('不変条件と状態遷移。', '不変条件と状態遷移。[要判断: D1]').replace(
                '| ACC-06（認証の関門） |', '| ACC-06（認証の関門）[要判断: D2] |')
            root = _ds_tree({**BUNDLE_FILES, 'docs/4-domains/chat/README.md': readme})
            mark = {'reqs': 'CHAT-R2', 'reads': ','.join(gh_task.build_reads('CHAT-R2', 'chat', root))}
            assert gh_task.bundle_stops(mark, root) == []
            assert len(gh_task.bundle_open_judgments(mark, root)) == 2

        t('reads: (1) 段に「概念と規則」「境界」の節を足す（要件を含まない行の [要判断] では止めない）', _bundle_includes_concept_and_boundary_sections)

        def _bundle_domain_dash_and_missing_readme() -> None:
            # domain が — は (4) だけ（reqs の文に書かれた FR・UC）
            assert _build('FR-CHT-002・UC-06', '—') == ['docs/1-requirements/features.md:6', 'docs/1-requirements/use-cases/UC-06-consult.md']
            assert _build('NTF-10〜13', '—') == []
            # README が無い領域（eu-web など）は飛ばし、ある領域だけで作る
            assert _build('CHAT-R2', 'eu-web, chat（注）')[0].startswith('docs/4-domains/chat/README.md#要件-chat-r2')
            assert _build('CHAT-R2', 'eu-web') == []

        t('reads: domain が — は FR・UC だけ・README が無い領域は飛ばす', _bundle_domain_dash_and_missing_readme)

        def _expand_ids_forms() -> None:
            assert gh_task.expand_ids('ERR-01〜ERR-03・ERR-12') == ['ERR-01', 'ERR-02', 'ERR-03', 'ERR-12']
            assert gh_task.expand_ids('FAV-R1・R2・R5') == ['FAV-R1', 'FAV-R2', 'FAV-R5']
            assert gh_task.expand_ids('FAV-R1〜R4') == ['FAV-R1', 'FAV-R2', 'FAV-R3', 'FAV-R4']
            assert gh_task.expand_ids('FR-ONB-007 と RECR-R1.2') == ['FR-ONB-007', 'RECR-R1.2']

        t('expand_ids: 範囲（〜）・頭の省略（・R2）・枝つきの受入を開く', _expand_ids_forms)

        def _table_body_writes_reads() -> None:
            row = dict(id='TBL-01', stream='Infra', reqs='CHAT-R1', done='ok')
            root = _ds_tree(BUNDLE_FILES)
            body = _with_root(root, lambda: gh_task.table_issue_body(row, 'tbl', 'PR9', 'chat'))
            mark = gh_task.parse_task_mark(body)
            assert mark['reads'].split(',')[0] == CHAT_R1 and len(mark['reads'].split(',')) == 9, mark
            assert mark['reqs'] == 'CHAT-R1' and mark['domain'] == 'chat', mark
            # 束が空のとき（domain —・FR も無い）は reads= を書かない
            bare = _with_root(root, lambda: gh_task.table_issue_body(dict(row, reqs='TBL-R1'), 'tbl', 'PR9', '—'))
            assert 'reads' not in gh_task.parse_task_mark(bare), bare

        t('table_issue_body: 目印に reads= を書く（束が空なら書かない）', _table_body_writes_reads)

        def _dry_run_prints_bundle_size() -> None:
            with open(_table_draft('tbl-bundle.md'), encoding='utf-8') as f:
                draft = f.read().replace('domain: —', 'domain: chat').replace('TBL-R1 | テストが通る', 'CHAT-R1 | テストが通る')
            path = _draft_path('tbl-bundle2.md', draft)
            root = _ds_tree(BUNDLE_FILES)
            rc, out = _with_root(root, lambda: _from_table(path, '--dry-run'))
            assert rc == 0 and '読む束=9 件' in out, out

        t('new --from-table --dry-run: 行ごとに読む束の件数を出す', _dry_run_prints_bundle_size)

        def _warns_when_requirement_is_only_in_the_proposal() -> None:
            root = _ds_tree(BUNDLE_FILES)
            # 提案の ID（TBL-R1）は README の `### 要件` に無い。README の ID と、受入の ID は見つかる
            assert gh_task.unresolved_requirements('TBL-R1・TBL-R2', 'chat', root) == ['TBL-R1', 'TBL-R2']
            assert gh_task.unresolved_requirements('CHAT-R1, CHAT-R3.1, TBL-R9', 'chat', root) == ['TBL-R9']
            assert gh_task.unresolved_requirements('TBL-R1', '—', root) == []  # README が無い提案は比べない
            with open(_table_draft('tbl-bundle.md'), encoding='utf-8') as f:
                draft = f.read().replace('domain: —', 'domain: chat')
            path = _draft_path('tbl-bundle3.md', draft)
            rc, out = _with_root(root, lambda: _from_table(path, '--dry-run'))
            assert rc == 0 and '警告: 要件の節が見つからない: TBL-R1' in out, out
            with open(_table_draft('tbl-bundle.md'), encoding='utf-8') as f:
                ok = f.read().replace('domain: —', 'domain: chat').replace('TBL-R1', 'CHAT-R1')
            rc, out = _with_root(root, lambda: _from_table(_draft_path('tbl-bundle4.md', ok), '--dry-run'))
            assert rc == 0 and '警告' not in out, out

        t('new --from-table: reqs の ID が README の要件に無いとき「要件の節が見つからない」と警告する', _warns_when_requirement_is_only_in_the_proposal)

        # -- 提案側の要件 ID と用語集（#1617 の裁定 2 点。偽の提案は docs/draft/doc-formats.md・agent-favorites.md の形を写す） --
        FAV_HEADING_PROPOSAL = (
            '# 営業のお気に入り\n\nid_prefix: FAV\nkind: 製品の機能\ndomain: chat\nstatus: 承認\n\n'
            '## 1. 問題\n\n## 2. 目指す状態\n\n### 追加された要件\n\n'
            '### 要件 FAV-R1: 入居者が印を置いたとき、システムは印を保存する\n\n'
            '- FAV-R1.1 Given 認証 When 置く Then 保存する（FR-CHT-001・UC-06・JOB-30）\n\n'
            '### 要件 FAV-R2: 入居者が一覧を開いたとき、システムは印の付いた営業だけを返す\n\n'
            '- FAV-R2.1 Given 印 When 開く Then 返す（FR-CHT-002）\n\n'
            '### 変更された要件\n\n'
            '### 要件 CHAT-R2: 一覧は印の付いた営業を先頭に出す（JOB-99）\n\n'
            '### 削除された要件\n\nなし。\n\n## 3. 変える上の層の現在形\n\n### 要件 FAV-R9: 節の外の見出し\n'
        )
        FAV_TABLE_PROPOSAL = (
            '# 営業のお気に入り\n\nid_prefix: FAV\nkind: 製品の機能\ndomain: chat\nstatus: 承認\n\n'
            '## 1. 問題\n\n## 2. 目指す状態\n\n### 追加された要件\n\n| ID | 〜のとき、システムは〜する | 確かめ |\n|---|---|---|\n'
            '| FAV-R1 | 印を置いたとき、保存する（FR-CHT-001・UC-06） | JOB-30 の単体 |\n'
            '| FAV-R2 | 一覧を開いたとき、印の付いた営業だけを返す | 単体 |\n\n'
            '### 削除された要件\n\nなし。\n\n## 3. 変える上の層の現在形\n'
        )
        FAV_REL = 'docs/draft/fav.md'

        def _build_fav(reqs: str, proposal: str, domain: str = 'chat') -> list[str]:
            root = _ds_tree({**BUNDLE_FILES, FAV_REL: proposal})
            return gh_task.build_reads(reqs, domain, root, slug='fav')

        def _notes_fav(reqs: str, proposal: str | None, domain: str = 'chat') -> list[str]:
            root = _ds_tree({**BUNDLE_FILES, **({FAV_REL: proposal} if proposal is not None else {})})
            return _with_root(root, lambda: gh_task._unresolved_notes(reqs, domain, 'fav'))

        def _proposal_requirement_section_heads_the_bundle() -> None:
            reads = _build_fav('FAV-R1', FAV_HEADING_PROPOSAL)
            assert reads[0] == 'docs/draft/fav.md#要件-fav-r1', reads
            assert reads[1:3] == [CHAT_CONCEPT, CHAT_BOUNDARY], reads  # README の概念と規則・境界はそのあと
            assert not any('#要件-chat' in r for r in reads), reads
            root = _ds_tree({**BUNDLE_FILES, FAV_REL: FAV_HEADING_PROPOSAL})
            # 束の anchor は start 側（_read_scope_span）で提案の節に当たり、見出しなしで止まらない
            assert gh_task.bundle_stops({'reqs': 'FAV-R1', 'reads': ','.join(reads), 'src': 'fav@PR9'}, root) == []

        t('reads: reqs が提案の要件 ID のとき、提案の「目指す状態」の要件の節が (1) の先頭に入る', _proposal_requirement_section_heads_the_bundle)

        def _proposal_body_narrows_parts_and_feeds_layer1() -> None:
            parts = lambda reads: [r for r in reads if r.startswith('docs/3-shared/')]
            reads = _build_fav('FAV-R1', FAV_HEADING_PROPOSAL)
            assert parts(reads) == ['docs/3-shared/jobs-and-files.md'], reads  # 受入の JOB-30（README の要件には無い）
            assert 'docs/1-requirements/features.md:5' in reads and 'docs/1-requirements/use-cases/UC-06-consult.md' in reads, reads
            # 別の要件の節の ID（R2 の FR-CHT-002）は混ざらない。層 3 の ID が無ければ表の全行
            r2 = _build_fav('FAV-R2', FAV_HEADING_PROPOSAL)
            assert len(parts(r2)) == 3 and 'docs/1-requirements/features.md:6' in r2 and 'docs/1-requirements/features.md:5' not in r2, r2

        t('reads: 提案の要件の節の本文と受入で部品を絞り、FR・UC を (4) に入れる', _proposal_body_narrows_parts_and_feeds_layer1)

        def _mixed_readme_and_proposal_ids() -> None:
            reads = _build_fav('FAV-R1,CHAT-R1', FAV_HEADING_PROPOSAL)
            assert reads[:2] == ['docs/draft/fav.md#要件-fav-r1', CHAT_R1], reads  # 提案の節が先頭・README の ID は README から
            # 変更された要件（README の ID でもある CHAT-R2）は README の節を使い、提案の節は入れない
            changed = _build_fav('CHAT-R2', FAV_HEADING_PROPOSAL)
            assert changed[0] == 'docs/4-domains/chat/README.md#要件-chat-r2' and not any(r.startswith('docs/draft/') for r in changed), changed
            # 節の外（3 節）の見出しは提案の要件に数えない
            assert _build_fav('FAV-R9', FAV_HEADING_PROPOSAL)[0] != 'docs/draft/fav.md#要件-fav-r9'

        t('reads: README の ID と提案の ID が混ざる reqs（README の ID は README から・提案の節は目指す状態の中だけ）', _mixed_readme_and_proposal_ids)

        def _table_form_proposal_takes_whole_section_and_warns() -> None:
            reads = _build_fav('FAV-R1', FAV_TABLE_PROPOSAL)
            assert reads[0] == 'docs/draft/fav.md#2-目指す状態', reads
            assert [r for r in reads if r.startswith('docs/3-shared/')] == ['docs/3-shared/jobs-and-files.md'], reads  # 表の FAV-R1 の行の JOB-30
            assert 'docs/1-requirements/features.md:5' in reads and 'docs/1-requirements/features.md:6' not in reads, reads
            root = _ds_tree({**BUNDLE_FILES, FAV_REL: FAV_TABLE_PROPOSAL})
            assert gh_task.bundle_stops({'reqs': 'FAV-R1', 'reads': ','.join(reads)}, root) == []
            notes = _notes_fav('FAV-R1', FAV_TABLE_PROPOSAL)
            assert len(notes) == 1 and notes[0].startswith('提案の要件が見出しで見つからない: FAV-R1'), notes

        t('reads: 提案の要件が表の形（### 要件 の見出しが無い）なら節全体を入れ、「提案の要件が見出しで見つからない」と警告する', _table_form_proposal_takes_whole_section_and_warns)

        def _missing_warning_only_when_neither_has_it() -> None:
            assert _notes_fav('FAV-R1', FAV_HEADING_PROPOSAL) == []
            assert _notes_fav('CHAT-R1', FAV_HEADING_PROPOSAL) == []
            assert _notes_fav('FAV-R1,CHAT-R1', FAV_HEADING_PROPOSAL) == []
            missing = _notes_fav('FAV-R1,FAV-R7', FAV_HEADING_PROPOSAL)
            assert len(missing) == 1 and missing[0].startswith('要件の節が見つからない: FAV-R7') and 'FAV-R1' not in missing[0], missing
            assert _notes_fav('FAV-R1', None)[0].startswith('要件の節が見つからない: FAV-R1')  # 提案の file が無い
            assert _notes_fav('FAV-R1', FAV_TABLE_PROPOSAL.replace('FAV-R1', 'FAV-R0'))[0].startswith('要件の節が見つからない: FAV-R1')

        t('reads: 「要件の節が見つからない」は README にも提案にも無いときだけ出す', _missing_warning_only_when_neither_has_it)

        def _before_column_judgment_does_not_stop() -> None:
            # 変更された要件の表の「前」は旧い README の文の引用（agent-templates.md:55 の形）。印は裁定のあとも残る
            proposal = FAV_TABLE_PROPOSAL.replace(
                '### 削除された要件', '### 変更された要件\n\n| ID | 前 | 後 |\n|---|---|---|\n'
                '| PROP-R11.2 | 保存先 `[要判断: PROP-Q14]`・未実装 | FAV-R1〜R2 を満たす |\n\n### 削除された要件')
            root = _ds_tree({**BUNDLE_FILES, FAV_REL: proposal})
            reads = gh_task.build_reads('FAV-R1', 'chat', root, slug='fav')
            mark = {'reqs': 'FAV-R1', 'reads': ','.join(reads)}
            assert 'docs/draft/fav.md#2-目指す状態' in reads and gh_task.bundle_stops(mark, root) == []
            assert gh_task.bundle_open_judgments(mark, root) == []  # 「前」の印は未決の一覧にも出さない
            # 「後」の列の印は、その task の要件を含む行なら止める
            after = proposal.replace('FAV-R1〜R2 を満たす', 'FAV-R1〜R2 を満たす `[要判断: FAV-Q1]`')
            root2 = _ds_tree({**BUNDLE_FILES, FAV_REL: after})
            assert [k for k, _t in gh_task.bundle_stops(mark, root2)] == ['judgment']

        t('start: 提案の変更された要件の表の「前」の列にある [要判断] では止めない（「後」の列の印は止める）', _before_column_judgment_does_not_stop)

        def _other_before_headers_do_not_stop() -> None:
            # 実在の提案の見出し: 変える前 | 変えた後 / 変更前 | 変更後 / 今 | 後 / 1 列の「変更前 → 後」
            for header, row in (('| ID | 変える前 | 変えた後 |', '| PROP-R11.2 | 保存先 `[要判断: PROP-Q14]` | FAV-R1〜R2 を満たす |'),
                                ('| ID | 変更前 | 変更後 |', '| PROP-R11.2 | 保存先 `[要判断: PROP-Q14]` | FAV-R1〜R2 を満たす |'),
                                ('| ID | 今 | 後 |', '| PROP-R11.2 | 保存先 `[要判断: PROP-Q14]` | FAV-R1〜R2 を満たす |'),
                                ('| ID | 変更前 → 後 |', '| PROP-R11.2 | 保存先 `[要判断: PROP-Q14]` → FAV-R1〜R2 を満たす |')):
                proposal = FAV_TABLE_PROPOSAL.replace(
                    '### 削除された要件', f'### 変更された要件\n\n{header}\n|---|---|---|\n{row}\n\n### 削除された要件')
                root = _ds_tree({**BUNDLE_FILES, FAV_REL: proposal})
                reads = gh_task.build_reads('FAV-R1', 'chat', root, slug='fav')
                mark = {'reqs': 'FAV-R1', 'reads': ','.join(reads)}
                assert gh_task.bundle_stops(mark, root) == [], header
            after = proposal.replace('→ FAV-R1〜R2 を満たす', '→ FAV-R1〜R2 を満たす `[要判断: FAV-Q1]`')
            root2 = _ds_tree({**BUNDLE_FILES, FAV_REL: after})
            assert [k for k, _t in gh_task.bundle_stops(mark, root2)] == ['judgment']  # → のあとは止める

        t('start: 「変える前」「変更前」「今」「変更前 → 後」の列の [要判断] でも止めない', _other_before_headers_do_not_stop)

        def _bare_number_continues_only_right_after_id() -> None:
            assert gh_task.expand_ids('NTFM-R8 | SMS を送るとき、8:00〜22:00 に') == ['NTFM-R8'], gh_task.expand_ids('NTFM-R8 | SMS を送るとき、8:00〜22:00 に')
            assert gh_task.expand_ids('SAVED-R3 は 関東ほか1・〜12万円') == ['SAVED-R3']
            assert gh_task.expand_ids('FAV-R1・R2〜R4・6') == ['FAV-R1', 'FAV-R2', 'FAV-R3', 'FAV-R4', 'FAV-R6']
            assert gh_task.expand_ids('FAV-R1〜3') == ['FAV-R1', 'FAV-R2', 'FAV-R3']

        t('reads: ID の頭を省いた数字は直前の ID に続くときだけ ID（時刻・金額の〜は ID にしない）', _bare_number_continues_only_right_after_id)

        def _domain_dash_keeps_reqs_fr_and_uc_with_proposal_section() -> None:
            reads = _build_fav('FAV-R1, FR-CHT-002, UC-06', FAV_HEADING_PROPOSAL.replace('FR-CHT-001・UC-06・', ''), '—')
            assert reads[0] == 'docs/draft/fav.md#要件-fav-r1', reads
            assert 'docs/1-requirements/features.md:6' in reads and 'docs/1-requirements/use-cases/UC-06-consult.md' in reads, reads

        t('reads: domain が — の提案で提案の要件が混ざっても、reqs の FR・UC は (4) に残る', _domain_dash_keeps_reqs_fr_and_uc_with_proposal_section)

        def _only_id_prefix_ids_are_proposal_requirements() -> None:
            proposal = (FAV_HEADING_PROPOSAL.replace('JOB-30）', 'JOB-30・ERR-03）')
                        .replace('Then 返す（', 'Then 返す `[要判断: 並び順]`（'))
            reads = _build_fav('FAV-R1,ERR-03', proposal)
            assert reads[0] == 'docs/draft/fav.md#要件-fav-r1' and 'docs/draft/fav.md#2-目指す状態' not in reads, reads
            notes = _notes_fav('FAV-R1,ERR-01〜ERR-03', proposal)
            assert not any('見出しで見つからない' in n for n in notes), notes
            assert len(notes) == 1 and notes[0].startswith('要件の節が見つからない: ERR-01・ERR-02・ERR-03'), notes
            root = _ds_tree({**BUNDLE_FILES, FAV_REL: proposal})
            assert gh_task.bundle_open_judgments({'reqs': 'FAV-R1', 'reads': ','.join(reads)}, root) == []

        t('reads: 提案の要件に数えるのは id_prefix の頭の ID だけ（受入に出る層 3 の ID で節全体を入れない）', _only_id_prefix_ids_are_proposal_requirements)

        def _glossary_sectioned_links_enter_stage5() -> None:
            readme = BUNDLE_README.replace('## 5. 非機能', '用語は [提案](../../1-requirements/glossary.md#募集提案マッチ相談する)・[マッチ](../../1-requirements/glossary.md#マッチ)・'
                                           '[全体](../../1-requirements/glossary.md)。\n\n## 5. 非機能')
            files = {**BUNDLE_FILES, 'docs/4-domains/chat/README.md': readme}
            reads = _build('CHAT-R2', 'chat', files)
            glossary = [r for r in reads if r.startswith('docs/1-requirements/glossary')]
            assert glossary == [GLOSSARY, 'docs/1-requirements/glossary.md#マッチ'], reads  # 同じ節の再掲は 1 件・file だけのリンクは入れない
            assert reads[-2:] == glossary, reads  # 最後の段
            assert not [r for r in _build('CHAT-R2', 'chat', {**BUNDLE_FILES, 'docs/4-domains/chat/README.md': BUNDLE_README.replace('glossary.md#', 'glossary.md?')})
                        if r.startswith('docs/1-requirements/glossary')]
            # domain が — は README を読まないので入れない
            assert not [r for r in _build('CHAT-R2', '—', files) if 'glossary' in r]

        t('reads: (5) 用語集は README の本文の節付きリンクだけ（file だけのリンクは入れない・domain が — なら入れない）', _glossary_sectioned_links_enter_stage5)

        def _dry_run_uses_the_proposal_itself() -> None:
            def draft(section2: str, name: str) -> str:
                text = (
                    '# 営業のお気に入り\n\nid_prefix: FAV\nkind: 製品の機能\ndomain: chat\nstatus: 承認\n'
                    'approvals: 要件=PR #9 設計=PR #9 task=PR #9\napproved_at: 2026-10-01（PR #9 の merge で承認）\n\n'
                    '## 1. 問題\n\n' + section2 + '## 10. 完了条件\n\n## 11. task\n\n### 11-1. 位置と前後\n\n### 11-3. 表\n\n'
                    '| id | kind | stream | 題名 | 親 | 止める依存 | 要件 | 完了条件 |\n|---|---|---|---|---|---|---|---|\n'
                    '| FAV-T1 | task | Infra | 印を保存する | feature #900 | — | FAV-R1 | テストが通る |\n\n## 12. 履歴\n'
                )
                return _draft_path(name, text)

            root = _ds_tree(BUNDLE_FILES)
            heading = FAV_HEADING_PROPOSAL.split('## 1. 問題\n\n', 1)[1].split('## 3.', 1)[0]
            rc, out = _with_root(root, lambda: _from_table(draft(heading, 'fav.md'), '--dry-run'))
            assert rc == 0 and '警告' not in out and '読む束=' in out, out
            rows = lambda text: int(re.search(r'読む束=(\d+) 件', text).group(1))
            rc2, out2 = _with_root(root, lambda: _from_table(draft(FAV_TABLE_PROPOSAL.split('## 1. 問題\n\n', 1)[1].split('## 3.', 1)[0], 'fav.md'), '--dry-run'))
            assert rc2 == 0 and '警告: 提案の要件が見出しで見つからない: FAV-R1' in out2 and '要件の節が見つからない' not in out2, out2
            assert rows(out) == len(_build_fav('FAV-R1', FAV_HEADING_PROPOSAL)), (out, rows(out))
            # 起票の本文の目印にも提案の節が先頭に入る
            body = _with_root(root, lambda: gh_task.table_issue_body(dict(id='FAV-T1', stream='Infra', reqs='FAV-R1', done='ok'), 'fav', 'PR9', 'chat', FAV_HEADING_PROPOSAL.splitlines()))
            assert gh_task.parse_task_mark(body)['reads'].split(',')[0] == 'docs/draft/fav.md#要件-fav-r1', body

        t('new --from-table: 提案の要件の節を束の先頭に入れ、表の形は警告する（--dry-run・目印の reads=）', _dry_run_uses_the_proposal_itself)

        def _rev_drift_compares_per_domain() -> None:
            root = _rev_tree(4)
            drift = gh_task.rev_drift({'rev': 'chat:3,proposal:5'}, root)
            assert drift == [('chat', 3, 4)], drift
            assert gh_task.rev_drift({'rev': 'chat:4,proposal:5'}, root) == []  # 同じなら出ない
            assert gh_task.rev_drift({'rev': '1'}, root) == []  # 数字だけの旧い目印は比べない
            assert gh_task.rev_drift({'rev': 'auth:1'}, root) == []  # README が無い領域は比べない
            assert gh_task.rev_drift(None, root) == []
            assert gh_task.rev_drift_text(drift) == '読む束が古い（chat 3→4）'

        t('rev_drift: 目印より新しい領域だけを「chat 3→4」で出す（同じ・数字だけ・README なしは出さない）', _rev_drift_compares_per_domain)

        def _start_refuses_stale_rev_and_keeps_status() -> None:
            body = _mark('TBL-01', 'tbl@PR9').replace('rev=1', 'rev=chat:3')
            for approved in (None, '承認 #1'):
                record: list = []
                rest_log: list = []
                gh_task.run_gh = make_write_gh(
                    {730: dict(title='task' + (' ' + gh_task.OPERATION_MARK if approved else ''),
                               status=gh_task.READY_STATUS, kind='task', body=body)},
                    record=record, rest_log=rest_log, graphql_writes=record)
                buf = io.StringIO()
                message = ''
                with redirect_stdout(buf):
                    try:
                        _with_root(_rev_tree(4), lambda: gh_task.cmd_start(730, approved))
                    except gh_task.GhError as exc:
                        assert exc.code == 2, exc.code
                        message = str(exc)
                assert '着手不可' in message and '読む束が古い（chat 3→4）' in message, message
                assert '読む束（' not in buf.getvalue() and '読む束なし' not in buf.getvalue()
                assert record == [] and not any(c[0] != 'GET' for c in rest_log), (record, rest_log)  # Status も本文も書いていない

        t('start: 目印の rev より現在形が新しいと「着手不可」で断り、Status も本文も書かない', _start_refuses_stale_rev_and_keeps_status)

        def _start_passes_when_rev_same_or_old_form() -> None:
            for rev in ('chat:4', '1'):
                gh_task.run_gh = make_write_gh(
                    {731: dict(title='task', status=gh_task.READY_STATUS, kind='task',
                               body=_mark('TBL-01', 'tbl@PR9').replace('rev=1', f'rev={rev}'))}, record=[])
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = _with_root(_rev_tree(4), lambda: gh_task.cmd_start(731, None))
                assert rc == 0 and f'Status={gh_task.IN_PROGRESS_STATUS}' in buf.getvalue(), buf.getvalue()

        t('start: rev が同じ・数字だけの旧い目印は止まらない', _start_passes_when_rev_same_or_old_form)

        def _coverage_reports_stale_rev_tasks() -> None:
            files = {}
            rows = [dict(number=n, status='進行中', kind='task') for n in (41, 42, 43, 44)] + [
                dict(number=45, status='完了', kind='task', state='CLOSED')]
            bodies = {
                41: _mark('TBL-01', 'none@PR1').replace('rev=1', 'rev=chat:3,proposal:5'),
                42: _mark('TBL-02', 'none@PR1').replace('rev=1', 'rev=chat:4'),
                43: _mark('TBL-03', 'none@PR1'),
                44: _mark('TBL-04', 'none@PR1').replace('rev=1', 'rev=proposal:2'),
                45: _mark('TBL-05', 'none@PR1').replace('rev=1', 'rev=chat:1'),
            }
            rc, out, _ = _with_root_cov(files, rows, bodies)
            assert rc == 0, out  # 報告のみ・常に exit 0（ADR-0699）
            assert '読む束が古い issue 2 件' in out, out
            assert '#41 TBL-01（進行中）: 読む束が古い（chat 3→4）' in out, out
            assert '#44 TBL-04（進行中）: 読む束が古い（proposal 2→5）' in out, out
            assert '#42 TBL-02' not in out and '#43 TBL-03' not in out and '#45 TBL-05' not in out, out

        def _with_root_cov(files, rows, bodies):
            real = gh_task._root
            root = _rev_tree(4)
            os.makedirs(os.path.join(root, 'docs', 'draft'), exist_ok=True)
            os.environ['HIRAI_TASK_ROOT'] = root
            try:
                return _run_coverage_in(root, files, rows, bodies)
            finally:
                os.environ.pop('HIRAI_TASK_ROOT', None)

        def _run_coverage_in(root, files, rows, bodies):
            calls: list = []
            gh_task.run_gh = make_ds_board_gh(rows, bodies, calls=calls)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = gh_task.cmd_coverage()
            return rc, buf.getvalue(), calls

        t('coverage: 現在形の rev が目印より新しい open の issue を「読む束が古い（chat 3→4）」で出す（閉じた・同じ・数字だけは出さない）', _coverage_reports_stale_rev_tasks)

        # -- 同じ feature の中の依存（#829・裁定 1） --
        def _sibling_specs(blocker_status: str, *, blocker_parent: int | None = 800, own_status: str = '依存待ち',
                           extra: dict | None = None) -> dict:
            specs = {
                801: dict(title='task', status=own_status, kind='task', parent_number=800,
                          blockers=[(802, 'OPEN')], body=_mark('TBL-02', 'tbl@PR9')),
                802: dict(title='task', status=blocker_status, kind='task', parent_number=blocker_parent),
                800: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
            }
            specs.update(extra or {})
            return specs

        def _start_sibling(specs: dict) -> tuple[int, str, str, list]:
            record: list = []
            gh_task.run_gh = make_write_gh(specs, record=record)
            buf = io.StringIO()
            message = ''
            rc = -1
            with redirect_stdout(buf):
                try:
                    rc = gh_task.cmd_start(801, None)
                except gh_task.GhError as exc:
                    rc = exc.code
                    message = str(exc)
            return rc, message, buf.getvalue(), record

        def _start_passes_for_in_flight_sibling_blocker() -> None:
            for blocker_status in (gh_task.IN_PROGRESS_STATUS, gh_task.REVIEW_STATUS):
                for own in ('依存待ち', gh_task.READY_STATUS, gh_task.PENDING_STATUS):
                    rc, message, out, record = _start_sibling(_sibling_specs(blocker_status, own_status=own))
                    assert rc == 0, (blocker_status, own, rc, message)
                    assert record == [('F_Status', 'O_Status_進行中')], (blocker_status, own, record)
                    assert f'Status={gh_task.IN_PROGRESS_STATUS}' in out, out

        t('start: 未完了の blocker がすべて同じ feature の子で 進行中・レビュー中なら通す（依存待ち・着手可・承認待ちから）', _start_passes_for_in_flight_sibling_blocker)

        def _start_still_stops_for_other_blockers() -> None:
            stops = {
                '前の task が承認待ち': _sibling_specs(gh_task.PENDING_STATUS),
                '前の task が着手可': _sibling_specs(gh_task.READY_STATUS),
                '前の task が依存待ち': _sibling_specs(gh_task.DEP_STATUS),
                '前の task が判断待ち': _sibling_specs(gh_task.JUDGMENT_STATUS),
                '前の task が別の feature': _sibling_specs(gh_task.IN_PROGRESS_STATUS, blocker_parent=900),
                '前の task に親が無い': _sibling_specs(gh_task.IN_PROGRESS_STATUS, blocker_parent=None),
                '前の task が板に無い': {k: v for k, v in _sibling_specs(gh_task.IN_PROGRESS_STATUS).items() if k != 802},
            }
            for label, specs in stops.items():
                rc, message, _out, record = _start_sibling(specs)
                assert rc == 2 and '未完了の blocked by がある: #802' in message, (label, rc, message)
                assert record == [], (label, record)  # Status を書かない
            # 2 本のうち 1 本が止める blocker なら、止めている番号だけを出して断る
            specs = _sibling_specs(gh_task.IN_PROGRESS_STATUS)
            specs[801]['blockers'] = [(802, 'OPEN'), (803, 'OPEN'), (804, 'CLOSED')]
            specs[803] = dict(title='task', status=gh_task.READY_STATUS, kind='task', parent_number=800)
            rc, message, _out, record = _start_sibling(specs)
            assert rc == 2 and '#803' in message and '#802' not in message and '#804' not in message, message
            assert record == [], record

        t('start: 前の task が承認待ち・着手可・依存待ち・別の feature・板に無いなら止まる（止める番号だけを出す）', _start_still_stops_for_other_blockers)

        def _start_dependent_keeps_approval_and_parent_gates() -> None:
            # 依存待ちを通す経路も、承認待ちの経路と同じ task_not_startable_reason を通る（目印・親・親の blocked by）
            cases = {
                '依存待ち × [操作]': (_sibling_specs(gh_task.IN_PROGRESS_STATUS), '[操作]', '目印つき'),
                '依存待ち × [User]': (_sibling_specs(gh_task.IN_PROGRESS_STATUS), '[User]', '目印つき'),
                '依存待ち × 親 feature が承認待ち': (
                    _sibling_specs(gh_task.IN_PROGRESS_STATUS, extra={
                        800: dict(title='feature', status=gh_task.PENDING_STATUS, kind='feature')}),
                    '', '着手可ではない'),
                '依存待ち × 親 feature に別 feature の open blocker': (
                    _sibling_specs(gh_task.IN_PROGRESS_STATUS, extra={
                        800: dict(title='feature', status=gh_task.READY_STATUS, kind='feature', blockers=[(900, 'OPEN')]),
                        900: dict(title='feature', status=gh_task.IN_PROGRESS_STATUS, kind='feature')}),
                    '', '未完了の blocked by がある: #900'),
            }
            for label, (specs, mark, word) in cases.items():
                if mark:
                    specs[801]['title'] = f'task {mark}'
                rc, message, _out, record = _start_sibling(specs)
                assert rc == 2 and word in message, (label, rc, message)
                assert record == [], (label, record)  # Status も出どころの行も書かない

        t('start: 依存待ちを同じ feature の blocker で通すときも、目印・親 feature の Status・親の blocked by を承認待ちと同じく見る', _start_dependent_keeps_approval_and_parent_gates)

        def _start_stops_for_foreign_or_unresolvable_blocker() -> None:
            # 別 repo の blocker: 番号が同じ feature の進行中の兄弟に当たっても通さない
            specs = _sibling_specs(gh_task.IN_PROGRESS_STATUS)
            specs[801]['blockers'] = [(802, 'OPEN', 'other-org/other-repo')]
            rc, message, _out, record = _start_sibling(specs)
            assert rc == 2 and '未完了の blocked by がある: #802' in message and record == [], (rc, message, record)
            # 別 repo の blocker の番号が、この repo の PR・存在しない番号（本物は errors つきで exit 1）
            specs = _sibling_specs(gh_task.IN_PROGRESS_STATUS)
            specs[801]['blockers'] = [(1500, 'OPEN', 'other-org/other-repo')]
            record = []
            gh_task.run_gh = make_write_gh(specs, record=record, strict_missing=True)
            try:
                gh_task.cmd_start(801, None)
                raise AssertionError('exit 2 で止まるはず')
            except gh_task.GhError as exc:
                assert exc.code == 2 and '未完了の blocked by がある: #1500' in str(exc), (exc.code, str(exc))
            assert record == [], record
            # repo 情報が無い（古い応答）番号がこの repo の PR で引けないときも exit 2
            specs = _sibling_specs(gh_task.IN_PROGRESS_STATUS)
            specs[801]['blockers'] = [(1500, 'OPEN')]
            gh_task.run_gh = make_write_gh(specs, record=record, strict_missing=True)
            try:
                gh_task.cmd_start(801, None)
                raise AssertionError('exit 2 で止まるはず')
            except gh_task.GhError as exc:
                assert exc.code == 2 and '#1500' in str(exc), (exc.code, str(exc))

        t('start: 別 repo の blocker・この repo の issue として引けない番号（NOT_FOUND）は exit 2 で止める（exit 1 で落ちず、同じ番号の兄弟に当てない）', _start_stops_for_foreign_or_unresolvable_blocker)

        # -- 読む束の中の要判断・失効・取り込み済み（#829・裁定 2・DS-R8.2） --
        def _draft_file(status: str) -> str:  # rmp-app の docs/draft/*.md の先頭の形
            return (f'# 表の提案\n\nstatus: {status}\napproved_at: 2026-10-02（PR #9 の merge で承認）\n'
                    'kind: 製品の機能\ndomain: chat\nimplements: —\n\n## 1. 背景\n本文\n')

        README_WITH_OPEN = _readme(4) + '\n## 7. 要件と受入\n営業の登録の入口（TBL-R1）は未決 `[要判断: #621]`。\n'

        def _start_in_tree(files: dict[str, str], body: str) -> tuple[int, str, str, list]:
            record: list = []
            gh_task.run_gh = make_write_gh(
                {740: dict(title='task', status=gh_task.READY_STATUS, kind='task', body=body)}, record=record)
            buf = io.StringIO()
            message = ''
            rc = -1
            with redirect_stdout(buf):
                try:
                    rc = _with_root(_ds_tree(files), lambda: gh_task.cmd_start(740, None))
                except gh_task.GhError as exc:
                    rc, message = exc.code, str(exc)
            return rc, message, buf.getvalue(), record

        def _start_stops_for_bundle_docs() -> None:
            readme = 'docs/4-domains/chat/README.md'
            CLEAN_README = _readme(4) + '\n## 7. 要件と受入\n印の無い節。\n'
            reads = f'{readme}#7.-要件と受入,docs/draft/tbl.md:3-9'
            stops = {
                '束の文書に [要判断: #n]': ({readme: README_WITH_OPEN, 'docs/draft/tbl.md': _draft_file('承認')}, '[要判断]'),
                '束の提案が失効': ({readme: CLEAN_README, 'docs/draft/tbl.md': _draft_file('失効')}, '失効'),
                '束の提案が取り込み済み': ({readme: CLEAN_README, 'docs/draft/tbl.md': _draft_file('取り込み済み')}, '取り込み済み'),
            }
            for label, (files, word) in stops.items():
                rc, message, out, record = _start_in_tree(files, _mark('TBL-01', 'tbl@PR9', reads).replace('rev=1 ', ''))
                assert rc == 2 and '着手不可' in message and word in message, (label, rc, message)
                assert record == [] and '読む束（' not in out, (label, record, out)  # Status を書かず、束も出さない
            # 通る: 印も失効も無い束・無い file・失効した提案が束の外にある・[要判断] は本文の参照の path にだけある
            passes = {
                '印の無い束': ({readme: CLEAN_README, 'docs/draft/tbl.md': _draft_file('承認')}, reads),
                '束の file が無い': ({}, reads),
                '承認の src は束に入っていなくても通る': ({readme: CLEAN_README, 'docs/draft/tbl.md': _draft_file('承認')}, readme),
            }
            for label, (files, bundle) in passes.items():
                rc, message, out, record = _start_in_tree(files, _mark('TBL-01', 'tbl@PR9', bundle).replace('rev=1 ', ''))
                assert rc == 0 and record == [('F_Status', 'O_Status_進行中')], (label, rc, message, record)

        t('start: reads= があれば束の各 path を見て、[要判断] の印・失効・取り込み済みの提案で「着手不可」と断る（Status を書かない）', _start_stops_for_bundle_docs)

        def _start_bundle_scope_is_the_section() -> None:
            readme = 'docs/4-domains/chat/README.md'
            other = '\n## 4. 決定と未決\n| 未決 | TBL-R1.2 の確かめ `[要判断: #700]` |\n'
            files = {readme: _readme(4) + '\n## 1. 目的\n目的の文。印の書き方は `[要判断: <ID>]` と `[要判断: …]`。\n' + other}
            for label, bundle in (
                ('見出しの節だけ', f'{readme}#1.-目的'),
                ('行の範囲だけ', f'{readme}:1-3'),
            ):
                rc, message, _out, record = _start_in_tree(files, _mark('TBL-01', 'tbl@PR9', bundle).replace('rev=1 ', ''))
                assert rc == 0 and record == [('F_Status', 'O_Status_進行中')], (label, rc, message, record)
            # 束の節に印があれば止まる・path だけは file 全体を見る
            for label, bundle in (('束の節に印', f'{readme}#4.-決定と未決'), ('path だけ', readme)):
                rc, message, _out, record = _start_in_tree(files, _mark('TBL-01', 'tbl@PR9', bundle).replace('rev=1 ', ''))
                assert rc == 2 and '[要判断]' in message and record == [], (label, rc, message)

        t('start: 読む束の範囲だけを見る（#見出しはその節・:行はその行）。束の外の節の [要判断] と、書き方の説明の [要判断: <ID>] では止まらない', _start_bundle_scope_is_the_section)

        def _start_bundle_github_anchor_forms() -> None:
            readme = 'docs/4-domains/chat/README.md'
            body = (
                _readme(4)
                + '\n### STG の通し確認（LINE）\n印の無い節。\n'
                + '\n### 要件 CHAT-R14: 登録（NFR-SEC-003）\n印の無い要件。\n'
                + '\n### 画面\n1 つ目。\n'
                + '\n### 画面\n2 つ目（TBL-R1）。 `[要判断: #800]`\n'
                + '\n### 未決\nTBL-R1 `[要判断: #801]`\n'
            )
            files = {readme: body}
            lines = body.splitlines()
            plain_line = next(i for i, ln in enumerate(lines, 1) if ln == '印の無い節。')
            open_line = next(i for i, ln in enumerate(lines, 1) if '#801' in ln)
            passes = {
                'GitHub の slug（括弧・全角記号を落とす）': f'{readme}#stg-の通し確認line',
                '要件の見出し（: ・（）を含む）': f'{readme}#要件-chat-r14-登録nfr-sec-003',
                '重複見出しの最初': f'{readme}#画面',
                '行 anchor #L': f'{readme}#L{plain_line}',
            }
            for label, bundle in passes.items():
                rc, message, _out, record = _start_in_tree(files, _mark('TBL-01', 'tbl@PR9', bundle).replace('rev=1 ', ''))
                assert rc == 0 and record == [('F_Status', 'O_Status_進行中')], (label, rc, message, record)
            stops = {
                '重複見出しの 2 つ目 (-1)': (f'{readme}#画面-1', '[要判断]'),
                '行 anchor の範囲 #La-Lb': (f'{readme}#L{open_line - 1}-L{open_line}', '[要判断]'),
                '見出しが見つからない': (f'{readme}#存在しない見出し', '見出しが見つからない'),
            }
            for label, (bundle, word) in stops.items():
                rc, message, _out, record = _start_in_tree(files, _mark('TBL-01', 'tbl@PR9', bundle).replace('rev=1 ', ''))
                assert rc == 2 and word in message and record == [], (label, rc, message, record)
                assert '範囲に' not in message or word == '[要判断]', message

        t('start: 読む束の #anchor は GitHub の slug・重複 -1・#L 行でも当たる。見つからない見出しは理由を分けて止める', _start_bundle_github_anchor_forms)

        def _start_without_reads_checks_only_src_draft() -> None:
            readme = 'docs/4-domains/chat/README.md'
            for status in ('失効', '取り込み済み'):
                rc, message, _out, record = _start_in_tree(
                    {'docs/draft/tbl.md': _draft_file(status)}, _mark('TBL-01', 'tbl@PR9'))
                assert rc == 2 and '着手不可' in message and status in message and 'tbl' in message, (status, message)
                assert record == [], record
            ok_body = _mark('TBL-01', 'tbl@PR9') + f'参照: {readme}:10-20\n'
            for label, files, body in (
                ('src の提案が承認', {'docs/draft/tbl.md': _draft_file('承認')}, ok_body),
                ('src の提案の file が無い', {}, ok_body),
                # 本文の path の文書に [要判断] があっても見ない
                ('本文の path は見ない', {readme: README_WITH_OPEN}, ok_body),
                ('目印が無い旧い形', {readme: README_WITH_OPEN, 'docs/draft/tbl.md': _draft_file('失効')}, f'旧い本文 {readme}\n'),
            ):
                rc, message, _out, record = _start_in_tree(files, body)
                assert rc == 0 and record == [('F_Status', 'O_Status_進行中')], (label, rc, message, record)

        t('start: reads= が無い issue は src= の提案の status（失効・取り込み済み）だけを見る（本文の path の文書は見ない）', _start_without_reads_checks_only_src_draft)

        # -- 束の中の [要判断]: その task の要件を含む行だけで止める（#1617・裁定 3） --
        STOP_README = (
            _readme(4) + '\n## 7. 要件と受入\n\n'
            '### 要件 TBL-R1: 送る（FR-CHT-001）\n\n'
            '- TBL-R1.2 Given 認証 When 送る Then 弾く `[要判断: #1]`\n'
            '- TBL-R10 Given 別の要件 When 開く Then 出す `[要判断: #2]`\n'
            '- 補足 `[要判断: #3]`\n'
        )

        def _stop_only_on_lines_naming_the_requirement() -> None:
            readme = 'docs/4-domains/chat/README.md'
            # 受入 TBL-R1.2 の行で止まる（理由に path:行）。TBL-R10 は TBL-R1 ではない
            rc, message, _out, record = _start_in_tree({readme: STOP_README}, _mark('TBL-01', 'tbl@PR9', readme).replace('rev=1 ', ''))
            assert rc == 2 and '[要判断]' in message and f'{readme}:' in message and record == [], (rc, message)
            # 要件を含む行が無い束は通り、未決は止めない一覧に出る
            other = _readme(4) + '\n## 7. 要件と受入\n- TBL-R10 Given 別 When 開く Then 出す `[要判断: #2]`\n- 補足 `[要判断: #3]`\n'
            rc, message, out, record = _start_in_tree({readme: other}, _mark('TBL-01', 'tbl@PR9', readme).replace('rev=1 ', ''))
            assert rc == 0 and record == [('F_Status', 'O_Status_進行中')], (rc, message, record)
            assert '読む束の未決 2 件（止めない' in out and f'{readme}:13' in out and f'{readme}:14' in out, out

        t('start: この task の要件 ID（と受入 <ID>.<n>）を含む行の [要判断] だけで止め、ほかは「未決 N 件（止めない）」と path:行 で出す', _stop_only_on_lines_naming_the_requirement)

        def _stop_ids_expand_ranges_and_no_reqs() -> None:
            readme = 'docs/4-domains/chat/README.md'
            body = _readme(4) + '\n- TBL-R3 の確かめ `[要判断: #5]`\n'
            ranged = _mark('TBL-01', 'tbl@PR9', readme).replace('rev=1 ', '').replace('reqs=TBL-R1', 'reqs=TBL-R1〜R3')
            rc, message, _out, _rec = _start_in_tree({readme: body}, ranged)
            assert rc == 2 and '[要判断]' in message, (rc, message)  # 範囲の中の R3
            no_reqs = _mark('TBL-01', 'tbl@PR9', readme).replace('rev=1 ', '').replace(' reqs=TBL-R1', '')
            rc, message, out, _rec = _start_in_tree({readme: body}, no_reqs)
            assert rc == 0 and '読む束の未決 1 件' in out, (rc, message, out)  # 要件が無い task は止めず一覧だけ

        t('start: reqs= の範囲（R1〜R3）を開いて照らす。reqs= が無い task は [要判断] で止めず一覧に出す', _stop_ids_expand_ranges_and_no_reqs)

        def _stop_keeps_other_reasons() -> None:
            readme = 'docs/4-domains/chat/README.md'
            clean = _readme(4) + '\n## 7. 要件と受入\n- 補足 `[要判断: #3]`\n'
            cases = {
                '失効': ({readme: clean, 'docs/draft/tbl.md': _draft_file('失効')}, f'{readme},docs/draft/tbl.md', '失効'),
                '取り込み済み': ({readme: clean, 'docs/draft/tbl.md': _draft_file('取り込み済み')}, f'{readme},docs/draft/tbl.md', '取り込み済み'),
                '見出しなし': ({readme: clean}, f'{readme}#存在しない', '見出しが見つからない'),
            }
            for label, (files, bundle, word) in cases.items():
                rc, message, _out, record = _start_in_tree(files, _mark('TBL-01', 'tbl@PR9', bundle).replace('rev=1 ', ''))
                assert rc == 2 and word in message and record == [], (label, rc, message)
            rc, message, _out, _rec = _start_in_tree({readme: clean}, _mark('TBL-01', 'tbl@PR9', readme).replace('rev=1', 'rev=chat:3'))
            assert rc == 2 and '読む束が古い' in message, (rc, message)

        t('start: 失効・取り込み済み・見出しなし・rev の差の止まり方は変えない', _stop_keeps_other_reasons)

        # -- start --reread（#829・裁定 5。止まった task から抜ける道） --
        def _reread_run(files: dict[str, str], body: str, *, reread: bool = True, fail_status_write: bool = False,
                        title: str = 'task', status: str | None = None, approved: str | None = None) -> dict:
            """偽 gh で start を 1 回走らせる。本文の PATCH（REST）を受けたら item の body を差し替える
            （2 回目の start が新しい本文を読む）。Status の書き込み（Project item の PATCH）は fail_status_write で落とせる。"""
            spec = dict(title=title, status=status or gh_task.READY_STATUS, kind='task', body=body, parent_number=751)
            record: list = []
            patches: list = []

            def rest_handler(method, path, payload):
                if method == 'PATCH' and re.match(r'^repos/[^/]+/[^/]+/issues/750$', path):
                    patches.append(payload)
                    spec['body'] = payload['body']
                    return {}
                return None

            inner = make_write_gh({750: spec, 751: dict(title='feature', status=gh_task.READY_STATUS, kind='feature')},
                                  record=record, rest_handler=rest_handler)

            def fake(args, input_text=None):
                if fail_status_write and args[:3] == ['api', '-X', 'PATCH'] and 'projectsV2' in args[3]:
                    return 1, '', 'boom'
                return inner(args, input_text)

            gh_task.run_gh = fake
            root = _ds_tree(files)
            buf = io.StringIO()
            rc, message = -1, ''
            with redirect_stdout(buf):
                try:
                    rc = _with_root(root, lambda: gh_task.cmd_start(750, approved, reread=reread))
                except gh_task.GhError as exc:
                    rc, message = exc.code, str(exc)
            return dict(rc=rc, message=message, out=buf.getvalue(), record=record, patches=patches, spec=spec, root=root,
                        again=lambda: _reread_again(spec, root))

        def _reread_again(spec: dict, root: str) -> tuple[int, str]:
            """同じ task をもう一度 --reread なしで start する（Status は着手可に戻して）。"""
            gh_task.run_gh = make_write_gh({750: dict(spec, status=gh_task.READY_STATUS)}, record=[])
            try:
                return _with_root(root, lambda: gh_task.cmd_start(750, None)), ''
            except gh_task.GhError as exc:
                return exc.code, str(exc)

        REREAD_TODAY = datetime.date.today().isoformat()
        REREAD_TAIL = '\n## 完了条件\nx\n\n## 出どころ\n- 本文の別の行  \n\t末尾に空白と tab があり、改行は CRLF\r\nchat:3 rev=1\n\n  '

        def _reread_body(rev: str = 'chat:3,proposal:5', src: str = 'tbl@PR9') -> str:
            return (f'<!-- rmp-task: id=TBL-01 rev={rev} stream=Infra src={src} domain=chat, proposal reqs=TBL-R1 -->\n'
                    + REREAD_TAIL)

        def _reread_rewrites_stale_rev() -> None:
            files = {'docs/4-domains/chat/README.md': _readme(4), 'docs/4-domains/proposal/README.md': _readme(5).replace('chat', 'proposal')}
            body = _reread_body()
            # --reread なしは止まる・案内は「読み直してから start <n> --reread」
            res = _reread_run(files, body, reread=False)
            assert res['rc'] == 2 and 'start 750 --reread' in res['message'] and res['patches'] == [] and res['record'] == [], res
            # --reread で目印の rev だけを今の版へ書き直して着手する（proposal は変わらない）
            res = _reread_run(files, body)
            assert res['rc'] == 0 and res['record'] == [('F_Status', 'O_Status_進行中')], res
            assert len(res['patches']) == 1, res['patches']
            new = res['patches'][0]['body']
            first, _, rest_new = new.partition('\n')
            _, _, rest_old = body.partition('\n')
            assert first == ('<!-- rmp-task: id=TBL-01 rev=chat:4,proposal:5 stream=Infra src=tbl@PR9 '
                             'domain=chat, proposal reqs=TBL-R1 -->'), first
            assert rest_new.encode() == rest_old.encode(), 'rev 以外の行が 1 バイトも変わらない'
            assert 'reread=' not in new
            rc, msg = res['again']()
            assert rc == 0, msg  # 書き直したあとは --reread なしでも通る

        t('start --reread: 目印の rev が古い task は rev を今の版へ書き直して着手する（本文の他の行は 1 バイトも変えない）', _reread_rewrites_stale_rev)

        def _reread_marks_merged_src() -> None:
            files = {'docs/draft/tbl.md': _draft_file('取り込み済み')}
            body = _mark('TBL-01', 'tbl@PR9')
            res = _reread_run(files, body, reread=False)
            assert res['rc'] == 2 and 'start 750 --reread' in res['message'] and res['patches'] == [], res
            res = _reread_run(files, body)
            assert res['rc'] == 0 and res['record'] == [('F_Status', 'O_Status_進行中')], res
            new = res['patches'][0]['body']
            assert new.partition('\n')[0] == ('<!-- rmp-task: id=TBL-01 rev=1 stream=Infra src=tbl@PR9 reqs=TBL-R1 '
                                              f'reread={REREAD_TODAY} -->'), new.partition('\n')[0]
            assert new.partition('\n')[2] == body.partition('\n')[2]
            rc, msg = res['again']()  # 2 回目の start は止まらない
            assert rc == 0, msg

        t('start --reread: 取り込み済みの src の task は reread=<日付> を足して着手し、2 回目の start は止まらない', _reread_marks_merged_src)

        def _start_checks_src_draft_even_with_reads() -> None:
            # #1617 の前は reads= が無く src= の提案の status で止まっていた。reads= が付いても（提案が束に入らなくても）止める
            readme = 'docs/4-domains/chat/README.md'
            clean = _readme(4) + '\n## 7. 要件と受入\n印の無い節。\n'
            for status, kind in (('失効', 'expired'), ('取り込み済み', 'merged')):
                files = {readme: clean, 'docs/draft/tbl.md': _draft_file(status)}
                body = _mark('TBL-01', 'tbl@PR9', f'{readme}#7.-要件と受入').replace('rev=1 ', '')
                stops = gh_task.bundle_stops(gh_task.parse_task_mark(body), _ds_tree(files))
                assert [k for k, _t in stops] == [kind], (status, stops)
                rc, message, _out, record = _start_in_tree(files, body)
                assert rc == 2 and '着手不可' in message and 'src=tbl' in message and status in message and record == [], (status, rc, message)
            # 提案が束にも入っているときは理由を二重に出さない
            both = _mark('TBL-01', 'tbl@PR9', f'{readme}#7.-要件と受入,docs/draft/tbl.md').replace('rev=1 ', '')
            stops = gh_task.bundle_stops(gh_task.parse_task_mark(both), _ds_tree({readme: clean, 'docs/draft/tbl.md': _draft_file('失効')}))
            assert len(stops) == 1, stops
            # --reread で抜けられるのは取り込み済みだけ（失効は止めたまま）
            body = _mark('TBL-01', 'tbl@PR9', f'{readme}#7.-要件と受入')
            merged = _reread_run({readme: clean, 'docs/draft/tbl.md': _draft_file('取り込み済み')}, body)
            assert merged['rc'] == 0 and 'reread=' in merged['patches'][0]['body'], merged
            expired = _reread_run({readme: clean, 'docs/draft/tbl.md': _draft_file('失効')}, body)
            assert expired['rc'] == 2 and expired['patches'] == [], expired

        t('start: reads= と src= を両方持つ目印でも、src= の提案が失効なら止まり、取り込み済みなら止まって --reread で抜ける', _start_checks_src_draft_even_with_reads)

        def _reread_approved_operation_rewrites_mark_first() -> None:
            files = {'docs/4-domains/chat/README.md': _readme(4), 'docs/4-domains/proposal/README.md': _readme(5).replace('chat', 'proposal')}
            body = _reread_body()
            res = _reread_run(files, body, title='[操作] task', status=gh_task.PENDING_STATUS, approved='x')
            assert res['rc'] == 0, res
            assert len(res['patches']) == 2, res['patches']  # 目印の書き直し → 出どころの追記
            assert res['patches'][0]['body'].partition('\n')[0].count('rev=chat:4,proposal:5') == 1, res['patches'][0]
            last = res['patches'][1]['body']
            assert last.partition('\n')[0] == res['patches'][0]['body'].partition('\n')[0], last
            assert last.endswith('- 出どころ: x\n'), last
            assert res['record'] == [('F_Status', 'O_Status_進行中')], res['record']

        t('start --reread --approved: [操作] の task も目印の rev を先に書き直し、出どころを足して着手する', _reread_approved_operation_rewrites_mark_first)

        def _reread_marks_merged_reads_file() -> None:
            files = {'docs/draft/b.md': _draft_file('取り込み済み')}
            body = _mark('TBL-01', 'tbl@PR9', 'docs/draft/b.md').replace('rev=1 ', '')
            res = _reread_run(files, body, reread=False)
            assert res['rc'] == 2 and '取り込み済み' in res['message'] and res['patches'] == [] and res['record'] == [], res
            res = _reread_run(files, body)
            assert res['rc'] == 0 and res['record'] == [('F_Status', 'O_Status_進行中')], res
            assert len(res['patches']) == 1, res['patches']
            first = res['patches'][0]['body'].partition('\n')[0]
            assert first.endswith(f'reread={REREAD_TODAY} -->'), first
            rc, msg = res['again']()  # そのあとの --reread なしの start も止まらない
            assert rc == 0, msg

        t('start --reread: reads= の束の file が取り込み済みの task も reread=<日付> を足して着手し、2 回目は止まらない', _reread_marks_merged_reads_file)

        def _reread_keeps_human_stops() -> None:
            readme = 'docs/4-domains/chat/README.md'
            cases = {
                '失効': ({'docs/draft/tbl.md': _draft_file('失効')}, _mark('TBL-01', 'tbl@PR9'), '失効'),
                '[要判断]': ({readme: README_WITH_OPEN}, _mark('TBL-01', 'tbl@PR9', readme).replace('rev=1 ', ''), '[要判断]'),
                '失効と取り込み済み': ({'docs/draft/tbl.md': _draft_file('失効'), 'docs/draft/b.md': _draft_file('取り込み済み')},
                                  _mark('TBL-01', 'tbl@PR9', 'docs/draft/tbl.md,docs/draft/b.md').replace('rev=1 ', ''), '失効'),
            }
            for label, (files, body, word) in cases.items():
                res = _reread_run(files, body)
                assert res['rc'] == 2 and '着手不可' in res['message'] and word in res['message'], (label, res)
                assert res['patches'] == [] and res['record'] == [], (label, res)  # 目印も Status も書かない
            # rev が古くても、失効が同居すれば目印は書き直さない
            files = {'docs/4-domains/chat/README.md': _readme(4), 'docs/draft/tbl.md': _draft_file('失効')}
            res = _reread_run(files, _reread_body(rev='chat:3', src='tbl@PR9'))
            assert res['rc'] == 2 and res['patches'] == [] and res['record'] == [], res

        t('start --reread: 失効の提案・[要判断] の印では止めたまま（目印も Status も書かない）', _reread_keeps_human_stops)

        def _reread_without_reason_is_plain_start() -> None:
            files = {'docs/4-domains/chat/README.md': _readme(4), 'docs/draft/tbl.md': _draft_file('承認')}
            for body in (_reread_body(rev='chat:4'), _mark('TBL-01', 'tbl@PR9'), '旧い本文\n'):
                res = _reread_run(files, body)
                assert res['rc'] == 0 and res['record'] == [('F_Status', 'O_Status_進行中')], res
                assert res['patches'] == [], res['patches']  # 目印を書き換えない

        t('start --reread: 止まる理由が無い task に付けても通常の start と同じ（目印を書き換えない）', _reread_without_reason_is_plain_start)

        def _reread_status_write_failure_leaves_retryable_state() -> None:
            files = {'docs/4-domains/chat/README.md': _readme(4)}
            body = _reread_body(rev='chat:3', src='tbl@PR9')
            res = _reread_run(files, body, fail_status_write=True)
            assert res['rc'] == 1 and res['record'] == [], res  # Status は書けていない
            assert len(res['patches']) == 1 and 'rev=chat:4' in res['patches'][0]['body'], res['patches']
            rc, msg = res['again']()  # 目印だけ新しい → 次の start は --reread なしで着手できる
            assert rc == 0, msg
            # 目印を書く PATCH 自体が落ちたら Status は書かない
            rec: list = []
            gh_task.run_gh = make_write_gh({750: dict(title='task', status=gh_task.READY_STATUS, kind='task', body=body)},
                                           record=rec, rest_handler=lambda m, p, b: None)
            try:
                _with_root(_ds_tree(files), lambda: gh_task.cmd_start(750, None, reread=True))
                raise AssertionError('本文の PATCH が落ちたのに通った')
            except gh_task.GhError as exc:
                assert exc.code == 1, exc.code
            assert rec == [], rec

        t('start --reread: Status の書き込みが落ちても目印だけ新しく Status は変わらず、次の start がやり直せる', _reread_status_write_failure_leaves_retryable_state)

        def _reread_arg_parsing_and_coverage_text() -> None:
            seen: list = []
            saved = gh_task.cmd_start
            gh_task.cmd_start = lambda n, approved, reread=False: seen.append((n, approved, reread)) or 0
            try:
                assert gh_task.main(['start', '750', '--reread']) == 0
                assert gh_task.main(['start', '750', '--reread', '--approved', 'x']) == 0
                assert gh_task.main(['start', '750', '--approved', 'x', '--reread']) == 0
                assert gh_task.main(['start', '750']) == 0
            finally:
                gh_task.cmd_start = saved
            assert seen == [(750, None, True), (750, 'x', True), (750, 'x', True), (750, None, False)], seen
            _expect_exit(lambda: gh_task.main(['start', '750', '--bogus']), 2)
            _expect_exit(lambda: gh_task.main(['start', '750', '--approved']), 2)
            rows = [dict(number=41, status='進行中', kind='task')]
            rc, out, _ = _with_root_cov({}, rows, {41: _mark('TBL-01', 'none@PR1').replace('rev=1', 'rev=chat:3')})
            assert '読み直してから start <n> --reread' in out, out

        t('start --reread: 引数の受け付け（順不同・--approved と併用・不正は exit 2）と coverage の案内', _reread_arg_parsing_and_coverage_text)

        def _reread_hard_stop_is_judged_before_drift() -> None:
            # rev が古く、かつ失効の提案がある task は、--reread なしでも失効で断り、--reread の案内を出さない
            files = {'docs/4-domains/chat/README.md': _readme(5), 'docs/draft/e.md': _draft_file('失効')}
            body = '<!-- rmp-task: id=TBL-01 rev=chat:3 stream=Infra src=e@PR1 domain=chat reqs=TBL-R1 -->\n' + REREAD_TAIL
            res = _reread_run(files, body, reread=False)
            assert res['rc'] == 2 and '失効' in res['message'], res
            assert '--reread' not in res['message'], res['message']
            assert res['patches'] == [] and res['record'] == [], res
            res = _reread_run(files, body)
            assert res['rc'] == 2 and '失効' in res['message'] and '--reread' not in res['message'], res
            assert res['patches'] == [] and res['record'] == [], res

        t('start: rev が古くても失効が同居すれば --reread なしでも失効で断り、--reread の案内を出さない', _reread_hard_stop_is_judged_before_drift)

        def _reread_rejects_option_as_approved_value() -> None:
            seen: list = []
            saved = gh_task.cmd_start
            gh_task.cmd_start = lambda n, approved, reread=False: seen.append((n, approved, reread)) or 0
            try:
                _expect_exit(lambda: gh_task.main(['start', '12', '--approved', '--reread']), 2)
                _expect_exit(lambda: gh_task.main(['start', '12', '--approved', '--reread', '--reread']), 2)
            finally:
                gh_task.cmd_start = saved
            assert seen == [], seen

        t('start: --approved の値が -- で始まるときは使い方を出して exit 2（--reread を出どころに取らない）', _reread_rejects_option_as_approved_value)

        # -- ready の「旧い形」の印（#829・裁定 3） --
        def _ready_marks_old_form_rows() -> None:
            rows = [
                dict(number=500, status=gh_task.READY_STATUS, kind='feature'),
                *[dict(number=n, status=gh_task.READY_STATUS, kind='task', parent_number=500) for n in (501, 502, 503)],
                dict(number=504, status=gh_task.IN_PROGRESS_STATUS, kind='task', parent_number=500),
                dict(number=506, status=gh_task.PENDING_STATUS, kind='feature'),
                dict(number=505, status=gh_task.READY_STATUS, kind='task', parent_number=506),  # 親が着手可でないので出ない
            ]
            bodies = {
                501: '旧い本文\n',
                502: _mark('TBL-02', 'tbl@PR9'),
                503: _mark('TBL-03', 'tbl@PR9', READS),
                504: '旧い本文\n',
            }
            asked: list = []
            inner = make_ds_board_gh(rows, bodies, calls=[])

            def spy(args, input_text=None):
                joined = ' '.join(args)
                if re.search(r'\bi0:', joined) and re.search(r'\bbody\b', joined):
                    asked.append([int(x) for x in re.findall(r'issue\(number:\s*(\d+)\)', joined)])
                return inner(args, input_text)

            gh_task.run_gh = spy
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = gh_task.cmd_ready()
            out = buf.getvalue()
            lines = {int(m.group(1)): line for line in out.splitlines() if (m := re.match(r'\s+#(\d+)\s', line))}
            assert rc == 0 and set(lines) == {501, 502, 503}, out
            assert lines[501].endswith(' [旧い形]') and lines[502].endswith(' [旧い形]'), out
            assert '[旧い形]' not in lines[503], out
            # 本文を引くのは出す行だけ（進行中の 504 は引かない）。問い合わせに body を含める
            assert asked == [[501, 502, 503]], asked

        t('ready: 目印が無い・目印はあるが reads= が無い行の末尾に [旧い形] を付ける（本文を取るのは出す行だけ）', _ready_marks_old_form_rows)

        def _ready_fake_returns_body_only_when_queried() -> None:
            # 偽の gh が、問い合わせに body が無いのに body を返すと、本文を取り忘れた回帰を捕まえられない
            rows = [dict(number=500, status=gh_task.READY_STATUS, kind='feature'),
                    dict(number=501, status=gh_task.READY_STATUS, kind='task', parent_number=500)]
            seen: list = []
            inner = make_ds_board_gh(rows, {501: _mark('TBL-03', 'tbl@PR9', READS)}, calls=[])

            def spy(args, input_text=None):
                joined = ' '.join(args)
                rc, out, err = inner(args, input_text)
                if re.search(r'\bi0:', joined) and 'blockedBy' not in joined:
                    seen.append(('body' in joined, '"body"' in out))
                return rc, out, err

            gh_task.run_gh = spy
            with redirect_stdout(io.StringIO()):
                gh_task.cmd_ready()
            assert seen and all(asked == returned for asked, returned in seen), seen
            assert any(asked for asked, _ in seen), seen

        t('ready: 偽の gh は問い合わせに body があるときだけ body を返し、ready は body を問い合わせる', _ready_fake_returns_body_only_when_queried)

        # -- 進行中の task をもう一度 start したとき（#829・裁定 4） --
        def _start_in_progress_notes_other_conversation() -> None:
            hint = '別の会話が進行中の可能性。続きなら show 750 で読む束を出す'
            for status, expect_hint in ((gh_task.IN_PROGRESS_STATUS, True), (gh_task.REVIEW_STATUS, False),
                                        (gh_task.DEP_STATUS, False), ('', False)):
                record: list = []
                gh_task.run_gh = make_write_gh(
                    {750: dict(title='task', status=status, kind='task', body=_mark('TBL-01', 'tbl@PR9'))}, record=record)
                message = ''
                with redirect_stdout(io.StringIO()) as buf:
                    try:
                        gh_task.cmd_start(750, None)
                    except gh_task.GhError as exc:
                        assert exc.code == 2, exc.code
                        message = str(exc)
                assert '着手可でも' in message, (status, message)  # 今までの断りの文は残す
                assert (hint in message) == expect_hint, (status, message)
                assert record == [] and buf.getvalue() == '', (status, record, buf.getvalue())

        t('start: 進行中の task は exit 2 で断り、「別の会話が進行中の可能性。続きなら show <n> で読む束を出す」を添える', _start_in_progress_notes_other_conversation)

        # -- coverage（#816・DS-R2.3） --
        def _cov_draft(status: str, rows: str, *, history: str = '- 2026-10-01 PR #9 の merge で承認', heading: str = '### 11-3. 表',
                       pr: int = 9, header_row: str | None = None, approvals: str | None = None) -> str:
            return (
                '# 試験\n\nid_prefix: TBL\nkind: ハーネス・進め方\ndomain: —\nstatus: ' + status + '\n'
                'approvals: ' + (approvals if approvals is not None else f'要件=PR #{pr} 設計=PR #{pr} task=PR #{pr}')
                + f'\napproved_at: 2026-10-01（PR #{pr} の merge で承認）\n\n'
                '## 1. 問題\n\n## 11. task\n\n' + heading + '\n\n'
                + (header_row or '| id | kind | stream | 題名 | 親 | 止める依存 | 要件 | 完了条件 |\n|---|---|---|---|---|---|---|---|') + '\n'
                + rows + '\n\n## 12. 履歴\n\n' + history + '\n')

        ROWS_ABC = ('| TBL-01 | task | Infra | 土台 | feature #900 | — | TBL-R1 | ok |\n'
                    '| TBL-02 | task | Infra | 命名 [要判断: TBL-Q1] | feature #900 | — | TBL-R2 | — |\n'
                    '| TBL-03 | task | Infra | 仕上げ | feature #900 | TBL-01 | TBL-R1 | ok |')

        def _run_coverage(files: dict[str, str], rows: list[dict], bodies: dict[int, str]) -> tuple[int, str, list]:
            root = _ds_tree({f'docs/draft/{k}.md': v for k, v in files.items()})
            calls: list = []
            fake = make_ds_board_gh(rows, bodies, calls=calls)
            gh_task.run_gh = fake
            saved = os.environ.get('HIRAI_TASK_ROOT')
            os.environ['HIRAI_TASK_ROOT'] = root
            try:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = gh_task.cmd_coverage()
            finally:
                if saved is None:
                    os.environ.pop('HIRAI_TASK_ROOT', None)
                else:
                    os.environ['HIRAI_TASK_ROOT'] = saved
            assert gh_task.run_gh is fake and calls, '外へ出る呼び出しが偽の gh に向いていない'
            return rc, buf.getvalue(), calls

        def _coverage_reports_missing_stale_expired() -> None:
            files = {
                'cov-a': _cov_draft('承認', ROWS_ABC),
                'cov-old': _cov_draft('承認', '| TBL-01 | task | Infra | x | feature #900 | — | TBL-R1 | ok |', pr=5,
                                      history='- 2026-10-01 PR #5 の merge で承認\n- 2026-10-09 PR #9 の merge で承認（要件を足した）'),
                'cov-exp': _cov_draft('失効', ROWS_ABC),
                'cov-merged': _cov_draft('取り込み済み', ROWS_ABC),
                'cov-draft': _cov_draft('起案', ROWS_ABC),
            }
            rows = [dict(number=n, status='承認待ち', kind='task') for n in (11, 12, 13)] + [
                dict(number=14, status='完了', kind='task', state='CLOSED')]
            bodies = {
                11: _mark('TBL-01', 'cov-a@PR9'), 12: _mark('TBL-01', 'cov-old@PR5'),
                13: _mark('TBL-01', 'cov-exp@PR3'), 14: _mark('TBL-01', 'cov-exp@PR3'),
            }
            rc, out, calls = _run_coverage(files, rows, bodies)
            assert rc == 0, out
            assert 'cov-a: 起票漏れ 1 件' in out and 'TBL-03' in out, out
            assert '（起票しない行 TBL-02' in out and '[要判断' in out, f'飛ばした行の理由が無い: {out}'
            assert 'cov-old: 起票漏れ 0 件' in out, out
            assert '古い版を指す issue 1 件' in out and '#12' in out and 'PR #9' in out, out
            assert '失効した提案を指す issue 1 件' in out and '#13' in out and '#14' not in out, f'閉じた issue は失効側に出さない: {out}'
            for skipped in ('cov-exp:', 'cov-merged:', 'cov-draft:'):
                assert skipped not in out, f'{skipped} は起票漏れの対象外のはず: {out}'
            assert not any('mutation' in c for c in calls), calls

        t('coverage: 起票漏れ・古い版・失効を指す issue を出し、取り込み済み・失効・起案は漏れの対象にしない', _coverage_reports_missing_stale_expired)

        def _coverage_zero_missing_for_fully_filed_draft() -> None:
            rows_one = '| TBL-01 | task | Infra | 土台 | feature #900 | — | TBL-R1 | ok |'
            rc, out, _ = _run_coverage(
                {'cov-ok': _cov_draft('承認', rows_one)},
                [dict(number=21, status='完了', kind='task', state='CLOSED')], {21: _mark('TBL-01', 'cov-ok@PR9')})
            assert rc == 0 and 'cov-ok: 起票漏れ 0 件' in out, out

        t('coverage: 承認済みの提案 1 本の行がすべて起票済み（閉じた issue も数える）なら「起票漏れ 0 件」', _coverage_zero_missing_for_fully_filed_draft)

        def _coverage_reads_old_form_table() -> None:
            old = _cov_draft('承認', '| TBL-01 | task | Infra | x | wave #634 | — | TBL-R1 | ok |', heading='### 8-3. task の表').replace(
                '## 11. task', '## 8. タスク分解')
            others = {
                f'cov-oldform-{label}': old.replace('status: 承認', f'status: {status}')
                for label, status in (('draft', '起案'), ('merged', '取り込み済み'))
            }
            rc, out, _ = _run_coverage({'cov-oldform': old, **others}, [], {})
            assert rc == 0 and 'cov-oldform: 照合できない（旧い形の表' in out, out
            assert 'cov-oldform: 起票漏れ' not in out, f'目印で照合できない表の件数を出した: {out}'
            assert 'cov-oldform-draft:' not in out and 'cov-oldform-merged:' not in out, f'起案・取り込み済みを数えた: {out}'

        t('coverage: 旧い形の承認済みの提案の「### 8-3. task の表」は目印で照合できないと 1 行出し、件数は出さない（起案・取り込み済みは出さない）', _coverage_reads_old_form_table)

        def _coverage_skips_unapproved_task_stage() -> None:
            text = _cov_draft('承認', ROWS_ABC).replace('task=PR #9', '').replace('要件=PR #9 設計=PR #9 ', '要件=PR #9 設計=PR #9')
            rc, out, _ = _run_coverage({'cov-nostage': text}, [], {})
            assert rc == 0 and 'cov-nostage: 起票漏れ' not in out, f'task の段が未承認なのに起票漏れを数えた: {out}'
            assert 'cov-nostage: 照合できない（' in out and 'task の段' in out, f'黙って飛ばした: {out}'

        t('coverage: task の段が未承認の提案は起票漏れに数えず、照合できないと 1 行出す', _coverage_skips_unapproved_task_stage)

        # -- impact（#817・DS-R-§8-2） --
        IMPACT_DRAFT = (
            '# 試験\n\nid_prefix: TBL\nstatus: 承認\n\n## 11. task\n\n### 11-1. 位置と前後\n\n'
            '- 入る wave: #634 ハーネスの改善\n- 止める依存（既存）: #611、#999\n- この設計を待つ既存 task: #675 #634\n'
            '- 変える既存 task: #700（閉じた）\n- 重なりを見る言葉: new-draft、from-table\n\n### 11-2. impact の出力\n\nここの #5 は読まない\n')
        IMPACT_ROWS = [
            dict(number=634, status='', kind='wave', title='ハーネスの改善', order=None),
            dict(number=675, status='着手可', kind='feature', title='ハーネス', parent_number=634, order=3),
            dict(number=611, status='承認待ち', kind='task', title='tasks.md へ', parent_number=675),
            dict(number=612, status='保留', kind='task', title='hirai-task', parent_number=675),
            dict(number=700, status='完了', kind='task', title='閉じた', state='CLOSED'),
        ]

        def _run_impact(text: str, rows: list[dict], extras: dict) -> tuple[int, str, list]:
            path = _draft_path('impact-draft.md', text)
            calls: list = []
            fake = make_ds_board_gh(rows, {}, extras, calls=calls)
            gh_task.run_gh = fake
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = gh_task.cmd_impact([path])
            assert gh_task.run_gh is fake and calls, '外へ出る呼び出しが偽の gh に向いていない'
            return rc, buf.getvalue(), calls

        def _impact_annotates_numbers() -> None:
            rc, out, _ = _run_impact(IMPACT_DRAFT, IMPACT_ROWS, {611: [610]})
            assert rc == 0 and '位置と前後の #番号 5 件' in out, out
            assert '#634 ハーネスの改善 — wave' in out, out
            assert '#675 ハーネス — feature・着手可・着手順 3・親 #634・子 2（承認待ち 1・保留 1）' in out, out
            assert '#611 tasks.md へ — task・承認待ち・親 #675・blocked by #610' in out, out
            assert '#999 Projects に載っていない' in out, out
            assert '#700 閉じた — task・完了・閉じた' in out, out
            assert '警告: 閉じた・保留の番号 #700' in out, out
            assert '#5 ' not in out, f'節（11-2）の外の番号まで拾った: {out}'

        t('impact: 位置と前後の #番号に 種別・Status・着手順・親・子の内訳・blocked by・閉じた を注記し、盤にない番号と警告も出す', _impact_annotates_numbers)

        def _impact_reads_old_form_and_clean_warning() -> None:
            text = '# 旧\n\nstatus: 承認\n\n## 8. タスク分解\n\n### 8-1. 位置と前後（既存の issue）\n- 入る wave: #675\n\n### 8-2. impact の出力\n'
            rc, out, _ = _run_impact(text, IMPACT_ROWS, {})
            assert rc == 0 and '#675 ハーネス' in out and '警告: なし（閉じた・保留の番号 0 件）' in out, out

        t('impact: 旧い形の「### 8-1. 位置と前後」も読み、閉じた・保留が無ければ「警告: なし」', _impact_reads_old_form_and_clean_warning)

        def _impact_refuses_draft_without_section() -> None:
            path = _draft_path('impact-none.md', '# x\n\n## 1. 問題\n')
            gh_task.run_gh = make_ds_board_gh([], {}, calls=[])
            _expect_exit(lambda: gh_task.cmd_impact([path]), 2)

        t('impact: 「位置と前後」の節が無い draft は exit 2', _impact_refuses_draft_without_section)

        # -- design-merge（#818・DS-R3.2・DS-R3.3） --
        README_BEFORE = (
            '# チャット（chat）\n\nid_prefix: CHAT\ndomain: chat\nstatus: 現在形\nrev: 3\n\n## 1. 目的\n\nx\n\n'
            '## 7. 要件と受入\n\n'
            '### 要件 CHAT-R1: 部屋を 1 つ用意する\n- CHAT-R1.1 Given a When b Then c\n\n'
            '### 要件 CHAT-R2: 一覧を返す\n- CHAT-R2.1 Given a When b Then c\n- CHAT-R2.2 Given d When e Then f\n\n'
            '### 要件 CHAT-R3: 参加者を返す\n- CHAT-R3.1 Given a When b Then c\n\n'
            '## 8. 上の層との差分\n\nなし\n')

        def _merge_draft(delta: str, *, status: str = '承認', domain: str = 'chat') -> str:
            return (
                '# 添付\n\nid_prefix: ATT\nkind: 製品の機能\ndomain: ' + domain + '\nstatus: ' + status + '\n'
                'approvals: 要件=PR #9 設計=PR #9 task=PR #9\napproved_at: 2026-10-01（PR #9 の merge で承認）\nmerged_into:\n\n'
                '## 1. 問題\n\n## 2. 目指す状態\n\n' + delta + '\n## 3. 変える上の層の現在形\n\nx\n')

        DELTA_OK = (
            '### 追加された要件\n\n### 要件 ATT-R1: 入居者が添付を送るとき、システムは画像と PDF だけを受け付ける\n'
            '- ATT-R1.1 Given JPEG When 送る Then 保存される\n- ATT-R1.2 Given exe When 送る Then 400\n\n'
            '### 変更された要件\n\n### 要件 CHAT-R2: 一覧を新しい順に返す\n'
            '- CHAT-R2.1 Given x When y Then z\n\n'
            '### 削除された要件\n\n- CHAT-R3（ATT-R1 に統合した）\n')

        def _merge(draft_text: str, readme_text: str = README_BEFORE) -> tuple[str, str, str, str]:
            root = _ds_tree({'docs/draft/att.md': draft_text, 'docs/4-domains/chat/README.md': readme_text})
            draft = os.path.join(root, 'docs/draft/att.md')
            readme = os.path.join(root, 'docs/4-domains/chat/README.md')
            calls: list = []
            gh_task.run_gh = make_ds_board_gh([], {}, calls=calls)  # design-merge が gh を呼んだら落とす
            buf = io.StringIO()
            try:
                with redirect_stdout(buf):
                    gh_task.cmd_design_merge([draft])
            finally:
                assert calls == [], f'design-merge が GitHub を引いた: {calls}'
            return buf.getvalue(), _read(draft), _read(readme), root

        def _design_merge_applies_delta() -> None:
            out, draft, readme, _ = _merge(_merge_draft(DELTA_OK))
            assert 'status: 取り込み済み' in draft and 'merged_into: docs/4-domains/chat/README.md' in draft, draft
            assert 'status: 承認' not in draft, draft
            assert '### 要件 ATT-R1: 入居者が添付を送るとき' in readme and '- ATT-R1.2 Given exe' in readme, readme
            assert readme.index('ATT-R1:') < readme.index('## 8. 上の層との差分'), '追加が「## 8.」の前に入っていない'
            assert '### 要件 CHAT-R2: 一覧を新しい順に返す' in readme and '- CHAT-R2.1 Given x When y Then z' in readme, readme
            assert '- CHAT-R2.2 Given d When e Then f' in readme, '書かなかった受入 CHAT-R2.2 が消えた'
            assert 'CHAT-R2.1 Given a' not in readme, '書いた受入 CHAT-R2.1 の古い行が残っている'
            assert 'CHAT-R3' not in readme, '削除した要件が残っている'
            assert 'CHAT-R1.1' in readme, '触れない要件が消えた'
            assert 'rev: 4' in readme and 'rev: 3' not in readme, readme
            assert '追加 1 件・変更 1 件・削除 1 件・rev: 3 → 4' in out and '+### 要件 ATT-R1' in out, out

        t('design-merge: 追加・変更・削除を現在形に当て、rev を上げ、提案の先頭を取り込み済みにして差分を出す', _design_merge_applies_delta)

        def _design_merge_keeps_old_acceptance_when_changed_has_none() -> None:
            delta = '### 変更された要件\n\n### 要件 CHAT-R1: 部屋を 1 つだけ用意する\n'
            _, _, readme, _ = _merge(_merge_draft(delta))
            assert '### 要件 CHAT-R1: 部屋を 1 つだけ用意する' in readme and '- CHAT-R1.1 Given a When b Then c' in readme, readme

        t('design-merge: 変更に受入が無ければ現在形の受入を残して文だけ替える', _design_merge_keeps_old_acceptance_when_changed_has_none)

        def _assert_merge_refused(draft_text: str, code: int, needle: str, readme_text: str = README_BEFORE) -> None:
            root = _ds_tree({'docs/draft/att.md': draft_text, 'docs/4-domains/chat/README.md': readme_text})
            draft = os.path.join(root, 'docs/draft/att.md')
            readme = os.path.join(root, 'docs/4-domains/chat/README.md')
            before = (_read(draft), _read(readme))
            try:
                gh_task.cmd_design_merge([draft])
            except gh_task.GhError as exc:
                assert exc.code == code, f'exit {exc.code}（期待 {code}）: {exc}'
                assert needle in str(exc), f'理由に「{needle}」が無い: {exc}'
            else:
                raise AssertionError('断るべきなのに通った')
            assert (_read(draft), _read(readme)) == before, '断ったのに file を書いた'

        def _design_merge_refuses_unappliable_without_writing() -> None:
            missing_change = '### 変更された要件\n\n### 要件 CHAT-R9: b\n- CHAT-R9.1 Given a When b Then c\n'
            _assert_merge_refused(_merge_draft(missing_change), 1, 'CHAT-R9')
            missing_delete = '### 削除された要件\n\n- CHAT-R8（理由）\n'
            _assert_merge_refused(_merge_draft(missing_delete), 1, 'CHAT-R8')
            dup_add = '### 追加された要件\n\n### 要件 CHAT-R1: 重なる\n- CHAT-R1.1 Given a When b Then c\n'
            _assert_merge_refused(_merge_draft(dup_add), 1, '既にある')
            # 追加は通るが削除が当たらない → 追加も書かない（全部か何もか）
            _assert_merge_refused(_merge_draft(DELTA_OK.replace('CHAT-R3（', 'CHAT-R7（')), 1, 'CHAT-R7')

        t('design-merge: 変更先の要件 ID が現在形に無い・追加が重なる差分は、何も書かず exit 1（一部だけ当てない）', _design_merge_refuses_unappliable_without_writing)

        def _design_merge_refuses_non_block_delta_and_empty() -> None:
            table = '### 追加された要件\n\n| ID | 文 |\n|---|---|\n| ATT-R1 | x |\n'
            _assert_merge_refused(_merge_draft(table), 1, '要件ブロック')
            empty = '### 追加された要件\n\nなし\n\n### 変更された要件\n\nなし\n\n### 削除された要件\n\nなし\n'
            _assert_merge_refused(_merge_draft(empty), 1, '差分が空')

        t('design-merge: 表の形の差分と空の差分は何も書かず exit 1', _design_merge_refuses_non_block_delta_and_empty)

        def _design_merge_refuses_wrong_state() -> None:
            _assert_merge_refused(_merge_draft(DELTA_OK, status='起案'), 2, '承認済み')
            _assert_merge_refused(_merge_draft(DELTA_OK, status='取り込み済み'), 2, '既に')
            _assert_merge_refused(_merge_draft(DELTA_OK, domain='chat, agent'), 1, '領域を 1 つに')
            _assert_merge_refused(_merge_draft(DELTA_OK).replace('要件=PR #9 ', '').replace('approvals: ', 'approvals: 設計=PR #9 '), 2, '要件の段')

        t('design-merge: 起案・取り込み済み・領域が 1 つでない・要件の段が未承認は書かずに断る', _design_merge_refuses_wrong_state)

        def _design_merge_is_not_repeatable() -> None:
            root = _ds_tree({'docs/draft/att.md': _merge_draft(DELTA_OK), 'docs/4-domains/chat/README.md': README_BEFORE})
            draft = os.path.join(root, 'docs/draft/att.md')
            with redirect_stdout(io.StringIO()):
                gh_task.cmd_design_merge([draft])
            _expect_exit(lambda: gh_task.cmd_design_merge([draft]), 2)
            assert _read(os.path.join(root, 'docs/4-domains/chat/README.md')).count('### 要件 ATT-R1') == 1

        t('design-merge: 2 回目は取り込み済みで断り、要件を二重に足さない', _design_merge_is_not_repeatable)

        def _coverage_drops_merged_draft_after_design_merge() -> None:
            root = _ds_tree({'docs/draft/att.md': _cov_draft('承認', ROWS_ABC) + '', 'docs/4-domains/chat/README.md': README_BEFORE})
            text = _read(os.path.join(root, 'docs/draft/att.md')).replace('domain: —', 'domain: chat').replace(
                '## 1. 問題\n', '## 1. 問題\n\n## 2. 目指す状態\n\n### 追加された要件\n\n### 要件 TBL-R1: x\n- TBL-R1.1 Given a When b Then c\n\n', 1)
            with open(os.path.join(root, 'docs/draft/att.md'), 'w', encoding='utf-8') as f:
                f.write(text)
            with redirect_stdout(io.StringIO()):
                gh_task.cmd_design_merge([os.path.join(root, 'docs/draft/att.md')])
            gh_task.run_gh = make_ds_board_gh([], {}, calls=[])
            saved = os.environ.get('HIRAI_TASK_ROOT')
            os.environ['HIRAI_TASK_ROOT'] = root
            try:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    gh_task.cmd_coverage()
            finally:
                if saved is None:
                    os.environ.pop('HIRAI_TASK_ROOT', None)
                else:
                    os.environ['HIRAI_TASK_ROOT'] = saved
            assert 'att: 起票漏れ' not in buf.getvalue(), buf.getvalue()

        t('design-merge のあと、その提案は coverage の対象から外れる（DS-R3.3）', _coverage_drops_merged_draft_after_design_merge)


        # -- レビューの直し（#816〜#818 の指摘） --
        def _coverage_unmatched_marks_are_not_zero() -> None:
            # 指摘 4: 表の issue に目印が無い（盤にあるが bodies に目印が無い）旧い形の表は、漏れ 1 と数えない
            old = _cov_draft('承認', '| TBL-01 | task | Infra | x | wave #634 | — | TBL-R1 | ok |', heading='### 8-3. task の表').replace(
                '## 11. task', '## 8. タスク分解')
            rc, out, _ = _run_coverage({'cov-nomark': old}, [dict(number=31, status='承認待ち', kind='task')], {31: '目印なし\n'})
            assert 'cov-nomark: 起票漏れ' not in out and 'cov-nomark: 照合できない' in out, out
            # 指摘 4: 表で「既存 #723 を使う」と書いた行は漏れに出さない
            row = '| TBL-01 | feature | Infra | メッセージ基盤（既存 #723 を使う） | wave #634 | — | TBL-R1 | ok |'
            rc, out, _ = _run_coverage({'cov-use': _cov_draft('承認', row)}, [], {})
            assert 'cov-use: 起票漏れ 0 件' in out, out

        t('coverage: 目印の無い旧い形の表は漏れと数えず、「既存 #n を使う」行は起票漏れに出さない', _coverage_unmatched_marks_are_not_zero)

        def _coverage_reports_unreadable_drafts() -> None:
            # 指摘 5・7: 列の違う表と、PR 番号の無い承認は黙らず 1 行出す（偽の 0 を出さない）
            narrow = _cov_draft('承認', '| TBL-01 | 土台 | feature #900 | ok |\n| TBL-02 | 命名 | feature #900 | ok |',
                                header_row='| ID | 題 | 親 | 完了条件 |\n|---|---|---|---|')
            hash_only = _cov_draft('承認', ROWS_ABC, approvals='要件=#1 設計=#1 task=#1532')
            here = _cov_draft('承認', ROWS_ABC, approvals='要件=この PR 設計=この PR task=この PR')
            rc, out, _ = _run_coverage({'cov-narrow': narrow, 'cov-hash': hash_only, 'cov-here': here}, [], {})
            assert rc == 0, out
            assert 'cov-narrow: 照合できない（表の列が new --from-table の形でない' in out, out
            assert 'cov-narrow: 起票漏れ' not in out and '（起票しない行' not in out, f'偽の 0 か行ごとの飛ばしが出た: {out}'
            assert 'cov-hash: 照合できない（' in out and 'task の段' in out, out
            assert 'cov-here: 照合できない（' in out and 'task の段' in out, out

        t('coverage: 列の違う表・task の段の承認が読めない提案は、起票漏れの件数を出さず「照合できない」を 1 行出す', _coverage_reports_unreadable_drafts)

        def _coverage_stale_reads_history_and_ignores_noise() -> None:
            # 指摘 9: 新しい承認が履歴だけにある → 古い版として拾う
            old = _cov_draft('承認', ROWS_ABC, pr=5, history='- 2026-10-09 PR #9 の merge で承認（要件を足した）')
            assert gh_task.latest_approval_pr(old.splitlines()) == 9, '履歴の承認を読んでいない'
            # 指摘 11: 承認でない PR の言及は数えない
            noisy = _cov_draft('承認', ROWS_ABC, pr=5, history=(
                '- 2026-10-01 PR #5 の merge で承認\n'
                '- PR #615 を merge した（移行）。同じ日にチャットの承認で #532 へ付け替えた\n'
                '- 承認待ちに戻した PR #7\n- 承認不要の誤記直し PR #8\n'
                '- 2026-10-12 承認（チャット。PR #11 の merge）'))
            assert gh_task.latest_approval_pr(noisy.splitlines()) == 11, gh_task.latest_approval_pr(noisy.splitlines())
            plain = _cov_draft('承認', ROWS_ABC, pr=5, history='- PR #615 を merge した。承認で #532 へ付け替えた\n- 承認待ちに戻した PR #7')
            assert gh_task.latest_approval_pr(plain.splitlines()) == 5

        t('coverage: 古い版の判定は履歴の承認の行だけを読み、承認でない PR 番号は数えない', _coverage_stale_reads_history_and_ignores_noise)

        def _coverage_merged_unknown_boundaries() -> None:
            files = {'cov-merged': _cov_draft('取り込み済み', ROWS_ABC)}
            rows = [dict(number=n, status='承認待ち', kind='task') for n in (41, 42)]
            bodies = {41: _mark('TBL-01', 'cov-merged@PR5'), 42: _mark('TBL-01', 'cov-gone@PR5')}
            rc, out, _ = _run_coverage(files, rows, bodies)
            assert '古い版を指す issue 0 件' in out and '#41' not in out, f'取り込み済みの提案を古い版に数えた: {out}'
            assert '#42 の src=cov-gone@PR5 は docs/draft/ に file が無い' in out, out

        t('coverage: 取り込み済みの提案を指す issue は古い版に数えず、file の無い src は 1 行出す', _coverage_merged_unknown_boundaries)

        def _start_approved_prints_bundle() -> None:
            gh_task.run_gh = make_write_gh(
                {727: dict(title=f'{gh_task.OPERATION_MARK} task', status=gh_task.READY_STATUS, kind='task',
                           body=_mark('TBL-01', 'tbl@PR9', READS), parent_number=728),
                 728: dict(title='feature', status=gh_task.READY_STATUS, kind='feature')},
                record=[], rest_handler=lambda m, p, b: {})
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = gh_task.cmd_start(727, '出どころ')
            assert rc == 0 and '1. docs/4-domains/chat/README.md' in buf.getvalue(), buf.getvalue()

        t('start --approved: 着手したあとに読む束を出す', _start_approved_prints_bundle)

        def _impact_section_end_is_heading_only() -> None:
            text = ('# x\n\nstatus: 承認\n\n## 11. task\n\n### 11-1. 位置と前後\n\n- 入る wave: #634\n'
                    '#611 ← DS-13\n```bash\n# 例 #888\n#701\n```\n- milestone は無い #675\n\n### 11-2. 出力\n\nここの #5 は読まない\n')
            numbers = gh_task.impact_numbers(text.splitlines())
            assert numbers == [634, 611, 675], f'節が途中で切れたか囲みの中を拾った: {numbers}'

        t('impact: 節の終わりは見出し（# の後ろに空白）だけで、#番号 で始まる行では切れず、コードの囲みの中は読まない', _impact_section_end_is_heading_only)

        # 実物（rmp-app の docs/4-domains/chat/README.md）の形: 受入は行頭の「- ID.n …」・末尾に「／ 確かめ: …」・R1.1 と R1.10 が並ぶ
        README_REAL = (
            '# チャット（chat）\n\nid_prefix: CHAT\ndomain: chat\nstatus: 現在形\nrev: 3\n\n## 7. 要件と受入\n\n'
            '### 要件 CHAT-R1: 入居者が会話を開いたとき、システムは部屋を 1 つだけ用意する（FR-MATCH-009）\n\n'
            '- CHAT-R1.1 Given 部屋が無い When POST Then 201 ／ 確かめ: [`a.test.ts`](../../../a.test.ts)\n'
            '- CHAT-R1.2 Given 部屋がある When POST Then 200 ／ 確かめ: なし\n'
            '- CHAT-R1.10 Given 相談した When accept Then 続けて POST ／ 確かめ: 通し: [`b.test.tsx`](../../../b.test.tsx)\n'
            '  （補足の続きの行）\n\n'
            '### 要件 CHAT-R2: 一覧を返す\n\n- CHAT-R2.1 Given a When b Then c\n\n'
            '## 8. 上の層との差分\n\nなし\n')

        def _design_merge_replaces_only_written_acceptance_ids() -> None:
            # 4-B: 書いた ID の行だけ差し替え・無い ID は足し、書かない ID（R1.2・R1.10 と続きの行）は残す。R1.1 は R1.10 を巻き込まない
            delta = ('### 変更された要件\n\n### 要件 CHAT-R1: 入居者が会話を開いたとき、システムは部屋を作る\n\n'
                     '- CHAT-R1.1 Given 部屋が無い When POST Then 201 と部屋を返す\n'
                     '- CHAT-R1.11 Given 見送り When POST Then 404\n')
            _, _, readme, _ = _merge(_merge_draft(delta), README_REAL)
            assert '### 要件 CHAT-R1: 入居者が会話を開いたとき、システムは部屋を作る\n' in readme, readme
            assert '- CHAT-R1.1 Given 部屋が無い When POST Then 201 と部屋を返す\n' in readme and '確かめ: [`a.test.ts`]' not in readme, readme
            assert '- CHAT-R1.2 Given 部屋がある When POST Then 200 ／ 確かめ: なし\n' in readme, '書かない R1.2 が消えた'
            assert '- CHAT-R1.10 Given 相談した When accept Then 続けて POST' in readme and '  （補足の続きの行）\n' in readme, 'R1.10 が R1.1 に巻き込まれた'
            assert '- CHAT-R1.11 Given 見送り When POST Then 404\n' in readme, '現在形に無い ID が足されていない'
            assert readme.index('CHAT-R1.10') < readme.index('CHAT-R1.11') < readme.index('### 要件 CHAT-R2'), '足した受入が要件ブロックの末尾に入っていない'
            assert '- CHAT-R2.1 Given a When b Then c' in readme

        t('design-merge: 変更は書いた受入の ID の行だけ差し替え、現在形に無い ID は足し、書かない ID は残す（R1.1 が R1.10 を巻き込まない）', _design_merge_replaces_only_written_acceptance_ids)

        def _design_merge_refuses_arrow_heading() -> None:
            for heading in ('一覧を返す → 新しい文', '（一覧を返す → 新しい文）'):
                delta = '### 変更された要件\n\n### 要件 CHAT-R2: ' + heading + '\n- CHAT-R2.1 Given x When y Then z\n'
                _assert_merge_refused(_merge_draft(delta), 1, '変更後の文だけ')

        t('design-merge: 変更の見出しに → があれば、何も書かず exit 1（見出しは変更後の文だけ）', _design_merge_refuses_arrow_heading)

        def _design_merge_refuses_foreign_acceptance_id() -> None:
            delta = '### 変更された要件\n\n### 要件 CHAT-R2: y\n- CHAT-R3.1 Given x When y Then z\n'
            _assert_merge_refused(_merge_draft(delta), 1, 'CHAT-R3.1')

        t('design-merge: 変更の要件に属さない受入の ID（CHAT-R2 の下の CHAT-R3.1）は何も書かず exit 1', _design_merge_refuses_foreign_acceptance_id)

        def _design_merge_deletes_acceptance_unit_and_requirement_unit() -> None:
            # 4-B: 「- ID.n」はその受入の行だけを消し（続きの行も）、「- ID」は要件ブロックを消す
            delta = '### 削除された要件\n\n- CHAT-R1.10（統合した）\n- CHAT-R2（廃止）\n'
            out, _, readme, _ = _merge(_merge_draft(delta), README_REAL)
            assert 'CHAT-R1.10' not in readme and '補足の続きの行' not in readme, readme
            assert 'CHAT-R1.1 ' in readme and 'CHAT-R1.2 ' in readme, '消す受入以外が消えた'
            assert '### 要件 CHAT-R1:' in readme, '受入の単位の削除で要件ブロックまで消えた'
            assert 'CHAT-R2' not in readme, '要件の単位の削除でブロックが残った'
            parsed = gh_task.parse_delta(_merge_draft(delta).splitlines())
            assert parsed['deleted'][0][0] == 'CHAT-R2' and parsed['unreadable'] == [], parsed
            assert '削除 1 件' in out and '受入の削除 1 件' in out, out

        t('design-merge: 削除の「- ID.n」はその受入の行だけを、「- ID」は要件ブロックを消す', _design_merge_deletes_acceptance_unit_and_requirement_unit)

        def _design_merge_refuses_deleting_missing_acceptance() -> None:
            _assert_merge_refused(_merge_draft('### 削除された要件\n\n- CHAT-R2.9（無い）\n'), 1, 'CHAT-R2.9')
            _assert_merge_refused(_merge_draft('### 削除された要件\n\n- CHAT-R8.1（要件ごと無い）\n'), 1, 'CHAT-R8.1')
            _assert_merge_refused(_merge_draft('### 削除された要件\n\n- CHAT-R2（x）\n- CHAT-R2.1（y）\n'), 1, '重複')
            both = ('### 変更された要件\n\n### 要件 CHAT-R2: y\n- CHAT-R2.1 Given a When b Then c\n\n'
                    '### 削除された要件\n\n- CHAT-R2.1（z）\n')
            _assert_merge_refused(_merge_draft(both), 1, '重複')

        t('design-merge: 現在形に無い受入・要件の削除、同じ ID を書き直しと削除の両方に書く差分は、何も書かず exit 1', _design_merge_refuses_deleting_missing_acceptance)

        def _design_merge_refuses_escaping_domain() -> None:
            # 指摘 2: domain を 1 つの段として検査し、docs/4-domains の外を書かない
            root = _ds_tree({'victim/README.md': README_BEFORE})
            victim = os.path.join(root, 'victim', 'README.md')
            before = _read(victim)
            for domain in ('../x', '/tmp/x', '..', 'chat/../billing', '../../../victim'):
                tree = _ds_tree({'docs/draft/att.md': _merge_draft(DELTA_OK, domain=domain),
                                 'docs/4-domains/chat/README.md': README_BEFORE})
                draft = os.path.join(tree, 'docs/draft/att.md')
                _expect_exit(lambda: gh_task.cmd_design_merge([draft]), 1)
                assert 'status: 承認' in _read(draft), f'{domain}: draft を書いた'
            assert _read(victim) == before
            # README の domain: が draft と違うときも断る
            other = README_BEFORE.replace('domain: chat', 'domain: billing')
            _assert_merge_refused(_merge_draft(DELTA_OK), 1, 'domain', readme_text=other)

        t('design-merge: domain が 1 つの段（英小文字・数字・ハイフン）でない・README の domain: と違うときは何も書かず exit 1', _design_merge_refuses_escaping_domain)

        def _design_merge_refuses_dash_domain() -> None:
            _assert_merge_refused(_merge_draft(DELTA_OK, domain='—'), 1, '手で当てる')
            _assert_merge_refused(_merge_draft(DELTA_OK, domain='chat, agent'), 1, '手で当てる')

        t('design-merge: domain が「—」なら領域を 1 つに決められないと exit 1', _design_merge_refuses_dash_domain)

        def _design_merge_accepts_nashi_with_punctuation() -> None:
            # 指摘 6
            delta = ('### 追加された要件\n\n### 要件 ATT-R1: 入居者が送る\n- ATT-R1.1 Given a When b Then c\n\n'
                     '### 変更された要件\n\nなし（Figma には出ない）。\n\n### 削除された要件\n\nなし。\n')
            out, _, readme, _ = _merge(_merge_draft(delta))
            assert '追加 1 件・変更 0 件・削除 0 件' in out and 'ATT-R1:' in readme, out

        t('design-merge: 「なし。」「なし（理由）。」は空の区分として通す', _design_merge_accepts_nashi_with_punctuation)

        def _design_merge_refuses_stray_lines_and_duplicates() -> None:
            # 指摘 13
            stray = ('### 変更された要件\n\n### 要件 CHAT-R2: y\n- CHAT-R2.1 z\n\n#### 補足\n本文\n')
            _assert_merge_refused(_merge_draft(stray), 1, '要件ブロック')
            dup = ('### 追加された要件\n\n### 要件 ATT-R1: a\n- ATT-R1.1 Given a When b Then c\n\n'
                   '### 要件 ATT-R1: b\n- ATT-R1.1 Given a When b Then c\n')
            _assert_merge_refused(_merge_draft(dup), 1, '重複')
            cross = (dup.split('### 要件 ATT-R1: b')[0] + '\n### 削除された要件\n\n- ATT-R1（x）\n')
            _assert_merge_refused(_merge_draft(cross), 1, '重複')

        t('design-merge: ブロックの後ろの関係ない行と、同じ ID の重複（区分をまたぐものも）は何も書かず exit 1', _design_merge_refuses_stray_lines_and_duplicates)

        README_DUP = (
            '# 提案（proposal）\n\nid_prefix: PROP\ndomain: chat\nstatus: 現在形\nrev: 3\n\n## 7. 要件と受入\n\n'
            '### 要件 CHAT-R9: 開封する\n- CHAT-R9.5 Given a When b Then 開封の口\n- CHAT-R9.5 Given c When d Then 未読を作らない\n\n'
            '### 要件 CHAT-R10: 別\n- CHAT-R10.1 Given a When b Then c\n\n## 8. 上の層との差分\n\nなし\n')

        def _design_merge_refuses_duplicate_current_acceptance_id() -> None:
            # 指摘 1: 現在形に同じ受入 ID が 2 行ある要件への変更・削除は、黙って片方だけ当てず exit 1
            change = '### 変更された要件\n\n### 要件 CHAT-R9: 新しい文\n- CHAT-R9.5 Given NEW When x Then y\n'
            _assert_merge_refused(_merge_draft(change), 1, '2 行ある', README_DUP)
            _assert_merge_refused(_merge_draft('### 削除された要件\n\n- CHAT-R9.5（x）\n'), 1, '2 行ある', README_DUP)

        t('design-merge: 現在形に同じ受入 ID が 2 行ある要件の変更・受入の削除は、何も書かず exit 1', _design_merge_refuses_duplicate_current_acceptance_id)

        def _design_merge_refuses_empty_or_old_text_heading() -> None:
            # 指摘 3・8: 見出しの文が空（受入だけを変えたつもり）は要件の文を消すので exit 1。指摘 4: 「変更前は」入りの見出しも exit 1
            for heading in ('', '   '):
                delta = '### 変更された要件\n\n### 要件 CHAT-R1:' + heading + '\n- CHAT-R1.1 Given d When e Then g\n'
                _assert_merge_refused(_merge_draft(delta), 1, '文が空')
            old = '### 変更された要件\n\n### 要件 CHAT-R2: 新しい文（変更前は「古い文」・`:49`）\n- CHAT-R2.1 Given x When y Then z\n'
            _assert_merge_refused(_merge_draft(old), 1, '変更前')

        t('design-merge: 変更の見出しの文が空・「変更前」入りなら、何も書かず exit 1', _design_merge_refuses_empty_or_old_text_heading)

        def _design_merge_refuses_multi_id_deleted_line() -> None:
            # 指摘 5: 1 行に ID が 2 つ以上の削除は一部だけ当てず exit 1。理由の括弧の中の ID は数えない
            for line in ('- CHAT-R2.1・CHAT-R2.2（理由）', '- CHAT-R2, CHAT-R3', '- CHAT-R2.1 CHAT-R3.1'):
                _assert_merge_refused(_merge_draft('### 削除された要件\n\n' + line + '\n'), 1, '要件ブロック')

        t('design-merge: 削除の 1 行に ID が 2 つ以上あれば、何も書かず exit 1（括弧の理由の ID は数えない）', _design_merge_refuses_multi_id_deleted_line)

        def _design_merge_unmatched_h3_ends_block() -> None:
            # 指摘 6: 見出しの正規表現に当たらない `### ` は前の要件のブロックの終わり。消した要件と一緒に消えない
            readme = README_BEFORE.replace(
                '### 要件 CHAT-R3: 参加者を返す',
                '### 要件 CHAT-R2・CHAT-R3: 案内（→ 別の領域）\n案内の文\n\n### 要件 CHAT-R3: 参加者を返す')
            _, _, after, _ = _merge(_merge_draft('### 削除された要件\n\n- CHAT-R2（x）\n'), readme)
            assert '### 要件 CHAT-R2・CHAT-R3: 案内' in after and '案内の文' in after, after
            assert '一覧を返す' not in after and 'CHAT-R3.1' in after, after

        t('design-merge: 見出しの形に当たらない ### の直前の要件を消しても、その見出しと文は消えない', _design_merge_unmatched_h3_ends_block)

        def _design_merge_refuses_indented_acceptance_and_leading_text() -> None:
            # 2 巡目の指摘 1: 字下げした受入の行は直前の受入の続きに入って同じ ID が 2 行になる／最初の受入より前の行は黙って捨てられる
            indented = '### 変更された要件\n\n### 要件 CHAT-R2: 一覧を返す\n- CHAT-R2.1 Given x When y Then z\n  - CHAT-R2.1 Given p When q Then r\n'
            _assert_merge_refused(_merge_draft(indented), 1, '要件ブロック')
            leading = '### 変更された要件\n\n### 要件 CHAT-R2: 一覧を返す\n  補足の文\n- CHAT-R2.1 Given x When y Then z\n'
            _assert_merge_refused(_merge_draft(leading), 1, '最初の受入より前')

        t('design-merge: 字下げした受入の行と、最初の受入より前の本文の行は、何も書かず exit 1', _design_merge_refuses_indented_acceptance_and_leading_text)

        def _design_merge_refuses_id_in_unmatched_h3() -> None:
            # 2 巡目の指摘 2: 形に当たらない `### 要件 A・B:` 見出しの ID を追加すると重複する
            readme = README_BEFORE.replace(
                '### 要件 CHAT-R3: 参加者を返す',
                '### 要件 CHAT-R8・CHAT-R9: 案内\n\n→ 案内の文\n\n### 要件 CHAT-R3: 参加者を返す')
            add = '### 追加された要件\n\n### 要件 CHAT-R9: 新しい文\n- CHAT-R9.1 Given a When b Then c\n'
            _assert_merge_refused(_merge_draft(add), 1, '既にある', readme)

        t('design-merge: 形に当たらない ### 見出しにある ID を追加すれば、何も書かず exit 1', _design_merge_refuses_id_in_unmatched_h3)

        def _design_merge_checks_added_body() -> None:
            # 2 巡目の指摘 3: 追加にも、別の要件の受入 ID・同じ受入 ID の 2 行・空の見出しの文の検査を当てる
            head = '### 追加された要件\n\n'
            _assert_merge_refused(_merge_draft(head + '### 要件 ATT-R1: a\n- ATT-R2.1 Given a When b Then c\n'), 1, '別の要件の受入')
            _assert_merge_refused(_merge_draft(head + '### 要件 ATT-R1: a\n- ATT-R1.1 Given a When b Then c\n- ATT-R1.1 Given d When e Then f\n'), 1, '重複')
            _assert_merge_refused(_merge_draft(head + '### 要件 ATT-R1:\n- ATT-R1.1 Given a When b Then c\n'), 1, '文が空')

        t('design-merge: 追加された要件の本文も、別の要件の受入 ID・同じ受入 ID の 2 行・空の見出しの文を断る', _design_merge_checks_added_body)

        def _design_merge_accepts_words_before_and_arrow_in_new_text() -> None:
            # 2 巡目の指摘 4: 変更後の文に「変更前」や → が語として入っていても通す。断るのは括弧書きの変更前と、現在形の今の文 → の形だけ
            for text in ('変更前の本文を履歴に残す', '送信 → 既読 → マッチ の順に進める'):
                delta = '### 変更された要件\n\n### 要件 CHAT-R2: ' + text + '\n- CHAT-R2.1 Given x When y Then z\n'
                _, _, after, _ = _merge(_merge_draft(delta))
                assert '### 要件 CHAT-R2: ' + text in after, after
            for text in ('（変更前は「古い文」）新しい文', '(変更前 古い文) 新しい文', '一覧を返す → 新しい文', '（一覧を返す → 新しい文）'):
                delta = '### 変更された要件\n\n### 要件 CHAT-R2: ' + text + '\n- CHAT-R2.1 Given x When y Then z\n'
                _assert_merge_refused(_merge_draft(delta), 1, '変更後の文だけ')

        t('design-merge: 「変更前」「→」が語として入る変更後の文は通し、括弧書きの変更前と「今の文 → 新しい文」は断る', _design_merge_accepts_words_before_and_arrow_in_new_text)

        def _draft_template_explanations_above_delta_headings() -> None:
            # 2 巡目の指摘 5: 雛形の説明の段落が区分の見出しの下にあると、そのまま使って unreadable で exit 1 になる
            template = _read(os.path.join(_base_plugin_root(), 'templates', 'draft.md'))
            template = template.replace('<現在形の id_prefix>', 'CHAT').replace('<id_prefix>', 'ATT')
            delta = gh_task.parse_delta(template.split('\n'))
            assert [r for r, _, _ in delta['added'] + delta['changed']] == ['ATT-R1', 'CHAT-R2'], delta
            assert delta['unreadable'] == [], delta

        t('templates/draft.md: 説明の段落は「### 追加された要件」より上にあり、区分の中に残らない', _draft_template_explanations_above_delta_headings)

        def _design_merge_second_write_failure_is_reported() -> None:
            # 指摘 8: 書く順は draft → README。README の置き換えが落ちたら draft を元へ戻して exit 1
            root = _ds_tree({'docs/draft/att.md': _merge_draft(DELTA_OK), 'docs/4-domains/chat/README.md': README_BEFORE})
            draft = os.path.join(root, 'docs/draft/att.md')
            readme = os.path.join(root, 'docs/4-domains/chat/README.md')
            before = (_read(draft), _read(readme))
            real_replace = os.replace

            def failing_replace(src, dst, *a, **k):
                if os.path.abspath(dst) == os.path.abspath(readme):
                    raise OSError('disk full')
                return real_replace(src, dst, *a, **k)

            os.replace = failing_replace
            try:
                try:
                    gh_task.cmd_design_merge([draft])
                except gh_task.GhError as exc:
                    assert exc.code == 1 and 'README' in str(exc), exc
                else:
                    raise AssertionError('置き換えの失敗を黙った')
            finally:
                os.replace = real_replace
            assert (_read(draft), _read(readme)) == before, '片方だけ書かれた状態で止まった'
            leftovers = [n for d in ('docs/draft', 'docs/4-domains/chat') for n in os.listdir(os.path.join(root, d)) if '.tmp' in n]
            assert not leftovers, f'tmp が残った: {leftovers}'

        t('design-merge: 2 本目の置き換えが失敗したら draft を元に戻し、tmp を残さず exit 1', _design_merge_second_write_failure_is_reported)

        # ── draft_approved_at ──
        def _draft_approved_table_form() -> None:
            approved = gh_task.draft_approved_at(_draft_path('table.md', '# 設計\n\n| approved | 2026-09-04 |\n'))
            assert approved == '2026-09-04', f'表の形の承認日を読めていない: {approved!r}'

        t('draft_approved_at は表の形（| approved |）を読む', _draft_approved_table_form)

        def _draft_approved_table_form_with_bold_date() -> None:
            # `| approved | **2026-09-04 ／ …` のように日付の前に強調が付く。
            approved = gh_task.draft_approved_at(_draft_path('bold.md', '# 設計\n\n| approved | **2026-09-04 ／ 承認** |\n'))
            assert approved == '2026-09-04', f'強調つきの表の形を読めていない: {approved!r}'

        t(
            'draft_approved_at は日付の前に強調（**）が付く表の形も読む',
            _draft_approved_table_form_with_bold_date,
        )

        def _draft_approved_frontmatter_form() -> None:
            approved = gh_task.draft_approved_at(_draft_path('frontmatter.md', '---\napproved_at: 2026-09-05\n---\n# 設計\n'))
            assert approved == '2026-09-05', f'frontmatter の approved_at: を読めていない: {approved!r}'

        t('draft_approved_at は frontmatter の approved_at: を読む', _draft_approved_frontmatter_form)

        def _draft_unapproved_table_form() -> None:
            approved = gh_task.draft_approved_at(_draft_path('unapproved-table.md', _UNAPPROVED_TABLE))
            assert approved is None, f'未承認のはずが承認済みと読んだ: {approved!r}'

        t('draft_approved_at は未承認の表（| approved | |）を None と読む', _draft_unapproved_table_form)

        def _draft_unapproved_frontmatter_form() -> None:
            approved = gh_task.draft_approved_at(_draft_path('unapproved-frontmatter.md', '---\napproved_at:\n---\n# 設計\n'))
            assert approved is None, f'未承認のはずが承認済みと読んだ: {approved!r}'

        t('draft_approved_at は空の approved_at: を None と読む', _draft_unapproved_frontmatter_form)

        # ── ready の並び ────────────────────
        def _sorted_ready(items: list[dict]) -> list[int]:
            tasks = [i for i in items if i.get('type') == 'Issue' and i.get('kind') == 'task']
            return [r['number'] for r in sorted(tasks, key=gh_task.ready_sort_key(items))]

        def _task_row(number, parent, *, status=gh_task.READY_STATUS, title=None, kind='task'):
            return {
                'number': number, 'type': 'Issue', 'kind': kind, 'title': title or f'task {number}',
                'status': status, 'state': 'OPEN', 'parent_number': parent,
            }

        def _ready_sort_uses_wave_position() -> None:
            # 題名の短い ID のアルファベット順なら P7 < P8 < P9 で 802 が先頭に来るはずだが、
            # POSITION（items の並び。800 が先頭）を使えば 800 の子が先頭になる。
            items = [
                {'number': 800, 'kind': 'wave', 'title': '基盤（P9）', 'parent_number': None},
                {'number': 801, 'kind': 'wave', 'title': '認証（P8）', 'parent_number': None},
                {'number': 802, 'kind': 'wave', 'title': '課金（P7）', 'parent_number': None},
                # task は逆順（802 の子から）に並べる
                _task_row(12, 802),
                _task_row(11, 801),
                _task_row(10, 800),
            ]
            numbers = _sorted_ready(items)
            assert numbers == [10, 11, 12], (
                f'POSITION の順（800→801→802 の子）になっていない: {numbers}'
            )

        t('偽の wave 行を 3 つ足すと、並びが POSITION の順に変わる（先祖の wave）', _ready_sort_uses_wave_position)

        def _ready_sort_puts_waveless_after_wave_tasks() -> None:
            items = [
                {'number': 810, 'kind': 'wave', 'title': 'レイアウト（P2）', 'parent_number': None},
                _task_row(20, None),
                _task_row(21, 810),
                _task_row(19, None),
            ]
            numbers = _sorted_ready(items)
            assert numbers == [21, 19, 20], f'wave の無い task は wave のある task のあと・番号順: {numbers}'

        t('先祖に wave の無い task は、wave のある task のあとに番号順で並ぶ', _ready_sort_puts_waveless_after_wave_tasks)

        def _ordered_board(orders: dict) -> list[dict]:
            # wave の POSITION は 800→801→802、番号は 10→11→12 の順。着手順はこれに逆らう値を渡す
            items = [
                {'number': 800, 'kind': 'wave', 'title': '基盤（P9）', 'parent_number': None},
                {'number': 801, 'kind': 'wave', 'title': '認証（P8）', 'parent_number': None},
                {'number': 802, 'kind': 'wave', 'title': '課金（P7）', 'parent_number': None},
                _task_row(10, 800), _task_row(11, 801), _task_row(12, 802),
            ]
            return [
                {**i, 'order': orders[i['number']]} if i['number'] in orders else i
                for i in items
            ]

        def _reversed_board(orders: dict) -> list[dict]:
            # POSITION の順（800→801→802）と番号の順が逆: 先頭の wave の子が最も大きい番号
            items = [
                {'number': 800, 'kind': 'wave', 'title': '基盤（P9）', 'parent_number': None},
                {'number': 801, 'kind': 'wave', 'title': '認証（P8）', 'parent_number': None},
                {'number': 802, 'kind': 'wave', 'title': '課金（P7）', 'parent_number': None},
                _task_row(12, 800), _task_row(11, 801), _task_row(10, 802),
            ]
            return [
                {**i, 'order': orders[i['number']]} if i['number'] in orders else i
                for i in items
            ]

        def _ready_sort_by_order_field() -> None:
            numbers = _sorted_ready(_ordered_board({10: 3.0, 11: 2.0, 12: 1.0}))
            assert numbers == [12, 11, 10], f'着手順の小さい順になっていない: {numbers}'

        t('ready は着手順の小さい順に並ぶ（wave の POSITION・番号に逆らう値）', _ready_sort_by_order_field)

        def _ready_sort_unordered_after_ordered() -> None:
            numbers = _sorted_ready(_ordered_board({12: 5.0}))
            assert numbers == [12, 10, 11], f'着手順の無い行が着手順のある行より前に出た: {numbers}'

        t('着手順の無い task は、着手順のある task の後ろに並ぶ', _ready_sort_unordered_after_ordered)

        def _ready_sort_same_order_keeps_current() -> None:
            numbers = _sorted_ready(_reversed_board({10: 1.0, 11: 1.0, 12: 1.0}))
            assert numbers == [12, 11, 10], f'同じ着手順が今の並び（POSITION → 番号）にならない: {numbers}'
            numbers = _sorted_ready(_reversed_board({10: 2.0, 12: 1.0, 11: 1.0}))
            assert numbers == [12, 11, 10], f'同じ着手順の組が POSITION の順にならない: {numbers}'

        t('同じ着手順の task は今の並び（先祖の wave の POSITION → 番号）のまま', _ready_sort_same_order_keeps_current)

        def _ready_sort_without_order_field_is_unchanged() -> None:
            plain = _reversed_board({})
            with_none = [{**i, 'order': None} for i in plain]
            assert _sorted_ready(plain) == [12, 11, 10] == _sorted_ready(with_none), (
                '着手順の項目が無い items で並びが変わった（POSITION の順のはず）'
            )

        t('着手順の項目が無い items では今の並びと同じ', _ready_sort_without_order_field_is_unchanged)

        def _parse_item_reads_number_value() -> None:
            def node(fvs):
                return {'id': 'x', 'content': {'__typename': 'Issue', 'number': 7, 'title': 't',
                        'state': 'OPEN', 'url': 'u', 'parent': {'number': 1}},
                        'fieldValues': {'nodes': fvs}}
            order_fv = {'__typename': 'ProjectV2ItemFieldNumberValue', 'number': 12,
                        'field': {'name': gh_task.ORDER_FIELD}}
            other_fv = {'__typename': 'ProjectV2ItemFieldNumberValue', 'number': 99,
                        'field': {'name': '見積'}}
            got = gh_task.parse_item(node([order_fv, other_fv]))
            assert got['order'] == 12.0 and isinstance(got['order'], float), f"order={got['order']!r}"
            assert gh_task.parse_item(node([other_fv]))['order'] is None, '別名の数値を着手順と読んだ'
            assert gh_task.parse_item(node([]))['order'] is None, '値が無いのに None でない'

        t('parse_item は NumberValue（着手順）を float で読み、無ければ None', _parse_item_reads_number_value)

        def _items_query_reads_number_value() -> None:
            assert re.search(r'ProjectV2ItemFieldNumberValue\s*\{\s*number\b', gh_task.ITEMS_QUERY), (
                'ITEMS_QUERY に NumberValue（着手順）の断片が無い（本番で order が常に None になる）'
            )
            nodes_part = gh_task.ITEMS_QUERY.split('nodes', 1)[1]
            assert len(re.findall(r'\bfirst:', nodes_part)) == 1, (
                'ITEMS_QUERY の nodes の中の first: が 1 本でない（connection を増やした）'
            )

        t('ITEMS_QUERY が NumberValue（着手順）を引き、connection を増やしていない', _items_query_reads_number_value)

        def _ready_prints_order() -> None:
            def run(rows):
                gh_task.run_gh = make_board_gh(rows)
                out = io.StringIO()
                with redirect_stdout(out):
                    rc = gh_task.main(['ready'])
                assert rc == 0
                return out.getvalue()

            def board(orders):
                return [
                    _fake_row(800, kind='wave'), _fake_row(801, kind='wave'),
                    _fake_row(500, status='着手可', kind='feature', parent_number=800),
                    _fake_row(10, status='着手可', kind='task', parent_number=500, order=orders.get(10)),
                    _fake_row(11, status='着手可', kind='task', parent_number=500, order=orders.get(11)),
                    _fake_row(12, status='着手可', kind='task', parent_number=500, order=orders.get(12)),
                ]

            with_order = run(board({10: 30.0, 11: 20.0, 12: 12.0}))
            pos = [with_order.index(f'#{n}') for n in (12, 11, 10)]
            assert pos == sorted(pos), f'行の順が着手順の順でない: {with_order!r}'
            assert '(着手順 12)' in with_order, f'着手順が出ていない: {with_order!r}'
            plain = run(board({}))
            assert '着手順' not in plain, f'着手順の無い盤で「着手順」が出た: {plain!r}'
            pos = [plain.index(f'#{n}') for n in (10, 11, 12)]
            assert pos == sorted(pos), f'着手順の無い盤で今の並び（番号順）にならない: {plain!r}'

        t('ready は着手順の順に出し、値のある行だけ (着手順 N) を付ける。無い盤では出力が変わらない', _ready_prints_order)

        # ── ready の厳しい形 ───────────────────────
        def _ready_numbers(items, extras=None) -> list[int]:
            return [r['number'] for r in gh_task.ready_rows(items, extras or {})]

        def _base_board() -> list[dict]:
            return [
                {'number': 900, 'type': 'Issue', 'kind': 'wave', 'title': '基盤（P1）',
                 'status': '', 'state': 'OPEN', 'parent_number': None},
                {'number': 901, 'type': 'Issue', 'kind': 'feature', 'title': 'f',
                 'status': gh_task.READY_STATUS, 'state': 'OPEN', 'parent_number': 900},
                _task_row(1, 901),
            ]

        def _ready_strict_shows_task_under_ready_feature() -> None:
            assert _ready_numbers(_base_board()) == [1]

        t('ready は親の feature が着手可の task を出す', _ready_strict_shows_task_under_ready_feature)

        def _ready_strict_hides_empty_kind() -> None:
            items = _base_board() + [_task_row(2, 901, kind='')]
            assert _ready_numbers(items) == [1], '種別が空の行が ready に出た（orphans が拾う）'

        t('ready は種別が task でない（空の）行を出さない', _ready_strict_hides_empty_kind)

        def _ready_strict_hides_task_without_ready_feature() -> None:
            items = _base_board() + [
                {'number': 902, 'type': 'Issue', 'kind': 'feature', 'title': 'f2',
                 'status': gh_task.PENDING_STATUS, 'state': 'OPEN', 'parent_number': 900},
                _task_row(2, 902),   # 親の feature が承認待ち
                _task_row(3, None),  # 親なし
                _task_row(4, 900),   # 親が wave
            ]
            assert _ready_numbers(items) == [1], _ready_numbers(items)

        t('ready は親が着手可の feature でない task（承認待ち・親なし・wave 直下）を出さない', _ready_strict_hides_task_without_ready_feature)

        def _ready_strict_hides_blocked_task_or_feature() -> None:
            items = _base_board() + [_task_row(2, 901)]
            extras = {2: {'blocked_by_open': 1, 'blocked_by_open_numbers': [77]}}
            assert _ready_numbers(items, extras) == [1], 'task の未完了の blocked by を見ていない'
            extras = {901: {'blocked_by_open': 1, 'blocked_by_open_numbers': [78]}}
            assert _ready_numbers(items, extras) == [], 'feature の未完了の blocked by を見ていない'

        t('ready は task と親の feature の未完了の blocked by を見る', _ready_strict_hides_blocked_task_or_feature)

        def _ready_strict_hides_user_mark_but_shows_operation_mark() -> None:
            items = _base_board() + [
                _task_row(2, 901, title=f'{gh_task.USER_MARK} 手作業'),
                _task_row(3, 901, title=f'{gh_task.OPERATION_MARK} 操作'),
            ]
            assert _ready_numbers(items) == [1, 3], _ready_numbers(items)

        t('ready は [User] を出さず、着手可の [操作] は出す', _ready_strict_hides_user_mark_but_shows_operation_mark)

        def _ready_ignores_preceding_wave_when_feature_is_ready() -> None:
            # P2（910）は P1（900）に止められている。P1 が出ていなくても、親の feature が
            # 着手可なら P2 の下の task は ready に出る（ADR-0760。ready は wave の本文を読まない）。
            board = _base_board() + [
                {'number': 910, 'type': 'Issue', 'kind': 'wave', 'title': '部品（P2）',
                 'status': '', 'state': 'OPEN', 'parent_number': None},
                {'number': 911, 'type': 'Issue', 'kind': 'feature', 'title': 'f3',
                 'status': gh_task.READY_STATUS, 'state': 'OPEN', 'parent_number': 910},
                _task_row(5, 911),
            ]
            extras = {910: {'blocked_by_numbers': [900], 'blocked_by_open_numbers': [900]}}
            assert _ready_numbers(board, extras) == [1, 5], 'P1 が未了でも、親の feature が着手可なら P2 の task も出る（ADR-0760）'
            # P1 が出た盤面でも同じ（出ていない側と結果が変わらない）
            done_board = [
                dict(i, status=gh_task.DONE_STATUS) if i['number'] in (1, 901) else i for i in board
            ]
            done_board = [i for i in done_board if i['number'] != 1] + [_task_row(1, 901, status=gh_task.DONE_STATUS)]
            assert _ready_numbers(done_board, extras) == [5], _ready_numbers(done_board, extras)

        t('ready は先の wave が未了でも、親の feature が着手可の task を出す（wave の門を見ない）', _ready_ignores_preceding_wave_when_feature_is_ready)

        def _ready_strict_hides_closed_and_non_ready_status() -> None:
            items = _base_board() + [
                dict(_task_row(2, 901), state='CLOSED'),
                _task_row(3, 901, status=gh_task.IN_PROGRESS_STATUS),
            ]
            assert _ready_numbers(items) == [1]

        t('ready は閉じた issue と、着手可でない Status の行を出さない', _ready_strict_hides_closed_and_non_ready_status)

        # ── close-parents ─────────────────────────
        def _close_parents_skips_childless_parent() -> None:
            items = [{'number': 100, 'kind': gh_task.FEATURE_KIND, 'state': 'OPEN', 'title': 'f'}]
            plan = gh_task.close_parents_plan(items, {}, {100: []})
            assert plan['close_parents'] == [], f'子 0 件なのに閉じる対象になった: {plan}'

        t('close-parents は子 0 件の親を閉じない', _close_parents_skips_childless_parent)

        def _close_parents_closes_fully_closed_parent() -> None:
            items = [{'number': 101, 'kind': gh_task.FEATURE_KIND, 'state': 'OPEN', 'title': 'f'}]
            plan = gh_task.close_parents_plan(items, {}, {101: [{'state': 'closed'}] * 3})
            assert plan['close_parents'] == [
                {'number': 101, 'kind': 'feature', 'children_total': 3},
            ], plan

        t('close-parents は直下の子が全部閉じた feature を閉じる対象にする', _close_parents_closes_fully_closed_parent)

        def _close_parents_skips_permanent_wave() -> None:
            items = [{'number': 102, 'kind': gh_task.WAVE_KIND, 'state': 'OPEN', 'title': 'P0'}]
            bodies = {102: gh_task.PERMANENT_MARK}
            plan = gh_task.close_parents_plan(items, bodies, {102: [{'state': 'closed'}] * 5})
            assert plan['close_parents'] == [], f'常設の wave を閉じようとした: {plan}'

        t('close-parents は「- 常設: はい」の wave を閉じない', _close_parents_skips_permanent_wave)

        # wave は「出る条件のコマンド」の行が無ければ、
        # 子が全部閉じていても close-parents では閉じない（wave-holds に回るだけ）。
        def _close_parents_skips_wave_without_exit_line() -> None:
            items = [{'number': 103, 'kind': gh_task.WAVE_KIND, 'state': 'OPEN', 'title': 'P1'}]
            plan = gh_task.close_parents_plan(items, {}, {103: [{'state': 'closed'}] * 2})
            assert plan['close_parents'] == [], (
                f'出る条件のコマンドの行が無い wave を閉じた: {plan}'
            )

        t(
            'close-parents は「出る条件のコマンド」の行が無い wave を閉じない',
            _close_parents_skips_wave_without_exit_line,
        )

        def _close_parents_closes_wave_with_exit_line() -> None:
            items = [{'number': 104, 'kind': gh_task.WAVE_KIND, 'state': 'OPEN', 'title': 'P1'}]
            bodies = {104: '- 出る条件のコマンド: exit 0（2026-09-28・abc1234）\n'}
            plan = gh_task.close_parents_plan(items, bodies, {104: [{'state': 'closed'}] * 2})
            assert plan['close_parents'] == [
                {'number': 104, 'kind': 'wave', 'children_total': 2},
            ], f'行があるのに閉じなかった: {plan}'

        t(
            'close-parents は「出る条件のコマンド」の行があり子が全部閉じた wave を閉じる',
            _close_parents_closes_wave_with_exit_line,
        )

        # ── unblocked ────────────────────────────────────────────
        def _unblocked_ignores_blocked_task() -> None:
            items = [{
                'number': 110, 'type': 'Issue', 'kind': 'task', 'status': gh_task.DEP_STATUS,
                'state': 'OPEN', 'title': 't', 'parent_number': None,
            }]
            rows = gh_task.unblocked_rows(items, {110: {'blocked_by_open': 1}}, {})
            assert rows == [], f'未完了の blocked by があるのに出た: {rows}'

        t('unblocked は未完了の blocked by がある task を出さない', _unblocked_ignores_blocked_task)

        def _unblocked_lists_resolved_task() -> None:
            items = [
                {
                    'number': 120, 'type': 'Issue', 'kind': gh_task.FEATURE_KIND,
                    'status': gh_task.READY_STATUS, 'state': 'OPEN', 'title': 'F',
                    'parent_number': None,
                },
                {
                    'number': 121, 'type': 'Issue', 'kind': 'task', 'status': gh_task.DEP_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 120,
                },
            ]
            extras = {121: {'blocked_by_open': 0}, 120: {'blocked_by_open': 0}}
            rows = gh_task.unblocked_rows(items, extras, {})
            assert rows == [{'number': 121, 'title': 't', 'set_status': gh_task.READY_STATUS}], rows

        t('unblocked は依存が解けた task を、親の Status とともに出す', _unblocked_lists_resolved_task)

        def _unblocked_crosses_wave_gate_only_for_ready_feature() -> None:
            items = [
                {
                    'number': 130, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'OPEN',
                    'title': 'P1', 'parent_number': None,
                },
                {
                    'number': 131, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'OPEN',
                    'title': 'P2', 'parent_number': None,
                },
                {
                    'number': 132, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 'F', 'parent_number': 131,
                },
                {
                    'number': 133, 'type': 'Issue', 'kind': 'task', 'status': gh_task.DEP_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 132,
                },
            ]
            extras = {
                133: {'blocked_by_open': 0}, 132: {'blocked_by_open': 0},
                131: {'blocked_by_open_numbers': [130]},
            }
            rows = gh_task.unblocked_rows(items, extras, {})
            assert rows == [{
                'number': 133, 'title': 't', 'set_status': gh_task.READY_STATUS,
                'note': '先の wave #130 が出ていないが feature #132 が着手可なので通した',
            }], f'親の feature が着手可なのに先の wave で止めた・note が無い: {rows}'
            # 親の feature が承認待ちなら、今までどおり先の wave が出るまで出さない
            pending_items = [dict(i, status=gh_task.PENDING_STATUS) if i['number'] == 132 else i for i in items]
            rows = gh_task.unblocked_rows(pending_items, extras, {})
            assert rows == [], f'親の feature が承認待ちなのに先の wave を越えた: {rows}'
            # Status が空の feature は着手可ではない（既定値で補わない）。先の wave が未了なら出さない
            empty_items = [dict(i, status='') if i['number'] == 132 else i for i in items]
            rows = gh_task.unblocked_rows(empty_items, extras, {})
            assert rows == [], f'Status が空の feature の子が先の wave を越えた: {rows}'
            # 先の wave が出た盤面では、親が着手可でも「通した」の note を付けない
            exited = {130: '- 出る条件のコマンド: exit 0（2026-09-30・abc1234）'}
            # （wave は task の子孫が全部完了で、出る条件の行があって「出た」。完了の task を足す）
            exited_items = items + [
                {'number': 134, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                 'state': 'OPEN', 'title': 'F0', 'parent_number': 130},
                {'number': 135, 'type': 'Issue', 'kind': 'task', 'status': gh_task.DONE_STATUS,
                 'state': 'CLOSED', 'title': 't0', 'parent_number': 134},
            ]
            rows = gh_task.unblocked_rows(exited_items, extras, exited)
            assert rows == [{'number': 133, 'title': 't', 'set_status': gh_task.READY_STATUS}], (
                f'W1 が出たのに「出ていないが通した」と書いた: {rows}')

        t('unblocked は親の feature が着手可なら先の wave を越えて note つきで出し、承認待ちなら今までどおり待つ',
          _unblocked_crosses_wave_gate_only_for_ready_feature)

        # 目印つき task は set で戻せない（set が承認待ち→
        # 着手可の目印つきを断る）ので、set_status の代わりに注記を出す。
        def _unblocked_marked_task_gets_note_not_set_status() -> None:
            items = [{
                'number': 134, 'type': 'Issue', 'kind': 'task', 'status': gh_task.DEP_STATUS,
                'state': 'OPEN', 'title': '[操作] t', 'parent_number': None,
            }]
            rows = gh_task.unblocked_rows(items, {134: {'blocked_by_open': 0}}, {})
            assert rows == [{
                'number': 134, 'title': '[操作] t', 'set_status': None,
                'note': 'start --approved が要る（目印つきの task は set で着手可にしない）',
            }], rows

        t(
            'unblocked は目印つきの task に set_status を出さず、注記だけ出す',
            _unblocked_marked_task_gets_note_not_set_status,
        )

        def _unblocked_non_feature_parent_gets_note_not_set_status() -> None:
            items = [
                {
                    'number': 140, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'OPEN',
                    'title': 'P1', 'parent_number': None,
                },
                {
                    'number': 141, 'type': 'Issue', 'kind': 'task', 'status': gh_task.DEP_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 140,
                },
            ]
            extras = {141: {'blocked_by_open': 0}, 140: {'blocked_by_open': 0}}
            rows = gh_task.unblocked_rows(items, extras, {})
            assert rows == [{
                'number': 141, 'title': 't', 'set_status': None,
                'note': '親が feature ではないため、戻す Status は人が判断する',
            }], rows

        t(
            'unblocked は親が feature でないとき set_status を出さず、注記だけ出す',
            _unblocked_non_feature_parent_gets_note_not_set_status,
        )

        # ── align ─────────────────────
        def _align_moves_ready_child_with_no_blockers() -> None:
            items = [
                {
                    'number': 200, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 'F', 'parent_number': None,
                },
                {
                    'number': 201, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 200,
                },
            ]
            extras = {201: {'blocked_by_open': 0}}
            plan = gh_task.align_plan(items, extras, {})
            assert plan == {
                'align': [{
                    'feature': 200,
                    'moves': [{'number': 201, 'to': gh_task.READY_STATUS, 'from': gh_task.PENDING_STATUS}],
                    'skipped': [],
                }],
            }, plan

        t('align は承認待ちの子を、blocked by が無ければ着手可へ動かす', _align_moves_ready_child_with_no_blockers)

        def _align_moves_blocked_child_to_dependency_wait() -> None:
            items = [
                {
                    'number': 210, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 'F', 'parent_number': None,
                },
                {
                    'number': 211, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 210,
                },
            ]
            extras = {211: {'blocked_by_open': 1}}
            plan = gh_task.align_plan(items, extras, {})
            assert plan['align'][0]['moves'] == [
                {'number': 211, 'to': gh_task.DEP_STATUS, 'from': gh_task.PENDING_STATUS},
            ], plan

        t('align は未完了の blocked by がある子を依存待ちへ動かす', _align_moves_blocked_child_to_dependency_wait)

        def _align_skips_marked_children() -> None:
            items = [
                {
                    'number': 220, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 'F', 'parent_number': None,
                },
                {
                    'number': 221, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                    'state': 'OPEN', 'title': '[操作] t', 'parent_number': 220,
                },
                {
                    'number': 222, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                    'state': 'OPEN', 'title': '[User] t2', 'parent_number': 220,
                },
            ]
            extras = {221: {'blocked_by_open': 0}, 222: {'blocked_by_open': 0}}
            plan = gh_task.align_plan(items, extras, {})
            entry = plan['align'][0]
            assert entry['moves'] == [], f'目印つきの子を動かした: {entry}'
            assert sorted(entry['skipped']) == [221, 222], entry

        t(
            'align は [操作]・[User] の目印つきの子を動かさず、番号だけを出す',
            _align_skips_marked_children,
        )

        def _align_moves_child_with_late_added_body_line() -> None:
            # 旧版（2.1.0 まで）の new が書いた「- 後から追加:」の行が本文に残る子も、目印が
            # 無ければ他の承認待ちの子と同じに動かす（行は読まない・消しにも行かない）。
            items = [
                {
                    'number': 230, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 'F', 'parent_number': None,
                },
                {
                    'number': 231, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 230,
                },
                {
                    'number': 232, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                    'state': 'OPEN', 'title': 't2', 'parent_number': 230,
                },
            ]
            extras = {231: {'blocked_by_open': 0}, 232: {'blocked_by_open': 1}}
            bodies = {
                231: '- 後から追加: 2026-09-28 12:00\n',
                232: '- 後から追加: 2026-09-28 12:00\n',
            }
            plan = gh_task.align_plan(items, extras, bodies)
            entry = plan['align'][0]
            assert entry['moves'] == [
                {'number': 231, 'to': gh_task.READY_STATUS, 'from': gh_task.PENDING_STATUS},
                {'number': 232, 'to': gh_task.DEP_STATUS, 'from': gh_task.PENDING_STATUS},
            ], f'「後から追加」の行が残る子を着手可・依存待ちへ動かしていない: {entry}'
            assert entry['skipped'] == [], entry

        t(
            'align は本文に「- 後から追加:」が残る承認待ちの子も着手可へ動かす（未完了の blocked by があれば依存待ち）',
            _align_moves_child_with_late_added_body_line,
        )

        def _align_moves_children_added_after_first_plan() -> None:
            # 1 回目の align_plan のあとで子になった task も、2 回目で着手可へ動く
            # （feature を初めて見た時点の子の一覧は持たない）。
            feature = {
                'number': 240, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                'state': 'OPEN', 'title': 'F', 'parent_number': None,
            }
            child_a = {
                'number': 241, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                'state': 'OPEN', 'title': 't1', 'parent_number': 240,
            }
            first_plan = gh_task.align_plan([feature, child_a], {241: {'blocked_by_open': 0}}, {})
            assert first_plan['align'][0]['moves'] == [
                {'number': 241, 'to': gh_task.READY_STATUS, 'from': gh_task.PENDING_STATUS},
            ], f'初回で既存の子を動かせていない: {first_plan}'
            # 1 回目で動かした 241 は、次に読むときには着手可になっている（手で反映させる）。
            child_a_after = dict(child_a, status=gh_task.READY_STATUS)
            child_b = {
                'number': 242, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                'state': 'OPEN', 'title': 't2', 'parent_number': 240,
            }
            second_plan = gh_task.align_plan(
                [feature, child_a_after, child_b],
                {241: {'blocked_by_open': 0}, 242: {'blocked_by_open': 0}}, {},
            )
            entry = second_plan['align'][0]
            assert entry['moves'] == [
                {'number': 242, 'to': gh_task.READY_STATUS, 'from': gh_task.PENDING_STATUS},
            ], f'あとから子になった 242 を着手可へ動かしていない: {entry}'
            assert entry['skipped'] == [], entry

        t(
            'align は 1 回目のあとで子になった task も、2 回目で着手可へ動かす（初めて見た子の一覧を持たない）',
            _align_moves_children_added_after_first_plan,
        )

        # ── 着手の判定が align・start・set・new で割れないこと ──────────────────
        EXIT_LINE = '- 出る条件のコマンド: exit 0 （例）'
        W1, F1, T1, W2, FEAT, CHILD = 10, 11, 12, 20, 21, 22

        def _board(
            *, title: str = 'task', status: str = gh_task.PENDING_STATUS, state: str = 'OPEN',
            parent_kind: str = 'feature', feature_status: str = gh_task.READY_STATUS,
            child_blockers: tuple = (), feature_blockers: tuple = (), prior: str = 'none',
        ) -> tuple[list[dict], dict, dict]:
            """W2（wave）→ FEAT（feature）→ CHILD（task）の板。prior は W2 を止める先の wave W1 の形:
            none=止めるものが無い / unfinished=W1 の task が進行中 / no-line=task は全部完了だが
            出る条件の行が無い / exited=行があり W1 は閉じた / exited-open=行があるが W1 はまだ開いている。"""
            items = [
                {'number': W2, 'kind': gh_task.WAVE_KIND, 'title': 'W2'},
                {'number': FEAT, 'kind': gh_task.FEATURE_KIND, 'status': feature_status,
                 'title': 'F', 'parent_number': W2},
                {'number': CHILD, 'kind': 'task', 'status': status, 'state': state,
                 'title': title, 'parent_number': FEAT if parent_kind == 'feature' else W2},
            ]
            if parent_kind != 'feature':
                items = [i for i in items if i['number'] != FEAT]
            extras: dict = {
                CHILD: {'blocked_by_open_numbers': list(child_blockers)},
                FEAT: {'blocked_by_open_numbers': list(feature_blockers)},
            }
            bodies: dict = {}
            if prior != 'none':
                items += [
                    {'number': W1, 'kind': gh_task.WAVE_KIND, 'title': 'W1',
                     'state': 'CLOSED' if prior == 'exited' else 'OPEN'},
                    {'number': F1, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                     'title': 'F1', 'parent_number': W1},
                    {'number': T1, 'kind': 'task', 'title': 'T1', 'parent_number': F1,
                     'status': gh_task.IN_PROGRESS_STATUS if prior == 'unfinished' else gh_task.DONE_STATUS,
                     'state': 'OPEN' if prior == 'unfinished' else 'CLOSED'},
                ]
                key = 'blocked_by_closed_numbers' if prior == 'exited' else 'blocked_by_open_numbers'
                extras[W2] = {key: [W1]}
                if prior in ('exited', 'exited-open'):
                    bodies[W1] = EXIT_LINE
            return items, extras, bodies

        def _align_destination(items, extras, bodies) -> str:
            gh_task.run_gh = make_command_gh(items, bodies=bodies, extras=extras)
            out = io.StringIO()
            with redirect_stdout(out):
                assert gh_task.cmd_align(as_json=True) == 0
            for entry in json.loads(out.getvalue())['align']:
                for move in entry['moves']:
                    if move['number'] == CHILD:
                        return 'ready' if move['to'] == gh_task.READY_STATUS else 'dep'
                if CHILD in entry['skipped']:
                    return 'skipped'
            return 'none'

        def _align_waived(items, extras, bodies) -> tuple[list, str]:
            """cmd_align の JSON の wave_waived（feature の行）と、テキストの出力。wave の extras を cmd_align が引く経路を通す。"""
            gh_task.run_gh = make_command_gh(items, bodies=bodies, extras=extras)
            out = io.StringIO()
            with redirect_stdout(out):
                assert gh_task.cmd_align(as_json=True) == 0
            waived = [w for entry in json.loads(out.getvalue())['align'] for w in entry.get('wave_waived') or []]
            text = io.StringIO()
            with redirect_stdout(text):
                assert gh_task.cmd_align(as_json=False) == 0
            return waived, text.getvalue()

        def _verdict(fn) -> str:
            try:
                fn()
            except gh_task.GhError as exc:
                assert exc.code == 2, f'exit {exc.code}（期待 2）: {exc}'
                return 'refused'
            return 'ok'

        def _start_verdict(items, extras, bodies) -> str:
            log: list = []
            gh_task.run_gh = make_command_gh(items, bodies=bodies, extras=extras, write_log=log)
            verdict = _verdict(lambda: gh_task.cmd_start(CHILD, None))
            assert (verdict == 'ok') == bool(log), f'start の結果と書き込みが合わない: {verdict} {log}'
            return verdict

        def _set_verdict(items, extras, bodies) -> str:
            log: list = []
            gh_task.run_gh = make_command_gh(items, bodies=bodies, extras=extras, write_log=log)
            verdict = _verdict(lambda: gh_task.cmd_set(CHILD, 'Status', gh_task.READY_STATUS))
            assert (verdict == 'ok') == bool(log), f'set の結果と書き込みが合わない: {verdict} {log}'
            return verdict

        def _new_verdict(items, extras, bodies, title: str) -> str:
            base = make_command_gh(items, bodies=bodies, extras=extras)

            def fake(args, input_text=None):
                if args[:4] == ['api', '-X', 'POST', f'repos/{gh_task.REPO}/issues']:
                    return 0, json.dumps({'number': CHILD, 'id': 424242, 'node_id': 'X'}), ''
                return base(args, input_text)

            gh_task.run_gh = fake
            out = io.StringIO()
            try:
                with redirect_stdout(out):
                    gh_task.cmd_new([title, '--parent', str(FEAT)])
            except gh_task.GhError:
                return 'refused'
            text = out.getvalue()
            if 'で着手できる' in text:
                return 'hint'
            return 'reason' if 'いまは着手できない' in text else 'silent'

        BOARD_TABLE = (
            ('止めるものが無い', {}, 'ready'),
            ('自分に blocked by', dict(child_blockers=(900,)), 'dep'),
            ('親の feature に blocked by', dict(feature_blockers=(900,)), 'dep'),
            ('先の wave が出ていない（task が進行中）でも、親の feature が着手可なら通す', dict(prior='unfinished'), 'ready'),
            ('先の wave の task は完了だが出る条件の行が無くても通す', dict(prior='no-line'), 'ready'),
            ('先の wave が出た（blocker は閉じた）', dict(prior='exited'), 'ready'),
            ('先の wave が出た（blocker はまだ開いている）', dict(prior='exited-open'), 'ready'),
            ('目印 [User]', dict(title='[User] task'), 'skipped'),
            ('目印 [操作]', dict(title=f'{gh_task.OPERATION_MARK} task'), 'skipped'),
            ('親の feature が承認待ち', dict(feature_status=gh_task.PENDING_STATUS), 'none'),
            ('親が wave', dict(parent_kind='wave'), 'none'),
            ('CLOSED', dict(state='CLOSED'), 'none'),
        )

        def _decision_matches_align() -> None:
            for label, spec, expected in BOARD_TABLE:
                items, extras, bodies = _board(**spec)
                dest = _align_destination(items, extras, bodies)
                assert dest == expected, f'{label}: align の行き先 {dest}（期待 {expected}）'
                # 門を越えて着手可へ動かしたときだけ、align は wave_waived と「通した」の 1 行を出す
                waived, text = _align_waived(items, extras, bodies)
                if dest == 'ready' and spec.get('prior') in ('unfinished', 'no-line'):
                    assert waived == [W1], f'{label}: wave_waived {waived}（期待 [{W1}]）'
                    assert f'先の wave #{W1} が出ていないが feature #{FEAT} が着手可なので通した' in text, f'{label}: {text}'
                else:
                    assert waived == [] and '通した' not in text, f'{label}: 門を越えていないのに通した: {waived} {text}'
                startable = dest == 'ready'
                start = _start_verdict(items, extras, bodies)
                setv = _set_verdict(items, extras, bodies)
                assert start == ('ok' if startable else 'refused'), f'{label}: start={start} align={dest}'
                assert setv == ('ok' if startable else 'refused'), f'{label}: set={setv} align={dest}'
                if spec.get('state') == 'CLOSED':
                    continue  # new が作る issue は常に開いている
                new = _new_verdict(items, extras, bodies, spec.get('title', 'task'))
                if startable:
                    assert new == 'hint', f'{label}: new={new} align={dest}'
                else:
                    assert new != 'hint', f'{label}: new が案内を出した（align={dest}）'
                if dest == 'dep':
                    assert new == 'reason', f'{label}: 断られる理由が出ていない（new={new}）'

        t(
            'align の行き先と、start（承認待ち）・set（→ 着手可）・new の案内の可否が、盤面の全行で一致する',
            _decision_matches_align,
        )

        def _unblocked_wave_gate_both_sides() -> None:
            # 依存待ちの task（blocker 0）が unblocked に出るかを、先の wave の形 × 親の feature の Status の全組で見る。
            # 先の wave が未了: 着手可の feature の子だけ note つきで通し、承認待ち・Status 空は待つ。
            # 先の wave が出た（または止めるものが無い）: 門は関係なく、note は付かない。
            for prior, unresolved in (('none', False), ('unfinished', True), ('no-line', True),
                                      ('exited', False), ('exited-open', False)):
                # 戻し先は親の Status そのもの。空の feature の子は set が断る値を出さず、人の判断にする（None）
                for feature_status, expected in (
                    (gh_task.READY_STATUS, gh_task.READY_STATUS),
                    (gh_task.PENDING_STATUS, gh_task.PENDING_STATUS),
                    ('', None),
                ):
                    items, extras, bodies = _board(status=gh_task.DEP_STATUS, feature_status=feature_status, prior=prior)
                    items = [dict(i, type='Issue') for i in items]
                    if W2 in extras:
                        # 本番の読み取りは blocked_by_numbers（open も closed も）で W2 を W1 に結ぶ。閉じた W1 も結んで渡す
                        merged = extras[W2].get('blocked_by_closed_numbers', []) + extras[W2].get('blocked_by_open_numbers', [])
                        extras = {**extras, W2: {'blocked_by_numbers': merged}}
                    rows = gh_task.unblocked_rows(items, extras, bodies)
                    label = f'先の wave={prior}・親の feature の Status={feature_status or "空"}'
                    if unresolved and feature_status != gh_task.READY_STATUS:
                        assert rows == [], f'{label}: 門を越えた: {rows}'
                        continue
                    assert [r['number'] for r in rows] == [CHILD] and rows[0]['set_status'] == expected, f'{label}: {rows}'
                    assert ('note' in rows[0]) == ((unresolved and feature_status == gh_task.READY_STATUS) or not feature_status), (
                        f'{label}: note の有無が合わない: {rows}')
                    if not feature_status:
                        assert rows[0]['note'] == '親の feature の Status が空。人が判断する', rows

        t('unblocked は先の wave の形 × 親の feature の Status の全組で、門を越えるのは「未了 × 着手可」だけ',
          _unblocked_wave_gate_both_sides)

        def _cmd_unblocked_prints_waived_note() -> None:
            items, extras, bodies = _board(status=gh_task.DEP_STATUS, prior='unfinished')
            items = [dict(i, type='Issue') for i in items]
            gh_task.run_gh = make_command_gh(items, bodies=bodies, extras=extras)
            out = io.StringIO()
            with redirect_stdout(out):
                assert gh_task.cmd_unblocked(items=items) == 0
            expected = f'着手可（先の wave #{W1} が出ていないが feature #{FEAT} が着手可なので通した）'
            assert expected in out.getvalue(), f'today に「通した」の 1 行が出ない: {out.getvalue()}'
            plain_items, plain_extras, plain_bodies = _board(status=gh_task.DEP_STATUS, prior='exited')
            plain_items = [dict(i, type='Issue') for i in plain_items]
            gh_task.run_gh = make_command_gh(plain_items, bodies=plain_bodies, extras=plain_extras)
            out = io.StringIO()
            with redirect_stdout(out):
                assert gh_task.cmd_unblocked(items=plain_items) == 0
            assert '通した' not in out.getvalue() and '→ 着手可' in out.getvalue(), out.getvalue()

        t('cmd_unblocked は通した行に「先の wave #N が出ていないが feature #M が着手可なので通した」を括弧で添える',
          _cmd_unblocked_prints_waived_note)

        def _unblocked_marked_task_keeps_waived_note() -> None:
            # 目印つき（[操作]）の task も、門を越えたなら note の後ろに「通した」を「・」でつなぐ
            items, extras, bodies = _board(status=gh_task.DEP_STATUS, prior='unfinished', title=f'{gh_task.OPERATION_MARK} DNS')
            items = [dict(i, type='Issue') for i in items]
            rows = gh_task.unblocked_rows(items, extras, bodies)
            assert len(rows) == 1 and rows[0]['set_status'] is None, rows
            assert rows[0]['note'] == ('start --approved が要る（目印つきの task は set で着手可にしない）'
                                       f'・先の wave #{W1} が出ていないが feature #{FEAT} が着手可なので通した'), rows
            items, extras, bodies = _board(status=gh_task.DEP_STATUS, prior='exited', title=f'{gh_task.OPERATION_MARK} DNS')
            items = [dict(i, type='Issue') for i in items]
            rows = gh_task.unblocked_rows(items, {**extras, W2: {'blocked_by_numbers': [W1]}}, bodies)
            assert [r['note'] for r in rows] == ['start --approved が要る（目印つきの task は set で着手可にしない）'], rows

        t('unblocked は目印つき（[操作]）の task にも、門を越えたときは「通した」を note の後ろに足す',
          _unblocked_marked_task_keeps_waived_note)

        def _wave_lookup_is_light_only_without_blocking_wave() -> None:
            # 親の feature が着手可と確かめたあとは先の wave を見ないので、板の全件（items(first:）を引かない（ADR-0760）。
            def count_board_fetches(prior: str) -> tuple[int, str]:
                calls = {'board': 0}
                items, extras, bodies = _board(prior=prior)
                base = make_command_gh(items, bodies=bodies, extras=extras)

                def counting(args, input_text=None):
                    if 'items(first:' in ' '.join(args):
                        calls['board'] += 1
                    return base(args, input_text)

                gh_task.run_gh = counting
                verdict = _verdict(lambda: gh_task.cmd_start(CHILD, None))
                return calls['board'], verdict

            assert count_board_fetches('none') == (0, 'ok')
            assert count_board_fetches('unfinished') == (0, 'ok'), '先の wave が未了でも、着手の判定は板の全件を引かず通す'

        t('着手の判定は、先の wave の有無によらず全件を引かずに通す（親の feature が着手可なら wave の門を見ない）',
          _wave_lookup_is_light_only_without_blocking_wave)

        def _new_survives_failing_hint_reads() -> None:
            # 案内のための親の feature の読み取りだけが落ちても、issue はできているので new は exit 0。1 行だけ出す。
            items, extras, bodies = _board(prior='exited')
            base = make_command_gh(items, bodies=bodies, extras=extras)
            posted: list = []

            def fake(args, input_text=None):
                if args[:4] == ['api', '-X', 'POST', f'repos/{gh_task.REPO}/issues']:
                    posted.append(1)
                    return 0, json.dumps({'number': CHILD, 'id': 424242, 'node_id': 'X'}), ''
                if posted and 'issue(number:$number) {' in ' '.join(args) and _extract_flag(args, 'number') == str(FEAT):
                    return 1, '', 'HTTP 502 (simulated)'
                return base(args, input_text)

            gh_task.run_gh = fake
            out = io.StringIO()
            with redirect_stdout(out):
                assert gh_task.cmd_new(['task', '--parent', str(FEAT)]) == 0
            text = out.getvalue()
            assert len(posted) == 1, f'issue を {len(posted)} 回作った'
            assert f'#{CHILD} task' in text, text
            assert '着手できるかを確かめられなかった: ' in text and 'HTTP 502' in text, text
            assert 'で着手できる' not in text and 'いまは着手できない' not in text, text

        t('new は issue を作ったあと、着手の案内の読み取りが落ちても exit 0 で、確かめられなかった旨を 1 行出す', _new_survives_failing_hint_reads)

        def _wave_is_read_once() -> None:
            # 親の feature が着手可なら先の wave を見ないので、wave の行を引かない（ADR-0760）。
            items, extras, bodies = _board(prior='unfinished')
            base = make_command_gh(items, bodies=bodies, extras=extras)
            reads: list = []

            def counting(args, input_text=None):
                if 'issue(number:$number) {' in ' '.join(args):
                    reads.append(int(_extract_flag(args, 'number')))
                return base(args, input_text)

            gh_task.run_gh = counting
            assert _verdict(lambda: gh_task.cmd_start(CHILD, None)) == 'ok'
            assert reads.count(W2) == 0, f'wave #{W2} を {reads.count(W2)} 回読んだ: {reads}'

        t('着手の判定は、先の wave を読まない', _wave_is_read_once)

        def _align_skips_closed_and_non_task_children() -> None:
            feature = {
                'number': 250, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                'state': 'OPEN', 'title': 'F', 'parent_number': None,
            }

            def child(number, **kw):
                row = {'number': number, 'type': 'Issue', 'kind': 'task',
                       'status': gh_task.PENDING_STATUS, 'state': 'OPEN', 'title': 't',
                       'parent_number': 250}
                row.update(kw)
                return row

            children = [
                child(251),                                  # 通常の子
                child(252, state='CLOSED'),                  # 閉じた子（承認待ちのまま）
                child(253, state='CLOSED', status=gh_task.READY_STATUS),
                child(254, kind=gh_task.DESIGN_MEMO_KIND),   # 設計メモ
                child(255, kind=''),                         # 種別が空は task 扱いで対象
                child(256, state='CLOSED', title=f'{gh_task.OPERATION_MARK} t'),  # 閉じた目印つき
            ]
            plan = gh_task.align_plan([feature] + children, {}, {})
            assert len(plan['align']) == 1, plan
            entry = plan['align'][0]
            assert [m['number'] for m in entry['moves']] == [251, 255], entry
            assert entry['skipped'] == [], f'閉じた子・設計メモが skipped に出た: {entry}'

        t('align は閉じた子と task 以外の種別の子を、moves にも skipped にも出さない（種別が空は対象のまま）', _align_skips_closed_and_non_task_children)

        def _align_does_not_fetch_child_bodies() -> None:
            items, extras, bodies = _board(prior='exited')
            gh_task.run_gh = make_command_gh(items, bodies=bodies, extras=extras)
            asked: list = []
            real_fetch_bodies = gh_task.fetch_bodies
            gh_task.fetch_bodies = lambda numbers: asked.append(sorted(numbers)) or real_fetch_bodies(numbers)
            try:
                with redirect_stdout(io.StringIO()):
                    assert gh_task.cmd_align(as_json=True) == 0
            finally:
                gh_task.fetch_bodies = real_fetch_bodies
            assert asked == [[W1, W2]], f'wave の本文だけを引くはず: {asked}'

        t('align は wave の本文だけを引き、子の本文を引かない', _align_does_not_fetch_child_bodies)

        def _align_does_not_read_or_write_align_seen_file() -> None:
            # 2.1.0 が gh-align-seen.json を実際に置いていた場所（共有の置き場）に、
            # 「この子は一覧に無い」と言う控えを残しても、読まず・書かず・消さず・横にも増やさない。
            import subprocess
            repo = os.path.realpath(tempfile.mkdtemp(dir=cache_tmp_dir))
            subprocess.run(['git', '-C', repo, 'init', '-q'], check=True, capture_output=True)
            saved_root = os.environ.get('HIRAI_TASK_ROOT')
            os.environ['HIRAI_TASK_ROOT'] = repo
            try:
                shared = gh_task._shared_state_dir()
                os.makedirs(shared, exist_ok=True)
                leftover = os.path.join(shared, 'gh-align-seen.json')
                old_body = json.dumps({f'{gh_task.REPO}#7': {'244': []}})
                with open(leftover, 'w', encoding='utf-8') as f:
                    f.write(old_body)
                before = sorted(os.listdir(shared))
                feature = {
                    'number': 244, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 'F', 'parent_number': None,
                }
                child = {
                    'number': 245, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 244,
                }
                plan = gh_task.align_plan([feature, child], {245: {'blocked_by_open': 0}}, {})
                assert plan['align'][0]['moves'] == [
                    {'number': 245, 'to': gh_task.READY_STATUS, 'from': gh_task.PENDING_STATUS},
                ], f'残っている控えを読んで動かさなかった: {plan}'
                # 実際の経路（--json と書く側）も通す。
                gh_task.run_gh = make_command_gh([feature, child])
                with redirect_stdout(io.StringIO()):
                    assert gh_task.cmd_align(as_json=True) == 0
                    assert gh_task.cmd_align() == 0
                with open(leftover, encoding='utf-8') as f:
                    assert f.read() == old_body, '残っている控えを書き換えた'
                added = [n for n in os.listdir(shared) if n.startswith('gh-align-seen') and n not in before]
                assert added == [], f'控えの横にファイルが増えた: {added}'
            finally:
                if saved_root is None:
                    os.environ.pop('HIRAI_TASK_ROOT', None)
                else:
                    os.environ['HIRAI_TASK_ROOT'] = saved_root
            assert not hasattr(gh_task, 'ALIGN_SEEN_CACHE'), '控えの定数が残っている'
            assert not hasattr(gh_task, 'LATE_ADD_PREFIX'), '「後から追加」の定数が残っている'

        t(
            'align は 2.1.0 が置いていた場所の gh-align-seen.json を読まず・書かず・消さず、横に増やさない（定数も残さない）',
            _align_does_not_read_or_write_align_seen_file,
        )

        def _since_cache_keeps_other_namespaces() -> None:
            # 共有の since の控えは、repo ごとの名前空間を分ける（ほかの名前空間を捨てない）。
            path = gh_task.COMMENTS_SINCE_CACHE
            other = 'other-org/other-repo'
            gh_task._save_shared_json(path, {other: {'since': 'X'}})
            try:
                gh_task._save_since_cache(path, gh_task.REPO, 'Y')
                assert set(gh_task._load_shared_json(path)) == {other, gh_task.REPO}
                assert gh_task._load_since_cache(path, gh_task.REPO) == 'Y'
                assert gh_task._load_since_cache(path, other) == 'X'
            finally:
                os.remove(path)

        t('since の控えは、ほかの repo の名前空間を残して書く', _since_cache_keeps_other_namespaces)

        def _shared_json_load_warns_on_corrupt_file_and_treats_as_empty() -> None:
            broken = os.path.join(cache_tmp_dir, 'gh-broken-shared.json')
            with open(broken, 'w', encoding='utf-8') as f:
                f.write('{not valid json')
            data = gh_task._load_shared_json(broken)
            assert data == {}, f'壊れたファイルを空以外に読んだ: {data}'
            os.remove(broken)

        t(
            '_load_shared_json は壊れたファイルを黒に飲まず、警告して空に倒す'.replace('黒に飲まず', '黙って飲まず'),
            _shared_json_load_warns_on_corrupt_file_and_treats_as_empty,
        )

        def _align_never_touches_non_pending_children() -> None:
            items = [
                {
                    'number': 250, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 'F', 'parent_number': None,
                },
                {
                    'number': 251, 'type': 'Issue', 'kind': 'task', 'status': gh_task.JUDGMENT_STATUS,
                    'state': 'OPEN', 'title': 'judgement', 'parent_number': 250,
                },
                {
                    'number': 252, 'type': 'Issue', 'kind': 'task', 'status': gh_task.DEP_STATUS,
                    'state': 'OPEN', 'title': 'dep', 'parent_number': 250,
                },
                {
                    'number': 253, 'type': 'Issue', 'kind': 'task', 'status': gh_task.HOLD_STATUS,
                    'state': 'OPEN', 'title': 'hold', 'parent_number': 250,
                },
            ]
            plan = gh_task.align_plan(items, {}, {})
            entry = plan['align'][0] if plan['align'] else None
            touched: set[int] = set()
            if entry:
                touched |= {m['number'] for m in entry['moves']} | set(entry['skipped'])
            assert not (touched & {251, 252, 253}), f'判断待ち・依存待ち・保留の子に触れた: {touched}'

        t('align は判断待ち・依存待ち・保留の子には触れない', _align_never_touches_non_pending_children)

        def _align_crosses_wave_gate_and_records_waived() -> None:
            items = [
                {
                    'number': 260, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'OPEN',
                    'title': 'P1', 'parent_number': None,
                },
                {
                    'number': 261, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'OPEN',
                    'title': 'P2', 'parent_number': None,
                },
                {
                    'number': 262, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 'F', 'parent_number': 261,
                },
                {
                    'number': 263, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 262,
                },
            ]
            extras = {263: {'blocked_by_open': 0}, 261: {'blocked_by_open_numbers': [260]}}
            plan = gh_task.align_plan(items, extras, {})
            entry = plan['align'][0]
            assert entry['moves'] == [
                {'number': 263, 'to': gh_task.READY_STATUS, 'from': gh_task.PENDING_STATUS},
            ], f'feature が着手可なのに、先の wave が未了で依存待ちへ動かした: {entry}'
            assert entry['wave_waived'] == [260], f'通した wave の番号が載っていない: {entry}'
            out = io.StringIO()
            with redirect_stdout(out):
                gh_task._print_align_plan(plan)
            printed = out.getvalue().splitlines()
            note_line = '  先の wave #260 が出ていないが feature #262 が着手可なので通した'
            assert note_line in printed, out.getvalue()
            assert printed.index(note_line) == 1 and printed[0].startswith('feature #262:'), (
                f'通した 1 行は feature の見出しの直後に出す: {printed}')
            # 着手可の子は先の wave が未了でも依存待ちへ動かさない（何も動かさないので plan にも出ない）
            ready_items = [dict(i, status=gh_task.READY_STATUS) if i['number'] == 263 else i for i in items]
            assert gh_task.align_plan(ready_items, extras, {}) == {'align': []}, '着手可の子を先の wave で依存待ちへ動かした'
            # 先の wave が出た盤面では、「出ていないが通した」と書かない（出た側の退行を見る）
            exited_body = {260: '- 出る条件のコマンド: exit 0（2026-09-30・abc1234）'}
            exited_items = items + [
                {'number': 264, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                 'state': 'OPEN', 'title': 'F0', 'parent_number': 260},
                {'number': 265, 'type': 'Issue', 'kind': 'task', 'status': gh_task.DONE_STATUS,
                 'state': 'CLOSED', 'title': 't0', 'parent_number': 264},
            ]
            exited = gh_task.align_plan(exited_items, extras, exited_body)['align'][0]
            assert exited['moves'][0]['to'] == gh_task.READY_STATUS and 'wave_waived' not in exited, (
                f'P1 が出たのに wave_waived を載せた: {exited}')
            # 止める wave が無いときは wave_waived を載せない
            plain = gh_task.align_plan(items, {263: {'blocked_by_open': 0}}, {})['align'][0]
            assert 'wave_waived' not in plain, plain
            # 子に blocked by があれば今までどおり依存待ち（wave_waived は着手可へ動かした分があるときだけ）
            blocked = gh_task.align_plan(items, {263: {'blocked_by_open': 1}, 261: {'blocked_by_open_numbers': [260]}}, {})['align'][0]
            assert blocked['moves'][0]['to'] == gh_task.DEP_STATUS and 'wave_waived' not in blocked, blocked
            # 親の feature が承認待ちなら align の対象外（承認待ちの feature の子は自動で着手可にしない）
            pending = [dict(i, status=gh_task.PENDING_STATUS) if i['number'] == 262 else i for i in items]
            assert gh_task.align_plan(pending, extras, {}) == {'align': []}, '承認待ちの feature の子を動かした'

        t('align は先の wave（P1）が未了でも、着手可の feature の子を着手可へ動かし wave_waived を載せる', _align_crosses_wave_gate_and_records_waived)

        # 「未完了の blocked by があれば依存待ちへ（着手可の子も同じ。先の wave は見ない・ADR-0760）」を、
        # 着手可の子にも適用する。
        def _align_moves_blocked_ready_child_to_dependency_wait() -> None:
            items = [
                {
                    'number': 270, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 'F', 'parent_number': None,
                },
                {
                    'number': 271, 'type': 'Issue', 'kind': 'task', 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 270,
                },
            ]
            extras = {271: {'blocked_by_open': 1}}
            plan = gh_task.align_plan(items, extras, {})
            entry = plan['align'][0]
            assert entry['moves'] == [
                {'number': 271, 'to': gh_task.DEP_STATUS, 'from': gh_task.READY_STATUS},
            ], f'着手可の子に未完了の blocked by があるのに動かさなかった: {entry}'

        t(
            'align は未完了の blocked by がある着手可の子も依存待ちへ動かす'
            '',
            _align_moves_blocked_ready_child_to_dependency_wait,
        )

        def _align_leaves_unblocked_ready_child_untouched() -> None:
            items = [
                {
                    'number': 272, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 'F', 'parent_number': None,
                },
                {
                    'number': 273, 'type': 'Issue', 'kind': 'task', 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 272,
                },
            ]
            extras = {273: {'blocked_by_open': 0}}
            plan = gh_task.align_plan(items, extras, {})
            entry = plan['align'][0] if plan['align'] else None
            touched = set()
            if entry:
                touched = {m['number'] for m in entry['moves']} | set(entry['skipped'])
            assert 273 not in touched, f'ブロックされていない着手可の子に触れた（着手可→着手可）: {entry}'

        t('align はブロックされていない着手可の子には触れない（着手可→着手可は出さない）', _align_leaves_unblocked_ready_child_untouched)

        def _align_moves_pending_child_when_feature_itself_blocked() -> None:
            # feature 自身の未完了の blocked by も見る
            # （unblocked と条件をそろえる）。
            items = [
                {
                    'number': 280, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 'F', 'parent_number': None,
                },
                {
                    'number': 281, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 280,
                },
            ]
            extras = {280: {'blocked_by_open': 1}, 281: {'blocked_by_open': 0}}
            plan = gh_task.align_plan(items, extras, {})
            entry = plan['align'][0]
            assert entry['moves'] == [
                {'number': 281, 'to': gh_task.DEP_STATUS, 'from': gh_task.PENDING_STATUS},
            ], f'feature 自身の blocked by を見ずに着手可へ動かした: {entry}'

        t(
            'align は feature 自身に未完了の blocked by があれば、子（自身は未ブロック）も依存待ちへ動かす',
            _align_moves_pending_child_when_feature_itself_blocked,
        )

        def _align_marked_ready_child_is_skipped_not_moved() -> None:
            items = [
                {
                    'number': 290, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 'F', 'parent_number': None,
                },
                {
                    'number': 291, 'type': 'Issue', 'kind': 'task', 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': '[操作] t', 'parent_number': 290,
                },
            ]
            extras = {291: {'blocked_by_open': 1}}
            plan = gh_task.align_plan(items, extras, {})
            entry = plan['align'][0]
            assert entry['moves'] == [], f'目印つきの着手可の子を動かした: {entry}'
            assert entry['skipped'] == [291], entry

        t('align は目印つきの着手可の子も動かさず、番号だけを出す', _align_marked_ready_child_is_skipped_not_moved)

        # ── wave-holds ────────────────────────────────────
        def _wave_has_exited_needs_both_conditions() -> None:
            items = [
                {
                    'number': 300, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'OPEN',
                    'title': 'P1', 'parent_number': None,
                },
                {
                    'number': 301, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.DONE_STATUS,
                    'state': 'CLOSED', 'title': 'F', 'parent_number': 300,
                },
                {
                    'number': 302, 'type': 'Issue', 'kind': 'task', 'status': gh_task.DONE_STATUS,
                    'state': 'CLOSED', 'title': 't', 'parent_number': 301,
                },
            ]
            items_by_number, children_of = gh_task._board_index(items)
            met, has_line = gh_task.wave_has_exited(300, items_by_number, children_of, {})
            assert met is True, '子孫が全部完了なのに子の条件を満たしていない'
            assert has_line is False, '出る条件のコマンドの行を書いていないのに読めてしまった'
            met2, has_line2 = gh_task.wave_has_exited(
                300, items_by_number, children_of,
                {300: '- 出る条件のコマンド: exit 0（2026-09-28・abc1234）\n'},
            )
            assert met2 is True and has_line2 is True, '出る条件のコマンドの行があるのに読めない'

        t('wave_has_exited は子の条件とコマンドの行の両方を見る', _wave_has_exited_needs_both_conditions)

        def _wave_has_exited_treats_empty_wave_as_not_met() -> None:
            # 子孫が 0 件（できたばかりの空の wave）を、子の条件を
            # 満たしたと vacuous に数えない。
            items = [{
                'number': 305, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'OPEN',
                'title': 'P3', 'parent_number': None,
            }]
            items_by_number, children_of = gh_task._board_index(items)
            met, has_line = gh_task.wave_has_exited(
                305, items_by_number, children_of,
                {305: '- 出る条件のコマンド: exit 0（2026-09-28・abc1234）\n'},
            )
            assert met is False, '子が 0 件の wave を「子の条件を満たした」と数えた'

        t(
            'wave_has_exited は子孫 0 件の wave を「子の条件を満たした」に数えない',
            _wave_has_exited_treats_empty_wave_as_not_met,
        )

        def _wave_has_exited_counts_only_tasks_not_feature_rows() -> None:
            # #521: feature は子が全部閉じたときにしか閉じない。保留の task だけを持つ
            # feature（承認待ち・着手可のまま）を子に持つ wave も、コマンドの行があれば出る。
            line = {310: '- 出る条件のコマンド: exit 0（2026-09-29・abc1234）\n'}
            for feature_status in (gh_task.PENDING_STATUS, gh_task.READY_STATUS):
                items = [
                    {'number': 310, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'OPEN',
                     'title': 'W1', 'parent_number': None},
                    {'number': 311, 'type': 'Issue', 'kind': gh_task.FEATURE_KIND,
                     'status': feature_status, 'state': 'OPEN', 'title': 'F', 'parent_number': 310},
                    {'number': 312, 'type': 'Issue', 'kind': 'task', 'status': gh_task.HOLD_STATUS,
                     'state': 'OPEN', 'title': 't', 'parent_number': 311},
                ]
                by_number, children_of = gh_task._board_index(items)
                met, has_line = gh_task.wave_has_exited(310, by_number, children_of, line)
                assert met is True and has_line is True, (
                    f'保留の task だけを持つ feature（{feature_status}）のせいで出たにならない'
                )

        t(
            'wave_has_exited は保留の task だけを持つ feature を子に持つ wave を、行があれば出たと読む（#521）',
            _wave_has_exited_counts_only_tasks_not_feature_rows,
        )

        def _wave_has_exited_open_task_under_pending_feature_blocks() -> None:
            line = {320: '- 出る条件のコマンド: exit 0（2026-09-29・abc1234）\n'}
            items = [
                {'number': 320, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'OPEN',
                 'title': 'W1', 'parent_number': None},
                {'number': 321, 'type': 'Issue', 'kind': gh_task.FEATURE_KIND,
                 'status': gh_task.PENDING_STATUS, 'state': 'OPEN', 'title': 'F', 'parent_number': 320},
                {'number': 322, 'type': 'Issue', 'kind': 'task', 'status': gh_task.HOLD_STATUS,
                 'state': 'OPEN', 'title': 't', 'parent_number': 321},
                # 種別が空でも task とみなす（§8-1）。この行が未完了なので wave は出ない
                {'number': 323, 'type': 'Issue', 'kind': '', 'status': gh_task.READY_STATUS,
                 'state': 'OPEN', 'title': 't2', 'parent_number': 321},
            ]
            by_number, children_of = gh_task._board_index(items)
            met, _has_line = gh_task.wave_has_exited(320, by_number, children_of, line)
            assert met is False, '承認待ちの feature の下に未完了の task があるのに出た扱い'

        t(
            'wave_has_exited は承認待ちの feature の下に未完了の task があれば出ない（#521）',
            _wave_has_exited_open_task_under_pending_feature_blocks,
        )

        def _feature_under_wave_items(wave: int) -> list[dict]:
            # wave → feature（承認待ち）→ 保留の task（#521 の実物の形）
            return [
                {'number': wave, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'OPEN',
                 'title': 'W1', 'parent_number': None},
                {'number': wave + 1, 'type': 'Issue', 'kind': gh_task.FEATURE_KIND,
                 'status': gh_task.PENDING_STATUS, 'state': 'OPEN', 'title': 'F',
                 'parent_number': wave},
                {'number': wave + 2, 'type': 'Issue', 'kind': 'task', 'status': gh_task.HOLD_STATUS,
                 'state': 'OPEN', 'title': 't', 'parent_number': wave + 1},
            ]

        def _unblocked_after_wave_with_pending_feature_of_hold_tasks() -> None:
            items = _feature_under_wave_items(330) + [
                {'number': 340, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'OPEN',
                 'title': 'W2', 'parent_number': None},
                {'number': 341, 'type': 'Issue', 'kind': gh_task.FEATURE_KIND,
                 'status': gh_task.READY_STATUS, 'state': 'OPEN', 'title': 'F2',
                 'parent_number': 340},
                {'number': 342, 'type': 'Issue', 'kind': 'task', 'status': gh_task.DEP_STATUS,
                 'state': 'OPEN', 'title': 't2', 'parent_number': 341},
            ]
            extras = {
                342: {'blocked_by_open': 0}, 341: {'blocked_by_open': 0},
                340: {'blocked_by_open_numbers': [330]},
            }
            bodies = {330: '- 出る条件のコマンド: exit 0（2026-09-29・abc1234）\n'}
            # 親の feature が着手可: W1 が出ていても出ていなくても出る。出たときは note を付けない
            rows = gh_task.unblocked_rows(items, extras, bodies)
            assert [r['number'] for r in rows] == [342] and 'note' not in rows[0], (
                f'W1 が出たのに「出ていないが通した」と書いた（#521）: {rows}'
            )
            assert 'note' in gh_task.unblocked_rows(items, extras, {})[0], 'W1 が未了なのに「通した」の note が無い'
            # 親の feature が承認待ち: 門が残る。W1 が出たら承認待ちへ戻し、出ていなければ待つ（#521）
            pending = [dict(i, status=gh_task.PENDING_STATUS) if i['number'] == 341 else i for i in items]
            rows = gh_task.unblocked_rows(pending, extras, bodies)
            assert rows == [{'number': 342, 'title': 't2', 'set_status': gh_task.PENDING_STATUS}], (
                f'保留の task だけの feature を挟む W1 が出たのに、承認待ちの W2 の子が承認待ちへ戻らない（#521）: {rows}'
            )
            assert gh_task.unblocked_rows(pending, extras, {}) == [], '承認待ちの feature の子が、W1 が未了のまま出た'
            # Status が空の feature の子は、W1 が未了なら出ない
            empty = [dict(i, status='') if i['number'] == 341 else i for i in items]
            assert gh_task.unblocked_rows(empty, extras, {}) == [], 'Status が空の feature の子が門を越えた'
            # 親が wave 直下の task（feature でない）は、W1 が未了なら出ない
            # （wave → task → task の入れ子。親が feature でないので、先の wave が未了なら出さない）
            under_task = [i for i in items if i['number'] not in (341, 342)] + [
                {'number': 343, 'type': 'Issue', 'kind': 'task', 'status': gh_task.IN_PROGRESS_STATUS,
                 'state': 'OPEN', 'title': 'p', 'parent_number': 340},
                {'number': 342, 'type': 'Issue', 'kind': 'task', 'status': gh_task.DEP_STATUS,
                 'state': 'OPEN', 'title': 't2', 'parent_number': 343},
            ]
            assert gh_task.unblocked_rows(under_task, extras, {}) == [], '親が feature でない task が門を越えた'
            assert [r['number'] for r in gh_task.unblocked_rows(under_task, extras, bodies)] == [342], (
                'W1 が出たのに、親が feature でない task が出ない')
            # 親の task が着手可でも、feature でなければ門を越えない（feature の判定を外す退行を捕まえる）
            ready_parent = [dict(i, status=gh_task.READY_STATUS) if i['number'] == 343 else i for i in under_task]
            assert gh_task.unblocked_rows(ready_parent, extras, {}) == [], '着手可の task（feature でない）の子が門を越えた'
            # Status が空の feature の子: W1 が出ていれば出るが、戻し先は人の判断（set が断る「着手可」を出さない）
            assert gh_task.unblocked_rows(empty, extras, bodies) == [{
                'number': 342, 'title': 't2', 'set_status': None,
                'note': '親の feature の Status が空。人が判断する',
            }], gh_task.unblocked_rows(empty, extras, bodies)

        t(
            'unblocked は、承認待ちの feature の下が保留の task だけの wave が出たら、次の wave の子を出す（#521）。門は承認待ち・Status 空・feature でない親に残る',
            _unblocked_after_wave_with_pending_feature_of_hold_tasks,
        )

        def _wave_hold_rows_sees_wave_with_pending_feature_of_hold_tasks() -> None:
            items = _feature_under_wave_items(350)
            lines = gh_task.wave_hold_rows(items, {})
            assert any('#350' in x for x in lines), (
                f'承認待ちの feature を挟む W1 の子の条件が満たされているのに wave-holds に出ない（#521）: {lines}'
            )

        t(
            'wave-holds は、承認待ちの feature の下が保留の task だけの wave も、行が無ければ出す（#521）',
            _wave_hold_rows_sees_wave_with_pending_feature_of_hold_tasks,
        )

        def _unresolved_wave_numbers_closed_wave_without_line_still_blocks() -> None:
            # 閉じた P1 でも、「出る条件のコマンド」の行が無ければ
            # 未了のまま。以前は blocked_by_open_numbers（open だけ）で見ており、閉じた
            # wave を無条件に「止めていない」と読んでいた。
            items = [
                {
                    'number': 320, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'CLOSED',
                    'title': 'P1', 'parent_number': None,
                },
                {
                    'number': 321, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'OPEN',
                    'title': 'P2', 'parent_number': None,
                },
            ]
            items_by_number, children_of = gh_task._board_index(items)
            extras = {321: {'blocked_by_open_numbers': [], 'blocked_by_numbers': [320]}}
            unresolved = gh_task.unresolved_wave_numbers(
                321, items_by_number, children_of, {}, extras,
            )
            assert unresolved == [320], (
                '閉じた P1 に行が無いのに、P2 を止めていないと判定した'
            )

        t(
            'unresolved_wave_numbers は、閉じた先の wave でも行が無ければ未了のまま扱う',
            _unresolved_wave_numbers_closed_wave_without_line_still_blocks,
        )

        def _wave_hold_rows_flags_missing_command_line() -> None:
            items = [
                {
                    'number': 310, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'OPEN',
                    'title': 'P1', 'parent_number': None,
                },
                {
                    'number': 311, 'type': 'Issue', 'kind': 'task', 'status': gh_task.HOLD_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 310,
                },
            ]
            lines = gh_task.wave_hold_rows(items, {})
            assert any('#310' in line for line in lines), (
                f'子の条件を満たした wave が wave-holds に出ていない: {lines}'
            )
            lines2 = gh_task.wave_hold_rows(
                items, {310: '- 出る条件のコマンド: exit 0（2026-09-28・abc1234）\n'},
            )
            assert lines2 == [], f'コマンドの行があるのに wave-holds に出た: {lines2}'

        t(
            'wave-holds は、子の条件を満たしコマンドの行が無い wave だけに出る',
            _wave_hold_rows_flags_missing_command_line,
        )

        def _design_pr_by_marker_or_kind() -> None:
            # 設計の PR は、本文の印か「種別: 設計・決定の文書」の行で見分ける（文の中の語だけでは数えない）。
            for body, want in (
                (f'<!-- {gh_task.DESIGN_PR_MARKER} -->\n本文', True),
                ('種別: 設計・決定の文書\n利用者への影響: NONE\n', True),
                ('<!-- x -->\n\n種別：「設計・決定の文書」\n', True),
                ('種別: 見えない変更\n\n設計・決定の文書 の直しを含む\n', False),
                ('- 設計・決定の文書: 設計・ADR の PR\n\n種別:\n', False),
                ('', False),
            ):
                assert gh_task.is_design_pr(body) is want, f'{body!r} の見分けが {want} でない'

        t('設計の PR は、本文の印か「種別: 設計・決定の文書」の行で見分ける', _design_pr_by_marker_or_kind)

        def _merged_designs_follow_the_default_branch() -> None:
            # 既定の branch が stg のとき、stg へ merge した設計 PR を拾う（rmp-app の #873）。
            import contextlib
            design = {
                'number': 901, 'title': '設計', 'merged_at': '2999-01-01T00:00:00Z',
                'body': f'<!-- {gh_task.DESIGN_PR_MARKER} -->\n本文',
            }
            calls: list[str] = []

            def make_fake(default_branch_rc: int):
                def fake(args, input_text=None):
                    path = args[3] if len(args) > 3 and args[0] == 'api' else ''
                    calls.append(path)
                    if path == f'repos/{gh_task.REPO}':
                        if default_branch_rc:
                            return default_branch_rc, '', 'boom'
                        return 0, json.dumps({'default_branch': 'stg'}), ''
                    if '/pulls?' in path:
                        # base を付けたときは、その branch へ merge した PR だけを返す。
                        if 'base=main' in path:
                            return 0, '[]', ''
                        return 0, json.dumps([design]), ''
                    return 1, '', f'unhandled: {path}'
                return fake

            orig = gh_task.run_gh
            try:
                gh_task.run_gh = make_fake(0)
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rows, _ = gh_task.merged_design_rows('2000-01-01T00:00:00Z')
                assert [r['number'] for r in rows] == [901], f'stg の設計 PR を拾えない: {rows}'
                assert any('base=stg' in c for c in calls), f'base=stg で引いていない: {calls}'
                assert sum(1 for c in calls if c == f'repos/{gh_task.REPO}') == 1, calls
                # 引けなかったときは base を付けずに引き、1 行出す。
                calls.clear()
                gh_task.run_gh = make_fake(1)
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rows, _ = gh_task.merged_design_rows('2000-01-01T00:00:00Z')
                assert [r['number'] for r in rows] == [901], f'引けないときに PR を拾えない: {rows}'
                assert not any('base=' in c for c in calls), f'base= を付けて引いた: {calls}'
                assert len([ln for ln in buf.getvalue().splitlines() if ln.strip()]) == 1, buf.getvalue()
            finally:
                gh_task.run_gh = orig

        t(
            'default_branch が stg のとき、stg へ merge した設計 PR を拾う（引けなければ base を付けずに引いて 1 行出す）',
            _merged_designs_follow_the_default_branch,
        )

        def _wave_with_human_judgment_line_is_not_held_nor_exited() -> None:
            # 出る条件が人の判断で回す命令が無い wave（rmp-app の #796）。
            human_line = '- 出る条件のコマンド: なし（人の判断）\n'
            items = [
                {
                    'number': 330, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'OPEN',
                    'title': 'P1', 'parent_number': None,
                },
                {
                    'number': 331, 'type': 'Issue', 'kind': 'task', 'status': gh_task.HOLD_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 330,
                },
                {
                    'number': 332, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'OPEN',
                    'title': 'P2', 'parent_number': None,
                },
            ]
            lines = gh_task.wave_hold_rows(items, {330: human_line})
            assert lines == [], f'人の判断の行を持つ wave が wave-holds に出た: {lines}'
            items_by_number, children_of = gh_task._board_index(items)
            met, has_line = gh_task.wave_has_exited(330, items_by_number, children_of, {330: human_line})
            assert met is True and has_line is False, (
                f'人の判断の行を「出た」と数えた: met={met} has_line={has_line}'
            )
            extras = {332: {'blocked_by_open_numbers': [], 'blocked_by_numbers': [330]}}
            assert gh_task.unresolved_wave_numbers(
                332, items_by_number, children_of, {330: human_line}, extras,
            ) == [330], '人の判断の行を持つ先の wave が、後続を止めなくなった'
            # 行が無い wave は、従来どおり wave-holds に出る。
            assert any('#330' in line for line in gh_task.wave_hold_rows(items, {})), (
                '行が無い wave が wave-holds に出なくなった'
            )

        t(
            '人の判断の行を持つ wave は wave-holds に出ず、出たとも数えない',
            _wave_with_human_judgment_line_is_not_held_nor_exited,
        )

        def _wave_hold_rows_ignores_closed_and_empty_waves() -> None:
            items = [
                {
                    'number': 312, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'CLOSED',
                    'title': 'P2 閉じた', 'parent_number': None,
                },
                {
                    'number': 313, 'type': 'Issue', 'kind': 'task', 'status': gh_task.HOLD_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 312,
                },
                {
                    'number': 314, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'OPEN',
                    'title': 'P3 新しい・子なし', 'parent_number': None,
                },
            ]
            lines = gh_task.wave_hold_rows(items, {})
            assert lines == [], (
                f'閉じた wave・子 0 件の新しい wave が wave-holds に出た: {lines}'
            )

        t(
            'wave-holds は閉じた wave と子 0 件の新しい wave を出さない',
            _wave_hold_rows_ignores_closed_and_empty_waves,
        )

        # ── orphans・stuck ────────────────────────────────────────
        def _orphan_rows_excludes_wave_and_design_memo() -> None:
            items = [
                {
                    'number': 400, 'type': 'Issue', 'kind': gh_task.WAVE_KIND, 'title': 'P1',
                    'parent_number': None, 'state': 'OPEN',
                },
                {
                    'number': 401, 'type': 'Issue', 'kind': gh_task.DESIGN_MEMO_KIND, 'title': 'memo',
                    'parent_number': None, 'state': 'OPEN',
                },
                {
                    'number': 402, 'type': 'Issue', 'kind': 'task', 'title': 'orphan task',
                    'parent_number': None, 'state': 'OPEN',
                },
                {
                    'number': 403, 'type': 'Issue', 'kind': '', 'title': 'no kind',
                    'parent_number': 1, 'state': 'OPEN',
                },
                {
                    'number': 404, 'type': 'Issue', 'kind': '', 'title': 'closed no kind',
                    'parent_number': 1, 'state': 'CLOSED',
                },
            ]
            rows = gh_task.orphan_rows(items)
            numbers = {r['number'] for r in rows}
            assert 400 not in numbers and 401 not in numbers, f'wave・設計メモを親なしに数えた: {rows}'
            assert 402 in numbers, f'親なしの task を見落とした: {rows}'
            assert 403 in numbers, f'種別なしの行を見落とした: {rows}'
            assert 404 not in numbers, f'CLOSED の種別なしの行を数えた: {rows}'

        t(
            'orphans は wave・設計メモの親なしと CLOSED の行を数えない（task・feature の OPEN・親なしだけ数える）',
            _orphan_rows_excludes_wave_and_design_memo,
        )

        def _stuck_includes_ready_child_of_pending_feature() -> None:
            items = [
                {
                    'number': 410, 'type': 'Issue', 'kind': gh_task.FEATURE_KIND,
                    'status': gh_task.PENDING_STATUS, 'state': 'OPEN', 'title': 'F',
                    'parent_number': None,
                },
                {
                    'number': 411, 'type': 'Issue', 'kind': 'task', 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 410,
                },
            ]
            lines = gh_task.stuck_rows(items, {})
            assert any('#411' in line and '承認待ち' in line for line in lines), lines

        t('stuck は、着手可なのに親の feature が承認待ちの task を出す', _stuck_includes_ready_child_of_pending_feature)

        # ── comments ─────────────────────────────────────
        def _comments_filters_ai_marker() -> None:
            def fake(args: list[str], input_text: str | None = None) -> tuple[int, str, str]:
                assert '--paginate' in args, f'頁送りを使っていない: {args}'
                comments = [
                    {
                        'issue_url': 'https://api.github.com/repos/o/r/issues/12',
                        'user': {'login': 'thirai'}, 'body': '人のコメント',
                    },
                    {
                        'issue_url': 'https://api.github.com/repos/o/r/issues/13',
                        'user': {'login': 'bot'}, 'body': f'{gh_task.AI_MARKER}\nAI のコメント',
                    },
                ]
                return 0, json.dumps(comments), ''

            gh_task.run_gh = fake
            picked, since = gh_task.fetch_user_comments(None)
            assert len(picked) == 1, f'AI_MARKER 付きも拾ってしまった: {picked}'
            assert picked[0]['issue_url'].endswith('/12'), picked
            assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$', since), f'since の形が違う: {since}'

        t('comments は AI_MARKER 付きのコメントを拾わない', _comments_filters_ai_marker)

        # ── 「- today は書かない: はい」 ─────────────
        def _no_today_marker_gates_writes_when_enabled() -> None:
            items = [
                {'number': 500, 'type': 'Issue', 'title': '[操作] 一括のそろえと戻し', 'state': 'OPEN'},
            ]
            orig_flag = gh_task.MIGRATION_ALIGN_WRITE_ENABLED
            gh_task.MIGRATION_ALIGN_WRITE_ENABLED = True
            try:
                def fake_with_marker(args: list[str], input_text: str | None = None):
                    joined = ' '.join(args)
                    numbers = [int(n) for n in re.findall(r'issue\(number:\s*(\d+)\)', joined)]
                    data = {
                        f'i{i}': {'issue': {'number': n, 'body': gh_task.NO_TODAY_MARK}}
                        for i, n in enumerate(numbers)
                    }
                    return 0, json.dumps({'data': data}), ''

                gh_task.run_gh = fake_with_marker
                assert gh_task.no_today_marker_open(items) is True
                assert gh_task.align_write_allowed(items) is False, '目印があるのに書き込みを許した'

                def fake_without_marker(args: list[str], input_text: str | None = None):
                    joined = ' '.join(args)
                    numbers = [int(n) for n in re.findall(r'issue\(number:\s*(\d+)\)', joined)]
                    data = {
                        f'i{i}': {'issue': {'number': n, 'body': '本文'}}
                        for i, n in enumerate(numbers)
                    }
                    return 0, json.dumps({'data': data}), ''

                gh_task.run_gh = fake_without_marker
                assert gh_task.no_today_marker_open(items) is False
                assert gh_task.align_write_allowed(items) is True, '目印を外したのに書き込みを許さない'
            finally:
                gh_task.MIGRATION_ALIGN_WRITE_ENABLED = orig_flag

        t(
            '「- today は書かない: はい」がある間は書き込みを許さず、外すと許す',
            _no_today_marker_gates_writes_when_enabled,
        )

        def _no_today_marker_is_not_gated_by_title() -> None:
            # 題名に `[操作]` が無い open issue の本文にも
            # 目印があれば拾う（以前は題名で絞っており、これが fail-open だった）。
            items = [
                {'number': 501, 'type': 'Issue', 'title': 'ふつうの task', 'state': 'OPEN'},
                {'number': 502, 'type': 'PullRequest', 'title': 'PR は見ない', 'state': 'OPEN'},
                {'number': 503, 'type': 'Issue', 'title': '閉じた行は見ない', 'state': 'CLOSED'},
            ]

            def fake(args: list[str], input_text: str | None = None):
                joined = ' '.join(args)
                numbers = [int(n) for n in re.findall(r'issue\(number:\s*(\d+)\)', joined)]
                assert numbers == [501], f'PR・CLOSED まで問い合わせた: {numbers}'
                data = {
                    f'i{i}': {'issue': {'number': n, 'body': gh_task.NO_TODAY_MARK}}
                    for i, n in enumerate(numbers)
                }
                return 0, json.dumps({'data': data}), ''

            gh_task.run_gh = fake
            assert gh_task.no_today_marker_open(items) is True, (
                '題名に [操作] が無い open issue の目印を読み落とした（fail-open の再発）'
            )

        t(
            'no_today_marker_open は題名を絞らず、open の Issue 全体の本文を見る',
            _no_today_marker_is_not_gated_by_title,
        )

        def _write_switch_is_on_after_1_8a() -> None:
            # MIGRATION_ALIGN_WRITE_ENABLED は既定で True。
            # 「- today は書かない: はい」が無ければ書き込みを許し、False にすると許さない。
            items = [{'number': 501, 'title': 'ふつうの task', 'state': 'OPEN', 'type': 'Issue'}]
            assert gh_task.MIGRATION_ALIGN_WRITE_ENABLED is True, '既定は True のはず'
            gh_task.run_gh = make_command_gh(items, bodies={501: '本文'})
            assert gh_task.align_write_allowed(items) is True
            orig_flag = gh_task.MIGRATION_ALIGN_WRITE_ENABLED
            gh_task.MIGRATION_ALIGN_WRITE_ENABLED = False
            try:
                assert gh_task.align_write_allowed(items) is False
            finally:
                gh_task.MIGRATION_ALIGN_WRITE_ENABLED = orig_flag

        t(
            'MIGRATION_ALIGN_WRITE_ENABLED は True で、False にすると align・close-parents が書かない',
            _write_switch_is_on_after_1_8a,
        )

        # ── #516: not planned で閉じた子も「閉じた」に数える ──
        def _close_parents_counts_not_planned_child_as_closed() -> None:
            items = [{
                'number': 650, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                'state': 'OPEN', 'title': 'F', 'parent_number': None,
            }]
            # 本番の実測（not planned の子は completed に数えない）から推した値。子 2 件がどちらも閉じていれば summary は completed 1・total 2 になる。判定は summary を読まず children の state だけで見る
            gh_task.run_gh = make_command_gh(
                items, summaries={650: {'total': 2, 'completed': 1}},
                children={650: [
                    {'number': 6501, 'state': 'closed', 'state_reason': 'completed'},
                    {'number': 6502, 'state': 'closed', 'state_reason': 'not_planned'},
                ]},
            )
            out = io.StringIO()
            with redirect_stdout(out):
                rc = gh_task.main(['close-parents', '--json'])
            assert rc == 0
            plan = json.loads(out.getvalue())
            assert plan['close_parents'] == [
                {'number': 650, 'kind': 'feature', 'children_total': 2},
            ], f'not planned の子を閉じた数に入れていない: {plan}'

        t(
            'close-parents は not planned で閉じた子も閉じた数に入れ、全部閉じた feature を候補にする（#516）',
            _close_parents_counts_not_planned_child_as_closed,
        )

        def _close_parents_keeps_parent_with_open_child() -> None:
            items = [{
                'number': 651, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                'state': 'OPEN', 'title': 'F', 'parent_number': None,
            }]
            gh_task.run_gh = make_command_gh(items, children={651: [
                {'number': 6511, 'state': 'closed', 'state_reason': 'not_planned'},
                {'number': 6512, 'state': 'open', 'state_reason': None},
            ]})
            out = io.StringIO()
            with redirect_stdout(out):
                rc = gh_task.main(['close-parents', '--json'])
            assert rc == 0
            assert json.loads(out.getvalue())['close_parents'] == [], out.getvalue()

        t('close-parents は open の子が 1 件でも残る親を閉じない（#516）', _close_parents_keeps_parent_with_open_child)

        # ── main([...]) を実際に走らせる（書き込みの有無を見る） ──
        def _close_parents_command_lists_but_does_not_write_when_switch_off() -> None:
            items = [{
                'number': 600, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                'state': 'OPEN', 'title': 'F', 'parent_number': None,
            }]
            write_log: list[tuple] = []
            gh_task.run_gh = make_command_gh(
                items, summaries={600: {'total': 2, 'completed': 2}}, write_log=write_log,
            )
            orig_flag = gh_task.MIGRATION_ALIGN_WRITE_ENABLED
            gh_task.MIGRATION_ALIGN_WRITE_ENABLED = False
            try:
                out = io.StringIO()
                with redirect_stdout(out):
                    rc = gh_task.main(['close-parents'])
            finally:
                gh_task.MIGRATION_ALIGN_WRITE_ENABLED = orig_flag
            assert rc == 0
            assert '閉じる親 1 件' in out.getvalue()
            assert not any(op == 'PATCH' for op, *_ in write_log), (
                f'切り替えを切ったのに書き込んだ: {write_log}'
            )

        t(
            'close-parents は切り替え（MIGRATION_ALIGN_WRITE_ENABLED）を切ると一覧だけで、閉じる書き込みをしない',
            _close_parents_command_lists_but_does_not_write_when_switch_off,
        )

        def _close_parents_command_writes_when_enabled() -> None:
            items = [{
                'number': 601, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                'state': 'OPEN', 'title': 'F', 'parent_number': None,
            }]
            write_log: list[tuple] = []
            gh_task.run_gh = make_command_gh(
                items, summaries={601: {'total': 2, 'completed': 2}}, write_log=write_log,
            )
            orig_flag = gh_task.MIGRATION_ALIGN_WRITE_ENABLED
            gh_task.MIGRATION_ALIGN_WRITE_ENABLED = True
            try:
                rc = gh_task.main(['close-parents'])
            finally:
                gh_task.MIGRATION_ALIGN_WRITE_ENABLED = orig_flag
            assert rc == 0
            patches = [(op, path) for op, path, *_ in write_log if op == 'PATCH']
            assert patches == [('PATCH', f'repos/{gh_task.REPO}/issues/601')], (
                f'閉じる書き込みが無い: {write_log}'
            )

        t(
            'close-parents は許可があれば（MIGRATION_ALIGN_WRITE_ENABLED=True）実際に閉じる',
            _close_parents_command_writes_when_enabled,
        )

        def _close_parents_json_never_writes_even_when_enabled() -> None:
            # --json は 一括処理が読む dry-run 専用で、
            # 許可があっても書かない。
            items = [{
                'number': 602, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                'state': 'OPEN', 'title': 'F', 'parent_number': None,
            }]
            write_log: list[tuple] = []
            gh_task.run_gh = make_command_gh(
                items, summaries={602: {'total': 2, 'completed': 2}}, write_log=write_log,
            )
            orig_flag = gh_task.MIGRATION_ALIGN_WRITE_ENABLED
            gh_task.MIGRATION_ALIGN_WRITE_ENABLED = True
            try:
                out = io.StringIO()
                with redirect_stdout(out):
                    rc = gh_task.main(['close-parents', '--json'])
            finally:
                gh_task.MIGRATION_ALIGN_WRITE_ENABLED = orig_flag
            assert rc == 0
            assert json.loads(out.getvalue())['close_parents'] == [
                {'number': 602, 'kind': 'feature', 'children_total': 2},
            ]
            assert write_log == [], f'--json なのに書き込んだ: {write_log}'

        t(
            'close-parents --json は許可があっても書かない',
            _close_parents_json_never_writes_even_when_enabled,
        )

        def _align_json_never_writes_even_when_enabled() -> None:
            items = [
                {
                    'number': 622, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 'F', 'parent_number': None,
                },
                {
                    'number': 623, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 622,
                },
            ]
            write_log: list[tuple] = []
            gh_task.run_gh = make_command_gh(
                items, extras={623: {'blocked_by_open': 0}}, write_log=write_log,
            )
            orig_flag = gh_task.MIGRATION_ALIGN_WRITE_ENABLED
            gh_task.MIGRATION_ALIGN_WRITE_ENABLED = True
            try:
                out = io.StringIO()
                with redirect_stdout(out):
                    rc = gh_task.main(['align', '--json'])
            finally:
                gh_task.MIGRATION_ALIGN_WRITE_ENABLED = orig_flag
            assert rc == 0
            payload = json.loads(out.getvalue())
            assert payload['align'][0]['moves'] == [
                {'number': 623, 'to': gh_task.READY_STATUS, 'from': gh_task.PENDING_STATUS},
            ], payload
            assert write_log == [], f'--json なのに書き込んだ: {write_log}'

        t(
            'align --json は許可があっても書かない',
            _align_json_never_writes_even_when_enabled,
        )

        def _unblocked_command_never_writes() -> None:
            items = [
                {
                    'number': 610, 'type': 'Issue', 'kind': gh_task.FEATURE_KIND,
                    'status': gh_task.READY_STATUS, 'state': 'OPEN', 'title': 'F',
                    'parent_number': None,
                },
                {
                    'number': 611, 'type': 'Issue', 'kind': 'task', 'status': gh_task.DEP_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 610,
                },
            ]
            write_log: list[tuple] = []
            extras = {611: {'blocked_by_open': 0}, 610: {'blocked_by_open': 0}}
            gh_task.run_gh = make_command_gh(items, extras=extras, write_log=write_log)
            out = io.StringIO()
            with redirect_stdout(out):
                rc = gh_task.main(['unblocked'])
            assert rc == 0
            assert '#611' in out.getvalue()
            assert write_log == [], f'unblocked が書き込みの API を呼んだ: {write_log}'

        t('unblocked は一覧だけで、書き込みの API を呼ばない', _unblocked_command_never_writes)

        def _align_command_writes_when_enabled_and_leaves_comment() -> None:
            items = [
                {
                    'number': 620, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 'F', 'parent_number': None,
                },
                {
                    'number': 621, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 620,
                },
            ]
            write_log: list[tuple] = []
            gh_task.run_gh = make_command_gh(
                items, extras={621: {'blocked_by_open': 0}}, write_log=write_log,
            )
            orig_flag = gh_task.MIGRATION_ALIGN_WRITE_ENABLED
            gh_task.MIGRATION_ALIGN_WRITE_ENABLED = True
            try:
                rc = gh_task.main(['align'])
            finally:
                gh_task.MIGRATION_ALIGN_WRITE_ENABLED = orig_flag
            assert rc == 0
            updates = [e for e in write_log if e[0] == 'item-update']
            assert updates, f'着手可への書き込みが無い: {write_log}'
            assert not [e for e in write_log if e[0] == 'graphql-update'], (
                f'GraphQL の書き込みを呼んだ: {write_log}'
            )
            comments = [
                e for e in write_log if e[0] == 'POST' and e[1].endswith('/620/comments')
            ]
            assert comments, f'feature への 1 行コメントが無い: {write_log}'
            assert gh_task.AI_MARKER in (comments[0][2] or {}).get('body', ''), (
                'コメントに AI_MARKER が無い（comments が誤って拾ってしまう）'
            )

        t(
            'align は許可があれば実際に子を動かし、feature に AI_MARKER 付きコメントを残す',
            _align_command_writes_when_enabled_and_leaves_comment,
        )

        def _apply_align_plan_skips_when_status_changed() -> None:
            # 書き込みの合間（8.5 秒×N 件）に人が判断待ちへ動かした
            # ような子は、計画の from と今の Status が違うので上書きしない。
            items = [{
                'number': 700, 'type': 'Issue', 'kind': 'task', 'status': gh_task.JUDGMENT_STATUS,
                'state': 'OPEN', 'title': 't', 'parent_number': None,
            }]
            write_log: list[tuple] = []
            gh_task.run_gh = make_command_gh(items, write_log=write_log)
            plan = {'align': [{
                'feature': 999,
                'moves': [{'number': 700, 'to': gh_task.READY_STATUS, 'from': gh_task.PENDING_STATUS}],
                'skipped': [],
            }]}
            gh_task._apply_align_plan(7, plan)
            updates = [e for e in write_log if e[0] in ('item-update', 'graphql-update')]
            assert updates == [], f'今の Status が計画の from と違うのに書いた: {write_log}'
            comments = [e for e in write_log if e[0] == 'POST']
            assert comments and '想定' in (comments[0][2] or {}).get('body', ''), (
                f'飛ばした理由をコメントに残していない: {write_log}'
            )

        t(
            '_apply_align_plan は今の Status が計画の from と違えば書かず、理由を残す',
            _apply_align_plan_skips_when_status_changed,
        )

        def _apply_align_plan_records_waived_wave_in_comment() -> None:
            # 通した wave の 1 行は today の画面だけでなく、feature に残すコメントにも書く（issue に記録が残る）
            items = [{
                'number': 701, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                'state': 'OPEN', 'title': 't', 'parent_number': None,
            }]
            write_log: list[tuple] = []
            gh_task.run_gh = make_command_gh(items, write_log=write_log)
            plan = {'align': [{
                'feature': 998, 'wave_waived': [627, 709],
                'moves': [{'number': 701, 'to': gh_task.READY_STATUS, 'from': gh_task.PENDING_STATUS}],
                'skipped': [],
            }]}
            gh_task._apply_align_plan(7, plan)
            comments = [e for e in write_log if e[0] == 'POST']
            body = (comments[0][2] or {}).get('body', '') if comments else ''
            assert '先の wave #627・#709 が出ていないが feature #998 が着手可なので通した' in body, (
                f'通した wave の 1 行がコメントに無い: {write_log}')
            assert '#701 を 着手可 にした' in body, body

        t('_apply_align_plan は通した wave の 1 行を feature のコメントにも残す', _apply_align_plan_records_waived_wave_in_comment)

        def _apply_align_plan_no_waived_line_when_nothing_written() -> None:
            # 計画のあと子が 保留 に動いて飛ばしたなら、何も門を越えていないので「通した」は書かない
            items = [{
                'number': 702, 'type': 'Issue', 'kind': 'task', 'status': gh_task.JUDGMENT_STATUS,
                'state': 'OPEN', 'title': 't', 'parent_number': None,
            }]
            write_log: list[tuple] = []
            gh_task.run_gh = make_command_gh(items, write_log=write_log)
            plan = {'align': [{
                'feature': 997, 'wave_waived': [627],
                'moves': [{'number': 702, 'to': gh_task.READY_STATUS, 'from': gh_task.PENDING_STATUS}],
                'skipped': [],
            }]}
            gh_task._apply_align_plan(7, plan)
            body = next((e[2] or {}).get('body', '') for e in write_log if e[0] == 'POST')
            assert '通した' not in body and '飛ばした' in body, body

        t('_apply_align_plan は着手可へ 1 件も書かなかったとき「通した」を書かない',
          _apply_align_plan_no_waived_line_when_nothing_written)

        def _after_merge_closes_parent() -> None:
            items = [
                {
                    'number': 630, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 'F', 'parent_number': None,
                },
                {
                    'number': 631, 'type': 'Issue', 'kind': 'task', 'status': gh_task.DONE_STATUS,
                    'state': 'CLOSED', 'title': 't', 'parent_number': 630,
                },
            ]
            write_log: list[tuple] = []
            gh_task.run_gh = make_command_gh(
                items, summaries={630: {'total': 1, 'completed': 1}},
                closing_refs={70: [631]}, write_log=write_log,
            )
            orig_flag = gh_task.MIGRATION_ALIGN_WRITE_ENABLED
            gh_task.MIGRATION_ALIGN_WRITE_ENABLED = True
            try:
                rc = gh_task.main(['after-merge', '70'])
            finally:
                gh_task.MIGRATION_ALIGN_WRITE_ENABLED = orig_flag
            assert rc == 0
            patches = [(op, path) for op, path, *_ in write_log if op == 'PATCH']
            assert patches == [('PATCH', f'repos/{gh_task.REPO}/issues/630')], (
                f'after-merge が親を閉じていない: {write_log}'
            )

        t(
            'after-merge は、その PR が閉じた task の親（子が全部閉じた feature）を閉じる',
            _after_merge_closes_parent,
        )

        def _after_merge_cascades_to_grandparent() -> None:
            # task を閉じて feature も全部閉じたら、同じ実行で
            # 祖父（wave）まで辿って閉じる（以前は直接の親だけだった）。
            items = [
                {
                    'number': 640, 'kind': gh_task.WAVE_KIND, 'status': '', 'state': 'OPEN',
                    'title': 'P1', 'parent_number': None,
                },
                {
                    'number': 641, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 'F', 'parent_number': 640,
                },
                {
                    'number': 642, 'type': 'Issue', 'kind': 'task', 'status': gh_task.DONE_STATUS,
                    'state': 'CLOSED', 'title': 't', 'parent_number': 641,
                },
            ]
            bodies = {640: '- 出る条件のコマンド: exit 0（2026-09-28・abc1234）\n'}
            write_log: list[tuple] = []
            gh_task.run_gh = make_command_gh(
                items, bodies=bodies,
                summaries={641: {'total': 1, 'completed': 1}, 640: {'total': 1, 'completed': 1}},
                closing_refs={80: [642]}, write_log=write_log,
            )
            orig_flag = gh_task.MIGRATION_ALIGN_WRITE_ENABLED
            gh_task.MIGRATION_ALIGN_WRITE_ENABLED = True
            try:
                out = io.StringIO()
                with redirect_stdout(out):
                    rc = gh_task.main(['after-merge', '80'])
            finally:
                gh_task.MIGRATION_ALIGN_WRITE_ENABLED = orig_flag
            assert rc == 0
            patches = [(op, path) for op, path, *_ in write_log if op == 'PATCH']
            assert patches == [
                ('PATCH', f'repos/{gh_task.REPO}/issues/641'),
                ('PATCH', f'repos/{gh_task.REPO}/issues/640'),
            ], f'祖父（wave）まで連鎖して閉じていない: {write_log}'
            assert '閉じる親 2 件' in out.getvalue()

        t(
            'after-merge は、親を閉じた結果さらに祖父も閉じられるなら連鎖して閉じる',
            _after_merge_cascades_to_grandparent,
        )

        # ── memos（単独サブコマンド） ─────────────────────────────
        def _memos_command_standalone() -> None:
            items = [
                {
                    'number': 910, 'type': 'Issue', 'kind': gh_task.DESIGN_MEMO_KIND,
                    'status': gh_task.HOLD_STATUS, 'state': 'OPEN', 'title': 'memo A',
                    'parent_number': None,
                },
            ]
            gh_task.run_gh = make_command_gh(items)
            out = io.StringIO()
            with redirect_stdout(out):
                rc = gh_task.main(['memos'])
            assert rc == 0
            assert '保留の設計メモ 1 件' in out.getvalue()
            assert '#910' in out.getvalue()

        t(
            'memos は単独のサブコマンドとして叩ける',
            _memos_command_standalone,
        )

        # ── today（通しで回す・以前は selftest で 1 度も
        #    走らせていなかった） ────────────────────────────────────────
        def _today_full_run_smoke() -> None:
            items = [
                {
                    'number': 920, 'type': 'Issue', 'kind': gh_task.FEATURE_KIND,
                    'status': gh_task.READY_STATUS, 'state': 'OPEN', 'title': 'F',
                    'parent_number': None,
                },
                {
                    'number': 921, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 920,
                },
                {
                    'number': 922, 'type': 'Issue', 'kind': gh_task.DESIGN_MEMO_KIND,
                    'status': gh_task.HOLD_STATUS, 'state': 'OPEN', 'title': 'memo',
                    'parent_number': None,
                },
                {
                    'number': 923, 'type': 'Issue', 'kind': '', 'status': '', 'state': 'OPEN',
                    'title': 'orphan', 'parent_number': None,
                },
                {
                    'number': 924, 'type': 'Issue', 'kind': 'task', 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': '[User] 手作業', 'parent_number': None,
                },
            ]
            extras = {921: {'blocked_by_open': 0}}
            write_log: list[tuple] = []
            gh_task.run_gh = make_command_gh(items, extras=extras, write_log=write_log)
            orig_flag = gh_task.MIGRATION_ALIGN_WRITE_ENABLED
            gh_task.MIGRATION_ALIGN_WRITE_ENABLED = False
            out = io.StringIO()
            try:
                with redirect_stdout(out):
                    rc = gh_task.main(['today'])
            finally:
                gh_task.MIGRATION_ALIGN_WRITE_ENABLED = orig_flag
            text = out.getvalue()
            assert rc == 0, f'today が exit {rc}: {text}'
            # write_log には merged-designs の GET pulls（読むだけ）も積まれる偽 gh の
            # 実装なので、実際の書き込み（PATCH・POST・graphql-update）だけを見る。
            writes = [e for e in write_log if e[0] in ('PATCH', 'POST', 'graphql-update', 'item-update')]
            assert writes == [], f'切り替えを切ったのに today が書き込みの API を呼んだ: {writes}'
            assert '#921' in text, f'align の一覧（書かないが出す）に無い: {text!r}'
            assert '保留の設計メモ 1 件' in text
            assert 'orphans' in text and '#923' in text
            assert '[User] 1 件' in text and '#924' in text
            assert 'カードの抜け: 承認 0・判断 0・人の作業 1（hirai-task card --lint）' in text, f'カードの抜けの行が無い: {text!r}'

        t(
            'today は comments→close-parents→align→一覧・警告行を通しで回し、'
            '切り替えを切ると書き込みの API を呼ばない',
            _today_full_run_smoke,
        )

        # ── today の直し 3 つ（閉じたのに完了でない・種別なし・no-issue の merge） ──
        import contextlib

        def _today_with(items, *, prs=None, flag=True, fail_numbers=(), extra_bodies=None, probe=None, on_sleep=None,
                        override=None, stdout=None, stderr=None, expect_rc=0):
            """items を板にして today を回し、(標準出力, 標準エラー, Status の PATCH した item 番号, 書き込みログ)
            を返す。prs は直近の closed PR（REST の pulls の形）。fail_numbers の行は item id の引きが落ちる。
            override(method, path, input_text) は REST を先に受け、(rc, 標準出力, 標準エラー) を返せばそれが答え、None なら偽の gh に任せる。
            stdout・stderr は出力先の差し替え（BrokenPipe を起こす用）。"""
            write_log: list[tuple] = []
            patched: list[int] = []
            graphql_log: list[str] = []
            inner = make_command_gh(items, bodies=extra_bodies or {}, write_log=write_log, graphql_log=graphql_log)
            sleeps: list[float] = []
            journal_before = (
                open(gh_task.JOURNAL_PATH, encoding='utf-8').read().splitlines()
                if os.path.exists(gh_task.JOURNAL_PATH) else []
            )

            def fake_sleep(seconds):
                sleeps.append(seconds)
                if on_sleep is not None:
                    on_sleep(len(sleeps))

            def fake(args, input_text=None):
                if len(args) > 3 and args[:2] == ['api', '-X']:
                    method, path = args[2], args[3]
                    if override is not None:
                        answered = override(method, path, input_text)
                        if answered is not None:
                            return answered
                    if method == 'GET' and '/pulls?' in path:
                        return 0, json.dumps(prs if prs is not None else []), ''
                    if method == 'GET' and path == f'repos/{gh_task.REPO}':
                        return 0, json.dumps({'default_branch': 'stg'}), ''
                    q = re.search(r'items\?.*q=([^&]*)', path)
                    if method == 'GET' and q:
                        num = re.search(r'#(\d+)', urllib.parse.unquote(q.group(1)))
                        if num and int(num.group(1)) in fail_numbers:
                            return 1, '', 'HTTP 502: boom'
                    patch = re.search(r'/items/(\d+)$', path)
                    if method == 'PATCH' and patch:
                        patched.append(int(patch.group(1)) - 1000)
                return inner(args, input_text)

            orig_flag = gh_task.MIGRATION_ALIGN_WRITE_ENABLED
            gh_task.MIGRATION_ALIGN_WRITE_ENABLED = flag
            gh_task.run_gh = fake
            orig_sleep = gh_task.sleep_fn
            gh_task.sleep_fn = fake_sleep
            out, err = stdout or io.StringIO(), stderr or io.StringIO()
            try:
                with redirect_stdout(out), contextlib.redirect_stderr(err):
                    rc = gh_task.main(['today'])
            finally:
                gh_task.MIGRATION_ALIGN_WRITE_ENABLED = orig_flag
                gh_task.sleep_fn = orig_sleep
            assert rc == expect_rc, f'today が exit {rc}: {out.getvalue()}{err.getvalue()}'
            if probe is not None:
                journal_after = (
                    open(gh_task.JOURNAL_PATH, encoding='utf-8').read().splitlines()
                    if os.path.exists(gh_task.JOURNAL_PATH) else []
                )
                probe['sleeps'] = sleeps
                probe['journal'] = [json.loads(ln) for ln in journal_after[len(journal_before):]]
                probe['graphql'] = graphql_log
            return out.getvalue(), err.getvalue(), patched, write_log

        def _closed_row(number, status, kind='task', title=None):
            return {
                'number': number, 'type': 'Issue', 'kind': kind, 'status': status, 'state': 'CLOSED',
                'title': title or f'closed {number}', 'parent_number': None,
            }

        def _today_writes_done_for_closed_not_done() -> None:
            items = [
                _closed_row(70, gh_task.IN_PROGRESS_STATUS), _closed_row(71, ''),
                _closed_row(72, gh_task.DONE_STATUS),
                {'number': 73, 'type': 'Issue', 'kind': 'task', 'status': gh_task.IN_PROGRESS_STATUS,
                 'state': 'OPEN', 'title': '開いている', 'parent_number': None},
            ]
            text, _err, patched, log = _today_with(items)
            assert patched == [70, 71], f'完了を書いた相手が違う: {patched}'
            statuses = [e for e in log if e[0] == 'item-update']
            assert statuses == [('item-update', 'F_Status', 'O_Status_完了')] * 2, statuses
            assert '閉じたのに完了でない 2 件を完了にした: #70・#71' in text, text
            assert '閉じたのに完了でない: #' not in text, f'書けたのに stuck に残った: {text}'

        t('today: 閉じたのに完了でない行へ Status=完了 だけを書き、番号を 1 行で出す（stuck には残さない）',
          _today_writes_done_for_closed_not_done)

        def _today_closed_fix_continues_after_one_failure() -> None:
            items = [_closed_row(80, gh_task.IN_PROGRESS_STATUS), _closed_row(81, gh_task.REVIEW_STATUS)]
            text, _err, patched, _log = _today_with(items, fail_numbers=(80,))
            assert patched == [81], f'書けない 1 件のあとが続かない: {patched}'
            assert '閉じたのに完了でない 1 件を完了にした: #81' in text, text
            assert '完了にできなかった: #80' in text and 'boom' in text, text
            failed_line = next(ln for ln in text.splitlines() if '完了にできなかった: #80' in ln)
            assert 'projectsV2' not in failed_line, f'理由の前に path の前置きが入った: {failed_line}'
            assert '閉じたのに完了でない: #80' in text, f'書けなかった行が stuck に残らない: {text}'

        t('today: 閉じたのに完了でない行の書き込みが 1 件落ちても理由を 1 行出し、ほかは続ける',
          _today_closed_fix_continues_after_one_failure)

        def _today_closed_fix_dry_when_not_allowed() -> None:
            items = [_closed_row(90, gh_task.IN_PROGRESS_STATUS)]
            text, _err, patched, _log = _today_with(items, flag=False)
            assert patched == [], f'許可が無いのに書いた: {patched}'
            assert '完了にした' not in text and '閉じたのに完了でない: #90' in text, text
            # 「- today は書かない: はい」の目印が open の issue にあるときも書かない。
            items = [
                _closed_row(91, gh_task.IN_PROGRESS_STATUS),
                {'number': 92, 'type': 'Issue', 'kind': 'task', 'status': gh_task.IN_PROGRESS_STATUS,
                 'state': 'OPEN', 'title': '[操作] 一括', 'parent_number': None},
            ]
            text, _err, patched, _log = _today_with(items, extra_bodies={92: gh_task.NO_TODAY_MARK})
            assert patched == [], f'目印があるのに書いた: {patched}'

        t('today: 書き込みの許可が無い（切り替え・today は書かない の目印）ときは、完了を書かず stuck に出すだけ',
          _today_closed_fix_dry_when_not_allowed)

        def _today_closed_fix_none_and_feature_untouched() -> None:
            items = [
                _closed_row(95, gh_task.DONE_STATUS),
                _closed_row(96, gh_task.IN_PROGRESS_STATUS, kind='feature', title='閉じた feature'),
            ]
            text, _err, patched, _log = _today_with(items)
            assert patched == [], f'task でない行・完了の行に書いた: {patched}'
            assert '完了にした' not in text, text

        t('today: 0 件なら何も書かず何も出さない（feature・完了の行は対象外）', _today_closed_fix_none_and_feature_untouched)

        def _closed_fix_matches_done_not_planned() -> None:
            # done --not-planned が書く Status と、today が書く Status は同じ値（完了）。today を通して比べる。
            specs = {97: dict(title='t', status=gh_task.IN_PROGRESS_STATUS, kind='task')}
            rec_done: list = []
            gh_task.run_gh = make_write_gh(specs, record=rec_done, rest_handler=lambda *a: {})
            gh_task.cmd_done(97, '見送り')
            _text, _err, patched, log = _today_with([_closed_row(97, gh_task.IN_PROGRESS_STATUS)])
            written = [(f, v) for k, f, v in log if k == 'item-update']
            assert patched == [97] and written == rec_done == [('F_Status', 'O_Status_完了')], (patched, written, rec_done)

        t('閉じた理由が not planned でも、done --not-planned と today が書く Status は同じ（完了）',
          _closed_fix_matches_done_not_planned)

        def _today_closed_fix_journal_sleep_order_graphql() -> None:
            # journal・8.5 秒おき・書く順（align の前）・板の取り直し・GraphQL を増やさない、を today を通して見る。
            def board():
                return [
                    _closed_row(60, gh_task.IN_PROGRESS_STATUS), _closed_row(61, ''),
                    {'number': 62, 'type': 'Issue', 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                     'state': 'OPEN', 'title': 'F', 'parent_number': None},
                    {'number': 63, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                     'state': 'OPEN', 'title': 'child', 'parent_number': 62},
                ]
            probe: dict = {}
            seen_by_align: list = []
            orig_align = gh_task.cmd_align

            def spy_align(*args, **kwargs):
                seen_by_align.extend((i['number'], i['status']) for i in (kwargs.get('items') or []))
                return orig_align(*args, **kwargs)

            gh_task.cmd_align = spy_align
            try:
                _text, _err, _patched, log = _today_with(board(), probe=probe)
            finally:
                gh_task.cmd_align = orig_align
            assert (60, gh_task.DONE_STATUS) in seen_by_align and (61, gh_task.DONE_STATUS) in seen_by_align, \
                f'align が書いたあとの板（完了）を見ていない: {seen_by_align}'
            closes = [r for r in probe['journal'] if r['op'] == 'close-sync']
            assert [(r['number'], r['from'], r['to']) for r in closes] == [
                (60, gh_task.IN_PROGRESS_STATUS, gh_task.DONE_STATUS), (61, '', gh_task.DONE_STATUS),
            ], probe['journal']
            assert all(r['repo'] == gh_task.REPO and r['project'] == 7 for r in closes)
            assert probe['sleeps'][:2] == [gh_task._WRITE_INTERVAL_SECONDS] * 2, probe['sleeps']
            writes = [(f, v) for k, f, v in log if k == 'item-update']
            assert writes == [('F_Status', 'O_Status_完了')] * 2 + [('F_Status', 'O_Status_着手可')], f'書く順が違う: {writes}'
            # 板は 3 回（最初・close-parents のあと・align のあと）。書き込みで GraphQL の読みは増えない。
            reads = [g for g in probe['graphql'] if 'items(first:' in g]
            assert len(reads) == 3, f'板の読みが {len(reads)} 回: 取り直しが消えた/増えた'
            base: dict = {}
            _today_with([_closed_row(60, gh_task.DONE_STATUS), board()[2], board()[3]], probe=base)
            extra = len(probe['graphql']) - len(base['graphql'])
            # 比べる元の板でも align が書くので、owner の種類を引く 1 回は両方にある。完了の書き込みで増えるのは 0 回。
            # open の issue の本文を読む GraphQL（許可の判定）は today 全体で 3 回（実測）。完了を書くために判定を増やさない。
            allow_reads = [g for g in probe['graphql'] if 'issue(number:' in g and 'blockedBy' not in g]
            assert len(allow_reads) == 3, f'許可の判定の読みが {len(allow_reads)} 回: {allow_reads}'
            assert extra == 0, f'GraphQL が {extra} 回増えた（許す書き込みの判定・owner の種類は 1 回ずつ）: {probe["graphql"]}'

        t('today: 完了の書き込みは journal に 1 件ずつ・8.5 秒おき・align の前・板は 3 回読み・GraphQL は増やさない',
          _today_closed_fix_journal_sleep_order_graphql)

        def _today_closed_fix_skips_reopened_and_other_repo() -> None:
            # 書く直前に読み直す: 板を読んだあと（1 件目を書いた間）に 61 が reopen されたら、完了を書かない。
            items = [_closed_row(60, gh_task.IN_PROGRESS_STATUS), _closed_row(61, gh_task.IN_PROGRESS_STATUS)]

            def reopen(n_sleeps):
                if n_sleeps == 1:
                    items[1]['state'] = 'OPEN'

            probe_reopen: dict = {}
            text, _err, patched, _log = _today_with(items, on_sleep=reopen, probe=probe_reopen)
            assert patched == [60], f'開き直された #61 に完了を書いた: {patched}'
            assert probe_reopen['sleeps'] == [gh_task._WRITE_INTERVAL_SECONDS], f'飛ばした行で眠った: {probe_reopen["sleeps"]}'
            assert '飛ばした: #61' in text and '2 件を完了にした' not in text, text
            # 別 repo の閉じた同じ番号（#70）で、この repo の開いている #70 を完了にしない。
            other = 'https://github.com/other-org/other-app/issues/70'
            items = [
                {**_closed_row(70, gh_task.IN_PROGRESS_STATUS), 'url': other},
                {'number': 70, 'type': 'Issue', 'kind': 'task', 'status': gh_task.IN_PROGRESS_STATUS,
                 'state': 'OPEN', 'title': 'この repo の 70', 'parent_number': None},
            ]
            text, _err, patched, _log = _today_with(items)
            assert patched == [] and '完了にした' not in text, f'別 repo の #70 でこの repo の #70 を書いた: {patched} {text}'
            board_70 = items
            # この repo に同じ番号が無い別 repo の閉じた行は、書く対象にも「にする」の行にも入れない。
            items = [{**_closed_row(72, gh_task.IN_PROGRESS_STATUS), 'url': other.replace('/70', '/72')}]
            text, _err, patched, _log = _today_with(items)
            assert patched == [] and '完了にする' not in text and '飛ばした' not in text and 'できなかった' not in text, text
            # 書き込み後の写しも、別 repo の行・開き直された行には当てない。
            rows = [{**board_70[0]}, {**board_70[1]}, {**_closed_row(80, ''), 'state': 'OPEN'}]
            done = gh_task.with_done_status(rows + [_closed_row(81, '')], [70, 80, 81])
            assert [r['status'] for r in done] == [gh_task.IN_PROGRESS_STATUS, gh_task.IN_PROGRESS_STATUS, '', gh_task.DONE_STATUS], done

        t('today: 書く直前に state を読み直して開き直された行は飛ばし、別 repo の同じ番号の行には書かない',
          _today_closed_fix_skips_reopened_and_other_repo)

        def _ov(issue=None, search=None, patch=None, seen=None):
            """REST の偽の答えを番号ごとに差し替える override（issue の GET・items の ?q= 検索・items の PATCH）。
            値は (rc, 標準出力, 標準エラー)・None（偽の gh に任せる）を返す関数か、その tuple。"""
            def pick(table, number):
                got = (table or {}).get(number)
                return got() if callable(got) else got

            def override(method, path, input_text):
                if seen is not None:
                    seen.append((method, path))
                m = re.match(r'^repos/[^/]+/[^/]+/issues/(\d+)$', path)
                if method == 'GET' and m:
                    return pick(issue, int(m.group(1)))
                q = re.search(r'items\?.*q=([^&]*)', path)
                if method == 'GET' and q:
                    num = re.search(r'#(\d+)', urllib.parse.unquote(q.group(1)))
                    return pick(search, int(num.group(1))) if num else None
                p = re.search(r'/items/(\d+)$', path)
                if method == 'PATCH' and p:
                    return pick(patch, int(p.group(1)) - 1000)
                return None
            return override

        RATE_403 = (1, '', 'gh: You have exceeded a secondary rate limit. (HTTP 403)')
        RATE_429 = (1, '', 'gh: Too Many Requests (HTTP 429)')

        def _today_closed_fix_limit_and_early_line() -> None:
            n = 7  # 書けた件数の上限は 5 件
            items = [_closed_row(300 + k, gh_task.IN_PROGRESS_STATUS) for k in range(n)]
            text, _err, patched, _log = _today_with(items)
            assert gh_task.CLOSED_DONE_WRITE_LIMIT == 5 and gh_task.CLOSED_DONE_TRY_LIMIT == 15, '上限の定数が変わった'
            assert patched == [300 + k for k in range(5)], patched
            lines = text.splitlines()
            head = next(i for i, ln in enumerate(lines) if ln == '閉じたのに完了でない 7 件のうち 5 件を完了にする: #300・#301・#302・#303・#304')
            done = next(i for i, ln in enumerate(lines) if ln.startswith('閉じたのに完了でない 5 件を完了にした'))
            assert head < done, '書く前の 1 行が書いた後の 1 行より先に出ない'
            assert '残り 2 件は次の today' in text, text

        t('today: 完了を書けた数に上限があり、書く前に「7 件のうち 5 件」の 1 行を出し、残りは次の today と出す', _today_closed_fix_limit_and_early_line)

        def _today_closed_fix_failures_do_not_use_the_quota() -> None:
            # 書けない 5 件が先頭に並んでも、あとの書ける 3 件に届く（失敗・飛ばしは書けた枠に数えない）。
            items = [_closed_row(100 + k, gh_task.IN_PROGRESS_STATUS) for k in range(8)]
            text, _err, patched, _log = _today_with(items, fail_numbers=tuple(range(100, 105)))
            assert patched == [105, 106, 107], f'先頭の失敗が枠を食った: {patched}'
            assert '閉じたのに完了でない 8 件のうち 5 件を完了にする: #100・#101・#102・#103・#104' in text, text
            assert '閉じたのに完了でない 3 件を完了にした: #105・#106・#107' in text, text
            assert '残り' not in text, f'全部試したのに「残り」を出した: {text}'
            # 試す数にも上限がある（15 件）。書けた 3 件のあと、試さなかった 5 件を「残り 5 件」と出す。
            items = [_closed_row(200 + k, gh_task.IN_PROGRESS_STATUS) for k in range(20)]
            text, _err, patched, _log = _today_with(items, fail_numbers=tuple(range(200, 212)))
            assert patched == [212, 213, 214], patched
            assert '残り 5 件は次の today' in text, text
            assert text.count('完了にできなかった:') == 12, text
            # 全部が書けないときも、試すのは 15 件まで。
            seen: list = []
            items = [_closed_row(220 + k, gh_task.IN_PROGRESS_STATUS) for k in range(20)]
            text, _err, patched, _log = _today_with(items, fail_numbers=tuple(range(220, 240)), override=_ov(seen=seen))
            tried = {int(re.search(r'%23(\d+)', p).group(1)) for m, p in seen if m == 'GET' and 'q=%23' in p}
            assert patched == [] and len(tried) == 15, f'試した件数が 15 でない: {sorted(tried)}'
            assert '残り 5 件は次の today' in text, text

        t('today: 失敗・飛ばしは書けた枠に数えず、試す数の上限は別（15）。「残り N 件」は試さなかった数',
          _today_closed_fix_failures_do_not_use_the_quota)

        def _today_closed_fix_stops_on_rate_limit() -> None:
            items = [_closed_row(110 + k, gh_task.IN_PROGRESS_STATUS) for k in range(8)]
            seen: list = []
            text, _err, patched, _log = _today_with(items, override=_ov(search={111: RATE_403}, seen=seen))
            assert patched == [110], f'403 のあとも書いた: {patched}'
            tried = [m for m, p in seen if m == 'GET' and 'q=%23' in p]
            assert len(tried) == 2, f'403 のあとも検索を続けた: {tried}'
            assert '完了にできなかった: #111' in text and '打ち切った' in text and '残り 6 件' in text, text
            # PATCH の 429（secondary rate limit）でも残りを打ち切る。
            items = [_closed_row(120 + k, gh_task.IN_PROGRESS_STATUS) for k in range(3)]
            text, _err, patched, _log = _today_with(items, override=_ov(patch={120: RATE_429}))
            assert patched == [] and '完了にできなかった: #120' in text and '残り 2 件は打ち切った' in text, text
            assert '完了にした' not in text, text
            # 読み直しの 403 でも同じ。
            items = [_closed_row(125 + k, gh_task.IN_PROGRESS_STATUS) for k in range(3)]
            text, _err, patched, _log = _today_with(items, override=_ov(issue={125: RATE_403}))
            assert patched == [] and '残り 2 件は打ち切った' in text, (patched, text)

        t('today: 403・429（rate limit）が出たら残りを打ち切り、その旨を 1 行出す（検索・読み直し・書き込みのどこでも）',
          _today_closed_fix_stops_on_rate_limit)

        def _today_closed_fix_reread_answers() -> None:
            issue = {
                130: (1, '', 'gh: Not Found (HTTP 404)'),
                132: (0, json.dumps({'number': 132}), ''),
                133: (0, 'null', ''),
                134: (0, json.dumps({'number': 134, 'state': 'open'}), ''),
                135: (0, json.dumps({'number': 135, 'state': 'closed', 'state_reason': 'not_planned'}), ''),
                136: (0, '[]', ''),
            }
            items = [_closed_row(130 + k, gh_task.IN_PROGRESS_STATUS) for k in range(7)]
            seen: list = []
            probe: dict = {}
            text, _err, patched, _log = _today_with(items, override=_ov(issue=issue, seen=seen), probe=probe)
            assert patched == [131, 135], patched
            values = [(f, v) for k, f, v in _log if k == 'item-update']
            assert values == [('F_Status', 'O_Status_完了')] * 2, f'完了以外を書いた: {values}'
            lines = {n: next((ln for ln in text.splitlines() if f'#{n}（' in ln and ('できなかった' in ln or '飛ばした' in ln)), '') for n in range(130, 137)}
            assert 'できなかった' in lines[130] and 'Not Found' in lines[130], lines[130]
            assert '飛ばした' in lines[132] and '不明' in lines[132] and 'reopen' not in lines[132], lines[132]
            assert 'できなかった' in lines[133], lines[133]
            assert '飛ばした' in lines[134] and 'reopen' in lines[134], lines[134]
            assert lines[135] == '' and lines[131] == '', 'not planned・普通の行が書けなかった扱いになった'
            assert 'できなかった' in lines[136], lines[136]
            assert '2 件を完了にした: #131・#135' in text, text
            # 読み直しはこの repo の issue を引き、飛ばした・失敗の行では眠らない。
            gets = [p for m, p in seen if m == 'GET' and re.match(r'^repos/[^/]+/[^/]+/issues/\d+$', p)]
            assert gets and all(p.startswith(f'repos/{gh_task.REPO}/issues/') for p in gets), gets
            assert probe['sleeps'].count(gh_task._WRITE_INTERVAL_SECONDS) == len(patched), probe['sleeps']

        t('today: 読み直しが 404・state なし・null・open・not planned・配列でも today は止まらず、安全側（書かない）に倒す。not planned は書く',
          _today_closed_fix_reread_answers)

        def _today_closed_fix_rereads_after_lookup() -> None:
            # 読み直しは item id の検索のあと、書く直前。検索の間に reopen された行へ 完了 を上書きしない。
            items = [_closed_row(140, gh_task.IN_PROGRESS_STATUS), _closed_row(141, gh_task.IN_PROGRESS_STATUS)]

            def reopen_during_search():
                items[0]['state'] = 'OPEN'
                return None

            text, _err, patched, _log = _today_with(items, override=_ov(search={140: reopen_during_search}))
            assert patched == [141] and '飛ばした: #140' in text, f'検索の間の reopen に書いた: {patched} {text}'
            # 検索の反映待ち（2 秒おきの引き直し）の間の reopen も同じ。
            row = [_closed_row(142, gh_task.IN_PROGRESS_STATUS)]
            calls = {'n': 0}

            def lagging_search():
                calls['n'] += 1
                return (0, '[]', '') if calls['n'] <= 2 else None

            def reopen_on_first_sleep(count):
                if count == 1:
                    row[0]['state'] = 'OPEN'

            text, _err, patched, _log = _today_with(row, on_sleep=reopen_on_first_sleep, override=_ov(search={142: lagging_search}))
            assert calls['n'] == 3 and patched == [] and '飛ばした: #142' in text, (calls, patched, text)

        t('today: 完了は「item id と選択肢を引く → state を読み直す → item_id を渡して書く」の順（検索の間・反映待ちの間の reopen に書かない）',
          _today_closed_fix_rereads_after_lookup)

        def _today_closed_fix_survives_closed_pipe() -> None:
            class _Out(io.StringIO):
                def __init__(self, broken):
                    super().__init__()
                    self.broken, self.snapshots = broken, []

                def flush(self):
                    self.snapshots.append(self.getvalue())
                    if self.broken:
                        raise BrokenPipeError(32, 'Broken pipe')

            def board():
                return [
                    _closed_row(150, gh_task.IN_PROGRESS_STATUS),
                    {'number': 151, 'type': 'Issue', 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                     'state': 'OPEN', 'title': 'F', 'parent_number': None},
                    {'number': 152, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                     'state': 'OPEN', 'title': 'child', 'parent_number': 151},
                ]
            # 出力先が閉じても（today | head）、完了を書いたあとの align まで進む。
            _text, _err, patched, log = _today_with(board(), stdout=_Out(True))
            writes = [(f, v) for k, f, v in log if k == 'item-update']
            assert writes == [('F_Status', 'O_Status_完了'), ('F_Status', 'O_Status_着手可')], f'align まで進まない: {writes}'
            # 対象の行は書く前に flush して残す（時間切れで止められても何を書いていたか分かる）。
            out = _Out(False)
            _today_with(board(), stdout=out)
            early = [s for s in out.snapshots if '件を完了にする: #150' in s]
            assert early and '完了にした' not in early[0], '書く前の行を flush していない'

        t('today: 出力先が閉じても（BrokenPipeError）stdout を捨てて続け、完了を書いたあとの align まで走る。書く前の行は flush する',
          _today_closed_fix_survives_closed_pipe)

        def _today_closed_fix_stuck_names_other_repo() -> None:
            other = 'https://github.com/other-org/other-app/issues/70'
            items = [
                {**_closed_row(70, gh_task.IN_PROGRESS_STATUS), 'url': other},
                _closed_row(71, gh_task.IN_PROGRESS_STATUS),
            ]
            text, _err, patched, _log = _today_with(items, fail_numbers=(71,))
            stuck70 = next(ln for ln in text.splitlines() if ln.startswith('  閉じたのに完了でない: #70'))
            stuck71 = next(ln for ln in text.splitlines() if ln.startswith('  閉じたのに完了でない: #71'))
            assert 'other-org/other-app' in stuck70, f'別 repo の行に repo 名が無い: {stuck70}'
            assert 'other-org' not in stuck71, f'この repo の行に repo 名が付いた: {stuck71}'

        t('today の stuck: 別 repo の閉じた行は repo 名を添えて出す（書けなかったこの repo の行と見分ける）',
          _today_closed_fix_stuck_names_other_repo)

        def _today_closed_fix_journal_failure_keeps_going() -> None:
            orig = gh_task._append_journal

            def broken(entry):
                raise OSError(28, 'No space left on device')

            gh_task._append_journal = broken
            try:
                items = [_closed_row(160, gh_task.IN_PROGRESS_STATUS), _closed_row(161, gh_task.IN_PROGRESS_STATUS)]
                text, err, patched, _log = _today_with(items)
            finally:
                gh_task._append_journal = orig
            assert patched == [160, 161] and '2 件を完了にした: #160・#161' in text, (patched, text)
            assert err.count('journal を書けなかった') == 2, err

        t('today: journal が書けなくても警告 1 行で続け、書いた番号を出す', _today_closed_fix_journal_failure_keeps_going)

        def _today_closed_fix_hold_and_kindless_rows() -> None:
            items = [
                _closed_row(170, '保留'),
                _closed_row(171, '', kind=''),
                _closed_row(172, gh_task.READY_STATUS),
            ]
            text, _err, patched, _log = _today_with(items)
            assert patched == [170, 171, 172], f'保留・種別空・着手可のまま閉じた行を書いていない: {patched}'
            assert '3 件を完了にした: #170・#171・#172' in text, text

        t('today: 保留・種別が空・着手可のまま閉じた行にも 完了 を書く', _today_closed_fix_hold_and_kindless_rows)

        def _today_with_args_exits_2_without_writing() -> None:
            for args in (['--json'], ['--dry-run'], ['--help']):
                write_log: list[tuple] = []
                gh_task.run_gh = make_command_gh([_closed_row(90, gh_task.IN_PROGRESS_STATUS)], write_log=write_log)
                err = io.StringIO()
                try:
                    with redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                        rc = gh_task.main(['today'] + args)
                except gh_task.GhError as exc:
                    rc = exc.code
                else:
                    rc = 0
                assert rc == 2, f'today {args} が exit {rc}'
                assert [e for e in write_log if e[0] in ('PATCH', 'POST', 'item-update', 'graphql-update')] == [], args

        t('today に引数（--json・--dry-run・--help）を付けると exit 2 で何も書かない', _today_with_args_exits_2_without_writing)

        def _closed_fix_reason_keeps_the_cause() -> None:
            exc = gh_task.GhError('gh api GET orgs/example-org/projectsV2/7/items?q=%2380&per_page=100 が失敗した: '
                                  'gh: API rate limit exceeded for user\nrun gh auth refresh -s project', 1)
            reason = gh_task._short_reason(exc)
            assert reason == 'gh: API rate limit exceeded for user / run gh auth refresh -s project', reason

        t('完了にできなかった理由は、path の前置きを落として gh の理由（2 行目の案内も）を残す', _closed_fix_reason_keeps_the_cause)

        def _closed_fix_reason_is_one_line_of_200() -> None:
            reason = gh_task._short_reason(gh_task.GhError('x' * 500))
            assert reason == 'x' * 200, len(reason)
            assert '\n' not in gh_task._short_reason(gh_task.GhError('a\n\n  b\nc')), '改行が残った'
            assert gh_task._short_reason(gh_task.GhError('')) == '不明'

        t('完了にできなかった理由は 1 行・200 字まで（空なら「不明」）', _closed_fix_reason_is_one_line_of_200)

        def _orphans_kindless_row_shows_fix_command() -> None:
            items = [
                {'number': 930, 'type': 'Issue', 'kind': '', 'status': '', 'state': 'OPEN',
                 'title': '種別なし', 'parent_number': None},
                {'number': 931, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                 'state': 'OPEN', 'title': '親なし', 'parent_number': None},
            ]
            text, _err, _patched, _log = _today_with(items, flag=False)
            lines = text.splitlines()
            i = next(n for n, ln in enumerate(lines) if '#930' in ln and '種別なし' in ln)
            assert lines[i + 1].strip() == '直す: hirai-task set 930 種別 task（feature・wave・設計メモならその値）', lines[i:i + 2]
            j = next(n for n, ln in enumerate(lines) if '#931' in ln and '親なし' in ln)
            assert '直す:' not in lines[j + 1] if j + 1 < len(lines) else True, '親なしの行に直す行を出した'
            assert text.count('直す:') == 1, text

        t('today の orphans: 種別なしの行の次に直すコマンドを 1 行出す（親なしの行には出さない）',
          _orphans_kindless_row_shows_fix_command)

        def _set_start_warn_when_kind_empty() -> None:
            def run(fn):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), redirect_stdout(io.StringIO()):
                    rc = fn()
                return rc, err.getvalue()

            specs = {
                940: dict(title='t', status=gh_task.READY_STATUS, kind=''),
                941: dict(title='t', status=gh_task.READY_STATUS, kind='task'),
            }
            rec: list = []
            gh_task.run_gh = make_write_gh(specs, record=rec)
            rc, err = run(lambda: gh_task.cmd_set(940, 'Status', gh_task.PENDING_STATUS))
            assert rc == 0 and err.strip() == '警告: #940 は種別が空。直すには hirai-task set 940 種別 task（feature・wave・設計メモならその値）', repr(err)
            assert rec == [('F_Status', 'O_Status_承認待ち')], f'警告で書き込みが変わった: {rec}'
            rc, err = run(lambda: gh_task.cmd_set(941, 'Status', gh_task.PENDING_STATUS))
            assert rc == 0 and err == '', repr(err)
            # 警告は書き込みの前に出す（書き込みで落ちても警告は残る）。
            err_buf = io.StringIO()
            order: list[str] = []
            inner_gh = gh_task.run_gh

            def spy(args, input_text=None):
                if 'PATCH' in args:
                    order.append('警告あり' if err_buf.getvalue() else '警告なし')
                return inner_gh(args, input_text)

            gh_task.run_gh = spy
            with contextlib.redirect_stderr(err_buf), redirect_stdout(io.StringIO()):
                gh_task.cmd_set(940, 'Status', gh_task.PENDING_STATUS)
            gh_task.run_gh = inner_gh
            assert order == ['警告あり'], f'警告が書き込みより後に出た: {order}'
            rc, err = run(lambda: gh_task.cmd_set(940, gh_task.KIND_FIELD, 'task'))
            assert rc == 0 and err == '', f'種別自身を set するのに警告した: {err!r}'
            rc, err = run(lambda: gh_task.cmd_start(940, None))
            assert rc == 0 and err.strip() == '警告: #940 は種別が空。直すには hirai-task set 940 種別 task（feature・wave・設計メモならその値）', repr(err)
            rc, err = run(lambda: gh_task.cmd_start(941, None))
            assert rc == 0 and err == '', repr(err)

        t('set・start: 相手の種別が空なら stderr に警告 1 行（止めない・exit 0・書き込みは同じ）。種別自身の set は警告しない',
          _set_start_warn_when_kind_empty)

        def _pr(number, labels, merged_at, updated_at=None):
            return {
                'number': number, 'title': f'PR {number}', 'body': '', 'merged_at': merged_at,
                'updated_at': updated_at or merged_at or '2000-01-01T00:00:00Z',
                'labels': [{'name': name} for name in labels],
            }

        def _days_ago(days: float) -> str:
            moment = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
            return moment.strftime('%Y-%m-%dT%H:%M:%SZ')

        def _no_issue_line(prs) -> str:
            text, _err, _p, _l = _today_with([], prs=prs, flag=False)
            return '\n'.join(ln for ln in text.splitlines() if 'no-issue の merge' in ln)

        def _today_lists_no_issue_merges() -> None:
            assert _no_issue_line([]) == '', '0 件なのに出た'
            prs = [
                _pr(11, ['no-issue'], _days_ago(1)),
                _pr(13, ['no-issue', 'x'], _days_ago(3)),
                _pr(12, ['no-issue'], _days_ago(2)),
                _pr(14, ['other'], _days_ago(1)),            # ラベル違い
                _pr(15, ['no-issue'], None),                 # merge されず close
                _pr(16, ['no-issue'], _days_ago(8)),         # 8 日前
            ]
            assert _no_issue_line(prs) == 'no-issue の merge（7 日）3 件: #11・#12・#13', _no_issue_line(prs)
            assert _no_issue_line([_pr(16, ['no-issue'], _days_ago(8))]) == '', '8 日前だけなのに出た'

        t('today: 直近 7 日に no-issue で merge した PR を「N 件: #a・#b」の 1 行で出す（0 件・8 日前・ラベル違い・未 merge は数えない）',
          _today_lists_no_issue_merges)

        def _today_no_issue_marks_truncation() -> None:
            recent = [_pr(200 + n, ['no-issue'] if n == 0 else [], _days_ago(1), _days_ago(1)) for n in range(100)]
            line = _no_issue_line(recent)
            assert line == 'no-issue の merge（7 日・直近の closed PR 100 件まで）1 件: #200', line
            # 100 件でも、最後の PR の更新が 7 日より前なら 7 日分は読み切っている。
            recent[-1] = _pr(299, [], _days_ago(9), _days_ago(9))
            assert _no_issue_line(recent) == 'no-issue の merge（7 日）1 件: #200', _no_issue_line(recent)

        t('today: closed の PR 100 件で 7 日に届かないときは「100 件まで」と分かるように出す', _today_no_issue_marks_truncation)

        def _today_no_issue_zero_but_cut_off_is_shown() -> None:
            recent = [_pr(400 + n, [], _days_ago(1), _days_ago(1)) for n in range(100)]
            line = _no_issue_line(recent)
            assert line == 'no-issue の merge（7 日・直近の closed PR 100 件まで）0 件', line
            assert _no_issue_line(recent[:99]) == '', '切れていない 0 件を出した'

        t('today: 100 件で 7 日に届かず no-issue が 0 件のときは「0 件」と出し、切れていない 0 件は出さない',
          _today_no_issue_zero_but_cut_off_is_shown)

        def _today_no_issue_window_labels_and_boundary() -> None:
            prs = [
                _pr(21, ['no-issue'], _days_ago(6)),            # 6 日前は数える（7 日の窓）
                _pr(22, ['no-issue-x'], _days_ago(1)),          # ラベルは名前の完全一致
                _pr(23, ['x-no-issue'], _days_ago(1)),
                _pr(24, ['No-Issue'], _days_ago(1)),
            ]
            assert _no_issue_line(prs) == 'no-issue の merge（7 日）1 件: #21', _no_issue_line(prs)
            # 境目: ちょうど 7 日前の merge は数え、1 秒前は数えない（時計を止めて比べる）。
            import types
            fixed = datetime.datetime(2026, 11, 24, 0, 0, 0, tzinfo=datetime.timezone.utc)

            class _Clock(datetime.datetime):
                @classmethod
                def now(cls, tz=None):
                    return fixed

            real = gh_task.datetime
            gh_task.datetime = types.SimpleNamespace(
                datetime=_Clock, timezone=datetime.timezone, timedelta=datetime.timedelta,
            )
            try:
                edge = gh_task.no_issue_merge_line([
                    _pr(31, ['no-issue'], '2026-11-17T00:00:00Z'), _pr(32, ['no-issue'], '2026-11-16T23:59:59Z'),
                ])
            finally:
                gh_task.datetime = real
            assert edge == 'no-issue の merge（7 日）1 件: #31', edge

        t('today の no-issue の merge: 窓は 7 日（6 日前は数え、ちょうど 7 日前は数え、1 秒前は数えない）。ラベルは完全一致',
          _today_no_issue_window_labels_and_boundary)

        def _today_no_issue_cut_off_uses_updated_at() -> None:
            # 100 件目の「更新」が窓の中なら、merge が古くても先に窓内の PR が残りうる（更新で見る）。
            recent = [_pr(500 + n, [], _days_ago(1), _days_ago(1)) for n in range(99)]
            last = _pr(599, [], _days_ago(30), _days_ago(1))
            line = _no_issue_line(recent + [last])
            assert line == 'no-issue の merge（7 日・直近の closed PR 100 件まで）0 件', line
            # updated_at が無いときは、窓の外と決めつけず見切れとして出す。
            nodate = _pr(598, [], _days_ago(30), _days_ago(1))
            del nodate['updated_at']
            line = _no_issue_line(recent + [nodate])
            assert '100 件まで' in line, line

        t('today の no-issue の merge: 100 件で見切れるかは最後の PR の更新で見る（merge の日付でも、updated_at なしでも）',
          _today_no_issue_cut_off_uses_updated_at)

        def _orphans_other_repo_kindless_row_has_no_fix() -> None:
            items = [
                {'number': 71, 'type': 'Issue', 'kind': '', 'status': '', 'state': 'OPEN', 'title': '別 repo',
                 'parent_number': None, 'url': 'https://github.com/other-org/other-app/issues/71'},
            ]
            text, _err, _p, _l = _today_with(items, flag=False)
            assert '#71' in text and '直す:' not in text, text

        t('today の orphans: 別 repo の種別なしの行には直すコマンドを出さない（この repo の同じ番号を書き換えさせない）',
          _orphans_other_repo_kindless_row_has_no_fix)

        def _today_reads_closed_prs_once() -> None:
            calls: list[str] = []
            inner = make_command_gh([])

            def fake(args, input_text=None):
                if len(args) > 3 and args[:2] == ['api', '-X'] and '/pulls?' in args[3]:
                    calls.append(args[3])
                    return 0, '[]', ''
                return inner(args, input_text)

            gh_task.run_gh = fake
            orig_flag = gh_task.MIGRATION_ALIGN_WRITE_ENABLED
            gh_task.MIGRATION_ALIGN_WRITE_ENABLED = False
            try:
                with redirect_stdout(io.StringIO()):
                    assert gh_task.main(['today']) == 0
            finally:
                gh_task.MIGRATION_ALIGN_WRITE_ENABLED = orig_flag
            assert len(calls) == 1, f'closed の PR を {len(calls)} 回引いた（API を増やさない）: {calls}'
            assert 'state=closed' in calls[0] and 'sort=updated&direction=desc&per_page=100' in calls[0], calls

        t('today: closed の PR の一覧は merged-designs と no-issue で 1 回だけ引く', _today_reads_closed_prs_once)

        # ── 前夜の CI（today の 1 行。nightly_ci の設定が無いときは gh を呼ばない） ──
        def _nightly(setting: str | None, gh_result, *, now: str = '2026-11-23T20:00:00+00:00',
                     home_setting: str | None = None, via_today: bool = False) -> tuple[str, list]:
            """偽の gh・偽の時計・使い捨ての project/home で today の 1 行を出し、(標準出力, gh の呼び出し) を返す。"""
            project = tempfile.mkdtemp(dir=cache_tmp_dir)
            home = tempfile.mkdtemp(dir=cache_tmp_dir)
            for base, text in ((project, setting), (home, home_setting)):
                if text is not None:
                    os.makedirs(os.path.join(base, '.claude'))
                    with open(os.path.join(base, '.claude', 'mode.yml'), 'w', encoding='utf-8') as f:
                        f.write(f'mode: normal\n{text}\n')
            calls: list[list[str]] = []
            inner = make_command_gh([]) if via_today else None

            def fake(args: list[str], input_text: str | None = None) -> tuple[int, str, str]:
                if args[:2] == ['run', 'list']:
                    calls.append(list(args))
                    return gh_result
                return inner(args, input_text)

            env_keys = ('HIRAI_TASK_ROOT', 'HOME')
            saved_env = {k: os.environ.get(k) for k in env_keys}
            saved_gh, saved_now = gh_task.run_gh, gh_task._now_utc
            os.environ.update({'HIRAI_TASK_ROOT': project, 'HOME': home})
            gh_task.run_gh = fake
            gh_task._now_utc = lambda: datetime.datetime.fromisoformat(now)
            out = io.StringIO()
            try:
                with redirect_stdout(out):
                    if via_today:
                        orig_flag = gh_task.MIGRATION_ALIGN_WRITE_ENABLED
                        gh_task.MIGRATION_ALIGN_WRITE_ENABLED = False
                        try:
                            assert gh_task.main(['today']) == 0
                        finally:
                            gh_task.MIGRATION_ALIGN_WRITE_ENABLED = orig_flag
                    else:
                        gh_task.print_nightly_ci()
            finally:
                gh_task.run_gh, gh_task._now_utc = saved_gh, saved_now
                for k, v in saved_env.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
            return out.getvalue(), calls

        def _runs(conclusion: str, status: str = 'completed', created: str = '2026-11-23T18:17:09Z') -> tuple[int, str, str]:
            row = {'conclusion': conclusion, 'status': status, 'createdAt': created, 'url': 'https://github.com/o/r/actions/runs/1'}
            return 0, json.dumps([row]), ''

        def _nightly_success() -> None:
            text, calls = _nightly('nightly_ci: ci.yml', _runs('success'))
            assert text == '前夜の CI（ci.yml・11-24 03:17）: 成功\n', repr(text)
            assert calls == [['run', 'list', '-R', 'example-org/example-repo', '--workflow', 'ci.yml', '--event',
                              'schedule', '-L', '1', '--json', 'conclusion,status,createdAt,url']], calls

        t('nightly_ci: 成功の run は「成功」を JST で 1 行に出す（gh の引数も固定）', _nightly_success)

        def _nightly_failure() -> None:
            for conclusion in ('failure', 'cancelled', 'timed_out'):
                text, _ = _nightly('nightly_ci: "ci.yml"  # 夜の CI', _runs(conclusion))
                assert text == ('前夜の CI（ci.yml・11-24 03:17）: 失敗 https://github.com/o/r/actions/runs/1'
                                ' — 赤のまま放置しない\n'), (conclusion, text)

        t('nightly_ci: failure・cancelled・timed_out は「失敗」と url を出す（引用符・行末コメントは外す）', _nightly_failure)

        def _nightly_in_progress() -> None:
            text, _ = _nightly('nightly_ci: ci.yml', _runs('', 'in_progress'))
            assert text == '前夜の CI（ci.yml・11-24 03:17）: 実行中\n', repr(text)

        t('nightly_ci: 実行中の run は「実行中」', _nightly_in_progress)

        def _nightly_no_run() -> None:
            text, calls = _nightly('nightly_ci: ci.yml', (0, '[]', ''))
            assert text == '前夜の CI（ci.yml）: schedule の run がまだ無い\n', repr(text)
            assert len(calls) == 1

        t('nightly_ci: run が 0 件なら「まだ無い」（取れないとは別の文）', _nightly_no_run)

        def _nightly_unreadable() -> None:
            text, _ = _nightly('nightly_ci: ci.yml', (1, '', 'HTTP 403: rate limit\nsecond line'))
            assert text == '前夜の CI（ci.yml）: 取れない（HTTP 403: rate limit）\n', repr(text)
            text, _ = _nightly('nightly_ci: ci.yml', (0, 'not json', ''))
            assert text.startswith('前夜の CI（ci.yml）: 取れない（gh の出力を読めない') and 'まだ無い' not in text, repr(text)
            text, _ = _nightly('nightly_ci: ci.yml', (0, '[{"status": "completed"}]', ''))
            assert text.startswith('前夜の CI（ci.yml）: 取れない（'), repr(text)

        t('nightly_ci: gh の失敗・JSON の崩れ・欠けた項目は「取れない（理由）」で 0 件と分ける', _nightly_unreadable)

        def _nightly_unset_calls_no_gh() -> None:
            for setting in (None, 'tasks: github-project', 'nightly_ci:', 'nightly_ci: # 空'):
                text, calls = _nightly(setting, _runs('success'))
                assert text == '' and calls == [], (setting, text, calls)

        t('nightly_ci: 設定が無い・空なら何も出さず gh を呼ばない', _nightly_unset_calls_no_gh)

        def _nightly_home_fallback() -> None:
            text, calls = _nightly(None, _runs('success'), home_setting='nightly_ci: ci.yml')
            assert text == '前夜の CI（ci.yml・11-24 03:17）: 成功\n' and len(calls) == 1, (text, calls)
            text, calls = _nightly('nightly_ci: own.yml', _runs('success'), home_setting='nightly_ci: ci.yml')
            assert calls[0][calls[0].index('--workflow') + 1] == 'own.yml', calls

        t('nightly_ci: プロジェクトの mode.yml が先・無ければホーム（土台の harness_yml_value と同じ）', _nightly_home_fallback)

        def _nightly_stale() -> None:
            text, _ = _nightly('nightly_ci: ci.yml', _runs('success'), now='2026-11-25T07:17:10+00:00')
            assert text == '前夜の CI（ci.yml・11-24 03:17）: 成功（36 時間より古い）\n', repr(text)
            text, _ = _nightly('nightly_ci: ci.yml', _runs('success'), now='2026-11-25T06:17:09+00:00')
            assert '古い' not in text, repr(text)

        t('nightly_ci: 36 時間より古い run には注記を足す（ちょうど 36 時間は足さない）', _nightly_stale)

        def _nightly_bad_value() -> None:
            text, calls = _nightly('nightly_ci: ../x y.yml', _runs('success'))
            assert '取れない' in text and calls == [], (text, calls)

        t('nightly_ci: workflow のファイル名でない値は gh に渡さない', _nightly_bad_value)

        def _nightly_in_today() -> None:
            text, calls = _nightly('nightly_ci: ci.yml', _runs('failure'), via_today=True)
            assert text.startswith('前夜の CI（ci.yml・11-24 03:17）: 失敗 '), repr(text[:120])
            assert len(calls) == 1
            text, calls = _nightly(None, _runs('failure'), via_today=True)
            assert '前夜の CI' not in text and calls == [], (text[:120], calls)

        t('nightly_ci: today の出力の先頭に 1 行だけ入り、設定が無ければ today は変わらない', _nightly_in_today)

        def _after_merge_no_closing_refs() -> None:
            gh_task.run_gh = make_command_gh([], closing_refs={})
            out = io.StringIO()
            with redirect_stdout(out):
                rc = gh_task.main(['after-merge', '71'])
            assert rc == 0
            assert '閉じた issue が無い' in out.getvalue()

        t('after-merge は closingIssuesReferences が空なら何もしない', _after_merge_no_closing_refs)

        def _after_merge_removable_worktrees() -> None:
            # 出力の末尾に「消してよい worktree: N 本」を 1 行（0 本・道具が無い・道具が失敗のときは出さない）。偽の hirai-worktrees を PATH に置く。
            gh_task.run_gh = make_command_gh([], closing_refs={})
            saved_path = os.environ.get('PATH', '')

            def tail(payload: str | None, rc: int = 0) -> str:
                bindir = tempfile.mkdtemp(dir=cache_tmp_dir)
                if payload is not None:
                    tool = os.path.join(bindir, 'hirai-worktrees')
                    with open(tool, 'w', encoding='utf-8') as fh:
                        fh.write("#!/bin/sh\ncat <<'EOF'\n%s\nEOF\nexit %d\n" % (payload, rc))
                    os.chmod(tool, 0o755)
                os.environ['PATH'] = bindir + os.pathsep + '/usr/bin' + os.pathsep + '/bin'
                out = io.StringIO()
                try:
                    with redirect_stdout(out):
                        assert gh_task.main(['after-merge', '71']) == 0
                finally:
                    os.environ['PATH'] = saved_path
                return out.getvalue()

            rows = json.dumps([{'verdict': '消してよい', 'evacuate': []},
                               {'verdict': '残す', 'evacuate': [{'dir': '.tmp', 'count': 3}]},
                               {'verdict': '消してよい', 'evacuate': [{'dir': '.tmp', 'count': 3}]}], ensure_ascii=False)
            text = tail(rows)
            want = '消してよい worktree: 2 本（うち退避が要る 1 本。`hirai-worktrees list` で見る）'
            assert text.rstrip('\n').splitlines()[-1] == want, repr(text)
            assert '消してよい worktree' not in tail(json.dumps([{'verdict': '残す'}])), '0 本なのに出した'
            assert '消してよい worktree' not in tail(None), '道具が無いのに出した'
            assert '消してよい worktree' not in tail(rows, rc=2), '道具が失敗したのに出した'
            assert '消してよい worktree' not in tail('not json'), '読めない出力で出した'

        t('after-merge の末尾に「消してよい worktree: N 本」を 1 行（0 本・道具なし・失敗では出さない）', _after_merge_removable_worktrees)

        # ── 書き込みのあとの件数の取り直し（refresh_board_counts・_entry） ──
        def _fake_plugin(function_body: str) -> tuple[str, str]:
            """ghp-path.sh の偽物を持つプラグインの置き場所と、呼ばれた記録のパスを返す。"""
            root = tempfile.mkdtemp(dir=cache_tmp_dir)
            os.makedirs(os.path.join(root, 'scripts'))
            marker = os.path.join(root, 'called.txt')
            with open(os.path.join(root, 'scripts', 'ghp-path.sh'), 'w', encoding='utf-8') as f:
                f.write(f'harness_ghp_refresh() {{\n  printf "%s|%s\\n" "$1" "$2" >> "{marker}"\n{function_body}\n}}\n')
            return root, marker

        def _with_plugin_root(root: str, fn) -> None:
            saved = os.environ.get('HIRAI_TASK_PLUGIN_ROOT')
            os.environ['HIRAI_TASK_PLUGIN_ROOT'] = root
            try:
                fn()
            finally:
                if saved is None:
                    os.environ.pop('HIRAI_TASK_PLUGIN_ROOT', None)
                else:
                    os.environ['HIRAI_TASK_PLUGIN_ROOT'] = saved

        def _refresh_calls_now_with_root() -> None:
            root, marker = _fake_plugin('return 0')
            _with_plugin_root(root, gh_task.refresh_board_counts)
            with open(marker, encoding='utf-8') as f:
                lines = f.read().splitlines()
            assert lines == [f'now|{gh_task._root()}'], f'harness_ghp_refresh now <root> を 1 回呼ぶはず: {lines}'

        t('refresh_board_counts は ghp-path.sh の harness_ghp_refresh now <作業ツリー> を呼ぶ', _refresh_calls_now_with_root)

        def _entry_refreshes_only_after_a_write() -> None:
            root, marker = _fake_plugin('return 0')

            def _read_marker() -> list[str]:
                try:
                    with open(marker, encoding='utf-8') as f:
                        return f.read().splitlines()
                except FileNotFoundError:
                    return []

            def _run() -> None:
                gh_task._state['wrote'] = False
                assert gh_task._entry(['no-such-subcommand']) == 2
                assert _read_marker() == [], f'書いていないのに取り直した: {_read_marker()}'
                gh_task.run_gh = make_command_gh([])
                gh_task.rest('POST', 'repos/x/y/issues/1/comments', {'body': 'x'}, ok_fail=True)
                assert gh_task._state['wrote'] is True, 'REST の POST で書き込みの印が立たない'
                assert gh_task._entry(['no-such-subcommand']) == 2, '取り直しが終了コードを変えた'
                assert len(_read_marker()) == 1, f'書いたのに取り直していない: {_read_marker()}'

            _with_plugin_root(root, _run)
            gh_task._state['wrote'] = False

        t('_entry は書き込みをしたときだけ件数を取り直し、終了コードを変えない', _entry_refreshes_only_after_a_write)

        def _failed_write_does_not_refresh() -> None:
            root, marker = _fake_plugin('return 0')

            def _run() -> None:
                gh_task._state['wrote'] = False
                gh_task.run_gh = lambda args, input_text=None: (1, '', 'boom')
                gh_task.rest('POST', 'repos/x/y/issues/1/comments', {'body': 'x'}, ok_fail=True)
                assert gh_task._state['wrote'] is False, '失敗した REST の書き込みで印が立った'
                try:
                    gh_task.graphql('mutation { x }')
                except gh_task.GhError:
                    pass
                assert gh_task._state['wrote'] is False, '失敗した mutation で印が立った'
                assert not os.path.exists(marker), '書き込みが成功していないのに取り直した'

            _with_plugin_root(root, _run)
            gh_task._state['wrote'] = False

        t('書き込みが失敗したときは書き込みの印を立てず、取り直さない', _failed_write_does_not_refresh)

        def _entry_refreshes_even_on_unexpected_exception() -> None:
            root, marker = _fake_plugin('return 0')
            saved_main = gh_task.main

            def _boom(argv):
                gh_task._state['wrote'] = True
                raise KeyError('unexpected')

            def _run() -> None:
                gh_task.main = _boom
                try:
                    gh_task._entry(['x'])
                    raise AssertionError('例外が握りつぶされた')
                except KeyError:
                    pass
                finally:
                    gh_task.main = saved_main
                assert len(open(marker, encoding='utf-8').read().splitlines()) == 1, '例外のときに取り直していない'

            _with_plugin_root(root, _run)
            gh_task._state['wrote'] = False

        t('GhError 以外の例外が出ても、書いたあとなら件数を取り直し、例外はそのまま投げる', _entry_refreshes_even_on_unexpected_exception)

        def _refresh_failure_and_missing_library_are_silent() -> None:
            root, marker = _fake_plugin('return 1')
            _with_plugin_root(root, gh_task.refresh_board_counts)
            _with_plugin_root(os.path.join(cache_tmp_dir, 'no-such-plugin'), gh_task.refresh_board_counts)

        t('件数の取り直しは、失敗しても本体が無くても例外を出さない', _refresh_failure_and_missing_library_are_silent)

        def _line_plugin(line_body: str) -> tuple[str, str]:
            """harness_ghp_line と harness_ghp_refresh_async の偽物を持つプラグインの置き場所と、呼ばれた記録のパス。"""
            root = tempfile.mkdtemp(dir=cache_tmp_dir)
            os.makedirs(os.path.join(root, 'scripts'))
            marker = os.path.join(root, 'called.txt')
            with open(os.path.join(root, 'scripts', 'ghp-path.sh'), 'w', encoding='utf-8') as f:
                f.write(f'harness_ghp_line() {{\n{line_body}\n}}\n'
                        f'harness_ghp_refresh_async() {{\n  printf "%s|%s\\n" "$1" "$2" >> "{marker}"\n}}\n')
            return root, marker

        def _run_line(root: str, args: list[str]) -> tuple[int, str]:
            out = io.StringIO()
            holder = {}

            def _call() -> None:
                with redirect_stdout(out):
                    holder['rc'] = gh_task.main(['line'] + args)

            _with_plugin_root(root, _call)
            return holder['rc'], out.getvalue()

        def _line_prints_the_cached_line_and_refreshes_only_with_flag() -> None:
            root, marker = _line_plugin("  printf '3（承認 1・裁定 1・取り込み 1）／進行中 2／待ち解け —（09:00 時点）'")
            rc, out = _run_line(root, [])
            assert rc == 0 and out == '3（承認 1・裁定 1・取り込み 1）／進行中 2／待ち解け —（09:00 時点）', (rc, out)
            assert not os.path.exists(marker), '--refresh なしで背景の取り直しを起こした'
            rc, out = _run_line(root, ['--refresh'])
            assert rc == 0 and out.startswith('3（承認'), (rc, out)
            with open(marker, encoding='utf-8') as f:
                assert f.read().splitlines() == [f'background|{gh_task._root()}'], '--refresh は background を 1 回起こす'

        t('line は控えの 1 行を出し、--refresh のときだけ背景の取り直しを起こす（GitHub も repo の判定も要らない）', _line_prints_the_cached_line_and_refreshes_only_with_flag)

        def _line_is_silent_when_cache_missing_or_library_absent() -> None:
            root, _ = _line_plugin('  return 1')
            rc, out = _run_line(root, [])
            assert rc == 0 and out == '', '控えが無い（harness_ghp_line が rc 1）なら何も出さず exit 0'
            rc, out = _run_line(os.path.join(cache_tmp_dir, 'no-such-plugin'), ['--refresh'])
            assert rc == 0 and out == '', 'ライブラリが無くても exit 0・出力なし'

        t('line は控えが無い・ライブラリが無いとき、何も出さず exit 0', _line_is_silent_when_cache_missing_or_library_absent)

        def _line_rejects_unknown_flag() -> None:
            root, _ = _line_plugin('  return 1')
            try:
                _run_line(root, ['--bogus'])
            except gh_task.GhError as exc:
                assert exc.code == 2, exc.code
                return
            raise AssertionError('未知の引数を受け付けた')

        t('line は未知の引数を exit 2 で断る', _line_rejects_unknown_flag)

        def _state_dirs_live_in_git_dir() -> None:
            import subprocess
            repo = os.path.realpath(tempfile.mkdtemp(dir=cache_tmp_dir))
            git = ['git', '-C', repo, '-c', 'user.name=t', '-c', 'user.email=t@example.com']
            subprocess.run(git + ['init', '-q'], check=True, capture_output=True)
            subprocess.run(git + ['commit', '-q', '--allow-empty', '-m', 'x'], check=True, capture_output=True)
            worktree = os.path.join(repo + '-wt')
            subprocess.run(git + ['worktree', 'add', '-q', worktree, '-b', 'wt'], check=True, capture_output=True)
            worktree = os.path.realpath(worktree)
            saved = os.environ.get('HIRAI_TASK_ROOT')
            try:
                os.environ['HIRAI_TASK_ROOT'] = worktree
                local = os.path.realpath(gh_task._local_state_dir())
                shared = os.path.realpath(gh_task._shared_state_dir())
            finally:
                if saved is None:
                    os.environ.pop('HIRAI_TASK_ROOT', None)
                else:
                    os.environ['HIRAI_TASK_ROOT'] = saved
            assert shared == os.path.join(repo, '.git', 'hirai-task'), f'共有の置き場所が common-dir の下でない: {shared}'
            assert local == os.path.join(repo, '.git', 'worktrees', os.path.basename(worktree), 'hirai-task'), (
                f'checkout ごとの置き場所が git-dir の下でない: {local}'
            )
            os.makedirs(shared)
            with open(os.path.join(shared, 'gh-align-seen.json'), 'w', encoding='utf-8') as f:
                f.write('{}')
            status = subprocess.run(git + ['status', '--porcelain'], capture_output=True, text=True).stdout
            assert status == '', f'控えが作業ツリーに現れて追跡の対象になった: {status!r}'

        t('控えは git ディレクトリの下に置き、worktree で共有し、作業ツリーを汚さない', _state_dirs_live_in_git_dir)

        _board_checks(t, cache_tmp_dir)
        _card_checks(t, cache_tmp_dir)
    finally:
        gh_task.run_gh = orig_run_gh
        gh_task.PROJECT_NUMBER_OVERRIDE = orig_override
        gh_task.FIELDS_CACHE = orig_cache_path
        gh_task.REST_FIELDS_CACHE = orig_rest_cache_path
        gh_task.sleep_fn = orig_sleep_fn
        gh_task._project_node_id_cache.clear()
        gh_task._project_node_id_cache.update(orig_project_node_id_cache)
        gh_task._owner_type_cache = orig_owner_type_cache
        gh_task.JOURNAL_PATH = orig_journal_path
        gh_task.COMMENTS_SINCE_CACHE = orig_comments_since_cache
        gh_task.MERGED_DESIGNS_SINCE_CACHE = orig_merged_designs_since_cache

    for line in results:
        print(line)
    verdict = 'OK' if fail == 0 else 'FAIL'
    print(f'結果: {verdict}')
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
