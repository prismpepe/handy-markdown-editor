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
  // レーザーポインターの大きさは、スライドの大きさに対する比率で決める（スライドの座標での直径。画面が大きいほど、点も大きくなる）
  const LASER_SIZES = [14, 18, 24, 30, 40, 48, 60, 72, 96];
  const nearestLaser = n => LASER_SIZES.reduce((b, x) => Math.abs(x - n) < Math.abs(b - n) ? x : b, LASER_SIZES[0]);
  let laserUnits = Math.min(160, Math.max(10, Number(cfg.laser) || 30));
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
  function applyLaser() {
    const l = $('laser'); if (!l) return;
    let s = scale;
    if (role === 'presenter') { const pane = document.querySelector('#presenter .cur-pane'); if (pane && pane.clientWidth) s = Math.min(pane.clientWidth / W, pane.clientHeight / H); }
    const px = Math.max(8, Math.round(laserUnits * s));
    l.style.width = l.style.height = px + 'px';
    l.style.margin = (-px / 2) + 'px 0 0 ' + (-px / 2) + 'px';
  }
  // step: +1 / -1（一覧の次の大きさ）、または、remote のときは、相手の画面から来た大きさそのもの
  function setLaser(v, remote, wrap) {
    if (remote) laserUnits = Math.min(160, Math.max(10, Number(v) || 30));
    else {
      const i = LASER_SIZES.indexOf(nearestLaser(laserUnits)), n = LASER_SIZES.length;
      laserUnits = LASER_SIZES[wrap ? (i + v + n) % n : Math.min(n - 1, Math.max(0, i + v))];
    }
    applyLaser(); renderInk();
    if (!remote) { toast('ポインター・ペンの大きさ: ' + (LASER_SIZES.indexOf(nearestLaser(laserUnits)) + 1) + ' / ' + LASER_SIZES.length); send({ lz: laserUnits }); }
  }
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
    applyLaser();
  }
  function layout() {
    W = Math.round(H * ratioValue());
    document.documentElement.style.setProperty('--slide-w', W + 'px');
    applyTransform(); renderInk();
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
    renderInk();
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


  // ---- 書き込み（マーキング）。左ボタンのドラッグで線を引く（Shift: 直線、Ctrl: 矢印）。中ボタン: 色。（右クリック = 前のスライドは、従来どおり）
  // 書いたものは、スライドごとに、この発表の間だけ覚える（保存しない）。位置は、スライド上の 0〜1 の比率で持ち、両方の画面で同じに描く
  const PEN_COLORS = [['赤', '#e5302a'], ['青', '#1f6feb'], ['緑', '#1a9850'], ['黄', '#f2c200'], ['黒', '#111111']];
  const PEN_TOOLS = [['pen', 'ペン'], ['marker', 'マーカー（蛍光ペン）'], ['line', '直線'], ['arrow', '矢印']];
  let drawOn = true, penColor = 0, penTool = 0, marks = {}, byId = {}, strokeSeq = 0, press = null, live = null, suppressClick = false, outbox = [], outTimer = null;
  const penWidth = tool => Math.max(2, laserUnits / 6) * (tool === 'marker' ? 3 : 1);          // スライドの座標での太さ（ポインターの大きさと連動）
  const idPrefix = role === 'presenter' ? 'p' : 'a';

  function strokeMarkup(st) {
    const P = st.p.map(q => [q[0] * W, q[1] * H]), c = st.c, w = st.w;
    if (!P.length) return '';
    const a = P[0], b = P[P.length - 1];
    const base = ' fill="none" stroke="' + c + '" stroke-width="' + w + '" stroke-linecap="round" stroke-linejoin="round"';
    if (st.t === 'marker') return '<polyline points="' + P.map(q => q[0].toFixed(1) + ',' + q[1].toFixed(1)).join(' ') + '"' + base + ' stroke-opacity="0.38"/>';
    if (st.t === 'line' || st.t === 'arrow') {
      let out = '<line x1="' + a[0].toFixed(1) + '" y1="' + a[1].toFixed(1) + '" x2="' + b[0].toFixed(1) + '" y2="' + b[1].toFixed(1) + '"' + base + '/>';
      if (st.t === 'arrow' && (a[0] !== b[0] || a[1] !== b[1])) {
        const ang = Math.atan2(b[1] - a[1], b[0] - a[0]), len = Math.max(w * 4, 22), spread = 0.45;
        const h1 = [b[0] - len * Math.cos(ang - spread), b[1] - len * Math.sin(ang - spread)], h2 = [b[0] - len * Math.cos(ang + spread), b[1] - len * Math.sin(ang + spread)];
        out += '<polyline points="' + h1[0].toFixed(1) + ',' + h1[1].toFixed(1) + ' ' + b[0].toFixed(1) + ',' + b[1].toFixed(1) + ' ' + h2[0].toFixed(1) + ',' + h2[1].toFixed(1) + '"' + base + '/>';
      }
      return out;
    }
    if (P.length === 1) return '<circle cx="' + a[0].toFixed(1) + '" cy="' + a[1].toFixed(1) + '" r="' + (w / 2) + '" fill="' + c + '"/>';
    return '<polyline points="' + P.map(q => q[0].toFixed(1) + ',' + q[1].toFixed(1)).join(' ') + '"' + base + '/>';
  }
  function inkSvg() {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'ink'); svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.style.cssText = 'position:absolute;left:0;top:0;width:' + W + 'px;height:' + H + 'px;pointer-events:none;overflow:visible;z-index:4';
    svg.innerHTML = (marks[idx] || []).map(strokeMarkup).join('');
    return svg;
  }
  // 聴衆の画面: #scaler の中の #ink。発表者ビュー: 「いまのスライド」の複製の中
  function renderInk() {
    let host = null, old = null;
    if (role === 'presenter') { host = document.querySelector('#presenter .cur-pane .inner'); old = host && host.querySelector('svg.ink'); }
    else { host = $('scaler'); old = $('ink'); }
    if (!host) return;
    const svg = inkSvg();
    if (role !== 'presenter') svg.id = 'ink';
    if (old) old.replaceWith(svg); else host.appendChild(svg);
  }
  function applyMark(m) {
    if (!m) return;
    if (m.o === 'b') {
      const st = { id: m.id, t: m.t, c: m.c, w: m.w, p: m.p.slice() };
      (marks[m.s] = marks[m.s] || []).push(st); byId[m.id] = st;
    } else if (m.o === 'a') {
      const st = byId[m.id]; if (!st) return;
      if (st.t === 'line' || st.t === 'arrow') st.p = [st.p[0], m.p[m.p.length - 1]]; else st.p.push(...m.p);
    } else if (m.o === 'u') { const a = marks[m.s]; if (a && a.length) { const x = a.pop(); delete byId[x.id]; } }
    else if (m.o === 'c') { (marks[m.s] || []).forEach(x => delete byId[x.id]); marks[m.s] = []; }
    else if (m.o === 'C') { marks = {}; byId = {}; }
    renderInk();
  }
  function flushOut() {
    outTimer = null;
    if (live && outbox.length) { send({ mk: { o: 'a', id: live.id, p: outbox } }); outbox = []; }
  }
  const slidePoint = (x, y) => {
    const el = role === 'presenter' ? document.querySelector('#presenter .cur-pane .inner') : $('scaler');
    const r = el.getBoundingClientRect();
    return [Math.min(1.2, Math.max(-0.2, (x - r.left) / r.width)), Math.min(1.2, Math.max(-0.2, (y - r.top) / r.height))];
  };
  function startStroke(x, y, shift, ctrl) {
    const tool = shift ? 'line' : ctrl ? 'arrow' : PEN_TOOLS[penTool][0];
    const p = slidePoint(x, y), id = idPrefix + (++strokeSeq);
    const m = { o: 'b', s: idx, id: id, t: tool, c: PEN_COLORS[penColor][1], w: Math.round(penWidth(tool) * 10) / 10, p: [p] };
    applyMark(m); live = byId[id]; outbox = [];
    send({ mk: m });
  }
  function extendStroke(x, y) {
    if (!live) return;
    const p = slidePoint(x, y);
    applyMark({ o: 'a', id: live.id, p: [p] });
    outbox.push(p);
    if (!outTimer) outTimer = setTimeout(flushOut, 30);
  }
  function endStroke() { clearTimeout(outTimer); flushOut(); live = null; }
  function cyclePenColor(remote) {
    penColor = (penColor + 1) % PEN_COLORS.length;
    toast('ペンの色: ' + PEN_COLORS[penColor][0]); if (!remote) send({ pc: penColor });
  }
  function cyclePenTool() {
    penTool = (penTool + 1) % PEN_TOOLS.length;
    toast('ペンの種類: ' + PEN_TOOLS[penTool][1] + '（Shift+ドラッグ: 直線、Ctrl+ドラッグ: 矢印）'); send({ pt: penTool });
  }
  function toggleDraw() {
    drawOn = !drawOn; toast(drawOn ? '書き込み: 入（ドラッグで線を引く。中ボタン / C: 色、[ ]: 大きさ）' : '書き込み: 切（ドラッグでは書けません）'); send({ dw: drawOn });
  }
  const undoStroke = () => { const m = { o: 'u', s: idx }; applyMark(m); send({ mk: m }); };
  const clearInk = all => { const m = all ? { o: 'C' } : { o: 'c', s: idx }; applyMark(m); send({ mk: m }); toast(all ? 'すべてのスライドの書き込みを消しました' : 'このスライドの書き込みを消しました'); };

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
  const PRESENTER_HINT = '<b>→</b>次　<b>←</b>前　<b>数字+Enter</b>そのスライドへ　<b>G</b>スライド一覧　<b>B</b>暗転　<b>W</b>白画面　<b>R</b>画面の比率　<b>F</b>全画面　<b>?</b>操作の一覧'
    + '<br><b>L</b>レーザーポインター　<b>[</b><b>]</b>点の大きさ　<b>Z</b>部分拡大　<span class="sub">（L・Z は、手元のスライドの上でマウスを動かすと、聴衆の画面に出ます）</span>'
    + '<br><b>ドラッグ</b>書き込み（Shift 直線・Ctrl 矢印）　<b>中ボタン/C</b>色　<b>M</b>ペンの種類　<b>D</b>入切　<b>U</b>戻す　<b>E</b>消す';
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
    renderInk();
    const n = slides[idx] && slides[idx].querySelector('.slide-note');
    const box = p.querySelector('.notes'); box.classList.toggle('empty', !n); box.innerHTML = n ? n.innerHTML : '（ノートはありません）';
    $('pcount').textContent = (idx + 1) + ' / ' + slides.length;
    applyLaser();
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
    ['G / Tab', 'スライド一覧'], ['B / W', '暗転 / 白画面'], ['L', 'レーザーポインター'], ['[ / ]', 'ポインター・ペンの大きさ（小さく / 大きく）'],
    ['ドラッグ', '書き込み（Shift: 直線、Ctrl: 矢印）'], ['中ボタン / C', 'ペンの色'], ['M', 'ペンの種類（ペン・マーカー・直線・矢印）'], ['D', '書き込みの入切'], ['U / E / Shift+E', '1 本戻す / このスライドを消す / すべて消す'], ['Z', '部分拡大（ホイールで倍率）'],
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
      toast(laserOn ? (role === 'presenter' ? 'レーザーポインター: 入（「いまのスライド」の上で動かすと、聴衆の画面に出ます。[ ] で大きさを変える）' : 'レーザーポインター: 入（[ ] で大きさを変える）') : 'レーザーポインター: 切');
      if (role === 'presenter') send({ laser: laserOn, u: null, v: null });
    }
    else if (k === 'z' || k === 'Z') {
      zoomOn = !zoomOn; applyTransform();
      toast(zoomOn ? (role === 'presenter' ? '部分拡大: 入（「いまのスライド」の上で動かすと、聴衆の画面が拡大されます。ホイールで倍率）' : '部分拡大: 入（ホイールで倍率）') : '部分拡大: 切');
      if (role === 'presenter') send({ zoom: zoomOn, zk: zoomK });
    }
    else if (k === 'r' || k === 'R') setRatio(RATIOS[(RATIOS.findIndex(r => r[0] === ratioKey) + 1) % RATIOS.length][0]);
    else if (k === 'd' || k === 'D') toggleDraw();
    else if (k === 'm' || k === 'M') cyclePenTool();
    else if (k === 'c' || k === 'C') cyclePenColor();
    else if (k === 'u' || k === 'U') undoStroke();
    else if (k === 'e') clearInk(false);
    else if (k === 'E') clearInk(true);
    else if (k === '[') setLaser(-1);
    else if (k === ']') setLaser(1);
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
      if (s.mk) applyMark(s.mk);
      if (typeof s.pc === 'number' && s.pc >= 0 && s.pc < PEN_COLORS.length) penColor = s.pc;
      if (typeof s.pt === 'number' && s.pt >= 0 && s.pt < PEN_TOOLS.length) penTool = s.pt;
      if (typeof s.dw === 'boolean') drawOn = s.dw;
      if (typeof s.lz === 'number' && role === 'presenter') setLaser(s.lz, true);
      if (role !== 'presenter') {                                                  // 発表者ビューからの、レーザー・部分拡大
        if (typeof s.laser === 'boolean') { laserOn = s.laser; document.body.classList.toggle('laser', laserOn); }
        if (typeof s.lz === 'number') setLaser(s.lz, true);
        if (typeof s.zk === 'number') zoomK = Math.min(5, Math.max(1.5, s.zk));
        if (typeof s.zoom === 'boolean') { zoomOn = s.zoom; applyTransform(); }
        if ('u' in s || 'v' in s) {
          const l = $('laser');
          if (typeof s.u !== 'number' || typeof s.v !== 'number') l.style.visibility = 'hidden';
          else { const p = slideToViewport(s.u, s.v); ptr = p; l.style.left = p.x + 'px'; l.style.top = p.y + 'px'; l.style.visibility = ''; if (zoomOn) applyTransform(); }
        } else if (typeof s.zk === 'number' && zoomOn) applyTransform();
      }
      if (typeof s.i === 'number') show(s.i, true); },
    state: () => ({ i: idx, n: slides.length, black: black, ratio: ratioKey, W: W, scale: scale, laser: laserOn, zoom: zoomOn, zk: zoomK, draw: drawOn, tool: PEN_TOOLS[penTool][0], color: penColor, ink: (marks[idx] || []).length, inkAll: Object.values(marks).reduce((n, a) => n + a.length, 0), lz: laserUnits, lpx: parseFloat(($('laser') || { style: {} }).style.width) || 0, overview: overviewOn, role: role, t0: startTime }),
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
    $('stage').addEventListener('click', e => { if (suppressClick) { suppressClick = false; return; } if (e.button === 0 && !overviewOn) next(); });
    $('screen').addEventListener('click', () => setScreen(''));                                          // 暗転は、クリックでも戻る
    $('stage').addEventListener('contextmenu', e => { e.preventDefault(); prev(); });                       // 右クリック = 前のスライド（書き込みの入切に関わらず、従来どおり）
    // 書き込み: 左ボタンのドラッグ（5px 以上動いたら始まる）。動かさずに離せば、ふつうのクリック（次へ）。中ボタン: ペンの色
    const inDrawArea = t => role === 'presenter' ? !!(t.closest && t.closest('#presenter .cur-pane')) : !!(t.closest && t.closest('#stage'));
    document.addEventListener('mousedown', e => {
      if (!drawOn || overviewOn || $('help').classList.contains('on') || !inDrawArea(e.target)) return;
      if (e.button === 0) press = { x: e.clientX, y: e.clientY, shift: e.shiftKey, ctrl: e.ctrlKey, started: false };
      else if (e.button === 1) e.preventDefault();                                         // 中ボタンの自動スクロールを止める
    });
    document.addEventListener('mousemove', e => {
      if (!press) return;
      if (!(e.buttons & 1)) { press = null; endStroke(); return; }
      if (!press.started && Math.hypot(e.clientX - press.x, e.clientY - press.y) > 5) { press.started = true; startStroke(press.x, press.y, press.shift, press.ctrl); }
      if (press.started) extendStroke(e.clientX, e.clientY);
    });
    document.addEventListener('mouseup', e => {
      if (e.button === 0 && press) { if (press.started) { endStroke(); suppressClick = true; setTimeout(() => { suppressClick = false; }, 0); } press = null; }
      else if (e.button === 1 && drawOn && !overviewOn && inDrawArea(e.target)) { e.preventDefault(); cyclePenColor(); }
    });

    if (role === 'presenter') {                                                                        // 手元の画面でも、スライドの上のクリックで進める（左: 次、右: 前）
      const inPane = t => !!(t.closest && t.closest('#presenter .cur-pane, #presenter .next-pane'));
      document.addEventListener('click', e => { if (e.button !== 0 || !inPane(e.target)) return; if (suppressClick) { suppressClick = false; return; } next(); });
      document.addEventListener('contextmenu', e => { if (inPane(e.target)) { e.preventDefault(); prev(); } });
    }
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
