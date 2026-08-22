---
description: 四半期のルール棚卸し。T0/T1 の全ルールを列挙し、予算残・失効条件・発火実績を点検して削除候補を提示する。
---

# /rules-audit

3 か月ごと、または T0 予算が上限に達した時に実行する。削除に user 承認は要らない。追加のみ承認が要る。

## ① 全ルールの列挙

```bash
for f in CLAUDE.md .claude/rules/*.md; do
  if head -5 "$f" | grep -q '^paths:'; then L=T1; else L=T0; fi
  printf '%s\t%s\t%s bytes\n' "$L" "$f" "$(wc -c < "$f")"
done
```

各ファイルを Read し、`- **<名前>**:` 形式のルール行を抜き出して番号を振る。

## ② 予算の実測

```bash
for f in CLAUDE.md .claude/rules/*.md; do head -5 "$f" | grep -q '^paths:' || wc -c "$f"; done \
  | awk '{s+=$1} END {print "T0:", s, "bytes ≈", int(s/3), "tokens / 上限 3000"}'
for f in .claude/rules/*.md; do head -5 "$f" | grep -q '^paths:' \
  && echo "T1 $f $(( $(wc -c < "$f") / 3 )) tokens / 上限 2000"; done
ls .claude/rules/*.md | wc -l          # T1 は 6 本まで
ls .claude/hooks/*.sh | wc -l          # hook は 5 本まで
ls .claude/commands/*.md | wc -l       # command は 12 個まで
```

## ③ 失効条件の点検

各ルール行の `失効:` を読み、その条件が既に成立しているかを実測で判定する。

- 「list.md を廃止したら」→ `ls docs/tasks/list.md` が exit 1 なら成立。
- 「CI で必ず落ちる構成になったら」→ `ls .github/workflows/*.yml` が exit 0 なら成立。
- `失効:` の記載が無い行は、それ自体を欠陥として一覧に載せる。

## ④ 発火実績の点検

各ルールについて、直近 3 か月の commit にそのルールが効いた痕跡があるかを調べる。

```bash
git log --since='3 months ago' --oneline | wc -l
git log --since='3 months ago' -S'<ルールに出てくる固有語>' --oneline -- <ルールの対象 path>
```

2 つ目の出力が 0 行なら **発火 0** と判定する。

## ⑤ 結果表と削除候補

次の表を出す。

```
| # | 層 | ファイル | ルール名 | tokens | 失効条件 | 成立 | 発火 |
|---|----|---------|---------|--------|---------|------|------|
```

その上で削除候補を優先順に提示する。

1. 失効条件が成立しているもの。
2. 発火 0 のもの。
3. `失効:` の記載が無いもの (記載を足すか削除するかを選ばせる)。
4. T0 にあるが「どの作業のときだけ必要か」を 1 文で言えるもの (T1 へ降格)。

## ⑥ 実行

1 と 2 は user 承認なしで削除する。削除したルールは行ごと `.claude/rules-archive/<元ファイル名>.md` へ移し、日付と削除理由 1 行を添える。3 と 4 は user に選ばせる。

削除後に ② を再実行し、T0 tokens が減ったことを実測する。

## 判定できる終了条件

- 結果表を出力した。
- T0 ≤ 3,000 tokens、T1 各 ≤ 2,000 tokens、T1 ≤ 6 本、hook ≤ 5 本、command ≤ 12 個が全部成立する。
- 成立しない項目があれば、その項目名と実測値と削除候補を報告して停止する。
