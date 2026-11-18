"""文字の色・背景の色（style の color / background-color と、色の class）の通し方。"""
import pytest

from sanitize import sanitize


@pytest.mark.parametrize("val", ["red", "Red", "#c00", "#cc0000", "#CC000080", "rgb(255, 0, 0)", "rgba(255,0,0,.5)", "hsl(0 100% 50%)", "rebeccapurple", "transparent"])
def test_色として確かな値は通る(val):
    out = sanitize(f'<span style="color:{val}">字</span>')
    assert out == f'<span style="color: {val.lower()}">字</span>'


def test_背景の色も通る():
    assert sanitize('<span style="background-color: yellow">字</span>') == '<span style="background-color: yellow">字</span>'


def test_文字と背景を一緒に指定できる():
    out = sanitize('<span style="color:#fff; background-color:#c00">字</span>')
    assert out == '<span style="color: #fff; background-color: #c00">字</span>'


@pytest.mark.parametrize("val", [
    "url(http://evil/x.png)", "expression(alert(1))", "var(--x)", "red !important", "javascript:alert(1)",
    "rgb(url(x))", "rgb(0,0,0) url(x)", "#12", "#12345", "redd", "calc(1px)", "inherit", "",
])
def test_色ではないもの_危ない値は落ちる(val):
    assert sanitize(f'<span style="color:{val}">字</span>') == '<span>字</span>'
    assert sanitize(f'<span style="background-color:{val}">字</span>') == '<span>字</span>'


def test_色以外の宣言は落ちる_色だけ残る():
    out = sanitize('<span style="color:red; position:fixed; font-size:99px; background-image:url(x)">字</span>')
    assert out == '<span style="color: red">字</span>'


def test_色のclassは残る():
    assert sanitize('<span class="red">字</span>') == '<span class="red">字</span>'
    assert sanitize('<span class="bg-yellow">字</span>') == '<span class="bg-yellow">字</span>'
