import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import mdeditor
import multiwin
import openlock as L


@pytest.fixture
def sleeper():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    yield p
    p.kill()
    p.wait()


def write_foreign_lock(root, path, proc):
    """別のプロセス（proc）が、このファイルを開いている印を、置く。"""
    import json
    os.makedirs(root, exist_ok=True)
    pid, created = multiwin.process_stamp(proc.pid)
    with open(os.path.join(root, L.lock_name(path)), "w", encoding="utf-8") as f:
        json.dump({"path": path, "owner": [pid, created], "since": "2026-11-08T10:00:00"}, f)


def test_own_lock_is_not_reported_as_elsewhere(tmp_path):
    root = str(tmp_path / "locks")
    doc = str(tmp_path / "a.md")
    assert L.claim(root, doc) is True
    assert L.holder(root, doc) is None                         # 自分の印は、「別のウィンドウ」ではない
    L.release(root, doc)
    assert not os.listdir(root)


def test_live_foreign_lock_is_reported_until_owner_exits(tmp_path, sleeper):
    root = str(tmp_path / "locks")
    doc = str(tmp_path / "a.md")
    write_foreign_lock(root, doc, sleeper)
    h = L.holder(root, doc)
    assert h == {"pid": sleeper.pid, "since": "2026-11-08T10:00:00"}
    assert L.holder(root, str(tmp_path / "other.md")) is None   # 別のファイルは、関係ない
    sleeper.kill()
    sleeper.wait()
    assert L.holder(root, doc) is None                          # 持ち主が終了したら、無いものとして扱う
    assert not os.listdir(root)                                 # 印も、片づけられる


def test_path_is_case_insensitive_and_normalized(tmp_path, sleeper):
    root = str(tmp_path / "locks")
    write_foreign_lock(root, str(tmp_path / "Doc.MD"), sleeper)
    assert L.holder(root, str(tmp_path / "doc.md")) is not None
    assert L.holder(root, str(tmp_path / "x" / ".." / "DOC.md")) is not None


def test_release_only_removes_own_lock(tmp_path, sleeper):
    root = str(tmp_path / "locks")
    doc = str(tmp_path / "a.md")
    write_foreign_lock(root, doc, sleeper)
    L.release(root, doc)                                        # 別のウィンドウの印は、消さない
    assert L.holder(root, doc) is not None


def test_claim_replaces_a_foreign_lock(tmp_path, sleeper):
    root = str(tmp_path / "locks")
    doc = str(tmp_path / "a.md")
    write_foreign_lock(root, doc, sleeper)
    assert L.claim(root, doc) is True                           # 承知のうえで開いた側が、最後に開いた持ち主になる
    assert L.holder(root, doc) is None


def test_sweep_removes_only_dead_owners_and_bad_files(tmp_path, sleeper):
    root = str(tmp_path / "locks")
    live, dead = str(tmp_path / "live.md"), str(tmp_path / "dead.md")
    write_foreign_lock(root, live, sleeper)
    import json
    with open(os.path.join(root, L.lock_name(dead)), "w", encoding="utf-8") as f:
        json.dump({"path": dead, "owner": [2_000_000_000, 1], "since": ""}, f)
    open(os.path.join(root, "broken.json"), "w").write("{壊れた")
    L.sweep(root)
    names = os.listdir(root)
    assert L.lock_name(live) in names and L.lock_name(dead) not in names
    L.sweep(str(tmp_path / "none"))                              # 置き場が無くても、失敗しない


def test_corrupt_lock_is_ignored(tmp_path):
    root = str(tmp_path)
    doc = str(tmp_path / "a.md")
    open(os.path.join(root, L.lock_name(doc)), "w").write("[1, 2]")
    assert L.holder(root, doc) is None


def test_api_open_elsewhere_claim_release(tmp_path, monkeypatch, sleeper):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    api = mdeditor.Api(None)
    doc = str(tmp_path / "a.md")
    assert api.open_elsewhere(doc) == {"elsewhere": False, "since": ""}
    write_foreign_lock(mdeditor.locks_root(), doc, sleeper)
    r = api.open_elsewhere(doc)
    assert r["elsewhere"] is True and r["since"].startswith("2026-11-08")
    assert api.claim_open(doc) is True                           # 承知のうえで開く
    assert api.open_elsewhere(doc)["elsewhere"] is False
    api.release_all_claims()                                     # 閉じるとき: 自分の印を、全部外す
    assert os.listdir(mdeditor.locks_root()) == []
    assert api.open_elsewhere(None) == {"elsewhere": False} and api.open_elsewhere(5) == {"elsewhere": False}


def test_api_open_in_new_window_validates_and_launches(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    api = mdeditor.Api(None)
    launched = []
    monkeypatch.setattr(multiwin, "launch_self", lambda args: launched.append(list(args)) or True)
    md = tmp_path / "a.md"
    md.write_text("x", encoding="utf-8")
    exe = tmp_path / "evil.exe"
    exe.write_text("x", encoding="utf-8")
    assert api.open_in_new_window(str(md)) == {"error": None} and launched[-1] == [str(md)]
    assert api.open_in_new_window(str(tmp_path)) == {"error": None} and launched[-1] == [str(tmp_path)]
    assert api.open_in_new_window(None) == {"error": None} and launched[-1] == []              # 空のウィンドウ
    n = len(launched)
    assert api.open_in_new_window(str(exe))["error"] and api.open_in_new_window(str(tmp_path / "none.md"))["error"]
    assert api.open_in_new_window(123)["error"]
    assert len(launched) == n                                    # Markdown ファイルとフォルダー以外は、起動しない
    monkeypatch.setattr(multiwin, "launch_self", lambda args: False)
    assert api.open_in_new_window(str(md))["error"]
