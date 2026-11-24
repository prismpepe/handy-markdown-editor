"""置換セットの保存と、標準のセット（replacesets.py）。"""
import json
import os
import re

import replacesets as R


def test_標準のセットは_型が正しく_正規表現として読める():
    ids = set()
    for s in R.BUILTIN:
        assert s["builtin"] is True and s["id"].startswith("b-") and s["id"] not in ids and s["name"] and s["steps"]
        ids.add(s["id"])
        for st in s["steps"]:
            assert set(st) == {"find", "replace", "regex", "case"}
            if st["regex"]:
                re.compile(st["find"])                           # Python の re でも読める形（前読みなど、共通の範囲）


def test_clean_set_は_使えないものを捨て_足りないものを補う():
    s = R.clean_set({"id": "u-1", "name": "  ", "steps": [{"find": "a", "replace": "b"}, {"find": 1, "replace": "x"}, "bad"]})
    assert s == {"id": "u-1", "name": R.NAME_DEFAULT, "builtin": False, "scope": "user", "steps": [{"find": "a", "replace": "b", "regex": False, "case": False}]}
    assert R.clean_set({"id": "b-img", "name": "x", "steps": []}) is None           # 標準の id は使えない
    assert R.clean_set({"id": "u-1", "name": "x"}) is None and R.clean_set("x") is None
    assert R.clean_set({"id": "u-2", "name": "n", "steps": [{"find": "x" * 3000, "replace": ""}]})["steps"] == []     # 長すぎる手順は捨てる
    long = R.clean_set({"id": "u-3", "name": "n" * 200, "steps": []})
    assert long is None or len(long["name"]) <= R.MAX_NAME or long["name"] == R.NAME_DEFAULT


def test_真偽は_True_だけを正規表現_大小区別として読む():
    s = R.clean_set({"id": "u-1", "name": "n", "steps": [{"find": "a", "replace": "b", "regex": "yes", "case": 1}]})
    assert s["steps"][0]["regex"] is False and s["steps"][0]["case"] is False


def test_clean_sets_は_重複する_id_と_上限を超えた分を捨てる():
    many = [{"id": "u-%d" % i, "name": "n", "steps": []} for i in range(R.MAX_SETS + 5)]
    assert len(R.clean_sets(many)) == R.MAX_SETS
    dup = R.clean_sets([{"id": "u-1", "name": "a", "steps": []}, {"id": "u-1", "name": "b", "steps": []}])
    assert [d["name"] for d in dup] == ["a"]
    assert R.clean_sets("x") == [] and R.clean_sets(None) == []


def test_保存して_読み戻せる_壊れたファイルは_空(tmp_path):
    p = str(tmp_path / "sub" / "replace_sets.json")
    saved = R.save(p, [{"id": "u-1", "name": "画像", "steps": [{"find": r"!\[(.*)\]", "replace": "$1", "regex": True, "case": False}]}])
    assert R.load(p) == saved and saved[0]["steps"][0]["regex"] is True
    assert json.load(open(p, encoding="utf-8"))["version"] == 1
    assert not [f for f in os.listdir(os.path.dirname(p)) if f.endswith(".tmp")]          # 一時ファイルが残らない
    open(p, "w", encoding="utf-8").write("{壊れた")
    assert R.load(p) == []
    assert R.load(str(tmp_path / "none.json")) == []


def test_Api_から_標準と_利用者のセットを_取り出し_保存できる(tmp_path, monkeypatch):
    import mdeditor
    monkeypatch.setenv("APPDATA", str(tmp_path))
    api = mdeditor.Api(None)
    r = api.replace_sets_get()
    assert len(r["builtin"]) == len(R.BUILTIN) and r["user"] == []
    out = api.replace_sets_save([{"id": "u-9", "name": "x", "steps": [{"find": "a", "replace": "b"}]}, {"id": "b-img", "name": "なりすまし", "steps": []}])
    assert out["ok"] and [s["id"] for s in out["user"]] == ["u-9"]
    assert [s["id"] for s in api.replace_sets_get()["user"]] == ["u-9"]


# ---------------------------------------------------------------- 文書フォルダー用のセット
def test_idが無いセットは_名前から_idを作り_重ならない():
    a = R.clean_set({"name": "画像", "steps": []}, set(), "project")
    b = R.clean_set({"name": "画像", "steps": []}, set(), "project")
    assert a["id"] == b["id"] and a["id"].startswith("p-") and a["scope"] == "project"
    both = R.clean_sets([{"name": "同じ名前", "steps": []}, {"name": "同じ名前", "steps": []}], "project")
    assert len(both) == 2 and both[0]["id"] != both[1]["id"]
    assert R.clean_set({"id": "x-1", "name": "n", "steps": []}) is None                 # 形の正しくない id は使えない


def test_フォルダー用のセットは_読み書きでき_scope_が_project_になる(tmp_path):
    d = str(tmp_path / ".markdown-editor")
    assert R.load_project(d) == [] and R.load_project(None) == []
    saved = R.save(R.project_path(d), [{"name": "管理組合の表記", "steps": [{"find": "ＡＢＣ", "replace": "ABC"}]}], "project")
    assert saved[0]["scope"] == "project" and R.load_project(d) == saved
    # 手で書いたファイル（id なし・余計な項目つき）も、読める
    open(R.project_path(d), "w", encoding="utf-8").write(json.dumps({"sets": [{"name": "手書き", "extra": 1, "steps": [{"find": "a", "replace": "b", "regex": True}]}]}, ensure_ascii=False))
    loaded = R.load_project(d)
    assert [x["name"] for x in loaded] == ["手書き"] and loaded[0]["steps"][0]["regex"] is True and loaded[0]["id"].startswith("p-")


def test_write_inherit_は_ほかの項目を残す(tmp_path):
    import settingsdir
    d = str(tmp_path / ".markdown-editor"); os.makedirs(d)
    open(os.path.join(d, "settings.json"), "w", encoding="utf-8").write(json.dumps({"snippets": {"inherit": False}}))
    settingsdir.write_inherit(d, R.KIND, False)
    cfg = json.load(open(os.path.join(d, "settings.json"), encoding="utf-8"))
    assert cfg == {"snippets": {"inherit": False}, "replace_sets": {"inherit": False}}
    assert settingsdir.read_inherit(d, R.KIND) is False
    settingsdir.write_inherit(d, R.KIND, True)
    assert settingsdir.read_inherit(d, R.KIND) is True


def test_Api_文書のフォルダーに_フォルダー用のセットを_保存し_読み出せる(tmp_path, monkeypatch):
    import mdeditor
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    api = mdeditor.Api(None)
    proj = tmp_path / "管理組合" / "議事録"; proj.mkdir(parents=True)
    doc = str(proj / "a.md"); open(doc, "w").close()
    info = api.replace_sets_get(doc)["info"]
    assert info["can_project"] and not info["exists"] and info["path"].endswith(os.path.join(".markdown-editor", "replace_sets.json"))
    assert not (proj / ".markdown-editor").exists()                                     # 読むだけでは、何も作らない
    r = api.replace_sets_save([], [{"id": "p-1", "name": "表記", "steps": [{"find": "a", "replace": "b"}]}], doc)
    assert r["ok"] and r["project"][0]["scope"] == "project"
    assert (proj / ".markdown-editor" / "replace_sets.json").is_file()
    g = api.replace_sets_get(str(proj))
    assert [s["name"] for s in g["project"]] == ["表記"] and g["info"]["exists"] and g["info"]["inherit"] is True
    # 親のフォルダーにある設定は、さかのぼって見つかる（子の文書でも、使える）
    sub = proj / "2026"; sub.mkdir(); (sub / "b.md").write_text("x")
    assert [s["name"] for s in api.replace_sets_get(str(sub / "b.md"))["project"]] == ["表記"]
    # inherit を false にすると、設定ファイルに書かれ、読み出しにも出る
    api.replace_sets_save([], g["project"], doc, False)
    assert api.replace_sets_get(doc)["info"]["inherit"] is False
    api.replace_sets_save([], g["project"], doc, True)
    assert api.replace_sets_get(doc)["info"]["inherit"] is True
    # 空にして保存しても、ファイルは残る（消さない）
    api.replace_sets_save([], [], doc)
    assert (proj / ".markdown-editor" / "replace_sets.json").is_file() and api.replace_sets_get(doc)["project"] == []


def test_Api_文書の場所が分からないとき_フォルダー用は_保存しない(tmp_path, monkeypatch):
    import mdeditor
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    api = mdeditor.Api(None)
    assert api.replace_sets_get(None)["info"]["can_project"] is False
    r = api.replace_sets_save([], [{"id": "p-1", "name": "x", "steps": []}], None)
    assert r["ok"] is False and "文書" in r["message"]
    assert api.replace_sets_save([], [], None)["ok"] is True                          # 空なら、何もしない
    assert api.open_replace_sets_folder(None)["error"]
