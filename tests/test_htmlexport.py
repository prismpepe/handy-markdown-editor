import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import dialogs
import multiwin
import mdeditor as appmod


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    return appmod.Api(None)


def test_html_save_kind_exists():
    label, pattern, ext, title = dialogs.SAVE_KINDS["html"]
    assert pattern == "*.html" and ext == "html"


def test_save_html_writes_utf8_and_adds_extension(api, tmp_path):
    r = api.save_html(str(tmp_path / "out"), "<!doctype html><title>日本語</title>")
    assert r["error"] is None and r["path"].endswith("out.html")
    assert open(r["path"], encoding="utf-8").read() == "<!doctype html><title>日本語</title>"
    assert r["bytes"] == len("<!doctype html><title>日本語</title>".encode("utf-8"))
    r2 = api.save_html(str(tmp_path / "b.htm"), "x")
    assert r2["path"].endswith("b.htm")                                      # .htm は、そのまま
    assert not [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]       # 一時ファイルは残らない


def test_save_html_keeps_existing_file_when_it_cannot_replace(api, tmp_path, monkeypatch):
    p = tmp_path / "keep.html"
    p.write_text("旧い内容", encoding="utf-8")
    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(PermissionError("locked")))
    monkeypatch.setattr(multiwin.time, "sleep", lambda s: None)
    r = api.save_html(str(p), "新しい内容")
    assert r["error"] and p.read_text(encoding="utf-8") == "旧い内容"           # 置き換えられなくても、元のファイルは壊れない
    assert not [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]


def test_save_html_rejects_bad_input_and_big_content(api, tmp_path, monkeypatch):
    assert api.save_html(None, "x")["error"] and api.save_html("", "x")["error"] and api.save_html(str(tmp_path / "a"), 5)["error"]
    monkeypatch.setattr(type(api), "MAX_HTML", 10)
    assert "大きすぎ" in api.save_html(str(tmp_path / "big"), "x" * 11)["error"]


def test_open_exported_html_only_opens_what_was_just_written(api, tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(os, "startfile", lambda p: opened.append(p), raising=False)
    other = tmp_path / "other.html"
    other.write_text("x", encoding="utf-8")
    assert api.open_exported_html(str(other))["error"] and not opened            # 書き出していないファイルは、開かない
    r = api.save_html(str(tmp_path / "mine.html"), "x")
    assert api.open_exported_html(r["path"]) == {"error": None} and opened == [r["path"]]
    assert api.open_exported_html(123)["error"] and api.open_exported_html(str(tmp_path / "evil.exe"))["error"]


def test_write_text_atomic_roundtrip(tmp_path):
    p = str(tmp_path / "sub" / "t.txt")
    assert multiwin.write_text_atomic(p, "あ\r\nい\n") is True
    assert open(p, "rb").read() == "あ\r\nい\n".encode("utf-8")                    # 改行を変えない
