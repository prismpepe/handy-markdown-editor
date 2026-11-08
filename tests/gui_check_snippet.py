"""スニペット（定型文の挿入）を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_snippet.py

設定の置き場所は一時フォルダーへ向ける（利用者の設定を書き換えない）。エクスプローラーは、実際には開かない。
"""
import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, '.')
os.environ['APPDATA'] = tempfile.mkdtemp(prefix='md_appdata_')
os.startfile = lambda p: None                      # 「定型文の場所を開く」で、エクスプローラーを開かない
import webview
import mdeditor
import gui_nodialog  # noqa: F401  OS のダイアログを出さない（キー入力を奪うため）

api = mdeditor.Api(None)
os.makedirs(api.snippet_folder())
open(os.path.join(api.snippet_folder(), '署名.md'), 'w', encoding='utf-8').write("{{氏名:山田}}　{{日付}}{{カーソル}}")
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


def choose(label):
    """定型文のボタンを押し、メニューから、表示名のものを選ぶ。"""
    js("document.getElementById('fSnip').click()")
    wait("!document.getElementById('ctx').hidden")
    js("[...document.querySelectorAll('#ctx .citem')].find(b => b.textContent === %s).click()" % json.dumps(label))


def set_text(t):
    js("cm.setValue(%s); cm.clearHistory(); null" % json.dumps(t))


def drive():
    time.sleep(8)
    wait("typeof snipItems !== 'undefined' && snipItems.length > 3")
    check("編集バーに、定型文のボタンがある（チャート・数式の隣）", js("document.getElementById('fMath').nextElementSibling.id"), 'fSnip')
    js("document.getElementById('fSnip').click()")
    check("押すと、メニューが出る", wait("!document.getElementById('ctx').hidden"), True)
    check("組み込みと、自分の定型文が、見出しで分かれて並ぶ",
          js("[...document.querySelectorAll('#ctx .citem')].filter(b => b.disabled).map(b => b.textContent)"), ['— 組み込み —', '— 自分の定型文 —'])
    check("組み込み9つ・自分の1つ・場所を開く", js("[...document.querySelectorAll('#ctx .citem')].filter(b => !b.disabled).length"), 11)
    check("自分の定型文は、ファイル名で出る", js("[...document.querySelectorAll('#ctx .citem')].some(b => b.textContent === '署名')"), True)
    check("メニューが、画面に収まる", js("(() => { const r = document.getElementById('ctx').getBoundingClientRect(); return r.bottom <= innerHeight && r.right <= innerWidth && r.top >= 0 })()"), True)
    js("document.getElementById('ctx').hidden = true; null")
    check("ボタンが、編集欄の幅に収まる", js("(() => { const s = document.getElementById('fSnip').getBoundingClientRect(), p = document.getElementById('editorPane').getBoundingClientRect(); return s.right <= p.right && s.left >= p.left })()"), True)
    check("編集バーの段数が、増えていない（5段以内）", js("new Set([...document.querySelectorAll('#fmt .fgroup')].map(g => Math.round(g.getBoundingClientRect().top))).size <= 5"), True)

    # --- 選んでいる文字を使う（欄が無い）
    set_text("前\nここを読む\n後")
    js("cm.setSelection({line: 1, ch: 0}, {line: 1, ch: 5}); null")
    choose('注意書き')
    check("選んでいた文字が、{{選択}} に入る", wait("cm.getValue() === '前\\n> **注意**　ここを読む\\n後'"), True)
    check("カーソルは、挿入した文字の末尾", js("[cm.getCursor().line, cm.getCursor().ch]"), [1, 14])
    check("1回の取り消しで元に戻る", (js("cm.undo(); null"), js("cm.getValue()"))[1], "前\nここを読む\n後")
    check("メニューは、選んだら閉じる", js("document.getElementById('ctx').hidden"), True)

    # --- 何も選んでいない: カーソルの位置へ
    set_text("あ\n")
    js("cm.setCursor({line: 1, ch: 0}); null")
    choose('チェックリスト')
    check("選んでいなければ、カーソルの位置へ入る", wait("cm.getValue() === 'あ\\n- [ ] \\n- [ ] \\n- [ ] '"), True)
    check("{{カーソル}} の位置（1つ目の項目の後ろ）にカーソルが入る", js("[cm.getCursor().line, cm.getCursor().ch]"), [1, 6])

    # --- 欄がある: 入力を聞く（既定値つき）。Enter で次の欄、最後の欄の Enter で挿入
    set_text("")
    js("cm.setSelection({line: 0, ch: 0}); null")
    choose('リンク')
    check("欄があると、入力の画面が出る", wait("document.getElementById('veil').classList.contains('show') && document.querySelectorAll('#dExtra input').length === 1"), True)
    check("欄の名前が出る", js("document.querySelector('#dExtra .sniprow span').textContent"), 'URL')
    js("(() => { const i = document.querySelector('#dExtra input'); i.value = 'https://example.com'; i.dispatchEvent(new Event('input')); i.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true})); })()")
    check("最後の欄で Enter を押すと、挿入される", wait("cm.getValue() === '[表示する文字](https://example.com)'"), True)
    check("入力の画面は閉じる", js("document.getElementById('veil').classList.contains('show')"), False)

    # --- 取りやめ
    set_text("そのまま")
    choose('リンク')
    wait("document.getElementById('veil').classList.contains('show')")
    js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}))")
    time.sleep(.5)
    check("Esc で取りやめると、何も挿入しない", js("cm.getValue()"), "そのまま")

    # --- 複数の欄: 既定値・Enter で次の欄へ
    set_text("")
    choose('署名')
    wait("document.querySelector('#dExtra .sniprow span') && document.querySelector('#dExtra .sniprow span').textContent === '氏名'")
    check("既定値が入っている", js("document.querySelector('#dExtra input').value"), '山田')
    js("document.querySelector('#dExtra input').value = '佐藤'; document.querySelector('#dBtns .primary').click()")
    check("自分の定型文も、同じように入る（日付は、いまの日付）", wait("/^佐藤　\\d{4}-\\d{2}-\\d{2}$/.test(cm.getValue())"), True)

    # --- 欄の無いもの（日付）は、すぐ入る
    set_text("")
    choose('日付（年月日・曜日）')
    check("組み込みの欄（年月日・曜日）は、聞かずに入る", wait("/^\\d{4}年\\d{1,2}月\\d{1,2}日（[月火水木金土日]）$/.test(cm.getValue())"), True)

    # --- 場所を開く／新しいファイルが、一覧に出る
    choose('定型文の場所を開く…')
    time.sleep(.4)
    check("場所を開いても、文書は変わらない", js("cm.getValue().length > 0"), True)
    open(os.path.join(api.snippet_folder(), '追加.md'), 'w', encoding='utf-8').write("追加です")
    js("loadSnippets()")
    time.sleep(.8)
    js("document.getElementById('fSnip').click()")
    check("置き場へ .md を足して、一覧を取り直すと、選べる", wait("[...document.querySelectorAll('#ctx .citem')].some(b => b.textContent === '追加')"), True)
    js("document.getElementById('ctx').hidden = true; null")
    set_text("")
    choose('追加')
    check("追加した定型文が入る", wait("cm.getValue() === '追加です'"), True)

    # --- 読み取り専用では、使えない
    js("doc.readonly = true; applyDocMeta(); null")
    check("読み取り専用では、ボタンが使えない", js("document.getElementById('fSnip').disabled"), True)
    js("doc.readonly = false; applyDocMeta(); null")
    check("元に戻ると、使える", js("document.getElementById('fSnip').disabled"), False)

    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
