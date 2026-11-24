"""置換セット（ダイアログ・標準のセット・実行・取り消し・保存）と、表の HTML 変換を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_replaceset.py

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


def apply_builtin(sid, text):
    return js("(() => { const s = rsFind(%s); return JSON.stringify(rsApply(s.steps, %s)); })()" % (json.dumps(sid), json.dumps(text)))


def drive():
    time.sleep(8)
    check("画面が組み上がる", wait("typeof cm !== 'undefined' && typeof openReplaceSetDlg === 'function'"), True)
    js("openReplaceSetDlg()"); time.sleep(1.5)
    check("置換セットのダイアログが開き、標準のセットが並ぶ", [js("!document.getElementById('rsveil').hidden"), js("document.getElementById('rsList').options.length >= 5")], [True, True])
    check("標準のセットは、読み取り専用（名前・手順の欄が無効）で、削除できない",
          js("[rsName.disabled, rsDel.disabled, rsAdd.disabled, [...document.querySelectorAll('#rsSteps input')].every(i => i.disabled)]"), [True, True, True, True])

    # --- 標準のセットの結果
    r = json.loads(apply_builtin('b-img', '![図](a.png) と ![題付き](b.png "タイトル") と ![](c.png)'))
    check("画像 → <img>（タイトル付きも、代替の文字が空でも）", r['text'], '<img src="a.png" alt="図"> と <img src="b.png" alt="題付き" title="タイトル"> と <img src="c.png" alt="">')
    check("画像: 手順ごとの件数", r['counts'], [1, 2])
    r = json.loads(apply_builtin('b-link', '[文字](https://e.com) と [題](https://e.com "T") と ![画像](x.png)'))
    check("リンク → <a>（画像は、そのまま）", r['text'], '<a href="https://e.com">文字</a> と <a href="https://e.com" title="T">題</a> と ![画像](x.png)')
    r = json.loads(apply_builtin('b-bold', '**太字** と *斜体* と 2*3*4 と **a**b'))
    check("太字・斜体 → <strong>・<em>（数式のような 2*3*4 は、そのまま）", r['text'], '<strong>太字</strong> と <em>斜体</em> と 2*3*4 と <strong>a</strong>b')
    r = json.loads(apply_builtin('b-trail', 'a  \nb\t\nc　\nd'))
    check("行末の空白を削除（全角の空白も）", r['text'], 'a\nb\nc\nd')
    r = json.loads(apply_builtin('b-bullet', '* 一\n  + 二\n- 三\n*強調*'))
    check("箇条書きの記号を - にそろえる（強調の * は、触らない）", r['text'], '- 一\n  - 二\n- 三\n*強調*')
    check("正規表現に誤りがあれば、1つも当てずに理由を返す",
          js("JSON.stringify(rsApply([{find: 'ok', replace: 'x', regex: false, case: false}, {find: '(', replace: '', regex: true, case: false}], 'ok'))").startswith('{"error":"手順 2'), True)

    # --- 実行・取り消し（文書全体と、選択範囲）
    js("rsClose.click()"); time.sleep(.5)
    js("cm.setValue('![図](a.png)\\n行末  \\n![図2](b.png)'); cm.clearHistory(); cm.setCursor({line: 0, ch: 0}); null")
    js("openReplaceSetDlg()"); time.sleep(1.2)
    js("rsList.value = 'b-img'; rsList.dispatchEvent(new Event('change'))"); time.sleep(.3)
    check("選んでいないときは、「選択範囲に実行」が使えない", js("rsRunSel.disabled"), True)
    js("cm.setSelection({line: 0, ch: 0}, {line: 0, ch: 11})"); js("rsShow('b-img')")
    check("選んでいれば、「選択範囲に実行」が使える", js("rsRunSel.disabled"), False)
    js("rsRunSel.click()"); time.sleep(.8)
    check("選択範囲だけが置換される（選ばなかった行は、そのまま）", js("cm.getValue()"), '<img src="a.png" alt="図">\n行末  \n![図2](b.png)')
    js("rsRunAll.click()"); time.sleep(.8)
    check("文書全体に実行すると、残りも置換される", js("cm.getValue()"), '<img src="a.png" alt="図">\n行末  \n<img src="b.png" alt="図2">')
    check("実行の結果が、ダイアログに出る", '件を置換しました' in js("document.getElementById('rsMsg').textContent"), True)
    js("rsClose.click()"); time.sleep(.5)
    js("cm.undo()"); js("cm.undo()")
    check("Ctrl+Z（取り消し）で、実行の前に戻る（1回の実行 = 1回の取り消し）", js("cm.getValue()"), '![図](a.png)\n行末  \n![図2](b.png)')

    # --- 利用者のセット: 新規・手順の追加・保存・コピー・削除
    js("openReplaceSetDlg()"); time.sleep(1.2)
    js("rsNew.click()"); time.sleep(.3)
    js("rsName.value = '私の置換'; rsName.dispatchEvent(new Event('input'))")
    js("(() => { const i = document.querySelectorAll('#rsSteps .rss input[type=text]'); i[0].value = '行末'; i[0].dispatchEvent(new Event('input')); i[1].value = '末尾'; i[1].dispatchEvent(new Event('input')); })()")
    time.sleep(1.2)                                                       # 少し待って保存される
    saved = api.replace_sets_get()['user']
    check("新しいセットが、保存される（名前と手順）", [[s['name'], s['steps'][0]['find'], s['steps'][0]['replace']] for s in saved], [['私の置換', '行末', '末尾']])
    js("cm.setValue('行末'); null")
    js("rsRunAll.click()"); time.sleep(.6)
    check("利用者のセットも、実行できる", js("cm.getValue()"), '末尾')
    js("cm.setValue('検索欄から'); null")
    js("document.getElementById('fq').value = '検索'; document.getElementById('fr').value = '置換'; document.getElementById('fRegex').checked = false; document.getElementById('fCase').checked = true; null")
    js("rsFromFind.click()"); time.sleep(1.0)
    st = api.replace_sets_get()['user'][0]['steps'][-1]
    check("検索欄の内容を、手順として追加できる（設定も引き継ぐ）", [st['find'], st['replace'], st['regex'], st['case']], ['検索', '置換', False, True])
    js("rsCopy.click()"); time.sleep(1.0)
    names = [s['name'] for s in api.replace_sets_get()['user']]
    check("コピーが作られる", names, ['私の置換', '私の置換（コピー）'])
    js("rsList.value = 'b-img'; rsList.dispatchEvent(new Event('change')); rsCopy.click()"); time.sleep(1.0)
    check("標準のセットも、コピーして、編集できる（コピーは、編集の欄が有効）",
          js("[rsName.disabled, rsName.value.startsWith('画像を <img>')]"), [False, True])
    js("rsDel.click()"); time.sleep(.6)
    # 削除の確認（askOver の「削除」）を押す
    js("(() => { const b = [...document.querySelectorAll('#dBtns button')].find(x => x.textContent === '削除'); if (b) b.click(); })()"); time.sleep(1.0)
    check("削除の確認で「削除」を押すと、セットが消える", len(api.replace_sets_get()['user']), 2)
    # 閉じて開き直しても、残る
    js("rsClose.click()"); time.sleep(.5)
    js("openReplaceSetDlg()"); time.sleep(1.2)
    check("閉じて開き直しても、利用者のセットは残る", js("[...rsList.options].filter(o => !o.textContent.startsWith('［標準］')).map(o => o.textContent.replace('［自分用］', '')).join('|')"), '私の置換|私の置換（コピー）')
    check("Esc で閉じる", [js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); null"), time.sleep(.8), js("document.getElementById('rsveil').hidden")][2], True)

    # --- 検索・置換の欄から、置換セットを開く
    js("finder.open(true)"); time.sleep(.5)
    check("検索・置換の欄に、「置換セット…」のボタンがある", js("!document.getElementById('rSets').closest('#rrow').hidden"), True)
    js("document.getElementById('rSets').click()"); time.sleep(1.2)
    check("そのボタンで、ダイアログが開く", js("!document.getElementById('rsveil').hidden"), True)
    js("rsClose.click()"); time.sleep(.5)

    # --- 文書フォルダー用のセット（.markdown-editor\replace_sets.json）
    proj = tempfile.mkdtemp(prefix='md_proj_')
    docp = os.path.join(proj, 'a.md')
    open(docp, 'w', encoding='utf-8').write('表記ゆれ ＡＢＣ\n')
    js("cm.markClean(); doc.metaDirty = false; null")                       # 未保存の変更があると、開く前に確認が出る
    js("openPath(%s)" % json.dumps(docp)); time.sleep(2.0)
    js("openReplaceSetDlg()"); time.sleep(1.5)
    where = js("document.getElementById('rsWhere').textContent")
    check("文書を開いていれば、フォルダー用のセットの置き場が表示される", ['.markdown-editor' in where, 'replace_sets.json' in where], [True, True])
    check("「保存先」に、この文書フォルダーを選べる", js("rsScope.querySelector('option[value=project]').disabled"), False)
    js("rsNew.click()"); time.sleep(.3)
    js("rsName.value = '管理組合の表記'; rsName.dispatchEvent(new Event('input'))")
    js("(() => { const i = document.querySelectorAll('#rsSteps .rss input[type=text]'); i[0].value = 'ＡＢＣ'; i[0].dispatchEvent(new Event('input')); i[1].value = 'ABC'; i[1].dispatchEvent(new Event('input')); })()")
    js("rsScope.value = 'project'; rsScope.dispatchEvent(new Event('change'))"); time.sleep(1.5)
    pfile = os.path.join(proj, '.markdown-editor', 'replace_sets.json')
    check("保存先を「この文書フォルダー」にすると、.markdown-editor に保存される", os.path.isfile(pfile), True)
    saved = json.load(open(pfile, encoding='utf-8'))['sets'] if os.path.isfile(pfile) else []
    check("保存された内容（名前と手順）", [[x['name'], x['steps'][0]['find'], x['steps'][0]['replace']] for x in saved], [['管理組合の表記', 'ＡＢＣ', 'ABC']])
    check("一覧では、［フォルダー］の印が付く", js("rsList.selectedOptions[0].textContent"), '［フォルダー］管理組合の表記')
    check("自分用のファイルには、入らない", [x['name'] for x in api.replace_sets_get(proj)['user']], ['私の置換', '私の置換（コピー）'])
    js("rsRunAll.click()"); time.sleep(.6)
    check("フォルダー用のセットも、実行できる", js("cm.getValue()"), '表記ゆれ ABC\n')
    js("rsClose.click()"); time.sleep(.5)
    # 閉じて開き直すと、フォルダー用が、先頭に出る（フォルダー → 自分用 → 標準）
    js("openReplaceSetDlg()"); time.sleep(1.2)
    check("開き直すと、フォルダー用のセットが、一覧の先頭に出る", js("rsList.options[0].textContent"), '［フォルダー］管理組合の表記')
    # 標準と自分用を出さない（inherit false）
    check("フォルダー用のセットがあれば、「標準と自分用を出さない」の欄が出る", js("!document.getElementById('rsInheritRow').hidden"), True)
    js("rsInherit.click()"); time.sleep(1.2)
    check("チェックすると、一覧は、フォルダー用だけになる", js("[...rsList.options].map(o => o.textContent).join('|')"), '［フォルダー］管理組合の表記')
    cfg = json.load(open(os.path.join(proj, '.markdown-editor', 'settings.json'), encoding='utf-8'))
    check("settings.json に、inherit: false が書かれる", cfg.get('replace_sets'), {'inherit': False})
    js("rsNew.click()"); time.sleep(.5)
    check("「出さない」設定のとき、新しいセットは、フォルダー用になる（一覧に出るため）", js("rsList.selectedOptions[0].textContent.startsWith('［フォルダー］')"), True)
    js("rsInherit.click()"); time.sleep(1.2)
    check("チェックを外すと、標準と自分用のセットが、また出る", js("rsList.options.length > 5"), True)
    js("rsClose.click()"); time.sleep(.8)
    cfg = json.load(open(os.path.join(proj, '.markdown-editor', 'settings.json'), encoding='utf-8'))
    check("外した設定も、保存される", cfg.get('replace_sets'), {'inherit': True})
    # 保存先を自分用へ戻すと、フォルダー用のファイルから消える
    js("openReplaceSetDlg()"); time.sleep(1.2)
    js("rsList.value = [...rsList.options].find(o => o.textContent === '［フォルダー］管理組合の表記').value; rsList.dispatchEvent(new Event('change'))")
    js("rsScope.value = 'user'; rsScope.dispatchEvent(new Event('change'))"); time.sleep(1.5)
    names = [x['name'] for x in json.load(open(pfile, encoding='utf-8'))['sets']]
    check("保存先を「自分用」に戻すと、フォルダー用のファイルから消え、自分用に入る",
          ['管理組合の表記' in names, '管理組合の表記' in [x['name'] for x in api.replace_sets_get(proj)['user']]], [False, True])
    js("rsClose.click()"); time.sleep(.5)

    # --- 表を HTML の表に変換
    js("finder.close(); cm.setValue('前の文\\n\\n| 名前 | 金額 |\\n| :-- | --: |\\n| **りんご** | 100 |\\n| みかん | `a\\\\|b` |\\n\\n後の文'); cm.clearHistory(); cm.setCursor({line: 4, ch: 3}); null")
    js("tableToHtml()"); time.sleep(1.5)
    got = js("cm.getValue()")
    check("表が HTML の表に置き換わる（前後の文は、そのまま）", got.startswith('前の文\n\n<table>\n') and got.endswith('</table>\n\n後の文'), True)
    check("配置・太字・コードが、HTML になる", [('<th align="right">金額</th>' in got), ('<strong>りんご</strong>' in got), ('<code>a|b</code>' in got)], [True, True, True])
    js("cm.undo()")
    check("Ctrl+Z で、Markdown の表に戻る（1回）", js("cm.getValue().includes('| :-- | --: |')"), True)
    js("cm.setCursor({line: 0, ch: 0})"); js("tableToHtml()"); time.sleep(1.0)
    check("表の外では、何もしない", js("cm.getValue().includes('<table>')"), False)

    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
