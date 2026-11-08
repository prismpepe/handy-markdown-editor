import datetime
import os
import struct
import sys
import zlib

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import clipboard
import mdeditor
import pasteimg


def decode_png(data):
    """試験用の最小の PNG 復号（8ビット RGB・フィルタ 0 だけ）。CRC も確かめる。"""
    assert data[:8] == pasteimg.PNG_SIGNATURE
    pos, idat, width = 8, b"", 0
    height = 0
    while pos < len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        kind, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        crc = struct.unpack(">I", data[pos + 8 + n:pos + 12 + n])[0]
        assert crc == zlib.crc32(kind + body) & 0xFFFFFFFF, kind
        if kind == b"IHDR":
            width, height, depth, ctype = struct.unpack(">IIBB", body[:10])
            assert (depth, ctype) == (8, 2)
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    raw = zlib.decompress(idat)
    assert len(raw) == height * (1 + width * 3)
    rows = []
    for y in range(height):
        line = raw[y * (1 + width * 3):(y + 1) * (1 + width * 3)]
        assert line[0] == 0
        rows.append([tuple(line[1 + x * 3:4 + x * 3]) for x in range(width)])
    return width, height, rows


def make_dib(width, height, pixels_bgr, bits=24, top_down=False, comp=0, masks=None, extra=b""):
    """pixels_bgr: 上の行から順の、(B,G,R) の行の並び。DIB は、ふつう下の行から並べる。"""
    step = bits // 8
    stride = ((width * bits + 31) // 32) * 4
    rows = []
    for row in pixels_bgr:
        raw = b"".join(bytes(p) + (b"\x00" if step == 4 else b"") for p in row)
        rows.append(raw + b"\x00" * (stride - len(raw)))
    if not top_down:
        rows.reverse()
    header = struct.pack("<IiiHHIIiiII", 40, width, -height if top_down else height, 1, bits, comp, stride * height, 0, 0, 0, 0)
    if comp == 3:
        header += struct.pack("<III", *(masks or (0x00FF0000, 0x0000FF00, 0x000000FF)))
    return header + extra + b"".join(rows)


PIX = [[(10, 20, 30), (40, 50, 60), (70, 80, 90)],      # B,G,R
       [(1, 2, 3), (4, 5, 6), (7, 8, 9)]]
RGB = [[(30, 20, 10), (60, 50, 40), (90, 80, 70)],
       [(3, 2, 1), (6, 5, 4), (9, 8, 7)]]


@pytest.mark.parametrize("bits", [24, 32])
def test_dib_to_png_converts_colors_and_row_order(bits):
    png = pasteimg.dib_to_png(make_dib(3, 2, PIX, bits))
    w, h, rows = decode_png(png)
    assert (w, h) == (3, 2) and rows == RGB                   # 上下も、色（B と R の入れ替え）も正しい


def test_dib_top_down_and_bitfields():
    assert decode_png(pasteimg.dib_to_png(make_dib(3, 2, PIX, 24, top_down=True)))[2] == RGB
    assert decode_png(pasteimg.dib_to_png(make_dib(3, 2, PIX, 32, comp=3)))[2] == RGB
    assert pasteimg.dib_to_png(make_dib(3, 2, PIX, 32, comp=3, masks=(0xFF, 0xFF00, 0xFF0000))) is None   # 標準でない色の並び


def test_dib_ignores_alpha_zero():
    dib = bytearray(make_dib(1, 1, [[(5, 6, 7)]], 32))
    assert dib[-1] == 0                                       # 透明度が 0 でも、透明にしない
    assert decode_png(pasteimg.dib_to_png(bytes(dib)))[2] == [[(7, 6, 5)]]


def test_dib_rejects_bad_input():
    good = make_dib(3, 2, PIX, 24)
    assert pasteimg.dib_to_png(good[:60]) is None             # 途中で切れている
    assert pasteimg.dib_to_png(b"") is None and pasteimg.dib_to_png(None) is None
    assert pasteimg.dib_to_png(make_dib(3, 2, PIX, 24)[:40] + b"") is None
    huge = bytearray(good)
    struct.pack_into("<i", huge, 4, 2_000_000_000)            # 巨大な幅（メモリを使い切る値）
    assert pasteimg.dib_to_png(bytes(huge)) is None
    pal = bytearray(good)
    struct.pack_into("<H", pal, 14, 8)                        # 8 ビット（パレット）は、対応しない
    assert pasteimg.dib_to_png(bytes(pal)) is None


def test_is_png():
    png = pasteimg.dib_to_png(make_dib(3, 2, PIX, 24))
    assert pasteimg.is_png(png) and not pasteimg.is_png(b"GIF89a....") and not pasteimg.is_png(None)


def test_save_png_names_and_never_overwrites(tmp_path):
    doc = tmp_path / "docs" / "a.md"
    png = pasteimg.dib_to_png(make_dib(3, 2, PIX, 24))
    now = datetime.datetime(2026, 11, 8, 16, 49, 5)
    r1 = pasteimg.save_png(str(doc), png, now=now)
    assert r1["rel"] == "images/image-20261108-164905.png"
    assert open(r1["path"], "rb").read() == png
    r2 = pasteimg.save_png(str(doc), png, now=now)            # 同じ秒でも、上書きしない
    r3 = pasteimg.save_png(str(doc), png, now=now)
    assert [r2["rel"], r3["rel"]] == ["images/image-20261108-164905-2.png", "images/image-20261108-164905-3.png"]
    assert os.path.dirname(r1["path"]) == str(tmp_path / "docs" / "images")
    with pytest.raises(ValueError):
        pasteimg.save_png(str(doc), b"not a png")


def test_api_paste_clipboard_image(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    png = pasteimg.dib_to_png(make_dib(3, 2, PIX, 24))
    monkeypatch.setattr(clipboard, "get_image_png", lambda: png)
    api = mdeditor.Api(None)
    doc = tmp_path / "x.md"
    r = api.paste_clipboard_image(str(doc))
    assert r["ok"] and r["rel"].startswith("images/image-") and r["bytes"] == len(png)
    assert open(tmp_path / r["rel"], "rb").read() == png
    assert api.paste_clipboard_image(None) == {"ok": True, "unsaved": True}       # 未保存では、保存しない
    assert not [p for p in os.listdir(tmp_path / "images")][1:]                    # 未保存のときに、ファイルを増やしていない
    assert api.paste_clipboard_image(123)["kind"] == "error"
    monkeypatch.setattr(clipboard, "get_image_png", lambda: None)
    assert api.paste_clipboard_image(str(doc)) == {"ok": False, "kind": "none"}
    monkeypatch.setattr(clipboard, "get_image_png", lambda: png)
    monkeypatch.setattr(pasteimg, "MAX_PNG", 10)
    assert api.paste_clipboard_image(str(doc))["kind"] == "error"                  # 大きすぎる


def make_dib_v5(width, height, pixels_bgr, repeat_masks):
    """Windows が DIB から作る DIBV5（32 ビット・ビットフィールド）。ヘッダーの後ろに、マスクを重ねて入れることがある。"""
    stride = width * 4
    rows = [b"".join(bytes(p) + b"\x00" for p in row) for row in pixels_bgr]
    rows.reverse()
    header = struct.pack("<IiiHHIIiiII", 124, width, height, 1, 32, 3, stride * height, 0, 0, 0, 0)
    header += struct.pack("<IIII", 0x00FF0000, 0x0000FF00, 0x000000FF, 0)           # マスク（R, G, B, A）
    header += b"\x00" * (124 - len(header))
    extra = struct.pack("<III", 0x00FF0000, 0x0000FF00, 0x000000FF) if repeat_masks else b""
    return header + extra + b"".join(rows)


@pytest.mark.parametrize("repeat", [False, True])
def test_dibv5_with_or_without_repeated_masks(repeat):
    png = pasteimg.dib_to_png(make_dib_v5(3, 2, PIX, repeat))
    assert decode_png(png)[2] == RGB                           # マスクの重なりがあっても、画素の位置を間違えない
