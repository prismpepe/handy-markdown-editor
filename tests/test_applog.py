import os
import sys

import pytest

import applog


@pytest.fixture
def log(tmp_path):
    folder = str(tmp_path / "log")
    applog._state.update({"dir": None, "enabled": False})
    yield folder
    applog.set_enabled(False)
    applog._state.update({"dir": None, "enabled": False})


def test_切っている間は_何も書かない(log):
    applog.setup(log, False)
    applog.event("save", path="a.md")
    assert not os.path.exists(log)


def test_入れると_起動と出来事が書かれ_文書の内容は書かない(log):
    applog.setup(log, True, app="editor", version="9.9")
    applog.event("save", path="C:\\docs\\a.md", chars=12, result="ok")
    text = open(os.path.join(log, "editor.log"), encoding="utf-8").read()
    assert " start " in text and "version=9.9" in text
    assert "save path=C:\\docs\\a.md chars=12 result=ok" in text
    assert f"pid={os.getpid()}" in text


def test_改行や長い値は_1行に収める(log):
    applog.setup(log, True)
    applog.event("x", v="a\nb", long="y" * 1000)
    lines = open(os.path.join(log, "editor.log"), encoding="utf-8").read().splitlines()
    assert len([l for l in lines if " x " in l]) == 1
    assert len(lines[-1]) < 600


def test_大きくなったら_回して_3世代で捨てる(log, monkeypatch):
    monkeypatch.setattr(applog, "MAX_BYTES", 400)
    applog.setup(log, True)
    for i in range(80):
        applog.event("tick", n=i, pad="z" * 30)
    names = sorted(os.listdir(log))
    assert "editor.log" in names and "editor.log.1" in names and "editor.log.3" not in names


def test_途中で切ったり入れたりできる(log):
    applog.setup(log, True)
    applog.set_enabled(False)
    applog.event("hidden")
    applog.set_enabled(True)
    applog.event("shown")
    text = open(os.path.join(log, "editor.log"), encoding="utf-8").read()
    assert "hidden" not in text and "shown" in text and "log_off" in text and "log_on" in text


def test_書けなくても_例外にしない(tmp_path):
    blocked = tmp_path / "file"
    blocked.write_text("x")                                           # フォルダにできない場所
    applog._state.update({"dir": str(blocked / "log"), "enabled": True})
    applog.event("save")                                              # 例外にならない
    applog._state.update({"dir": None, "enabled": False})


def test_終了の記録がなく_動いてもいないプロセスは_異常終了の疑い(log):
    applog.setup(log, True)
    ghost = 2_000_000_000                                              # 存在しない pid
    with open(os.path.join(log, "editor.log"), "a", encoding="utf-8") as f:
        f.write(f"2026-11-16 00:30:00.000 pid={ghost} start app=editor\n")
        f.write(f"2026-11-16 00:31:00.000 pid={ghost} alive\n")
        f.write("2026-11-16 00:30:00.000 pid=1999999999 start app=editor\n")
        f.write("2026-11-16 00:40:00.000 pid=1999999999 exit\n")        # 正常終了
    found = dict(applog.previous_unclean())
    assert ghost in found and found[ghost] == "2026-11-16 00:31:00.000"
    assert 1999999999 not in found
    applog.check_previous()
    assert ghost not in dict(applog.previous_unclean())                # 1 度知らせたら、繰り返さない
    assert "unclean_suspected target=%d" % ghost in open(os.path.join(log, "editor.log"), encoding="utf-8").read()


def test_自分自身は_異常終了の疑いに入れない(log):
    applog.setup(log, True)
    assert os.getpid() not in dict(applog.previous_unclean())


def test_保存すると_記録に残り_設定で切れる(tmp_path, monkeypatch):
    import mdeditor
    monkeypatch.setenv("APPDATA", str(tmp_path))
    api = mdeditor.Api(None)
    applog._state.update({"dir": None, "enabled": False})
    applog.setup(mdeditor.log_root(), True, "editor", "t")
    doc = tmp_path / "x.md"
    doc.write_text("old", encoding="utf-8")
    r = api.save(str(doc), "新しい内容", "UTF-8", "LF", None)
    assert r["ok"] is True
    text = open(os.path.join(mdeditor.log_root(), "editor.log"), encoding="utf-8").read()
    assert "save path=" in text and "chars=5 result=ok" in text and "新しい内容" not in text     # 内容は書かない
    api.set_prefs({"safety": {"log": False}})
    assert applog.enabled() is False
    api.save(str(doc), "さらに", "UTF-8", "LF", None)
    assert "chars=3" not in open(os.path.join(mdeditor.log_root(), "editor.log"), encoding="utf-8").read()
    applog.set_enabled(False)
    applog._state.update({"dir": None, "enabled": False})
