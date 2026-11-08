"""自動保存（下書き）と復元を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_autosave.py

設定の置き場所は一時フォルダーへ向ける（利用者の設定・下書きを書き換えない）。
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
import drafts
import mdeditor
import gui_nodialog  # noqa: F401  OS のダイアログを出さない（キー入力を奪うため）

work = tempfile.mkdtemp(prefix='md_work_')
real = os.path.join(work, 'real.md')
open(real, 'w', encoding='utf-8').write('元の内容\n')
# 前回の起動で残った下書き（無題 1 つと、ファイルの 1 つ）
root = mdeditor.drafts_root()
drafts.save_draft(root, None, '# 前回の無題\n本文', slot='untitledold', owner=[2_000_000_000, 1])
drafts.save_draft(root, real, '# 書きかけ\nファイルの下書き', 'UTF-8', 'LF', slot='untitledold', owner=[2_000_000_000, 1])

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


def previews():
    return sorted(d['preview'] for d in drafts.list_drafts(root))


def key(k, ctrl=False):
    js("document.dispatchEvent(new KeyboardEvent('keydown', {key: %s, ctrlKey: %s, bubbles: true, cancelable: true}))"
       % (json.dumps(k), 'true' if ctrl else 'false'))


def drive():
    time.sleep(8)
    wait("typeof safety !== 'undefined' && !document.getElementById('rveil').hidden", 20)

    # --- 起動したとき、前回の下書きを提案する
    check("起動時に、復元のダイアログが出る", js("!document.getElementById('rveil').hidden"), True)
    check("下書きが2件、並ぶ", js("document.querySelectorAll('#rList .rrow').length"), 2)
    check("ファイルの下書きには、ファイル名が出る", js("[...document.querySelectorAll('#rList .rname')].some(n => n.textContent.endsWith('real.md'))"), True)
    check("無題の下書きには、「無題」と出る", js("[...document.querySelectorAll('#rList .rname')].some(n => n.textContent.startsWith('無題'))"), True)
    check("冒頭の1行が見える", js("[...document.querySelectorAll('#rList .rprev')].map(p => p.textContent).sort().join('|')"), '# 前回の無題|# 書きかけ')
    key('n', True)
    time.sleep(.3)
    check("ダイアログが開いている間は、Ctrl+N を受けない（ダイアログは開いたまま）", js("document.getElementById('rveil').hidden"), False)

    # 「あとで」では、下書きを消さない
    js("document.getElementById('rLater').click()")
    check("「あとで」で閉じる", js("document.getElementById('rveil').hidden"), True)
    check("「あとで」では、下書きが残る", previews(), ['# 前回の無題', '# 書きかけ'])
    js("autosaveTick()")
    time.sleep(.8)
    check("編集していない間は、前回の下書きを消さない", previews(), ['# 前回の無題', '# 書きかけ'])

    # --- 復元
    js("offerRestore()")
    wait("!document.getElementById('rveil').hidden")
    js("[...document.querySelectorAll('#rList .rrow')].find(r => r.querySelector('.rname').textContent.startsWith('無題')).querySelector('button.primary').click()")
    check("復元すると、内容が編集欄に入る", wait("cm.getValue() === '# 前回の無題\\n本文'"), True)
    check("復元した内容は、保存していない状態", js("isDirty()"), True)
    check("ほかの下書きがあるので、ダイアログは出たまま", wait("!document.getElementById('rveil').hidden"), True)
    js("document.getElementById('rLater').click()")
    check("復元しただけでは、前回の下書きは消えない（保存するまで残す）", previews(), ['# 前回の無題', '# 書きかけ'])
    # 復元した内容は、次の下書きに引き継がれ、復元元は消える
    js("autosaveTick()")
    time.sleep(1.0)
    check("次の下書きを書くと、復元元は今回の分に置き換わる（重複しない）", previews(), ['# 前回の無題', '# 書きかけ'])
    check("下書きは 2 件のまま", len(drafts.list_drafts(root)), 2)
    check("復元元の名前（untitledold）は、もう無い", [d['key'] for d in drafts.list_drafts(root) if d['key'] == 'untitledold'], [])
    check("ファイルは書き換えられていない", open(real, encoding='utf-8').read(), '元の内容\n')

    # --- 下書きを書く
    js("cm.setValue('# 新しい内容\\n追記'); null")
    js("autosaveTick()")
    check("編集した内容が、下書きに書かれる", wait("safety.lastAt !== ''"), True)
    time.sleep(.6)
    check("下書きに、新しい内容が入る", '# 新しい内容' in previews(), True)
    n = len(drafts.list_drafts(root))
    js("autosaveTick()")
    time.sleep(.5)
    check("変更がなければ、書き直さない（件数は変わらない）", len(drafts.list_drafts(root)), n)

    # --- 保存すると、下書きが消える
    target = os.path.join(work, 'saved.md')
    js("saveTo(%s, null)" % json.dumps(target))
    check("保存できる", wait("!isDirty()"), True)
    time.sleep(.8)
    check("保存したあと、今回の下書きは無い（前回の未処理の1件だけ）", previews(), ['# 書きかけ'])
    check("保存したファイルの中身", open(target, encoding='utf-8').read().replace('\r\n', '\n'), '# 新しい内容\n追記')

    # --- 「保存しない」を選ぶと、下書きが消える
    js("cm.setValue('# 捨てる内容'); null")
    js("autosaveTick()")
    time.sleep(.8)
    check("編集すると、また下書きができる", '# 捨てる内容' in previews(), True)
    js("window._ask = ask; ask = async () => 1; confirmDiscard().then(v => { window._cd = v; ask = window._ask; })")
    wait("window._cd !== undefined")
    time.sleep(.5)
    check("「保存しない」を選ぶと、下書きも消える", '# 捨てる内容' in previews(), False)

    # --- 破棄
    js("window._ask = ask; ask = async () => 0; null")
    js("offerRestore()")
    wait("!document.getElementById('rveil').hidden")
    js("document.querySelector('#rList .rrow button:not(.primary)').click()")
    time.sleep(1.0)
    check("「破棄」で、その下書きが消える", previews(), [])
    check("下書きが無くなると、ダイアログも閉じる", js("document.getElementById('rveil').hidden"), True)
    js("ask = window._ask; null")

    # --- 保存の設定
    check("自動保存のボタンは「入」", js("document.getElementById('autoBtn').textContent.includes('入')"), True)
    js("document.getElementById('autoBtn').click()")
    check("ボタンで、設定のダイアログが開く", js("!document.getElementById('sveil').hidden"), True)
    check("既定: 自動保存が入・30秒・退避5件", js("[sAuto.checked, sInterval.value, sKeep.value]"), [True, '30', '5'])
    js("sKeep.value = '12'; sKeep.dispatchEvent(new Event('change'))")
    time.sleep(.6)
    check("退避の数を変えると、設定に残る", js("prefs.safety.keep"), 12)
    check("Python 側の設定にも入る", api.safety()['keep'], 12)
    js("sKeep.value = '0'; sKeep.dispatchEvent(new Event('change'))")
    check("範囲外（0）は受け付けず、元の値に戻す", js("[sKeep.value, !!sMsg.textContent]"), ['12', True])
    js("sInterval.value = '60'; sInterval.dispatchEvent(new Event('change'))")
    check("間隔を変えると、設定に残る", js("prefs.safety.interval"), 60)
    js("sAuto.click()")
    time.sleep(.5)
    check("自動保存を切ると、ボタンが「切」になる", js("document.getElementById('autoBtn').textContent.includes('切')"), True)
    check("切ると、間隔の欄が使えなくなる", js("sInterval.disabled"), True)
    check("切った設定が残る", api.safety()['autosave'], False)
    key('Escape')
    time.sleep(.3)
    check("Esc でダイアログが閉じる", js("document.getElementById('sveil').hidden"), True)
    js("document.getElementById('autoBtn').click()")
    js("sAuto.click()")
    time.sleep(.4)
    check("もう一度入れると、ボタンが「入」に戻る", js("document.getElementById('autoBtn').textContent.includes('入')"), True)
    js("document.getElementById('sClose').click()")

    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
