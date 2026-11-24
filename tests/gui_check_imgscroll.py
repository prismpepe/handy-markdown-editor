"""画像の多い文書で、編集（再描画）や、画像の遅れた読み込みがあっても、プレビューの表示位置がずれないことを、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_imgscroll.py

画像は、読み込むまで大きさが分からない。再描画のたびに、一時的に高さが縮み、スクロールの位置が切り詰められると、画像が読み込まれた
あとで、表示位置が大きくずれていた。また、編集欄のスクロールに合わせた位置も、画像が読み込まれる前の高さで決まり、そのまま残っていた。
画像は、わざと遅れて返す小さなサーバー（毎回読み込み直す設定）から読み込む（ネットの画像と同じ状況にする）。
設定の置き場所は一時フォルダーへ向ける（利用者の設定を書き換えない）。
"""
import http.server
import json
import os
import struct
import sys
import tempfile
import threading
import time
import zlib

sys.path.insert(0, '.')
os.environ['APPDATA'] = tempfile.mkdtemp(prefix='md_appdata_')
import webview
import mdeditor
import gui_nodialog  # noqa: F401  OS のダイアログを出さない（キー入力を奪うため）

tmp = tempfile.mkdtemp()
DELAY = 0.5


def png(w, h, rgb):
    raw = b''.join(b'\x00' + bytes(rgb) * w for _ in range(h))

    def chunk(t, d):
        c = struct.pack('>I', len(d)) + t + d
        return c + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 1)) + chunk(b'IEND', b'')


IMAGES = [png(900, 500, (40 * i + 30, 120, 200 - 20 * i)) for i in range(6)]


class Slow(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(DELAY)
        n = int(self.path.split('/p')[1].split('.')[0])
        body = IMAGES[n % 6]
        self.send_response(200)
        self.send_header('Content-Type', 'image/png')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')            # 毎回、読み込み直す
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Slow)
threading.Thread(target=srv.serve_forever, daemon=True).start()
PORT = srv.server_address[1]

parts = []
for n in range(30):
    parts.append(f"## 項目 {n}\n\n説明の文章です。{n} 番目の項目です。\n\n![図{n}](http://127.0.0.1:{PORT}/p{n % 6}.png?n={n})\n")
DOC = os.path.join(tmp, 'img.md')
open(DOC, 'w', encoding='utf-8').write("# 画像の多い文書\n\n" + "\n".join(parts))

api = mdeditor.Api(None)
w = webview.create_window('t', html=mdeditor.build_html(), js_api=api, width=1400, height=900, x=20, y=20)
api._window = w
results = []


def js(code):
    return w.evaluate_js(code)


def check(name, got, want):
    ok = got == want
    results.append(ok)
    print(('OK ' if ok else 'NG ') + name + ('' if ok else f'\n    実際: {got!r}\n    期待: {want!r}'), flush=True)


def wait(code, timeout=20):
    t = time.time()
    while time.time() - t < timeout:
        try:
            if w.evaluate_js(code):
                return True
        except Exception:
            pass
        time.sleep(.2)
    return False


ALL_LOADED = "[...document.querySelectorAll('#preview img')].length === 30 && [...document.querySelectorAll('#preview img')].every(i => i.complete && i.naturalWidth > 0)"


def pos_of(line):
    """その行の要素の、プレビューの上端からの位置。"""
    return js(("(() => { const pv = document.getElementById('pscroll'); const e = [...document.querySelectorAll('#preview [data-line]')].find(x => +x.dataset.line === %d);"
               " return e ? Math.round(e.getBoundingClientRect().top - pv.getBoundingClientRect().top) : null; })()") % line)


def line_with(text):
    return js("(() => { for (let i = 0; i < cm.lineCount(); i++) if (cm.getLine(i).includes(%s)) return i; return -1; })()" % json.dumps(text))


def drive():
    time.sleep(8)
    js("openPath(%s)" % json.dumps(DOC))
    check("文書が開いて、遅れて届く画像が、すべて読み込まれる", wait(ALL_LOADED, 60), True)
    time.sleep(.8)

    # --- 1. 打鍵のたびの再描画（画像は、毎回、読み込み直し。読み込まれるまで、高さが縮む）
    ln = line_with('15 番目')
    js("cm.setCursor({line: %d, ch: 0}); cm.scrollIntoView(null, 200); null" % ln)
    time.sleep(1.0)
    wait(ALL_LOADED, 60); time.sleep(.5)
    for k in range(3):
        js("cm.setCursor({line: %d, ch: cm.getLine(%d).length}); cm.replaceSelection('あ'); null" % (ln, ln))
        time.sleep(.3)                                       # 読み込みの途中で、次の打鍵
    wait(ALL_LOADED, 60); time.sleep(1.5)
    target = js("Math.round(document.getElementById('pscroll').clientHeight * 0.3)")
    got = pos_of(ln)
    check("編集して、画像が読み込まれたあと、書いている場所が、プレビューの 3 割あたりにある（±70px）", got is not None and abs(got - target) <= 70, True)
    print('    書いている行の位置', got, '（目標', target, '）', flush=True)

    # --- 2. 編集欄をスクロールしている間に、画像が遅れて届く
    js("document.getElementById('pscroll').scrollTop = 0; cm.scrollTo(0, 0); null")
    js("(() => { for (const i of document.querySelectorAll('#preview img')) { i.dataset.s = i.src; i.removeAttribute('src'); } })()")      # 画像が、まだ無い状態にする
    time.sleep(.3)
    js("cm.scrollTo(0, cm.heightAtLine(90, 'local')); null")
    time.sleep(.5)
    js("(() => { for (const i of document.querySelectorAll('#preview img')) { i.src = i.dataset.s + '&r=' + Math.random(); } })()")       # 画像が、遅れて届く
    wait(ALL_LOADED, 60); time.sleep(1.5)
    got = js("""(() => { const l = cm.lineAtHeight(cm.getScrollInfo().top, 'local'); const pv = document.getElementById('pscroll');
      const els = [...document.querySelectorAll('#preview [data-line]')].map(e => ({ l: +e.dataset.line, e })).filter(x => x.l <= l);
      const last = els[els.length - 1]; return last ? Math.round(last.e.getBoundingClientRect().top - pv.getBoundingClientRect().top) : null; })()""")
    check("編集欄の位置に合わせたあと、画像が遅れて届いても、プレビューが同じ場所を指す（上端付近）", got is not None and -120 <= got <= 80, True)
    print('    編集欄の先頭の行に対応する要素の位置', got, flush=True)

    # --- 3. 自分でスクロールしたあとは、画像の読み込みで、勝手に動かさない
    js("(() => { const pv = document.getElementById('pscroll'); pv.scrollTop = 2000; pv.dispatchEvent(new WheelEvent('wheel', {deltaY: 1, bubbles: true})); })()")
    time.sleep(.3)
    s1 = js("document.getElementById('pscroll').scrollTop")
    js("(() => { for (const i of document.querySelectorAll('#preview img')) { i.src = i.dataset.s + '&q=' + Math.random(); } })()")
    time.sleep(2.5)
    check("プレビューを自分でスクロールしたあとは、画像が読み込まれても、勝手に動かない", js("document.getElementById('pscroll').scrollTop"), s1)
    check("待ちが終わったら、一時の余白（pspacer）は、なくなる", js("document.getElementById('pspacer') ? document.getElementById('pspacer').offsetHeight : 0"), 0)

    # --- 4. 編集欄を少しずつスクロールしたとき、プレビューが、画像 1 枚分ずつ飛ばない（折り返しの中の位置も使って、なめらかに合わせる）
    wait(ALL_LOADED, 60); time.sleep(1.0)
    js("(() => { for (const i of document.querySelectorAll('#preview img')) { if (i.dataset.s) i.src = i.dataset.s + '&z=' + Math.random(); } })()")
    wait(ALL_LOADED, 60); time.sleep(1.5)
    mx = int(js("cm.getScrollInfo().height - cm.getScrollInfo().clientHeight"))
    last, worst = None, 0
    for y in range(0, min(mx, 3000), 8):
        js("cm.scrollTo(0, %d); null" % y); time.sleep(.03)
        st = js("document.getElementById('pscroll').scrollTop")
        if last is not None:
            worst = max(worst, abs(st - last))
        last = st
    check("編集欄を 8px ずつスクロールしたとき、プレビューの動きが、1 回で 60px を超えない（行の番号だけで合わせると、画像の行で、100px 以上飛ぶ）", worst <= 60, True)
    print('    1 回の最大の動き', worst, 'px', flush=True)

    # --- 5. 編集欄を最下端までスクロールしたら、プレビューも最下端になる（大きな要素が末尾にあっても、途中で止まらない）
    js("cm.scrollTo(0, 1e9); null"); time.sleep(.6)
    gap = js("(() => { const p = document.getElementById('pscroll'); return Math.round(p.scrollHeight - p.clientHeight - p.scrollTop); })()")
    check("編集欄が最下端のとき、プレビューも最下端（残り 5px 以内）", gap <= 5, True)
    print('    プレビューの残り', gap, 'px', flush=True)

    # --- 6. 再描画の途中で、編集欄を最上端へ戻しても、描画のあとで、プレビューが古い位置（最下端）へ戻らない
    js("cm.scrollTo(0, 1e9); null"); time.sleep(.6)
    js("updatePreview(false); null")                     # 描画を始めたところで、
    js("cm.scrollTo(0, 0); null")                        # 編集欄を、最上端へ
    time.sleep(2.0)
    top = js("document.getElementById('pscroll').scrollTop")
    check("再描画の途中で編集欄を最上端へ戻したら、プレビューも上端（60px 以内）", top <= 60, True)
    print('    プレビューの位置', top, flush=True)

    # --- 7. 画像が読み込まれる前に、編集欄を最下端へ動かしても、読み込まれたあとで、プレビューも最下端になる
    js("(() => { for (const i of document.querySelectorAll('#preview img')) { i.dataset.s = i.dataset.s || i.src; i.removeAttribute('src'); } cm.scrollTo(0, 1e9); })()")
    time.sleep(.4)
    js("(() => { for (const i of document.querySelectorAll('#preview img')) { i.src = i.dataset.s + '&b=' + Math.random(); } })()")
    wait(ALL_LOADED, 60); time.sleep(1.5)
    gap = js("(() => { const p = document.getElementById('pscroll'); return Math.round(p.scrollHeight - p.clientHeight - p.scrollTop); })()")
    check("画像が遅れて届いても、編集欄が最下端なら、プレビューも最下端（残り 5px 以内）", gap <= 5, True)
    print('    プレビューの残り', gap, 'px', flush=True)

    # --- 8. 編集欄に合わせているとき、利用者の操作でなく、プレビューが動かされたら、元の位置へ戻る
    js("pvUserAt = 0; cm.scrollTo(0, 0); null"); time.sleep(.6)
    js("document.getElementById('pscroll').scrollTop = 900; null"); time.sleep(.8)
    check("プレビューが、操作によらず動かされても、編集欄の位置（最上端）へ戻る", js("document.getElementById('pscroll').scrollTop") <= 20, True)

    # --- 9. 大きな窓で、編集欄の動ける幅が短い文書でも、最上端ではプレビューも最上端・最下端では最下端・途中は順に動く
    SHORT = os.path.join(tmp, 'short.md')
    body = ['# 短い文書', '']
    for n in range(3):
        body += ['あ' * 60, '', f'![図](http://127.0.0.1:{PORT}/p{n}.png?s={n})', '']
    open(SHORT, 'w', encoding='utf-8').write('\n'.join(body))
    w.resize(1900, 1380); time.sleep(1.5)
    js("cm.markClean(); doc.metaDirty = false; null")        # 「変更を保存しますか?」の確認で、止まらないようにする
    js("openPath(%s)" % json.dumps(SHORT)); time.sleep(1)
    wait("[...document.querySelectorAll('#preview img')].length === 3 && [...document.querySelectorAll('#preview img')].every(i => i.complete && i.naturalWidth > 0)", 60); time.sleep(1.0)
    for filler in range(0, 200, 4):                       # 編集欄の動ける幅が、画面の高さより、だいぶ短くなる行数を探す
        js("var NL = String.fromCharCode(10); cm.setValue(cm.getValue().split(NL + '---fill---')[0] + NL + '---fill---' + NL.repeat(%d)); null" % filler)
        time.sleep(.15)
        emax = js("cm.getScrollInfo().height - cm.getScrollInfo().clientHeight")
        if 40 < emax < 300:
            break
    print('    編集欄の動ける幅', emax, 'px', flush=True)
    js("cm.scrollTo(0, 0); null"); time.sleep(.6)
    check("動ける幅が短い文書で、編集欄が最上端のとき、プレビューも最上端（20px 以内）", js("document.getElementById('pscroll').scrollTop") <= 20, True)
    ys = []
    for k in range(0, 11):
        js("cm.scrollTo(0, %d); null" % int(emax * k / 10)); time.sleep(.3)
        ys.append(js("document.getElementById('pscroll').scrollTop"))
    check("編集欄を最上端から最下端へ動かすと、プレビューは、順に動き続ける", all(b >= a for a, b in zip(ys, ys[1:])), True)
    gap = js("(() => { const p = document.getElementById('pscroll'); return Math.round(p.scrollHeight - p.clientHeight - p.scrollTop); })()")
    check("動ける幅が短い文書で、編集欄が最下端のとき、プレビューも最下端（5px 以内）", gap <= 5, True)

    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()


def watchdog():
    """試験が止まっても、テスト用の画面を残さない（確認のダイアログなどで止まったとき）。"""
    time.sleep(300)
    print('NG 時間切れ（試験が止まったため、終了した）', flush=True)
    os._exit(1)


threading.Thread(target=watchdog, daemon=True).start()
webview.start()
