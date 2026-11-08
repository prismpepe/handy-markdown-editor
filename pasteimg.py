"""クリップボードの画像（スクリーンショットなど）を、画像ファイルにして、文書のそばへ保存する。

- 保存先は、文書のあるフォルダーの `images\\`。ファイル名は `image-年月日-時分秒.png`（同じ名前があれば `-2` `-3`）。
  既にあるファイルは、上書きしない。
- クリップボードの画像は、登録された形式 "PNG"（そのまま使う）か、DIB（ビットマップ。PNG に変換する）で受け取る。
- 画面にも Win32 にも依存しない部分（DIB→PNG の変換、保存）だけを、ここに置く（試験できるように）。
"""
import datetime
import os
import struct
import zlib

MAX_PNG = 40 * 1024 * 1024        # 保存する画像の大きさの上限
MAX_PIXELS = 100_000_000          # 変換する画像の画素数の上限（巨大な値のヘッダで、メモリを使い切らないため）
FOLDER = "images"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def is_png(data):
    """PNG として読める入れ物か（署名と IHDR）。中身の全部は調べない。"""
    return (isinstance(data, (bytes, bytearray)) and len(data) > 33 and data[:8] == PNG_SIGNATURE
            and data[12:16] == b"IHDR")


def _chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def encode_png(width, height, rows):
    """RGB の行（各行 width*3 バイト）の並びから、PNG を作る。"""
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return PNG_SIGNATURE + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(raw, 6)) + _chunk(b"IEND", b"")


def dib_to_png(dib):
    """Windows のビットマップ（DIB）を PNG にする。24 ビット・32 ビット（標準の色の並び）だけ対応。変換できなければ None。
    32 ビットの透明度は、使わない（スクリーンショットでは、0 が入っていて、透明に見えてしまうことがあるため）。"""
    if not isinstance(dib, (bytes, bytearray)) or len(dib) < 40:
        return None
    size, width, height, planes, bits, comp = struct.unpack_from("<IiiHHI", dib, 0)
    colors_used = struct.unpack_from("<I", dib, 32)[0]
    if size < 40 or planes != 1 or bits not in (24, 32) or comp not in (0, 3):
        return None
    top_down = height < 0
    height = abs(height)
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        return None
    offset = size
    if comp == 3:                                        # 色のマスク。標準の並び（B,G,R の順）だけを受け付ける
        if size == 40:
            masks = struct.unpack_from("<III", dib, 40)
            offset += 12
        else:
            masks = struct.unpack_from("<III", dib, 40)
        if masks != (0x00FF0000, 0x0000FF00, 0x000000FF):
            return None
    offset += colors_used * 4
    stride = ((width * bits + 31) // 32) * 4
    if comp == 3 and size >= 108 and dib[offset:offset + 12] == dib[40:52] and \
            len(dib) >= offset + 12 + stride * height:
        offset += 12             # Windows が DIB から作る DIBV5 は、ヘッダーの後ろに、色のマスクをもう一度入れている
    if len(dib) < offset + stride * height:
        return None
    step = bits // 8
    rows = []
    for y in range(height):
        src = height - 1 - y if not top_down else y        # DIB は、ふつう下の行から
        row = dib[offset + src * stride: offset + src * stride + width * step]
        out = bytearray(width * 3)
        out[0::3] = row[2::step]                         # R
        out[1::3] = row[1::step]                         # G
        out[2::3] = row[0::step]                         # B
        rows.append(out)
    return encode_png(width, height, rows)


def save_png(doc_path, png, folder=FOLDER, now=None):
    """文書のあるフォルダーの `folder` へ、新しい名前で保存する。{"path", "rel"}（rel は、文書から見た相対パス）。"""
    if not is_png(png):
        raise ValueError("PNG ではありません")
    target_dir = os.path.join(os.path.dirname(os.path.abspath(doc_path)), folder)
    os.makedirs(target_dir, exist_ok=True)
    stem = "image-" + (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")
    n = 1
    while True:
        name = stem + (".png" if n == 1 else "-%d.png" % n)
        path = os.path.join(target_dir, name)
        try:
            with open(path, "xb") as f:                      # すでにあるファイルは、上書きしない
                f.write(png)
            return {"path": path, "rel": folder + "/" + name}
        except FileExistsError:
            n += 1
