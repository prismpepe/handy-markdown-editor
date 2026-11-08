"""ファイルを、ごみ箱へ移す（元に戻せるように、削除ではなく、ごみ箱へ）。Windows の SHFileOperation を使う。"""
import ctypes
import os
from ctypes import wintypes

FO_DELETE = 0x3
FOF_SILENT = 0x4
FOF_NOCONFIRMATION = 0x10
FOF_ALLOWUNDO = 0x40
FOF_NOERRORUI = 0x400


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                ("fFlags", wintypes.WORD), ("fAnyOperationsAborted", wintypes.BOOL), ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", wintypes.LPCWSTR)]


def move_to_trash(path):
    """path を、ごみ箱へ移す。移せたら True。ファイルが無い・移せないときは False。"""
    if os.name != "nt" or not os.path.exists(path):
        return False
    try:
        buf = ctypes.create_unicode_buffer(os.path.abspath(path) + "\0")          # 末尾は、二重の NUL
        op = SHFILEOPSTRUCTW()
        op.wFunc = FO_DELETE
        op.pFrom = ctypes.cast(buf, wintypes.LPCWSTR)
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
        rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        return rc == 0 and not op.fAnyOperationsAborted and not os.path.exists(path)
    except Exception:
        return False
