"""複数のウィンドウで使うときの安全策と、新しいウィンドウで開く入口を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_multiwin.py

別のウィンドウは、実際の別プロセスを「持ち主」にして再現する。新しいウィンドウの起動は、実際には行わず、呼ばれた内容を記録する。
設定の置き場所は一時フォルダーへ向ける（利用者の設定を書き換えない）。
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, '.')
os.environ['APPDATA'] = tempfile.mkdtemp(prefix='md_appdata_')
import webview
import mdeditor
import gui_nodialog  # noqa: F401  OS のダイアログを出さない（キー入力を奪うため）
import multiwin
import openlock

launched = []
multiwin.launch_self = lambda args: launched.append(list(args)) or True

tmp = tempfile.mkdtemp(prefix='md_work_')
A, B = os.path.join(tmp, 'a.md'), os.path.join(tmp, 'b.md')
open(A, 'w', encoding='utf-8').write('# A\n\n[Bへ](b.md)\n')
open(B, 'w', encoding='utf-8').write('# B\n')

# 別のウィンドウ（別プロセス）が、a.md を開いている
other = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
pid, created = multiwin.process_stamp(other.pid)
os.makedirs(mdeditor.locks_root(), exist_ok=True)
json.dump({'path': A, 'owner': [pid, created], 'since': '2026-11-08T10:00:00'},
          open(os.path.join(mdeditor.locks_root(), openlock.lock_name(A)), 'w', encoding='utf-8'))

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


def wait(code, timeout=15):
    t = time.time()
    while time.time() - t < timeout:
        if js(code):
            return True
        time.sleep(.2)
    return bool(js(code))


def answer(i):
    js("window._asked = []; window._ask = window._ask || ask; ask = async (t, x, b) => { window._asked.push(t); return %d; }; null" % i)


def open_path(p):
    js("window._r = undefined; openPath(%s).then(v => { window._r = v === undefined ? 'undefined' : v; })" % json.dumps(p))
    wait("window._r !== undefined")
    return js("window._r")


def holder(p):
    return openlock.holder(mdeditor.locks_root(), p)


def drive():
    time.sleep(8)
    wait("typeof openInNewWindow === 'function'")
    js("loadFolder(%s).then(() => null)" % json.dumps(tmp))
    wait("document.querySelectorAll('#list .item').length === 2")

    # --- 別のウィンドウで開いているファイル
    answer(2)                                                   # キャンセル
    check("別のウィンドウで開かれているファイルを開こうとすると、先に知らせる", (open_path(A), js("window._asked"))[1], ['このファイルは、別のウィンドウで開かれています'])
    check("キャンセルすると、開かない", [js("doc.path"), open_path.__name__ and js("cm.getValue()")], [None, ''])
    check("キャンセルしても、印は変わらない（別のウィンドウの持ち主のまま）", holder(A)['pid'], other.pid)

    answer(0)                                                   # 読み取り専用で開く
    open_path(A)
    check("「読み取り専用で開く」で、読み取り専用で開く", [js("doc.path"), js("doc.readonly"), js("cm.getOption('readOnly')")], [A, True, True])
    check("そのことを、画面に出す", js("document.getElementById('smsg').textContent.includes('読み取り専用で開きました')"), True)
    check("読み取り専用で開いたものは、印を置かない（別のウィンドウの印のまま）", holder(A)['pid'], other.pid)
    js("doc.readonly = false; null")

    answer(1)                                                   # このまま開く
    open_path(A)
    check("「このまま開く」で、編集できる状態で開く", [js("doc.path"), js("doc.readonly")], [A, False])
    check("承知して開いたので、このウィンドウの印になる（警告の対象でなくなる）", holder(A), None)
    check("開いた文書の中身", js("cm.getValue()").startswith('# A'), True)

    # --- 印のないファイルは、そのまま開く。開いていた文書の印は、外れる
    answer(2)
    check("印のないファイルは、確認なしで開く", (open_path(B), js("window._asked"))[1], [])
    check("b.md を開いた", js("doc.path"), B)
    locks = sorted(os.listdir(mdeditor.locks_root()))
    check("a.md の印は外れ、b.md の印が置かれる", locks, [openlock.lock_name(B)])

    # --- 新規（無題）にすると、印を外す
    js("document.getElementById('bNew').click()")
    time.sleep(.8)
    check("新規にすると、開いていたファイルの印が外れる", os.listdir(mdeditor.locks_root()), [])

    # --- 別名で保存すると、新しい名前の印になる
    C = os.path.join(tmp, 'c.md')
    api.pick_save = lambda *a, **k: C
    js("cm.setValue('# C'); null")
    js("saveAs()")
    wait("doc.path !== null")
    time.sleep(.8)
    check("名前を付けて保存すると、その名前の印になる", os.listdir(mdeditor.locks_root()), [openlock.lock_name(C)])

    # --- 閉じるときに、印を全部外す
    api.release_all_claims()
    check("閉じるとき、このウィンドウの印を、全部外す", os.listdir(mdeditor.locks_root()), [])

    # --- 新しいウィンドウで開く: 一覧の Ctrl+クリック・中クリック・右クリック
    js("window.__open = openPath; openPath = async () => { window._plain = (window._plain || 0) + 1; return true; }; null")
    js("document.querySelector('#list .item[data-rel=\"b.md\"]').dispatchEvent(new MouseEvent('click', {ctrlKey: true, bubbles: true, cancelable: true}))")
    time.sleep(.5)
    check("一覧の Ctrl+クリックで、新しいウィンドウを起動する（このウィンドウの文書は、そのまま）", [launched[-1:], js("window._plain || 0")], [[[B]], 0])
    js("document.querySelector('#list .item[data-rel=\"a.md\"]').dispatchEvent(new MouseEvent('auxclick', {button: 1, bubbles: true, cancelable: true}))")
    time.sleep(.5)
    check("中クリックでも、新しいウィンドウ", launched[-1], [A])
    js("document.querySelector('#list .item[data-rel=\"b.md\"]').dispatchEvent(new MouseEvent('contextmenu', {clientX: 60, clientY: 200, bubbles: true, cancelable: true}))")
    check("一覧のファイルを右クリックすると、メニューが出る", wait("!document.getElementById('ctx').hidden"), True)
    check("メニューの内容", js("[...document.querySelectorAll('#ctx .citem')].map(b => b.firstChild.textContent)"), ['開く', '新しいウィンドウで開く'])
    js("[...document.querySelectorAll('#ctx .citem')].find(b => b.firstChild.textContent === '新しいウィンドウで開く').click()")
    time.sleep(.5)
    check("「新しいウィンドウで開く」で起動する", launched[-1], [B])
    js("document.querySelector('#list .item[data-rel=\"a.md\"]').click()")
    time.sleep(.4)
    check("普通のクリックは、これまでどおり、このウィンドウで開く", js("window._plain"), 1)
    js("openPath = window.__open; null")

    # --- プレビューのリンクの Ctrl+クリック
    set_doc = "cm.setValue('[Bへ](b.md)'); doc.path = %s; null" % json.dumps(A)
    js(set_doc)
    wait("document.querySelector('#preview a') !== null")
    n = len(launched)
    js("document.querySelector('#preview a').dispatchEvent(new MouseEvent('click', {ctrlKey: true, bubbles: true, cancelable: true}))")
    time.sleep(.8)
    check("リンクの Ctrl+クリックで、新しいウィンドウ", [len(launched), launched[-1]], [n + 1, [B]])
    check("このウィンドウの文書は、そのまま", js("doc.path"), A)

    # --- Ctrl+Shift+N
    js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'N', ctrlKey: true, shiftKey: true, bubbles: true, cancelable: true}))")
    time.sleep(.5)
    check("Ctrl+Shift+N で、空の新しいウィンドウ", launched[-1], [])
    check("Ctrl+N（新規）とは、別の動作", js("doc.path"), A)

    other.kill()
    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
