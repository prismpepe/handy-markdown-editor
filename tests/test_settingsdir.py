import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import settingsdir as S


def make_settings(root, kind_files=None, cfg=None):
    sd = os.path.join(root, S.SETTINGS_DIR)
    os.makedirs(sd, exist_ok=True)
    for kind, files in (kind_files or {}).items():
        os.makedirs(os.path.join(sd, kind), exist_ok=True)
        for name, text in files.items():
            with open(os.path.join(sd, kind, name + ".md"), "w", encoding="utf-8") as f:
                f.write(text)
    if cfg is not None:
        with open(os.path.join(sd, "settings.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)
    return sd


def test_find_walks_up_to_the_nearest_settings_dir(tmp_path):
    sd = make_settings(str(tmp_path))
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    doc = deep / "x.md"
    doc.write_text("x", encoding="utf-8")
    assert S.find_settings_dir(str(deep)) == sd                  # 親へさかのぼる
    assert S.find_settings_dir(str(doc)) == sd                   # ファイルを渡しても、そのフォルダーから
    inner = make_settings(str(tmp_path / "a"))
    assert S.find_settings_dir(str(deep)) == inner               # 近い方（a の設定）が先


def test_find_returns_none_when_missing_or_bad_input(tmp_path):
    assert S.find_settings_dir(str(tmp_path)) is None
    assert S.find_settings_dir(None) is None and S.find_settings_dir("") is None and S.find_settings_dir(5) is None
    (tmp_path / ".markdown-editor").write_text("ファイルであって、フォルダーではない", encoding="utf-8")
    assert S.find_settings_dir(str(tmp_path)) != str(tmp_path / ".markdown-editor")


def test_kind_dir_and_inherit_defaults(tmp_path):
    sd = make_settings(str(tmp_path), {"snippets": {"a": "A"}})
    assert S.kind_dir(sd, "snippets") and S.kind_dir(sd, "templates") is None
    assert S.kind_dir(sd, "bad") is None and S.kind_dir(None, "snippets") is None
    assert S.read_inherit(sd, "snippets") is True                # settings.json が無ければ、下の層に追加
    make_settings(str(tmp_path), cfg={"snippets": {"inherit": False}, "templates": {"inherit": "no"}})
    assert S.read_inherit(sd, "snippets") is False
    assert S.read_inherit(sd, "templates") is True               # 真偽値でないものは、既定（追加）
    (tmp_path / S.SETTINGS_DIR / "settings.json").write_text("{壊れた", encoding="utf-8")
    assert S.read_inherit(sd, "snippets") is True


def item(name, kind):
    return {"id": "x:" + name, "name": name, "kind": kind}


def test_merge_union_with_priority_and_replace_mode():
    project = [item("注意", "project"), item("独自", "project")]
    user = [item("注意", "user"), item("自分の", "user")]
    builtin = [item("注意", "builtin"), item("日付", "builtin")]
    merged = S.merge(project, user, builtin, True, True)
    assert [(i["name"], i["kind"]) for i in merged] == [("注意", "project"), ("独自", "project"), ("自分の", "user"), ("日付", "builtin")]
    assert S.merge(project, user, builtin, True, False) == project              # 置き換え: そのフォルダーだけ
    assert [i["kind"] for i in S.merge([], user, builtin, False, False)] == ["user", "user", "builtin"]   # フォルダーが無ければ、下の層（inherit は無関係）
    assert S.merge([], [], builtin, False, True) == builtin                      # 何も無ければ、組み込み（メモリの既定値）
    assert [i["name"] for i in S.merge([], [item("Memo", "user")], [item("memo", "builtin")], False, True)] == ["Memo"]   # 名前は、大文字小文字を区別しない


def test_safe_file_name():
    assert S.safe_file_name('a/b:c*d?"e<f>g|h\\i') == "a_b_c_d__e_f_g_h_i"
    assert S.safe_file_name("  名前. ") == "名前" and S.safe_file_name("...") == "無題" and S.safe_file_name("") == "無題"
    assert len(S.safe_file_name("あ" * 200)) == 80


def test_export_set_writes_files_without_overwriting_and_sets_inherit_false(tmp_path):
    sd = str(tmp_path / S.SETTINGS_DIR)
    os.makedirs(sd)
    r = S.export_set(sd, "snippets", [{"name": "日付", "text": "{{日付}}"}, {"name": "a/b", "text": "AB"}])
    assert r == {"written": 2, "skipped": 0}
    assert open(os.path.join(sd, "snippets", "日付.md"), encoding="utf-8").read() == "{{日付}}"
    assert os.path.isfile(os.path.join(sd, "snippets", "a_b.md"))
    (tmp_path / S.SETTINGS_DIR / "snippets" / "日付.md").write_text("利用者が書き換えた", encoding="utf-8")
    r2 = S.export_set(sd, "snippets", [{"name": "日付", "text": "{{日付}}"}, {"name": "新規", "text": "N"}])
    assert r2 == {"written": 1, "skipped": 1}                                  # 書き換えたものは、上書きしない
    assert open(os.path.join(sd, "snippets", "日付.md"), encoding="utf-8").read() == "利用者が書き換えた"
    cfg = json.load(open(os.path.join(sd, "settings.json"), encoding="utf-8"))
    assert cfg == {"snippets": {"inherit": False}}
    S.export_set(sd, "templates", [{"name": "議事録", "text": "T"}])
    cfg = json.load(open(os.path.join(sd, "settings.json"), encoding="utf-8"))
    assert cfg == {"snippets": {"inherit": False}, "templates": {"inherit": False}}   # 別の種類の設定は、残る


def test_list_md_sorted_and_only_md_files(tmp_path):
    for n in ("b.md", "A.md", "x.txt"):
        (tmp_path / n).write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    items = S.list_md(str(tmp_path), "project")
    assert [i["name"] for i in items] == ["A", "b"] and all(i["kind"] == "project" for i in items)
    assert S.list_md(str(tmp_path / "none"), "project") == []


def test_recycle_moves_file_out_of_place(tmp_path, monkeypatch):
    import recycle
    p = tmp_path / "gone.md"
    p.write_text("x", encoding="utf-8")
    calls = []

    class FakeShell:
        def SHFileOperationW(self, ref):
            calls.append(True)
            os.remove(str(p))                                                    # ごみ箱へ移った（元の場所から消えた）ことにする
            return 0

    class FakeWin:
        shell32 = FakeShell()

    monkeypatch.setattr(recycle.ctypes, "windll", FakeWin(), raising=False)
    assert recycle.move_to_trash(str(p)) is True and calls
    assert recycle.move_to_trash(str(tmp_path / "none.md")) is False             # 無いファイルは、False
