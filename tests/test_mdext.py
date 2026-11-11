"""脚注・Qiita の注釈ブロック（:::note）・GitHub のアラート（[!NOTE]）・コードブロックのファイル名（mdext.py）。"""
import highlight
import mdeditor as app
import mdext
from sanitize import sanitize


def render(text):
    return sanitize(app.make_renderer().render(text, {"base": ""}))


# ---------------------------------------------------------------- 脚注
def test_脚注は本文に上付きの番号が付きと文末に一覧が出る():
    out = render("本文[^1]です。\n\n[^1]: 脚注です。\n")
    assert '<sup class="footnote-ref"><a href="#fn1" id="fnref1">1</a></sup>' in out
    assert '<li id="fn1" class="footnote-item">' in out and "脚注です。" in out
    assert 'href="#fnref1"' in out                     # 本文へ戻るリンク


def test_脚注の番号はと書いた順に振られる():
    out = render("あ[^b]い[^a]\n\n[^a]: A\n[^b]: B\n")
    assert out.index('id="fnref1"') < out.index('id="fnref2"')
    assert out.index("B") < out.index("A", out.index("footnotes"))      # 一覧も、本文に出た順


def test_定義のない脚注はとそのまま文字で出る():
    out = render("本文[^x]です。")
    assert "[^x]" in out and "footnote-ref" not in out


def test_脚注の中身のHTMLは無害化される():
    out = render("あ[^1]\n\n[^1]: <script>alert(1)</script>危険\n")
    assert "<script" not in out and "危険" in out


def test_脚注のないふつうの文書は変わらない():
    assert "footnotes" not in render("# 見出し\n\n本文\n")


# ---------------------------------------------------------------- Qiita の注釈ブロック
def test_note_は種類ごとのクラスが付く():
    for kind in ("info", "warn", "alert"):
        out = render(f":::note {kind}\n中身です\n:::\n")
        assert f'<div class="md-note md-note-{kind}">' in out and "中身です" in out


def test_種類を書かないnoteは_info():
    assert 'class="md-note md-note-info"' in render(":::note\n中身\n:::\n")


def test_注釈ブロックの中もとMarkdownとして変換される():
    out = render(":::note warn\n**強調** と `code`\n\n- 項目\n:::\n")
    assert "<strong>強調</strong>" in out and "<code>code</code>" in out and ">項目</li>" in out


def test_知らない種類や余計な語のnoteはと注釈にならない():
    for src in (":::note foo\n中身\n:::\n", ":::note info extra\n中身\n:::\n", ":::message\n中身\n:::\n"):
        assert "md-note" not in render(src)
    assert "中身" in render(":::note foo\n中身\n:::\n")           # 文字は消えない


def test_閉じ忘れた注釈ブロックはと文書の終わりで閉じる():
    out = render(":::note info\n中身です\n")
    assert 'class="md-note md-note-info"' in out and "中身です" in out


def test_note_の種類を使ったクラスの注入はできない():
    out = render(':::note info"onclick="x\n中身\n:::\n')
    assert "onclick" not in out or "md-note" not in out


def test_note_の判定():
    assert mdext.note_kind("note info") == "info" and mdext.note_kind("note warn") == "warn"
    assert mdext.note_kind("note") == "info" and mdext.note_kind("note INFO") == "info"
    assert mdext.note_kind("note foo") is None and mdext.note_kind("tip") is None and mdext.note_kind("") is None


# ---------------------------------------------------------------- GitHub のアラート
def test_アラートは5種類ともと見出しとクラスが付く():
    for mark, kind, title in (("NOTE", "note", "Note"), ("TIP", "tip", "Tip"), ("IMPORTANT", "important", "Important"),
                              ("WARNING", "warning", "Warning"), ("CAUTION", "caution", "Caution")):
        out = render(f"> [!{mark}]\n> 本文です\n")
        assert f'<blockquote class="md-alert md-alert-{kind}"' in out
        assert f'<p class="md-alert-title">{title}</p>' in out and "本文です" in out
        assert "[!" not in out                         # 印は取り除かれる


def test_アラートの印はと小文字でも通る():
    assert "md-alert-tip" in render("> [!tip]\n> 本文\n")


def test_印だけのアラートはと見出しだけになる():
    out = render("> [!NOTE]\n")
    assert "md-alert-note" in out and ">Note</p>" in out


def test_アラートの本文はと複数行と段落でも欠けない():
    out = render("> [!WARNING]\n> 一行目\n> 二行目\n>\n> 次の段落\n")
    assert "一行目" in out and "二行目" in out and "次の段落" in out


def test_ふつうの引用やと印が先頭にない引用はとアラートにならない():
    assert "md-alert" not in render("> 普通の引用\n")
    assert "md-alert" not in render("> 前置き\n> [!NOTE]\n")
    assert "[!NOTE]" in render("> 前置き\n> [!NOTE]\n")
    assert "md-alert" not in render("> [!INFO]\n> 知らない種類\n")


def test_アラートは箇条書きの中やと入れ子の引用の中でも使える():
    assert "md-alert-note" in render("- 項目\n\n  > [!NOTE]\n  > 中\n")
    assert "md-alert-tip" in render("> 外\n>\n> > [!TIP]\n> > 内\n")


# ---------------------------------------------------------------- コードブロックの情報行
def test_情報行の分解():
    assert mdext.split_info("ruby:app.rb") == ("ruby", "app.rb", False)
    assert mdext.split_info("diff_ruby") == ("diff", "", True)
    assert mdext.split_info("bat:C:\\x\\a.bat") == ("bat", "C:\\x\\a.bat", False)
    assert mdext.split_info("python") == ("python", "", False)
    assert mdext.split_info("{.python}") == ("python", "", False)
    assert mdext.split_info('python title="a.py"') == ("python", "", False)
    assert mdext.split_info("") == ("", "", False)
    assert mdext.split_info(":x") == (":x", "", False)             # 言語が空の書き方は、ファイル名にしない
    assert mdext.split_info("ruby:") == ("ruby:", "", False)


def test_言語名は_highlight_からも同じに読める():
    assert highlight.language_of("ruby:app.rb") == "ruby"
    assert highlight.language_of("diff_js") == "diff"
    assert highlight.language_of("language-python") == "python"


def test_ファイル名つきのコードはと見出しが出てと色分けも効く():
    out = render("```ruby:app.rb\nputs 1\n```\n")
    assert '<div class="code-filename">app.rb</div>' in out
    assert 'class="language-ruby highlighted"' in out and "puts" in out


def test_ファイル名の特殊文字はと無害化される():
    out = render("```ruby:<b>x.rb\nputs 1\n```\n")
    assert "<b>x.rb" not in out and "&lt;b&gt;x.rb" in out


def test_差分はと追加と削除に色が付く():
    out = render("```diff_ruby\n- a\n+ b\n```\n")
    assert 'class="language-diff highlighted"' in out and "tok-gd" in out and "tok-gi" in out
    assert "- a" in out and "+ b" in out                  # 文字は変わらない


def test_ファイル名つきでもとコードの中身は変わらない():
    code = "a < b && c > d\n  indent\n"
    out = render(f"```text:note.txt\n{code}```\n")
    assert "a &lt; b &amp;&amp; c &gt; d" in out and "  indent" in out


def test_図と数式の書き方はと影響を受けない():
    assert "mermaid-src" in render("```mermaid\ngraph TD; A-->B\n```\n")
    assert "math" in render("```math\nx^2\n```\n")


# ---------------------------------------------------------------- 文中の脚注・数式との組み合わせ（利用者の報告: 変換が例外になり、画面が更新されなくなった）
def test_文中の脚注_は枝番がなくても描ける():
    out = render("文中の脚注です^[インラインの脚注です]。\n")
    assert 'id="fnref1"' in out and "インラインの脚注です" in out and "[1:" not in out


def test_同じ脚注を2回使うと枝番が付く():
    out = render("あ[^1]い[^1]\n\n[^1]: 説明\n")
    assert 'id="fnref1"' in out and 'id="fnref1:1"' in out and ">1:1<" in out


def test_数式と脚注と文中の脚注が混ざった文書():
    src = ("インライン数式は $x^2$ のように書きます。\n\n$$\nx^2 + y^2 = 1\n$$\n\n"
           "本文に脚注を付けます[^1]。インラインでも書けます^[インラインの脚注です]。\n\n[^1]: 脚注の内容です。\n")
    out = render(src)
    assert 'class="math inline"' in out and 'class="math block"' in out
    assert "脚注の内容です" in out and "インラインの脚注です" in out


def test_拡張の書き方をでたらめに組み合わせても_変換が例外にならない():
    import random
    parts = ["本文[^1]", "[^1]: 定義", "[^x]", "文中^[注]", "$x^2$", "$$\na\n$$", ":::note info\n中\n:::", ":::note",
             ":::", "> [!NOTE]\n> a", "> [!TIP]", "> 引用", "```ruby:a.rb\nputs 1\n```", "```diff_js\n- a\n+ b\n```", "```",
             "- 項目\n  > [!NOTE]\n  > 中", "| a | b |\n|---|---|\n| 1[^1] | 2 |", "# 見出し[^1]", "[^1]: 二つ目の定義", "<details>\n[^1]\n</details>",
             "**強調[^1]**", "[リンク][^1]", "![画像](a.png)[^1]", "1. 番号\n   [^2]: 入れ子の定義", "[^1][^1][^1]", "^[a^[b]]"]
    rnd = random.Random(20261112)
    for _ in range(400):
        text = "\n\n".join(rnd.choice(parts) for _ in range(rnd.randint(1, 8)))
        render(text)                                            # 例外にならないこと


def test_変換が例外になっても_画面に出す文を返し_例外を投げない():
    api = app.Api(None)

    def boom(text, env):
        raise RuntimeError("壊れた <b>入力</b>")
    api._md.render = boom
    out = api.render("本文", None)
    assert "表示できませんでした" in out and "RuntimeError" in out
    assert "<b>入力</b>" not in out and "&lt;b&gt;入力&lt;/b&gt;" in out            # 例外の文は、無害化される
