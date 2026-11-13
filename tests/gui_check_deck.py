"""発表（スライドショー）を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_deck.py

組み立てたスライドを別ウィンドウで開き、キー操作・拡大縮小・スライド一覧・暗転・縮小・印刷用の紙面・発表者ビューとの連動・PDF を確かめる。
設定の置き場所は一時フォルダーへ向ける（利用者の設定を書き換えない）。発表のウィンドウは、全画面にしない（試験用）。
"""
import json
import os
import re
import sys
import tempfile
import threading
import time

sys.path.insert(0, '.')
os.environ['APPDATA'] = tempfile.mkdtemp(prefix='md_appdata_')
import webview
import mdeditor
import gui_nodialog  # noqa: F401  OS のダイアログを出さない（キー入力を奪うため）

APP = 'editor'
OPEN = 'openPath'
tmp = tempfile.mkdtemp()
DOC = os.path.join(tmp, 'deck.md')
os.makedirs(os.path.join(tmp, '.markdown-editor', 'themes'))
open(os.path.join(tmp, '.markdown-editor', 'themes', '自分.css'), 'w', encoding='utf-8').write(
    '.slide { --slide-bg: #fff3cd; background-image: url("bg.png"); }\n')
open(os.path.join(tmp, '.markdown-editor', 'themes', 'bg.png'), 'wb').write(
    bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea75be1930000000049454e44ae426082'))
body_long = "\n".join("- 項目 %d：これは長い箇条書きの項目です" % i for i in range(1, 22))
body_over = "\n".join("- 項目 %d：これは、とても長い箇条書きの項目で、さらに文字を増やして、1 行をできるだけ長くします" % i for i in range(1, 70))
open(DOC, 'w', encoding='utf-8').write("""# 発表のテスト

<!-- _class: lead -->

マンション管理組合 理事会

<!-- note: 最初の挨拶をする。
時間は 5 分。 -->

---

## 議題

- 修繕計画について
- 会計報告
- [外部リンク](https://example.com)

<!-- note: 議題を読み上げる -->

---

## 費用の比較[^1]

| 項目 | 金額 |
| --- | ---: |
| 外壁 | 1,200万円 |

数式 $x^2 + y^2 = r^2$

---

## 長いスライド

""" + body_long + """

---

## 二段組み

::::columns
:::col
左の段
- A
:::
:::col
右の段
- B
:::
::::

---

## 収まらない

""" + body_over + """

[^1]: 脚注の本文です。
""")

api = mdeditor.Api(None)
w = webview.create_window('t', html=mdeditor.build_html(), js_api=api, width=1400, height=900, x=20, y=20)
api._window = w
results = []
dwin = []


def js(code):
    return w.evaluate_js(code)


def check(name, got, want):
    ok = got == want
    results.append(ok)
    print(('OK ' if ok else 'NG ') + name + ('' if ok else f'\n    実際: {got!r}\n    期待: {want!r}'), flush=True)


def wait(code, timeout=20, win=None):
    t = time.time()
    win = win or w
    while time.time() - t < timeout:
        try:
            if win.evaluate_js(code):
                return True
        except Exception:
            pass
        time.sleep(.2)
    return False


def build(theme='light', ratio='16:9', from_cursor=False):
    js("window.__b = null; api.deck_prepare(null).then(a => deckBuild({theme: %s, ratio: %s, fromCursor: %s, assets: a.assets, title: 't'})).then(b => { window.__b = b; });" % (
        json.dumps(theme), json.dumps(ratio), 'true' if from_cursor else 'false'))
    wait("window.__b !== null", 40)
    return js("window.__b.html"), json.loads(js("JSON.stringify({count: window.__b.count, start: window.__b.start, warnings: window.__b.warnings})"))


def open_deck(html, name='deck', size=(1280, 720)):
    d = webview.create_window(name, html=html.replace('"__DECK_ROLE__"', '"standalone"'), width=size[0], height=size[1], x=40, y=40)
    dwin.append(d)
    ok = wait("!!(window.Deck && window.Deck.state)", 25, d)
    return d, ok


def key(d, k, **kw):
    d.evaluate_js("document.dispatchEvent(new KeyboardEvent('keydown', Object.assign({key: %s, bubbles: true}, %s)))" % (json.dumps(k), json.dumps(kw)))
    time.sleep(.25)


def st(d):
    return json.loads(d.evaluate_js("JSON.stringify(Deck.state())"))


def mouse(win, sel, kind, u, v, btn=0, buttons=0, **mods):
    win.evaluate_js("(() => { const el = document.querySelector(%s), r = el.getBoundingClientRect(); el.dispatchEvent(new MouseEvent(%s, Object.assign({clientX: r.left + r.width * %s, clientY: r.top + r.height * %s, button: %s, buttons: %s, bubbles: true, cancelable: true}, %s))); })()" % (
        json.dumps(sel), json.dumps(kind), u, v, btn, buttons, json.dumps(mods)))
    time.sleep(.15)


def drag(win, sel, u0, v0, u1, v1, click=False, **mods):
    # 押す → 動かす → 離す を、1 回の呼び出しで行う（click=True なら、離した直後に click も届ける。実際のブラウザーと同じ順序）
    win.evaluate_js("(() => { const el = document.querySelector(%s), r = el.getBoundingClientRect(); const P = (u, v) => [r.left + r.width * u, r.top + r.height * v]; const mods = %s;"
                    " const fire = (t, p, btn, bs) => el.dispatchEvent(new MouseEvent(t, Object.assign({clientX: p[0], clientY: p[1], button: btn, buttons: bs, bubbles: true, cancelable: true}, mods)));"
                    " const a = P(%s, %s), m = P(%s, %s), b = P(%s, %s);"
                    " fire('mousedown', a, 0, 1); fire('mousemove', m, 0, 1); fire('mousemove', b, 0, 1); fire('mouseup', b, 0, 0);"
                    " if (%s) fire('click', b, 0, 0); })()" % (
                        json.dumps(sel), json.dumps(mods), u0, v0, (u0 + u1) / 2, (v0 + v1) / 2, u1, v1, 'true' if click else 'false'))
    time.sleep(.5)


def svg_count(win, tag):
    return win.evaluate_js("(document.getElementById('ink') ? document.getElementById('ink') : document.querySelector('svg.ink')).querySelectorAll(%s).length" % json.dumps(tag))


def last_attr(win, name):
    return win.evaluate_js("document.querySelector('#ink, svg.ink').lastElementChild.getAttribute(%s)" % json.dumps(name))


def drive():
    time.sleep(8)
    js("%s(%s)" % (OPEN, json.dumps(DOC)))
    check("文書が開いて、描かれる", wait("document.querySelector('#preview .deck-columns') !== null && document.querySelector('#preview .katex') !== null"), True)
    time.sleep(.8)

    # --- 組み立て
    html, info = build()
    check("スライドに分かれる（水平線で区切り、脚注は最後の 1 枚）", info['count'], 7)
    check("1つで完結する HTML（役割の印・実行部分・テーマ・数式の CSS が入る）",
          [html.startswith('<!doctype html>'), '"__DECK_ROLE__"' in html, 'window.Deck' in html, '.slide-num' in html, '.katex' in html, '--slide-accent' in html], [True] * 6)
    check("外部への読み込みがない（1つで完結）", re.findall(r'(?:src|href)="https?://', html.replace('href="https://example.com"', '')), [])
    js("window.__m = null; deckMeasure(window.__b.html).then(m => { window.__m = m; }); null")
    wait("window.__m !== null", 20)
    check("収まらないスライドの警告は、実行前の測定で出る", json.loads(js("JSON.stringify(window.__m)")), {"over": [6], "shrunk": [4]})
    check("測定の文言", js("deckMeasureText(window.__m)"), ["収まらないスライド: 6（内容を減らすか、分けてください）", "縮小して収めるスライド: 4"])

    d, ok = open_deck(html)
    check("別ウィンドウで、スライドが動き出す", ok, True)
    time.sleep(1.5)
    s = st(d)
    check("最初のスライド・7 枚・単独", [s['i'], s['n'], s['role']], [0, 7, 'standalone'])
    check("画面に合わせて拡大縮小される（1280×720 の窓で、倍率はほぼ 1 以下）", 0.4 < s['scale'] <= 1.0, True)
    check("スライドの種類（lead）が付く", d.evaluate_js("document.querySelectorAll('.slide')[0].classList.contains('sd-lead')"), True)
    check("発表者ノートは、スライドに付き、画面には出ない",
          d.evaluate_js("[document.querySelectorAll('.slide')[0].querySelector('.slide-note').textContent.includes('時間は 5 分'), getComputedStyle(document.querySelector('.slide-note')).display]"), [True, 'none'])
    d.evaluate_js("Deck.goto(4)"); time.sleep(.4)
    check("段組みが横に並ぶ", d.evaluate_js("(() => { const c = document.querySelectorAll('.slide')[4].querySelectorAll('.deck-col'); return Math.abs(c[0].getBoundingClientRect().top - c[1].getBoundingClientRect().top) < 2 && c[1].getBoundingClientRect().left > c[0].getBoundingClientRect().left; })()"), True)
    d.evaluate_js("Deck.goto(0)")
    check("収まらないスライドは縮小される（4 枚目）、それでも収まらないものは印が付く（6 枚目）", d.evaluate_js("JSON.stringify([Deck.shrunk(), Deck.overflow()])"), '[[4],[6]]')
    check("最後のスライドは、脚注", d.evaluate_js("document.querySelectorAll('.slide')[6].textContent.includes('脚注の本文です')"), True)

    # --- 操作
    key(d, 'ArrowRight'); check("→ で次へ", st(d)['i'], 1)
    key(d, ' '); check("Space で次へ", st(d)['i'], 2)
    key(d, 'ArrowLeft'); check("← で前へ", st(d)['i'], 1)
    key(d, 'End'); check("End で最後へ", st(d)['i'], 6)
    key(d, 'ArrowRight'); check("最後で → を押しても、はみ出さない", st(d)['i'], 6)
    key(d, 'Home'); check("Home で最初へ", st(d)['i'], 0)
    key(d, 'ArrowLeft'); check("最初で ← を押しても、はみ出さない", st(d)['i'], 0)
    key(d, '4'); key(d, 'Enter'); check("数字 + Enter で、そのスライドへ（4 → 4 枚目）", st(d)['i'], 3)
    key(d, 'b'); check("B で暗転", st(d)['black'], 'black')
    check("暗転は、画面全体を覆う", d.evaluate_js("getComputedStyle(document.getElementById('screen')).display"), 'block')
    key(d, 'b'); check("もう一度 B で戻る", st(d)['black'], '')
    key(d, 'b'); d.evaluate_js("document.getElementById('screen').click()"); time.sleep(.3)
    check("暗転は、クリックでも戻る", st(d)['black'], '')
    key(d, 'w'); check("W で白画面", st(d)['black'], 'white'); key(d, 'w')
    key(d, 'l'); check("L でレーザーポインター", [st(d)['laser'], d.evaluate_js("document.body.classList.contains('laser')")], [True, True]); key(d, 'l')
    key(d, 'z'); check("Z で部分拡大", st(d)['zoom'], True)
    check("部分拡大では、拡大の倍率が掛かる", d.evaluate_js("document.getElementById('scaler').style.transform.includes('scale(')"), True); key(d, 'z')
    key(d, '?'); check("? で操作の一覧", d.evaluate_js("document.getElementById('help').classList.contains('on')"), True); key(d, 'Escape')
    check("Esc で操作の一覧が閉じる", d.evaluate_js("document.getElementById('help').classList.contains('on')"), False)

    # --- スライド一覧
    key(d, 'g'); check("G でスライド一覧が開く（7 枚）", [st(d)['overview'], d.evaluate_js("document.querySelectorAll('#overview .thumb').length")], [True, 7])
    check("一覧のサムネイルでも、表紙は中央寄せのまま", d.evaluate_js("getComputedStyle(document.querySelector('#overview .thumb .slide')).display"), "flex")
    fit = d.evaluate_js("Math.round(parseFloat(document.querySelectorAll('.slide')[3].dataset.fit) * 100)")
    check("一覧に、縮小と収まらない印が付く", d.evaluate_js("[...document.querySelectorAll('#overview .thumb .warn')].map(e => e.textContent)"), ["縮小 %d%%" % fit, "収まらない"])
    key(d, 'ArrowRight'); key(d, 'Enter'); check("一覧で → と Enter を押すと、そのスライドへ（4 → 5 枚目）", [st(d)['overview'], st(d)['i']], [False, 4])
    key(d, 'g'); d.evaluate_js("document.querySelectorAll('#overview .thumb')[1].click()"); time.sleep(.3)
    check("一覧のサムネイルを押すと、そのスライドへ", [st(d)['overview'], st(d)['i']], [False, 1])

    # --- 画面の比率
    key(d, 'r'); check("R で比率が変わる（16:10 → 幅 1152）", [st(d)['ratio'], st(d)['W']], ['16:10', 1152])
    key(d, 'r'); check("4:3 → 幅 960", [st(d)['ratio'], st(d)['W']], ['4:3', 960])
    key(d, 'r'); check("画面に合わせる → 窓の比率", [st(d)['ratio'], abs(st(d)['W'] / 720 - d.evaluate_js("innerWidth / innerHeight")) < 0.02], ['auto', True])
    key(d, 'r'); check("もう一度で、16:9 に戻る", [st(d)['ratio'], st(d)['W']], ['16:9', 1280])

    # --- リンクは開かない
    d.evaluate_js("goto = Deck.goto; Deck.goto(2)"); time.sleep(.3)
    check("発表中は、リンクを押しても、ウィンドウが別のページに変わらない",
          d.evaluate_js("(() => { const a = document.querySelector('.slide.cur a'); const e = new MouseEvent('click', {bubbles: true, cancelable: true}); a.dispatchEvent(e); return e.defaultPrevented; })()"), True)

    # --- 印刷用の紙面
    pp = json.loads(d.evaluate_js("JSON.stringify(Deck.preparePrint(false))"))
    check("印刷（スライド）: 1 スライド 1 ページ、ページの大きさはスライド", [pp['pages'], pp['w'], pp['h'], d.evaluate_js("document.querySelectorAll('#printroot .page').length")], [7, 1280, 720, 7])
    check("印刷（スライド）: 用紙の指定がスライドの大きさ", d.evaluate_js("document.getElementById('pagestyle').textContent.includes('1280px 720px')"), True)
    check("印刷（スライド）: 表紙は、中央寄せのまま（画面と同じ配置）", d.evaluate_js("getComputedStyle(document.querySelector('#printroot .page .slide')).display"), "flex")
    d.evaluate_js("Deck.endPrint()")
    check("印刷の紙面は、片付けられる", d.evaluate_js("[document.querySelectorAll('#printroot .page').length, !!document.getElementById('pagestyle')]"), [0, False])
    pp = json.loads(d.evaluate_js("JSON.stringify(Deck.preparePrint(true))"))
    check("配布資料: A4 縦、ノートが付く", [pp['w'], pp['h'], d.evaluate_js("document.querySelectorAll('#printroot .page .note')[0].textContent.includes('時間は 5 分')")], [794, 1123, True])
    d.evaluate_js("Deck.endPrint()")
    d.destroy(); dwin.clear()

    # --- テーマ
    html, _ = build(theme='dark')
    d, ok = open_deck(html); time.sleep(1)
    check("ダークのテーマ: 背景が暗い", d.evaluate_js("getComputedStyle(document.querySelector('.slide.cur')).backgroundColor"), 'rgb(13, 17, 23)')
    d.destroy(); dwin.clear()
    js("window.__tids = null; api.deck_prepare(%s).then(a => { window.__tids = a.themes; });" % json.dumps(DOC))
    wait("window.__tids !== null")
    user_id = [t['id'] for t in json.loads(js("JSON.stringify(window.__tids)")) if t['name'] == '自分'][0]
    check("自分のテーマが一覧に出る（文書フォルダー）", user_id.startswith('user:'), True)
    html, _ = build(theme=user_id)
    d, ok = open_deck(html); time.sleep(1)
    check("自分のテーマ: 背景色と、埋め込まれた背景画像（データ）が効く",
          d.evaluate_js("[getComputedStyle(document.querySelector('.slide.cur')).backgroundColor, document.querySelector('style').textContent.includes('data:image/png;base64')]"), ['rgb(255, 243, 205)', True])
    d.destroy(); dwin.clear()
    # --- 見本のテーマ: 表紙が、見える（背景と文字が、同じ色にならない）
    mk = api.deck_make_theme(DOC)
    check("テーマの見本を作る", [mk["error"], os.path.isfile(mk["path"])], [None, True])
    js("window.__tids = null; api.deck_prepare(%s).then(a => { window.__tids = a.themes; });" % json.dumps(DOC))
    wait("window.__tids !== null")
    sample_id = [t["id"] for t in json.loads(js("JSON.stringify(window.__tids)")) if t["name"] == "マイテーマ"][0]
    html, _ = build(theme=sample_id)
    d, ok = open_deck(html); time.sleep(1)
    cover = json.loads(d.evaluate_js("JSON.stringify((() => { const s = document.querySelector('.slide.sd-lead'); return [getComputedStyle(s).backgroundColor, getComputedStyle(s.querySelector('.md-body')).color, getComputedStyle(s.querySelector('h1')).color]; })())"))
    check("見本のテーマ: 表紙の背景と、文字・見出しの色が違う（空白に見えない）", [cover[0] != cover[1], cover[0] != cover[2]], [True, True])
    check("見本のテーマ: 表紙の背景は、見出しの色（アクセント）そのものではなく、濃い色", cover[0], "rgb(180, 84, 26)")
    d.destroy(); dwin.clear()

    # --- 編集中の位置から始める
    js("cm.setCursor({line: 20, ch: 0})")
    html, info = build(from_cursor=True)
    check("編集中の位置のスライドから始める（20 行目は 3 枚目の途中）", info['start'], 2)
    d, ok = open_deck(html); time.sleep(1)
    check("その位置で開く", st(d)['i'], 2)
    d.destroy(); dwin.clear()

    # --- 書き込み（マーキング）
    html, _ = build()
    d, ok = open_deck(html); time.sleep(1)
    SC = '#scaler'
    drag(d, SC, 0.2, 0.2, 0.4, 0.4)
    check("レーザーポインターが切れていると、ドラッグしても書き込めない（書き込みは、L を入れているときだけ）", [st(d)['laser'], st(d)['ink']], [False, 0])
    key(d, 'l')
    check("L でレーザーポインターを入れると、書き込めるようになる", [st(d)['laser'], st(d)['draw']], [True, True])
    d.evaluate_js("document.getElementById('stage').dispatchEvent(new MouseEvent('click', {bubbles: true, button: 0}))"); time.sleep(.3)
    check("動かさないクリックは、これまでどおり次のスライドへ", st(d)['i'], 1)
    key(d, 'Home')
    drag(d, SC, 0.2, 0.3, 0.6, 0.5, click=True)
    check("左ボタンのドラッグで、線が引ける", [st(d)['ink'], st(d)['tool'], svg_count(d, 'polyline')], [1, 'pen', 1])
    check("ドラッグのあとのクリックでは、スライドは進まない", st(d)['i'], 0)
    first = d.evaluate_js("document.querySelector('#ink polyline').getAttribute('points').split(' ')[0].split(',').map(Number)")
    check("線の始まりは、押した位置（スライド上の 0.2・0.3）", [abs(first[0] - 0.2 * 1280) < 2, abs(first[1] - 0.3 * 720) < 2], [True, True])
    drag(d, SC, 0.1, 0.8, 0.5, 0.8, shiftKey=True)
    check("Shift+ドラッグで、直線", [st(d)['ink'], svg_count(d, 'line')], [2, 1])
    drag(d, SC, 0.1, 0.9, 0.4, 0.6, ctrlKey=True)
    check("Ctrl+ドラッグで、矢印（線と、矢じり）", [st(d)['ink'], svg_count(d, 'line'), svg_count(d, 'polyline')], [3, 2, 2])
    key(d, 'c')
    check("C キーで、ペンの色が変わる（赤 → 青）", st(d)['color'], 1)
    drag(d, SC, 0.7, 0.2, 0.9, 0.4)
    check("変えた色で、線が引ける", last_attr(d, 'stroke'), '#1f6feb')
    d.evaluate_js("Deck.goto(1)"); time.sleep(.3)
    mouse(d, SC, 'contextmenu', 0.5, 0.5, 2, 2); time.sleep(.3)
    check("右クリックは、書き込みが入っていても、これまでどおり前のスライドへ", st(d)['i'], 0)
    for _ in range(4):
        key(d, 'c')
    check("C キーを続けると、色が一巡する（青 → 緑 → 黄 → 黒 → 赤）", st(d)['color'], 0)
    lz0 = st(d)['lz']
    drag(d, SC, 0.7, 0.6, 0.9, 0.7)
    w_small = float(last_attr(d, 'stroke-width'))
    key(d, ']'); key(d, ']'); key(d, ']'); time.sleep(.4)
    drag(d, SC, 0.7, 0.7, 0.9, 0.8)
    w_big = float(last_attr(d, 'stroke-width'))
    check("] でペンの大きさが変わる（30 → 40 → 48 → 60）", [lz0, st(d)['lz']], [30, 60])
    check("大きさに応じて、ペンの太さも変わる", w_big > w_small, True)
    key(d, '['); key(d, '['); key(d, '['); time.sleep(.3)
    key(d, 'm')
    check("M でペンの種類が変わる（ペン → マーカー）", st(d)['tool'], 'marker')
    drag(d, SC, 0.1, 0.1, 0.4, 0.12)
    check("マーカーは、半透明の太い線", last_attr(d, 'stroke-opacity'), '0.38')
    n0 = st(d)['ink']
    d.evaluate_js("Deck.goto(1)"); time.sleep(.4)
    check("スライドを変えると、書き込みは見えなくなる（スライドごと）", [st(d)['ink'], svg_count(d, 'polyline')], [0, 0])
    d.evaluate_js("Deck.goto(0)"); time.sleep(.4)
    check("同じスライドに戻ると、書いたものが残っている", st(d)['ink'], n0)
    key(d, 'u'); check("U で 1 本戻る", st(d)['ink'], n0 - 1)
    key(d, 'e'); check("E で、このスライドの書き込みが消える", [st(d)['ink'], svg_count(d, 'polyline') + svg_count(d, 'line')], [0, 0])
    d.evaluate_js("Deck.goto(1)"); time.sleep(.3)
    drag(d, SC, 0.2, 0.2, 0.5, 0.5); d.evaluate_js("Deck.goto(2)"); time.sleep(.3); drag(d, SC, 0.2, 0.2, 0.5, 0.5)
    check("別のスライドにも書ける", st(d)['inkAll'], 2)
    key(d, 'E'); check("Shift+E で、すべてのスライドの書き込みが消える", [st(d)['inkAll'], st(d)['ink']], [0, 0])
    key(d, 'l'); check("L でレーザーポインターを切ると、書き込めなくなる", [st(d)['laser'], st(d)['draw']], [False, False])
    drag(d, SC, 0.2, 0.2, 0.5, 0.5)
    check("レーザーポインターが切れていると、ドラッグしても線は引けない", st(d)['inkAll'], 0)
    d.destroy(); dwin.clear()

    # --- レーザーの大きさを、発表の画面で選べる
    js("window.__b = null; api.deck_prepare(null).then(a => deckBuild({theme: 'light', ratio: '16:9', fromCursor: false, assets: a.assets, title: 't', laser: 48})).then(b => { window.__b = b; });")
    wait("window.__b !== null", 40)
    d, ok = open_deck(js("window.__b.html")); time.sleep(1)
    check("発表の画面で選んだ大きさ（48）で始まる（点の大きさは、48 × 拡大率）", [st(d)["lz"], abs(d.evaluate_js("Deck.state().lpx") - round(48 * d.evaluate_js('Math.min(innerWidth / 1280, innerHeight / 720)'))) <= 1], [48, True])
    d.destroy(); dwin.clear()

    # --- 聴衆の画面と発表者ビューの連動（全画面にしない）
    html, _ = build()
    r = api.deck_open(html, {'screen': 0, 'presenter': True, 'fullscreen': False, 'title': '試験'})
    check("発表を始める（聴衆と発表者ビューの 2 つ）", [r['error'], r['windows']], [None, ['audience', 'presenter']])
    ws = api._deck._windows
    ok1 = wait("!!(window.Deck && window.Deck.state)", 25, ws['audience']) and wait("!!(window.Deck && window.Deck.state)", 25, ws['presenter'])
    check("2 つとも動き出す", ok1, True)
    aud, pres = ws['audience'], ws['presenter']
    aud.move(20, 20); aud.resize(900, 520); pres.move(960, 20); pres.resize(1000, 700); time.sleep(1)
    check("役割が分かれている", [st(aud)['role'], st(pres)['role']], ['audience', 'presenter'])
    check("発表者ビューでも、表紙は聴衆の画面と同じ配置（中央寄せ）", pres.evaluate_js("[getComputedStyle(document.querySelector('.cur-pane .slide')).display, getComputedStyle(document.querySelector('.cur-pane .slide .md-body')).textAlign]"), ["flex", "center"])
    hint = pres.evaluate_js("document.getElementById('phint').textContent")
    check("発表者ビューに、ポインターのボタンはない（キーで操作する）", pres.evaluate_js("[!!document.getElementById('plaserminus'), !!document.getElementById('plaserplus')]"), [False, False])
    check("発表者ビューに、キー操作のメモが出る（スライド一覧 G・画面の比率 R など）", all(t in hint for t in ("G", "スライド一覧", "R", "画面の比率", "B", "暗転", "?", "操作の一覧", "L", "Z")), True)
    check("メモでは、L・書き込み・Z が、この順に続けて並ぶ", [hint.index("レーザー") < hint.index("書き込み") < hint.index("部分拡大")], [True])
    ls = "(() => { const s = Deck.state(), sc = Math.min(innerWidth / 1280, innerHeight / 720); return [s.lz, s.lpx, sc]; })()"
    lsp = "(() => { const s = Deck.state(), p = document.querySelector('#presenter .cur-pane'), sc = Math.min(p.clientWidth / 1280, p.clientHeight / 720); return [s.lz, s.lpx, sc]; })()"
    a = aud.evaluate_js(ls); p = pres.evaluate_js(lsp)
    check("聴衆の画面: レーザーの点の大きさは、スライドの大きさに比例する（既定 30 × 拡大率）", [a[0], abs(a[1] - round(30 * a[2])) <= 1, a[1] >= 8], [30, True, True])
    check("発表者ビュー: 点の大きさも、「いまのスライド」の大きさに比例する", [p[0], abs(p[1] - round(30 * p[2])) <= 1], [30, True])
    aud.resize(600, 340); time.sleep(1.2)
    b = aud.evaluate_js(ls)
    check("窓の大きさを変えても、スライドに対する点の大きさは変わらない", abs(b[1] / b[2] - a[1] / a[2]) < 2, True)
    aud.resize(900, 520); time.sleep(1)
    key(aud, "]"); time.sleep(.8)
    check("] で点が大きくなり（30 → 40）、発表者ビューにも反映される", [aud.evaluate_js("Deck.state().lz"), pres.evaluate_js("Deck.state().lz")], [40, 40])
    key(pres, "["); key(pres, "["); time.sleep(.8)
    check("発表者ビューで [ を 2 回押すと、小さくなり（24）、聴衆の画面にも反映される", [aud.evaluate_js("Deck.state().lz"), pres.evaluate_js("Deck.state().lz")], [24, 24])
    key(pres, "]"); key(pres, "]"); time.sleep(.8)
    check("発表者ビューで ] を 2 回押すと、大きくなる（24 → 30 → 40）", [aud.evaluate_js("Deck.state().lz"), pres.evaluate_js("Deck.state().lz")], [40, 40])
    key(pres, "["); time.sleep(.8)
    check("使い終わったら、既定の 30 に戻しておく", [aud.evaluate_js("Deck.state().lz"), abs(aud.evaluate_js("Deck.state().lpx") - round(30 * aud.evaluate_js("Math.min(innerWidth / 1280, innerHeight / 720)"))) <= 1], [30, True])
    # --- 書き込み: 発表者ビューで書くと、聴衆の画面にも出る
    key(pres, 'l'); time.sleep(.7)
    check("発表者ビューで L を入れると、聴衆の画面でも入る（書き込みは、L を入れているとき）", [st(pres)['laser'], st(aud)['laser']], [True, True])
    drag(pres, '#presenter .cur-pane .inner', 0.3, 0.4, 0.7, 0.6)
    time.sleep(.8)
    check("発表者ビューのドラッグで、聴衆の画面にも線が出る", [st(pres)['ink'], st(aud)['ink']], [1, 1])
    fa = aud.evaluate_js("document.querySelector('#ink polyline').getAttribute('points').split(' ')[0].split(',').map(Number)")
    check("線の位置が、スライド上で同じ（0.3・0.4）", [abs(fa[0] - 0.3 * 1280) < 3, abs(fa[1] - 0.4 * 720) < 3], [True, True])
    key(pres, 'c'); time.sleep(.6)
    check("発表者ビューの C で、ペンの色が変わり、聴衆の画面にも合う", [st(pres)['color'], st(aud)['color']], [1, 1])
    drag(aud, '#scaler', 0.1, 0.1, 0.3, 0.2); time.sleep(.8)
    check("聴衆の画面で書いた線も、発表者ビューに出る（青）", [st(aud)['ink'], st(pres)['ink'], pres.evaluate_js("document.querySelector('#presenter svg.ink').lastElementChild.getAttribute('stroke')")], [2, 2, '#1f6feb'])
    key(pres, 'u'); time.sleep(.8)
    check("発表者ビューの U で、聴衆の画面の線も 1 本戻る", [st(pres)['ink'], st(aud)['ink']], [1, 1])
    key(aud, 'e'); time.sleep(.8)
    check("聴衆の画面の E で、発表者ビューの書き込みも消える", [st(pres)['ink'], st(aud)['ink']], [0, 0])
    key(aud, 'l'); time.sleep(.8)
    check("聴衆の画面で L を切ると、発表者ビューでも切れて、書き込めなくなる", [st(pres)['laser'], st(aud)['laser'], st(pres)['draw']], [False, False, False])
    drag(pres, '#presenter .cur-pane .inner', 0.3, 0.3, 0.5, 0.4); time.sleep(.6)
    check("L が切れていると、発表者ビューでも、ドラッグしても書けない", [st(pres)['ink'], st(aud)['ink']], [0, 0])
    # --- 発表者ビュー: スライドの上のクリックで進める（左: 次、右: 前）
    key(pres, 'c'); key(pres, 'c'); key(pres, 'c'); key(pres, 'c'); time.sleep(.4)
    i0 = st(pres)['i']
    pres.evaluate_js("document.querySelector('#presenter .cur-pane .inner').dispatchEvent(new MouseEvent('click', {bubbles: true, button: 0}))"); time.sleep(.8)
    check("発表者ビューの「いまのスライド」を左クリックすると、次へ進む（聴衆の画面も）", [st(pres)['i'], st(aud)['i']], [i0 + 1, i0 + 1])
    mouse(pres, '#presenter .cur-pane .inner', 'contextmenu', 0.5, 0.5, 2, 2); time.sleep(.8)
    check("右クリックで、前へ戻る（聴衆の画面も）", [st(pres)['i'], st(aud)['i']], [i0, i0])
    pres.evaluate_js("document.querySelector('#presenter .next-pane .inner').dispatchEvent(new MouseEvent('click', {bubbles: true, button: 0}))"); time.sleep(.8)
    check("「次のスライド」を左クリックしても、次へ進む", [st(pres)['i'], st(aud)['i']], [i0 + 1, i0 + 1])
    pres.evaluate_js("document.getElementById('pprev').click()"); time.sleep(.8)
    key(pres, 'l'); time.sleep(.6)
    drag(pres, '#presenter .cur-pane .inner', 0.3, 0.3, 0.5, 0.4, click=True)
    check("発表者ビューで書いたあとのクリックでは、進まない（書き込みと区別される）", [st(pres)['i'], st(aud)['i'], st(pres)['ink']], [i0, i0, 1])
    key(pres, 'e'); time.sleep(.6)
    key(pres, 'l'); time.sleep(.6)
    key(pres, "r"); time.sleep(.8)
    check("発表者ビューで R を押すと、聴衆の画面の比率も変わる（16:10）", [st(pres)["ratio"], st(aud)["ratio"], st(aud)["W"]], ["16:10", "16:10", 1152])
    key(pres, "r"); key(pres, "r"); key(pres, "r"); time.sleep(.8)
    check("R を続けて押すと、4:3 → 画面に合わせる → 16:9 と進み、両方の画面が同じ", [st(pres)["ratio"], st(aud)["ratio"]], ["16:9", "16:9"])
    key(pres, "l"); time.sleep(.6)
    check("発表者ビューで L を押すと、聴衆の画面でもレーザーが入る", [st(pres)["laser"], st(aud)["laser"]], [True, True])
    mv = "(() => { const r = document.querySelector('#presenter .cur-pane .inner').getBoundingClientRect(); document.dispatchEvent(new MouseEvent('mousemove', {clientX: r.left + r.width * %s, clientY: r.top + r.height * %s, bubbles: true})); })()"
    exp = "(() => { const l = document.getElementById('laser'), sc = Math.min(innerWidth / 1280, innerHeight / 720); return [parseFloat(l.style.left) - ((innerWidth - 1280 * sc) / 2 + %s * 1280 * sc), parseFloat(l.style.top) - ((innerHeight - 720 * sc) / 2 + %s * 720 * sc), l.style.visibility]; })()"
    pres.evaluate_js(mv % ("0.5", "0.5")); time.sleep(.8)
    p = aud.evaluate_js(exp % ("0.5", "0.5"))
    check("手元のスライドの中央にマウスを置くと、聴衆の画面のスライドの中央に、レーザーの点が出る", [abs(p[0]) < 6, abs(p[1]) < 6, p[2]], [True, True, ""])
    pres.evaluate_js(mv % ("0.25", "0.75")); time.sleep(.8)
    p = aud.evaluate_js(exp % ("0.25", "0.75"))
    check("マウスの位置に、点が付いてくる（左から 1/4・上から 3/4）", [abs(p[0]) < 6, abs(p[1]) < 6], [True, True])
    pres.evaluate_js(mv % ("-0.2", "0.5")); time.sleep(.8)
    check("スライドの外にマウスを出すと、聴衆の画面の点は消える", aud.evaluate_js("document.getElementById('laser').style.visibility"), "hidden")
    key(pres, "z"); time.sleep(.6)
    check("発表者ビューで Z を押すと、聴衆の画面で部分拡大が入る", [st(pres)["zoom"], st(aud)["zoom"]], [True, True])
    pres.evaluate_js(mv % ("0.5", "0.5")); time.sleep(.6)
    pres.evaluate_js("document.dispatchEvent(new WheelEvent('wheel', {deltaY: -100, bubbles: true, cancelable: true}))"); time.sleep(.8)
    check("発表者ビューのホイールで、聴衆の画面の拡大の倍率が変わる（2 → 2.25）", [aud.evaluate_js("Deck.state().zk"), aud.evaluate_js("document.getElementById('scaler').style.transform.includes('scale(')")], [2.25, True])
    key(pres, "z"); key(pres, "l"); time.sleep(.8)
    check("もう一度 Z・L で、聴衆の画面の拡大とレーザーが切れる", [st(aud)["zoom"], st(aud)["laser"], st(pres)["laser"]], [False, False, False])
    check("発表者ビューは、ノートと次のスライドを出す",
          pres.evaluate_js("[document.querySelector('#presenter .notes').textContent.includes('時間は 5 分'), document.querySelectorAll('#presenter .inner').length]"), [True, 2])
    pres.evaluate_js("document.getElementById('pnext').click()"); time.sleep(1)
    check("発表者ビューで次へ → 聴衆の画面も進む", [st(aud)['i'], st(pres)['i']], [1, 1])
    check("発表者ビューのノートが、次のスライドのものに変わる", pres.evaluate_js("document.querySelector('#presenter .notes').textContent.includes('議題を読み上げる')"), True)
    key(aud, 'ArrowRight'); time.sleep(.8)
    check("聴衆の画面で次へ → 発表者ビューも進む", [st(aud)['i'], st(pres)['i']], [2, 2])
    key(aud, 'b'); time.sleep(.8)
    check("聴衆の画面を暗転 → 発表者ビューにも反映される", st(pres)['black'], 'black')
    check("暗転しても、発表者ビューは、暗くならない（膜がかからない）", pres.evaluate_js("getComputedStyle(document.getElementById('screen')).display"), 'none')
    check("暗転中は、発表者ビューのボタンが「暗転を解除」になる", pres.evaluate_js("document.getElementById('pblack').textContent"), '暗転を解除')
    pres.evaluate_js("document.getElementById('pnext').click()"); time.sleep(.8)
    check("暗転中でも、発表者ビューで操作できる（次へ → 聴衆の位置も進む）", [st(pres)['i'], st(aud)['i']], [3, 3])
    pres.evaluate_js("document.getElementById('pprev').click()"); time.sleep(.6)
    pres.evaluate_js("document.getElementById('pblack').click()"); time.sleep(.8)
    check("発表者ビューから暗転を戻せる", st(aud)['black'], '')
    check("発表者ビューは、収まらないスライドを知らせる", pres.evaluate_js("document.getElementById('pwarn').textContent"), '収まらないスライド: 6')
    check("経過時間は、発表を始めたときから動いている（2 枚目に進む前から）", pres.evaluate_js("document.getElementById('pelapsed').textContent") != '00:00', True)
    check("経過時間の起点は、2 つのウィンドウで同じ", [type(st(aud)['t0']).__name__ in ('int', 'float'), st(aud)['t0'] == st(pres)['t0']], [True, True])
    pres.evaluate_js("document.getElementById('ptimer').click()"); time.sleep(.5)
    check("「タイマーを戻す」で、00:00 に戻る", pres.evaluate_js("document.getElementById('pelapsed').textContent"), '00:00')
    aud.destroy(); time.sleep(1.5)
    check("片方を閉じると、もう片方も閉じる", list(api._deck._windows), [])

    # --- 発表者ビューを、あとから開く（O）
    r = api.deck_open(html, {'screen': 0, 'presenter': False, 'fullscreen': False, 'title': '試験'})
    check("発表者ビューなしで始める", r['windows'], ['audience'])
    wait("!!(window.Deck && window.Deck.state)", 25, api._deck._windows['audience'])
    api._deck.open_presenter(); time.sleep(.5)
    check("あとから、発表者ビューが開く", sorted(api._deck._windows), ['audience', 'presenter'])
    api._deck.close(); time.sleep(1)
    check("閉じると、すべて閉じる", list(api._deck._windows), [])

    # --- PDF
    out_slides, out_hand = os.path.join(tmp, 's.pdf'), os.path.join(tmp, 'h.pdf')
    rs = api.deck_export_pdf(html, 'slides', out_slides)
    check("スライドの PDF（7 ページ）", [rs['error'], rs['pages']], [None, 7])
    data = open(out_slides, 'rb').read()
    box = re.findall(rb'/MediaBox\s*\[([^\]]+)\]', data)[0].split()
    check("スライドの PDF: ページの大きさが 16:9（960×540pt）", [round(float(box[2])), round(float(box[3]))], [960, 540])
    rh = api.deck_export_pdf(html, 'handout', out_hand)
    check("配布資料の PDF（7 ページ）", [rh['error'], rh['pages']], [None, 7])
    box = re.findall(rb'/MediaBox\s*\[([^\]]+)\]', open(out_hand, 'rb').read())[0].split()
    check("配布資料の PDF: A4 縦（595×842pt）", [round(float(box[2])), round(float(box[3]))], [595, 842])
    check("PDF にできない内容は、エラーで返す（例外にしない）", bool(api.deck_export_pdf('<html></html>', 'slides', os.path.join(tmp, 'x.pdf'))['error']), True)

    # --- 発表の操作: ダイアログ（部分は、ask を差し替えて動かす）
    js("window.__asked = []; window._ask0 = ask; ask = async (t, x, b, extra) => { window.__asked.push(t); window.__form = extra ? extra.innerText : ''; return 0; }; const o = api.deck_open; api.deck_open = (h, op) => o.call(api, h, Object.assign({}, op, {fullscreen: false})); null")
    js("startPresentation()")
    check("「発表」のダイアログが開き、発表を始めると、ウィンドウが開く", wait("window.__asked.length >= 1", 20) and wait("true"), True)
    time.sleep(3)
    check("ダイアログの項目（画面・テーマ・比率・開始・発表者ビュー）", all(t in js("window.__form") for t in ('発表を出す画面', 'デザイン（テーマ）', '画面の比率', '開始', '発表者ビュー', 'レーザーポインターの大きさ')), True)
    check("開いたウィンドウに、スライドが入っている", bool(api._deck._windows) and wait("!!(window.Deck && window.Deck.state)", 20, api._deck._windows['audience']), True)
    check("選んだ設定が、次回の既定として保存される", sorted(api.get_prefs().get('deck', {}).keys()), ['laser', 'presenter', 'ratio', 'screen', 'theme'])
    api._deck.close(); time.sleep(1)

    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
