import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import foldersearch as F


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.md").write_text("# 議事録\n漏水の件。\nほかの話\n漏水が再発した。漏水調査。\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("何もなし\n", encoding="utf-8")
    (tmp_path / "sub" / "c.md").write_text("LEAK と leak と Leak\n行末が CRLF\r\nleak!\r\n", encoding="utf-8")
    return tmp_path, ["a.md", "b.md", "sub/c.md"]


def run(tree, query, **kw):
    folder, files = tree
    return F.search(str(folder), files, query, read=read, **kw)


def test_plain_search_returns_lines_columns_and_counts(tree):
    r = run(tree, "漏水")
    assert r["error"] is None and r["files"] == 1 and r["total"] == 2 and r["scanned"] == 3
    a = r["results"][0]
    assert a["rel"] == "a.md" and a["count"] == 2
    assert [(h["line"], h["col"], h["len"]) for h in a["hits"]] == [(1, 0, 2), (3, 0, 2)]      # 1行に2つあっても、1件
    h = a["hits"][0]
    assert h["text"][h["s"]:h["e"]] == "漏水"                                                     # 切り出しの中の位置


def test_case_option_and_crlf(tree):
    assert run(tree, "leak")["total"] == 2                       # 区別しない: 0 行目と 2 行目（CRLF の行も探せる）
    assert run(tree, "LEAK")["total"] == 2
    assert run(tree, "LEAK", case=True)["total"] == 1            # 区別する: 大文字の LEAK がある 0 行目だけ
    assert run(tree, "Leak", case=True)["total"] == 1
    r = run(tree, "leak!")
    assert r["results"][0]["hits"][0]["text"].endswith("leak!")  # 行末の CR は含めない


def test_regex_and_invalid_regex_and_empty_match(tree):
    r = run(tree, r"漏水(が|調査)", regex=True)
    assert r["total"] == 1 and r["results"][0]["hits"][0]["line"] == 3
    bad = run(tree, "(", regex=True)
    assert bad["error"].startswith("正規表現が正しくありません") and bad["results"] == []
    assert run(tree, "x*", regex=True)["total"] == 0              # 空の一致は、数えない
    assert run(tree, "")["results"] == [] and run(tree, "(")["error"] is None   # 文字列なら、括弧もそのまま探せる


def test_plain_query_is_escaped(tree):
    (tree[0] / "d.md").write_text("a.b と a+b と (x)\n", encoding="utf-8")
    r = F.search(str(tree[0]), ["d.md"], "a.b", read=read)
    assert r["total"] == 1 and r["results"][0]["hits"][0]["col"] == 0      # . は、任意の文字ではなく、点
    assert F.search(str(tree[0]), ["d.md"], "(x)", read=read)["total"] == 1


def test_snippet_is_trimmed_with_ellipsis():
    line = "あ" * 100 + "ここ" + "い" * 100
    text, s, e = F._snippet(line, 100, 102)
    assert text.startswith("…") and text.endswith("…") and text[s:e] == "ここ"
    assert len(text) == 1 + 40 + 2 + 40 + 1
    assert F._snippet("短い行", 0, 1)[0] == "短い行"


def test_overrides_replace_disk_content(tree):
    folder, files = tree
    key = os.path.normcase(os.path.abspath(str(folder / "b.md")))
    r = F.search(str(folder), files, "編集中", read=read, overrides={key: "編集中の内容\n"})
    assert r["total"] == 1 and r["results"][0]["rel"] == "b.md"                 # 保存していない内容を探す


def test_limits_and_truncation(tmp_path):
    (tmp_path / "many.md").write_text("\n".join("hit %d" % i for i in range(300)), encoding="utf-8")
    r = F.search(str(tmp_path), ["many.md"], "hit", read=read, per_file=10)
    assert r["results"][0]["count"] == 300 and len(r["results"][0]["hits"]) == 10  # 件数は全部、返す一致は上限まで
    r = F.search(str(tmp_path), ["many.md"], "hit", read=read, max_hits=50)
    assert r["truncated"] and "50 件" in r["reason"]
    (tmp_path / "big.md").write_text("hit" * 10, encoding="utf-8")
    r = F.search(str(tmp_path), ["big.md"], "hit", read=read, max_bytes=5)
    assert r["skipped"] == 1 and r["total"] == 0                                  # 大きなファイルは、探さない


def test_unreadable_and_missing_files_are_skipped(tmp_path):
    (tmp_path / "ok.md").write_text("hit\n", encoding="utf-8")
    r = F.search(str(tmp_path), ["gone.md", "ok.md"], "hit", read=read)
    assert r["total"] == 1 and r["skipped"] == 1
    r = F.search(str(tmp_path), ["ok.md"], "hit", read=lambda p: None)            # 読めなかった（文字コード不明など）
    assert r["skipped"] == 1 and r["scanned"] == 0


def test_cancel_and_time_limit(tree):
    folder, files = tree
    r = F.search(str(folder), files, "漏水", read=read, cancelled=lambda: True)
    assert r["truncated"] and "取りやめ" in r["reason"] and r["results"] == []
    r = F.search(str(folder), files, "漏水", read=read, seconds=-1)
    assert r["truncated"] and "時間の上限" in r["reason"]


def test_long_line_is_capped_for_matching(tmp_path):
    (tmp_path / "long.md").write_text("a" * 5000 + "TARGET\n", encoding="utf-8")
    assert F.search(str(tmp_path), ["long.md"], "TARGET", read=read)["total"] == 0   # 長すぎる行の後ろは、探さない
    (tmp_path / "ok.md").write_text("TARGET " + "a" * 5000 + "\n", encoding="utf-8")
    r = F.search(str(tmp_path), ["ok.md"], "TARGET", read=read)
    assert r["total"] == 1 and len(r["results"][0]["hits"][0]["text"]) < 100
