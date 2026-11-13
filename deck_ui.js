/* 発表（スライドショー）の画面側。ビューアとエディタで同じ内容を使う（ui.html の中に入る）。
   いま表示している文書（プレビュー）から、スライドの HTML を組み立て、Python（deck.py）に渡して、別ウィンドウで開く。
   実行部分（キー操作・拡大縮小・発表者ビューなど）は、deck.js。組み立てた HTML は、1つで完結するので、保存もできる。

   呼び出し側（ui.html）が、DECK_HOST を用意する:
     { docPath(): 文書のパス（無ければ null）, startLine(): 編集中の行（無ければ null）, say(text): 画面に知らせる,
       hasDocument(): 文書があるか, refresh(): 発表の前に、プレビューを最新にする（async）, appName: 'Editor' | 'Viewer' }
   ほかに、ui.html の次のものを使う: api, EXPORT_ROOT, settleRender, printBeforeDiagrams, collectExportCss, escHtml, ask。 */

const deckState = { busy: false };

// ---- 文書をスライドに分ける。区切りは、水平線（---）。脚注の区切り線（footnotes-sep）は、区切りではない
function deckLineOf(el) {
  const v = el && el.getAttribute && el.getAttribute('data-line');
  return v === null || v === undefined || v === '' ? null : parseInt(v, 10);
}
function splitSlides(root) {
  const out = [];
  let cur = { nodes: [], classes: [], notes: [], first: null };
  let footnotes = null;
  const flush = () => { if (cur.nodes.length) out.push(cur); cur = { nodes: [], classes: [], notes: [], first: null }; };
  for (const el of [...root.children]) {
    const cls = el.classList;
    if (el.tagName === 'HR' && cls.contains('footnotes-sep')) continue;
    if (cls.contains('footnotes')) { footnotes = el; continue; }
    if (el.tagName === 'HR') { flush(); cur.first = deckLineOf(el); continue; }
    if (cls.contains('slide-directive')) { cur.classes.push(...[...cls].filter(c => /^sd-[a-z0-9_-]+$/.test(c))); continue; }
    if (cls.contains('slide-note')) { cur.notes.push(el.innerHTML); continue; }
    if (cur.first === null) cur.first = deckLineOf(el);
    cur.nodes.push(el);
  }
  flush();
  if (footnotes) {
    const h = document.createElement('h2'); h.textContent = '脚注';
    out.push({ nodes: [h, footnotes], classes: ['sd-footnotes'], notes: [], first: null });
  }
  return out;
}
// 編集中の行にあたるスライドの番号（0 から）。分からなければ 0
function slideIndexForLine(slides, line) {
  if (line === null || line === undefined) return 0;
  let best = 0;
  slides.forEach((s, i) => { if (s.first !== null && s.first <= line) best = i; });
  return best;
}

function deckAttr(s) { return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;'); }
function deckJson(o) { return JSON.stringify(o).replace(/</g, String.fromCharCode(92) + 'u003c').split(String.fromCharCode(0x2028)).join(String.fromCharCode(92) + 'u2028').split(String.fromCharCode(0x2029)).join(String.fromCharCode(92) + 'u2029'); }

// ---- スライドの HTML を組み立てる（1つで完結する）。役割（聴衆・発表者・単独）は、あとで Python か保存時に入れる
async function buildDeckHtml(opts) {
  const root = document.querySelector(EXPORT_ROOT);
  const clone = root.cloneNode(true), warnings = [];
  clone.querySelectorAll('mark.find-hit').forEach(m => m.replaceWith(document.createTextNode(m.textContent)));
  const slides = splitSlides(clone);
  clone.querySelectorAll('[data-src]').forEach(e => e.removeAttribute('data-src'));
  clone.querySelectorAll('.diagram').forEach(e => { e.style.minHeight = ''; if (!e.getAttribute('style')) e.removeAttribute('style'); });
  slides.forEach(s => s.nodes.forEach(n => { if (n.removeAttribute) n.removeAttribute('data-line'); if (n.querySelectorAll) n.querySelectorAll('[data-line]').forEach(e => e.removeAttribute('data-line')); }));
  if (clone.querySelector('.diagram-error, .math-error')) warnings.push('描けなかった図・グラフ・数式があります（エラーの表示のまま入ります）');
  const lost = [...clone.querySelectorAll('img')].map(i => i.getAttribute('src') || '').filter(s => s && !/^(data:|https?:)/i.test(s));
  if (lost.length) warnings.push('画像を埋め込めませんでした（相対パスのまま）: ' + lost.slice(0, 3).join('、') + (lost.length > 3 ? ' ほか' : ''));
  if (!slides.length) return { html: null, warnings: ['スライドにする内容がありません'], count: 0, start: 0 };
  const hasKatex = !!clone.querySelector('.katex');                     // スライドへ要素を移すと、clone は空になるので、先に調べる
  const start = opts.fromCursor ? slideIndexForLine(slides, DECK_HOST.startLine()) : 0;
  const body = slides.map(s => {
    const notes = s.notes.length ? '<aside class="slide-note">' + s.notes.join('<br>\n') + '</aside>' : '';
    const wrap = document.createElement('div');
    s.nodes.forEach(n => wrap.appendChild(n));
    return '<section class="slide' + s.classes.map(c => ' ' + c).join('') + '"><div class="md-body">' + wrap.innerHTML + '</div>' + notes + '</section>';
  }).join('\n');
  const katexCss = hasKatex ? (await api.get_katex()).css : '';
  const assets = opts.assets;
  const themeCss = await api.deck_theme_css(opts.theme, DECK_HOST.docPath());
  const title = opts.title || '発表';
  const html = '<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    + '<meta name="generator" content="Handy Markdown ' + DECK_HOST.appName + ' v__APP_VERSION__">\n<title>' + escHtml(title) + '</title>\n<style>\n'
    + assets.css + '\n' + collectExportCss() + '\n' + katexCss + '\n/* テーマ */\n' + themeCss + '\n</style>\n</head>\n<body>\n'
    + '<div id="stage"><div id="scaler">\n' + body + '\n</div></div>\n'
    + '<div id="hud"><i id="hudbar"></i></div><div id="toast"></div><div id="screen"></div><div id="laser"></div><div id="help"></div><div id="overview"></div><div id="presenter"></div><div id="printroot"></div>\n'
    + '<script>window.DECK = {role: "__DECK_ROLE__", t0: "__DECK_T0__", ratio: ' + deckJson(opts.ratio) + ', laser: ' + (parseInt(opts.laser, 10) || 30) + ', start: ' + start + ', title: ' + deckJson(title) + '};<\/script>\n'
    + '<script>\n' + assets.js.replace(/<\/script/gi, '<\\/script') + '\n<\/script>\n</body>\n</html>\n';
  return { html, warnings, count: slides.length, start };
}

// 描き終えるのを待ち、図を明るい配色にしてから、スライドを組み立てる
async function deckBuild(opts) {
  await DECK_HOST.refresh();
  await settleRender();
  const restore = await printBeforeDiagrams();
  try { return await buildDeckHtml(opts); } finally { if (restore) await restore(); }
}

function deckTitle() {
  const h = document.querySelector(EXPORT_ROOT + ' h1');
  const p = DECK_HOST.docPath();
  return (h && h.textContent.trim()) || (p ? p.substring(p.lastIndexOf('\\') + 1).replace(/\.[^.]*$/, '') : '発表');
}

// ---- 「発表」のダイアログ
function deckCountSlides() {
  const root = document.querySelector(EXPORT_ROOT); if (!root) return 0;
  return splitSlides(root.cloneNode(true)).length;
}
function deckForm(info, prefs, canCursor) {
  const box = document.createElement('div'); box.className = 'deckform';
  box.style.cssText = 'display:grid;grid-template-columns:auto 1fr;gap:8px 12px;align-items:center;text-align:left;margin-top:8px';
  const row = (label, el) => { const l = document.createElement('label'); l.textContent = label; box.appendChild(l); box.appendChild(el); return el; };
  const sel = (id, opts, val) => { const s = document.createElement('select'); s.id = id; opts.forEach(([v, t]) => { const o = new Option(t, v); s.appendChild(o); }); if (val !== undefined) s.value = String(val); return s; };
  const screens = info.screens || [];
  const sOpts = screens.length ? screens.map(s => [String(s.index), '画面 ' + (s.index + 1) + '（' + s.width + '×' + s.height + (s.primary ? '・主' : '') + '）']) : [['-1', '（モニターを調べられません）']];
  const defScreen = Number.isInteger(prefs.screen) && screens.some(s => s.index === prefs.screen) ? prefs.screen : (info.defaults ? info.defaults.audience : -1);
  row('発表を出す画面', sel('dkScreen', sOpts, defScreen));
  const themes = info.themes.map(t => [t.id, t.name + (t.source !== '組み込み' ? '（' + t.source + '）' : '')]);
  row('デザイン（テーマ）', sel('dkTheme', themes, prefs.theme && themes.some(t => t[0] === prefs.theme) ? prefs.theme : 'light'));
  row('画面の比率', sel('dkRatio', [['16:9', '16:9（フル HD など）'], ['16:10', '16:10'], ['4:3', '4:3（古いプロジェクター）'], ['auto', '画面に合わせる']], prefs.ratio || '16:9'));
  const startOpts = [['top', '最初のスライドから']]; if (canCursor) startOpts.push(['cursor', '編集中の位置のスライドから']);
  row('開始', sel('dkStart', startOpts, 'top'));
  const lsOpts = [['18', '小'], ['30', '中'], ['48', '大'], ['72', '特大']];
  const lsVal = Number.isInteger(prefs.laser) ? prefs.laser : 30;
  if (!lsOpts.some(o => o[0] === String(lsVal))) lsOpts.push([String(lsVal), '前回の大きさ']);
  row('レーザーポインターの大きさ', sel('dkLaser', lsOpts, lsVal));
  const lab = document.createElement('label'); lab.style.cssText = 'grid-column:1 / 3;display:flex;gap:8px;align-items:center';
  const cb = document.createElement('input'); cb.type = 'checkbox'; cb.id = 'dkPresenter';
  cb.checked = typeof prefs.presenter === 'boolean' ? prefs.presenter : screens.length >= 2;
  lab.appendChild(cb); lab.appendChild(document.createTextNode('手元の画面に発表者ビュー（次のスライド・ノート・タイマー）を開く'));
  box.appendChild(lab);
  return box;
}

// 組み立てたスライドを、画面の外の枠で一度動かし、1 枚に収まらないスライドを調べる
async function deckMeasure(html) {
  const f = document.createElement('iframe');
  f.style.cssText = 'position:fixed;left:-20000px;top:0;width:1280px;height:720px;border:0;visibility:hidden';
  f.srcdoc = html.replace('"__DECK_ROLE__"', '"standalone"');
  document.body.appendChild(f);
  try {
    await new Promise(res => { f.onload = res; setTimeout(res, 8000); });
    await new Promise(r => setTimeout(r, 400));
    const D = f.contentWindow && f.contentWindow.Deck;
    return D ? { over: D.overflow(), shrunk: D.shrunk() } : null;
  } catch (e) { return null; } finally { f.remove(); }
}
function deckMeasureText(m) {
  const out = [];
  if (m && m.over.length) out.push('収まらないスライド: ' + m.over.join('、') + '（内容を減らすか、分けてください）');
  if (m && m.shrunk.length) out.push('縮小して収めるスライド: ' + m.shrunk.join('、'));
  return out;
}

async function startPresentation() {
  if (deckState.busy) return;
  if (!DECK_HOST.hasDocument()) { DECK_HOST.say('先に、文書を開いてください'); return; }
  deckState.busy = true;
  try {
    for (;;) {
      const info = await api.deck_prepare(DECK_HOST.docPath());
      const prefs = ((await api.get_prefs()) || {}).deck || {};
      await DECK_HOST.refresh();
      const n = deckCountSlides();
      const canCursor = DECK_HOST.startLine() !== null;
      const form = deckForm(info, prefs, canCursor);
      const text = (n <= 1 ? '区切り（---）が無いので、スライドは 1 枚になります。' : 'スライドは ' + n + ' 枚です（水平線 --- で区切っています）。')
        + '\n発表中は、? キーで操作の一覧が出ます。';
      const i = await ask('発表（スライドショー）', text,
        [{ label: '発表を始める', primary: true }, { label: '保存（PDF・HTML）…' }, { label: 'テーマの見本を作る' }, { label: 'キャンセル' }], form);
      const val = id => document.getElementById(id) ? document.getElementById(id).value : '';
      const opts = { theme: val('dkTheme') || 'light', ratio: val('dkRatio') || '16:9', fromCursor: val('dkStart') === 'cursor',
        screen: parseInt(val('dkScreen'), 10), presenter: !!(document.getElementById('dkPresenter') || {}).checked, assets: info.assets, title: deckTitle(), laser: parseInt(val('dkLaser'), 10) || 30 };
      if (i === 3 || i < 0) return;
      // 選んだ内容は、次回の初期値にする
      api.set_prefs({ deck: { theme: opts.theme, ratio: opts.ratio, presenter: opts.presenter, screen: Number.isInteger(opts.screen) ? opts.screen : -1, laser: opts.laser } });
      if (i === 2) {
        const r = await api.deck_make_theme(DECK_HOST.docPath());
        if (r.error) DECK_HOST.say(r.error);
        else await ask('テーマの見本を作りました', r.path + '\n\nこのファイルを編集すると、「デザイン（テーマ）」の一覧に、ファイル名で出ます。', [{ label: '閉じる', primary: true }]);
        continue;                                               // 一覧に出るよう、ダイアログを開き直す
      }
      let kind = null;
      if (i === 1) {
        const k = await ask('スライドを保存する', 'どの形で保存しますか。',
          [{ label: 'スライドの PDF（1 枚 1 ページ）', primary: true }, { label: '配布資料の PDF（ノート付き）' }, { label: 'HTML スライドショー' }, { label: '戻る' }]);
        if (k === 3 || k < 0) continue;
        kind = ['slides', 'handout', 'html'][k];
      }
      const built = await deckBuild(opts);
      if (!built.html) { DECK_HOST.say(built.warnings[0]); return; }
      const measured = deckMeasureText(await deckMeasure(built.html));
      const notes = measured.concat(built.warnings);
      if (kind === 'html') { await deckSaveHtml(built, notes); return; }
      if (kind) { await deckSavePdf(built, kind, notes); return; }
      const r = await api.deck_open(built.html, { screen: opts.screen, presenter: opts.presenter, title: opts.title });
      if (r.error) { DECK_HOST.say(r.error); return; }
      if (notes.length) DECK_HOST.say('※ ' + notes.join(' ※ '));
      return;
    }
  } finally { deckState.busy = false; }
}

function deckBaseName() {
  const p = DECK_HOST.docPath();
  return p ? p.substring(p.lastIndexOf('\\') + 1).replace(/\.[^.]*$/, '') : '無題';
}
function deckDirName() { const p = DECK_HOST.docPath(); return p ? p.substring(0, p.lastIndexOf('\\')) : null; }

// 1つで完結する HTML のスライドショーとして保存する（ブラウザーだけで発表できる。F で全画面、? で操作の一覧）
async function deckSaveHtml(built, notes) {
  const html = built.html.replace('"__DECK_ROLE__"', '"standalone"');
  const path = await api.pick_html_path(deckBaseName() + '-スライド.html', deckDirName());
  if (!path) return;
  const r = await api.save_html(path, html);
  if (r.error) { DECK_HOST.say(r.error); return; }
  const warn = notes && notes.length ? '\n\n※ ' + notes.join('\n※ ') : '';
  const i = await ask('HTML スライドを保存しました', r.path + '\n（' + Math.round(r.bytes / 1024).toLocaleString() + ' KB。アプリが無くても、ブラウザーで開いて発表できます。F で全画面、? で操作の一覧）' + warn,
    [{ label: 'ブラウザーで開く', primary: true }, { label: '閉じる' }]);
  if (i === 0) { const o = await api.open_exported_html(r.path); if (o.error) DECK_HOST.say(o.error); }
}

// スライド（1 枚 1 ページ。ページの大きさはスライドの大きさ）か、配布資料（A4 縦。スライドとノート）の PDF として保存する
async function deckSavePdf(built, kind, notes) {
  const path = await api.pick_pdf_path(deckBaseName() + (kind === 'handout' ? '-配布資料.pdf' : '-スライド.pdf'), deckDirName());
  if (!path) return;
  DECK_HOST.say('PDF を作っています…');
  const r = await api.deck_export_pdf(built.html, kind, path);
  if (r.error) { DECK_HOST.say(r.error); return; }
  const warn = notes && notes.length ? '\n\n※ ' + notes.join('\n※ ') : '';
  await ask('PDF を保存しました', r.path + '\n（' + r.pages + ' ページ。' + (kind === 'handout' ? 'A4 縦に、スライドとノートを並べています' : '1 ページが、スライド 1 枚です') + '）' + warn,
    [{ label: '閉じる', primary: true }]);
}
