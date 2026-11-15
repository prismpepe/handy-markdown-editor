"""動作の記録（診断ログ）。ウィンドウが突然消えた・保存が反映されなかった、といった「あとから原因を調べたい」ときの材料。

- 記録するのは、起動・終了・保存・新しいウィンドウ・例外・止まらず動いている印（5 分ごと）。**文書の内容は書かない**
  （ファイルの場所・文字数・結果だけ）。
- 置き場は `%APPDATA%\\MarkdownEditor\\log\\`（`editor.log`。大きくなったら古い順に `.1` `.2` へ回し、3 世代で捨てる）。
  ネイティブの異常終了（画面部品の落下など）は、`fault.log` に呼び出しの跡が残る。
- 設定で切れる（保存の設定）。切っている間は、何も書かない。
- **記録の失敗で、アプリを止めない**（書けなくても、黙って捨てる）。
- 前回、終了の記録なしに消えたプロセスがあれば、起動時に「異常終了の疑い」として残す（強制終了・クラッシュの手がかり）。
- 画面に依存しない。
"""
import atexit
import datetime
import faulthandler
import os
import sys
import threading
import traceback

import multiwin

MAX_BYTES = 300_000           # 1 つのログファイルの大きさの上限
GENERATIONS = 3               # editor.log と、回した古い分（.1 .2）
HEARTBEAT_SECONDS = 300       # 動いている印を書く間隔
FIELD_MAX = 300               # 1 項目の長さの上限（長い文字列は切る）

_state = {"dir": None, "enabled": False, "fault": None, "hooks": False, "beat": None}
_lock = threading.RLock()


def _log_path(n=0):
    base = os.path.join(_state["dir"], "editor.log")
    return base if n == 0 else f"{base}.{n}"


def _fmt(v):
    s = str(v).replace("\r", " ").replace("\n", " ")
    if len(s) > FIELD_MAX:
        s = s[:FIELD_MAX] + "…"
    return '"' + s + '"' if (" " in s or not s) else s


def _rotate():
    try:
        if os.path.getsize(_log_path()) < MAX_BYTES:
            return
    except OSError:
        return
    for n in range(GENERATIONS - 1, 0, -1):
        try:
            src = _log_path(n - 1)
            if os.path.exists(src):
                os.replace(src, _log_path(n))
        except OSError:
            pass


def event(kind, **fields):
    """1 行書く。切っているとき・置き場が無いとき・書けないときは、何もしない（例外にしない）。"""
    if not (_state["enabled"] and _state["dir"]):
        return
    try:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"{now} pid={os.getpid()} {kind}" + "".join(f" {k}={_fmt(v)}" for k, v in fields.items()) + "\n"
        with _lock:
            os.makedirs(_state["dir"], exist_ok=True)
            _rotate()
            with open(_log_path(), "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass


def enabled():
    return bool(_state["enabled"])


def set_enabled(flag):
    """記録の入切。入れたら、異常終了の跡（faulthandler）も取り始める。切ったら、止める。"""
    flag = bool(flag)
    was = _state["enabled"]
    if was and not flag:
        event("log_off")                  # 切る前に、切ったことを書く
        _state["enabled"] = False
        _stop_fault()
    elif flag and not was:
        _state["enabled"] = True
        _start_fault()
        event("log_on")


def _start_fault():
    if _state["fault"] is not None or not _state["dir"]:
        return
    try:
        os.makedirs(_state["dir"], exist_ok=True)
        f = open(os.path.join(_state["dir"], "fault.log"), "a", encoding="utf-8")
        faulthandler.enable(file=f, all_threads=True)
        _state["fault"] = f
    except Exception:
        _state["fault"] = None


def _stop_fault():
    f = _state["fault"]
    if f is None:
        return
    try:
        faulthandler.disable()
        f.close()
    except Exception:
        pass
    _state["fault"] = None


def setup(folder, enabled_flag, app="editor", version=""):
    """起動時に 1 回。置き場と、入切を決める。入っていれば、起動を書き、前回の異常終了の疑いを調べる。"""
    _state["dir"] = folder
    _state["enabled"] = False
    set_enabled(bool(enabled_flag))
    if _state["enabled"]:
        frozen = bool(getattr(sys, "frozen", False))
        event("start", app=app, version=version, ppid=os.getppid(), frozen=frozen, mei=getattr(sys, "_MEIPASS", ""))
        check_previous()


def read_lines():
    """記録の行（古い順）。"""
    lines = []
    for n in range(GENERATIONS - 1, -1, -1):
        try:
            with open(_log_path(n), encoding="utf-8") as f:
                lines.extend(f.read().splitlines())
        except OSError:
            pass
    return lines


def _parse(line):
    """行から (時刻の文字列, pid, 種類)。読めなければ None。"""
    parts = line.split(" ", 4)
    if len(parts) < 4 or not parts[2].startswith("pid="):
        return None
    try:
        return parts[0] + " " + parts[1], int(parts[2][4:]), parts[3]
    except ValueError:
        return None


def previous_unclean():
    """起動の記録はあるのに、終了の記録がなく、もう動いていないプロセス: [(pid, 最後の記録の時刻)]。"""
    started, last, finished, reported = {}, {}, set(), set()
    for line in read_lines():
        p = _parse(line)
        if not p:
            continue
        when, pid, kind = p
        last[pid] = when
        if kind == "start":
            started[pid] = when
            finished.discard(pid)
        elif kind == "exit":
            finished.add(pid)
        elif kind == "unclean_suspected" and " target=" in line:
            try:
                reported.add(int(line.split(" target=", 1)[1].split(" ", 1)[0]))
            except ValueError:
                pass
    out = []
    for pid in started:
        if pid in finished or pid in reported or pid == os.getpid():
            continue
        if multiwin.is_alive(pid):
            continue
        out.append((pid, last.get(pid, "")))
    return out


def check_previous():
    for pid, last in previous_unclean():
        event("unclean_suspected", target=pid, last_seen=last)


def install_hooks():
    """終了・例外・止まらず動いている印を記録する。起動時に 1 回。"""
    if _state["hooks"]:
        return
    _state["hooks"] = True
    atexit.register(lambda: event("exit"))
    old_hook = sys.excepthook

    def excepthook(t, v, tb):
        event("exception", where="main", error="".join(traceback.format_exception(t, v, tb))[-1500:])
        old_hook(t, v, tb)

    sys.excepthook = excepthook
    old_thread_hook = getattr(threading, "excepthook", None)

    def thread_hook(args):
        event("exception", where="thread:" + str(getattr(args.thread, "name", "")),
              error="".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))[-1500:])
        if old_thread_hook is not None:
            old_thread_hook(args)

    if old_thread_hook is not None:
        threading.excepthook = thread_hook

    stop = threading.Event()

    def beat():
        while not stop.wait(HEARTBEAT_SECONDS):
            event("alive")

    t = threading.Thread(target=beat, name="applog-heartbeat", daemon=True)
    t.start()
    _state["beat"] = stop
