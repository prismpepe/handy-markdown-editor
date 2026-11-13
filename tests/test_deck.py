"""発表（スライドショー）: テーマ・モニターの選び方・ウィンドウの受け渡し（deck.py）と、発表用の書き方（mdext.py）。"""
import json
import os

import deck
import mdeditor as app
import mdext
from sanitize import sanitize


def render(text):
    return sanitize(app.make_renderer().render(text, {"base": ""}))


# ---------------------------------------------------------------- 発表用の書き方
def test_発表者ノートは_aside_になり_HTMLは無害化される():
    out = render("本文\n\n<!-- note: ここは\n発表者ノート <b>x</b> -->\n")
    assert '<aside class="slide-note">ここは<br>' in out
    assert "&lt;b&gt;x&lt;/b&gt;" in out and "<b>x</b>" not in out


def test_ノートの書き出しは_日本語の語も使える():
    for word in ("note", "notes", "ノート", "メモ", "発表者ノート"):
        assert "slide-note" in render("<!-- %s: 中身 -->\n" % word)


def test_中身のないノートや_ふつうのコメントは_何も出さない():
    assert "slide-note" not in render("<!-- note: -->\n")
    assert "<aside" not in render("<!-- ふつうのコメント -->\n")


def test_スライドの種類の指定はクラスになる():
    out = render("<!-- _class: lead -->\n")
    assert 'class="slide-directive sd-lead"' in out
    assert 'sd-lead sd-center' in render("<!-- class: Lead  center -->\n")


def test_スライドの種類に変な文字は入れられない():
    out = render('<!-- _class: lead" onclick="x -->\n')
    assert "onclick=" not in out and out.count("=") <= 2          # data-line（あれば）と class だけ（属性は増えない）。引用符は、語から取り除かれる
    assert "sd-" not in render("<!-- _class: !!! -->\n")                    # 使える語が無ければ、何も出さない


def test_段組みの書き方():
    out = render("::::columns\n:::col\n左\n:::\n:::col\n右\n:::\n::::\n")
    assert '<div class="deck-columns">' in out and out.count('class="deck-col"') == 2


def test_水平線はそのまま水平線で出る():
    assert "<hr" in render("前\n\n---\n\n後\n")


# ---------------------------------------------------------------- テーマ
def make_theme(folder, name, css="/* x */"):
    d = os.path.join(folder, ".markdown-editor", "themes")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(css)
    return path


def test_組み込みテーマは4つ():
    assert [t["id"] for t in deck.list_themes()] == ["light", "dark", "mono", "blue"]


def test_文書フォルダーと上のフォルダーのテーマが一覧に出る(tmp_path):
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    make_theme(str(tmp_path), "上.css")
    make_theme(str(sub), "近い.css")
    doc = sub / "x.md"
    doc.write_text("# x", encoding="utf-8")
    names = [t["name"] for t in deck.list_themes(str(doc))]
    assert names[:4] == ["標準（明るい）", "ダーク", "白黒（印刷向き）", "ブルー（見出しの帯）"]
    assert "近い" in names and "上" in names and names.index("近い") < names.index("上")


def test_同じ名前は近いほうが勝つ(tmp_path):
    sub = tmp_path / "a"
    sub.mkdir()
    near = make_theme(str(sub), "同名.css", "/* 近い */")
    make_theme(str(tmp_path), "同名.css", "/* 遠い */")
    themes = [t for t in deck.list_themes(str(sub / "x.md")) if t["name"] == "同名"]
    assert len(themes) == 1 and themes[0]["id"] == "user:" + near


def test_css以外は一覧に出ない(tmp_path):
    make_theme(str(tmp_path), "メモ.txt")
    assert [t["name"] for t in deck.list_themes(str(tmp_path / "x.md")) if t["source"] != "組み込み"] == []


def test_アプリの設定フォルダーのテーマも出る(tmp_path):
    d = tmp_path / "appdata" / "themes"
    d.mkdir(parents=True)
    (d / "全体用.css").write_text("/* x */", encoding="utf-8")
    got = [t for t in deck.list_themes(None, str(tmp_path / "appdata")) if t["source"] == "ユーザー"]
    assert [t["name"] for t in got] == ["全体用"]


def test_テーマのcssを読む(tmp_path):
    path = make_theme(str(tmp_path), "自分.css", ".slide { --slide-bg: #123456; }")
    doc = str(tmp_path / "x.md")
    assert "#123456" in deck.theme_css("user:" + path, doc)
    assert "--slide-bg: #ffffff" in deck.theme_css("light")
    assert deck.theme_css("知らない") == deck.BUILTIN["light"][1]


def test_一覧にないファイルは読まない(tmp_path):
    secret = tmp_path / "秘密.css"
    secret.write_text(".slide { --slide-bg: #abcdef; }", encoding="utf-8")
    out = deck.theme_css("user:" + str(secret), str(tmp_path / "x.md"))
    assert "#abcdef" not in out and out == deck.BUILTIN["light"][1]


def test_大きすぎるcssは使わない(tmp_path):
    path = make_theme(str(tmp_path), "巨大.css", "/*" + "x" * (deck.MAX_CSS + 10) + "*/")
    assert deck.theme_css("user:" + path, str(tmp_path / "x.md")) == deck.BUILTIN["light"][1]


def test_cssの相対パスの画像は埋め込まれる(tmp_path):
    path = make_theme(str(tmp_path), "背景.css", '.slide { background-image: url("bg.png"); }')
    (tmp_path / ".markdown-editor" / "themes" / "bg.png").write_bytes(b"\x89PNG\r\n\x1a\nxx")
    out = deck.theme_css("user:" + path, str(tmp_path / "x.md"))
    assert "url(\"data:image/png;base64," in out and "bg.png" not in out


def test_cssの外部URLや無いファイルや大きいファイルは_そのまま():
    css = 'a { background: url(https://example.com/a.png); } b { background: url("無い.png"); } c { background: url(data:image/png;base64,AAAA); }'
    assert deck.inline_urls(css, os.getcwd()) == css


def test_大きい画像は埋め込まない(tmp_path):
    (tmp_path / "big.png").write_bytes(b"0" * (deck.MAX_ASSET + 1))
    css = '.slide { background: url(big.png); }'
    assert deck.inline_urls(css, str(tmp_path)) == css


def test_テーマの見本を作る(tmp_path):
    doc = tmp_path / "x.md"
    doc.write_text("# x", encoding="utf-8")
    a = deck.make_sample_theme(str(doc))
    assert a["error"] is None and a["path"].endswith("マイテーマ.css") and os.path.isfile(a["path"])
    b = deck.make_sample_theme(str(doc))
    assert b["path"] != a["path"] and os.path.isfile(b["path"])                      # 上書きしない
    assert any(t["name"] == "マイテーマ" for t in deck.list_themes(str(doc)))


def test_テーマの見本は_置き場所が決まらなければ_作らない():
    assert deck.make_sample_theme(None, None)["error"]


def test_テーマの見本は_フォルダーを渡しても作れる(tmp_path):
    a = deck.make_sample_theme(str(tmp_path))
    assert a["error"] is None and os.path.dirname(a["path"]).endswith(os.path.join(".markdown-editor", "themes"))


# ---------------------------------------------------------------- モニター
def S(i, x, y, primary=False):
    return {"index": i, "width": 1920, "height": 1080, "x": x, "y": y, "primary": primary}


def test_モニターが2枚なら_主以外に発表し_主に発表者ビュー():
    assert deck.default_screens([S(0, 0, 0, True), S(1, 1920, 0)]) == {"audience": 1, "presenter": 0}
    assert deck.default_screens([S(0, -1920, 0), S(1, 0, 0, True)]) == {"audience": 0, "presenter": 1}


def test_モニターが1枚なら_どちらもそれ():
    assert deck.default_screens([S(0, 0, 0, True)]) == {"audience": 0, "presenter": 0}


def test_モニターが分からなければ_どちらも_マイナス1():
    assert deck.default_screens([]) == {"audience": -1, "presenter": -1}


# ---------------------------------------------------------------- ウィンドウの受け渡し
class FakeWindow:
    def __init__(self):
        self.calls = []
        self.destroyed = False

    def evaluate_js(self, code):
        self.calls.append(code)

    def destroy(self):
        self.destroyed = True


def host_with(roles):
    h = deck.DeckHost(lambda n: n)
    h._windows = {r: FakeWindow() for r in roles}
    return h


def test_状態は_相手のウィンドウだけに渡る():
    h = host_with(["audience", "presenter"])
    h._relay("presenter", json.dumps({"i": 3, "black": "black", "t": 1700000000000}))
    assert h._windows["presenter"].calls == []
    (call,) = h._windows["audience"].calls
    assert call.startswith("window.Deck && window.Deck.apply(") and '"i": 3' in call and '"black": "black"' in call


def test_受け渡す内容は_決まった項目だけ():
    h = host_with(["audience", "presenter"])
    h._relay("audience", json.dumps({"i": 1, "evil": "alert(1)", "black": "<script>", "t": "x"}))
    (call,) = h._windows["presenter"].calls
    assert "evil" not in call and "script" not in call and '"i": 1' in call and '"black"' not in call and '"t"' not in call


def test_正しくない状態は_捨てる():
    h = host_with(["audience", "presenter"])
    for bad in ("{", "[]", "null", 5, None):
        h._relay("audience", bad)
    assert h._windows["presenter"].calls == []


def test_片方を閉じると_もう片方も閉じる():
    h = host_with(["audience", "presenter"])
    other = h._windows["presenter"]
    h._on_closed("audience")
    assert other.destroyed and h._windows == {}


def test_すべて閉じる():
    h = host_with(["audience", "presenter"])
    ws = list(h._windows.values())
    h.close()
    assert all(w.destroyed for w in ws) and h._windows == {}


def test_発表の内容が正しくなければ_開かない():
    h = deck.DeckHost(lambda n: n)
    assert h.open("<html></html>", {})["error"]                      # 役割の印が無い
    assert h.open(123, {})["error"]
    assert h.open('"__DECK_ROLE__"', "x")["error"]
    assert h._windows == {}


def test_PDFにする内容が正しくなければ_作らない(tmp_path):
    h = deck.DeckHost(lambda n: n)
    assert h.export_pdf("<html></html>", "slides", str(tmp_path / "a.pdf"))["error"]
    assert h.export_pdf('"__DECK_ROLE__"', "ぜんぶ", str(tmp_path / "a.pdf"))["error"]
    assert h.export_pdf('"__DECK_ROLE__"', "slides", "")["error"]


def test_橋渡しの属性は_JavaScriptに出ない():
    b = deck._Bridge(deck.DeckHost(lambda n: n), "audience")
    public = [n for n in dir(b) if not n.startswith("_")]
    assert sorted(public) == ["close_all", "open_presenter", "sync", "toggle_fullscreen"]


def test_部品の読み込み():
    root = os.path.dirname(os.path.abspath(deck.__file__))
    h = deck.DeckHost(lambda n: os.path.join(root, n))
    a = h.assets()
    assert "Deck" in a["js"] and "#scaler" in a["css"]


def test_部品をまとめて返す():
    root = os.path.dirname(os.path.abspath(deck.__file__))
    p = deck.DeckHost(lambda n: os.path.join(root, n)).prepare(None)
    assert set(p) == {"assets", "themes", "screens", "defaults", "error"} and p["error"] is None


def test_設定の検査():
    import uiprefs
    ok = uiprefs.clean_prefs({"deck": {"theme": "dark", "ratio": "4:3", "presenter": True, "screen": 1}})
    assert ok == {"deck": {"theme": "dark", "ratio": "4:3", "presenter": True, "screen": 1}}
    assert uiprefs.clean_prefs({"deck": {"ratio": "9:16", "presenter": "yes", "screen": 99, "theme": ""}}) == {}
    assert uiprefs.clean_prefs({"deck": {"screen": True}}) == {}
    assert uiprefs.clean_prefs({"deck": "x"}) == {}


def test_テーマの色の変数は_同じ規則の中で_互いを参照しない():
    """--slide-bg: var(--slide-accent) と書いて、同じ規則の中で --slide-accent も書き換えると、背景が意図しない色になる
    （見本のテーマの表紙が、白地に白い文字で空白に見えた不具合の再発防止）。"""
    import re
    sources = [css for _, css in deck.BUILTIN.values()] + [deck.SAMPLE_THEME]
    for css in sources:
        for body in re.findall(r"\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S)):
            decl = dict(re.findall(r"(--[a-z-]+)\s*:\s*([^;]+);?", body))
            for name, value in decl.items():
                for ref in re.findall(r"var\((--[a-z-]+)\)", value):
                    assert ref not in decl, (name, ref, body)


def test_見本のテーマの表紙は_背景と文字が同じ色にならない():
    import re
    m = re.search(r"\.slide\.sd-lead \{([^}]*)\}", deck.SAMPLE_THEME)
    decl = dict(re.findall(r"(--[a-z-]+)\s*:\s*([^;]+);", m.group(1)))
    assert decl["--slide-bg"].startswith("#") and decl["--slide-bg"].lower() != decl["--slide-fg"].lower()


def test_旧い見本のテーマで作られたファイルは_読み込むときに表紙の指定が直る(tmp_path):
    old = ".slide { --slide-accent: #b4541a; }\n.slide.sd-lead { --slide-bg: var(--slide-accent); --slide-fg: #fff; --slide-accent: #fff; }\n"
    path = make_theme(str(tmp_path), "旧.css", old)
    out = deck.theme_css("user:" + path, str(tmp_path / "x.md"))
    assert "--slide-bg: #b4541a" in out and "--slide-bg: var(--slide-accent)" not in out
    with open(path, encoding="utf-8") as f:
        assert f.read() == old                                                  # ファイルは、書き換えない


def test_画面の比率も受け渡す_決まった値だけ():
    h = host_with(["audience", "presenter"])
    h._relay("presenter", json.dumps({"i": 0, "ratio": "4:3"}))
    assert '"ratio": "4:3"' in h._windows["audience"].calls[0]
    h._windows["audience"].calls.clear()
    h._relay("presenter", json.dumps({"i": 0, "ratio": "99:1"}))
    assert "ratio" not in h._windows["audience"].calls[0]


def test_レーザーと拡大の状態を受け渡す_範囲を超える値は丸める_変な値は捨てる():
    h = host_with(["audience", "presenter"])
    h._relay("presenter", json.dumps({"laser": True, "zoom": True, "zk": 9, "u": 0.5, "v": 0.25}))
    call = h._windows["audience"].calls[0]
    assert '"laser": true' in call and '"zoom": true' in call and '"zk": 5.0' in call and '"u": 0.5' in call and '"v": 0.25' in call
    h._windows["audience"].calls.clear()
    h._relay("presenter", json.dumps({"u": None, "v": None}))
    assert '"u": null' in h._windows["audience"].calls[0] and '"v": null' in h._windows["audience"].calls[0]
    h._windows["audience"].calls.clear()
    h._relay("presenter", json.dumps({"laser": "yes", "zoom": 1, "zk": True, "u": 99, "v": "x"}))
    assert h._windows["audience"].calls[0] == "window.Deck && window.Deck.apply({})"


def test_レーザーの大きさの設定の検査():
    import uiprefs
    assert uiprefs.clean_prefs({"deck": {"laser": 48}}) == {"deck": {"laser": 48}}
    for bad in (5, 500, True, "30", 3.5):
        assert uiprefs.clean_prefs({"deck": {"laser": bad}}) == {}


def test_レーザーの大きさは_受け渡し_範囲に丸め_設定に覚える():
    saved = []
    h = deck.DeckHost(lambda n: n, None, saved.append)
    h._windows = {"audience": FakeWindow(), "presenter": FakeWindow()}
    h._relay("presenter", json.dumps({"lz": 48}))
    assert '"lz": 48.0' in h._windows["audience"].calls[0] and saved == [{"deck": {"laser": 48}}]
    h._windows["audience"].calls.clear()
    h._relay("presenter", json.dumps({"lz": 1000}))
    assert '"lz": 160.0' in h._windows["audience"].calls[0] and saved[-1] == {"deck": {"laser": 160}}
    n = len(saved)
    h._relay("presenter", json.dumps({"lz": "大"}))
    h._relay("presenter", json.dumps({"lz": True}))
    assert len(saved) == n


def test_発表の設定は_項目ごとに足される_別の項目を消さない(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    api = app.Api(None)
    api.set_prefs({"deck": {"theme": "dark", "ratio": "4:3"}})
    api.set_prefs({"deck": {"laser": 48}})
    assert api.get_prefs()["deck"] == {"theme": "dark", "ratio": "4:3", "laser": 48}


def test_書き込みの操作の検査_正しいもの():
    b = {"o": "b", "s": 2, "id": "a12", "t": "arrow", "c": "#E5302A", "w": 6, "p": [[0.1, 0.2], [0.5, 0.6]]}
    assert deck.clean_mark(b) == {"o": "b", "s": 2, "id": "a12", "t": "arrow", "c": "#E5302A", "w": 6.0, "p": [[0.1, 0.2], [0.5, 0.6]]}
    assert deck.clean_mark({"o": "a", "id": "p3", "p": [[0, 1]]}) == {"o": "a", "id": "p3", "p": [[0.0, 1.0]]}
    assert deck.clean_mark({"o": "u", "s": 4}) == {"o": "u", "s": 4}
    assert deck.clean_mark({"o": "c", "s": 0}) == {"o": "c", "s": 0}
    assert deck.clean_mark({"o": "C"}) == {"o": "C"}


def test_書き込みの操作の検査_正しくないものは捨てる():
    good = {"o": "b", "s": 0, "id": "a1", "t": "pen", "c": "#112233", "w": 5, "p": [[0.5, 0.5]]}
    assert deck.clean_mark(good) is not None
    bad = [
        {**good, "id": "x1"}, {**good, "id": "a"}, {**good, "id": "a1;alert(1)"},                      # 識別子の形
        {**good, "c": "red"}, {**good, "c": "#12345"}, {**good, "c": "url(javascript:x)"},               # 色は #rrggbb だけ
        {**good, "t": "eraser"}, {**good, "w": 0}, {**good, "w": 9999}, {**good, "w": True},             # 種類・太さ
        {**good, "s": -1}, {**good, "s": "0"}, {**good, "s": 99999},                                      # スライドの番号
        {**good, "p": []}, {**good, "p": [[0.1]]}, {**good, "p": [[9, 9]]}, {**good, "p": [["a", "b"]]},  # 点
        {**good, "p": [[0.1, 0.1]] * 81}, {**good, "p": "x"},
        {"o": "z"}, {"o": "a", "id": "a1", "p": []}, {"o": "u"}, {"o": "u", "s": "x"}, "x", None, 5, [],
    ]
    for m in bad:
        assert deck.clean_mark(m) is None, m


def test_書き込みは受け渡す_ペンの状態も_決まった値だけ():
    h = host_with(["audience", "presenter"])
    mk = {"o": "b", "s": 1, "id": "p5", "t": "line", "c": "#1f6feb", "w": 5, "p": [[0.2, 0.3]]}
    h._relay("presenter", json.dumps({"mk": mk, "pc": 2, "pt": 3, "dw": False}))
    call = h._windows["audience"].calls[0]
    assert '"mk"' in call and '"id": "p5"' in call and '"pc": 2' in call and '"pt": 3' in call and '"dw": false' in call
    h._windows["audience"].calls.clear()
    h._relay("presenter", json.dumps({"mk": {**mk, "c": "red"}, "pc": 99, "pt": -1, "dw": "no"}))
    assert h._windows["audience"].calls[0] == "window.Deck && window.Deck.apply({})"
