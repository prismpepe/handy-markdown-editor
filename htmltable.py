"""HTML の表（`<table>`）のセル結合・解除（colspan / rowspan）の編集支援。

- カーソルのある `<table>` を見つけ、セルを読み取って「何行何列目に、どのセルがあるか」の格子にする。すでに `colspan` `rowspan`
  があっても、位置を正しく数える。
- 操作: **右のセルと結合**（colspan を足し、右のセルを取り除く）・**下のセルと結合**（rowspan）・**結合を解除**（空のセルを補う）。
- **書き換えは、必要な部分だけ**（変えるセルの開始タグと、取り除くセル、補うセル）。手で整えた書式や、`class` `style` などの属性は、壊さない。
- 取り除くセルに文字があるとき、**そのまま実行せず**、確認の文を返す（force=True で、今のセルの内容の後ろに `<br>` でつなぐ）。
- 扱えるのは、単純な表だけ（変換機能・「表・データ」の取り込みで作る表と同じ形）。表の入れ子・終了タグを省いたセル・重なるセルなどは、
  何もせず、理由を返す。見出し（thead）と本文（tbody）をまたぐ結合は、しない。
- 位置は、文書全体の文字の数（offset）で扱う。結果は、**変わった部分だけ**（from〜to を text に置き換える）。
- 画面にも変換器にも依存しない（試験できるように）。
"""
import re

TAG = re.compile(r"<(/?)(table|thead|tbody|tfoot|tr|td|th)\b([^>]*)>", re.I)
CELL_CLOSE = {"td": re.compile(r"</\s*td\s*>", re.I), "th": re.compile(r"</\s*th\s*>", re.I)}
TABLE_OPEN = re.compile(r"<table\b", re.I)
TABLE_CLOSE = re.compile(r"</\s*table\s*>", re.I)
BAD_INNER = re.compile(r"<(table|tr|td|th|thead|tbody|tfoot)\b", re.I)
EMPTY = re.compile(r"(\s|&nbsp;|<br\s*/?>)+", re.I)
OPS = ("merge_right", "merge_down", "split")
MAX_SPAN = 1000


class Unsupported(Exception):
    pass


def _span(attrs, name):
    m = re.search(r"\b%s\s*=\s*[\"']?(\d+)" % name, attrs, re.I)
    return max(1, min(int(m.group(1)), MAX_SPAN)) if m else 1


def find_table(text, offset):
    """offset を含む表の範囲 (開始, 終わり)。無ければ None。入れ子の表は、Unsupported。"""
    for m in TABLE_OPEN.finditer(text):
        close = TABLE_CLOSE.search(text, m.end())
        if not close:
            continue
        if m.start() <= offset <= close.end():
            if TABLE_OPEN.search(text, m.end(), close.start()):
                raise Unsupported("表の中の表（入れ子）は、扱えません")
            return m.start(), close.end()
    return None


def parse(text, start, end):
    """表を読む。(行, セル, 格子)。行 = {i, section, open_start, open_end, cells}、
    セル = {tag, attrs, start, open_end, close_start, end, row, col, colspan, rowspan, section}、格子 = {(行, 列): セル}。"""
    src = text[start:end]
    rows, cells = [], []
    section, row, first, pos = None, None, True, 0
    while True:
        m = TAG.search(src, pos)
        if not m:
            break
        closing, name, attrs = m.group(1) == "/", m.group(2).lower(), m.group(3)
        pos = m.end()
        if name == "table":
            if not closing and not first:
                raise Unsupported("表の中の表（入れ子）は、扱えません")
            first = False
        elif name in ("thead", "tbody", "tfoot"):
            section = None if closing else name
        elif name == "tr":
            if closing:
                row = None
            else:
                row = {"i": len(rows), "section": section, "open_start": start + m.start(), "open_end": start + m.end(), "cells": []}
                rows.append(row)
        else:                                                              # td / th
            if closing:
                raise Unsupported("開始タグのない終了タグがあります")
            if row is None:
                raise Unsupported("行（tr）の外に、セルがあります")
            close = CELL_CLOSE[name].search(src, m.end())
            if not close:
                raise Unsupported("終了タグのないセルがあります")
            if BAD_INNER.search(src, m.end(), close.start()):
                raise Unsupported("終了タグを省いたセルや、表の入れ子は、扱えません")
            cell = {"tag": name, "tagtext": src[m.start() + 1:m.start() + 1 + len(name)], "attrs": attrs, "start": start + m.start(),
                    "open_end": start + m.end(), "close_start": start + close.start(), "end": start + close.end(),
                    "row": row["i"], "section": section, "colspan": _span(attrs, "colspan"), "rowspan": _span(attrs, "rowspan")}
            row["cells"].append(cell)
            cells.append(cell)
            pos = close.end()
    if not cells:
        raise Unsupported("セルがありません")
    grid = {}
    for r in rows:
        c = 0
        for cell in r["cells"]:
            while (r["i"], c) in grid:
                c += 1
            cell["col"] = c
            if cell["row"] + cell["rowspan"] > len(rows):
                raise Unsupported("rowspan が、表の行数を超えています")
            for rr in range(cell["row"], cell["row"] + cell["rowspan"]):
                for cc in range(c, c + cell["colspan"]):
                    if (rr, cc) in grid:
                        raise Unsupported("セルが重なっています（colspan / rowspan の指定が合っていません）")
                    grid[(rr, cc)] = cell
            c += cell["colspan"]
    return rows, cells, grid


def cell_at(cells, offset):
    """offset の位置のセル。セルの外（行の境目など）なら、次のセル（無ければ、最後のセル）。"""
    for c in cells:
        if c["start"] <= offset <= c["end"]:
            return c
    after = [c for c in cells if c["start"] > offset]
    return after[0] if after else cells[-1]


def _set_attr(attrs, name, value):
    """属性 name を、value にする（1 なら、取り除く）。ほかの属性は、そのまま。"""
    pat = re.compile(r"(\s+)%s(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\"'>]+))?" % name, re.I)
    m = pat.search(attrs)
    if value <= 1:
        return pat.sub("", attrs, count=1) if m else attrs
    new = ' %s="%d"' % (name, value)
    if m:
        return attrs[:m.start()] + new + attrs[m.end():]
    return attrs.rstrip() + new


def _open_tag(cell, colspan, rowspan):
    attrs = _set_attr(_set_attr(cell["attrs"], "colspan", colspan), "rowspan", rowspan)
    return "<" + cell["tagtext"] + attrs + ">"


def _inner(text, cell):
    return text[cell["open_end"]:cell["close_start"]]


def _is_empty(inner):
    return EMPTY.sub("", inner) == ""


def _plain(inner, limit=30):
    s = re.sub(r"<[^>]*>", " ", inner)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= limit else s[:limit] + "…"


def _remove_range(text, a, b):
    """セルを取り除く範囲。そのセルだけが 1 行を占めていれば、その行ごと（改行も）取り除く。"""
    ls = text.rfind("\n", 0, a) + 1
    le = text.find("\n", b)
    le = len(text) if le < 0 else le
    if not text[ls:a].strip() and not text[b:le].strip():
        return ls, min(le + 1, len(text))
    return a, b


def plan(text, rows, grid, cell, op, force=False):
    """操作の計画。{"edits": [(開始, 終わり, 置き換える文字)], "done": 完了の文} か、{"error": 理由}、{"confirm": 確認の文}。"""
    if op not in OPS:
        return {"error": "この操作は、できません"}
    A = cell
    if op == "split":
        if A["colspan"] == 1 and A["rowspan"] == 1:
            return {"error": "このセルは、結合されていません"}
        edits = [(A["start"], A["open_end"], _open_tag(A, 1, 1))]
        empty = "<%s></%s>" % (A["tagtext"], A["tagtext"])
        for i in range(A["row"], A["row"] + A["rowspan"]):
            k = A["colspan"] - 1 if i == A["row"] else A["colspan"]
            if k <= 0:
                continue
            if i == A["row"]:
                at = A["end"]
            else:
                left = [c for c in rows[i]["cells"] if c["col"] < A["col"]]
                at = max(left, key=lambda c: c["col"])["end"] if left else rows[i]["open_end"]
            edits.append((at, at, empty * k))
        return {"edits": edits, "done": "結合を解除しました"}

    if op == "merge_right":
        B = grid.get((A["row"], A["col"] + A["colspan"]))
        if not B:
            return {"error": "右に、結合できるセルがありません（表の端です）"}
        if B["row"] != A["row"] or B["col"] != A["col"] + A["colspan"]:
            return {"error": "右のセルは、上の行から続いているため、結合できません"}
        if B["rowspan"] != A["rowspan"]:
            return {"error": "右のセルと、高さ（行数）が違うため、結合できません"}
        new_cs, new_rs, where = A["colspan"] + B["colspan"], A["rowspan"], "右"
    else:
        r2 = A["row"] + A["rowspan"]
        B = grid.get((r2, A["col"]))
        if not B:
            return {"error": "下に、結合できるセルがありません（表の端です）"}
        if rows[r2]["section"] != rows[A["row"]]["section"]:
            return {"error": "見出し（thead）と本文（tbody）をまたぐ結合は、できません"}
        if B["row"] != r2 or B["col"] != A["col"]:
            return {"error": "下のセルは、左の列から続いているため、結合できません"}
        if B["colspan"] != A["colspan"]:
            return {"error": "下のセルと、幅（列数）が違うため、結合できません"}
        new_cs, new_rs, where = A["colspan"], A["rowspan"] + B["rowspan"], "下"

    a_in, b_in = _inner(text, A), _inner(text, B)
    b_empty, a_empty = _is_empty(b_in), _is_empty(a_in)
    if not b_empty and not force:
        if a_empty:
            tail = "今のセルは空なので、そのセルの文字が、そのまま入ります。"
        else:
            tail = "結合すると、今のセルの文字の後ろに、改行（<br>）でつなぎます。"
        return {"confirm": "%sのセルに、文字があります:「%s」。%s実行しますか？" % (where, _plain(b_in), tail)}
    edits = [(A["start"], A["open_end"], _open_tag(A, new_cs, new_rs))]
    if not b_empty:
        if a_empty:
            edits.append((A["open_end"], A["close_start"], b_in.strip()))
        else:
            edits.append((A["close_start"], A["close_start"], "<br>" + b_in.strip()))
    edits.append(_remove_range(text, B["start"], B["end"]) + ("",))
    return {"edits": edits, "done": "%sのセルと結合しました" % where}


def _apply(text, start, end, edits):
    """edits を後ろから当てた、表の文字列。"""
    out = text
    for a, b, rep in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        out = out[:a] + rep + out[b:]
    return out[start:len(out) - (len(text) - end)]


def _locate(text, offset):
    if not isinstance(text, str) or not isinstance(offset, int) or not 0 <= offset <= len(text):
        return None, "位置が正しくありません"
    try:
        span = find_table(text, offset)
        if not span:
            return None, None
        rows, cells, grid = parse(text, *span)
    except Unsupported as e:
        return None, str(e)
    return (span, rows, cells, grid), None


def info(text, offset):
    """カーソルの位置が、扱える HTML の表の中か。メニューに、何を出すかを決めるための情報。"""
    loc, err = _locate(text, offset)
    if not loc:
        return {"in_table": err is not None, "error": err, "can_right": False, "can_down": False, "can_split": False}
    span, rows, cells, grid = loc
    cell = cell_at(cells, offset)
    out = {"in_table": True, "error": None, "row": cell["row"], "col": cell["col"], "colspan": cell["colspan"], "rowspan": cell["rowspan"]}
    for key, op in (("can_right", "merge_right"), ("can_down", "merge_down"), ("can_split", "split")):
        p = plan(text, rows, grid, cell, op)
        out[key] = "error" not in p
    return out


def edit(text, offset, op, force=False):
    """セルを結合・解除する。{"ok": True, "from", "to", "text", "cursor", "message"}（from〜to を text に置き換える）。
    取り除くセルに文字があるときは、{"ok": False, "confirm": 確認の文}。できないときは、{"ok": False, "message": 理由}。"""
    loc, err = _locate(text, offset)
    if not loc:
        return {"ok": False, "message": ("この HTML の表は、扱えません: " + err) if err else "カーソルが、HTML の表の中にありません"}
    span, rows, cells, grid = loc
    cell = cell_at(cells, offset)
    p = plan(text, rows, grid, cell, op, force)
    if "error" in p:
        return {"ok": False, "message": p["error"]}
    if "confirm" in p:
        return {"ok": False, "confirm": p["confirm"]}
    old = text[span[0]:span[1]]
    new = _apply(text, span[0], span[1], p["edits"])
    pre = 0
    while pre < min(len(old), len(new)) and old[pre] == new[pre]:
        pre += 1
    suf = 0
    while suf < min(len(old), len(new)) - pre and old[len(old) - 1 - suf] == new[len(new) - 1 - suf]:
        suf += 1
    delta = len(p["edits"][0][2]) - (cell["open_end"] - cell["start"])             # 今のセルの開始タグの長さの変化
    return {"ok": True, "from": span[0] + pre, "to": span[1] - suf, "text": new[pre:len(new) - suf],
            "cursor": cell["open_end"] + delta, "message": p["done"]}

