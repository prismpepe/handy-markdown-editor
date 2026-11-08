"""スニペット（文中に挿入する定型文）。

- 欄の書き方は、テンプレート（templating.py）と同じ: `{{名前}}`、`{{名前:既定値}}`、`{{日付}}` など。
  テンプレートは「新しい文書を作る」もの、スニペットは「いまの文書の、カーソルの位置へ挿入する」もの。
- スニペット専用の特別な欄が2つ:
    {{選択}}     いま選んでいる文字に置き換わる（選んでいなければ、`{{選択:既定値}}` の既定値。無ければ空）
    {{カーソル}} 挿入したあとのカーソルの位置（文字としては残らない。無ければ、挿入した文字の末尾）
- 自分のスニペットは、置き場（`%APPDATA%\\MarkdownEditor\\snippets\\`）に `.md` を置く。1ファイル＝1スニペット。名前はファイル名。
- 置き換えだけを行う。命令の実行やファイルの取り込みはしない（templating.py と同じ）。
"""
import os
import re

import templating

SELECTION = "選択"
CURSOR = "カーソル"
RESERVED = (SELECTION, CURSOR)
MAX_BYTES = 100_000                 # スニペットは短いもの。これより大きなファイルは、使わない
_MARK = "\x00CURSOR\x00"            # 挿入したあとの、カーソルの位置を示す、一時的な印

BUILTIN = {
    "注意書き": "> **注意**　{{選択}}{{カーソル}}",
    "ヒント": "> **ヒント**　{{選択}}{{カーソル}}",
    "折りたたみ": "<details>\n<summary>{{見出し:詳細}}</summary>\n\n{{選択}}{{カーソル}}\n\n</details>",
    "チェックリスト": "- [ ] {{選択}}{{カーソル}}\n- [ ] \n- [ ] ",
    "コードブロック": "```{{言語}}\n{{選択}}{{カーソル}}\n```",
    "リンク": "[{{選択:表示する文字}}]({{URL}}){{カーソル}}",
    "日付（年月日・曜日）": "{{年月日}}（{{曜日}}）",
    "日時": "{{日時}}",
    "TODO のメモ": "<!-- TODO: {{内容}} -->",
}


def builtin_snippets():
    return [{"id": "builtin:" + name, "name": name, "kind": "builtin"} for name in BUILTIN]


def user_snippets(folder):
    """置き場の .md を、名前順に返す（サブフォルダーは見ない。無ければ空）。"""
    try:
        names = [n for n in os.listdir(folder) if n.lower().endswith(".md") and os.path.isfile(os.path.join(folder, n))]
    except OSError:
        return []
    names.sort(key=lambda n: n.casefold())
    return [{"id": "file:" + os.path.join(folder, n), "name": os.path.splitext(n)[0], "kind": "user"} for n in names]


def fields(text):
    """利用者に聞く欄（特別な欄と、組み込みの欄を除く）。templating.fields と同じ形。"""
    return [f for f in templating.fields(text) if f["name"] not in RESERVED]


def expand(text, values=None, selection="", now=None):
    """欄を置き換えた挿入文字と、その中のカーソルの位置（文字数。無ければ None）を返す。
    選んでいる文字（selection）は、{{選択}} に入る。値や選んだ文字の中に {{ }} があっても、もう一度は置き換えない。"""
    vals = {str(k): v for k, v in (values or {}).items() if k not in RESERVED}
    vals[SELECTION] = selection if selection else None          # None なら、{{選択:既定値}} の既定値
    vals[CURSOR] = _MARK
    out = templating.render(str(text), vals, now)
    cursor = None
    if _MARK in out:
        cursor = out.index(_MARK)
        out = out.replace(_MARK, "")
    return {"text": out, "cursor": cursor}
