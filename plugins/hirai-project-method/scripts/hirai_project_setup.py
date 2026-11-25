#!/usr/bin/env python3
"""
hirai_project_setup.py — このリポの GitHub Project を、hirai-project-method の形
（docs/rules-reference/project-setup.md）に立ち上げる。

  python3 scripts/hirai_project_setup.py [--title <名前>] [--from-template <owner>/<number>] [--apply] [--json]
  python3 scripts/hirai_project_setup.py --selftest

既定は計画を出すだけ（読むだけで、GitHub には 1 バイトも書かない）。--apply を付けたときだけ書く。
Project を作るのは外向きの操作なので、呼ぶ側（/hirai-project-method:project-setup）が計画を見せて承認を取ってから --apply する。

対象のリポは bin/hirai-task と同じく HIRAI_TASK_REPO（既定は `git remote get-url origin`）。
Project の選び方も同じ: HIRAI_TASK_PROJECT があればその番号、無ければリポに紐づいた Project
（0 件なら作る・1 件ならそれ・2 件以上なら「種別」を持つ 1 件、決まらなければ exit 2）。
すでにある Project には足りないものだけを足す。既存の項目・選択肢・ビューは消さず、名前も変えない
（選択肢を足すときは既存の選択肢を id ごと渡す。id を渡さないと、その値を持つ行の値が消える）。

API でできる（--apply で自動にする）: Project の作成か複製、リポへの紐づけ、項目「種別」「着手順」、
Status の 8 値、ビュー 8 枚とその絞り込み（承認ビューは前の版の値のときだけ書き換える）、カードを写す項目「ひとこと」「推奨」と、
承認ビューのその 2 列（今の列の後ろに足す。v2.8.1）。
画面に残る（確認リストに出す）: 組込の自動化の On と設定値（API は読むのと消すのだけ）、
全体ビューの階層表示（Hierarchy）・並べ替え・グループ化（ビューの設定の API は表示する項目だけ）。
出典（2026-11-15 に確かめた）:
  複製で引き継ぐもの: https://docs.github.com/en/issues/planning-and-tracking-with-projects/creating-projects/copying-an-existing-project
    ビュー・カスタム項目・draft issue・設定済みの自動化（auto-add を除く）・insights。行・リポの紐づけは引き継がない。
  mutation と入力の形: https://docs.github.com/en/graphql/reference/projects
    createProjectV2View・updateProjectV2View（filter）・updateProjectV2Field（singleSelectOptions は上書き、
    既存の id を渡すと値が保たれる）。自動化は deleteProjectV2Workflow しか無い（On にする mutation が無い）。

落ちる条件: 引数の誤り・リポが決まらない・Project の候補が決まらない → exit 2（gh を叩く前に見る）／
gh が無い・未ログイン・token に project の scope が無い・gh が失敗した → exit 1。
HIRAI_SETUP_GH は gh の代わりに呼ぶコマンド（selftest が呼び出しを記録するために使う）。
失効: タスクの正本を GitHub Projects 以外へ移したとき。
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

KIND_FIELD = '種別'
ORDER_FIELD = '着手順'
STATUS_FIELD = 'Status'
# project-setup.md 4 章の 8 値。色は GitHub の 8 色、説明は「入るとき」。
STATUS_OPTIONS = (
    ('承認待ち', 'PINK', 'task が Project に入ったとき（自動）'),
    ('着手可', 'ORANGE', '人が feature の着手を承認したとき'),
    ('判断待ち', 'YELLOW', '裁定が要るとき'),
    ('依存待ち', 'RED', '先の task（blocked by）が済んでいないとき'),
    ('進行中', 'BLUE', 'AI が着手したとき'),
    ('レビュー中', 'PURPLE', 'PR が task に紐づいたとき（自動）'),
    ('完了', 'GREEN', 'PR を merge したとき（自動）'),
    ('保留', 'GRAY', '止めると決めたとき'),
)
KIND_OPTIONS = (('wave', 'BLUE', '並びの段'), ('feature', 'GREEN', 'wave × 機能。着手の承認の単位'),
                ('task', 'GRAY', 'feature の PR で閉じる作業'), ('設計メモ', 'YELLOW', '止めた設計'))
# 承認カード（approval-template.md）を承認ビューで読むための項目。`hirai-task card <n> --sync` が書く。
HEADLINE_FIELD = 'ひとこと'
RECOMMEND_FIELD = '推奨'
RECOMMEND_OPTIONS = (('承認する', 'GREEN', 'カードの推奨'), ('条件つき', 'YELLOW', '条件はカードの 1 行目'),
                     ('承認しない', 'GRAY', '取り下げを勧める'))
# project-setup.md 6 章。
VIEWS = (
    ('承認', '種別:feature status:承認待ち'),
    ('裁定', 'status:判断待ち'),
    ('取り込み', 'is:pr is:open'),
    ('全体', '種別:wave'),
    ('止まっているもの', '種別:task status:依存待ち,判断待ち,保留'),
    ('保留中の設計メモ', '種別:設計メモ status:保留'),
    # 人の作業（[User]・[操作]）。題名の部分一致は公式の `field:*TEXT*` の形だけを使う（OR の「,」と * の
    # 組み合わせは docs に無いので 2 枚に分ける。2026-11-15、docs.github.com の Filtering projects で確認）。
    ('人の作業', 'is:open title:*User*'),
    ('人の操作', 'is:open title:*操作*'),
)
# 題名の部分一致は広く拾う（`*[User]*` のように括弧を含む形と、* と引用符の組み合わせは docs に無いので使わない）。
VIEW_NOTES = {'人の作業': '題名に User を含む別の issue も拾う', '人の操作': '題名に「操作」を含む別の issue も拾う'}
# 前の版の値。今の絞り込みがこれと同じときだけ新しい値へ書き換える（利用者が変えた値は変えない）。
OLD_VIEW_FILTERS = {'承認': ('種別:feature status:承認待ち,着手可',)}
# project-setup.md 3 章。
WORKFLOWS = (
    ('Item added to project', '対象は issue だけ（PR は除く）。Set Status = 承認待ち'),
    ('Pull request linked to issue', 'Set Status = レビュー中'),
    ('Item closed', '対象は issue だけ。Set Status = 完了'),
    ('Auto-add to project', 'フィルタ is:pr（リポは紐づけたリポ）'),
    ('Auto-add sub-issues to project', 'On のまま'),
)
NEW_PROJECT_STATUS = ('Todo', 'In Progress', 'Done')  # 作った直後の既定（行が無いので置き換えてよい）
MUTATION_TAGS = ('update-field', 'create-view', 'update-view', 'update-view-columns')
READ_TAGS = ('state', 'project')  # 読むだけの問い合わせ。selftest はこれ以外をすべて書き込みとみなす
WRITE_SUBCOMMANDS = ('create', 'copy', 'link', 'field-create')


class SetupError(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


# ── gh ─────────────────────────────────────────────────────────
def run_gh(args: list[str], stdin: str | None = None) -> tuple[int, str, str]:
    cmd = os.environ.get('HIRAI_SETUP_GH', '').strip() or 'gh'
    try:
        proc = subprocess.run([cmd] + args, capture_output=True, text=True, input=stdin)
    except (FileNotFoundError, PermissionError) as exc:
        raise SetupError('gh が無い。https://cli.github.com/ から入れ、`gh auth login -s project` でログインする', 1) from exc
    return proc.returncode, proc.stdout, proc.stderr


def graphql(query: str, variables: dict) -> dict:
    rc, out, err = run_gh(['api', 'graphql', '--input', '-'], json.dumps({'query': query, 'variables': variables}))
    if rc != 0:
        raise SetupError(f'gh api graphql が失敗した（exit {rc}）: {(err or out).strip()[:400]}', 1)
    try:
        payload = json.loads(out)
    except json.JSONDecodeError as exc:
        raise SetupError(f'gh api graphql が JSON を返さなかった（認証・レート制限を疑う）: {out[:200]}', 1) from exc
    if payload.get('errors'):
        raise SetupError('gh api graphql がエラーを返した: ' + json.dumps(payload['errors'], ensure_ascii=False)[:400], 1)
    return payload.get('data') or {}


def gh_write(args: list[str]) -> str:
    rc, out, err = run_gh(args)
    if rc != 0:
        raise SetupError(f'gh {" ".join(args[:2])} が失敗した（exit {rc}）: {(err or out).strip()[:400]}', 1)
    return out


def resolve_repo() -> tuple[str, str]:
    """bin/hirai-task と同じ: HIRAI_TASK_REPO、無ければ git remote の origin。"""
    repo = os.environ.get('HIRAI_TASK_REPO', '').strip()
    if not repo:
        try:
            proc = subprocess.run(['git', 'remote', 'get-url', 'origin'], capture_output=True, text=True, check=True)
            match = re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$', proc.stdout.strip())
            repo = f'{match.group(1)}/{match.group(2)}' if match else ''
        except (OSError, subprocess.CalledProcessError):
            repo = ''
    owner, _, name = repo.partition('/')
    if not owner or not name or '/' in name:
        raise SetupError('リポを決められない（origin が GitHub のリポでない）。HIRAI_TASK_REPO=<owner>/<repo> で指定できる', 2)
    return owner, name


def preflight(apply: bool) -> list[str]:
    """gh のログインと scope を見る。書くなら project、読むだけなら read:project でもよい。"""
    # --active: アカウントが複数あるとき、使っていないアカウントの scope で判定しない。知らない古い gh では付けずに読み直す。
    rc, out, err = run_gh(['auth', 'status', '--active', '--hostname', 'github.com'])
    if rc != 0 and 'unknown flag' in err:
        rc, out, err = run_gh(['auth', 'status', '--hostname', 'github.com'])
    if rc != 0:
        raise SetupError('gh にログインしていない。`gh auth login -s project` でログインする', 1)
    match = re.search(r'Token scopes:\s*(.*)', out + err)
    if not match:
        return ['token の scope を確かめられなかった（fine-grained token など）。書き込みで落ちたら `gh auth refresh -s project`']
    scopes = set(re.findall(r"'([^']+)'", match.group(1)))
    if not scopes & ({'project'} if apply else {'project', 'read:project'}):
        raise SetupError('token に project の scope が無い。`gh auth refresh -s project` で足す'
                         '（計画を見るだけなら read:project でもよい）', 1)
    return []


# ── 読む ─────────────────────────────────────────────────────────
FRAGMENT = '''fragment P on ProjectV2 { id number title url
  repositories(first: 20) { nodes { nameWithOwner } }
  fields(first: 50) { nodes { ... on ProjectV2FieldCommon { id name dataType }
    ... on ProjectV2SingleSelectField { options { id name color description } } } }
  views(first: 50) { nodes { id number name filter fields(first: 50) { nodes { ... on ProjectV2FieldCommon { id name } } } } }
  workflows(first: 30) { nodes { name enabled } } }'''
STATE_QUERY = '''#hps:state
query($owner:String!, $name:String!) { viewer { login } repositoryOwner(login:$owner) { __typename }
  repository(owner:$owner, name:$name) { projectsV2(first: 20) { nodes { ...P } } } }
''' + FRAGMENT
PROJECT_QUERY = '''#hps:project
query($owner:String!, $number:Int!) { repositoryOwner(login:$owner) { __typename
  ... on Organization { projectV2(number:$number) { ...P } } ... on User { projectV2(number:$number) { ...P } } } }
''' + FRAGMENT
UPDATE_FIELD = '''#hps:update-field
mutation($fieldId:ID!, $options:[ProjectV2SingleSelectFieldOptionInput!]) {
  updateProjectV2Field(input:{fieldId:$fieldId, singleSelectOptions:$options}) { clientMutationId } }'''
CREATE_VIEW = '''#hps:create-view
mutation($projectId:ID!, $name:String!) {
  createProjectV2View(input:{projectId:$projectId, name:$name, layout:TABLE_LAYOUT}) { projectV2View { id number } } }'''
UPDATE_VIEW = '''#hps:update-view
mutation($viewId:ID!, $filter:String!) {
  updateProjectV2View(input:{viewId:$viewId, filter:$filter}) { projectV2View { id } } }'''
# 列（表示する項目）。渡した一覧がそのまま列になるので、今の列の後ろに足した一覧を渡す（今の列を消さない）。
# 2026-11-15、rmp-app の Project #7 の view 5 でこの mutation を当てて、足した列が末尾に出ることを確かめた。
UPDATE_VIEW_COLUMNS = '''#hps:update-view-columns
mutation($viewId:ID!, $fields:[ID!]) {
  updateProjectV2View(input:{viewId:$viewId, configuration:{visibleFieldIds:$fields}}) { projectV2View { id } } }'''
APPROVAL_VIEW = '承認'


def normalize(node: dict | None) -> dict | None:
    if not node:
        return None
    fields = {}
    for f in (node.get('fields') or {}).get('nodes') or []:
        if f and f.get('name'):
            fields[f['name']] = {'id': f.get('id'), 'type': f.get('dataType'), 'options': f.get('options') or []}
    return {
        'id': node.get('id'), 'number': node['number'], 'title': node.get('title') or '', 'url': node.get('url') or '',
        'repos': [r['nameWithOwner'] for r in (node.get('repositories') or {}).get('nodes') or [] if r],
        'fields': fields, 'views': [v for v in (node.get('views') or {}).get('nodes') or [] if v],
        'workflows': {w['name']: bool(w.get('enabled')) for w in (node.get('workflows') or {}).get('nodes') or [] if w},
    }


def read_project(owner: str, number: int) -> dict:
    data = graphql(PROJECT_QUERY, {'owner': owner, 'number': number})
    project = normalize((data.get('repositoryOwner') or {}).get('projectV2'))
    if project is None:
        raise SetupError(f'Project {owner}/#{number} が見つからない（番号・owner・権限を確かめる）', 1)
    return project


def choose_project(linked: list[dict]) -> dict | None:
    """bin/hirai-task の discover_project_number と同じ判定。"""
    if len(linked) <= 1:
        return linked[0] if linked else None
    with_kind = [p for p in linked if KIND_FIELD in p['fields']]
    if len(with_kind) == 1:
        return with_kind[0]
    listing = '\n'.join(f"  #{p['number']} {p['title']}" for p in (with_kind or linked))
    raise SetupError(f'Project の候補が複数ある。HIRAI_TASK_PROJECT で選ぶこと:\n{listing}', 2)


# ── 計画 ─────────────────────────────────────────────────────────
def option_steps(field_name: str, field: dict, wanted: tuple, replace: bool) -> list[dict]:
    names = [o['name'] for o in field['options']]
    missing = [w for w in wanted if w[0] not in names]
    if not missing:
        return []
    if replace:
        keep = [o for o in field['options'] if o['name'] not in NEW_PROJECT_STATUS]
    else:
        keep = list(field['options'])
    options = [{'id': o['id'], 'name': o['name'], 'color': o.get('color') or 'GRAY',
                'description': o.get('description') or ''} for o in keep]
    options += [{'name': n, 'color': c, 'description': d} for n, c, d in missing]
    dropped = [n for n in names if replace and n in NEW_PROJECT_STATUS]
    note = f'（作った直後の既定 {"・".join(dropped)} は置き換える）' if dropped else '（既存の選択肢は id ごと残す）'
    return [{'kind': 'options', 'field': field_name, 'fieldId': field['id'], 'options': options,
             'summary': f'項目「{field_name}」に選択肢 {"・".join(m[0] for m in missing)} を足す{note}',
             'command': 'gh api graphql（updateProjectV2Field）'}]


def plan_existing(project: dict, ctx: dict, *, fresh: bool) -> tuple[list[dict], list[dict]]:
    """project（実物か予測）に足りないものの手順と、変えずに人へ回す食い違いを返す。"""
    n, own = project.get('number'), ctx['gh_owner']
    num = str(n) if n else '<番号>'
    steps, conflicts = [], []
    if ctx['repo'] not in project['repos']:
        steps.append({'kind': 'link', 'summary': f'Project をリポ {ctx["repo"]} に紐づける',
                      'command': f'gh project link {num} --owner {own} --repo {ctx["name"]}'})
    for name, wanted, dtype in ((STATUS_FIELD, STATUS_OPTIONS, 'SINGLE_SELECT'),
                                (KIND_FIELD, KIND_OPTIONS, 'SINGLE_SELECT'), (ORDER_FIELD, None, 'NUMBER'),
                                (HEADLINE_FIELD, None, 'TEXT'), (RECOMMEND_FIELD, RECOMMEND_OPTIONS, 'SINGLE_SELECT')):
        field = project['fields'].get(name)
        if field is None:
            opts = ','.join(w[0] for w in wanted) if wanted else ''
            what = '単一選択: ' + opts if opts else {'NUMBER': '数値', 'TEXT': '文字'}[dtype]
            steps.append({'kind': 'field-create', 'field': name, 'dataType': dtype, 'optionNames': opts,
                          'summary': f'項目「{name}」（{what}）を作る',
                          'command': f'gh project field-create {num} --owner {own} --name {name} --data-type {dtype}'
                                     + (f' --single-select-options {opts}' if opts else '')})
        elif field['type'] != dtype:
            conflicts.append({'what': f'項目「{name}」の型が {field["type"]}（{dtype} が要る）', 'where': f'{ctx["base"]}/settings',
                              'value': f'{dtype} の「{name}」', 'state': '変えていない（行の値が消えるため人が決める）'})
        elif wanted:
            steps += option_steps(name, field, wanted, replace=fresh and name == STATUS_FIELD)
    have = {v['name']: v for v in project['views']}
    for name, flt in VIEWS:
        view = have.get(name)
        if view is None:
            note = f'。{VIEW_NOTES[name]}' if name in VIEW_NOTES else ''
            steps.append({'kind': 'view', 'name': name, 'filter': flt, 'summary': f'ビュー「{name}」（絞り込み {flt}）を作る{note}',
                          'command': 'gh api graphql（createProjectV2View → updateProjectV2View）'})
        elif not (view.get('filter') or '').strip():  # 作ったが絞り込みを入れ損ねたビュー。空だけは入れて立て直す
            steps.append({'kind': 'view-filter', 'name': name, 'viewId': view.get('id'), 'filter': flt,
                          'summary': f'ビュー「{name}」に絞り込み {flt} を入れる（いまは絞り込みなし）',
                          'command': 'gh api graphql（updateProjectV2View）'})
        elif (view.get('filter') or '').strip() in OLD_VIEW_FILTERS.get(name, ()):
            old = view['filter'].strip()
            steps.append({'kind': 'view-filter', 'name': name, 'viewId': view.get('id'), 'filter': flt,
                          'summary': f'ビュー「{name}」の絞り込みを前の版の {old} から {flt} に変える',
                          'command': 'gh api graphql（updateProjectV2View）'})
        elif (view.get('filter') or '').strip() != flt:
            conflicts.append({'what': f'ビュー「{name}」の絞り込みが違う', 'where': view_url(ctx, view),
                              'value': flt, 'state': f'いまは {view.get("filter") or "（なし）"}。変えていない'})
    # 承認ビューに承認カードの 2 列（ひとこと・推奨）を出す。作るビューは列がまだ無いので、作ったあとで足す。
    shown = {f.get('name') for f in view_columns(have.get(APPROVAL_VIEW))}
    add = [n for n in (HEADLINE_FIELD, RECOMMEND_FIELD) if n not in shown]
    if add:
        steps.append({'kind': 'view-columns', 'name': APPROVAL_VIEW, 'add': add,
                      'summary': f'ビュー「{APPROVAL_VIEW}」に列 {"・".join(add)} を出す（今の列は消さず、末尾に足す）',
                      'command': 'gh api graphql（updateProjectV2View の configuration.visibleFieldIds）'})
    return steps, conflicts


def view_columns(view: dict | None) -> list[dict]:
    """ビューに今見えている項目（{id, name}）を並びのまま。"""
    return [f for f in ((view or {}).get('fields') or {}).get('nodes') or [] if f and f.get('id')]


def view_url(ctx: dict, view: dict | None) -> str:
    return f'{ctx["base"]}/views/{view["number"]}' if view and view.get('number') else ctx['base']


def checklist(project: dict | None, ctx: dict, route: str) -> list[dict]:
    """画面でしかできない作業。自動化の On/Off は読めるが、設定値（対象・Set Status）は読めない。"""
    rows = []
    for name, value in WORKFLOWS:
        if project is not None and route == 'existing':
            state = ('On（設定値は画面で確かめる）' if project['workflows'][name] else 'Off → On にする') \
                if name in project['workflows'] else '読めなかった（画面で確かめる）'
        elif route == 'template':
            state = {'Auto-add to project': 'On にする（複製では引き継がれない）',
                     'Auto-add sub-issues to project': '複製で引き継ぐか未確認（画面で確かめる）'}.get(
                         name, '複製で引き継ぐ（設定値を画面で確かめる）')
        else:
            state = '作ったあとで On にする'
        rows.append({'what': f'組込の自動化「{name}」', 'where': f'{ctx["base"]}/workflows', 'value': value, 'state': state})
    whole = next((v for v in (project or {}).get('views', []) if v['name'] == '全体'), None)
    rows.append({'what': '全体ビューの階層表示（Hierarchy）', 'where': view_url(ctx, whole),
                 'value': '階層 On・並べ替えなし', 'state': '画面で On にする（API で設定できない）'})
    rows.append({'what': 'wave の並び', 'where': view_url(ctx, whole),
                 'value': '全体ビューで wave の行を並べ替える（行の並び = wave の並び）', 'state': '人が決める'})
    return rows


def base_url(ctx: dict, project: dict | None) -> str:
    if project and project.get('url'):
        return project['url']
    host = 'orgs' if ctx['org'] else 'users'
    return f'https://github.com/{host}/{ctx["owner"]}/projects/<作った番号>'


# ── 実行 ─────────────────────────────────────────────────────────
def execute(step: dict, project: dict, ctx: dict) -> None:
    num, own = str(project['number']), ctx['gh_owner']
    if step['kind'] == 'link':
        gh_write(['project', 'link', num, '--owner', own, '--repo', ctx['name']])
    elif step['kind'] == 'field-create':
        args = ['project', 'field-create', num, '--owner', own, '--name', step['field'], '--data-type', step['dataType']]
        gh_write(args + (['--single-select-options', step['optionNames']] if step['optionNames'] else []))
    elif step['kind'] == 'options':
        graphql(UPDATE_FIELD, {'fieldId': step['fieldId'], 'options': step['options']})
    elif step['kind'] == 'view':
        data = graphql(CREATE_VIEW, {'projectId': project['id'], 'name': step['name']})
        view = ((data.get('createProjectV2View') or {}).get('projectV2View') or {})
        if not view.get('id'):
            raise SetupError(f'ビュー「{step["name"]}」を作れたか分からない（応答に id が無い）', 1)
        graphql(UPDATE_VIEW, {'viewId': view['id'], 'filter': step['filter']})
    elif step['kind'] == 'view-filter':
        graphql(UPDATE_VIEW, {'viewId': step['viewId'], 'filter': step['filter']})
    elif step['kind'] == 'view-columns':
        # 項目とビューはこの回に作ったかもしれないので、id を読み直してから足す
        fresh = read_project(ctx['owner'], project['number'])
        view = next((v for v in fresh['views'] if v.get('name') == step['name']), None)
        missing = [n for n in step['add'] if not (fresh['fields'].get(n) or {}).get('id')]
        if view is None or missing:
            raise SetupError(f'ビュー「{step["name"]}」に列を足せない（'
                             + ('ビューが無い' if view is None else '項目が無い: ' + '・'.join(missing)) + '）', 1)
        columns = view_columns(view)
        names = {f.get('name') for f in columns}
        add = [fresh['fields'][n]['id'] for n in step['add'] if n not in names]
        if add:
            graphql(UPDATE_VIEW_COLUMNS, {'viewId': view['id'], 'fields': [f['id'] for f in columns] + add})
    step['done'] = True


def create_or_copy(ctx: dict, args) -> int:
    if ctx['org'] is False and ctx['gh_owner'] != '@me':
        raise SetupError(f'{ctx["owner"]} は個人のアカウントで、いまのログイン（{ctx["viewer"]}）と違う。'
                         '個人の Project は本人のログインでしか作れない', 1)
    if args['template']:
        t_owner, t_num = args['template']
        out = gh_write(['project', 'copy', str(t_num), '--source-owner', t_owner, '--target-owner', ctx['gh_owner'],
                        '--title', args['title'] or ctx['name'], '--format', 'json'])
    else:
        out = gh_write(['project', 'create', '--owner', ctx['gh_owner'], '--title', args['title'] or ctx['name'], '--format', 'json'])
    try:
        return int(json.loads(out)['number'])
    except (ValueError, KeyError, TypeError) as exc:
        raise SetupError(f'作った Project の番号を読めなかった: {out[:200]}', 1) from exc


def parse_args(argv: list[str]) -> dict:
    args = {'apply': False, 'json': False, 'title': None, 'template': None, 'selftest': False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--apply', '--json', '--selftest'):
            args[a[2:]] = True
        elif a in ('--title', '--from-template'):
            if i + 1 >= len(argv) or not argv[i + 1].strip() or argv[i + 1].startswith('--'):
                raise SetupError(f'{a} に値が要る', 2)
            value = argv[i + 1].strip()
            i += 1
            if a == '--title':
                args['title'] = value
            else:
                m = re.fullmatch(r'([A-Za-z0-9][A-Za-z0-9-]*)/([0-9]+)', value)
                if not m or int(m.group(2)) < 1:
                    raise SetupError(f'--from-template は <owner>/<番号>（{value} は不正）', 2)
                args['template'] = (m.group(1), int(m.group(2)))
        elif a in ('-h', '--help'):
            raise SetupError(__doc__.split('\n\n')[1], 0)
        else:
            raise SetupError(f'未知の引数: {a}', 2)
        i += 1
    return args


def run(args: dict) -> dict:
    owner, name = resolve_repo()
    override = os.environ.get('HIRAI_TASK_PROJECT', '').strip()
    if override and not override.isdigit():
        raise SetupError(f'HIRAI_TASK_PROJECT は番号（{override} は不正）', 2)
    warnings = preflight(args['apply'])
    data = graphql(STATE_QUERY, {'owner': owner, 'name': name})
    if data.get('repository') is None:
        raise SetupError(f'リポ {owner}/{name} を読めなかった（名前・権限を確かめる）', 1)
    org = (data.get('repositoryOwner') or {}).get('__typename') != 'User'
    viewer = (data.get('viewer') or {}).get('login') or ''
    ctx = {'owner': owner, 'name': name, 'repo': f'{owner}/{name}', 'org': org, 'viewer': viewer,
           'gh_owner': owner if org or viewer != owner else '@me'}
    linked = [normalize(n) for n in (data['repository'].get('projectsV2') or {}).get('nodes') or [] if n]
    project = read_project(owner, int(override)) if override else choose_project(linked)
    route = 'existing' if project else ('template' if args['template'] else 'create')
    steps: list[dict] = []
    if route == 'existing' and args['template']:
        warnings.append('すでに Project があるので複製しない（--from-template は使わなかった）')
    if project is None:
        if route == 'template':
            predicted = dict(read_project(*args['template']), repos=[], url='', number=None, id=None)
            src = f'{args["template"][0]}/#{args["template"][1]}'
            steps.append({'kind': 'copy', 'summary': f'Project {src} を複製する（ビュー・項目・自動化（auto-add を除く）を引き継ぐ）',
                          'command': f'gh project copy {args["template"][1]} --source-owner {args["template"][0]} '
                                     f'--target-owner {ctx["gh_owner"]} --title {shlex.quote(args["title"] or name)}'})
        else:
            predicted = {'id': None, 'number': None, 'title': '', 'url': '', 'repos': [], 'views': [], 'workflows': {},
                         'fields': {STATUS_FIELD: {'id': None, 'type': 'SINGLE_SELECT',
                                                   'options': [{'id': None, 'name': s} for s in NEW_PROJECT_STATUS]}}}
            steps.append({'kind': 'create', 'summary': f'Project「{args["title"] or name}」を作る',
                          'command': f'gh project create --owner {ctx["gh_owner"]} --title {shlex.quote(args["title"] or name)}'})
    ctx['base'] = base_url(ctx, project)
    created = None
    try:
        if args['apply'] and project is None:
            created = create_or_copy(ctx, args)
            project = read_project(owner, created)
            steps[0]['done'] = True
            ctx['base'] = base_url(ctx, project)
        rest, conflicts = plan_existing(project or predicted, ctx, fresh=(route == 'create'))
        steps += rest
        if args['apply']:
            for step in rest:
                execute(step, project, ctx)
            project = read_project(owner, project['number'])
    except SetupError as exc:
        if created is None:
            raise
        # 作った Project はまだリポに紐づいていないことがある。回し直しで 2 つ目を作らせない。
        raise SetupError(f'{exc}\nProject #{created} は作った。続きは HIRAI_TASK_PROJECT={created} を付けて回し直す'
                         '（足りない分だけの計画になる）', exc.code) from exc
    rows = checklist(project, ctx, 'existing' if args['apply'] else route) + conflicts
    shown = project or {}
    hint = f'gh project mark-template {shown.get("number") or "<番号>"} --owner {owner}' if org else None
    return {'applied': args['apply'], 'repo': ctx['repo'], 'ownerType': 'Organization' if org else 'User', 'route': route,
            'project': {k: shown.get(k) for k in ('number', 'title', 'url')} if shown else None,
            'steps': [{k: s.get(k) for k in ('kind', 'summary', 'command')} | {'done': bool(s.get('done'))} for s in steps],
            'checklist': rows, 'templateHint': hint, 'warnings': warnings}


def render(result: dict) -> str:
    applied = result['applied']
    head = '書いた（--apply）' if applied else '計画のみ。GitHub には何も書いていない。書くには --apply'
    lines = [f'GitHub Project の立ち上げ（{head}）',
             f'リポ: {result["repo"]}（{"組織" if result["ownerType"] == "Organization" else "個人"}）']
    p = result['project']
    if p:
        lines.append(f'Project: #{p["number"]} {p["title"]} {p["url"]}')
    else:
        lines.append('Project: まだ無い（リポに紐づいた Project が 0 件）')
    lines += [f'注意: {w}' for w in result['warnings']]
    steps = result['steps']
    lines.append('')
    lines.append(f'API で{"行ったこと" if applied else "行うこと"}（{len(steps)} 件）:' if steps
                 else 'API で行うこと: 0 件（項目・選択肢・ビュー・紐づけはそろっている）')
    for i, s in enumerate(steps, 1):
        mark = '済 ' if s['done'] else ''
        lines.append(f'  {i}. {mark}{s["summary"]}')
        lines.append(f'     {s["command"]}')
    lines += ['', '画面で行うこと（API ではできない・読めない）:', '| 何を | どこで | どの値で | いま |', '|---|---|---|---|']
    lines += [f'| {r["what"]} | {r["where"]} | {r["value"]} | {r["state"]} |' for r in result['checklist']]
    if result['templateHint']:
        lines += ['', f'ほかのリポでも同じ形で始めるなら、組織のテンプレートにする: {result["templateHint"]}'
                      '（次からは --from-template で複製できる）']
    lines += ['', '立ち上げ後の確かめ: docs/rules-reference/project-setup.md 8 章（hirai-task ready が空でもエラーにならない ほか）']
    return '\n'.join(lines)


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
        if args['selftest']:
            return selftest()
        result = run(args)
    except SetupError as exc:
        print(str(exc), file=sys.stdout if exc.code == 0 else sys.stderr)
        return exc.code
    print(json.dumps(result, ensure_ascii=False, indent=2) if args['json'] else render(result))
    return 0


# ── selftest（偽の gh で、呼んだ引数と順番を見る） ───────────────────────────
FAKE_GH = r'''#!/usr/bin/env python3
import json, os, re, sys
sc = json.load(open(os.environ["FAKE_GH_SCENARIO"]))
log = os.environ["FAKE_GH_LOG"]
argv = sys.argv[1:]
body = json.loads(sys.stdin.read()) if argv[:3] == ["api", "graphql", "--input"] else None
tag = re.match(r"#hps:([\w-]+)", body["query"]).group(1) if body else ""
seen = sum(1 for line in open(log) if json.loads(line)["tag"] == tag) if tag else 0
with open(log, "a") as fh:
    fh.write(json.dumps({"argv": argv, "tag": tag, "vars": body and body["variables"]}, ensure_ascii=False) + "\n")
if argv[:2] == ["auth", "status"]:
    if sc.get("no_active") and "--active" in argv:
        sys.stderr.write("unknown flag: --active"); sys.exit(1)
    sys.stderr.write(sc.get("auth", "")); sys.exit(sc.get("auth_rc", 0))
if tag:
    out = sc["graphql"].get(tag, {"data": {}} if tag.startswith(("update-", "create-")) else None)
    if out is None:
        sys.stderr.write("fake gh: no answer for " + tag); sys.exit(9)
    print(json.dumps(out[min(seen, len(out) - 1)] if isinstance(out, list) else out)); sys.exit(0)
if argv[:2] in (["project", "create"], ["project", "copy"]):
    print(json.dumps(sc[argv[1]])); sys.exit(0)
if argv[:2] == ["project", "link"] and sc.get("link_fail"):
    sys.stderr.write("boom"); sys.exit(1)
if argv[:2] in (["project", "link"], ["project", "field-create"]):
    print("{}"); sys.exit(0)
sys.stderr.write("fake gh: unexpected " + " ".join(argv)); sys.exit(9)
'''
AUTH_OK = "github.com\n  ✓ Logged in to github.com account me (keyring)\n  - Token scopes: 'gist', 'project', 'repo'\n"


def _proj(number, org=True, repos=(), status=(), kind=None, order=False, views=(), workflows=None, owner='acme', cards=False,
          view_cards=None):
    fields = [{'id': 'F_t', 'name': 'Title', 'dataType': 'TITLE'}]
    if status is not None:
        fields.append({'id': 'F_s', 'name': STATUS_FIELD, 'dataType': 'SINGLE_SELECT',
                       'options': [{'id': f's{i}', 'name': n, 'color': 'GRAY', 'description': 'd'} for i, n in enumerate(status)]})
    if kind is not None:
        fields.append({'id': 'F_k', 'name': KIND_FIELD, 'dataType': 'SINGLE_SELECT',
                       'options': [{'id': f'k{i}', 'name': n, 'color': 'BLUE', 'description': ''} for i, n in enumerate(kind)]})
    if order:
        fields.append({'id': 'F_o', 'name': ORDER_FIELD, 'dataType': 'NUMBER'})
    if cards:
        fields.append({'id': 'F_h', 'name': HEADLINE_FIELD, 'dataType': 'TEXT'})
        fields.append({'id': 'F_r', 'name': RECOMMEND_FIELD, 'dataType': 'SINGLE_SELECT',
                       'options': [{'id': f'r{i}', 'name': n, 'color': 'GRAY', 'description': ''}
                                   for i, (n, _c, _d) in enumerate(RECOMMEND_OPTIONS)]})
    return {'id': f'PVT_{number}', 'number': number, 'title': f'p{number}',
            'url': f'https://github.com/{"orgs" if org else "users"}/{owner}/projects/{number}',
            'repositories': {'nodes': [{'nameWithOwner': r} for r in repos]}, 'fields': {'nodes': fields},
            'views': {'nodes': [{'id': f'V{i}', 'number': i + 1, 'name': n, 'filter': f, 'fields': {'nodes': (
                [{'id': 'F_t', 'name': 'Title'}, {'id': 'F_s', 'name': STATUS_FIELD}]
                + ([{'id': 'F_h', 'name': HEADLINE_FIELD}, {'id': 'F_r', 'name': RECOMMEND_FIELD}]
                   if (cards if view_cards is None else view_cards) and n == '承認' else []))}}
                for i, (n, f) in enumerate(views)]},
            'workflows': {'nodes': [{'name': n, 'enabled': e} for n, e in (workflows or {}).items()]}}


def _state(projects, org=True, viewer='me'):
    return {'data': {'viewer': {'login': viewer}, 'repositoryOwner': {'__typename': 'Organization' if org else 'User'},
                     'repository': {'projectsV2': {'nodes': projects}}}}


def _pq(project, org=True):
    return {'data': {'repositoryOwner': {'__typename': 'Organization' if org else 'User', 'projectV2': project}}}


def selftest() -> int:
    tmp = tempfile.mkdtemp(prefix='hps-selftest-')
    fake = os.path.join(tmp, 'gh')
    with open(fake, 'w') as fh:
        fh.write(FAKE_GH)
    os.chmod(fake, 0o755)
    failures = []

    def run_case(scenario, argv, repo='acme/app', extra=None):
        sc, log = os.path.join(tmp, 'sc.json'), os.path.join(tmp, 'log.jsonl')
        with open(sc, 'w') as fh:
            json.dump({'auth': AUTH_OK, **scenario}, fh, ensure_ascii=False)
        open(log, 'w').close()
        env = {k: v for k, v in os.environ.items() if k not in ('HIRAI_TASK_PROJECT', 'HIRAI_TASK_REPO')}
        env.update({'HIRAI_SETUP_GH': fake, 'FAKE_GH_SCENARIO': sc, 'FAKE_GH_LOG': log, 'HIRAI_TASK_REPO': repo})
        env.update(extra or {})
        proc = subprocess.run([sys.executable, os.path.abspath(__file__)] + argv, capture_output=True, text=True, env=env, cwd=tmp)
        with open(log) as fh:
            calls = [json.loads(line) for line in fh]
        return proc.returncode, proc.stdout + proc.stderr, calls

    def writes(calls):
        # 読むと分かっている呼び出し（auth status と、問い合わせの state・project）以外はすべて書き込みとみなす。
        # mutation や gh のサブコマンドが増えても「書いていない」と空振りしないため。
        return [c for c in calls if c['tag'] not in READ_TAGS if c['tag'] or c['argv'][:2] != ['auth', 'status']]

    def expect(name, want, got):
        print(('PASS ' if want == got else 'FAIL ') + name + ('' if want == got else f'（期待 {want!r}・実測 {got!r}）'))
        if want != got:
            failures.append(name)

    full = ['承認待ち', '着手可', '判断待ち', '依存待ち', '進行中', 'レビュー中', '完了', '保留']
    wf_all = {n: True for n, _ in WORKFLOWS}
    done = _proj(7, repos=('acme/app',), status=full, kind=['wave', 'feature', 'task', '設計メモ'], order=True,
                 views=VIEWS, workflows=wf_all, cards=True)
    empty = _state([])
    new_pq = _pq(_proj(3, status=list(NEW_PROJECT_STATUS), views=[('View 1', '')]))

    for bad in (['--bogus'], ['--from-template', 'acme'], ['--from-template', 'acme/0'], ['--title'], ['--title', '--apply']):
        rc, _, calls = run_case({'graphql': {}}, bad)
        expect(f'不正な引数 {bad} は exit 2 で gh を呼ばない', (2, 0), (rc, len(calls)))
    rc, _, calls = run_case({'graphql': {}}, [], repo='nope')
    expect('リポが決まらないと exit 2 で gh を呼ばない', (2, 0), (rc, len(calls)))
    rc, out, _ = run_case({'graphql': {}}, [], extra={'HIRAI_SETUP_GH': os.path.join(tmp, 'missing')})
    expect('gh が無いと exit 1 で入れ方を出す', (1, True), (rc, 'cli.github.com' in out))
    rc, out, calls = run_case({'auth_rc': 1, 'graphql': {}}, [])
    expect('未ログインは exit 1 で gh auth login を出し、ほかを呼ばない', (1, True, 1), (rc, 'gh auth login' in out, len(calls)))
    rc, out, calls = run_case({'auth': "  - Token scopes: 'repo'\n", 'graphql': {}}, [])
    expect('project の scope が無いと exit 1 で gh auth refresh -s project を出す', (1, True, 1),
           (rc, 'gh auth refresh -s project' in out, len(calls)))
    rc, _, _ = run_case({'auth': "  - Token scopes: 'read:project', 'repo'\n", 'graphql': {'state': _state([done])}}, [])
    expect('計画だけなら read:project で通る', 0, rc)
    rc, _, _ = run_case({'auth': "  - Token scopes: 'read:project'\n", 'graphql': {}}, ['--apply'])
    expect('--apply は read:project では通さない', 1, rc)

    rc, out, calls = run_case({'graphql': {'state': empty}}, [])
    expect('dry-run（Project なし・組織）は書き込みを 1 回も呼ばない', (0, []), (rc, writes(calls)))
    expect('dry-run は作成・紐づけ・項目 4・Status・ビュー 8 を計画する', (True, True, 4, True, 8),
           ('gh project create --owner acme' in out, 'gh project link <番号> --owner acme --repo app' in out,
            out.count('gh project field-create'), '既定 Todo・In Progress・Done は置き換える' in out, out.count('createProjectV2View')))
    expect('組織の URL は orgs/', True, 'https://github.com/orgs/acme/projects/<作った番号>/workflows' in out)
    expect('項目「ひとこと」は文字（TEXT）・「推奨」は 3 択で作る', (True, True),
           (f'--name {HEADLINE_FIELD} --data-type TEXT' in out,
            f'--name {RECOMMEND_FIELD} --data-type SINGLE_SELECT --single-select-options 承認する,条件つき,承認しない' in out))
    expect('人の作業・人の操作のビューは、公式に書かれた形（is:open と title:*文字*）だけで絞る', (True, True),
           ('ビュー「人の作業」（絞り込み is:open title:*User*）' in out, 'ビュー「人の操作」（絞り込み is:open title:*操作*）' in out))
    expect('人の作業・人の操作のビューが、題名に User・操作 を含む別の issue も拾うことを出す', (True, True),
           ('題名に User を含む別の issue も拾う' in out, '題名に「操作」を含む別の issue も拾う' in out))
    rc, out, calls = run_case({'graphql': {'state': _state([], org=False, viewer='acme')}}, [])
    expect('個人（本人）は --owner @me・URL は users/', (0, True, True),
           (rc, 'gh project create --owner @me' in out, 'https://github.com/users/acme/projects/' in out))
    rc, out, calls = run_case({'graphql': {'state': _state([], org=False, viewer='other')}}, ['--apply'])
    expect('個人で本人でないなら --apply は exit 1 で何も書かない', (1, []), (rc, writes(calls)))

    built = _pq(_proj(3, status=full, kind=['wave', 'feature', 'task', '設計メモ'], order=True, cards=True, view_cards=False,
                      views=VIEWS))  # 作ったあとの読み直し（列はまだ出ていない）
    sc = {'create': {'number': 3}, 'graphql': {'state': empty, 'project': [new_pq, built, built],
                                                'create-view': {'data': {'createProjectV2View': {'projectV2View': {'id': 'NV', 'number': 9}}}},
                                                'update-view': {'data': {}}, 'update-field': {'data': {}}}}
    rc, out, calls = run_case(sc, ['--apply', '--title', 'X'])
    seq = [c['tag'] or ' '.join(c['argv'][:2]) for c in calls]
    expect('--apply（新規）の順番', ['auth status', 'state', 'project create', 'project', 'project link', 'update-field',
                                    'project field-create', 'project field-create', 'project field-create', 'project field-create']
           + ['create-view', 'update-view'] * 8 + ['project', 'update-view-columns', 'project'],
           seq)
    create = next(c['argv'] for c in calls if c['argv'][:2] == ['project', 'create'])
    expect('--apply の作成は owner と題名を渡す', ['--owner', 'acme', '--title', 'X'], create[2:6])
    status_vars = next(c['vars'] for c in calls if c['tag'] == 'update-field')
    expect('新規の Status は 8 値だけにする（既定は置き換える）', full, [o['name'] for o in status_vars['options']])
    link = next(c['argv'] for c in calls if c['argv'][:2] == ['project', 'link'])
    expect('紐づけは番号・owner・リポ名', ['3', '--owner', 'acme', '--repo', 'app'], link[2:])
    views = [c['vars'] for c in calls if c['tag'] == 'update-view']
    expect('ビューの絞り込みは 6 章の値', [f for _, f in VIEWS], [v['filter'] for v in views])

    part = _proj(5, repos=('acme/app',), status=['Todo', '承認待ち', 'Done'], kind=['wave', 'task'],
                 views=[('承認', VIEWS[0][1]), ('裁定', 'status:Todo')], workflows={'Item closed': False, 'Auto-add to project': True})
    sc = {'graphql': {'state': _state([part]), 'project': _pq(part), 'update-field': {'data': {}},
                      'create-view': {'data': {'createProjectV2View': {'projectV2View': {'id': 'NV', 'number': 9}}}},
                      'update-view': {'data': {}}}}
    rc, out, calls = run_case(sc, [])
    expect('一部ある Project の dry-run は足りない分だけ（項目 3・選択肢 2・ビュー 6）で書かない', (0, 3, 2, 6, []),
           (rc, out.count('gh project field-create'), out.count('updateProjectV2Field'), out.count('createProjectV2View'), writes(calls)))
    expect('食い違うビューは変えずに表へ出し、自動化の On/Off を読む', (True, True, True),
           ('ビュー「裁定」の絞り込みが違う' in out, 'Off → On にする' in out, 'On（設定値は画面で確かめる）' in out))
    rc, out, calls = run_case(sc, ['--apply'])
    upd = [c['vars'] for c in calls if c['tag'] == 'update-field']
    st = next(u for u in upd if u['fieldId'] == 'F_s')
    expect('既存の選択肢は id ごと先頭に残し、足りない 7 値を足す', (['s0', 's1', 's2'], 10),
           ([o.get('id') for o in st['options'][:3]], len(st['options'])))
    kd = next(u for u in upd if u['fieldId'] == 'F_k')
    expect('種別は wave・task を残して feature・設計メモを足す', ['wave', 'task', 'feature', '設計メモ'],
           [o['name'] for o in kd['options']])
    expect('一部ある Project の --apply は作成・紐づけをしない', [], [c for c in calls if c['argv'][:2] in
                                                                (['project', 'create'], ['project', 'link'], ['project', 'copy'])])

    # 前の --apply で作ったビューに絞り込みを入れ損ねた（updateProjectV2View の失敗）ときの立て直し
    blank = _proj(6, repos=('acme/app',), status=full, kind=['wave', 'feature', 'task', '設計メモ'], order=True, cards=True,
                  views=[(n, '' if n == '止まっているもの' else f) for n, f in VIEWS])
    sc = {'graphql': {'state': _state([blank]), 'project': _pq(blank), 'update-view': {'data': {}}}}
    rc, out, calls = run_case(sc, [])
    expect('絞り込みが空のビューは「絞り込みを入れる」手順にし、食い違いには回さない（dry-run は書かない）',
           (0, True, False, []), (rc, 'ビュー「止まっているもの」に絞り込み' in out, '「止まっているもの」の絞り込みが違う' in out, writes(calls)))
    rc, out, calls = run_case(sc, ['--apply'])
    upd = [c['vars'] for c in calls if c['tag'] == 'update-view']
    expect('空の絞り込みは --apply で updateProjectV2View だけを呼び、ビューを作り直さない',
           (0, [{'viewId': 'V4', 'filter': dict(VIEWS)['止まっているもの']}], []),
           (rc, upd, [c for c in calls if c['tag'] == 'create-view']))

    created = {'link_fail': True, 'create': {'number': 3}, 'graphql': {'state': empty, 'project': [new_pq, new_pq]}}
    rc, out, calls = run_case(created, ['--apply', '--title', 'X'])
    expect('作った直後に紐づけで落ちたら、作った番号と回し直し方を出す（もう 1 つ作らせない）', (1, True),
           (rc, 'HIRAI_TASK_PROJECT=3' in out))
    rc, out, calls = run_case({'graphql': {'state': empty}}, ['--title', 'a b; rm x'])
    expect('計画に出す題名は引用符で囲む（貼り付けてもシェルに解釈されない）', (0, True),
           (rc, "--title 'a b; rm x'" in out))
    rc, out, calls = run_case({'no_active': True, 'graphql': {'state': empty}}, [])
    expect('--active を知らない古い gh では付けずに読み直す', (0, 2),
           (rc, sum(1 for c in calls if c['argv'][:2] == ['auth', 'status'])))

    rc, out, calls = run_case({'graphql': {'state': _state([done]), 'project': _pq(done)}}, ['--apply'])
    expect('そろった Project は --apply でも書かない', (0, [], True), (rc, writes(calls), 'API で行うこと: 0 件' in out))
    rc, _, _ = run_case({'graphql': {'state': _state([_proj(1), _proj(2)])}}, [])
    expect('種別の無い Project が 2 件なら exit 2', 2, rc)
    rc, out, calls = run_case({'graphql': {'state': _state([])}}, [], extra={'HIRAI_TASK_PROJECT': 'x'})
    expect('HIRAI_TASK_PROJECT が番号でないなら exit 2 で gh を呼ばない', (2, 0), (rc, len(calls)))

    tpl = _proj(1, owner='tpl', status=full, kind=['wave', 'feature', 'task', '設計メモ'], order=True, views=VIEWS[:-1], cards=True)
    rc, out, calls = run_case({'graphql': {'state': empty, 'project': _pq(tpl)}}, ['--from-template', 'tpl/1'])
    expect('テンプレートの dry-run は複製・紐づけ・足りないビュー 1 だけで、書かない', (0, True, 1, 0, []),
           (rc, 'gh project copy 1 --source-owner tpl --target-owner acme' in out, out.count('createProjectV2View'),
            out.count('field-create'), writes(calls)))
    expect('テンプレートの経路は Auto-add を画面の作業に回す', True, 'On にする（複製では引き継がれない）' in out)
    expect('承認ビューの列は画面の作業の表に出さない（API で出す）', False,
           f'承認ビューに項目「{HEADLINE_FIELD}」「{RECOMMEND_FIELD}」の列を出す' in out)
    shown = _proj(10, repos=('acme/app',), status=full, kind=['wave', 'feature', 'task', '設計メモ'], order=True, cards=True,
                  view_cards=False, views=VIEWS, workflows=wf_all)
    rc, out, calls = run_case({'graphql': {'state': _state([shown]), 'project': _pq(shown)}}, [])
    expect('承認ビューに列が見えていなければ、計画に「列を出す」手順が出る（書かない）', (0, True, []),
           (rc, f'ビュー「承認」に列 {HEADLINE_FIELD}・{RECOMMEND_FIELD} を出す' in out, writes(calls)))
    rc, out, calls = run_case({'graphql': {'state': _state([shown]), 'project': _pq(shown)}}, ['--apply'])
    cols = [c['vars'] for c in calls if c['tag'] == 'update-view-columns']
    expect('列を出すのは今の列の後ろに 2 つを足した一覧（今の列は消さない・並びを変えない）',
           (0, [{'viewId': 'V0', 'fields': ['F_t', 'F_s', 'F_h', 'F_r']}]), (rc, cols))
    copied = _proj(4, status=full, kind=['wave', 'feature', 'task', '設計メモ'], order=True, views=VIEWS[:-1], cards=True)
    old_view = _proj(8, repos=('acme/app',), status=full, kind=['wave', 'feature', 'task', '設計メモ'], order=True, cards=True,
                     views=[('承認', OLD_VIEW_FILTERS['承認'][0])] + list(VIEWS[1:]))
    rc, out, calls = run_case({'graphql': {'state': _state([old_view]), 'project': _pq(old_view), 'update-view': {'data': {}}}},
                              ['--apply'])
    upd = [c['vars'] for c in calls if c['tag'] == 'update-view']
    expect('承認ビューの絞り込みが旧い値なら新しい値へ書き換える（作り直さない）',
           (0, [{'viewId': 'V0', 'filter': dict(VIEWS)['承認']}], []), (rc, upd, [c for c in calls if c['tag'] == 'create-view']))
    own = _proj(9, repos=('acme/app',), status=full, kind=['wave', 'feature', 'task', '設計メモ'], order=True, cards=True,
                views=[('承認', '種別:feature status:承認待ち label:ui')] + list(VIEWS[1:]))
    rc, out, calls = run_case({'graphql': {'state': _state([own]), 'project': _pq(own)}}, [])
    expect('承認ビューの絞り込みが利用者の値なら書き換えず、食い違いとして表に出す', (0, [], True),
           (rc, writes(calls), 'ビュー「承認」の絞り込みが違う' in out))
    sc = {'copy': {'number': 4}, 'graphql': {'state': empty, 'project': [_pq(tpl), _pq(copied), _pq(copied)],
                                              'create-view': {'data': {'createProjectV2View': {'projectV2View': {'id': 'NV'}}}},
                                              'update-view': {'data': {}}}}
    rc, out, calls = run_case(sc, ['--from-template', 'tpl/1', '--apply'])
    seq = [c['tag'] or ' '.join(c['argv'][:2]) for c in calls]
    expect('テンプレートの --apply は 複製 → 読み直し → 紐づけ → ビュー 1', ['auth status', 'state', 'project', 'project copy', 'project',
                                                                          'project link', 'create-view', 'update-view', 'project'], seq)
    rc, out, _ = run_case({'graphql': {'state': _state([done])}}, ['--json'])
    parsed = json.loads(out) if rc == 0 else {}
    expect('--json は機械可読（route・steps・checklist）', ('existing', 0, 7),
           (parsed.get('route'), len(parsed.get('steps', [1])), len(parsed.get('checklist', []))))
    if failures:
        print(f'FAIL: hirai_project_setup selftest（{len(failures)} 件）')
        return 1
    print('PASS: hirai_project_setup selftest')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
