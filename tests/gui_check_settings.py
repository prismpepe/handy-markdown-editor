"""文書フォルダーに連動する設定（定型文・テンプレートの、文書フォルダーへの書き出し・編集・削除）を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_settings.py

設定の置き場所は一時フォルダーへ向ける（利用者の設定を書き換えない）。ごみ箱へは、実際には移さない（試験用の関数に差し替える）。
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
import recycle

trashed = []


def fake_trash(path):
    trashed.append(path)
    os.remove(path)
    return True


recycle.move_to_trash = fake_trash

proj = tempfile.mkdtemp(prefix='md_proj_')
os.makedirs(os.path.join(proj, 'docs'))
A = os.path.join(proj, 'docs', 'a.md')
open(A, 'w', encoding='utf-8').write('# メモ\n')
SD = os.path.join(proj, 'docs', '.markdown-editor')       # 設定は、文書のあるフォルダー（docs）に作られる

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


def menu():
    js("document.getElementById('fSnip').click()")
    wait("!document.getElementById('ctx').hidden")
    return js("[...document.querySelectorAll('#ctx .citem')].map(b => (b.disabled ? '×' : '') + b.firstChild.textContent)")


def click_menu(label):
    js("[...document.querySelectorAll('#ctx .citem')].find(b => b.firstChild.textContent === %s).click()" % json.dumps(label))


def right_click_menu(label):
    js("[...document.querySelectorAll('#ctx .citem')].find(b => b.firstChild.textContent === %s).dispatchEvent(new MouseEvent('contextmenu', {clientX: 300, clientY: 300, bubbles: true, cancelable: true}))" % json.dumps(label))
    time.sleep(.4)
    return js("[...document.querySelectorAll('#ctx .citem')].map(b => (b.disabled ? '×' : '') + b.firstChild.textContent)")


def drive():
    time.sleep(8)
    wait("typeof createSettingsHere === 'function'")
    js("window._ask = ask; window._asked = []; window._ans = 0; ask = async (t, x, b, ...r) => { if (/設定を作り|削除/.test(t)) { window._asked.push(t); return window._ans; } return window._ask(t, x, b, ...r); }; null")
    js("loadFolder(%s).then(() => openPath(%s))" % (json.dumps(os.path.join(proj, 'docs')), json.dumps(A)))
    wait("doc.path === %s" % json.dumps(A))
    time.sleep(.8)

    # --- 設定が無いとき: 組み込み（メモリの既定値）
    m = menu()
    check("設定が無いと、組み込みだけが並ぶ（見出しは「組み込み」）", [x for x in m if x.startswith('×—')], ['×— 組み込み —'])
    js("document.getElementById('ctx').hidden = true; null")
    check("文書フォルダーに、設定のフォルダーは無い", os.path.exists(SD), False)

    # --- 設定を作る（確認 → 書き出し）
    js("window._ans = 1; null")                                           # キャンセル
    menu(); click_menu('この文書フォルダー用の設定を作る…')
    time.sleep(.8)
    check("確認で取りやめると、何も作らない", [js("window._asked"), os.path.exists(SD)], [['この文書フォルダー用の設定を作りますか？'], False])
    js("window._ans = 0; window._asked = []; null")
    menu(); click_menu('この文書フォルダー用の設定を作る…')
    t0 = time.time()
    while time.time() - t0 < 10 and not os.path.isdir(os.path.join(SD, 'snippets')):
        time.sleep(.3)
    print('   画面の知らせ:', js("document.getElementById('smsg') ? document.getElementById('smsg').textContent : null"), '/ 確認:', js("window._asked"), flush=True)
    check("「作る」で、文書フォルダーの .markdown-editor が作られる", os.path.isdir(os.path.join(SD, 'snippets')), True)
    check("定型文 8 つと、テンプレート 4 つが、ファイルになる", [len(os.listdir(os.path.join(SD, 'snippets'))), len(os.listdir(os.path.join(SD, 'templates')))], [8, 4])
    cfg = json.load(open(os.path.join(SD, 'settings.json'), encoding='utf-8'))
    check("settings.json は、組み込みを使わない（inherit: false）設定", cfg, {"snippets": {"inherit": False}, "templates": {"inherit": False}})
    check("知らせが出る（保存先と件数）", wait("document.getElementById('smsg').textContent.includes('設定を作りました')"), True)

    # --- 設定のファイルが、エディタの一覧に出る（編集できる）
    check("左の一覧に、.markdown-editor のフォルダーが出る", wait("[...document.querySelectorAll('#list .dirrow')].some(d => d.dataset.dir === '.markdown-editor')"), True)
    js("document.querySelector('.dirrow[data-dir=\".markdown-editor\"]').click()")
    js("document.getElementById('treeOpen').click()")
    check("その中の定型文・テンプレートの .md が、一覧に並ぶ", wait("document.querySelectorAll('#list .item[data-rel^=\".markdown-editor/\"]').length === 12"), True)

    # --- 作ったあとは、そのフォルダーのファイルだけが使われる
    m = menu()
    check("メニューの見出しは、「この文書フォルダーの設定」だけ（組み込みは出ない）", [x for x in m if x.startswith('×—')], ['×— この文書フォルダーの設定 —'])
    check("8 つの定型文", sum(1 for x in m if not x.startswith('×') and x not in ('この文書フォルダー用の設定を作る…', '自分用の定型文の場所を開く…')), 8)

    # --- 右クリック: 削除（ごみ箱へ）
    sub = right_click_menu('日時')
    check("項目を右クリックすると、編集・削除が出る", sub[:2], ['編集（このエディタで開く）', '削除（ごみ箱へ）'])
    js("window._asked = []; null")
    click_menu('削除（ごみ箱へ）')
    check("削除は、確認を出す", wait("window._asked.length === 1"), True)
    check("確認すると、ごみ箱へ移す（試験では、関数に差し替え）", wait("true") and (time.sleep(1.0) or [os.path.basename(p) for p in trashed]), ['日時.md'])
    m = menu()
    check("消した項目は、メニューから消える（組み込みの日時は、戻らない）", '日時' in m, False)
    js("document.getElementById('ctx').hidden = true; null")

    # --- 右クリック: 編集（このエディタで開く）
    js("window._asked = []; null")
    menu(); right_click_menu('リンク'); click_menu('編集（このエディタで開く）')
    check("「編集」で、その定型文のファイルが、エディタで開く", wait("doc.path === %s" % json.dumps(os.path.join(SD, 'snippets', 'リンク.md'))), True)
    check("中身は、定型文の本文（欄の記法のまま）", js("cm.getValue()"), '[{{選択:表示する文字}}]({{URL}}){{カーソル}}')
    # 書き換えて保存 → 使われる
    js("cm.setValue('[[{{選択:書き換えた}}]]({{URL}})'); null")
    js("saveTo(doc.path, doc.stamp)")
    check("保存できる", wait("!isDirty()"), True)
    js("openPath(%s)" % json.dumps(A))
    wait("doc.path === %s" % json.dumps(A))
    time.sleep(.5)
    js("cm.setValue(''); null")
    menu(); click_menu('リンク')
    wait("document.querySelector('#dExtra input')")
    print('   挿入の様子:', js("[document.getElementById('veil').hidden, document.getElementById('dlg') && document.getElementById('dlg').innerText.slice(0,80), cm.getValue(), doc.path]"), flush=True)
    js("document.querySelector('#dExtra input').value = 'U'; document.querySelector('#dBtns .primary').click()")
    check("書き換えた定型文が、挿入に使われる", wait("cm.getValue() === '[[書き換えた]](U)'"), True)

    # --- テンプレートのダイアログも、同じ層を使う
    js("document.getElementById('bTemplate').click()")
    wait("!document.getElementById('mveil').hidden && document.getElementById('mList').options.length > 0")
    time.sleep(.6)
    check("テンプレートの一覧は、文書フォルダーの設定の 4 つだけ", js("[...document.querySelectorAll('#mList optgroup')].map(g => g.label + ':' + g.children.length)"), ['この文書フォルダーの設定:4'])
    js("document.getElementById('mClose').click()")

    # --- 設定を消せば、組み込みの既定値（メモリ）に戻る
    import shutil
    shutil.rmtree(SD)
    js("openPath(%s)" % json.dumps(A))
    wait("doc.path === %s" % json.dumps(A))
    js("loadSnippets()")
    time.sleep(1.2)
    m = menu()
    check("設定のフォルダーを消すと、組み込み（メモリの既定値）に戻る", [x for x in m if x.startswith('×—')], ['×— 組み込み —'])
    js("document.getElementById('ctx').hidden = true; null")

    # --- 組み込みの右クリック: 編集は、設定を作ってから開く。削除は、できない
    js("saveTo(doc.path, doc.stamp)")                       # 編集中の文書があると、開く前に確認が出る。保存しておく
    wait("!isDirty()")
    menu()
    sub = right_click_menu('日時')
    check("組み込みの右クリック: 編集はできるが、削除はできない", sub[:2], ['編集…（設定を作って、開く）', '×削除（ごみ箱へ）'])
    js("window._asked = []; null")
    click_menu('編集…（設定を作って、開く）')
    check("組み込みを編集すると、設定を作って、そのファイルを開く", wait("doc.path === %s" % json.dumps(os.path.join(SD, 'snippets', '日時.md'))), True)
    check("確認が、先に出る", js("window._asked[0]"), 'この文書フォルダー用の設定を作りますか？')

    # --- 保存していない無題の文書で、フォルダーも開いていないとき
    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
