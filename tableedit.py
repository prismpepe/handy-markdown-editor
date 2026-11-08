"""Markdown の表の編集支援（整形・列と行の追加／削除／移動・配置・セルの移動）。

- カーソルのある表を見つけ、操作したあとの、表の行（文字列）と、カーソルの位置を返す。画面は、その範囲を置き換える。
- **整形**は、列の幅をそろえる。幅は、見た目の幅で測る（全角の文字は 2、半角は 1。編集欄の等幅フォントの見え方に合わせる）。
  配置（`:--` `:-:` `--:`）に合わせて、左寄せ・中央・右寄せにそろえる。
- セルの区切りは、エスケープしていない `|`（`\\|` は、文字の `|`）。GFM の決まりに合わせる（コードの中の `|` も、区切りになる）。
- **文字は、捨てない。** 見出し行よりセルが多い行があるときは、直さず、理由を返す（プレビューでは、はみ出した分が、表示されない）。
- 引用（`> |`）や、リストの中の表は、対象外（字下げ 3 文字までの表だけ）。コードブロックの中は、表として扱わない。
- 画面にも変換器にも依存しない（試験できるように）。
"""
import re
import unicodedata

DELIM_CELL = re.compile(r"^:?-+:?$")
OPS = ("format", "add_col_right", "add_col_left", "del_col", "move_col_left", "move_col_right",
       "add_row_below", "add_row_above", "del_row", "align_left", "align_center", "align_right", "align_none")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def display_width(text):
    """等幅フォントでの見た目の幅（全角・絵文字は 2、結合文字は 0、そのほかは 1）。"""
    w = 0
    for ch in text:
        if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def _split(line):
    """1行を、セルに分ける。[(中身の始まり, 中身の終わり, 区切りの `|` の位置（このセルの後ろ。無ければ行の長さ）, 前の `|` の位置)]。
    先頭・末尾の `|` は、なくてもよい。区切りが1つも無ければ None。中身は、前後の空白を除いた範囲（空のセルは、始まり＝終わり）。"""
    pipes, i = [], 0
    while i < len(line):
        if line[i] == "\\":
            i += 2
            continue
        if line[i] == "|":
            pipes.append(i)
        i += 1
    if not pipes:
        return None
    first = len(line) - len(line.lstrip())
    last = len(line.rstrip()) - 1
    bounds = list(pipes)
    if pipes[0] != first:
        bounds.insert(0, first - 1)                      # 先頭の | が無い: 行頭までをセルにする
    if pipes[-1] != last:
        bounds.append(last + 1)                          # 末尾の | が無い
    cells = []
    for a, b in zip(bounds, bounds[1:]):
        s, e = a + 1, b
        while s < e and line[s].isspace():
            s += 1
        while e > s and line[e - 1].isspace():
            e -= 1
        cells.append((s, e, b, a))
    return cells


def _cells(line):
    sp = _split(line)
    return None if sp is None else [line[s:e] for s, e, _, _ in sp]


def _is_delim(line):
    cells = _cells(line)
    return bool(cells) and all(DELIM_CELL.match(c) for c in cells)


def _cell_cursor(line, c):
    """セル c の、カーソルを置く位置（中身の先頭。空のセルは、区切りの `|` と空白の次）。"""
    s, e, nxt, prev = _split(line)[c]
    return s if s < e else min(prev + 2, nxt)


def _column_at(line, ch):
    """桁 ch は、何番目のセルか（`|` の手前までが、そのセル。行頭・行末の外は、端のセル）。"""
    sp = _split(line)
    if not sp:
        return 0
    for c, (_, _, nxt, _) in enumerate(sp):
        if ch <= nxt:
            return c
    return len(sp) - 1


def _in_fence(lines, index):
    """index の行が、コードブロックの中（開き・閉じの行を含む）か。文書の先頭から数える。"""
    marker = None
    for i in range(index + 1):
        m = FENCE.match(lines[i])
        if marker is None:
            if m:
                marker = m.group(1)
                if i == index:
                    return True
        else:
            if i == index:
                return True
            if m and m.group(1)[0] == marker[0] and len(m.group(1)) >= len(marker) and not lines[i].strip().strip(marker[0]):
                marker = None
    return False


def find_block(lines, index):
    """index の行を含む表の範囲 (開始, 終わり)（終わりは、含まない）。表の中でなければ None。
    表は、見出し行・区切り行（`---`）・本文の行から成る。"""
    if not (0 <= index < len(lines)) or _split(lines[index]) is None or _in_fence(lines, index):
        return None
    lo = index
    while lo > 0 and lines[lo - 1].strip() and _split(lines[lo - 1]) is not None:
        lo -= 1
    hi = index
    while hi + 1 < len(lines) and lines[hi + 1].strip() and _split(lines[hi + 1]) is not None:
        hi += 1
    for d in range(max(lo + 1, 1), hi + 1):               # 区切り行（見出し行の次）を探す
        if not _is_delim(lines[d]) or len(_cells(lines[d - 1])) != len(_cells(lines[d])):
            continue
        if index < d - 1:
            return None                                    # 表の上の、パイプを含む文章の行
        block = lines[d - 1:hi + 1]
        if max(len(ln) - len(ln.lstrip()) for ln in block) > 3 or block[0].lstrip().startswith(">"):
            return None
        return d - 1, hi + 1
    return None


def _parse(lines, start, end):
    prefix = lines[start][:len(lines[start]) - len(lines[start].lstrip())]
    header = _cells(lines[start])
    ncols = len(header)
    align = ["center" if c.startswith(":") and c.endswith(":") else "right" if c.endswith(":") else "left" if c.startswith(":") else "none"
             for c in _cells(lines[start + 1])]
    body, wide = [], []
    for k in range(start + 2, end):
        cells = _cells(lines[k])
        if len(cells) > ncols:
            wide.append(k + 1)
        body.append(cells + [""] * (ncols - len(cells)))
    return prefix, header, align, body, wide


def _pad(text, width, align):
    gap = width - display_width(text)
    if align == "right":
        return " " * gap + text
    if align == "center":
        return " " * (gap // 2) + text + " " * (gap - gap // 2)
    return text + " " * gap


def _delim(width, align):
    if align == "center":
        return ":" + "-" * (width - 2) + ":"
    if align == "right":
        return "-" * (width - 1) + ":"
    if align == "left":
        return ":" + "-" * (width - 1)
    return "-" * width


def render(prefix, header, align, body):
    """表の行（見出し・区切り・本文）を作る。[行の文字列]。"""
    ncols = len(header)
    widths = [max([3, display_width(header[c])] + [display_width(r[c]) for r in body]) for c in range(ncols)]
    out = [prefix + "| " + " | ".join(_pad(header[c], widths[c], align[c]) for c in range(ncols)) + " |",
           prefix + "| " + " | ".join(_delim(widths[c], align[c]) for c in range(ncols)) + " |"]
    for r in body:
        out.append(prefix + "| " + " | ".join(_pad(r[c], widths[c], align[c]) for c in range(ncols)) + " |")
    return out


def _locate(text, line):
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return lines, find_block(lines, line)


def _row_number(start, line):
    """0: 見出し行、-1: 区切り行、1〜: 本文の行（1 から数える）。"""
    return 0 if line == start else (-1 if line == start + 1 else line - start - 1)


def info(text, line, ch):
    """カーソルの位置が、表の中か。メニューに、何を出すかを決めるための情報。"""
    lines, blk = _locate(text, line)
    if not blk:
        return {"in_table": False}
    start, end = blk
    ncols = len(_cells(lines[start]))
    row = _row_number(start, line)
    return {"in_table": True, "kind": "header" if row == 0 else "delim" if row == -1 else "body",
            "col": min(_column_at(lines[line], ch), ncols - 1), "ncols": ncols, "rows": end - start - 2}


def _result(start, end, out, row_out, col):
    """操作の結果。カーソルは、出力の row_out 行目（0 が見出し）の、col 列目のセルの先頭。"""
    return {"ok": True, "start": start, "end": end, "lines": out, "cursor": [start + row_out, _cell_cursor(out[row_out], col)]}


def edit(text, line, ch, op):
    """表を編集する。{"ok": True, "start", "end", "lines", "cursor": [行, 桁]}（start〜end の行を、lines に置き換える）。
    できないときは {"ok": False, "message"}。"""
    if op not in OPS:
        return {"ok": False, "message": "この操作は、できません"}
    lines, blk = _locate(text, line)
    if not blk:
        return {"ok": False, "message": "カーソルが、表の中にありません"}
    start, end = blk
    prefix, header, align, body, wide = _parse(lines, start, end)
    if wide:
        return {"ok": False, "message": "見出し行よりセルが多い行があります（%s 行目）。直してから、操作してください" % "・".join(map(str, wide[:5]))}
    ncols = len(header)
    row = _row_number(start, line)
    col = min(_column_at(lines[line], ch), ncols - 1)
    crow, ccol = row, col                                  # 操作のあとの、カーソルのセル

    if op in ("add_col_left", "add_col_right"):
        at = col if op == "add_col_left" else col + 1
        header.insert(at, ""); align.insert(at, "none")
        for r in body:
            r.insert(at, "")
        ccol = at
    elif op == "del_col":
        if ncols <= 1:
            return {"ok": False, "message": "最後の1列は、削除できません"}
        del header[col]; del align[col]
        for r in body:
            del r[col]
        ccol = min(col, ncols - 2)
    elif op in ("move_col_left", "move_col_right"):
        to = col - 1 if op == "move_col_left" else col + 1
        if not 0 <= to < ncols:
            return {"ok": False, "message": "これ以上、動かせません"}
        for seq in [header, align] + body:
            seq[col], seq[to] = seq[to], seq[col]
        ccol = to
    elif op == "add_row_above":
        if row < 1:
            return {"ok": False, "message": "見出し行の上には、行を足せません"}
        body.insert(row - 1, [""] * ncols)
        crow = row                                          # 新しい行（本文の row 番目）
    elif op == "add_row_below":
        body.insert(max(row, 0), [""] * ncols)              # 見出し・区切り行のときは、本文の先頭に入る
        crow = max(row, 0) + 1
    elif op == "del_row":
        if row < 1:
            return {"ok": False, "message": "見出し行と区切り行は、削除できません"}
        del body[row - 1]
        crow = min(row, len(body)) if body else 0
    elif op.startswith("align_"):
        align[col] = op[len("align_"):]

    out = render(prefix, header, align, body)
    row_out = 1 if crow == -1 else (0 if crow == 0 else crow + 1)       # 出力の何行目か（0 見出し、1 区切り、2〜 本文）
    return _result(start, end, out, min(row_out, len(out) - 1), min(ccol, len(header) - 1))


def tab(text, line, ch, forward=True):
    """Tab / Shift+Tab: 次の（前の）セルの内容の先頭へ移る（区切り行は飛ばす）。最後のセルで Tab を押すと、新しい行を足す。
    表の中でなければ {"ok": False, "not_table": True}。移るだけのときは、文書を変えない（lines は None）。"""
    lines, blk = _locate(text, line)
    if not blk:
        return {"ok": False, "not_table": True}
    start, end = blk
    ncols = len(_cells(lines[start]))
    r = line - start                                        # 0: 見出し、1: 区切り、2〜: 本文
    c = min(_column_at(lines[line], ch), ncols - 1)
    if forward:
        c += 1
        if c >= ncols:
            c, r = 0, r + 1
        r = 2 if r == 1 else r
    else:
        c -= 1
        if c < 0:
            c, r = ncols - 1, r - 1
        r = 0 if r == 1 else r
    if r < 0:
        return {"ok": True, "lines": None, "cursor": [line, ch]}               # 先頭のセルで Shift+Tab: 動かない
    if r > end - start - 1:
        return edit(text, end - 1, 0, "add_row_below")                         # 最後のセルで Tab: 行を足して、その先頭へ
    return {"ok": True, "lines": None, "cursor": [start + r, _cell_cursor(lines[start + r], c)]}
