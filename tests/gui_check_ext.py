"""脚注・Qiita の注釈ブロック・GitHub のアラート・コードブロックのファイル名を、実際の画面で確かめる（エディタ用）。

    .venv\\Scripts\\python tests\\gui_check_ext.py

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
DOC = os.path.join(tmp, 'ext.md')
open(DOC, 'w', encoding='utf-8').write("# 拡張の表示\n\n本文に脚注を付けます[^1]。\n\n"
    + "余白の行です。\n\n" * 60
    + """:::note info
情報です **強調**
:::

:::note warn
警告です
:::

:::note alert
注意です
:::

> [!NOTE]
> GitHub のノートです。

> [!CAUTION]
> 危険です。

```ruby:app.rb
puts "hello"
```

```diff_ruby
- puts "a"
+ puts "b"
```

[^1]: 脚注の本文です。
""")

api = mdeditor.Api(None)
w = webview.create_window('t', html=mdeditor.build_html(), js_api=api, width=1400, height=900, x=20, y=20)
api._window = w
results = []
ROOT = '#preview'
OPEN = 'openPath'


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


def q(sel):
    return ROOT + ' ' + sel


def drive():
    time.sleep(8)
    js("document.getElementById('vPrev').click()")
    js("%s(%s)" % (OPEN, json.dumps(DOC)))
    check("文書が開いて、描かれる", wait("document.querySelector(%s) !== null" % json.dumps(q('.md-note'))), True)
    time.sleep(.8)

    check("脚注: 本文に上付きの番号が付く", js("(() => { const a = document.querySelector(%s); return a ? [a.textContent, a.getAttribute('href')] : null; })()" % json.dumps(q('sup.footnote-ref a'))), ['1', '#fn1'])
    check("脚注: 文末に一覧が出て、中身が残っている", js("document.querySelector(%s).textContent.includes('脚注の本文です')" % json.dumps(q('.footnotes'))), True)
    js("document.getElementById('pscroll').scrollTop = 0")
    time.sleep(.3)
    js("document.querySelector(%s).click()" % json.dumps(q('sup.footnote-ref a')))
    time.sleep(.8)
    check("脚注: 番号を押すと、文末の脚注へ移る", js("document.getElementById('pscroll').scrollTop > 400"), True)
    js("document.querySelector(%s).click()" % json.dumps(q('.footnote-backref')))
    time.sleep(.8)
    check("脚注: 戻りのリンクで、本文へ戻る", js("document.getElementById('pscroll').scrollTop < 400"), True)

    check("Qiita の注釈ブロック: 3種類が、色つきの箱になる",
          js("[...document.querySelectorAll(%s)].map(e => e.className + ':' + (getComputedStyle(e).backgroundColor !== 'rgba(0, 0, 0, 0)'))" % json.dumps(q('.md-note'))),
          ['md-note md-note-info:true', 'md-note md-note-warn:true', 'md-note md-note-alert:true'])
    check("Qiita の注釈ブロック: 3種類の色が違う", js("new Set([...document.querySelectorAll(%s)].map(e => getComputedStyle(e).backgroundColor)).size" % json.dumps(q('.md-note'))), 3)
    check("Qiita の注釈ブロック: 中身が Markdown として変換される", js("document.querySelector(%s).innerHTML.includes('<strong>強調</strong>')" % json.dumps(q('.md-note-info'))), True)

    check("GitHub のアラート: 見出しが付き、印の文字は消える",
          js("[...document.querySelectorAll(%s)].map(e => e.querySelector('.md-alert-title').textContent + '/' + e.textContent.includes('[!'))" % json.dumps(q('blockquote.md-alert'))),
          ['Note/false', 'Caution/false'])
    check("GitHub のアラート: 種類ごとに左の線の色が違う",
          js("new Set([...document.querySelectorAll(%s)].map(e => getComputedStyle(e).borderLeftColor)).size" % json.dumps(q('blockquote.md-alert'))), 2)

    check("コードブロック: ファイル名が上に出る", js("(() => { const f = document.querySelector(%s); return f ? [f.textContent, f.nextElementSibling.tagName] : null; })()" % json.dumps(q('.code-filename'))), ['app.rb', 'PRE'])
    check("コードブロック: 色分けも効く", js("document.querySelector(%s) !== null" % json.dumps(q('.code-filename + pre code.language-ruby .tok-nb'))), True)
    check("コードブロック: diff_ruby は、追加と削除に色が付く", js("[...document.querySelectorAll(%s)].map(e => e.className)" % json.dumps(q('code.language-diff span:not(.tok-w)'))), ['tok-gd', 'tok-gi'])

    # --- HTML への書き出しにも、見た目が入る
    html = js("window.__h = null; buildExportHtml('t').then(h => { window.__h = h; }); null")
    wait("window.__h !== null", 30)
    h = js("window.__h.html")
    for needle, name in (('.md-body .md-note-info', '注釈ブロックの色'), ('.md-body blockquote.md-alert', 'アラートの色'),
                         ('.md-body .code-filename', 'ファイル名の見出し'), ('.md-body sup.footnote-ref', '脚注の番号')):
        check("HTML 書き出し: %s のスタイルが入る" % name, needle in h, True)
    check("HTML 書き出し: 脚注・注釈の本文が入る", all(t in h for t in ('脚注の本文です', '情報です', 'GitHub のノートです')), True)

    # --- 編集欄で、書き換えると、描き直される
    js("cm.setValue(':::note warn\\n書き換え後\\n:::\\n')")
    check("編集すると、注釈ブロックが描き直される", wait("document.querySelectorAll(%s).length === 1 && document.querySelector(%s).textContent.includes('書き換え後')" % (json.dumps(q('.md-note-warn')), json.dumps(q('.md-note-warn')))), True)

    print("RESULT", sum(results), "/", len(results), flush=True)
    api._dirty = False
    api._closing = True
    os._exit(0)


threading.Thread(target=drive, daemon=True).start()
webview.start()
