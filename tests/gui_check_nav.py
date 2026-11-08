"""戻る・進む（開いたファイルの履歴）を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_nav.py

設定の置き場所は一時フォルダーへ向ける（利用者の設定を書き換えない）。
"""
import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, '.')
os.environ['APPDATA'] = tempfile.mkdtemp(prefix='md_appdata_')
import webview
import mdeditor
import gui_nodialog  # noqa: F401  OS のダイアログを出さない（キー入力を奪うため）

tmp = tempfile.mkdtemp()
filler = "".join(f"段落{i}です。\n\n" for i in range(150))
files = {
    'a.md': "# A\n\n[Bへ](b.md)\n\n" + filler,
    'b.md': "# B\n\n[Cへ](c.md)\n\n[Aへ戻るリンク](a.md)\n\n" + filler,
    'c.md': "# C\n\n" + filler,
    'd.md': "# D\n",
}
for n, t in files.items():
    open(os.path.join(tmp, n), 'w', encoding='utf-8').write(t)
P = {n: os.path.join(tmp, n) for n in files}

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


def wait(code, timeout=12):
    t = time.time()
    while time.time() - t < timeout:
        if js(code):
            return True
        time.sleep(.2)
    return bool(js(code))


def h1():
    return js("(document.querySelector('#preview h1') || {}).textContent")


def waith(t):
    return wait("(document.querySelector('#preview h1') || {}).textContent === %s" % json.dumps(t))


def state():
    return js("[nav.list.map(e => e.path.split('\\\\').pop()).join(','), nav.idx, document.getElementById('btnBack').disabled, document.getElementById('btnFwd').disabled]")


def drive():
    time.sleep(8)
    wait("typeof nav !== 'undefined'")
    check("タイトル行に、戻る・進むのボタンがある", js("[!!document.getElementById('btnBack'), !!document.getElementById('btnFwd')]"), [True, True])
    check("最初は、どちらも押せない", js("[document.getElementById('btnBack').disabled, document.getElementById('btnFwd').disabled]"), [True, True])

    js("loadFolder(%s).then(() => openPath(%s))" % (json.dumps(tmp), json.dumps(P['a.md'])))
    check("a を開く", waith('A'), True)
    check("履歴は a だけ。戻れない・進めない", state(), ['a.md', 0, True, True])

    # リンクをたどる（a → b → c）。a では、下へ読み進めておく
    js("cm.scrollTo(0, 500); null")
    time.sleep(.3)
    top_a = js("Math.round(cm.getScrollInfo().top)")
    js("[...document.querySelectorAll('#preview a')].find(a => a.textContent === 'Bへ').click()")
    check("リンクで b に移る", waith('B'), True)
    check("履歴: a, b。戻れる", state(), ['a.md,b.md', 1, False, True])
    js("cm.scrollTo(0, 300); null")
    time.sleep(.3)
    top_b = js("Math.round(cm.getScrollInfo().top)")
    js("[...document.querySelectorAll('#preview a')].find(a => a.textContent === 'Cへ').click()")
    check("リンクで c に移る", waith('C'), True)
    check("履歴: a, b, c", state(), ['a.md,b.md,c.md', 2, False, True])
    check("戻るボタンの説明に、戻り先が出る", js("document.getElementById('btnBack').title.startsWith('戻る: b.md')"), True)

    # 戻る
    js("document.getElementById('btnBack').click()")
    check("戻る → b", waith('B'), True)
    check("b の読んでいた位置に戻る", wait("Math.abs(Math.round(cm.getScrollInfo().top) - %d) <= 3" % top_b), True)
    check("履歴の位置は b。進める", state(), ['a.md,b.md,c.md', 1, False, False])
    js("document.getElementById('btnBack').click()")
    check("戻る → a", waith('A'), True)
    check("a の読んでいた位置に戻る", wait("Math.abs(Math.round(cm.getScrollInfo().top) - %d) <= 3" % top_a), True)
    check("先頭では、戻れない", state()[2:], [True, False])
    js("document.getElementById('btnBack').click()")
    time.sleep(.4)
    check("戻れないときに押しても、何も起きない", [h1(), state()[1]], ['A', 0])

    # 進む
    js("document.getElementById('btnFwd').click()")
    check("進む → b", waith('B'), True)

    # Alt+Shift+←・Alt+Shift+→
    js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowLeft', altKey: true, shiftKey: true, bubbles: true, cancelable: true}))")
    check("Alt+Shift+← で戻る（a）", waith('A'), True)
    js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight', altKey: true, shiftKey: true, bubbles: true, cancelable: true}))")
    check("Alt+Shift+→ で進む（b）", waith('B'), True)

    # 戻ってから別のファイルを開くと、進む側は捨てる
    js("document.getElementById('btnBack').click()")
    waith('A')
    js("document.querySelector('.item[data-rel=\"d.md\"]').click()")
    check("一覧から d を開く", waith('D'), True)
    check("途中で別のファイルを開くと、「進む」側は捨てる（a, d）", state(), ['a.md,d.md', 1, False, True])

    # 同じファイルをもう一度開いても、増えない
    js("document.querySelector('.item[data-rel=\"d.md\"]').click()")
    time.sleep(.8)
    check("同じファイルをもう一度開いても、増えない", state()[0], 'a.md,d.md')

    # 消えたファイルは、履歴から外す
    js("document.getElementById('btnBack').click()")
    waith('A')
    js("document.querySelector('.item[data-rel=\"b.md\"]').click()")
    waith('B')
    js("document.getElementById('btnBack').click()")
    waith('A')
    os.remove(P['b.md'])
    js("document.getElementById('btnFwd').click()")
    check("消えたファイルへは進めず、メッセージが出る", wait("document.getElementById('msg').textContent.length > 0"), True)
    check("消えたファイルは、履歴から外れる", state()[0], 'a.md')
    check("表示は、そのまま（a）", h1(), 'A')

    # 「無題」を挟む: 新規に作ると、履歴には入れず、「戻る」で直前の文書へ戻れる
    js("document.getElementById('bNew').click()")
    time.sleep(.6)
    check("新規（無題）では、戻るが使え、進むは使えない", state()[2:], [False, True])
    js("document.getElementById('btnBack').click()")
    check("無題から戻ると、直前の文書", waith('A'), True)
    check("履歴は、そのまま（a だけ）", state()[:2], ['a.md', 0])

    # 保存していない変更があると、移る前に確認する（取りやめると、移らない）
    js("cm.replaceRange('追記\\n', {line: 0, ch: 0}); null")
    js("window._ask = ask; ask = async () => 2; null")                       # 確認で「キャンセル」
    js("document.querySelector('.item[data-rel=\"d.md\"]').click()")
    time.sleep(.8)
    check("確認で取りやめると、移動しない（編集中のまま、履歴も変わらない）", [js("cm.getValue().startsWith('追記')"), state()[:2]], [True, ['a.md', 0]])
    js("ask = window._ask; cm.undo(); null")

    # 別名で保存すると、履歴の項目も新しい名前になる
    renamed = os.path.join(tmp, 'renamed.md')
    js("saveTo(%s, null)" % json.dumps(renamed))
    time.sleep(1.0)
    check("別名で保存すると、履歴の項目も新しい名前になる", state()[:2], ['renamed.md', 0])

    print("RESULT", sum(results), "/", len(results), flush=True)
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
