"""同じアプリを、複数のウィンドウ（複数のプロセス）で使うための部品。ビューアとエディタで、同じ内容。

- 他のウィンドウの位置を調べ、新しいウィンドウを、少しずらして開く（真上に重なって「開かなかった」ように見えるのを避ける）。
- 新しいウィンドウ（別のプロセス）を起動する。
- プロセスが、まだ動いているかを調べる（ロック・下書きの持ち主が、動いているかの確認に使う）。
- 設定ファイル（JSON）を、書き込みの途中で止まっても壊れない形で書く（一時ファイルに書いてから置き換える）。
画面（pywebview）には依存しない。
"""
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes

STILL_ACTIVE = 259
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def other_windows(marker):
    """このプロセス以外の、表示中（最小化していない）の最上位ウィンドウのうち、タイトルに marker を含むものの
    位置と大きさ: [(左, 上, 幅, 高さ)]。取れなければ空。"""
    if os.name != "nt":
        return []
    try:
        user32 = ctypes.windll.user32
        me = os.getpid()
        found = []
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def callback(hwnd, _):
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if not n:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if marker not in buf.value:
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == me:
                return True
            rect = wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                found.append((rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top))
            return True

        user32.EnumWindows(enum_proc(callback), 0)
        return found
    except Exception:
        return []


def cascade(x, y, others, step=32, tries=12, tolerance=10):
    """(x, y) に、他のウィンドウの左上が近いとき、右下へ step ずつずらす。ずらした先の (x, y) を返す。"""
    for _ in range(tries):
        if not any(abs(ox - x) <= tolerance and abs(oy - y) <= tolerance for ox, oy, _, _ in others):
            break
        x, y = x + step, y + step
    return x, y


def launch_self(args):
    """このアプリを、新しいウィンドウ（別のプロセス）で起動する。args は、引数の並び（ファイル・フォルダーのパスなど）。
    起動できたら True。このウィンドウを閉じても、新しいウィンドウは残る。"""
    try:
        if getattr(sys, "frozen", False):
            cmd = [sys.executable] + list(args)
        else:
            cmd = [sys.executable, os.path.abspath(sys.argv[0])] + list(args)
        flags = 0
        if os.name == "nt":
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(cmd, close_fds=True, creationflags=flags)
        return True
    except OSError:
        return False


def _creation_time(handle):
    c, e, k, u = (wintypes.FILETIME() for _ in range(4))
    if not ctypes.windll.kernel32.GetProcessTimes(handle, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
        return None
    return (c.dwHighDateTime << 32) | c.dwLowDateTime


def process_stamp(pid=None):
    """プロセスを見分けるための値 (pid, 起動した時刻)。pid が使い回されても、取り違えないため。取れなければ (pid, None)。"""
    pid = pid or os.getpid()
    if os.name != "nt":
        return pid, None
    try:
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = wintypes.HANDLE
        handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return pid, None
        try:
            return pid, _creation_time(handle)
        finally:
            k32.CloseHandle(handle)
    except Exception:
        return pid, None


def is_alive(pid, created=None):
    """pid のプロセスが、まだ動いているか。created（process_stamp の時刻）が分かっていれば、同じプロセスかも確かめる。
    調べられないときは、動いているものとして扱う（持ち主が生きているものを、誤って奪わないため）。"""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    try:
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = wintypes.HANDLE
        handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ctypes.windll.kernel32.GetLastError() == 5            # 5: アクセス拒否 = 存在するが、調べられない
        try:
            code = wintypes.DWORD()
            if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            if code.value != STILL_ACTIVE:
                return False
            if created is not None:
                now = _creation_time(handle)
                if now is not None and now != created:
                    return False                                           # pid が、別のプロセスに使い回されている
            return True
        finally:
            k32.CloseHandle(handle)
    except Exception:
        return True


def write_text_atomic(path, text):
    """文字列を（UTF-8 で）、一時ファイルに書いてから、置き換える。書き込みの途中で止まっても、元のファイルは壊れない。成功したら True。
    置き換え先を、別のプロセス（ブラウザーなど）が開いていて、一時的に置き換えられないことがあるので、少し待って何度か試す。"""
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        return False
    for _ in range(10):
        try:
            os.replace(tmp, path)
            return True
        except PermissionError:
            time.sleep(0.02)
        except OSError:
            break
    try:
        os.remove(tmp)
    except OSError:
        pass
    return False


def write_json_atomic(path, data):
    """JSON を、一時ファイルに書いてから、置き換える。書き込みの途中で止まっても、元のファイルは壊れない。
    別のプロセスが、置き換え先を読んでいて、一時的に置き換えられないことがあるので、少し待って何度か試す。成功したら True。"""
    folder = os.path.dirname(path)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        os.makedirs(folder, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        return False
    for _ in range(10):
        try:
            os.replace(tmp, path)
            return True
        except PermissionError:
            time.sleep(0.02)
        except OSError:
            break
    try:
        os.remove(tmp)
    except OSError:
        pass
    return False
