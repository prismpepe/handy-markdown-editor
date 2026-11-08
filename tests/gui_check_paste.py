"""クリップボードの画像の貼り付け（Ctrl+V・貼り付けボタン）を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_paste.py

利用者のクリップボードは触らない（画像を読む部分を、試験用の関数に差し替える）。設定の置き場所は一時フォルダーへ向ける。
"""
import json
import os
import struct
import sys
import tempfile
import threading
import time

sys.path.insert(0, '.')
os.environ['APPDATA'] = tempfile.mkdtemp(prefix='md_appdata_')
import webview
import mdeditor
import gui_nodialog  # noqa: F401  OS のダイアログを出さない（キー入力を奪うため）
import clipboard
import pasteimg

# 2x2 の画像（赤・緑・青・白）を PNG にして、クリップボードの画像として返す
dib = struct.pack("<IiiHHIIiiII", 40, 2, 2, 1, 24, 0, 16, 0, 0, 0, 0) \
    + bytes([255, 0, 0, 255, 255, 255, 0, 0] + [0, 0, 255, 0, 255, 0, 0, 0])      # 下の行（青・白）→ 上の行（赤・緑）の順
PNG = pasteimg.dib_to_png(dib)
clip = {'png': PNG}
clipboard.get_image_png = lambda: clip['png']

work = tempfile.mkdtemp(prefix='md_work_')
doc = os.path.join(work, 'note.md')
open(doc, 'w', encoding='utf-8').write('# メモ\n\n')

api = mdeditor.Api(None)
api.clipboard_get = lambda: None                      # 文字は無い（貼り付けボタンの試験用）
w = webview.create_window('t', html=mdeditor.build_html(), js_api=api, width=1400, height=900, x=20, y=20)
api._window = w
results = []


def js(code):
    return w.evaluate_js(code)


def check(name, got, want):
    ok = got == want
    results.append(ok)
    print(('OK ' if ok else 'NG ') + name + ('' if ok else f'\n    実際: {got!r}\n    期待: {want!r}'), flush=True)


def wait(code, timeout=15):
    t = time.time()
    while time.time() - t < timeout:
        if js(code):
            return True
        time.sleep(.2)
    return bool(js(code))


def paste_event(types):
    """貼り付けのイベントを、編集欄へ送る。types: 'image'（画像だけ）/ 'both'（文字と画像）/ 'text'（文字だけ）。"""
    code = """(() => {
      const dt = new DataTransfer();
      if (%s) dt.items.add(new File([new Uint8Array([1, 2, 3])], 'a.png', { type: 'image/png' }));
      if (%s) dt.setData('text/plain', 'ABC');
      const ev = new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true });
      cm.getInputField().dispatchEvent(ev);
      return ev.defaultPrevented;
    })()""" % ('true' if types in ('image', 'both') else 'false', 'true' if types in ('text', 'both') else 'false')
    return js(code)


def images_dir():
    d = os.path.join(work, 'images')
    return sorted(os.listdir(d)) if os.path.isdir(d) else []


def drive():
    time.sleep(8)
    wait("typeof pasteImage === 'function'")

    # --- 保存していない文書: 画像を置く場所が決まらない。確認が出て、取りやめると何も起きない
    js("window._ask = ask; window._asked = []; ask = async (t, x, b) => { window._asked.push(t); return window._answer; }; window._answer = 1; null")
    check("画像だけのとき、貼り付けは、画像として扱う（既定の貼り付けを止める）", paste_event('image'), True)
    time.sleep(.8)
    check("未保存の文書では、先に保存するか尋ねる", js("window._asked"), ['画像を貼り付けます'])
    check("取りやめると、文書は変わらない", js("cm.getValue()"), '')
    check("画像ファイルも、作られない", images_dir(), [])

    # --- 保存してから貼り付ける
    js("window._answer = 0; window.pickCalls = 0; null")
    api.pick_save = lambda *a, **k: (setattr(api, '_picked', True) or doc)
    paste_event('image')
    check("「保存してから貼り付ける」で、文書が保存される", wait("doc.path !== null"), True)
    check("保存先が、選んだ場所", js("doc.path"), doc)
    check("画像が、文書のあるフォルダーの images に保存される", wait("true") and len(images_dir()) == 1 and images_dir()[0].startswith('image-') and images_dir()[0].endswith('.png'), True)
    name = images_dir()[0]
    check("保存された画像は、貼り付けた画像と同じ", open(os.path.join(work, 'images', name), 'rb').read(), PNG)
    check("文書に、画像へのリンクが入る", wait("cm.getValue().includes('![画像](images/%s)')" % name), True)
    check("「画像」の部分が選ばれている（そのまま打ち替えられる）", js("cm.getSelection()"), '画像')
    check("プレビューに、画像が出る", wait("(() => { const i = document.querySelector('#preview img'); return !!i && i.complete && i.naturalWidth === 2 })()"), True)
    check("画面に、知らせが出る", js("document.getElementById('smsg').textContent.includes('画像を保存して貼り付けました')"), True)

    # --- 保存済みの文書: 確認なしで、すぐ貼り付く
    js("window._asked = []; cm.setCursor({line: 2, ch: 0}); null")
    time.sleep(1.1)                                      # 同じ秒に作る別のファイルも、上書きされない
    paste_event('image')
    check("2枚目も、貼り付く（名前が重ならない）", wait("true") and (time.sleep(.8) or len(images_dir())), 2)
    check("保存済みの文書では、確認を出さない", js("window._asked"), [])
    check("リンクが2つになる", js("(cm.getValue().match(/!\\[画像\\]\\(images\\//g) || []).length"), 2)

    # --- 文字もあるとき（Excel のセルなど）は、これまでどおり文字を貼り付ける
    js("window._calls = 0; window._orig = pasteImage; pasteImage = async () => { window._calls++; return true; }; null")
    js("cm.setValue(''); null")
    paste_event('both')
    time.sleep(.4)
    check("文字と画像の両方があるときは、文字が貼り付く（Excel のセルなど）", js("cm.getValue()"), 'ABC')
    paste_event('text')
    time.sleep(.4)
    check("文字だけのときも、文字が貼り付く", js("cm.getValue()"), 'ABCABC')
    check("この2回では、画像の貼り付けは、呼ばれていない", js("window._calls"), 0)
    check("画像だけのときは、呼ばれる", (paste_event('image'), time.sleep(.3), js("window._calls"))[2], 1)
    js("pasteImage = window._orig; null")

    # --- 貼り付けボタン（文字が無く、画像があるとき）
    before = len(images_dir())
    js("document.querySelector('#fmt [data-e=paste]').click()")
    time.sleep(1.2)
    check("貼り付けボタンでも、画像が貼り付く", len(images_dir()), before + 1)

    # --- 画像が無いとき
    clip['png'] = None
    js("window._msg = ''; null")
    js("document.querySelector('#fmt [data-e=paste]').click()")
    check("文字も画像も無いときは、知らせる", wait("document.getElementById('smsg').textContent.includes('貼り付けられる文字・画像がありません')"), True)
    clip['png'] = PNG

    # --- 読み取り専用では、貼り付けない
    js("doc.readonly = true; null")
    n = len(images_dir())
    check("読み取り専用では、貼り付けのイベントを止めない（何もしない）", paste_event('image'), False)
    time.sleep(.5)
    check("画像も、増えない", len(images_dir()), n)
    js("doc.readonly = false; null")

    # --- 取り消し
    js("cm.undo(); null")
    check("Ctrl+Z で、リンクの挿入を取り消せる", js("(cm.getValue().match(/!\\[画像\\]\\(images\\//g) || []).length") < 3, True)

    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
