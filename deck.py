"""発表（スライドショー）。ビューアとエディタで同じ内容を使う。

- スライドは、文書の水平線（---）で区切る。区切りの扱いと、HTML の組み立ては、画面側（deck_ui.js）が受け持つ。
  組み立てた HTML は、1つで完結する（deck.js・deck.css・テーマ・文書の中身が全部入る）ので、そのまま、
  アプリの別ウィンドウ（全画面）でも、保存してブラウザーでも使える。
- ここでは、(1) テーマ（見た目の CSS）、(2) モニターの一覧、(3) 発表用のウィンドウ（聴衆の画面と、手元の発表者ビュー）を扱う。
- ウィンドウは、聴衆の画面（選んだモニターで全画面）と、発表者ビュー（手元の画面）の 2 つ。2 つの間は、Python を経由して、
  スライドの位置・暗転・タイマーを合わせる。
- テーマは、組み込みのほか、利用者が CSS で作れる。置き場所は、文書のあるフォルダー（と、その上のフォルダー）の
  `.markdown-editor\\themes\\*.css` と、アプリの設定フォルダーの `themes\\*.css`（近いものが先）。
  CSS の中の相対パスの画像（url(...)）は、1つで完結させるため、データとして埋め込む。
"""
import base64
import json
import mimetypes
import os
import re
import threading
import time

import webview

SETTINGS_DIR = ".markdown-editor"        # 文書フォルダー用の設定の置き場所（エディタの定型文・テンプレートと同じ）
MAX_ASSET = 3 * 1024 * 1024              # テーマの CSS から埋め込む画像 1 つの上限
MAX_CSS = 512 * 1024

BUILTIN = {
    "light": ("標準（明るい）", """
.slide { --slide-bg: #ffffff; --slide-fg: #1f2328; --slide-accent: #0969da; border-top: 12px solid var(--slide-accent); }
.slide .md-body h1, .slide .md-body h2 { color: var(--slide-accent); }
"""),
    "dark": ("ダーク", """
.slide { --slide-bg: #0d1117; --slide-fg: #e6edf3; --slide-accent: #58a6ff; --code: #161b22; --border: #30363d; --muted: #9da7b3; border-top: 12px solid var(--slide-accent); }
.slide .md-body h1, .slide .md-body h2 { color: var(--slide-accent); }
.slide .md-body a { color: #79c0ff; }
.slide .md-body th { background: #161b22; }
"""),
    "mono": ("白黒（印刷向き）", """
.slide { --slide-bg: #ffffff; --slide-fg: #000000; --slide-accent: #000000; --code: #f2f2f2; border-top: 6px solid #000; }
.slide .md-body h1, .slide .md-body h2 { color: #000; }
"""),
    "blue": ("ブルー（見出しの帯）", """
.slide { --slide-bg: #ffffff; --slide-fg: #1f2328; --slide-accent: #1f4e9c; padding-top: 0; }
.slide .md-body > h1:first-child, .slide .md-body > h2:first-child { background: var(--slide-accent); color: #fff; margin: 0 -80px .7em; padding: .55em 80px; }
.slide.sd-lead, .slide.sd-title { --slide-bg: #1f4e9c; --slide-fg: #fff; --slide-accent: #fff; }
.slide.sd-lead .md-body > h1:first-child, .slide.sd-title .md-body > h1:first-child { background: transparent; color: #fff; margin: 0 0 .5em; padding: 0; }
"""),
}
SAMPLE_THEME = """/* 発表のテーマ（自分用）。このファイルを編集すると、「発表」のテーマの一覧に、ファイル名で出ます。
   .slide がスライド 1 枚です。色は変数で決めます（--slide-bg 背景、--slide-fg 文字、--slide-accent 見出しなどの強調色）。
   スライドごとの種類は、文書に <!-- _class: lead --> と書くと、.slide.sd-lead として指定できます（lead・title・center は標準で用意）。
   画像は、このファイルからの相対パスで書けます（発表のときに、データとして埋め込まれます）。 */
.slide {
  --slide-bg: #fffdf5;
  --slide-fg: #2b2b2b;
  --slide-accent: #b4541a;
  /* background-image: url("背景.png"); background-size: cover; */
  border-left: 18px solid var(--slide-accent);
}
.slide .md-body h1, .slide .md-body h2 { color: var(--slide-accent); }
/* 表紙: 背景の色は、色そのものを書く（--slide-bg: var(--slide-accent) と書くと、同じ規則の中で --slide-accent を書き換えているため、背景が白くなる） */
.slide.sd-lead { --slide-bg: #b4541a; --slide-fg: #fff; --slide-accent: #fff; }
/* 全スライドのフッター（左下）: */
.slide::before { content: "資料の名前"; position: absolute; left: 80px; bottom: 16px; font-size: 18px; opacity: .55; }
"""


# 試験用ビルドの見本テーマにあった、表紙の背景の指定の誤り（--slide-bg: var(--slide-accent) と書き、同じ規則の中で --slide-accent も
# 書き換えていたため、背景が白、文字も白で、表紙が空白に見えた）。そのとき作られたファイルは、読み込むときに直す（ファイルは書き換えない）
_OLD_SAMPLE_LEAD = ".slide.sd-lead { --slide-bg: var(--slide-accent); --slide-fg: #fff; --slide-accent: #fff; }"
_NEW_SAMPLE_LEAD = ".slide.sd-lead { --slide-bg: #b4541a; --slide-fg: #fff; --slide-accent: #fff; }"


def screens():
    """接続されているモニターの一覧。[{index, width, height, x, y, primary}]。"""
    out = []
    try:
        for i, s in enumerate(webview.screens):
            out.append({"index": i, "width": int(s.width), "height": int(s.height), "x": int(s.x), "y": int(s.y)})
    except Exception:
        return []
    primary = next((s["index"] for s in out if s["x"] == 0 and s["y"] == 0), 0 if out else -1)
    for s in out:
        s["primary"] = s["index"] == primary
    return out


def default_screens(infos=None):
    """発表を出すモニター（聴衆）と、発表者ビューを出すモニター（手元）の、既定の選び方。

    2 枚以上あれば、主モニター以外の最初のものを聴衆に、主モニターを手元にする（ノートパソコン + プロジェクター）。
    1 枚なら、どちらもそれ。モニターが分からなければ、どちらも -1。
    """
    infos = screens() if infos is None else infos
    if not infos:
        return {"audience": -1, "presenter": -1}
    primary = next((s["index"] for s in infos if s["primary"]), infos[0]["index"])
    others = [s["index"] for s in infos if s["index"] != primary]
    return {"audience": others[0] if others else primary, "presenter": primary}


def theme_dirs(doc_path, user_dir=None):
    """テーマの置き場所を、近い順に返す: 文書のあるフォルダーとその上の `.markdown-editor\\themes`、アプリの設定フォルダーの `themes`。"""
    out = []
    if doc_path:
        d = os.path.dirname(os.path.abspath(doc_path)) if not os.path.isdir(doc_path) else os.path.abspath(doc_path)
        for _ in range(16):
            cand = os.path.join(d, SETTINGS_DIR, "themes")
            if os.path.isdir(cand):
                out.append(("文書フォルダー", cand))
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    if user_dir:
        cand = os.path.join(user_dir, "themes")
        if os.path.isdir(cand):
            out.append(("ユーザー", cand))
    return out


def list_themes(doc_path=None, user_dir=None):
    """選べるテーマ: 組み込み + 利用者の CSS。[{id, name, source}]。同じ名前は、近いほうが勝つ。"""
    items = [{"id": k, "name": v[0], "source": "組み込み"} for k, v in BUILTIN.items()]
    seen = set()
    for label, folder in theme_dirs(doc_path, user_dir):
        try:
            names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".css"))
        except OSError:
            continue
        for n in names:
            stem = n[:-4]
            if stem in seen:
                continue
            seen.add(stem)
            items.append({"id": "user:" + os.path.join(folder, n), "name": stem, "source": label})
    return items


_URL = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""", re.I)


def inline_urls(css, base_dir):
    """CSS の url(...) のうち、相対パスのファイルを、データ（data:）にして埋め込む。見つからない・大きすぎるものは、そのまま。"""
    def sub(m):
        ref = m.group(2).strip()
        if re.match(r"^(data:|https?:|#|//)", ref, re.I):
            return m.group(0)
        path = os.path.normpath(os.path.join(base_dir, ref.replace("/", os.sep)))
        try:
            if os.path.getsize(path) > MAX_ASSET:
                return m.group(0)
            with open(path, "rb") as f:
                raw = f.read()
        except OSError:
            return m.group(0)
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        return 'url("data:%s;base64,%s")' % (mime, base64.b64encode(raw).decode("ascii"))
    return _URL.sub(sub, css)


def theme_css(theme_id, doc_path=None, user_dir=None):
    """テーマの CSS。組み込みの id、または list_themes が返した利用者のテーマ。知らなければ、標準。"""
    if theme_id in BUILTIN:
        return BUILTIN[theme_id][1]
    if isinstance(theme_id, str) and theme_id.startswith("user:"):
        path = theme_id[5:]
        allowed = {os.path.normcase(os.path.abspath(t["id"][5:])) for t in list_themes(doc_path, user_dir) if t["id"].startswith("user:")}
        if os.path.normcase(os.path.abspath(path)) in allowed:       # 一覧にあるものだけ（任意のファイルを読ませない）
            try:
                if os.path.getsize(path) <= MAX_CSS:
                    with open(path, encoding="utf-8-sig") as f:
                        return inline_urls(f.read().replace(_OLD_SAMPLE_LEAD, _NEW_SAMPLE_LEAD), os.path.dirname(path))
            except (OSError, UnicodeDecodeError):
                pass
    return BUILTIN["light"][1]


def make_sample_theme(doc_path=None, user_dir=None):
    """自分用のテーマの見本を作る。文書のあるフォルダー（無ければ設定フォルダー）の themes に書く。{error, path}。"""
    if doc_path:
        base = os.path.dirname(os.path.abspath(doc_path)) if not os.path.isdir(doc_path) else os.path.abspath(doc_path)
        folder = os.path.join(base, SETTINGS_DIR, "themes")
    elif user_dir:
        folder = os.path.join(user_dir, "themes")
    else:
        return {"error": "置き場所が決まりません（先に、文書かフォルダーを開いてください）", "path": None}
    try:
        os.makedirs(folder, exist_ok=True)
        n, path = 0, os.path.join(folder, "マイテーマ.css")
        while os.path.exists(path):
            n += 1
            path = os.path.join(folder, "マイテーマ%d.css" % (n + 1))
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(SAMPLE_THEME)
    except OSError as e:
        return {"error": "作れませんでした: " + str(e), "path": None}
    return {"error": None, "path": path}


class _Bridge:
    """発表用のウィンドウの JavaScript から呼ぶもの。ウィンドウごとに 1 つ（役割: audience / presenter）。

    属性は、先頭に _ を付ける（pywebview は、公開された属性の中のメソッドまで、JavaScript へ出してしまうため）。
    """

    def __init__(self, host, role):
        self._host = host
        self._role = role

    def sync(self, state_json):
        self._host._relay(self._role, state_json)

    def toggle_fullscreen(self):
        w = self._host._windows.get(self._role)
        if w is not None:
            w.toggle_fullscreen()

    def close_all(self):
        self._host.close()

    def open_presenter(self):
        self._host.open_presenter()


class DeckHost:
    def __init__(self, resource_path, user_dir_func=None):
        self._resource_path = resource_path
        self._user_dir = user_dir_func or (lambda: None)
        self._windows = {}
        self._html = None
        self._opts = {}
        self._t0 = 0
        self._lock = threading.RLock()

    # ---- 部品
    def assets(self):
        out = {}
        for key, name in (("js", "deck.js"), ("css", "deck.css")):
            with open(self._resource_path(name), encoding="utf-8") as f:
                out[key] = f.read()
        return out

    def prepare(self, doc_path=None):
        """発表の画面を組み立てるのに要るもの: 部品・テーマの一覧・モニターの一覧・既定のモニター。"""
        infos = screens()
        return {"assets": self.assets(), "themes": list_themes(doc_path, self._user_dir()), "screens": infos,
                "defaults": default_screens(infos), "error": None}

    def theme_css(self, theme_id, doc_path=None):
        return theme_css(theme_id, doc_path, self._user_dir())

    def make_sample_theme(self, doc_path=None):
        return make_sample_theme(doc_path, self._user_dir())

    # ---- ウィンドウ
    def _screen(self, index):
        try:
            infos = list(webview.screens)
        except Exception:
            return None
        return infos[index] if isinstance(index, int) and 0 <= index < len(infos) else None

    def _make(self, role, title, screen, fullscreen):
        html = self._html.replace('"__DECK_ROLE__"', json.dumps(role)).replace('"__DECK_T0__"', str(self._t0))       # 経過時間の起点は、2 つのウィンドウで同じ
        kw = dict(html=html, js_api=_Bridge(self, role), background_color="#000000", text_select=False, zoomable=False)
        if screen is not None:
            kw["screen"] = screen
        if fullscreen:
            kw["fullscreen"] = True
        else:
            kw.update(width=1180, height=760, min_size=(720, 480))
        w = webview.create_window(title, **kw)
        try:
            w.events.closed += lambda: self._on_closed(role)
        except Exception:
            pass
        self._windows[role] = w
        return w

    def open(self, html, opts):
        """発表を始める。opts: {screen（聴衆のモニターの番号）, presenter（発表者ビューも開く）, presenter_screen, title}。"""
        if not (isinstance(html, str) and '"__DECK_ROLE__"' in html and isinstance(opts, dict)):
            return {"error": "発表の内容が正しくありません"}
        with self._lock:
            self.close()
            self._html = html
            self._opts = dict(opts)
            self._t0 = int(time.time() * 1000)
            title = str(opts.get("title") or "発表")[:120]
            d = default_screens()
            aud = opts.get("screen")
            aud = aud if isinstance(aud, int) else d["audience"]
            pres_screen = opts.get("presenter_screen")
            pres_screen = pres_screen if isinstance(pres_screen, int) else d["presenter"]
            self._make("audience", title, self._screen(aud), opts.get("fullscreen", True) is not False)       # 試験では、全画面にしない
            if opts.get("presenter"):
                self._make("presenter", title + "（発表者ビュー）", self._screen(pres_screen), False)
        return {"error": None, "windows": sorted(self._windows)}

    def open_presenter(self):
        with self._lock:
            if self._html is None or "presenter" in self._windows:
                return
            d = default_screens()
            ps = self._opts.get("presenter_screen")
            self._make("presenter", str(self._opts.get("title") or "発表")[:120] + "（発表者ビュー）", self._screen(ps if isinstance(ps, int) else d["presenter"]), False)

    def export_pdf(self, html, mode, path):
        """スライドを PDF にする。mode: "slides"（1 スライド 1 ページ。ページの大きさ = スライドの大きさ）、
        "handout"（A4 縦に、スライドとノート）。画面の外に置いたウィンドウで組み、WebView2 の PDF 出力を使う。"""
        if not (isinstance(html, str) and '"__DECK_ROLE__"' in html and mode in ("slides", "handout") and isinstance(path, str) and path):
            return {"error": "PDF にする内容が正しくありません"}
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        import printing
        w = None
        try:
            w = webview.create_window("PDF", html=html.replace('"__DECK_ROLE__"', '"standalone"'), x=-32000, y=-32000, width=1280, height=720, focus=False, background_color="#ffffff")       # 画面の外に出す（hidden にすると、ページが読み込まれない）
            deadline = time.time() + 30
            ready = False
            while time.time() < deadline and not ready:
                try:
                    ready = bool(w.evaluate_js("!!(window.Deck && window.Deck.preparePrint)"))
                except Exception:
                    ready = False
                if not ready:
                    time.sleep(0.2)
            if not ready:
                return {"error": "PDF にするための準備が、時間内に終わりませんでした"}
            time.sleep(0.4)                                # 縮小・図の配置が終わるのを待つ
            info = json.loads(w.evaluate_js("JSON.stringify(Deck.preparePrint(%s))" % ("true" if mode == "handout" else "false")))
            time.sleep(0.3)
            printing.save_pdf_sized(w, path, info["w"], info["h"], 12 if mode == "handout" else 0)
            with open(path, "rb") as f:
                pages = printing.count_pdf_pages(f.read())
        except printing.PrintError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": "PDF にできませんでした: " + str(e)}
        finally:
            if w is not None:
                try:
                    w.destroy()
                except Exception:
                    pass
        return {"error": None, "path": path, "pages": pages}

    def _relay(self, sender, state_json):
        """片方のウィンドウの状態（スライドの位置・暗転・タイマー）を、もう片方へ渡す。"""
        try:
            state = json.loads(state_json)
        except (TypeError, ValueError):
            return
        if not isinstance(state, dict):
            return
        safe = {}
        if isinstance(state.get("i"), int):
            safe["i"] = state["i"]
        if state.get("black") in ("", "black", "white"):
            safe["black"] = state["black"]
        if state.get("ratio") in ("16:9", "16:10", "4:3", "auto"):
            safe["ratio"] = state["ratio"]
        for key in ("laser", "zoom"):
            if isinstance(state.get(key), bool):
                safe[key] = state[key]
        zk = state.get("zk")
        if isinstance(zk, (int, float)) and not isinstance(zk, bool):
            safe["zk"] = min(5.0, max(1.5, float(zk)))
        for key in ("u", "v"):                                         # レーザー・拡大の位置（スライド上の 0〜1。スライドの外は null）
            if key in state:
                val = state[key]
                if val is None:
                    safe[key] = None
                elif isinstance(val, (int, float)) and not isinstance(val, bool) and -0.5 <= val <= 1.5:
                    safe[key] = float(val)
        if isinstance(state.get("t"), (int, float)):
            safe["t"] = state["t"]
        for role, w in list(self._windows.items()):
            if role != sender:
                try:
                    w.evaluate_js("window.Deck && window.Deck.apply(%s)" % json.dumps(safe))
                except Exception:
                    pass

    def _on_closed(self, role):
        with self._lock:
            self._windows.pop(role, None)
            others = list(self._windows.values())
            self._windows.clear()
        for w in others:                 # 片方を閉じたら、もう片方も閉じる
            try:
                w.destroy()
            except Exception:
                pass

    def close(self):
        with self._lock:
            ws = list(self._windows.values())
            self._windows.clear()
        for w in ws:
            try:
                w.destroy()
            except Exception:
                pass
