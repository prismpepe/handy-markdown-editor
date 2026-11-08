"""同じファイルを、複数のエディタのウィンドウで開いていないか、見張るための「開いている印」。

- ファイルを開いたウィンドウ（プロセス）が、置き場（`%APPDATA%\\MarkdownEditor\\locks\\`）に、印のファイルを置く。
  別のウィンドウが、同じファイルを開こうとしたとき、印の持ち主が**まだ動いていれば**、警告する。
- 持ち主が動いていない（異常終了など）印は、無いものとして扱い、片づける。pid が別のプロセスに使い回されても、
  起動した時刻で見分ける（multiwin.is_alive）。
- 警告するだけで、開けなくはしない（利用者が、承知のうえで開ける。読み取り専用で開く選択もある）。
  書き込みの競合は、保存のときの「他のアプリが変更しています」の確認（スタンプの比較）が、別に守っている。
- 画面に依存しない。
"""
import hashlib
import json
import os

import multiwin


def lock_name(path):
    """ファイルの印の名前。パスは大文字小文字を区別しない（Windows）。"""
    return hashlib.sha1(os.path.normcase(os.path.abspath(path)).encode("utf-8")).hexdigest()[:20] + ".json"


def _file(root, path):
    return os.path.join(root, lock_name(path))


def _read(root, path):
    try:
        with open(_file(root, path), encoding="utf-8") as f:
            body = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict) or not isinstance(body.get("owner"), list) or len(body["owner"]) != 2:
        return None
    return body


def holder(root, path):
    """このファイルを、別のウィンドウが開いていれば、その持ち主 {"pid", "since"}。無ければ（自分・動いていない持ち主）None。"""
    body = _read(root, path)
    if not body:
        return None
    pid, created = body["owner"]
    if pid == os.getpid():
        return None
    if not multiwin.is_alive(pid, created):
        try:
            os.remove(_file(root, path))                      # 動いていない持ち主の印は、片づける
        except OSError:
            pass
        return None
    return {"pid": pid, "since": body.get("since", "")}


def claim(root, path, now=None):
    """このウィンドウが、このファイルを開いた印を置く（すでに別の印があれば、置き換える）。置けたら True。"""
    import datetime
    pid, created = multiwin.process_stamp()
    body = {"path": os.path.abspath(path), "owner": [pid, created],
            "since": (now or datetime.datetime.now()).isoformat(timespec="seconds")}
    return multiwin.write_json_atomic(_file(root, path), body)


def release(root, path):
    """このウィンドウの印だけを消す（別のウィンドウの印は、残す）。"""
    body = _read(root, path)
    if body and body["owner"][0] == os.getpid():
        try:
            os.remove(_file(root, path))
        except OSError:
            pass


def sweep(root):
    """動いていない持ち主の印を、まとめて片づける（起動時）。"""
    try:
        names = [n for n in os.listdir(root) if n.endswith(".json")]
    except OSError:
        return
    for n in names:
        try:
            with open(os.path.join(root, n), encoding="utf-8") as f:
                body = json.load(f)
            pid, created = body["owner"]
            if pid != os.getpid() and not multiwin.is_alive(pid, created):
                os.remove(os.path.join(root, n))
        except (OSError, ValueError, KeyError, TypeError):
            pass
