import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import multiwin as M


def test_cascade_moves_away_from_other_windows():
    assert M.cascade(100, 100, []) == (100, 100)
    assert M.cascade(100, 100, [(100, 100, 800, 600)]) == (132, 132)
    assert M.cascade(100, 100, [(100, 100, 800, 600), (132, 132, 800, 600), (164, 164, 800, 600)]) == (196, 196)
    assert M.cascade(100, 100, [(300, 300, 800, 600)]) == (100, 100)               # 離れていれば、そのまま
    assert M.cascade(100, 100, [(105, 95, 800, 600)]) == (132, 132)                # 少しのずれは、同じ位置とみなす
    x, y = M.cascade(0, 0, [(i * 32, i * 32, 1, 1) for i in range(50)])            # 無限に探さない（上限がある）
    assert (x, y) == (12 * 32, 12 * 32)


def test_other_windows_does_not_include_self_and_never_raises():
    assert isinstance(M.other_windows("このタイトルのウィンドウは存在しない-xyz"), list)
    assert M.other_windows("") is not None


def test_is_alive():
    assert M.is_alive(os.getpid()) is True
    assert M.is_alive(0) is False and M.is_alive(-5) is False and M.is_alive("x") is False
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        pid, created = M.process_stamp(p.pid)
        assert M.is_alive(pid, created) is True
        assert M.is_alive(pid, (created or 0) + 12345) is (True if created is None else False)   # 起動時刻が違えば、別のプロセス
    finally:
        p.kill()
        p.wait()
    assert M.is_alive(p.pid) is False                                              # 終了したら、動いていない


def test_process_stamp_of_self():
    pid, created = M.process_stamp()
    assert pid == os.getpid() and (created is None or created > 0)


def test_write_json_atomic(tmp_path):
    p = str(tmp_path / "sub" / "settings.json")
    assert M.write_json_atomic(p, {"a": "日本語", "b": [1, 2]}) is True
    assert json.load(open(p, encoding="utf-8")) == {"a": "日本語", "b": [1, 2]}
    assert M.write_json_atomic(p, {"a": 2}) is True
    assert json.load(open(p, encoding="utf-8")) == {"a": 2}
    assert not [n for n in os.listdir(tmp_path / "sub") if n.endswith(".tmp")]      # 一時ファイルは残らない


def test_write_json_atomic_keeps_old_file_when_data_cannot_be_written(tmp_path):
    p = str(tmp_path / "settings.json")
    M.write_json_atomic(p, {"ok": 1})
    try:
        M.write_json_atomic(p, {"bad": object()})
    except TypeError:
        pass                                                                        # 書き込みの途中で失敗しても
    assert json.load(open(p, encoding="utf-8")) == {"ok": 1}                         # 元のファイルは、壊れていない


def test_launch_self_uses_current_executable(monkeypatch):
    seen = {}

    class Fake:
        def __init__(self, cmd, **kw):
            seen["cmd"], seen["kw"] = cmd, kw

    monkeypatch.setattr(subprocess, "Popen", Fake)
    assert M.launch_self(["C:\docs\a.md"]) is True
    assert seen["cmd"][0] == sys.executable and seen["cmd"][-1] == "C:\docs\a.md"
    if os.name == "nt":
        assert seen["kw"]["creationflags"] & subprocess.DETACHED_PROCESS                # 元のウィンドウを閉じても、残る
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert M.launch_self([]) is True and seen["cmd"] == [sys.executable]
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    assert M.launch_self([]) is False
