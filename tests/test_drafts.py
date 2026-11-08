import datetime
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import drafts as D
import filemodel as fm
import uiprefs
import mdeditor


def test_save_list_and_overwrite(tmp_path):
    root = str(tmp_path / "d")
    k = D.save_draft(root, r"C:\docs\a.md", "# 本文\nあ", "UTF-8", "CRLF")
    assert k == D.draft_key(r"C:\docs\a.md")
    D.save_draft(root, r"C:\docs\a.md", "# 本文\nあい")           # 同じ文書は上書き
    items = D.list_drafts(root)
    assert len(items) == 1 and items[0]["chars"] == len("# 本文\nあい") and items[0]["preview"] == "# 本文"
    body = D.read_draft(root, k)
    assert body["text"] == "# 本文\nあい" and body["path"] == r"C:\docs\a.md"


def test_key_ignores_case_and_untitled_slots(tmp_path):
    assert D.draft_key(r"C:\Docs\A.md") == D.draft_key(r"c:\docs\a.md")
    assert D.draft_key(None, "untitledab") == "untitledab" != D.draft_key(None, "untitledcd")
    root = str(tmp_path)
    D.save_draft(root, None, "前回の無題", slot="untitled1")
    D.save_draft(root, None, "今回の無題", slot="untitled2")       # 前回の下書きを上書きしない
    assert {d["preview"] for d in D.list_drafts(root)} == {"前回の無題", "今回の無題"}
    D.delete_for(root, None, slot="untitled2")
    assert [d["preview"] for d in D.list_drafts(root)] == ["前回の無題"]


def test_blank_text_removes_draft(tmp_path):
    root = str(tmp_path)
    D.save_draft(root, "x.md", "中身")
    assert D.save_draft(root, "x.md", "  \n ") is None
    assert D.list_drafts(root) == []


def test_delete_and_corrupt_files(tmp_path):
    root = str(tmp_path)
    D.save_draft(root, "a.md", "A")
    (tmp_path / "bad.json").write_text("{壊れた", encoding="utf-8")
    (tmp_path / "list.json").write_text("[1]", encoding="utf-8")
    assert len(D.list_drafts(root)) == 1                       # 壊れたものは出さない
    assert D.read_draft(root, "bad") is None
    D.delete_for(root, "a.md")
    assert D.list_drafts(root) == []
    D.delete_draft(root, "nothing")                            # 無くても失敗しない
    assert D.list_drafts(str(tmp_path / "no_such_dir")) == []


def test_read_draft_rejects_path_tricks(tmp_path):
    D.save_draft(str(tmp_path), "a.md", "A")
    for bad in ("../x", "a/b", "..", "", None, 5):
        assert D.read_draft(str(tmp_path), bad) is None


def test_cap_keeps_newest(tmp_path):
    root = str(tmp_path)
    base = datetime.datetime(2026, 1, 1)
    for i in range(D.MAX_DRAFTS + 5):
        D.save_draft(root, f"f{i}.md", "x", now=base + datetime.timedelta(minutes=i))
    items = D.list_drafts(root)
    assert len(items) == D.MAX_DRAFTS
    assert D.draft_key("f0.md") not in {d["key"] for d in items}          # いちばん古いものから消える
    assert D.draft_key(f"f{D.MAX_DRAFTS + 4}.md") in {d["key"] for d in items}


def test_leftover_tmp_is_cleaned_and_write_is_atomic(tmp_path):
    root = str(tmp_path)
    (tmp_path / "x.json.tmp").write_text("書きかけ", encoding="utf-8")
    D.save_draft(root, "a.md", "A")
    assert not [n for n in os.listdir(root) if n.endswith(".tmp")]


def test_disk_newer_and_missing_file(tmp_path):
    root = str(tmp_path / "d")
    doc = tmp_path / "doc.md"
    doc.write_text("元", encoding="utf-8")
    D.save_draft(root, str(doc), "下書き", now=datetime.datetime.now() - datetime.timedelta(hours=1))
    d = D.list_drafts(root)[0]
    assert d["disk_newer"] is True and d["exists"] is True      # 下書きのあとに、ファイルが書き換えられた
    D.save_draft(root, str(doc), "下書き")
    assert D.list_drafts(root)[0]["disk_newer"] is False
    os.remove(doc)
    assert D.list_drafts(root)[0]["exists"] is False
    D.save_draft(root, None, "無題")
    assert [x for x in D.list_drafts(root) if x["path"] is None][0]["disk_newer"] is False


def test_clean_safety():
    assert uiprefs.clean_safety({"autosave": False, "interval": 60, "keep": 20}) == {"autosave": False, "interval": 60, "keep": 20}
    assert uiprefs.clean_safety({"interval": 7, "keep": 0}) == {}              # 候補にない間隔・範囲外の件数は捨てる
    assert uiprefs.clean_safety({"keep": 101}) == {} and uiprefs.clean_safety({"keep": 100}) == {"keep": 100}
    assert uiprefs.clean_safety({"autosave": "yes", "keep": True, "interval": 30.0}) == {"interval": 30}
    assert uiprefs.clean_safety(None) == {}
    assert uiprefs.clean_prefs({"safety": {"keep": 9}}) == {"safety": {"keep": 9}}


def test_backup_keep_is_configurable(tmp_path):
    path = str(tmp_path / "a.md")
    backup = str(tmp_path / "bk")
    for i in range(12):
        fm.write_document(path, f"v{i}", "UTF-8", "LF", backup_root=backup, backup_keep=3)
        time.sleep(0.002)
    kept = [f for d in os.listdir(backup) for f in os.listdir(os.path.join(backup, d))]
    assert len(kept) == 3
    fm.prune_backups(backup, 1)
    assert len([f for d in os.listdir(backup) for f in os.listdir(os.path.join(backup, d))]) == 1


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return mdeditor.Api(None)


def test_api_safety_defaults_and_set(api):
    assert api.safety() == {"autosave": True, "interval": 30, "keep": 5}
    api.set_prefs({"safety": {"autosave": False, "keep": 2}})
    assert api.safety() == {"autosave": False, "interval": 30, "keep": 2}
    assert api.get_prefs()["safety"] == {"autosave": False, "keep": 2}


def test_api_save_uses_configured_keep_and_prunes_at_once(api, tmp_path):
    api.set_prefs({"safety": {"keep": 2}})
    p = str(tmp_path / "x.md")
    stamp = None
    for i in range(6):
        r = api.save(p, f"v{i}", "UTF-8", "LF", stamp)
        assert r["ok"]
        stamp = r["stamp"]
        time.sleep(0.002)
    bk = mdeditor.backup_root()
    count = lambda: len([f for d in os.listdir(bk) for f in os.listdir(os.path.join(bk, d))])
    assert count() == 2
    api.set_prefs({"safety": {"keep": 1}})                     # 減らすと、すぐ整理する
    assert count() == 1


def test_api_drafts_roundtrip(api, tmp_path):
    root = mdeditor.drafts_root()
    r = api.save_draft(None, "無題の内容", "UTF-8", "CRLF")
    assert r["ok"] and r["key"].startswith("untitled")
    r2 = api.save_draft(str(tmp_path / "f.md"), "ファイルの内容", "Shift-JIS (CP932)", "LF")
    assert r2["ok"]
    items = D.list_drafts(root)                                  # 置き場にある、全部の下書き
    assert {i["preview"] for i in items} == {"無題の内容", "ファイルの内容"}
    body = api.get_draft(r2["key"])
    assert body["encoding"] == "Shift-JIS (CP932)" and body["newline"] == "LF"
    assert api.list_drafts() == []                               # 自分（動いているウィンドウ）が書いたものは、「前回の残り」として出さない
    assert api.save_draft(None, 5)["ok"] is False
    assert api.save_draft(123, "x")["ok"] is False
    api.discard_drafts_for([None])
    assert [i["preview"] for i in D.list_drafts(root)] == ["ファイルの内容"]
    api.discard_draft("../evil")                                 # 名前に使えないものは、何もしない
    api.discard_draft(r2["key"])
    assert D.list_drafts(root) == []


def test_api_draft_does_not_touch_the_document(api, tmp_path):
    p = tmp_path / "keep.md"
    p.write_text("元の内容", encoding="utf-8")
    api.save_draft(str(p), "書き換え中", "UTF-8", "LF")
    assert p.read_text(encoding="utf-8") == "元の内容"          # 文書のファイルは、下書きでは書き換えない
    assert api.save_draft(str(p), "   ")["key"] is None


DEAD = [2_000_000_000, 12345]            # 動いていないプロセス（存在しない pid）


def test_same_document_in_two_windows_has_separate_drafts(tmp_path):
    root = str(tmp_path)
    D.save_draft(root, "a.md", "窓1の内容", slot="untitledaa")
    D.save_draft(root, "a.md", "窓2の内容", slot="untitledbb")
    assert len(D.list_drafts(root)) == 2                                      # 取り合わない
    D.delete_for(root, "a.md", slot="untitledaa")                              # 窓1が保存したら、窓1の下書きだけ消える
    assert [d["preview"] for d in D.list_drafts(root)] == ["窓2の内容"]


def test_drafts_of_live_windows_are_not_offered_for_restore(tmp_path):
    import subprocess
    import multiwin
    root = str(tmp_path)
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        D.save_draft(root, "live.md", "生きているウィンドウの下書き", slot="untitledlive", owner=list(multiwin.process_stamp(p.pid)))
        D.save_draft(root, "dead.md", "異常終了した下書き", slot="untitleddead", owner=DEAD)
        D.save_draft(root, "mine.md", "自分の下書き", slot="untitledmine")
        assert {d["preview"] for d in D.list_drafts(root)} == {"生きているウィンドウの下書き", "異常終了した下書き", "自分の下書き"}
        assert [d["preview"] for d in D.list_drafts(root, skip_live=True)] == ["異常終了した下書き"]     # 残りものだけ
    finally:
        p.kill()
        p.wait()
    assert {d["preview"] for d in D.list_drafts(root, skip_live=True)} == {"生きているウィンドウの下書き", "異常終了した下書き"}   # 終了したら、残りもの


def test_old_drafts_without_owner_are_offered(tmp_path):
    import json
    root = str(tmp_path)
    (tmp_path / "x.json").write_text(json.dumps({"path": None, "text": "旧い版の下書き", "saved_at": "2026-01-01T00:00:00"}), encoding="utf-8")
    assert [d["preview"] for d in D.list_drafts(root, skip_live=True)] == ["旧い版の下書き"]
