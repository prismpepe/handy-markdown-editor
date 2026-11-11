"""脚注・Qiita の注釈ブロック・GitHub のアラートの書き間違いの検査（X011〜X013）。"""
import lint
import mdeditor


def run(text, disabled=()):
    return lint.lint(text, mdeditor.make_renderer(), None, disabled)


def rules(text):
    return [(i["line"], i["rule"]) for i in run(text) if i["rule"] in ("X011", "X012", "X013")]


def test_正しい脚注は指摘されない():
    assert rules("本文[^1]です。\n\n[^1]: 脚注\n") == []


def test_定義のない脚注を指摘する():
    got = run("本文[^a]と[^b]\n\n[^a]: A\n")
    assert [(i["line"], i["rule"]) for i in got if i["rule"] == "X011"] == [(0, "X011")]
    assert "[^b]" in [i["message"] for i in got if i["rule"] == "X011"][0]


def test_使われない定義を指摘する_変換器は黙って捨てるため():
    got = [i for i in run("本文[^a]\n\n[^a]: A\n[^z]: 使われない\n") if i["rule"] == "X011"]
    assert len(got) == 1 and got[0]["line"] == 3 and "[^z]" in got[0]["message"] and got[0]["severity"] == "info"


def test_コードの中の脚注の書き方は指摘しない():
    assert rules("```\n[^x]\n```\n\n`[^y]` です\n") == []


def test_定義の行の先頭は参照として数えない():
    assert rules("[^1]: だけある\n") == [(0, "X011")]                 # 使われない定義だけ


def test_注釈ブロックの種類の誤りを指摘する():
    assert rules(":::note foo\n中身\n:::\n") == [(0, "X012")]
    assert rules(":::note info extra\n中身\n:::\n") == [(0, "X012")]


def test_正しい注釈ブロックは指摘されない():
    for kind in ("", " info", " warn", " alert"):
        assert rules(f":::note{kind}\n中身\n:::\n") == []


def test_閉じ忘れた注釈ブロックを指摘する():
    assert rules(":::note info\n中身\n") == [(0, "X012")]


def test_入れ子や他の記法のブロックの閉じに惑わされない():
    assert rules(":::details 題\n:::note info\n中\n:::\n:::\n") == []
    assert rules(":::message\n中\n:::\n") == []


def test_アラートの種類の誤りを指摘する():
    assert rules("> [!INFO]\n> 本文\n") == [(0, "X013")]
    for mark in ("NOTE", "TIP", "IMPORTANT", "WARNING", "CAUTION", "note"):
        assert rules(f"> [!{mark}]\n> 本文\n") == []


def test_規則は無効にできる():
    assert [i for i in run(":::note foo\n中\n:::\n", disabled=("X012",)) if i["rule"] == "X012"] == []


def test_規則の一覧に載っている():
    ids = [r[0] for r in lint.RULES]
    assert {"X011", "X012", "X013"} <= set(ids)
    assert all(r[2] for r in lint.RULES if r[0] in ("X011", "X012", "X013"))      # 既定で検査する


def test_拡張の書き方をでたらめに組み合わせても_検査が例外にならない():
    import random
    parts = ["本文[^1]", "[^1]: 定義", "[^x]", "文中^[注]", "$x^2$", "$$\na\n$$", ":::note info\n中\n:::", ":::note", ":::", ":::details 題",
             "> [!NOTE]\n> a", "> [!TIP]", "> [!INFO]", "> 引用", "```ruby:a.rb\nputs 1\n```", "```diff_js\n- a\n+ b\n```", "```",
             "- 項目\n  > [!NOTE]\n  > 中", "| a | b |\n|---|---|\n| 1[^1] | 2 |", "# 見出し[^1]", "[^1]: 二つ目の定義",
             "**強調[^1]**", "[リンク][^1]", "1. 番号\n   [^2]: 入れ子の定義", "[^1][^1][^1]", "^[a^[b]]", "`[^c]`"]
    rnd = random.Random(20261112)
    for _ in range(300):
        text = "\n\n".join(rnd.choice(parts) for _ in range(rnd.randint(1, 8)))
        run(text)
