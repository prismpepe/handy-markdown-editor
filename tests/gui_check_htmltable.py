"""HTML の表のセル結合・解除（メニュー・確認・実行・取り消し）を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_htmltable.py

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

MD = "| 名前 | 金額 | 備考 |\n| :-- | --: | --- |\n| りんご | 100 |  |\n| みかん | 200 | 甘い |\n"


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


def menu_at(line, ch):
    """その位置での、HTML の表のメニュー項目 [(ラベル, 無効か)]。"""
    js("window.__m = null; api.html_table_info(cm.getValue(), %d, %d).then(i => { window.__m = JSON.stringify(htmlTableMenuItems(i).filter(x => x !== '-').map(x => [x.label, !!x.disabled])); });" % (line, ch))
    wait("window.__m !== null", 10)
    return json.loads(js("window.__m"))


def click_ask(label):
    """確認のダイアログの、ボタンを押す。"""
    js("(() => { const b = [...document.querySelectorAll('#dBtns button')].find(x => x.textContent === %s); if (b) b.click(); })()" % json.dumps(label))


def line_of(text_part):
    return js("(() => { const n = cm.lineCount(); for (let i = 0; i < n; i++) if (cm.getLine(i).includes(%s)) return i; return -1; })()" % json.dumps(text_part))


def drive():
    time.sleep(8)
    check("画面が組み上がる", wait("typeof cm !== 'undefined' && typeof htmlTableEdit === 'function'"), True)
    # Markdown の表 → HTML の表（変換機能で作る表が、そのまま対象になる）
    js("cm.setValue(%s); cm.clearHistory(); cm.setCursor({line: 2, ch: 3}); null" % json.dumps(MD))
    js("tableToHtml()"); time.sleep(1.5)
    base = js("cm.getValue()")
    check("まず、Markdown の表を HTML の表に変換する", base.startswith('<table>') and '<td align="left">りんご</td>' in base, True)

    # --- メニュー
    r = line_of('りんご')
    c0 = js("cm.getLine(%d).indexOf('<td align=\"left\">りんご') + 3" % r)
    m = menu_at(r, c0)
    check("HTML の表の中の右クリックメニューに、結合の項目が出る", [x[0] for x in m], ['— HTML の表（セルの結合）—', '右のセルと結合', '下のセルと結合', '結合を解除'])
    check("結合されていないセルでは、「結合を解除」が使えない（右・下は使える）", [x[1] for x in m[1:]], [False, False, True])
    check("表の外では、メニューが出ない", api.html_table_info('ただの文\n', 0, 0)['in_table'], False)

    # --- 文字のあるセルとの結合: 確認が出て、「やめる」なら何もしない
    js("cm.setCursor({line: %d, ch: %d}); htmlTableEdit('merge_right')" % (r, c0)); time.sleep(1.2)
    check("取り除くセルに文字があると、確認が出る（改行でつなぐ旨）", [js("document.getElementById('veil').classList.contains('show')"), '改行' in js("document.getElementById('dText').textContent")], [True, True])
    click_ask('やめる'); time.sleep(.8)
    check("「やめる」を押すと、何も変わらない", js("cm.getValue()"), base)
    # 「結合する」
    js("cm.setCursor({line: %d, ch: 8}); htmlTableEdit('merge_right')" % r); time.sleep(1.2)
    click_ask('結合する'); time.sleep(1.2)
    got = js("cm.getValue()")
    check("「結合する」を押すと、colspan が付き、文字が改行でつながる", '<td align="left" colspan="2">りんご<br>100</td>' in got and got.count('<tr>') == base.count('<tr>'), True)
    check("結合したセルの右のセルは、取り除かれる（その行は、1 つ減る）", got.count('<td') == base.count('<td') - 1, True)
    js("cm.undo()")
    check("Ctrl+Z（取り消し）で、1 回で、元に戻る", js("cm.getValue()"), base)

    # --- 空のセルとは、確認なしで結合できる（備考の列: りんごの行は空）
    ln = line_of('りんご')
    ch = js("cm.getLine(%d).indexOf('<td align=\"right\">100') + 3" % ln)
    js("cm.setCursor({line: %d, ch: %d}); htmlTableEdit('merge_right')" % (ln, ch)); time.sleep(1.2)
    check("右のセルが空なら、確認なしで結合される", [js("document.getElementById('veil').classList.contains('show')"), '<td align="right" colspan="2">100</td>' in js("cm.getValue()")], [False, True])

    # --- 下のセルと結合 → 結合を解除
    js("cm.undo(); cm.setCursor({line: %d, ch: %d}); htmlTableEdit('merge_down')" % (ln, c0)); time.sleep(1.2)
    click_ask('結合する'); time.sleep(1.2)
    got = js("cm.getValue()")
    check("下のセルと結合すると、rowspan が付く", '<td align="left" rowspan="2">りんご<br>みかん</td>' in got, True)
    rl = line_of('rowspan')
    m = menu_at(rl, js("cm.getLine(%d).indexOf('rowspan')" % rl))
    check("結合したセルでは、「結合を解除」が使える", [x[1] for x in m[1:]][2], False)
    js("cm.setCursor({line: %d, ch: %d}); htmlTableEdit('split')" % (rl, js("cm.getLine(%d).indexOf('rowspan')" % rl))); time.sleep(1.2)
    got = js("cm.getValue()")
    check("結合を解除すると、rowspan が消え、空のセルが補われる", ['rowspan' not in got, got.count('<td') == base.count('<td')], [True, True])

    # --- 見出しと本文をまたぐ結合・表の端
    js("cm.setValue(%s); cm.setCursor({line: 0, ch: 0}); null" % json.dumps(base))
    hl = line_of('<th')
    js("cm.setCursor({line: %d, ch: 20}); htmlTableEdit('merge_down')" % hl); time.sleep(1.0)
    check("見出しと本文をまたぐ結合は、しない（理由が出る）", 'thead' in js("document.getElementById('smsg').textContent"), True)

    # --- 扱えない表
    js("cm.setValue('<table><tr><td><table><tr><td>x</td></tr></table></td></tr></table>'); cm.setCursor({line: 0, ch: 12}); null")
    m = menu_at(0, 12)
    check("入れ子の表は、扱えない旨が、メニューに出る", ['扱えません' in x[0] or '結合できません' in x[0] for x in m][-1], True)
    # 手書きの単純な表（「表・データ」の取り込みで作る表と同じ形）
    js("cm.setValue('<table border=\"1\">\\n<thead><tr><th>A</th><th>B</th></tr></thead>\\n<tbody><tr><td>1</td><td></td></tr></tbody>\\n</table>'); cm.setCursor({line: 2, ch: 17}); null")
    js("htmlTableEdit('merge_right')"); time.sleep(1.0)
    check("手書きの単純な表（1 行にまとめた書き方）でも、結合できる", '<td colspan="2">1</td>' in js("cm.getValue()"), True)

    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
