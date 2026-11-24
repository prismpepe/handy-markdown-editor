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
    assert s == {"id": "u-1", "name": R.NAME_DEFAULT, "builtin": False, "steps": [{"find": "a", "replace": "b", "regex": False, "case": False}]}
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
