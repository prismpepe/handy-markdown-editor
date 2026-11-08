"""検査の自動修正（直す・すべて直す・前後の確認・取り消し）を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_lintfix.py

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

api = mdeditor.Api(None)
w = webview.create_window('t', html=mdeditor.build_html(), js_api=api, width=1400, height=900, x=20, y=20)
api._window = w
results = []

TEXT = "#題名\n本文  \n\n\n\n### 飛んだ\n中身\n\n[空]()\n"


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


def set_text(text):
    js("cm.setValue(%s); cm.clearHistory(); null" % json.dumps(text))


def val():
    return js("cm.getValue()")


def rules():
    return js("[...document.querySelectorAll('#lintList .lrow')].map(r => r.querySelector('.rid').textContent + (r.querySelector('.lfix') ? '+' : ''))")


def key(k):
    js("document.dispatchEvent(new KeyboardEvent('keydown', {key: %s, bubbles: true, cancelable: true}))" % json.dumps(k))


def drive():
    time.sleep(8)
    wait("typeof lint !== 'undefined' && lint.rules.length > 0")
    js("document.getElementById('lintBtn').click()")
    set_text(TEXT)
    check("検査が走る", wait("document.querySelectorAll('#lintList .lrow').length >= 3"), True)
    r = rules()
    check("直せる指摘には「直す」が付く（MD018）", 'MD018+' in r, True)
    check("直せない指摘には付かない（MD042）", 'MD042' in r, True)
    check("「すべて直す」が出て、件数が付く", js("document.getElementById('lintFixAll').textContent"), 'すべて直す（%d）' % sum(1 for x in r if x.endswith('+')))

    # --- 1件を直す: 確認が出る
    js("[...document.querySelectorAll('#lintList .lrow')].find(x => x.querySelector('.rid').textContent === 'MD018').querySelector('.lfix').click()")
    check("確認のダイアログが出る", wait("!document.getElementById('fxveil').hidden"), True)
    check("直す前と直したあとが並ぶ", js("[document.querySelector('#fxList .fb').textContent, document.querySelector('#fxList .fa').textContent]"), ['#題名', '# 題名'])
    check("ここまでは、文書は変わっていない", val(), TEXT)
    key('Escape')
    time.sleep(.3)
    check("Esc で取りやめると、文書は変わらない", [js("document.getElementById('fxveil').hidden"), val()], [True, TEXT])
    js("[...document.querySelectorAll('#lintList .lrow')].find(x => x.querySelector('.rid').textContent === 'MD018').querySelector('.lfix').click()")
    wait("!document.getElementById('fxveil').hidden")
    js("document.getElementById('fxOk').click()")
    check("「直す」で、その1か所だけ直る", wait("cm.getValue().startsWith('# 題名\\n')"), True)
    check("ほかの行は変わっていない", val(), TEXT.replace('#題名', '# 題名'))
    check("Ctrl+Z で元に戻る", (js("cm.undo(); null"), val())[1], TEXT)

    # --- すべて直す: 1回の取り消しで、全部が戻る
    wait("lint.gen === cm.changeGeneration() && !document.getElementById('lintFixAll').hidden")      # 取り消しのあとの、自動検査を待つ
    js("document.getElementById('lintFixAll').click()")
    check("「すべて直す」で、確認が出る", wait("!document.getElementById('fxveil').hidden"), True)
    n = js("document.querySelectorAll('#fxList .fr').length")
    check("確認の行数が、件数と合う", js("document.getElementById('fxTitle').textContent.includes('%d か所')" % n), True)
    js("document.getElementById('fxOk').click()")
    check("全部が直る（段飛び・行末の空白・続く空行・見出しの前後の空行）",
          wait("cm.getValue() === %s" % json.dumps("# 題名\n本文\n\n### 飛んだ\n\n中身\n\n[空]()\n")), True)
    wait("[...document.querySelectorAll('#lintList .rid')].every(r => r.textContent !== 'MD009')")
    check("直したあと、検査し直される（#題名 が見出しになったので、その段・空行の指摘が新しく出る）", sorted(x for x in rules() if x.endswith('+')), ['MD001+', 'MD022+'])
    check("新しく直せる指摘が出たら、もう一度押すよう案内する", js("document.getElementById('smsg').textContent.includes('もう一度')"), True)
    check("直せない指摘（MD042）は、そのまま残る", 'MD042' in rules(), True)
    js("cm.undo(); null")
    check("Ctrl+Z 1回で、全部が元に戻る", val(), TEXT)

    # もう一度すべて直す → 2回目の検査で出た分（見出しになった行の段飛びなど）も直す
    wait("lint.gen === cm.changeGeneration() && !document.getElementById('lintFixAll').hidden")
    js("document.getElementById('lintFixAll').click()")
    wait("!document.getElementById('fxveil').hidden")
    js("document.getElementById('fxOk').click()")
    wait("cm.getValue().startsWith('# 題名')")
    time.sleep(1.2)
    if js("document.getElementById('lintFixAll').hidden") is False:
        js("document.getElementById('lintFixAll').click()")
        wait("!document.getElementById('fxveil').hidden")
        js("document.getElementById('fxOk').click()")
        time.sleep(1.0)
    check("数回で、直せる指摘がなくなる", wait("document.getElementById('lintFixAll').hidden"), True)
    check("段飛びが直っている（### → ##）", '## 飛んだ' in val(), True)

    # --- 検査のあとで文書が変わったら、直さずに検査し直す
    set_text("#見出し\n")
    wait("document.querySelectorAll('#lintList .lfix').length === 1")
    js("cm.replaceRange('追記', {line: 1, ch: 0}); document.querySelector('#lintList .lfix').click()")
    time.sleep(.8)
    check("検査のあとで文書が変わっていると、確認を出さない", js("document.getElementById('fxveil').hidden"), True)
    check("検査し直したと知らせる", js("document.getElementById('smsg').textContent.includes('検査し直しました')"), True)
    check("文書は書き換わらない", val(), "#見出し\n追記")

    # --- 読み取り専用では、直せない
    set_text("#見出し\n")
    wait("document.querySelectorAll('#lintList .lfix').length === 1")
    js("doc.readonly = true; renderLint(); null")
    check("読み取り専用では、「直す」が出ない", js("document.querySelectorAll('#lintList .lfix').length"), 0)
    check("「すべて直す」も出ない", js("document.getElementById('lintFixAll').hidden"), True)
    js("doc.readonly = false; null")

    # --- ダイアログ中は、ほかのショートカットを受けない
    set_text("#見出し\n")
    wait("document.querySelectorAll('#lintList .lfix').length === 1")
    js("document.querySelector('#lintList .lfix').click()")
    wait("!document.getElementById('fxveil').hidden")
    js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'n', ctrlKey: true, bubbles: true, cancelable: true}))")
    time.sleep(.3)
    check("ダイアログが開いている間は、Ctrl+N を受けない", val(), "#見出し\n")
    key('Escape')

    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
