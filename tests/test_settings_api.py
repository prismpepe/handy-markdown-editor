import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import mdeditor
import recycle
import settingsdir as S
import snippets
import templating


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    return mdeditor.Api(None)


def project(tmp_path, snippets_files=None, templates_files=None, cfg=None):
    root = tmp_path / "proj"
    sd = root / S.SETTINGS_DIR
    for kind, files in (("snippets", snippets_files), ("templates", templates_files)):
        if files is not None:
            (sd / kind).mkdir(parents=True, exist_ok=True)
            for n, t in files.items():
                (sd / kind / (n + ".md")).write_text(t, encoding="utf-8")
    if cfg is not None:
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "settings.json").write_text(json.dumps(cfg), encoding="utf-8")
    (root / "docs").mkdir(parents=True, exist_ok=True)
    doc = root / "docs" / "a.md"
    doc.write_text("x", encoding="utf-8")
    return root, str(doc)


def names(r):
    return [(i["name"], i["kind"]) for i in r["items"]]


def test_no_settings_means_builtin_defaults(api, tmp_path):
    root, doc = project(tmp_path)
    r = api.list_snippets(doc)
    assert [n for n, k in names(r)] == list(snippets.BUILTIN) and r["project"] is None
    assert all(k == "builtin" for _, k in names(r))
    assert api.list_snippets(None)["items"] == r["items"]                      # 文脈が無くても、同じ（既定値）


def test_project_settings_are_found_from_the_document_and_win(api, tmp_path):
    root, doc = project(tmp_path, {"日付（年月日・曜日）": "独自の日付: {{日付}}", "新規": "N"})        # inherit 指定なし = 追加
    r = api.list_snippets(doc)
    got = dict(names(r))
    assert got["日付（年月日・曜日）"] == "project" and got["新規"] == "project"            # 同じ名前は、文書フォルダーが優先
    assert got["日時"] == "builtin"                                                       # ほかの組み込みは、残る
    assert r["project"].endswith("snippets") and r["inherit"] is True
    mine = [i for i in r["items"] if i["name"] == "日付（年月日・曜日）"][0]
    assert api.get_snippet(mine["id"], doc)["text"] == "独自の日付: {{日付}}"
    assert [i["name"] for i in r["items"]][:2] == ["新規", "日付（年月日・曜日）"]          # 文書フォルダーのものが、先頭


def test_inherit_false_hides_builtin_and_user_snippets(api, tmp_path):
    os.makedirs(api.snippet_folder())
    open(os.path.join(api.snippet_folder(), "自分用.md"), "w", encoding="utf-8").write("U")
    root, doc = project(tmp_path, {"だけ": "ONLY"}, cfg={"snippets": {"inherit": False}})
    assert names(api.list_snippets(doc)) == [("だけ", "project")]                         # そのフォルダーのファイルだけ
    other = tmp_path / "other"
    other.mkdir()
    assert "自分用" in [n for n, k in names(api.list_snippets(str(other)))]                # 設定の無い場所では、自分用＋組み込み


def test_snippets_and_templates_have_separate_inherit(api, tmp_path):
    root, doc = project(tmp_path, {"S1": "x"}, {"T1": "# {{題名}}"}, cfg={"snippets": {"inherit": False}})
    assert names(api.list_snippets(doc)) == [("S1", "project")]
    t = names(api.list_templates(doc))
    assert ("T1", "project") in t and ("議事録", "builtin") in t                         # templates は、inherit 指定なし = 追加
    assert api.get_template([i["id"] for i in api.list_templates(doc)["items"] if i["name"] == "T1"][0], doc)["fields"] == [{"name": "題名", "default": ""}]


def test_settings_dir_only_for_a_kind_that_exists(api, tmp_path):
    root, doc = project(tmp_path, templates_files={"T": "t"}, cfg={"snippets": {"inherit": False}})
    assert [n for n, k in names(api.list_snippets(doc))] == list(snippets.BUILTIN)       # snippets\ が無ければ、inherit false でも、既定値のまま


def test_get_refuses_files_outside_allowed_dirs(api, tmp_path):
    root, doc = project(tmp_path, {"ok": "OK"})
    secret = tmp_path / "secret.md"
    secret.write_text("秘密", encoding="utf-8")
    assert "使えません" in api.get_snippet("file:" + str(secret), doc)["error"]
    assert "使えません" in api.get_snippet("file:" + str(root / S.SETTINGS_DIR / "settings.json"), doc)["error"]
    assert "使えません" in api.get_snippet("file:" + str(root / S.SETTINGS_DIR / "snippets" / ".." / ".." / ".." / "secret.md"), doc)["error"]
    ok = str(root / S.SETTINGS_DIR / "snippets" / "ok.md")
    assert api.get_snippet("file:" + ok, doc)["text"] == "OK"
    assert "使えません" in api.get_snippet("file:" + ok, None)["error"]                    # 文脈が無ければ、文書フォルダーの設定は、読ませない


def test_export_writes_effective_set_and_does_not_overwrite(api, tmp_path):
    os.makedirs(api.snippet_folder())
    open(os.path.join(api.snippet_folder(), "自分用.md"), "w", encoding="utf-8").write("U{{x}}")
    root = tmp_path / "work"
    (root / "d").mkdir(parents=True)
    doc = str(root / "d" / "a.md")
    open(doc, "w", encoding="utf-8").write("x")
    r = api.export_settings(doc)
    assert r["error"] is None and r["dir"] == str(root / "d" / S.SETTINGS_DIR)
    sdir = root / "d" / S.SETTINGS_DIR / "snippets"
    files = sorted(os.listdir(sdir))
    assert len(files) == len(snippets.BUILTIN) + 1 and "自分用.md" in files            # 組み込みと、自分用が、ファイルになる
    assert r["snippets"]["written"] == len(files) and r["templates"]["written"] == len(templating.BUILTIN)
    cfg = json.load(open(root / "d" / S.SETTINGS_DIR / "settings.json", encoding="utf-8"))
    assert cfg == {"snippets": {"inherit": False}, "templates": {"inherit": False}}
    (sdir / "日時.md").write_text("書き換えた", encoding="utf-8")
    r2 = api.export_settings(doc)
    assert r2["snippets"]["written"] == 0 and (sdir / "日時.md").read_text(encoding="utf-8") == "書き換えた"
    listed = api.list_snippets(doc)                                                      # 書き出したあとは、そのフォルダーだけ
    assert all(i["kind"] == "project" for i in listed["items"]) and len(listed["items"]) == len(files)
    os.remove(sdir / "日時.md")
    assert "日時" not in [i["name"] for i in api.list_snippets(doc)["items"]]            # ファイルを消すと、その項目が消える（組み込みは戻らない）


def test_export_needs_a_context_and_reuses_the_nearest_settings_dir(api, tmp_path):
    assert api.export_settings(None)["error"] and api.export_settings("C:/no/such/place")["error"]
    root, doc = project(tmp_path, {"x": "1"})
    r = api.export_settings(doc)                                                         # 親に設定があれば、そこへ書く（入れ子にしない）
    assert r["dir"] == str(root / S.SETTINGS_DIR) and not (root / "docs" / S.SETTINGS_DIR).exists()


def test_trash_only_inside_settings_dirs(api, tmp_path, monkeypatch):
    moved = []
    monkeypatch.setattr(recycle, "move_to_trash", lambda p: moved.append(p) or True)
    root, doc = project(tmp_path, {"消す": "x"})
    target = str(root / S.SETTINGS_DIR / "snippets" / "消す.md")
    assert api.trash_setting_file(target, doc) == {"error": None} and moved == [target]
    other = tmp_path / "other.md"
    other.write_text("x", encoding="utf-8")
    for bad in (str(other), str(root / S.SETTINGS_DIR / "settings.json"), None, 5, target.replace("消す.md", "消す.txt")):
        assert api.trash_setting_file(bad, doc)["error"]
    assert moved == [target]                                                             # 外のファイルは、触らない
    assert api.trash_setting_file(target, None)["error"]                                 # 文脈が無ければ、文書フォルダーの設定は、消せない
    monkeypatch.setattr(recycle, "move_to_trash", lambda p: False)
    assert "ごみ箱" in api.trash_setting_file(target, doc)["error"]


def test_settings_folder_is_listed_so_it_can_be_edited(api, tmp_path):
    root, doc = project(tmp_path, {"a": "A"}, {"t": "T"})
    (root / ".hidden-other").mkdir()
    (root / ".hidden-other" / "x.md").write_text("x", encoding="utf-8")
    files, _ = mdeditor.scan_markdown(str(root))
    assert ".markdown-editor/snippets/a.md" in files and ".markdown-editor/templates/t.md" in files    # 設定のファイルを、一覧から開ける
    assert not [f for f in files if f.startswith(".hidden-other")]                                    # ほかの . のフォルダーは、今までどおり除く
