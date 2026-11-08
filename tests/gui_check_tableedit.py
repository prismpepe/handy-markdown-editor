"""表の編集支援（右クリックメニュー・整形・列と行の操作・Tab でのセル移動）を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_tableedit.py

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

TABLE = "前の文章\n\n|名前|数|\n|-|-:|\n|りんご|3|\n|みかん|12|\n\n後の文章\n"


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


def set_text(t, line=0, ch=0):
    js("cm.setValue(%s); cm.clearHistory(); cm.setCursor({line: %d, ch: %d}); cm.focus(); null" % (json.dumps(t), line, ch))


def value():
    return js("cm.getValue()")


def right_click(line, ch):
    """その位置で、右クリックする（メニューが出るのを待つ）。"""
    js("(() => { cm.hideCtxForTest = 1; const p = cm.charCoords({line: %d, ch: %d}, 'window'); const ev = new MouseEvent('contextmenu', {clientX: Math.round(p.left) + 1, clientY: Math.round(p.top) + 3, bubbles: true, cancelable: true, button: 2}); cm.getWrapperElement().dispatchEvent(ev); })()" % (line, ch))
    return wait("!document.getElementById('ctx').hidden")


def menu_labels():
    return js("[...document.querySelectorAll('#ctx .citem')].map(b => (b.disabled ? '×' : '') + b.firstChild.textContent)")


def pick(label):
    js("[...document.querySelectorAll('#ctx .citem')].find(b => b.firstChild.textContent === %s).click()" % json.dumps(label))
    time.sleep(.5)


def tab(shift=False):
    js("cm.focus(); cm.getInputField().dispatchEvent(new KeyboardEvent('keydown', {key: 'Tab', code: 'Tab', keyCode: 9, which: 9, shiftKey: %s, bubbles: true, cancelable: true}))" % ('true' if shift else 'false'))
    time.sleep(.5)


def cursor():
    return js("[cm.getCursor().line, cm.getCursor().ch]")


def drive():
    time.sleep(8)
    wait("typeof tableEdit === 'function'")

    # --- 右クリック: 表の中なら、メニューの先頭に「表の編集」
    set_text(TABLE)
    check("表の中で右クリックすると、メニューが出る", right_click(4, 2), True)
    labels = menu_labels()
    check("先頭に、「表の編集」の項目が並ぶ", labels[:3], ['×— 表の編集 —', '表を整形（列の幅をそろえる）', '列を左に追加'])
    check("そのあとに、いつもの項目（元に戻す…）が続く", '×元に戻す' in labels and '貼り付け' in labels, True)
    check("本文の行では、「行を削除」が使える", '行を削除' in labels, True)
    js("document.getElementById('ctx').hidden = true; null")

    # --- 整形（全角は幅 2）。1回の取り消しで戻る
    right_click(4, 2); pick('表を整形（列の幅をそろえる）')
    check("整形される（全角を 2 と数えて、幅がそろう）", value(), "前の文章\n\n| 名前   |  数 |\n| ------ | --: |\n| りんご |   3 |\n| みかん |  12 |\n\n後の文章\n")
    check("周りの文章は、変わらない", value().startswith("前の文章\n\n") and value().endswith("\n\n後の文章\n"), True)
    js("cm.undo(); null")
    check("Ctrl+Z 1回で、整形前に戻る", value(), TABLE)

    # --- 列の追加・移動・削除・配置
    right_click(4, 2); pick('列を右に追加')
    check("列を右に追加", value().split("\n")[2], "| 名前   |     |  数 |")
    js("cm.undo(); null")
    right_click(4, 2); pick('列を削除')
    check("列を削除（その列の全部のセルが消える）", [value().split("\n")[4], value().split("\n")[5]], ["|   3 |", "|  12 |"])
    check("列を削除したあとの列数", value().split("\n")[2].count("|"), 2)
    js("cm.undo(); null")
    right_click(4, 2); pick('列を右へ移動')
    check("列を右へ移動（配置も一緒に動く）", value().split("\n")[3], "| --: | ------ |")
    js("cm.undo(); null")
    right_click(4, 2); pick('配置: 中央')
    check("配置を中央に", value().split("\n")[3].startswith("| :----: |"), True)
    js("cm.undo(); null")

    # --- 行の追加・削除
    right_click(4, 2); pick('行を下に追加')
    check("行を下に追加（カーソルは、新しい行）", [len(value().split("\n")), cursor()[0]], [10, 5])
    js("cm.undo(); null")
    right_click(5, 2); pick('行を削除')
    check("行を削除", "みかん" not in value() and "りんご" in value(), True)
    js("cm.undo(); null")
    check("見出し行では、「行を削除」「行を上に追加」が使えない", (right_click(2, 2), [l for l in menu_labels() if '行を' in l])[1], ['×行を上に追加', '行を下に追加', '×行を削除'])
    js("document.getElementById('ctx').hidden = true; null")

    # --- 表の外では、表のメニューを出さない
    check("表の外では、メニューの先頭は、いつもの項目", (right_click(0, 2), menu_labels()[0])[1], '×元に戻す')
    js("document.getElementById('ctx').hidden = true; null")

    # --- Tab / Shift+Tab: セルの移動
    set_text(TABLE.replace("|名前|数|\n|-|-:|\n|りんご|3|\n|みかん|12|\n", "| 名前 | 数 |\n| --- | --: |\n| りんご | 3 |\n| みかん | 12 |\n"), 2, 3)
    tab()
    check("Tab で、次のセルへ（見出し行の 2 つ目）", js("cm.getRange({line: 2, ch: 0}, cm.getCursor()).endsWith('| 名前 | ')"), True)
    tab()
    check("見出し行の最後から Tab で、区切り行を飛ばして、本文の最初のセルへ", cursor()[0], 4)
    tab(); tab()
    check("本文の次の行の最初のセルへ進む", cursor()[0], 5)
    tab(True)
    check("Shift+Tab で、前のセルへ戻る", cursor()[0], 4)
    check("文書は、変わっていない（移るだけ）", value().count("\n"), 8)
    # 最後のセルで Tab → 行が増える
    js("cm.setCursor({line: 5, ch: cm.getLine(5).length - 3}); null")
    tab()
    check("最後のセルで Tab を押すと、行が足され、その先頭へ移る", [value().split("\n")[6].replace("|", "").strip() == "", cursor()[0]], [True, 6])
    js("cm.undo(); null")
    check("1回の取り消しで、足した行が消える", value().count("\n"), 8)
    # 先頭のセルで Shift+Tab: 動かない
    js("cm.setCursor({line: 2, ch: 3}); null")
    tab(True)
    check("先頭のセルでの Shift+Tab は、動かない", cursor(), [2, 3])

    # --- 表の外の Tab は、これまでどおり（空白2つ）
    set_text("文章", 0, 0)
    tab()
    check("表の外では、Tab で、半角空白が2つ入る", value(), "  文章")
    set_text("a | b", 0, 5)
    tab()
    check("パイプを含む文章（表ではない）でも、これまでどおり", value(), "a | b  ")
    # コードブロックの中の表は、表として扱わない
    set_text("```\n| a | b |\n|---|---|\n```\n", 1, 2)
    tab()
    check("コードブロックの中では、Tab は、これまでどおり", value().split("\n")[1], "| " + "  " + "a | b |")

    # --- 安全: セルが多い行があるときは、直さない（文字を捨てない）
    bad = "| a | b |\n|---|---|\n| 1 | 2 | 3 |\n"
    set_text(bad, 0, 2)
    right_click(0, 2); pick('表を整形（列の幅をそろえる）')
    check("見出し行よりセルが多い行があるときは、直さず、知らせる", [value(), js("document.getElementById('smsg').textContent.includes('3 行目')")], [bad, True])

    # --- 読み取り専用では、表のメニューも、Tab のセル移動も、働かない
    set_text(TABLE, 4, 2)
    js("doc.readonly = true; applyDocMeta(); null")
    right_click(4, 2)
    check("読み取り専用では、表の編集の項目が出ない", [l for l in menu_labels() if '表の編集' in l or '表を整形' in l], [])
    js("document.getElementById('ctx').hidden = true; doc.readonly = false; applyDocMeta(); null")

    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
