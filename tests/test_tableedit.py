import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tableedit as T

TABLE = "| 名前 | 数 |\n|---|--:|\n| りんご | 3 |\n| みかん | 12 |\n"


def apply(text, res):
    """edit / tab の結果を、文書に当てる（画面と同じ: start〜end の行を置き換える）。"""
    lines = text.split("\n")
    lines[res["start"]:res["end"]] = res["lines"]
    return "\n".join(lines)


def do(text, line, ch, op):
    res = T.edit(text, line, ch, op)
    assert res["ok"], res
    return apply(text, res), res


def test_display_width():
    assert T.display_width("abc") == 3 and T.display_width("りんご") == 6 and T.display_width("Ａ") == 2
    assert T.display_width("é") == 1 and T.display_width("é") == 1                  # 結合文字は 0
    assert T.display_width("😀") == 2 and T.display_width("") == 0


def test_split_row_variants():
    assert T._cells("| a | b |") == ["a", "b"]
    assert T._cells("a | b") == ["a", "b"]                                  # 先頭・末尾の | は、なくてもよい
    assert T._cells("|a|b") == ["a", "b"] and T._cells("| a | |") == ["a", ""]
    assert T._cells(r"| a \| b | c |") == [r"a \| b", "c"]                   # エスケープした | は、区切りにしない
    assert T._cells("文章") is None


def test_find_block_and_exclusions():
    lines = ["前の文 | パイプ入り", "", "| a | b |", "|---|---|", "| 1 | 2 |", "", "後"]
    assert T.find_block(lines, 2) == (2, 5) and T.find_block(lines, 4) == (2, 5)
    assert T.find_block(lines, 0) is None and T.find_block(lines, 5) is None
    assert T.find_block(["```", "| a | b |", "|---|---|", "```"], 1) is None             # コードブロックの中
    assert T.find_block(["> | a | b |", "> |---|---|"], 0) is None                         # 引用の中
    assert T.find_block(["    | a | b |", "    |---|---|"], 0) is None                    # 字下げ4文字以上（コード）
    assert T.find_block(["| a | b |", "|---|---|---|"], 0) is None                         # 列数が合わない（表にならない）
    assert T.find_block(["| a | b |", "| 1 | 2 |"], 0) is None                              # 区切り行が無い
    assert T.find_block(["段落 | パイプ", "| a | b |", "|---|---|"], 0) is None            # 表の上の文章の行
    assert T.find_block(["段落 | パイプ", "| a | b |", "|---|---|"], 1) == (1, 3)


def test_format_aligns_with_full_width_and_alignment():
    new, res = do("|名前|数|\n|-|-:|\n|りんご|3|\n|みかん|12|\n", 0, 2, "format")
    assert new == "| 名前   |  数 |\n| ------ | --: |\n| りんご |   3 |\n| みかん |  12 |\n"
    widths = {T.display_width(ln) for ln in new.strip().split("\n")}
    assert len(widths) == 1                                              # 全角を 2 と数えるので、見た目の幅がそろう


def test_format_center_and_left_and_idempotent():
    src = "| a | b | c |\n|:--|:-:|---|\n| あ | い | う |\n"
    new, _ = do(src, 0, 0, "format")
    assert new.split("\n")[1] == "| :-- | :-: | --- |"
    again, _ = do(new, 2, 0, "format")
    assert again == new                                                    # 何度整形しても同じ


def test_center_alignment_content():
    new, _ = do("| 見出し | x |\n|:-:|---|\n| a | b |\n", 0, 0, "format")
    assert new.split("\n")[1] == "| :----: | --- |"
    assert new.split("\n")[2] == "|   a    | b   |"                      # 幅 6 の中央（左 2・右 3）


def test_format_keeps_escaped_pipes_and_pads_missing_cells():
    new, _ = do("| a | b |\n|---|---|\n| 1 \\| 2 |\n", 0, 0, "format")
    row = new.split("\n")[2]
    assert "1 \\| 2" in row                                                # エスケープした | は、そのまま
    assert row.rstrip().endswith("|") and row.count(" | ") == 1             # 足りないセルは、空で補う（列数は、見出しにそろう）


def test_refuses_when_a_row_has_too_many_cells():
    res = T.edit("| a | b |\n|---|---|\n| 1 | 2 | 3 |\n", 0, 0, "format")
    assert res["ok"] is False and "3 行目" in res["message"]                    # 文字を捨てない


def test_add_columns_and_cursor():
    new, res = do(TABLE, 2, 3, "add_col_right")                               # りんご の列の右へ
    assert new.split("\n")[0].count("|") == 4 and res["cursor"][0] == 2
    assert res["cursor"][1] == T._cell_cursor(new.split("\n")[2], 1)           # 新しい列の、同じ行
    new2, res2 = do(TABLE, 0, 2, "add_col_left")
    assert new2.split("\n")[0] == "|     | 名前   |  数 |"
    assert res2["cursor"] == [0, 2]                                           # 新しい（空の）列の先頭


def test_delete_column_and_last_column_refused():
    new, _ = do(TABLE, 2, 3, "del_col")
    assert [ln.split("|")[1].strip() for ln in new.strip().split("\n")] == ["数", "--:", "3", "12"]
    one = "| a |\n|---|\n| 1 |\n"
    assert T.edit(one, 0, 2, "del_col")["ok"] is False


def test_move_column_swaps_alignment_too():
    new, res = do(TABLE, 0, 3, "move_col_right")
    head, delim = new.split("\n")[:2]
    assert head.index("数") < head.index("名前") and delim == "| --: | ------ |"      # 配置も、一緒に動く
    assert res["cursor"][0] == 0 and res["cursor"][1] == T._cell_cursor(head, 1)
    assert T.edit(TABLE, 0, 3, "move_col_left")["ok"] is False                      # 左端は、これ以上動かせない
    assert T.edit(new, 0, len(head) - 2, "move_col_right")["ok"] is False           # 右端も


def test_add_and_delete_rows():
    new, res = do(TABLE, 2, 3, "add_row_below")
    lines = new.strip().split("\n")
    assert len(lines) == 5 and lines[3].replace("|", "").strip() == "" and res["cursor"][0] == 3
    new2, res2 = do(TABLE, 3, 3, "add_row_above")
    assert new2.split("\n")[3].replace("|", "").strip() == "" and "みかん" in new2.split("\n")[4] and res2["cursor"][0] == 3
    assert T.edit(TABLE, 0, 3, "add_row_above")["ok"] is False                  # 見出しの上には足せない
    new3, _ = do(TABLE, 0, 3, "add_row_below")                                   # 見出し行で「下に足す」と、本文の先頭
    assert new3.split("\n")[2].replace("|", "").strip() == ""
    gone, res3 = do(TABLE, 2, 3, "del_row")
    assert "りんご" not in gone and "みかん" in gone
    assert T.edit(TABLE, 0, 3, "del_row")["ok"] is False and T.edit(TABLE, 1, 3, "del_row")["ok"] is False
    only, res4 = do("| a |\n|---|\n| 1 |\n", 2, 2, "del_row")
    assert only.strip().split("\n")[-1].startswith("| ---") and res4["cursor"][0] == 0   # 最後の本文行を消すと、見出し行へ


def test_alignment_ops():
    new, _ = do(TABLE, 2, 3, "align_center")
    assert new.split("\n")[1].split("|")[1].strip().startswith(":") and new.split("\n")[1].split("|")[1].strip().endswith(":")
    new, _ = do(new, 2, 3, "align_none")
    assert set(new.split("\n")[1].split("|")[1].strip()) == {"-"}
    new, _ = do(new, 2, 3, "align_right")
    assert new.split("\n")[1].split("|")[1].strip().endswith(":")
    new, _ = do(new, 2, 3, "align_left")
    assert new.split("\n")[1].split("|")[1].strip().startswith(":") and not new.split("\n")[1].split("|")[1].strip().endswith(":")


def test_prefix_indent_is_kept():
    new, _ = do("  |a|b|\n  |-|-|\n  |1|2|\n", 0, 3, "format")
    assert all(ln.startswith("  | ") for ln in new.rstrip("\n").split("\n"))


def test_not_in_table_and_bad_op():
    assert T.edit("ただの文章", 0, 0, "format") == {"ok": False, "message": "カーソルが、表の中にありません"}
    assert T.edit(TABLE, 0, 0, "ない操作")["ok"] is False
    assert T.info("ただの文章", 0, 0) == {"in_table": False}


def test_info():
    i = T.info(TABLE, 2, 3)
    assert i["in_table"] and i["kind"] == "body" and i["ncols"] == 2 and i["rows"] == 2 and i["col"] == 0
    assert T.info(TABLE, 0, 8)["col"] == 1 and T.info(TABLE, 1, 0)["kind"] == "delim"


def test_tab_moves_through_cells_skips_delimiter_and_adds_row():
    t = "| a | b |\n|---|---|\n| 1 | 2 |\n"
    r = T.tab(t, 0, 2, True)                                  # a → b
    assert r["lines"] is None and r["cursor"] == [0, T._cell_cursor("| a | b |", 1)]
    r = T.tab(t, 0, 6, True)                                  # b（見出し行の最後）→ 区切り行を飛ばして、本文の最初
    assert r["cursor"] == [2, T._cell_cursor("| 1 | 2 |", 0)]
    r = T.tab(t, 2, 6, False)                                 # 本文の 2 → 戻る（本文の 1）
    assert r["cursor"][0] == 2 and r["cursor"][1] == T._cell_cursor("| 1 | 2 |", 0)
    r = T.tab(t, 2, 2, False)                                 # 本文の最初 → 区切り行を飛ばして、見出し行の最後
    assert r["cursor"] == [0, T._cell_cursor("| a | b |", 1)]
    assert T.tab(t, 0, 2, False)["cursor"] == [0, 2]          # 先頭のセルでの Shift+Tab: 動かない
    r = T.tab(t, 2, 6, True)                                  # 最後のセルでの Tab: 行を足す
    assert r["ok"] and r["lines"] is not None and len(r["lines"]) == 4
    assert r["cursor"][0] == 3 and r["cursor"][1] == T._cell_cursor(r["lines"][3], 0)
    assert T.tab("ただの文章", 0, 0) == {"ok": False, "not_table": True}


def test_tab_in_header_only_table_adds_first_body_row():
    t = "| a | b |\n|---|---|\n"
    r = T.tab(t, 1, 0, True)
    assert r["ok"]
    r = T.tab(t, 0, 6, True)                                  # 見出し行の最後 → 本文が無いので、行を足す
    assert r["ok"] and r["lines"] is not None and len(r["lines"]) == 3


def test_empty_cell_cursor_position():
    assert T._cell_cursor("|   |   |", 0) == 2                  # 空のセルは、| と空白の次
    assert T._cell_cursor("| a | b |", 1) == 6


def test_unicode_table_roundtrip_stays_stable():
    src = "| 項目 | 説明 |\n|---|---|\n| 日本語 | テスト👍 |\n| abc | ｱｲｳ |\n"
    new, _ = do(src, 0, 0, "format")
    assert {T.display_width(ln) for ln in new.strip().split("\n")} == {T.display_width(new.split("\n")[0])}
    assert do(new, 0, 0, "format")[0] == new
