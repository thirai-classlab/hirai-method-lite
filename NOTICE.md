# NOTICE

このリポジトリは MIT License で配布している (`LICENSE`)。
以下は第三者の著作物を同梱している部分で、それぞれの原ライセンスと著作権表示をここに保持する。

## agents/tdd-guide.md

- 出典: [everything-claude-code](https://github.com/affaan-m/everything-claude-code) の `agents/` (commit `1a50145`)
- ライセンス: MIT License
- 変更: 本プラグインに同梱していないスキルを指す参照 1 行を削除した。カバレッジの「80%+」4 か所を「導入先が決めた基準」に替えた（v2.7.0）。
- 同じ出典の `code-reviewer.md` と `security-reviewer.md` も v2.6.0 まで同梱していたが、v2.7.0 で外した（Claude Code 組み込みの `/code-review`・`/simplify`・`/security-review` に置き換え）。

```
MIT License

Copyright (c) 2026 Affaan Mustafa

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## skills/grilling/SKILL.md

- 出典: [mattpocock/skills](https://github.com/mattpocock/skills) の `skills/productivity/grilling/SKILL.md`
  - 取得元 URL: `https://raw.githubusercontent.com/mattpocock/skills/0ab1b63a410a/skills/productivity/grilling/SKILL.md`
  - commit: `0ab1b63a410a03d3627979a109c8695de27af954`（Claude Code 公式マーケットプレイスのプラグイン `mattpocock-skills` v1.2.3 が pin している版）
  - 取り込み時点の `main` HEAD は `6654f6b60cd9d5be8b54c6fafe44346dabeb3b76` だが、**この 1 ファイルの内容は pin 版と 1 バイトも違わない**ことを実測して確認している（sha256 が一致）。
- ライセンス: MIT License
- 変更: **なし（1 バイトも変えていない）。** sha256 = `10ff989e7498b23b5acb49d5048f11dcd906757d2f79c5cdf8a00001381296f2`（1,987 bytes）。`shasum -a 256 skills/grilling/SKILL.md` でいつでも突き合わせられる。

```
MIT License

Copyright (c) 2026 Matt Pocock

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
