"""Windows のクリップボード（文字列）。ボタンからのコピー・貼り付けに使う。

画面側の navigator.clipboard は、権限や実行環境の事情で使えないことがある。
Win32 を直接呼べば、どの環境でも同じように動く。
"""
import ctypes
import time
from ctypes import wintypes

CF_UNICODETEXT = 13
CF_DIB = 8
CF_DIBV5 = 17
GMEM_MOVEABLE = 0x0002

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
kernel32.GlobalSize.restype = ctypes.c_size_t
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
user32.RegisterClipboardFormatW.restype = wintypes.UINT


def _open(retries=10):
    """他のアプリが握っていると開けないことがあるので、少し待って何度か試す。"""
    for _ in range(retries):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def get_text():
    """文字列を返す。文字列が無い（画像など）か、開けなければ None。"""
    if not _open():
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _read_bytes(fmt):
    """（クリップボードを開いたまま）指定した形式の中身を、バイト列で返す。無ければ None。"""
    if not user32.IsClipboardFormatAvailable(fmt):
        return None
    handle = user32.GetClipboardData(fmt)
    if not handle:
        return None
    size = kernel32.GlobalSize(handle)
    ptr = kernel32.GlobalLock(handle)
    if not ptr or not size:
        return None
    try:
        return ctypes.string_at(ptr, size)
    finally:
        kernel32.GlobalUnlock(handle)


def get_image_png():
    """クリップボードの画像を、PNG のバイト列で返す。画像が無い・変換できないときは None。
    登録された形式 "PNG"（ブラウザー・切り取りツールなど）があればそのまま、無ければ DIB から変換する。"""
    import pasteimg
    if not _open():
        return None
    try:
        png = _read_bytes(user32.RegisterClipboardFormatW("PNG"))
        if png and pasteimg.is_png(png):
            return png
        for fmt in (CF_DIB, CF_DIBV5):           # 標準の DIB を先に（DIBV5 は、Windows が変換して作ることが多く、並びが違うことがある）
            dib = _read_bytes(fmt)
            if dib:
                png = pasteimg.dib_to_png(dib)
                if png:
                    return png
        return None
    finally:
        user32.CloseClipboard()


def set_text(text):
    """文字列を書き込む。成功したら True。"""
    data = (text + "\0").encode("utf-16-le")
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        return False
    ptr = kernel32.GlobalLock(handle)
    if not ptr:
        kernel32.GlobalFree(handle)
        return False
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(handle)
    if not _open():
        kernel32.GlobalFree(handle)
        return False
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False
        return True                      # 所有権はクリップボードへ移った（解放しない）
    finally:
        user32.CloseClipboard()
