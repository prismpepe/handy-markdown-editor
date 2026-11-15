"""配布用 zip を作る。入れるものを列挙し、出来た zip を検査する。

    python tools/make_release.py     # dist/MarkdownEditor_v<バージョン>.zip（版は、mdeditor.py の APP_VERSION）

除外を並べる方式にすると、テスト文書や設定などが黙って混ざる。
入れるものを列挙し、最後に zip の中身が列挙どおりかを確かめる。
"""
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOP = "MarkdownEditor"
# (リポジトリ内のパス, zip 内の名前)
FILES = [
    ("dist/MarkdownEditor.exe", "MarkdownEditor.exe"),
    ("docs/取扱説明書.md", "取扱説明書.md"),
    ("docs/簡易仕様書.md", "簡易仕様書.md"),
    ("登録.cmd", "登録.cmd"),
    ("登録解除.cmd", "登録解除.cmd"),
    ("LICENSE", "LICENSE"),
    ("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md"),
]


def app_version():
    """アプリの版（mdeditor.py の APP_VERSION）。zip の名前に入れる（同じ日に何度リリースしても、区別できるように）。"""
    with open(os.path.join(ROOT, "mdeditor.py"), encoding="utf-8") as f:
        m = re.search(r'^APP_VERSION\s*=\s*"([0-9]+(?:\.[0-9]+)*)"', f.read(), re.M)
    if not m:
        sys.exit("APP_VERSION が見つかりません（mdeditor.py）")
    return m.group(1)


def zip_name():
    return f"{TOP}_v{app_version()}.zip"


def build():
    out = os.path.join(ROOT, "dist", zip_name())
    for src, _ in FILES:
        if not os.path.isfile(os.path.join(ROOT, src)):
            sys.exit(f"見つかりません: {src}（exe は build.cmd で作る）")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for src, name in FILES:
            z.write(os.path.join(ROOT, src), f"{TOP}/{name}")
    verify(out)
    return out


def verify(path):
    expected = sorted(f"{TOP}/{name}" for _, name in FILES)
    with zipfile.ZipFile(path) as z:
        actual = sorted(z.namelist())
        bad = z.testzip()
    if actual != expected or bad:
        sys.exit(f"zip の中身が想定と違います: {actual} 壊れ: {bad}")


if __name__ == "__main__":
    path = build()
    print(path, os.path.getsize(path), "bytes")
