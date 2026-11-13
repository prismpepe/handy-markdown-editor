/* 発表（スライドショー）の実行部分。1つで完結する HTML（deck_ui.js が組み立てる）の中に入る。
   アプリの別ウィンドウでも、保存した HTML をブラウザーで開いたときでも、同じものが動く。
   window.DECK = { role: 'audience' | 'presenter' | 'standalone', ratio, start, title } は、組み立てた HTML の側が渡す。 */
(function () {
  'use strict';
  const cfg = window.DECK || {};
  const role = cfg.role || 'standalone';
  const RATIOS = [['16:9', 16 / 9], ['16:10', 16 / 10], ['4:3', 4 / 3], ['auto', 0]];
  const RATIO_NAME = { '16:9': '16:9', '16:10': '16:10', '4:3': '4:3', auto: '画面に合わせる' };
  const H = 720;
  const $ = id => document.getElementById(id);
  const slides = [...document.querySelectorAll('#scaler > .slide')];
  let idx = Math.min(Math.max(0, cfg.start | 0), Math.max(0, slides.length - 1));
  let ratioKey = RATIOS.some(r => r[0] === cfg.ratio) ? cfg.ratio : '16:9';
  let W = 1280, scale = 1, black = '', laserOn = false, zoomOn = false, zoomK = 2, ptr = { x: 0, y: 0 };
  let overviewOn = false, sel = 0, numBuf = '', startTime = Number(cfg.t0) || Date.now(), noteSize = 22, lastWheel = 0, idleTimer = null;      // 経過時間は、発表を始めたとき（Python が決める。2 つのウィンドウで同じ）から数える
  const sync = () => { if (role !== 'standalone' && window.pywebview && window.pywebview.api && window.pywebview.api.sync) window.pywebview.api.sync(JSON.stringify({ i: idx, black: black, ratio: ratioKey })); };

  // 一部の項目だけを、もう片方のウィンドウへ送る（レーザーの位置など）
  const send = obj => { if (role !== 'standalone' && window.pywebview && window.pywebview.api && window.pywebview.api.sync) window.pywebview.api.sync(JSON.stringify(obj)); };
  // スライド上の位置（0〜1）を、窓の座標（px）にする。聴衆の画面で、レーザーや拡大の位置に使う
  function slideToViewport(u, v) {
    const vw = innerWidth, vh = innerHeight, sc = Math.min(vw / W, vh / H);
    return { x: (vw - W * sc) / 2 + u * W * sc, y: (vh - H * sc) / 2 + v * H * sc };
  }
  let lastPtrSend = 0;
  // 発表者ビューで、「いまのスライド」の上のマウスの位置を、聴衆の画面へ送る（レーザー・部分拡大が入っているとき）
  function pointerToAudience(e) {
    const now = Date.now(); if (now - lastPtrSend < 40) return; lastPtrSend = now;
    const inner = document.querySelector('#presenter .cur-pane .inner'); if (!inner) return;
    const r = inner.getBoundingClientRect();
    let u = (e.clientX - r.left) / r.width, v = (e.clientY - r.top) / r.height;
    if (!(u >= 0 && u <= 1 && v >= 0 && v <= 1)) { u = null; v = null; }                  // スライドの外では、聴衆の画面の点を消す
    send({ u: u, v: v });
  }

  function toast(text) {
    const t = $('toast'); t.textContent = text; t.classList.add('on');
    clearTimeout(toast.h); toast.h = setTimeout(() => t.classList.remove('on'), 1600);
  }
  const ratioValue = () => ratioKey === 'auto' ? innerWidth / Math.max(1, innerHeight) : RATIOS.find(r => r[0] === ratioKey)[1];

  // ---- 大きさ: スライドは固定の大きさで組み、画面に収まるように拡大・縮小する
  function applyTransform() {
    const vw = innerWidth, vh = innerHeight;
    scale = Math.min(vw / W, vh / H);
    const tx = (vw - W * scale) / 2, ty = (vh - H * scale) / 2;
    const el = $('scaler');
    if (zoomOn) {
      const k = zoomK;
      el.style.transform = 'translate(' + (k * (tx - ptr.x) + ptr.x) + 'px,' + (k * (ty - ptr.y) + ptr.y) + 'px) scale(' + (k * scale) + ')';
    } else {
      el.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + scale + ')';
    }
  }
  function layout() {
    W = Math.round(H * ratioValue());
    document.documentElement.style.setProperty('--slide-w', W + 'px');
    applyTransform();
    if (role === 'presenter') renderPresenter();
    if (overviewOn) buildOverview();
  }

  // ---- 1枚に収まらないスライドは、中身を縮める（最小 50%）。それでも収まらなければ、印を付ける
  function fit(sl) {
    const body = sl.firstElementChild;
    if (!body || !body.classList.contains('md-body')) return;
    body.style.transform = ''; body.style.width = '';
    delete sl.dataset.fit; delete sl.dataset.over;
    sl.classList.add('measuring');
    const cs = getComputedStyle(sl);
    const avail = H - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
    if (body.offsetHeight > avail + 1) {
      let lo = 0.5, hi = 1, best = 0;
      for (let k = 0; k < 8; k++) {
        const f = (lo + hi) / 2;
        body.style.width = (100 / f) + '%'; body.style.transform = 'scale(' + f + ')';
        if (body.offsetHeight * f <= avail) { best = f; lo = f; } else hi = f;
      }
      if (best) { body.style.width = (100 / best) + '%'; body.style.transform = 'scale(' + best + ')'; sl.dataset.fit = best.toFixed(2); }
      else { body.style.width = '200%'; body.style.transform = 'scale(0.5)'; sl.dataset.fit = '0.50'; sl.dataset.over = '1'; }
    }
    sl.classList.remove('measuring');
  }
  function fitAll() {
    slides.forEach(fit);
    if (overviewOn) buildOverview();
    if (role === 'presenter') renderPresenter();
  }
  const overflowList = () => slides.map((s, i) => s.dataset.over ? i + 1 : 0).filter(Boolean);
  const shrunkList = () => slides.map((s, i) => s.dataset.fit && !s.dataset.over ? i + 1 : 0).filter(Boolean);

  // ---- 表示
  function show(i, remote) {
    if (!slides.length) return;
    i = Math.min(Math.max(0, i), slides.length - 1);
    slides[idx].classList.remove('cur'); idx = i; slides[idx].classList.add('cur');
    $('hudbar').style.width = (slides.length > 1 ? idx / (slides.length - 1) * 100 : 100) + '%';
    if (role === 'presenter') renderPresenter();
    if (!remote) sync();
  }
  const next = () => show(idx + 1);
  const prev = () => show(idx - 1);
  function setScreen(kind, remote) {
    black = kind || '';
    $('screen').className = black ? black : '';
    const pb = $('pblack'); if (pb) { pb.textContent = black ? '暗転を解除' : '暗転'; pb.classList.toggle('on', !!black); }
    if (!remote) sync();
  }

  // ---- スライド一覧（G）
  function cloneSlide(src) {
    const c = src.cloneNode(true); c.classList.remove('cur', 'measuring'); c.classList.add('show'); c.removeAttribute('id'); return c;
  }
  function buildOverview() {
    const box = $('overview'); box.textContent = '';
    const grid = document.createElement('div'); grid.className = 'grid';
    const tw = Math.max(200, Math.min(340, Math.floor((innerWidth - 80) / Math.ceil(innerWidth / 360))));
    grid.style.setProperty('--thumb-w', tw + 'px');
    const s = tw / W;
    slides.forEach((sl, i) => {
      const t = document.createElement('div'); t.className = 'thumb' + (i === sel ? ' sel' : ''); t.style.width = tw + 'px'; t.style.height = Math.round(H * s) + 'px';
      const inner = document.createElement('div'); inner.className = 'inner'; inner.style.width = W + 'px'; inner.style.height = H + 'px'; inner.style.transform = 'scale(' + s + ')';
      inner.appendChild(cloneSlide(sl)); t.appendChild(inner);
      const no = document.createElement('span'); no.className = 'no'; no.textContent = String(i + 1); t.appendChild(no);
      if (sl.dataset.over) { const w = document.createElement('span'); w.className = 'warn'; w.textContent = '収まらない'; t.appendChild(w); }
      else if (sl.dataset.fit) { const w = document.createElement('span'); w.className = 'warn shrunk'; w.textContent = '縮小 ' + Math.round(parseFloat(sl.dataset.fit) * 100) + '%'; t.appendChild(w); }
      t.onclick = () => { closeOverview(); show(i); };
      grid.appendChild(t);
    });
    box.appendChild(grid);
    const cur = grid.children[sel]; if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: 'nearest' });
  }
  function openOverview() { overviewOn = true; sel = idx; $('overview').classList.add('on'); buildOverview(); }
  function closeOverview() { overviewOn = false; $('overview').classList.remove('on'); }
  function moveSel(d) {
    const grid = $('overview').firstChild; if (!grid) return;
    let n = sel + d; n = Math.min(Math.max(0, n), slides.length - 1); sel = n;
    [...grid.children].forEach((c, i) => c.classList.toggle('sel', i === sel));
    grid.children[sel].scrollIntoView({ block: 'nearest' });
  }
  function colsOfGrid() {
    const g = $('overview').firstChild; if (!g || g.children.length < 2) return 1;
    const top = g.children[0].offsetTop; let n = 0; for (const c of g.children) { if (c.offsetTop === top) n++; else break; } return Math.max(1, n);
  }

  // ---- 発表者ビュー（手元の画面）
  // 発表者ビューの下に出す、キー操作のメモ（キーは、この画面でも、聴衆の画面でも使える。L・Z は、マウスのある画面で働く）
  const PRESENTER_HINT = '<b>→</b>次　<b>←</b>前　<b>数字+Enter</b>そのスライドへ　<b>G</b>スライド一覧　<b>B</b>暗転　<b>W</b>白画面　<b>R</b>画面の比率（聴衆の画面も切替）　<b>F</b>全画面　<b>?</b>操作の一覧'
    + '<br><span class="sub"><b>L</b>レーザーポインター・<b>Z</b>部分拡大: 入れたあと、手元の「いまのスライド」の上でマウスを動かすと、聴衆の画面に出ます（ホイールで拡大の倍率）</span>';
  function buildPresenter() {
    const p = $('presenter');
    p.innerHTML = '<div class="pane cur-pane"><span class="label">いまのスライド</span><div class="inner"></div></div>'
      + '<div class="side"><div class="pane next-pane"><span class="label">次のスライド</span><div class="inner"></div></div><div class="notes empty"></div></div>'
      + '<div class="bar"><span class="big" id="pcount"></span><span class="big" id="pelapsed">00:00</span><span id="pclock"></span><span class="grow warnline" id="pwarn"></span>'
      + '<button id="pprev">◀ 前へ</button><button id="pnext">次へ ▶</button><button id="pblack">暗転</button><button id="ptimer">タイマーを戻す</button><button id="pnoteminus">ノート −</button><button id="pnoteplus">ノート ＋</button></div>'
      + '<div class="hint" id="phint">' + PRESENTER_HINT + '</div>';
    $('pprev').onclick = prev; $('pnext').onclick = next;
    $('pblack').onclick = () => setScreen(black ? '' : 'black');
    $('ptimer').onclick = () => { startTime = Date.now(); tick(); };
    $('pnoteminus').onclick = () => { noteSize = Math.max(12, noteSize - 2); p.style.setProperty('--note-size', noteSize + 'px'); };
    $('pnoteplus').onclick = () => { noteSize = Math.min(60, noteSize + 2); p.style.setProperty('--note-size', noteSize + 'px'); };
  }
  function placeClone(pane, sl) {
    const inner = pane.querySelector('.inner'); inner.textContent = '';
    if (!sl) { inner.style.transform = ''; inner.style.width = inner.style.height = ''; inner.textContent = ''; const e = document.createElement('div'); e.style.cssText = 'color:#6e7681;padding:24px;font-size:18px'; e.textContent = '（最後のスライドです）'; inner.appendChild(e); return; }
    inner.style.width = W + 'px'; inner.style.height = H + 'px';
    inner.appendChild(cloneSlide(sl));
    const s = Math.min(pane.clientWidth / W, pane.clientHeight / H);
    inner.style.transform = 'translate(' + ((pane.clientWidth - W * s) / 2) + 'px,' + ((pane.clientHeight - H * s) / 2) + 'px) scale(' + s + ')';
  }
  function renderPresenter() {
    const p = $('presenter'); if (!p.firstChild) buildPresenter();
    placeClone(p.querySelector('.cur-pane'), slides[idx]);
    placeClone(p.querySelector('.next-pane'), slides[idx + 1]);
    const n = slides[idx] && slides[idx].querySelector('.slide-note');
    const box = p.querySelector('.notes'); box.classList.toggle('empty', !n); box.innerHTML = n ? n.innerHTML : '（ノートはありません）';
    $('pcount').textContent = (idx + 1) + ' / ' + slides.length;
    const o = overflowList(); $('pwarn').textContent = o.length ? '収まらないスライド: ' + o.join('、') : '';
  }
  function pad(n) { return String(n).padStart(2, '0'); }
  function tick() {
    if (role !== 'presenter') return;
    const now = new Date(); const c = $('pclock'); if (c) c.textContent = pad(now.getHours()) + ':' + pad(now.getMinutes());
    const e = $('pelapsed'); if (!e) return;
    const sec = Math.max(0, Math.floor((Date.now() - startTime) / 1000));
    e.textContent = pad(Math.floor(sec / 60)) + ':' + pad(sec % 60);
  }

  // ---- 印刷・PDF（スライド: 1 スライド 1 ページ、配布資料: A4 縦にスライドとノート）
  // preparePrint は、印刷用の紙面を組む（印刷の実行は、呼び出し側）。紙面の大きさ（px）を返す。endPrint で片付ける
  function preparePrint(handout) {
    endPrint();
    const root = $('printroot');
    const st = document.createElement('style'); st.id = 'pagestyle';
    let w, h;
    if (handout) {
      const pw = 700, s = pw / W; w = 794; h = 1123;                         // A4 縦（96dpi で 794×1123）。余白は 12mm
      st.textContent = '@page { size: A4 portrait; margin: 12mm; }';
      slides.forEach((sl, i) => {
        const page = document.createElement('div'); page.className = 'page'; page.style.width = pw + 'px'; page.style.height = '1020px';
        const inner = document.createElement('div'); inner.style.cssText = 'position:absolute;left:0;top:0;transform-origin:0 0;width:' + W + 'px;height:' + H + 'px;transform:scale(' + s + ');outline:1px solid #888';
        inner.appendChild(cloneSlide(sl)); page.appendChild(inner);
        const note = document.createElement('div'); note.className = 'note'; note.style.top = Math.round(H * s + 18) + 'px';
        const n = sl.querySelector('.slide-note'); note.innerHTML = '<b>' + (i + 1) + ' / ' + slides.length + '</b><br>' + (n ? n.innerHTML : '');
        page.appendChild(note); root.appendChild(page);
      });
    } else {
      w = W; h = H;
      st.textContent = '@page { size: ' + W + 'px ' + H + 'px; margin: 0; }';
      slides.forEach(sl => {
        const page = document.createElement('div'); page.className = 'page'; page.style.width = W + 'px'; page.style.height = H + 'px';
        page.appendChild(cloneSlide(sl)); root.appendChild(page);
      });
    }
    document.head.appendChild(st);
    return { w: w, h: h, handout: !!handout, pages: slides.length };
  }
  function endPrint() {
    const st = $('pagestyle'); if (st) st.remove();
    $('printroot').textContent = '';
  }
  function printDeck(handout) {                                              // P: ブラウザーの印刷画面（Shift+P: 配布資料）
    preparePrint(handout);
    const done = () => { endPrint(); window.removeEventListener('afterprint', done); };
    window.addEventListener('afterprint', done);
    setTimeout(() => { try { window.print(); } catch (e) { done(); } }, 60);
  }

  // ---- 操作
  const HELP = [['→ ↓ Space Enter', '次のスライド'], ['← ↑ BackSpace', '前のスライド'], ['Home / End', '最初 / 最後'], ['数字 + Enter', 'そのスライドへ'],
    ['G / Tab', 'スライド一覧'], ['B / W', '暗転 / 白画面'], ['L', 'レーザーポインター'], ['Z', '部分拡大（ホイールで倍率）'],
    ['R', '画面の比率を切り替える'], ['F', '全画面の入切'], ['O', '発表者ビューを開く'], ['P / Shift+P', '印刷 / ノート付きの配布資料'], ['Esc', '閉じる'], ['?', 'この説明']];
  function toggleHelp() {
    const h = $('help'); if (!h.firstChild) h.innerHTML = '<div>' + HELP.map(r => '<div><b>' + r[0] + '</b>' + r[1] + '</div>').join('') + '</div>';
    h.classList.toggle('on');
  }
  function toggleFullscreen() {
    if (role === 'standalone') { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen && document.documentElement.requestFullscreen(); }
    else if (window.pywebview && window.pywebview.api && window.pywebview.api.toggle_fullscreen) window.pywebview.api.toggle_fullscreen();
  }
  function closeAll() { if (role !== 'standalone' && window.pywebview && window.pywebview.api && window.pywebview.api.close_all) window.pywebview.api.close_all(); }
  function setRatio(key, remote) {
    ratioKey = key; layout(); fitAll(); if (!remote) sync(); toast('画面の比率: ' + RATIO_NAME[key] + (key === 'auto' ? '' : '（' + W + '×' + H + '）'));
  }
  function onKey(e) {
    if (e.ctrlKey || e.altKey || e.metaKey) return;
    const k = e.key;
    if ($('help').classList.contains('on')) { if (k === 'Escape' || k === '?' || k === 'Enter') { toggleHelp(); e.preventDefault(); } return; }
    if (overviewOn) {
      if (k === 'Escape' || k === 'g' || k === 'G' || k === 'Tab') closeOverview();
      else if (k === 'ArrowRight') moveSel(1); else if (k === 'ArrowLeft') moveSel(-1);
      else if (k === 'ArrowDown') moveSel(colsOfGrid()); else if (k === 'ArrowUp') moveSel(-colsOfGrid());
      else if (k === 'Enter' || k === ' ') { closeOverview(); show(sel); }
      else return;
      e.preventDefault(); return;
    }
    if (/^[0-9]$/.test(k)) { numBuf = (numBuf + k).slice(-4); toast('スライド ' + numBuf + '（Enter で移動）'); return; }
    if (k === 'Enter' && numBuf) { show(parseInt(numBuf, 10) - 1); numBuf = ''; e.preventDefault(); return; }
    numBuf = '';
    if (k === 'ArrowRight' || k === 'ArrowDown' || k === 'PageDown' || k === ' ' || k === 'Enter' || k === 'n') next();
    else if (k === 'ArrowLeft' || k === 'ArrowUp' || k === 'PageUp' || k === 'Backspace') prev();
    else if (k === 'Home') show(0); else if (k === 'End') show(slides.length - 1);
    else if (k === 'g' || k === 'G' || k === 'Tab') openOverview();
    else if (k === 'b' || k === 'B' || k === '.') setScreen(black === 'black' ? '' : 'black');
    else if (k === 'w' || k === 'W' || k === ',') setScreen(black === 'white' ? '' : 'white');
    else if (k === 'l' || k === 'L') {
      laserOn = !laserOn; document.body.classList.toggle('laser', laserOn);
      toast(laserOn ? (role === 'presenter' ? 'レーザーポインター: 入（「いまのスライド」の上で動かすと、聴衆の画面に出ます）' : 'レーザーポインター: 入') : 'レーザーポインター: 切');
      if (role === 'presenter') send({ laser: laserOn, u: null, v: null });
    }
    else if (k === 'z' || k === 'Z') {
      zoomOn = !zoomOn; applyTransform();
      toast(zoomOn ? (role === 'presenter' ? '部分拡大: 入（「いまのスライド」の上で動かすと、聴衆の画面が拡大されます。ホイールで倍率）' : '部分拡大: 入（ホイールで倍率）') : '部分拡大: 切');
      if (role === 'presenter') send({ zoom: zoomOn, zk: zoomK });
    }
    else if (k === 'r' || k === 'R') setRatio(RATIOS[(RATIOS.findIndex(r => r[0] === ratioKey) + 1) % RATIOS.length][0]);
    else if (k === 'f' || k === 'F') toggleFullscreen();
    else if (k === 'o' || k === 'O') { if (role === 'audience' && window.pywebview && window.pywebview.api && window.pywebview.api.open_presenter) window.pywebview.api.open_presenter(); }
    else if (k === 'p') printDeck(false);
    else if (k === 'P') printDeck(true);
    else if (k === '?' || k === '/') toggleHelp();
    else if (k === 'Escape') closeAll();
    else return;
    e.preventDefault();
  }

  // ---- 外から呼ぶもの（アプリの側が、別のウィンドウの状態を合わせる / 試験）
  window.Deck = {
    apply: function (s) { if (!s) return; if (typeof s.black === 'string') setScreen(s.black, true); if (typeof s.ratio === 'string' && s.ratio !== ratioKey && RATIOS.some(r => r[0] === s.ratio)) setRatio(s.ratio, true);
      if (role !== 'presenter') {                                                  // 発表者ビューからの、レーザー・部分拡大
        if (typeof s.laser === 'boolean') { laserOn = s.laser; document.body.classList.toggle('laser', laserOn); }
        if (typeof s.zk === 'number') zoomK = Math.min(5, Math.max(1.5, s.zk));
        if (typeof s.zoom === 'boolean') { zoomOn = s.zoom; applyTransform(); }
        if ('u' in s || 'v' in s) {
          const l = $('laser');
          if (typeof s.u !== 'number' || typeof s.v !== 'number') l.style.visibility = 'hidden';
          else { const p = slideToViewport(s.u, s.v); ptr = p; l.style.left = p.x + 'px'; l.style.top = p.y + 'px'; l.style.visibility = ''; if (zoomOn) applyTransform(); }
        } else if (typeof s.zk === 'number' && zoomOn) applyTransform();
      }
      if (typeof s.i === 'number') show(s.i, true); },
    state: () => ({ i: idx, n: slides.length, black: black, ratio: ratioKey, W: W, scale: scale, laser: laserOn, zoom: zoomOn, zk: zoomK, overview: overviewOn, role: role, t0: startTime }),
    next: next, prev: prev, goto: i => show(i), overflow: overflowList, shrunk: shrunkList, setRatio: setRatio, fitAll: fitAll, print: printDeck,
    preparePrint: preparePrint, endPrint: endPrint,
  };

  // ---- 起動
  function start() {
    if (role === 'presenter') document.body.classList.add('presenter');
    layout(); fitAll();
    if (slides.length) slides[idx].classList.add('cur');
    show(idx, true);
    slides.forEach((s, i) => { const n = document.createElement('div'); n.className = 'slide-num'; n.textContent = String(i + 1); s.appendChild(n); });
    setInterval(tick, 500);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitAll);
    window.addEventListener('load', fitAll);
    document.querySelectorAll('img').forEach(im => { if (!im.complete) im.addEventListener('load', fitAll); });
    window.addEventListener('resize', () => { layout(); if (ratioKey === 'auto') fitAll(); });
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousemove', e => {
      ptr = { x: e.clientX, y: e.clientY };
      const l = $('laser'); l.style.left = e.clientX + 'px'; l.style.top = e.clientY + 'px';
      if (role !== 'presenter') l.style.visibility = '';                                   // 手元から消された点も、この画面のマウスが動けば、また出る
      if (zoomOn) applyTransform();
      if (role === 'presenter' && (laserOn || zoomOn)) pointerToAudience(e);
      document.body.classList.remove('idle'); clearTimeout(idleTimer); idleTimer = setTimeout(() => document.body.classList.add('idle'), 2500);
    });
    $('stage').addEventListener('click', e => { if (e.button === 0 && !overviewOn) next(); });
    $('screen').addEventListener('click', () => setScreen(''));                                          // 暗転は、クリックでも戻る
    $('stage').addEventListener('contextmenu', e => { e.preventDefault(); prev(); });
    document.addEventListener('click', e => { const a = e.target.closest && e.target.closest('a'); if (a) e.preventDefault(); }, true);     // 発表中は、リンクを開かない（ウィンドウが別のページに変わらないように）
    document.addEventListener('wheel', e => {
      if (overviewOn) return;
      if (zoomOn) { zoomK = Math.min(5, Math.max(1.5, zoomK + (e.deltaY < 0 ? 0.25 : -0.25))); applyTransform(); toast('拡大 ' + zoomK.toFixed(2) + ' 倍'); if (role === 'presenter') send({ zk: zoomK }); e.preventDefault(); return; }
      const now = Date.now(); if (now - lastWheel < 350) return; lastWheel = now;
      if (e.deltaY > 0) next(); else if (e.deltaY < 0) prev();
    }, { passive: false });
    let tx = null;
    document.addEventListener('touchstart', e => { tx = e.touches[0].clientX; }, { passive: true });
    document.addEventListener('touchend', e => { if (tx === null) return; const d = e.changedTouches[0].clientX - tx; tx = null; if (Math.abs(d) > 50) { if (d < 0) next(); else prev(); } }, { passive: true });
    document.title = cfg.title || document.title;
  }
  start();
})();
