import datetime
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import mdeditor
import snippets as S

NOW = datetime.datetime(2026, 11, 8, 9, 5)


def test_builtin_list_and_all_builtins_expand():
    names = [i["name"] for i in S.builtin_snippets()]
    assert "囲み（注意・ヒント）" in names and "折りたたみ" in names and len(set(names)) == len(names)
    for text in S.BUILTIN.values():
        out = S.expand(text, {}, "", NOW)
        assert "{{" not in out["text"] and "\x00" not in out["text"]


def test_selection_is_inserted_and_default_used_when_empty():
    assert S.expand("> **注意**　{{選択}}{{カーソル}}", {}, "ここを読む")["text"] == "> **注意**　ここを読む"
    assert S.expand("[{{選択:表示する文字}}]({{URL}})", {"URL": "https://x"}, "")["text"] == "[表示する文字](https://x)"
    assert S.expand("[{{選択:表示する文字}}]({{URL}})", {"URL": "https://x"}, "選んだ")["text"] == "[選んだ](https://x)"
    assert S.expand("<{{選択}}>", {}, "")["text"] == "<>"                       # 選んでいなくて既定値も無いときは、空


def test_cursor_position_and_removal():
    r = S.expand("ab{{カーソル}}cd", {}, "")
    assert r == {"text": "abcd", "cursor": 2}
    r = S.expand("> **注意**　{{選択}}{{カーソル}}", {}, "あい")
    assert r["text"].endswith("あい") and r["cursor"] == len(r["text"])        # 選んだ文字の後ろ
    r = S.expand("{{カーソル}}x{{カーソル}}", {}, "")
    assert r == {"text": "x", "cursor": 0}                                      # 複数あっても、最初の位置。印は全部消える
    assert S.expand("なし", {}, "")["cursor"] is None


def test_fields_exclude_reserved_and_builtin_names():
    fs = S.fields("{{選択}} {{カーソル}} {{日付}} {{URL}} {{見出し:詳細}} {{URL}}")
    assert fs == [{"name": "URL", "default": ""}, {"name": "見出し", "default": "詳細"}]


def test_builtin_date_fields_are_filled():
    assert S.expand("{{年月日}}（{{曜日}}）", {}, "", NOW)["text"] == "2026年11月8日（日）"


def test_values_and_selection_are_not_expanded_again():
    r = S.expand("[{{選択}}]({{URL}})", {"URL": "{{日付}}"}, "{{カーソル}}x")
    assert r["text"] == "[{{カーソル}}x]({{日付}})"                              # 入力・選んだ文字の中の {{ }} は、文字のまま
    assert r["cursor"] is None


def test_cannot_inject_reserved_values_from_fields():
    r = S.expand("{{選択}}|{{カーソル}}|", {"選択": "悪い", "カーソル": "悪い"}, "本物")
    assert r["text"] == "本物||" and r["cursor"] == 3                            # 欄の値で、特別な欄は書き換えられない


def test_escape_and_non_fields_stay():
    assert S.expand(r"\{{名前}} {{1}} {{ $x }}", {}, "")["text"] == "{{名前}} {{1}} {{ $x }}"


def test_user_snippets_listing(tmp_path):
    (tmp_path / "b.md").write_text("B", encoding="utf-8")
    (tmp_path / "A.md").write_text("A", encoding="utf-8")
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    items = S.user_snippets(str(tmp_path))
    assert [i["name"] for i in items] == ["A", "b"] and all(i["kind"] == "user" for i in items)
    assert S.user_snippets(str(tmp_path / "none")) == []


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return mdeditor.Api(None)


def test_api_list_get_expand(api, tmp_path):
    os.makedirs(api.snippet_folder())
    with open(os.path.join(api.snippet_folder(), "署名.md"), "w", encoding="utf-8") as f:
        f.write("{{氏名:山田}}\n{{日付}}")
    lst = api.list_snippets()
    assert lst["folder"] == api.snippet_folder()
    assert [i["name"] for i in lst["items"]][0] == "署名"                                   # 自分用が、組み込みより上（優先）
    mine = [i for i in lst["items"] if i["kind"] == "user"][0]
    got = api.get_snippet(mine["id"])
    assert got["error"] is None and got["fields"] == [{"name": "氏名", "default": "山田"}]
    b = api.get_snippet("builtin:囲み（注意・ヒント）")
    assert b["error"] is None and b["fields"] == [{"name": "種類", "default": "注意"}]       # 注意・ヒントを、1つにまとめて、種類を聞く
    assert api.expand_snippet(b["text"], {"種類": "注意"}, "本文")["text"] == "> **注意**　本文"
    assert api.expand_snippet(b["text"], {"種類": "ヒント"}, "本文")["text"] == "> **ヒント**　本文"


def test_api_get_snippet_refuses_outside_paths_and_big_files(api, tmp_path):
    outside = tmp_path / "secret.md"
    outside.write_text("秘密", encoding="utf-8")
    assert api.get_snippet("file:" + str(outside))["error"]                  # 置き場の外は読ませない
    assert api.get_snippet("file:" + os.path.join(api.snippet_folder(), "..", "secret.md"))["error"]
    assert api.get_snippet("builtin:ない")["error"] and api.get_snippet(None)["error"]
    os.makedirs(api.snippet_folder())
    big = os.path.join(api.snippet_folder(), "big.md")
    with open(big, "w", encoding="utf-8") as f:
        f.write("a" * (S.MAX_BYTES + 1))
    assert "大きすぎる" in api.get_snippet("file:" + big)["error"]


def test_api_expand_rejects_bad_types(api):
    assert api.expand_snippet(None, {}, "") == {"text": "", "cursor": None}
    assert api.expand_snippet("x{{a}}", "bad", "")["text"] == "x"
    assert api.expand_snippet("x", {}, None) == {"text": "", "cursor": None}
