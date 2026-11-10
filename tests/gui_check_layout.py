"""表示モード・フォルダーの切替・ツールバーの折り返しを、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_layout.py

設定の置き場所は一時フォルダーへ向ける（利用者の設定を書き換えない）。旧い設定からの引き継ぎは、
設定を書いたうえで起動し直す必要があるので、引数つきで自分自身を起動して確かめる。
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, '.')
SCENARIO = sys.argv[1] if len(sys.argv) > 1 else ''

# ---- 旧い設定からの引き継ぎ: 「書いておく設定」→「起動したあとの表示モード」
MIGRATION = {
    'old_split_list_visible': ({'prefs': {'view': 'split'}}, 'triple'),                      # 旧: 2画面+一覧あり = 今の3画面
    'old_split_list_hidden': ({'prefs': {'view': 'split'}, 'side_hidden': True}, 'split'),   # 旧: 2画面+一覧なし = 今の2画面
    'old_edit': ({'prefs': {'view': 'edit'}}, 'edit'),
    'old_preview': ({'prefs': {'view': 'preview'}}, 'preview'),
    'new_user': ({}, 'triple'),                                                               # 設定なし = 3画面
    'already_new': ({'prefs': {'view': 'split', 'layout_v': 2}}, 'split'),                    # 新しい設定の2画面は、一覧なしのまま
}

if not SCENARIO:       # 親: 引き継ぎの各場合を別の起動で確かめ、そのあと通常の確認を行う
    ok = True
    for name in MIGRATION:
        out = subprocess.run([sys.executable, __file__, name], capture_output=True, text=True, encoding='utf-8').stdout
        line = [l for l in out.splitlines() if l.startswith(('OK ', 'NG '))]
        print(line[-1] if line else f'NG {name}: 結果が出ませんでした', flush=True)
        ok = ok and bool(line) and line[-1].startswith('OK ')
    os.execv(sys.executable, [sys.executable, __file__, 'main'])

os.environ['APPDATA'] = tempfile.mkdtemp(prefix='md_appdata_')
import webview
import mdeditor

import gui_nodialog  # noqa: F401  OS のダイアログを出さない（キー入力を奪うため）

if SCENARIO in MIGRATION:
    mdeditor.save_settings(MIGRATION[SCENARIO][0])

tmp = tempfile.mkdtemp()
folder_a, folder_b = os.path.join(tmp, 'A'), os.path.join(tmp, 'B')
os.makedirs(folder_a)
os.makedirs(folder_b)
doc_a = os.path.join(folder_a, 'a.md')
open(doc_a, 'w', encoding='utf-8', newline='\n').write("# Aの文書\n\n本文\n")
open(os.path.join(folder_b, 'b.md'), 'w', encoding='utf-8').write("# Bの文書\n")

api = mdeditor.Api(None)
w = webview.create_window('t', html=mdeditor.build_html(), js_api=api, width=1400, height=800, x=20, y=20)
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
        time.sleep(.3)
    return bool(js(code))


def state():
    return json.loads(js("""JSON.stringify({
      view: prefs.view,
      side: !document.getElementById('side').classList.contains('hidden'),
      editor: getComputedStyle(document.getElementById('editorPane')).display !== 'none',
      preview: getComputedStyle(document.getElementById('previewPane')).display !== 'none',
      splitter: getComputedStyle(document.getElementById('split')).display !== 'none',
      active: ['vTriple','vSplit','vEdit','vPrev'].filter(i => document.getElementById(i).classList.contains('active')) })"""))


def click_dialog(label):
    js("[...document.querySelectorAll('#dBtns button')].find(b => b.textContent === %s).click()" % json.dumps(label))


def finish():
    # hidden 属性の要素は、実際に隠れている（display を指定した CSS が、hidden を打ち消していないか）
    shown = js("[...document.querySelectorAll('[hidden]')].filter(e => getComputedStyle(e).display !== 'none').map(e => e.id || e.className || e.tagName)")
    check("hidden 属性の要素が、すべて隠れている", shown, [])

    # 編集ボタンは、編集欄の左に縦に並ぶ（編集 → 書式 → リスト・ブロック）。選択欄などは、各画面の見出しの1行に置く
    check("縦の列のグループの名前と並び", js("[...document.querySelectorAll('#fmt .fgroup .glabel')].map(e => e.textContent)"), ['編集', '書式', 'ブロック'])
    check("編集: 元に戻す・やり直し・切り取り・コピー・貼り付け・検索・置換", js("[...document.querySelectorAll('#fmt .fgroup')[0].querySelectorAll('button')].map(b => b.dataset.e)"),
          ['undo', 'redo', 'cut', 'copy', 'paste', 'find', 'replace'])
    check("書式: H1〜H6 のボタン、そのあとに装飾・リンク・画像（画像は、行の中に入るので、リンクの隣。見出しの選択欄はない）", js("[...document.querySelectorAll('#fmt .fgroup')[1].querySelectorAll('button')].map(b => b.dataset.h || b.dataset.f)"),
          ['1', '2', '3', '4', '5', '6', 'bold', 'italic', 'strike', 'code', 'link', 'image'])
    check("見出しの選択欄は、なくなった", js("document.getElementById('fHead')"), None)
    check("ブロックは、引用がコードブロックの隣。末尾に、表（アイコンだけ）", js("[...document.querySelectorAll('#fmt .fgroup')[2].querySelectorAll('button')].map(b => b.dataset.f)"),
          ['ul', 'ol', 'task', 'quote', 'codeblock', 'rule', 'table'])
    check("画像・表のボタンは、アイコンだけ（文言なし）", js("[...document.querySelectorAll('#fmt button[data-f=image], #fmt button[data-f=table]')].map(b => b.textContent.trim())"), ['🖼', '▦'])
    check("グループの名前は、背景と違う色の帯に出る（埋もれない）",
          js("(() => { const l = document.querySelector('#fmt .glabel'); return getComputedStyle(l).backgroundColor !== getComputedStyle(document.getElementById('fmt')).backgroundColor && parseInt(getComputedStyle(l).fontWeight) >= 600; })()"), True)

    check("各画面の見出しは「編集画面」「プレビュー画面」", js("[document.querySelector('#ehead .ptitle').textContent, document.querySelector('#phead .ptitle').textContent]"), ['編集画面', 'プレビュー画面'])
    check("編集画面の見出し: 画像の挿入・チャート・数式・定型文・目次・表・データ", js("[...document.querySelectorAll('#ehead .hbtns > *')].map(e => e.id)"), ['fImage', 'fDiagram', 'fMath', 'fSnip', 'fToc', 'fTable'])
    check("プレビュー画面の見出し: 倍率・印刷／PDF・HTML", js("[...document.querySelectorAll('#phead .hbtns button, #phead .hbtns input')].map(e => e.id)"), ['zOut', 'zVal', 'zIn', 'z100', 'bPrint', 'bHtml'])
    check("全体表示のボタンは、なくなった", js("document.getElementById('zFit')"), None)
    check("トップバーには、倍率・印刷／PDF・HTML がない", js("['zoombox', 'bPrint', 'bHtml'].map(i => !!document.querySelector('#toolbar #' + i))"), [False, False, False])
    check("チャートと数式は、2つの選択欄に分かれる（名前）", (js("document.querySelector('#fDiagram option').textContent"), js("document.querySelector('#fMath option').textContent")), ('チャートを挿入…', '数式を挿入…'))

    w.resize(1400, 800)
    time.sleep(.8)
    check("既定の3画面（幅1400）: トップバーは1段", js("document.getElementById('toolbar').getBoundingClientRect().height < 60"), True)
    check("編集画面とプレビュー画面の見出しは、同じ高さの1行（本文が同じ高さから始まる）",
          js("(() => { const e = document.getElementById('ehead').getBoundingClientRect(), p = document.getElementById('phead').getBoundingClientRect(); return [Math.round(e.height), Math.round(p.height), Math.round(e.bottom - p.bottom)]; })()"), [36, 36, 0])
    check("編集欄は、見出しの直下から始まり、プレビューと同じ高さから始まる",
          js("(() => { const c = document.querySelector('#edbox .CodeMirror').getBoundingClientRect(), p = document.getElementById('pscroll').getBoundingClientRect(); return Math.round(c.top - p.top); })()"), 0)
    check("高さの足りない窓（800）では、縦の列は2列", js("document.getElementById('fmt').classList.contains('two')"), True)
    check("縦の列は、編集欄の高さに収まる（はみ出さない）", js("(() => { const f = document.getElementById('fmt'); return f.scrollHeight <= f.clientHeight + 1; })()"), True)
    w.resize(1400, 1040)
    time.sleep(1.0)
    check("高い窓（1040）では、縦の列は1列", js("document.getElementById('fmt').classList.contains('two')"), False)
    check("1列のときは、列の幅が狭い（編集欄を広く使える）", js("Math.round(document.getElementById('fmt').getBoundingClientRect().width) <= 56"), True)
    w.resize(1400, 800)
    time.sleep(.8)

    # --- 倍率（プレビュー画面の見出し）
    js("document.getElementById('zIn').click()")
    check("＋で倍率が上がる", js("+document.getElementById('zVal').value > 100"), True)
    js("document.getElementById('z100').click()")
    check("100% で等倍に戻る", js("[+document.getElementById('zVal').value, document.getElementById('preview').style.zoom]"), [100, '1'])

    # --- 窓が狭くなっても、見出しの部品や縦の列が、はみ出さない
    for width in (1400, 900, 600, 420):
        js("document.getElementById('%s').click()" % ('vTriple' if width >= 900 else 'vSplit'))       # 狭い窓では、一覧を隠す（2画面）
        w.resize(width, 800)
        time.sleep(0.8)
        over = js("""(() => { const out = [];
          for (const id of ['ehead', 'phead']) { const h = document.getElementById(id), r = h.getBoundingClientRect();
            if (r.width === 0) continue;
            for (const e of h.querySelectorAll('button, select, input')) { const b = e.getBoundingClientRect(); if (b.width > 0 && b.right > r.right + 1) out.push(id + ':' + (e.id || e.textContent.trim())); } }
          return out; })()""")
        check("幅 %d: 見出しの部品が、見出しの右端を越えない" % width, over, [])
    js("document.getElementById('vTriple').click()")
    # --- 編集欄を狭めても、部品が編集欄からはみ出して、プレビューに重ならない
    w.resize(1400, 800)
    time.sleep(.5)
    for width in (420, 330, 260, 200):
        js("document.getElementById('editorPane').style.flex = '0 0 %dpx'" % width)
        time.sleep(.5)
        over = js("""(() => { const pane = document.getElementById('editorPane').getBoundingClientRect();
          return [...document.querySelectorAll('#ehead button, #ehead select, #fmt button')].filter(e => e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().right > pane.right + 1)
            .map(e => (e.id || e.textContent.trim()) + ':' + Math.round(e.getBoundingClientRect().right - pane.right)); })()""")
        check("編集欄の幅 %dpx: 見出しの部品と縦の列が、編集欄の右端を越えない" % width, over, [])
    js("document.getElementById('editorPane').style.flex = ''")
    w.resize(1400, 800)
    time.sleep(.5)
    js("document.getElementById('editorPane').style.flex = '0 0 540px'")
    time.sleep(.6)
    check("編集欄が狭い（540）と、定型文・目次・表・データは、アイコンだけになり、見出しは1行のまま",
          js("[Math.round(document.getElementById('ehead').getBoundingClientRect().height), getComputedStyle(document.querySelector('#ehead .bl')).display]"), [36, 'none'])
    js("document.getElementById('editorPane').style.flex = ''")

    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


def drive_migration():
    time.sleep(8)
    want = MIGRATION[SCENARIO][1]
    s = state()
    saved = mdeditor.load_settings().get('prefs', {})
    ok = s['view'] == want and saved.get('layout_v') == 2 and saved.get('view') == want and s['active'] == [
        {'triple': 'vTriple', 'split': 'vSplit', 'edit': 'vEdit', 'preview': 'vPrev'}[want]]
    print(('OK ' if ok else 'NG ') + f'旧い設定の引き継ぎ（{SCENARIO}）→ {want}'
          + ('' if ok else f'  実際: view={s["view"]} 保存={saved} active={s["active"]}'), flush=True)
    os._exit(0)


def drive():
    time.sleep(8)
    # ---- 表示を切り替えるボタンが1か所にまとまっている
    check("「一覧を隠す」のボタンはない", js("document.getElementById('bSide')"), None)
    check("表示のボタンは4つ", js("[...document.querySelectorAll('#vTriple, #vSplit, #vEdit, #vPrev')].map(b => b.textContent).join('/')"),
          '3画面/2画面/編集のみ/プレビューのみ')
    expect = {
        'triple': dict(side=True, editor=True, preview=True, splitter=True, active=['vTriple']),
        'split': dict(side=False, editor=True, preview=True, splitter=True, active=['vSplit']),
        'edit': dict(side=False, editor=True, preview=False, splitter=False, active=['vEdit']),
        'preview': dict(side=False, editor=False, preview=True, splitter=False, active=['vPrev']),
    }
    for view, btn in (('triple', 'vTriple'), ('split', 'vSplit'), ('edit', 'vEdit'), ('preview', 'vPrev')):
        js(f"document.getElementById('{btn}').click()")
        time.sleep(.4)
        s = state()
        s.pop('view')
        check(f"「{view}」: 一覧・編集・プレビューの出し方", s, expect[view])
    js("document.getElementById('vTriple').click()")
    time.sleep(.3)
    js("toggleSide()")
    check("Ctrl+\\（一覧の表示切替）: 3画面 → 2画面", state()['view'], 'split')
    js("toggleSide()")
    check("Ctrl+\\: 2画面 → 3画面", state()['view'], 'triple')
    js("document.getElementById('vEdit').click()")
    js("toggleSide()")
    check("Ctrl+\\: 編集のみ → 3画面", state()['view'], 'triple')
    for key, want in (('1', 'triple'), ('2', 'split'), ('3', 'edit'), ('4', 'preview')):
        js("document.dispatchEvent(new KeyboardEvent('keydown', {key: %s, ctrlKey: true, bubbles: true}))" % json.dumps(key))
        time.sleep(.3)
        check(f"Ctrl+{key} → {want}", state()['view'], want)
    check("選んだ表示モードが保存される", mdeditor.load_settings()['prefs']['view'], 'preview')
    js("document.getElementById('vTriple').click()")

    # ---- フォルダーを変えたときの文書の扱い
    js(f"loadFolder({json.dumps(folder_a)}).then(() => openPath({json.dumps(doc_a)}))")
    wait("doc.path && doc.path.endsWith('a.md')")
    check("文書が開いている", js("cm.getValue().startsWith('# Aの文書')"), True)
    js(f"switchFolder({json.dumps(folder_a)})")
    time.sleep(1)
    check("同じフォルダーを選び直しても、文書は開いたまま（確認も出ない）",
          (js("doc.path") is not None, js("document.getElementById('veil').classList.contains('show')")), (True, False))

    js(f"window.__r = null; switchFolder({json.dumps(folder_b)}).then(v => {{ window.__r = v; }})")
    wait("window.__r !== null")
    check("未保存でなければ、確認なしで別のフォルダーへ移り、文書を閉じる",
          (js("doc.path"), js("cm.getValue()"), js("files.join(',')")), (None, '', 'b.md'))
    check("ファイル名の表示は「無題」・変更なし", (js("document.getElementById('title').textContent"), js("isDirty()")), ('無題', False))
    check("一覧に選択中の行はない", js("document.querySelectorAll('#list .item.sel').length"), 0)

    # 未保存の変更があるとき: キャンセル → 移らない
    js(f"switchFolder({json.dumps(folder_a)}).then(() => openPath({json.dumps(doc_a)}))")
    wait("doc.path && doc.path.endsWith('a.md')")
    js("cm.replaceRange('追記\\n', {line: 0, ch: 0})")
    check("未保存の変更がある", js("isDirty()"), True)
    js(f"window.__r = null; switchFolder({json.dumps(folder_b)}).then(v => {{ window.__r = v; }})")
    check("保存を促す確認が出る", wait("document.getElementById('veil').classList.contains('show')"), True)
    check("確認の文言に文書名がある", 'a.md' in js("document.getElementById('dText').textContent"), True)
    click_dialog('キャンセル')
    wait("window.__r !== null")
    check("キャンセルすると、フォルダーも文書も、そのまま", (js("window.__r"), js("folder") == folder_a, js("doc.path") is not None, js("isDirty()")), (False, True, True, True))

    # 保存しない → 変更を捨てて移る
    js(f"window.__r = null; switchFolder({json.dumps(folder_b)}).then(v => {{ window.__r = v; }})")
    wait("document.getElementById('veil').classList.contains('show')")
    click_dialog('保存しない')
    wait("window.__r !== null")
    check("「保存しない」: 移って、文書は空白になる", (js("window.__r"), js("doc.path"), js("cm.getValue()"), js("files.join(',')")), (True, None, '', 'b.md'))
    check("「保存しない」: ファイルは書き換わっていない", open(doc_a, encoding='utf-8').read(), "# Aの文書\n\n本文\n")

    # 保存する → 保存してから移る
    js(f"switchFolder({json.dumps(folder_a)}).then(() => openPath({json.dumps(doc_a)}))")
    wait("doc.path && doc.path.endsWith('a.md')")
    js("cm.replaceRange('保存する追記\\n', {line: 0, ch: 0})")
    js(f"window.__r = null; switchFolder({json.dumps(folder_b)}).then(v => {{ window.__r = v; }})")
    wait("document.getElementById('veil').classList.contains('show')")
    click_dialog('保存する')
    wait("window.__r !== null")
    check("「保存する」: 保存してから移り、文書は空白になる",
          (js("window.__r"), js("doc.path"), js("cm.getValue()"), open(doc_a, encoding='utf-8').read().startswith('保存する追記')), (True, None, '', True))

    # 書きかけの「無題」も、保存を促す
    js("cm.setValue('書きかけ')")
    js(f"window.__r = null; switchFolder({json.dumps(folder_a)}).then(v => {{ window.__r = v; }})")
    check("書きかけの「無題」でも、保存を促す", wait("document.getElementById('veil').classList.contains('show')"), True)
    click_dialog('キャンセル')
    wait("window.__r !== null")
    check("キャンセルすると、書きかけは残る", (js("window.__r"), js("cm.getValue()")), (False, '書きかけ'))
    js("cm.setValue('')")

    # ---- 一覧が、時間か件数の上限で途中までのときの表示
    js("listTruncated = true; renderList()")
    check("一覧が途中までのとき、件数の行で知らせる", '途中までです' in js("document.getElementById('count').textContent"), True)
    check("途中までの知らせは、色でも目立たせる", js("document.getElementById('count').style.color") != '', True)
    js("listTruncated = false; renderList()")
    check("途中でなければ、知らせは出ない", '途中' in js("document.getElementById('count').textContent"), False)

    # ---- ツールバーの折り返し
    def toolbar():
        return json.loads(js("""(() => {
          const t = document.getElementById('toolbar');
          const btns = [...t.querySelectorAll('button')];
          const tops = [...new Set(btns.map(b => Math.round(b.getBoundingClientRect().top)))];
          return JSON.stringify({ maxBtnH: Math.max(...btns.map(b => b.getBoundingClientRect().height)), rows: tops.length,
                                  overflowX: t.scrollWidth > t.clientWidth + 1 });
        })()"""))
    for width in (700, 520, 380):
        w.resize(width, 800)
        time.sleep(1)
        r = toolbar()
        check(f"幅{width}px: ボタンが縦長にならない（高さ {r['maxBtnH']:.0f}px）", r['maxBtnH'] < 45, True)
        check(f"幅{width}px: ツールバーが横にはみ出さない（{r['rows']}行）", r['overflowX'], False)
    finish()


(drive_migration if SCENARIO in MIGRATION else drive)() if False else None
threading.Thread(target=drive_migration if SCENARIO in MIGRATION else drive, daemon=True).start()
webview.start()
