"""左の一覧の階層表示（サブフォルダの開閉）を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_tree.py

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
for rel in ['top.md', 'A/a1.md', 'A/a2.md', 'A/B/b1.md', 'A/B/C/c1.md', 'D/d1.md', 'Z.md']:
    p = os.path.join(tmp, *rel.split('/'))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'w', encoding='utf-8').write('# ' + rel + '\n')

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


ROWS = "[...document.querySelectorAll('#list > div')].map(r => r.classList.contains('dirrow') ? (r.querySelector('.chev').textContent + r.querySelector('.dname').textContent.replace('📁 ', '') + '(' + r.querySelector('.dcnt').textContent + ')') : r.textContent.trim())"


def rows():
    return js(ROWS)


def click_dir(path):
    js("document.querySelector('.dirrow[data-dir=%s]').click()" % json.dumps(path))
    time.sleep(.2)


def drive():
    time.sleep(8)
    wait("typeof tree !== 'undefined'")
    js("loadFolder(%s)" % json.dumps(tmp))
    wait("document.querySelectorAll('#list > div').length > 0")
    check("初めは、直下のフォルダだけ開く（深いものは閉じる）。フォルダが先、ファイルが後",
          rows(), ['▾A(4)', '▸B(2)', 'a1.md', 'a2.md', '▾D(1)', 'd1.md', 'Z.md', 'top.md'])
    check("フォルダ行に、中のファイルの数（下の階層を含む）", js("document.querySelector('.dirrow[data-dir=\"A\"] .dcnt').textContent"), '4')
    check("「すべて開く・閉じる」のボタンが出る", js("document.getElementById('treeBtns').hidden"), False)
    check("階層が深いほど、字下げが大きい", js("(() => { const a = document.querySelector('.dirrow[data-dir=\"A\"]'), b = document.querySelector('.dirrow[data-dir=\"A/B\"]'); return parseInt(b.style.paddingLeft) > parseInt(a.style.paddingLeft) })()"), True)

    click_dir('A/B')
    check("閉じているフォルダを押すと、開く", rows(), ['▾A(4)', '▾B(2)', '▸C(1)', 'b1.md', 'a1.md', 'a2.md', '▾D(1)', 'd1.md', 'Z.md', 'top.md'])
    click_dir('A')
    check("開いているフォルダを押すと、閉じる（中の階層も隠れる）", rows(), ['▸A(4)', '▾D(1)', 'd1.md', 'Z.md', 'top.md'])
    check("aria-expanded が付く", js("document.querySelector('.dirrow[data-dir=\"A\"]').getAttribute('aria-expanded')"), 'false')

    js("document.getElementById('treeOpen').click()")
    check("「すべて開く」で、全部のフォルダが開く", rows(), ['▾A(4)', '▾B(2)', '▾C(1)', 'c1.md', 'b1.md', 'a1.md', 'a2.md', '▾D(1)', 'd1.md', 'Z.md', 'top.md'])
    js("document.getElementById('treeClose').click()")
    check("「すべて閉じる」で、全部のフォルダが閉じる", rows(), ['▸A(4)', '▸D(1)', 'Z.md', 'top.md'])

    # 文書を開くと、そのフォルダまで自動で開く
    js("openPath(%s)" % json.dumps(os.path.join(tmp, 'A', 'B', 'C', 'c1.md')))
    check("深いところの文書を開くと、そこまでのフォルダが開く", wait("document.querySelector('.item.sel') !== null"), True)
    check("開いた文書が選ばれている", js("document.querySelector('.item.sel').textContent.trim()"), 'c1.md')
    click_dir('A/B/C')
    check("開いた文書のあるフォルダも、自分で閉じられる（また開き直されない）", js("document.querySelector('.item.sel')"), None)
    js("renderList()")
    check("描き直しても、閉じたまま", js("document.querySelector('.item.sel')"), None)

    # 絞り込みは、これまでどおり平ら
    js("const f = document.getElementById('filter'); f.value = 'b1'; f.dispatchEvent(new Event('input'))")
    time.sleep(.3)
    check("絞り込み中は、平らに並べ、フォルダ名を添える", js("[...document.querySelectorAll('#list > div')].map(r => r.className + ':' + r.textContent.trim())"), ['item:b1.mdA/B'])
    check("絞り込み中は、開閉ボタンを隠す", js("document.getElementById('treeBtns').hidden"), True)
    js("const f = document.getElementById('filter'); f.value = ''; f.dispatchEvent(new Event('input'))")
    time.sleep(.3)
    check("絞り込みを消すと、階層表示に戻り、開閉の状態も保たれる", js(ROWS)[:1], ['▾A(4)'])

    # ファイルの選択
    js("document.querySelector('.item[data-rel=\"top.md\"]').click()")
    check("ファイルを押すと開く", wait("document.querySelector('#preview h1') && document.querySelector('#preview h1').textContent === 'top.md'"), True)

    print("RESULT", sum(results), "/", len(results), flush=True)
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
