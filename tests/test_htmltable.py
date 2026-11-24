"""HTML の表のセル結合・解除（htmltable.py）。"""
import re

import htmltable as H

# 変換機能が作る形（1 行 1 行）
GEN = """前の文

<table>
  <thead>
    <tr><th align="left">名前</th><th align="right">金額</th><th>備考</th></tr>
  </thead>
  <tbody>
    <tr><td>りんご</td><td align="right">100</td><td></td></tr>
    <tr><td>みかん</td><td align="right">200</td><td>甘い</td></tr>
    <tr><td>ぶどう</td><td align="right">300</td><td></td></tr>
  </tbody>
</table>

後の文
"""


def at(text, needle, nth=0):
    """needle の（nth 番目の）位置のうち、中身の先頭あたり。"""
    idx = -1
    for _ in range(nth + 1):
        idx = text.index(needle, idx + 1)
    return idx + 1


def apply(text, r):
    assert r["ok"], r
    return text[:r["from"]] + r["text"] + text[r["to"]:]


def test_右のセルと結合_空のセルなら_確認なしで_colspan_になる():
    r = H.edit(GEN, at(GEN, "<td>りんご"), "merge_right")
    assert r["ok"] is False and "confirm" in r                    # 右（100）に文字がある
    r = H.edit(GEN, at(GEN, "<td>りんご"), "merge_right", force=True)
    out = apply(GEN, r)
    assert '<tr><td colspan="2">りんご<br>100</td><td></td></tr>' in out     # 右のセルは取り除かれ、文字は、改行でつながる
    assert out.startswith("前の文\n\n<table>") and out.endswith("</table>\n\n後の文\n")


def test_取り除くセルが空なら_確認なしで結合できる():
    t = '<table>\n<tr><td>a</td><td></td><td>c</td></tr>\n</table>'
    r = H.edit(t, at(t, "<td>a"), "merge_right")
    assert r["ok"] and apply(t, r) == '<table>\n<tr><td colspan="2">a</td><td>c</td></tr>\n</table>'


def test_空のセルの扱い_nbsp_と_br_だけでも_空とみなす():
    t = '<table>\n<tr><td>a</td><td>&nbsp;</td><td><br></td></tr>\n</table>'
    assert H.edit(t, at(t, "<td>a"), "merge_right")["ok"] is True


def test_今のセルが空で_右に文字があれば_確認のあと_その文字が入る():
    t = '<table>\n<tr><td></td><td>b</td></tr>\n</table>'
    r = H.edit(t, 9, "merge_right")
    assert "confirm" in r and "そのまま入ります" in r["confirm"]
    assert apply(t, H.edit(t, 9, "merge_right", force=True)) == '<table>\n<tr><td colspan="2">b</td></tr>\n</table>'


def test_下のセルと結合は_rowspan_になり_下のセルが取り除かれる():
    t = '<table>\n<tr><td>a</td><td>b</td></tr>\n<tr><td></td><td>d</td></tr>\n</table>'
    out = apply(t, H.edit(t, at(t, "<td>a"), "merge_down"))
    assert out == '<table>\n<tr><td rowspan="2">a</td><td>b</td></tr>\n<tr><td>d</td></tr>\n</table>'


def test_結合を解除すると_空のセルが補われる_行をまたぐ結合も():
    t = '<table>\n<tr><td rowspan="2" colspan="2">a</td><td>b</td></tr>\n<tr><td>c</td></tr>\n<tr><td>d</td><td>e</td><td>f</td></tr>\n</table>'
    out = apply(t, H.edit(t, at(t, "<td rowspan"), "split"))
    assert out == ('<table>\n<tr><td>a</td><td></td><td>b</td></tr>\n<tr><td></td><td></td><td>c</td></tr>\n'
                   '<tr><td>d</td><td>e</td><td>f</td></tr>\n</table>')


def test_解除して_また結合すると_元に戻る():
    t = '<table>\n<tr><td colspan="3">a</td></tr>\n<tr><td>1</td><td>2</td><td>3</td></tr>\n</table>'
    split = apply(t, H.edit(t, at(t, "<td colspan"), "split"))
    assert split == '<table>\n<tr><td>a</td><td></td><td></td></tr>\n<tr><td>1</td><td>2</td><td>3</td></tr>\n</table>'
    again = apply(split, H.edit(split, at(split, "<td>a"), "merge_right"))
    again = apply(again, H.edit(again, at(again, "<td colspan"), "merge_right"))
    assert again == t


def test_行を超える格子でも_位置を正しく数える():
    # 1 行目の左端が rowspan=2 のとき、2 行目の最初のセルは、2 列目にある
    t = '<table>\n<tr><td rowspan="2">a</td><td>b</td></tr>\n<tr><td>c</td></tr>\n</table>'
    i = H.info(t, at(t, "<td>c"))
    assert i["row"] == 1 and i["col"] == 1 and i["can_right"] is False and i["can_down"] is False and i["can_split"] is False
    i = H.info(t, at(t, "<td rowspan"))
    assert i["can_down"] is False and i["can_right"] is False and i["can_split"] is True        # 右（b）は 1 行だけなので、高さが違う


def test_結合できない形は_理由を返し_何もしない():
    t = '<table>\n<tr><td rowspan="2">a</td><td>b</td></tr>\n<tr><td>c</td></tr>\n</table>'
    r = H.edit(t, at(t, "<td>b"), "merge_down")                    # 下（c）は、2 列目。幅は同じなので、結合できる
    assert r["ok"] is False and "confirm" in r
    r = H.edit(t, at(t, "<td rowspan"), "merge_right")             # 右（b）と、高さが違う
    assert r["ok"] is False and "高さ" in r["message"]
    r = H.edit(t, at(t, "<td>c"), "merge_right")
    assert r["ok"] is False and "表の端" in r["message"]
    r = H.edit(t, at(t, "<td>c"), "merge_down")
    assert r["ok"] is False and "表の端" in r["message"]
    r = H.edit(t, at(t, "<td>b"), "split")
    assert r["ok"] is False and "結合されていません" in r["message"]
    r = H.edit(t, at(t, "<td>b"), "nonsense")
    assert r["ok"] is False


def test_見出しと本文をまたぐ結合は_しない():
    r = H.edit(GEN, at(GEN, "<th>備考"), "merge_down")
    assert r["ok"] is False and "thead" in r["message"]


def test_幅が違う下のセルとは_結合しない():
    t = '<table>\n<tr><td colspan="2">a</td></tr>\n<tr><td>b</td><td>c</td></tr>\n</table>'
    r = H.edit(t, at(t, "<td colspan"), "merge_down")
    assert r["ok"] is False and "幅" in r["message"]


def test_ほかの属性や書式は_そのまま_残る():
    t = '<table class="t" id="x">\n  <tr>\n    <td class="a" style="color:red"  align=right>あ</td>\n    <td class="b"></td>\n  </tr>\n</table>'
    out = apply(t, H.edit(t, at(t, "<td class"), "merge_right"))
    assert '<td class="a" style="color:red"  align=right colspan="2">あ</td>' in out
    assert '<td class="b">' not in out and out.startswith('<table class="t" id="x">\n  <tr>\n')
    assert "\n    \n" not in out                                          # 取り除いたセルの行が、空行で残らない


def test_すでにある_colspan_は_書き換える_1に戻れば属性ごと消える():
    t = '<table>\n<tr><td colspan="2">a</td><td>b</td></tr>\n</table>'
    out = apply(t, H.edit(t, at(t, "<td colspan"), "merge_right", force=True))
    assert '<td colspan="3">a<br>b</td>' in out
    s = apply(t, H.edit(t, at(t, "<td colspan"), "split"))
    assert s == '<table>\n<tr><td>a</td><td></td><td>b</td></tr>\n</table>'


def test_大文字の_タグ_と_属性の引用符なしでも_読める():
    t = '<TABLE>\n<TR><TD>a</TD><TD COLSPAN=2>b</TD></TR>\n<TR><TD>c</TD><TD>d</TD><TD>e</TD></TR>\n</TABLE>'
    i = H.info(t, at(t, "<TD COLSPAN"))
    assert i["colspan"] == 2 and i["col"] == 1 and i["can_split"] is True
    out = apply(t, H.edit(t, at(t, "<TD COLSPAN"), "split"))
    assert "<TD>b</TD><TD></TD>" in out and "COLSPAN" not in out


def test_扱えない表は_理由を返す():
    nested = '<table>\n<tr><td><table><tr><td>x</td></tr></table></td></tr>\n</table>'
    assert "入れ子" in H.edit(nested, 12, "merge_right")["message"]
    noend = '<table>\n<tr><td>a<td>b</tr>\n</table>'
    assert "扱えません" in H.edit(noend, 12, "merge_right")["message"]
    overlap = '<table>\n<tr><td>x</td><td rowspan="2">y</td></tr>\n<tr><td colspan="3">z</td></tr>\n</table>'
    assert "重なって" in H.edit(overlap, 12, "merge_right")["message"]
    over = '<table>\n<tr><td rowspan="5">a</td></tr>\n</table>'
    assert "行数を超えて" in H.edit(over, 12, "merge_right")["message"]
    assert H.info(nested, 12)["in_table"] is True and H.info(nested, 12)["error"]


def test_表の外では_何もしない_カーソルが範囲外でも_落ちない():
    assert H.edit(GEN, 2, "merge_right")["ok"] is False and H.info(GEN, 2)["in_table"] is False
    assert H.edit(GEN, -1, "merge_right")["ok"] is False and H.edit(GEN, 10 ** 6, "merge_right")["ok"] is False
    assert H.edit(None, 0, "split")["ok"] is False


def test_行の境目や_thead_の行に_カーソルがあっても_近いセルが対象になる():
    i = H.info(GEN, GEN.index("<tr><th"))
    assert i["row"] == 0 and i["col"] == 0
    i = H.info(GEN, GEN.index("</tbody>"))
    assert i["in_table"] is True


def test_結果は_変わった部分だけ_カーソルは_今のセルの中():
    r = H.edit(GEN, at(GEN, "<td>みかん"), "merge_right", force=True)
    assert len(r["text"]) < 80 and r["from"] > GEN.index("<tbody>")
    out = apply(GEN, r)
    assert out[r["cursor"]:].startswith("みかん<br>200")                 # カーソルは、今のセルの中身の先頭


def test_変換機能の出力と_組み合わせて_どの行でも結合できる(tmp_path, monkeypatch):
    import mdeditor
    monkeypatch.setenv("APPDATA", str(tmp_path))
    api = mdeditor.Api(None)
    md = "| 地域 | 4月 | 5月 |\n| --- | --: | --: |\n| 東 | 1 | 2 |\n| 西 | 3 | 4 |\n"
    html = "\n".join(api.table_to_html(md, 0, 0)["lines"])
    first = apply(html, H.edit(html, at(html, "<td>東"), "merge_down", force=True))
    assert re.search(r'<td rowspan="2">東<br>西</td>', first) and first.count("<tr>") == 3
