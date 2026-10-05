# GitHub Project でやることを管理する立ち上げ手順

`/hirai-lite:init` が案内する、GitHub の形（GitHub Project にやることを載せる形）の立ち上げ手順。設定のファイルは作らない。共通の仕組みはプラグインに入っており、案件ごとの中身（wave・feature・順番・期日）は Project の中に持つ。

## 1. 立ち上げの 4 手順

1. Project を作り、リポに紐づける
2. 組込の自動化を On にする（3 章の 4 本）
3. 項目「種別」を作る（4 章）
4. wave と feature の issue を作り、並べ替える（5 章）

## 2. 仕事の組み立て

- **3 段**: wave → feature → task。段は項目「種別」と sub-issue で表す。着手の承認は feature の単位で、人がボードで「着手可」に動かす。着手可の feature の子の task（目印なし）は、あとから足したものも着手してよい
- **task**: PR 1 本で閉じる作業。PR の本文に `Closes #<番号>` を書く
- **止める依存**: blocked by で表す。wave の行の並び順が wave の並び
- **止めた設計**: 種別「設計メモ」・Status「保留」の issue にする。理由と再開条件は本文に書く

## 3. 組込の自動化 4 本の設定値（画面で On にする）

Project の Workflows で次の 4 本を On にする。トークンは要らない。

| 自動化 | 設定値 | 効果 |
|---|---|---|
| Item added to project | 対象は issue だけ（PR は除く）。Set Status = 承認待ち | task が Project に入ったら承認待ち |
| Pull request linked to issue | Set Status = レビュー中 | PR が task に紐づいたらレビュー中 |
| Item closed | 対象は issue だけ。Set Status = 完了 | merge で `Closes` が task を閉じたら完了 |
| Auto-add to project | フィルタ `is:pr`（リポは紐づけたリポ） | PR が Project に入り、取り込みのビューに出る |

- **確かめ方**: 新しい PR の `projectItems.totalCount` が 1 になれば Auto-add が効いている。Item added と Item closed が issue だけに絞れたかは画面で見る
- Auto-add sub-issues to project も On のままにする（sub-issue が Project に入る）

## 4. 項目とその値

- **Status**（単一選択・8 値）: 承認待ち / 着手可 / 判断待ち / 依存待ち / 進行中 / レビュー中 / 完了 / 保留
- **種別**（単一選択・4 値）: wave / feature / task / 設計メモ
- **着手順**（数値・任意）: task の行に入れる。ある Project では `hirai-task ready` が小さい順に出し、値の無い行は後ろに回る（同じ値・無い行どうしは wave の並び順）。wave・feature に入れても効かない。型は Number にする（Text では読まない）

| Status | 入るとき | 動かすもの |
|---|---|---|
| 承認待ち | task が Project に入ったとき | 自動（Item added） |
| 着手可 | feature の着手が承認されたとき | 人が feature を動かし、AI が子の task をそろえる（そろう前でも、先の wave が出ていて未完了の blocked by が無ければ、`hirai-task start` で承認待ちの子を進行中にできる） |
| 判断待ち | 裁定が要るとき | AI |
| 依存待ち | 先の task や wave が済んでいないとき | AI |
| 進行中 | AI が着手したとき | AI（`hirai-task start <n>`） |
| レビュー中 | PR が task に紐づいたとき | 自動（Pull request linked） |
| 完了 | PR を merge したとき | 自動（Item closed） |
| 保留 | 止めると決めたとき | AI |

- AI は feature の「承認待ち → 着手可」を自分で動かさない。着手可の feature の子の task（目印なし・あとから足したものも）は、`hirai-task align`（today が回す）が着手可へ（blocked by か先の wave が済んでいなければ依存待ちへ）動かす。`set`（→ 着手可）・`start`（承認待ち → 進行中）も、align が「着手可へ」と出す子だけを通す。`set` で進行中を書けるのはレビュー中・進行中・完了からだけ（承認待ち・判断待ち・依存待ち・保留・着手可・空からは `start` を使う）。`[操作]`・`[User]` の task は align も set も動かさず、`[操作]` は `start --approved` で進める
- 依存待ち・判断待ち・保留が解けた task は、親 feature の Status に合わせて戻す（着手可なら着手可、承認待ちなら承認待ち）

## 5. wave と feature の作り方

- **wave**: 種別 wave の issue。Project の中での行の並び順が wave の並び（ボードで行を並べ替える）。終わりの無い仕事は常設の wave に置く
- **feature**: 種別 feature の issue。wave の sub-issue にする（wave × 機能）
- **task**: 種別 task の issue。feature の sub-issue にする。起票は `/hirai-lite:new-task`（`hirai-task new`）が種別と親を付けて Project に入れる
- **期日**: Milestone は期日のある出す段だけに付ける

## 6. ビュー 6 枚

| ビュー | 絞り込み | 見るもの |
|---|---|---|
| 承認 | `種別:feature status:承認待ち,着手可` | 着手の承認を待つ feature |
| 裁定 | `status:判断待ち` | 人の答えを待つ問い |
| 取り込み | `is:pr is:open` | merge を待つ PR |
| 全体 | 階層 On・`種別:wave`・並べ替えなし | wave を並び順に並べ、開くと feature と task の帯 |
| 止まっているもの | `種別:task status:依存待ち,判断待ち,保留` | 待っている task |
| 保留中の設計メモ | `種別:設計メモ status:保留` | 止めた設計 |

- 機能をまたいで見るとき: `種別:feature title:*認証*` のように絞る
- 帯は直下の子だけを数える。wave の行は feature が閉じた数、feature の行は task の完了の割合

## 7. 画面でしか付けられない 3 つ

API で付けられるかは未検証。付けられない前提で、ビューを作ったあと人が画面で付けて見る。

1. **階層表示**: 全体ビューで Hierarchy を On にする
2. **並べ替え**: wave の並びを決める（全体ビューは並べ替えなしで、Project の行の並びに従う）
3. **グループ化**: 種別でのグループ化は、どのビューに付けるかが決まっていない。付けるなら人が画面で決める

## 8. 立ち上げ後の確かめ

- `hirai-task ready` が、着手できる task を出す（空でもエラーにならない）
- テスト用 issue を 1 本作って Project に入れ、Status が承認待ちになる
- テスト用 PR に `Closes #<番号>` を書いて出し、レビュー中 → merge で完了と動く
