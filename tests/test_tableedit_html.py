"""Markdown の表を HTML の表に変換する（tableedit.to_html）。"""
import html

import tableedit


def inline(s):                       # 画面では、Markdown の変換器の行内変換を渡す。ここでは、目印だけ付ける簡易版
    return html.escape(s).replace("**", "<b>", 1).replace("**", "</b>", 1) if "**" in s else html.escape(s)


TABLE = "前の文\n\n| 名前 | 金額 |\n| :-- | --: |\n| **りんご** | 100 |\n| みかん | 2,000 |\n\n後の文\n"


def test_表が_thead_と_tbody_と_配置つきのHTMLになる():
    r = tableedit.to_html(TABLE, 3, 2, inline)
    assert r["ok"] and (r["start"], r["end"]) == (2, 6)
    assert r["lines"] == [
        "<table>", "  <thead>",
        '    <tr><th align="left">名前</th><th align="right">金額</th></tr>',
        "  </thead>", "  <tbody>",
        '    <tr><td align="left"><b>りんご</b></td><td align="right">100</td></tr>',
        '    <tr><td align="left">みかん</td><td align="right">2,000</td></tr>',
        "  </tbody>", "</table>"]
    assert r["cursor"] == [2, 0]


def test_配置の指定がなければ_align_は付けない():
    r = tableedit.to_html("| a | b |\n| - | - |\n| 1 | 2 |\n", 0, 0, inline)
    assert "<th>a</th><th>b</th>" in r["lines"][2] and "<td>1</td><td>2</td>" in r["lines"][5]


def test_セルの_バックスラッシュパイプ_は_パイプに戻る():
    r = tableedit.to_html("| a | b |\n| - | - |\n| x\\|y | 2 |\n", 2, 3, inline)
    assert "<td>x|y</td>" in r["lines"][5]


def test_データの行がなければ_tbody_は出さない():
    r = tableedit.to_html("| a | b |\n| - | - |\n", 0, 0, inline)
    assert r["ok"] and "<tbody>" not in "".join(r["lines"])


def test_字下げは_そのまま_引き継ぐ():
    r = tableedit.to_html("  | a |\n  | - |\n  | 1 |\n", 0, 3, inline)
    assert all(l.startswith("  ") for l in r["lines"]) and r["cursor"] == [0, 2]


def test_表の外_と_セルがはみ出す表は_何もしない():
    assert tableedit.to_html("ただの文\n", 0, 0, inline)["ok"] is False
    r = tableedit.to_html("| a |\n| - |\n| 1 | 2 |\n", 0, 0, inline)
    assert r["ok"] is False and "セルが多い" in r["message"]


def test_変換器の例外は_Api_側で_エスケープに落とす(tmp_path, monkeypatch):
    import mdeditor
    monkeypatch.setenv("APPDATA", str(tmp_path))
    api = mdeditor.Api(None)
    r = api.table_to_html("| a | b |\n| - | - |\n| **太字** `x\\|y` | [リンク](https://e.com \"T\") |\n", 0, 0)
    row = r["lines"][5]
    assert "<strong>太字</strong>" in row and "<code>x|y</code>" in row and '<a href="https://e.com" title="T">リンク</a>' in row
    assert api.table_to_html("x", 0, -1)["ok"] is False
