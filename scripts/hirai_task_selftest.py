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
  7. 書き込みのあとの件数の取り直し（refresh_board_counts）は、プラグイン本体の
     tasks-path.sh を偽物に差し替えて見る（書いたときだけ呼ぶ・失敗しても結果を
     変えない）。gh は呼ばない

落ちる条件: 検査が 1 件でも FAIL → exit 1
失効: タスクの正本を GitHub Projects 以外へ移したとき。
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import tempfile
import urllib.parse
from contextlib import redirect_stdout
from importlib import machinery, util


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
) -> dict:
    field_values = []
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
                            'nodes': [{'number': n, 'state': s} for n, s in blockers],
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
            'nodes': [{'number': n, 'state': s} for n, s in blockers],
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
            'options': [{'id': f"R_{o['id']}", 'name': o['name']} for o in d.get('options', [])],
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
    graphql_writes: list[tuple] | None = None,
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
    return {
        'id': f"ITEM_{i['number']}",
        'content': {
            '__typename': i.get('type', 'Issue'), 'number': i['number'],
            'title': i.get('title', f"row {i['number']}"), 'state': i.get('state', 'OPEN'),
            'url': '',
            'parent': ({'number': i['parent_number']} if i.get('parent_number') is not None else None),
        },
        'fieldValues': {'nodes': field_values},
    }


def make_command_gh(
    items: list[dict], *, bodies: dict[int, str] | None = None,
    summaries: dict[int, dict] | None = None, extras: dict[int, dict] | None = None,
    closing_refs: dict[int, list[int]] | None = None, project_number: int = 7,
    write_log: list[tuple] | None = None, paginate: dict[str, list] | None = None,
):
    """close-parents・align・unblocked・after-merge・today を main([...]) 経由で走らせる
    ための、まとまった偽 gh。write_log には、実際に書き込みが起きたときだけ 1 行ずつ積む
    （GraphQL の更新は ('graphql-update', field_id, option_id_or_text)、REST の項目の値の
    更新は ('item-update', field_id, value)、それ以外の REST は
    (method, path, body) の 3 要素）。paginate は `--paginate` の応答を、path に含まれる
    部分文字列で切り分ける（comments・repo_only_issue_numbers・merged-designs のテストが
    使う。既定はどれも []）。"""
    bodies = bodies or {}
    summaries = summaries or {}
    extras = extras or {}
    closing_refs = closing_refs or {}
    paginate = paginate or {}
    items_by_number = {i['number']: i for i in items}
    _reset_rest_fields_cache()
    gh_task._owner_type_cache = None

    def fake_run_gh(args: list[str], input_text: str | None = None) -> tuple[int, str, str]:
        joined = ' '.join(args)
        if 'repositoryOwner' in joined:
            return 0, json.dumps({'data': {'repositoryOwner': {'__typename': 'Organization'}}}), ''
        if '--paginate' in args:
            idx = args.index('--paginate')
            path = args[idx + 1] if len(args) > idx + 1 else ''
            if re.search(r'projectsV2/\d+/fields', path):
                return 0, json.dumps(_fake_rest_field_defs(_fake_field_defs())), ''
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
                    data[f'i{i}'] = {
                        'issue': {
                            'number': number,
                            'blockedBy': {
                                'totalCount': len(blocker_numbers),
                                'nodes': [{'number': n, 'state': 'OPEN'} for n in blocker_numbers],
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
                state=item.get('state', 'OPEN'), parent_number=item.get('parent_number'),
                status=item.get('status', ''), kind=item.get('kind', ''),
            )), ''
        if 'project field-list' in joined:
            return 0, json.dumps({'fields': _fake_field_defs()}), ''
        if len(args) >= 2 and args[0] == 'api' and args[1] == '-X':
            method, path = args[2], args[3]
            body = json.loads(input_text) if input_text else None
            builtin = _fake_rest_project_call(
                method, path, body, items_by_number, _fake_field_defs(), None, None, None,
            )
            if builtin is not None:
                if method == 'PATCH' and write_log is not None:
                    for fid_back, value_back in _rest_patch_to_graphql_ids(
                        _fake_field_defs(), (body or {}).get('fields', []),
                    ) or []:
                        write_log.append(('item-update', fid_back, value_back))
                return 0, json.dumps(builtin), ''
            m = re.match(r'^repos/[^/]+/[^/]+/issues/(\d+)$', path)
            if method == 'GET' and m:
                number = int(m.group(1))
                return 0, json.dumps({
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
    # align 以下が使うキャッシュ（align-seen・journal・since の 2 つ）も、実ファイルに触れず
    # 隔離する（同じ考え方。汚染すると次に道具を回す会話の状態を書き換えてしまう）。
    orig_align_seen_cache = gh_task.ALIGN_SEEN_CACHE
    orig_journal_path = gh_task.JOURNAL_PATH
    orig_comments_since_cache = gh_task.COMMENTS_SINCE_CACHE
    orig_merged_designs_since_cache = gh_task.MERGED_DESIGNS_SINCE_CACHE
    gh_task.ALIGN_SEEN_CACHE = f'{cache_tmp_dir}/gh-align-seen.json'
    gh_task.JOURNAL_PATH = f'{cache_tmp_dir}/gh-task-journal.jsonl'
    gh_task.COMMENTS_SINCE_CACHE = f'{cache_tmp_dir}/gh-comments-since.json'
    gh_task.MERGED_DESIGNS_SINCE_CACHE = f'{cache_tmp_dir}/gh-merged-designs-since.json'
    try:
        # 1) 偽の 800 行（8 頁）で ready が全件を読む。
        def _paginates_800() -> None:
            gh_task.run_gh = make_paginated_gh(800)
            items = gh_task.fetch_all_items(7)
            assert len(items) == 801, f'800 件 + 親の feature 1 件のはずが {len(items)} 件しか読めていない'
            rows = gh_task.ready_rows(items, {}, {})
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

        t('set は承認待ち→着手可を断る（feature をボードで着手可にし、align に任せる）', _set_rejects_pending_to_ready)

        def _set_rejects_pending_child_of_ready_feature() -> None:
            # 親の feature が着手可でも、承認待ちの子を set で着手可にしない（そろえるのは
            # align の役目。守りを外すと exit 2 で落ちず、FAIL する）。
            record: list = []
            gh_task.run_gh = make_write_gh({
                640: dict(title='task', status=gh_task.PENDING_STATUS, kind='task', parent_number=641),
                641: dict(title='feature', status=gh_task.READY_STATUS, kind='feature'),
            }, record=record)
            _expect_exit(lambda: gh_task.cmd_set(640, 'Status', gh_task.READY_STATUS), 2)
            assert record == [], f'書き込みが起きた: {record}'

        t(
            'set は親が着手可の feature の、承認待ちの子にも着手可を書かない（exit 2）',
            _set_rejects_pending_child_of_ready_feature,
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

        # ── start（着手可からだけ進める。[操作] は --approved で承認待ちからも） ──
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
            gh_task.run_gh = make_write_gh({624: dict(title='task', status=gh_task.DEP_STATUS, kind='task')})
            _expect_exit(lambda: gh_task.cmd_start(624, None), 2)

        t('start（既定の形）は着手可でなければ断る', _start_default_requires_ready)

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
                    kind='task', body='元の本文',
                )},
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

        t('start（既定の形）は着手可から進行中に進む', _start_default_ready_ok)

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
            'reopen は承認待ち→着手可を断る（set と同じ守りを通す。approve を経由させる）',
            _reopen_rejects_pending_to_ready_even_when_closed,
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
                           kind='task', body='本文')},
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

        def _new_marks_late_addition_when_parent_ready() -> None:
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
            rc = gh_task.cmd_new(['新しい task', '--parent', '702'])
            assert rc == 0
            # 「後から追加」は作成時の最初の本文に入れる（あとで読み直して PATCH しない・
            # 途中で落ちると承認済みの子なのに印が無い状態が残っていた）。
            creates = [
                c for c in rest_calls
                if c[0] == 'POST' and c[1] == f'repos/{gh_task.REPO}/issues'
            ]
            assert creates, 'issue の作成が呼ばれていない'
            assert '後から追加' in creates[0][2]['body']
            patches = [
                c for c in rest_calls
                if c[0] == 'PATCH' and c[1] == f'repos/{gh_task.REPO}/issues/901'
            ]
            assert patches == [], f'作成後に本文の PATCH が要らないはず: {patches}'

        t(
            'new は親の feature が着手可なら、最初の本文に「後から追加」を書く',
            _new_marks_late_addition_when_parent_ready,
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

        # ── ready の厳しい形 ───────────────────────
        def _ready_numbers(items, extras=None, bodies=None) -> list[int]:
            return [r['number'] for r in gh_task.ready_rows(items, extras or {}, bodies or {})]

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

        def _ready_strict_holds_task_while_preceding_wave_open() -> None:
            # P2（910）は P1（900）に止められている。P1 の出る条件（子が全部完了・保留と、
            # 出る条件のコマンドの行）を満たすまで、P2 の下の task は ready に出ない。
            board = _base_board() + [
                {'number': 910, 'type': 'Issue', 'kind': 'wave', 'title': '部品（P2）',
                 'status': '', 'state': 'OPEN', 'parent_number': None},
                {'number': 911, 'type': 'Issue', 'kind': 'feature', 'title': 'f3',
                 'status': gh_task.READY_STATUS, 'state': 'OPEN', 'parent_number': 910},
                _task_row(5, 911),
            ]
            extras = {910: {'blocked_by_numbers': [900], 'blocked_by_open_numbers': [900]}}
            assert _ready_numbers(board, extras, {}) == [1], 'P1 が未了なのに P2 の task が出た'
            # P1 の子（task 1・feature 901）を完了にし、出る条件の行を足すと、P2 の task も出る
            done_board = [
                dict(i, status=gh_task.DONE_STATUS) if i['number'] in (1, 901) else i for i in board
            ]
            done_board = [i for i in done_board if i['number'] != 1] + [_task_row(1, 901, status=gh_task.DONE_STATUS)]
            body = {900: '- 出る条件のコマンド: exit 0（2026-09-30・abc1234）'}
            assert _ready_numbers(done_board, extras, body) == [5], _ready_numbers(done_board, extras, body)
            # 子は全部完了でも、出る条件のコマンドの行が無ければ出ない
            assert _ready_numbers(done_board, extras, {}) == [], '出る条件の行が無いのに出た'

        t('ready は先の wave が出る条件を満たすまで、あとの wave の task を出さない', _ready_strict_holds_task_while_preceding_wave_open)

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
            plan = gh_task.close_parents_plan(items, {}, {100: {'total': 0, 'completed': 0}})
            assert plan['close_parents'] == [], f'子 0 件なのに閉じる対象になった: {plan}'

        t('close-parents は子 0 件の親を閉じない', _close_parents_skips_childless_parent)

        def _close_parents_closes_fully_closed_parent() -> None:
            items = [{'number': 101, 'kind': gh_task.FEATURE_KIND, 'state': 'OPEN', 'title': 'f'}]
            plan = gh_task.close_parents_plan(items, {}, {101: {'total': 3, 'completed': 3}})
            assert plan['close_parents'] == [
                {'number': 101, 'kind': 'feature', 'children_total': 3},
            ], plan

        t('close-parents は直下の子が全部閉じた feature を閉じる対象にする', _close_parents_closes_fully_closed_parent)

        def _close_parents_skips_permanent_wave() -> None:
            items = [{'number': 102, 'kind': gh_task.WAVE_KIND, 'state': 'OPEN', 'title': 'P0'}]
            bodies = {102: gh_task.PERMANENT_MARK}
            plan = gh_task.close_parents_plan(items, bodies, {102: {'total': 5, 'completed': 5}})
            assert plan['close_parents'] == [], f'常設の wave を閉じようとした: {plan}'

        t('close-parents は「- 常設: はい」の wave を閉じない', _close_parents_skips_permanent_wave)

        # wave は「出る条件のコマンド」の行が無ければ、
        # 子が全部閉じていても close-parents では閉じない（wave-holds に回るだけ）。
        def _close_parents_skips_wave_without_exit_line() -> None:
            items = [{'number': 103, 'kind': gh_task.WAVE_KIND, 'state': 'OPEN', 'title': 'P1'}]
            plan = gh_task.close_parents_plan(items, {}, {103: {'total': 2, 'completed': 2}})
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
            plan = gh_task.close_parents_plan(items, bodies, {104: {'total': 2, 'completed': 2}})
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

        def _unblocked_respects_preceding_wave() -> None:
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
            assert rows == [], f'先の wave が未了なのに出た: {rows}'

        t('unblocked は先の wave が未了なら出さない', _unblocked_respects_preceding_wave)

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
            seen_store: dict = {}
            plan = gh_task.align_plan(items, extras, {}, seen_store=seen_store)
            assert plan == {
                'align': [{
                    'feature': 200,
                    'moves': [{'number': 201, 'to': gh_task.READY_STATUS, 'from': gh_task.PENDING_STATUS}],
                    'skipped': [],
                }],
            }, plan
            assert seen_store == {'200': [201]}, f'初めて見た子の一覧が記録されていない: {seen_store}'

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
            plan = gh_task.align_plan(items, extras, {}, seen_store={})
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
            plan = gh_task.align_plan(items, extras, {}, seen_store={})
            entry = plan['align'][0]
            assert entry['moves'] == [], f'目印つきの子を動かした: {entry}'
            assert sorted(entry['skipped']) == [221, 222], entry

        t(
            'align は [操作]・[User] の目印つきの子を動かさず、番号だけを出す',
            _align_skips_marked_children,
        )

        def _align_skips_late_added_body_marker() -> None:
            items = [
                {
                    'number': 230, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                    'state': 'OPEN', 'title': 'F', 'parent_number': None,
                },
                {
                    'number': 231, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                    'state': 'OPEN', 'title': 't', 'parent_number': 230,
                },
            ]
            extras = {231: {'blocked_by_open': 0}}
            bodies = {231: f'{gh_task.LATE_ADD_PREFIX} 2026-09-28 12:00\n'}
            plan = gh_task.align_plan(items, extras, bodies, seen_store={})
            entry = plan['align'][0]
            assert entry['moves'] == [] and entry['skipped'] == [231], entry

        t('align は本文に「- 後から追加:」がある子を動かさない', _align_skips_late_added_body_marker)

        def _align_skips_children_added_after_first_seen() -> None:
            feature = {
                'number': 240, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                'state': 'OPEN', 'title': 'F', 'parent_number': None,
            }
            child_a = {
                'number': 241, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                'state': 'OPEN', 'title': 't1', 'parent_number': 240,
            }
            seen_store: dict = {}
            first_plan = gh_task.align_plan(
                [feature, child_a], {241: {'blocked_by_open': 0}}, {}, seen_store=seen_store,
            )
            assert first_plan['align'][0]['moves'] == [
                {'number': 241, 'to': gh_task.READY_STATUS, 'from': gh_task.PENDING_STATUS},
            ], (
                f'初回で既存の子を動かせていない: {first_plan}'
            )
            # 実運用では、1 回目で動かした 241 は次に読むときには着手可になっている
            # （cmd_align が実際に書き込んだあと。ここでは手で反映させる）。
            child_a_after = dict(child_a, status=gh_task.READY_STATUS)
            child_b = {
                'number': 242, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                'state': 'OPEN', 'title': 't2', 'parent_number': 240,
            }
            second_plan = gh_task.align_plan(
                [feature, child_a_after, child_b],
                {241: {'blocked_by_open': 0}, 242: {'blocked_by_open': 0}},
                {}, seen_store=seen_store,
            )
            entry = second_plan['align'][0]
            assert entry['moves'] == [], f'あとから子になった 242 を動かした: {entry}'
            assert entry['skipped'] == [242], entry
            assert seen_store['240'] == [241], f'初回の一覧が書き換わった: {seen_store}'

        t(
            'align は feature が初めて着手可になった時点の子の一覧に無い子を動かさない'
            '',
            _align_skips_children_added_after_first_seen,
        )

        def _align_seen_cache_is_namespaced_by_repo_and_project() -> None:
            # 控えは checkout に依らない共有の置き場所に、
            # repo・project の組で分けて置く（同じ番号でも別リポ・別 Project では混ざらない）。
            feature = {
                'number': 244, 'kind': gh_task.FEATURE_KIND, 'status': gh_task.READY_STATUS,
                'state': 'OPEN', 'title': 'F', 'parent_number': None,
            }
            child = {
                'number': 245, 'type': 'Issue', 'kind': 'task', 'status': gh_task.PENDING_STATUS,
                'state': 'OPEN', 'title': 't', 'parent_number': 244,
            }
            gh_task.align_plan([feature, child], {245: {'blocked_by_open': 0}}, {}, project_number=7)
            data = gh_task._load_shared_json(gh_task.ALIGN_SEEN_CACHE)
            assert data.get(f'{gh_task.REPO}#7') == {'244': [245]}, (
                f'namespace {gh_task.REPO}#7 に基準が書かれていない: {data}'
            )
            # 別の project_number（同じ repo・同じ feature 番号）は別の名前空間に入り、
            # まだ基準が無いので独立に「初めて見た」と判定する。
            gh_task.align_plan(
                [feature, child], {245: {'blocked_by_open': 0}}, {}, project_number=8,
            )
            data2 = gh_task._load_shared_json(gh_task.ALIGN_SEEN_CACHE)
            assert set(data2) == {f'{gh_task.REPO}#7', f'{gh_task.REPO}#8'}, data2
            assert data2[f'{gh_task.REPO}#8'] == {'244': [245]}, data2

        t(
            'align の基準（gh-align-seen.json）は repo・project の組で名前空間を分ける'
            '',
            _align_seen_cache_is_namespaced_by_repo_and_project,
        )

        def _shared_json_load_warns_on_corrupt_file_and_treats_as_empty() -> None:
            with open(gh_task.ALIGN_SEEN_CACHE, 'w', encoding='utf-8') as f:
                f.write('{not valid json')
            data = gh_task._load_shared_json(gh_task.ALIGN_SEEN_CACHE)
            assert data == {}, f'壊れたファイルを空以外に読んだ: {data}'
            os.remove(gh_task.ALIGN_SEEN_CACHE)

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
            plan = gh_task.align_plan(items, {}, {}, seen_store={})
            entry = plan['align'][0] if plan['align'] else None
            touched: set[int] = set()
            if entry:
                touched |= {m['number'] for m in entry['moves']} | set(entry['skipped'])
            assert not (touched & {251, 252, 253}), f'判断待ち・依存待ち・保留の子に触れた: {touched}'

        t('align は判断待ち・依存待ち・保留の子には触れない', _align_never_touches_non_pending_children)

        def _align_respects_preceding_wave() -> None:
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
            plan = gh_task.align_plan(items, extras, {}, seen_store={})
            entry = plan['align'][0]
            assert entry['moves'] == [
                {'number': 263, 'to': gh_task.DEP_STATUS, 'from': gh_task.PENDING_STATUS},
            ], (
                f'先の wave が未了なのに着手可へ動かした: {entry}'
            )

        t('align は先の wave（P1）が未了なら、子を依存待ちへ動かす', _align_respects_preceding_wave)

        # 「未完了の blocked by があるか、先の wave が未了なら、
        # 依存待ちへ（着手可の子も同じ）」を、着手可の子にも適用する。
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
            seen_store = {'270': [271]}
            plan = gh_task.align_plan(items, extras, {}, seen_store=seen_store)
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
            seen_store = {'272': [273]}
            plan = gh_task.align_plan(items, extras, {}, seen_store=seen_store)
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
            seen_store = {'280': [281]}
            plan = gh_task.align_plan(items, extras, {}, seen_store=seen_store)
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
            seen_store = {'290': [291]}
            plan = gh_task.align_plan(items, extras, {}, seen_store=seen_store)
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

        def _preceding_wave_unresolved_closed_wave_without_line_still_blocks() -> None:
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
            unresolved = gh_task.preceding_wave_unresolved(
                321, items_by_number, children_of, {}, extras,
            )
            assert unresolved is True, (
                '閉じた P1 に行が無いのに、P2 を止めていないと判定した'
            )

        t(
            'preceding_wave_unresolved は、閉じた先の wave でも行が無ければ未了のまま扱う',
            _preceding_wave_unresolved_closed_wave_without_line_still_blocks,
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

        t(
            'today は comments→close-parents→align→一覧・警告行を通しで回し、'
            '切り替えを切ると書き込みの API を呼ばない',
            _today_full_run_smoke,
        )

        def _after_merge_no_closing_refs() -> None:
            gh_task.run_gh = make_command_gh([], closing_refs={})
            out = io.StringIO()
            with redirect_stdout(out):
                rc = gh_task.main(['after-merge', '71'])
            assert rc == 0
            assert '閉じた issue が無い' in out.getvalue()

        t('after-merge は closingIssuesReferences が空なら何もしない', _after_merge_no_closing_refs)

        # ── 書き込みのあとの件数の取り直し（refresh_board_counts・_entry） ──
        def _fake_plugin(function_body: str) -> tuple[str, str]:
            """tasks-path.sh の偽物を持つプラグインの置き場所と、呼ばれた記録のパスを返す。"""
            root = tempfile.mkdtemp(dir=cache_tmp_dir)
            os.makedirs(os.path.join(root, 'scripts'))
            marker = os.path.join(root, 'called.txt')
            with open(os.path.join(root, 'scripts', 'tasks-path.sh'), 'w', encoding='utf-8') as f:
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

        t('refresh_board_counts は tasks-path.sh の harness_ghp_refresh now <作業ツリー> を呼ぶ', _refresh_calls_now_with_root)

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
    finally:
        gh_task.run_gh = orig_run_gh
        gh_task.PROJECT_NUMBER_OVERRIDE = orig_override
        gh_task.FIELDS_CACHE = orig_cache_path
        gh_task.REST_FIELDS_CACHE = orig_rest_cache_path
        gh_task.sleep_fn = orig_sleep_fn
        gh_task._project_node_id_cache.clear()
        gh_task._project_node_id_cache.update(orig_project_node_id_cache)
        gh_task._owner_type_cache = orig_owner_type_cache
        gh_task.ALIGN_SEEN_CACHE = orig_align_seen_cache
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
