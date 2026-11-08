"""編集中の文書の下書き（自動保存）。異常終了・強制終了・Windows の再起動のあとで、未保存の内容を取り戻すため。

- 下書きは、文書そのものとは別の場所（置き場 `drafts\\`）に書く。**利用者のファイルは書き換えない**。
- 文書ごとに1つ（同じ文書の下書きは上書き）。保存していない「無題」は、1つだけ。
- 保存したとき・「保存しない」を選んだときは、その文書の下書きを消す。残るのは、保存も破棄もされずに
  終わった（＝異常終了した）ものだけ。
- 書き込みは、一時ファイルへ書いてから置き換える。書いている途中で止まっても、前の下書きは壊れない。
- 画面に依存しない。
"""
import datetime
import hashlib
import json
import os

import multiwin

MAX_DRAFTS = 50                 # 置き場に残す下書きの数の上限（超えたら古いものから消す）
UNTITLED = "untitled"
PREVIEW_CHARS = 60


def draft_key(path, slot=UNTITLED):
    """文書の下書きの名前。パスは大文字小文字を区別しない（Windows）。保存していない文書は、起動ごとに1つ（slot）。
    起動ごとに分けるのは、前回の未処理の下書きを、今回の「無題」が上書きしないため。"""
    if not path:
        return slot
    # 文書の下書きも、ウィンドウ（起動）ごとに分ける。同じ文書を、複数のウィンドウで開いても、下書きを取り合わない
    suffix = slot[len(UNTITLED):] if slot.startswith(UNTITLED) else ""
    return hashlib.sha1(os.path.abspath(path).lower().encode("utf-8")).hexdigest()[:16] + "s" + suffix


def _file(root, key):
    return os.path.join(root, key + ".json")


def save_draft(root, path, text, encoding="UTF-8", newline="CRLF", now=None, slot=UNTITLED, owner=None):
    """下書きを書く。中身が空（空白だけ）なら、守るものが無いので下書きを消す。書けたら下書きの名前（key）、消したら None。"""
    key = draft_key(path, slot)
    if not text or not text.strip():
        delete_draft(root, key)
        return None
    when = (now or datetime.datetime.now()).isoformat(timespec="seconds")
    body = {"path": path or None, "text": text, "encoding": encoding, "newline": newline, "saved_at": when,
            "owner": list(owner) if owner is not None else list(multiwin.process_stamp())}          # 書いたウィンドウ（プロセス）。動いている間は、「前回の残り」として出さない
    os.makedirs(root, exist_ok=True)
    target = _file(root, key)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)
    prune_drafts(root)
    return key


def delete_draft(root, key):
    try:
        os.remove(_file(root, key))
    except OSError:
        pass


def delete_for(root, *paths, slot=UNTITLED):
    """指定した文書（None は、この起動の「無題」）の下書きを消す。"""
    for p in paths:
        delete_draft(root, draft_key(p, slot))


def _load(root, key):
    try:
        with open(_file(root, key), encoding="utf-8") as f:
            body = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict) or not isinstance(body.get("text"), str):
        return None
    return body


def read_draft(root, key):
    """下書きの中身。壊れている・無いときは None。key は、list_drafts が返したものだけ使える。"""
    if not isinstance(key, str) or not key.isalnum():
        return None
    return _load(root, key)


def _disk_newer(body):
    """下書きのあとに、元のファイルが書き換えられたか（復元すると、その変更を上書きする恐れがある）。"""
    path = body.get("path")
    if not path:
        return False
    try:
        saved = datetime.datetime.fromisoformat(body.get("saved_at", ""))
        # 下書きの時刻は秒までなので、同じ秒の書き込みを「あとから書き換えられた」と誤らないよう、2秒の余裕を見る
        return datetime.datetime.fromtimestamp(os.path.getmtime(path)) > saved + datetime.timedelta(seconds=2)
    except (OSError, ValueError):
        return False


def _owner_alive(body):
    owner = body.get("owner")
    if not (isinstance(owner, list) and len(owner) == 2):
        return False                                       # 持ち主の記録が無い（旧い版の下書き）: 残りものとして扱う
    return multiwin.is_alive(owner[0], owner[1])


def list_drafts(root, skip_live=False):
    """残っている下書きの一覧（新しい順）。壊れたものは出さない。
    skip_live: 書いたウィンドウが、まだ動いている下書きは出さない（別のウィンドウで編集中のものを、前回の残りと取り違えない）。"""
    out = []
    try:
        names = [n[:-5] for n in os.listdir(root) if n.endswith(".json")]
    except OSError:
        return out
    for key in names:
        body = _load(root, key)
        if not body or (skip_live and _owner_alive(body)):
            continue
        text = body["text"]
        first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        out.append({
            "key": key, "path": body.get("path"), "chars": len(text),
            "saved_at": body.get("saved_at", ""), "preview": first[:PREVIEW_CHARS],
            "disk_newer": _disk_newer(body), "exists": bool(body.get("path")) and os.path.isfile(body["path"]),
        })
    out.sort(key=lambda d: d["saved_at"], reverse=True)
    return out


def prune_drafts(root, keep=MAX_DRAFTS):
    items = list_drafts(root)
    for d in items[keep:]:
        delete_draft(root, d["key"])
    try:
        for n in os.listdir(root):                       # 書き込みの途中で止まった一時ファイルを片づける
            if n.endswith(".tmp"):
                os.remove(os.path.join(root, n))
    except OSError:
        pass
