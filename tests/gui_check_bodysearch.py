"""フォルダー全体の検索（本文を探す）を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_bodysearch.py

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
os.makedirs(os.path.join(tmp, 'sub'))
A, B = os.path.join(tmp, 'a.md'), os.path.join(tmp, 'sub', 'b.md')
open(A, 'w', encoding='utf-8').write("# 議事録\n\n漏水の件を報告した。\n\n別の段落\n\n漏水が再発した。 LEAK と leak\n")
open(B, 'w', encoding='utf-8').write("# 設計\n漏水調査の計画\n")
open(os.path.join(tmp, 'c.md'), 'w', encoding='utf-8').write("何もない\n")

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


def set_query(q):
    js("(() => { const f = document.getElementById('filter'); f.value = %s; f.dispatchEvent(new Event('input')); })()" % json.dumps(q))


def heads():
    return js("[...document.querySelectorAll('#list .shead')].map(h => h.firstChild.textContent + ':' + h.querySelector('.scnt').textContent)")


def drive():
    time.sleep(8)
    wait("typeof bodyOn === 'function'")
    js("loadFolder(%s)" % json.dumps(tmp))
    wait("document.querySelectorAll('#list .item').length === 2")
    check("初めは「本文を探す」は切れている", js("[document.getElementById('bodySearch').checked, document.getElementById('bodyOpts').hidden]"), [False, True])

    js("document.getElementById('bodySearch').click()")
    set_query('漏水')
    check("本文を探す: ファイルごとの結果", wait("document.querySelectorAll('#list .shead').length === 2"), True)
    check("ファイル名と、一致した行の数", heads(), ['b.md:1 行', 'a.md:2 行'])
    check("本文検索の結果も、フォルダーごとにまとめる（サブフォルダーが先）", js("[...document.querySelectorAll('#list > div')].map(r => r.classList.contains('dirrow') ? 'D:' + r.querySelector('.dname').textContent.replace('📁 ', '') + '(' + r.querySelector('.dcnt').textContent + ')' : r.classList.contains('shead') ? 'F:' + r.firstChild.textContent : null).filter(x => x)"), ['D:sub(1)', 'F:b.md', 'F:a.md'])
    check("本文検索でも、「すべて開く・閉じる」が使える", js("document.getElementById('treeBtns').hidden"), False)
    js("document.getElementById('treeClose').click()")
    check("「すべて閉じる」で、フォルダーが畳まれる（探した結果は、そのまま）", js("[document.querySelectorAll('#list .dirrow[aria-expanded=false]').length, document.querySelectorAll('#list .shead').length, document.getElementById('count').textContent.includes('2 ファイル')]"), [1, 1, True])
    js("document.getElementById('treeOpen').click()")
    check("「すべて開く」で、また開く", js("document.querySelectorAll('#list .shead').length"), 2)
    check("行番号と一致", js("[...document.querySelectorAll('#list .shit')].map(r => r.querySelector('.sln').textContent + '|' + r.querySelector('mark').textContent)"), ['2|漏水', '3|漏水', '7|漏水'])

    # --- 行へ移る: ファイルを開いて、その行の、一致した文字を選ぶ
    js("document.querySelectorAll('#list .shit')[2].click()")
    check("2つ目の一致（7行目）を押すと、a.md が開く", wait("doc.path === %s" % json.dumps(A)), True)
    check("その行の、一致した文字（漏水）が、選ばれる", wait("cm.getSelection() === '漏水' && cm.getCursor('from').line === 6"), True)
    check("編集欄に焦点が移る", js("cm.hasFocus()"), True)
    js("document.querySelectorAll('#list .shit')[1].click()")
    check("同じファイルの別の行へも、そのまま移る（開き直さない）", wait("cm.getCursor('from').line === 2 && cm.getSelection() === '漏水'"), True)
    js("document.querySelectorAll('#list .shit')[0].click()")
    check("ほかのファイル（sub/b.md）の行を押すと、そのファイルが開く", wait("doc.path === %s && cm.getSelection() === '漏水' && cm.getCursor('from').line === 1" % json.dumps(B)), True)
    check("選ばれる範囲は、一致の桁から（行の途中でも）", js("cm.getCursor('from').ch"), 0)
    check("一致した文字に、目立つ黄色の印が付く（1つだけ。前のファイルの印は残らない）",
          js("[document.querySelectorAll('.cm-bodyhit').length, document.querySelector('.cm-bodyhit') && document.querySelector('.cm-bodyhit').textContent]"), [1, '漏水'])
    check("印の色は、黄色（選択の水色ではない）", js("getComputedStyle(document.querySelector('.cm-bodyhit')).backgroundColor"), 'rgb(255, 211, 61)')
    js("document.getElementById('bodySearch').click()")
    check("「本文を探す」を切ると、印も選択も消える", wait("document.querySelectorAll('.cm-bodyhit').length === 0 && cm.getSelection() === ''"), True)
    js("document.getElementById('bodySearch').click()")
    wait("!document.getElementById('bodyOpts').hidden")

    # --- 保存していない編集中の内容を、探す
    js("openPath(%s)" % json.dumps(A))
    wait("doc.path === %s" % json.dumps(A))
    js("cm.replaceRange('新しい漏水の一行\\n', {line: 0, ch: 0}); null")
    check("編集して、まだ保存していない", js("isDirty()"), True)
    set_query('新しい')
    check("保存していない編集中の内容も、探す（ディスクにはまだ無い）", wait("document.querySelectorAll('#list .shead').length === 1 && document.querySelector('#list .shead').firstChild.textContent === 'a.md'"), True)
    check("行番号は、編集中の内容のもの（1行目）", js("document.querySelector('#list .shit .sln').textContent"), '1')
    js("document.querySelector('#list .shit').click()")
    check("開いている（編集中の）文書は、確認なしで、その行へ移る", wait("cm.getSelection() === '新しい' && cm.getCursor('from').line === 0 && isDirty()"), True)
    js("cm.undo(); cm.markClean(); doc.metaDirty = false; updateDirty(); null")

    # --- 保存していない変更があるときに、別のファイルを開く結果を押すと、これまでどおり確認する
    js("cm.replaceRange('x', {line: 0, ch: 0}); null")
    js("window._ask = ask; window._asked = []; ask = async (t, x, b) => { window._asked.push(t); return 2; }; null")      # キャンセル
    set_query('設計')
    wait("[...document.querySelectorAll('#list .shead')].map(h => h.firstChild.textContent).join() === 'b.md'")
    js("document.querySelector('#list .shit').click()")
    time.sleep(.8)
    check("確認を出す（保存するか）", js("window._asked"), ['変更を保存しますか？'])
    check("取りやめると、開かない", js("doc.path === %s" % json.dumps(A)), True)
    js("ask = window._ask; cm.undo(); cm.markClean(); doc.metaDirty = false; updateDirty(); null")

    # --- 大文字小文字・正規表現
    js("document.getElementById('bsCase').click()")
    set_query('LEAK')
    check("大文字小文字を区別する", wait("document.querySelectorAll('#list .shit').length === 1"), True)
    js("document.getElementById('bsCase').click()")
    js("document.getElementById('bsRe').click()")
    set_query('(')
    check("正規表現が正しくないときは、理由を出す", wait("document.getElementById('count').textContent.includes('正規表現が正しくありません')"), True)
    set_query('漏水(が|調査)')
    check("正規表現で探せる", wait("document.querySelectorAll('#list .shit').length === 2"), True)
    js("document.getElementById('bsRe').click()")

    # --- 切ると、ファイル一覧に戻る
    js("document.getElementById('bodySearch').click()")
    set_query('')
    check("「本文を探す」を切ると、ファイルの一覧に戻る", wait("document.querySelectorAll('#list .item').length === 2 && document.getElementById('bodyOpts').hidden"), True)

    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
