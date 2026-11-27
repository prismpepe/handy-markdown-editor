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
  let W = 1280, scale = 1, black = '', laserOn = false, zoomOn = false, zoomK = 1, ptr = { x: 0, y: 0 };
  let mapActive = 0, mapHover = false;                               // 1 画面の地図: 最後にマウスを動かした（拡大を変えた）時刻と、マウスが地図の上にあるか
  let audAspect = 0;                                                 // 聴衆の画面の窓の縦横比（発表者ビューが、枠の大きさを決めるために使う）
  let presenterOn = false;                                           // 聴衆の画面から見て、発表者ビューが開いているか（開いていなければ、1 画面。枠のかわりに、右下の地図を出す）
  let zc = { u: 0.5, v: 0.5 }, zgrab = null;                        // 拡大の枠の中心（スライド上の 0〜1）と、枠をつかんで動かしている間の状態
  let overviewOn = false, sel = 0, numBuf = '', startTime = Number(cfg.t0) || Date.now(), noteSize = 22, lastWheel = 0, idleTimer = null;      // 経過時間は、発表を始めたとき（Python が決める。2 つのウィンドウで同じ）から数える
  const sync = () => { if (role !== 'standalone' && window.pywebview && window.pywebview.api && window.pywebview.api.sync) window.pywebview.api.sync(JSON.stringify({ i: idx, black: black, ratio: ratioKey })); };

  // 一部の項目だけを、もう片方のウィンドウへ送る（レーザーの位置など）
  const send = obj => { if (role !== 'standalone' && window.pywebview && window.pywebview.api && window.pywebview.api.sync) window.pywebview.api.sync(JSON.stringify(obj)); };
  // スライド上の位置（0〜1）を、窓の座標（px）にする。聴衆の画面で、レーザーや拡大の位置に使う
  function slideToViewport(u, v) {
    const vw = innerWidth, vh = innerHeight, sc = Math.min(vw / W, vh / H);
    return { x: (vw - W * sc) / 2 + u * W * sc, y: (vh - H * sc) / 2 + v * H * sc };
  }
  let zsel = null;                                                    // 拡大中のドラッグ（拡大する範囲の選択）
  function zselBox() {
    let b = document.getElementById('zsel');
    if (!b) { b = document.createElement('div'); b.id = 'zsel'; b.style.cssText = 'position:fixed;z-index:30;pointer-events:none;border:2px dashed #ffd43b;background:rgba(255,212,59,.18);display:none'; document.body.appendChild(b); }
    return b;
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

  // ---- 診断（Ctrl+Shift+D）: 倍率の違う画面（150% など）で、マウスの位置が、見えている位置とずれるときの確認用。
  // 赤い輪が、「ページが認識しているマウスの位置」。実際のカーソルと重なっていれば、座標は合っている
  let diagOn = false;
  function toggleDiag() {
    diagOn = !diagOn;
    let d = document.getElementById('diag'), c = document.getElementById('diagdot');
    if (!d) {
      d = document.createElement('pre'); d.id = 'diag';
      d.style.cssText = 'position:fixed;left:8px;top:8px;z-index:60;margin:0;padding:6px 10px;background:rgba(0,0,0,.85);color:#fff;font:13px/1.5 Consolas,monospace;pointer-events:none;white-space:pre';
      c = document.createElement('div'); c.id = 'diagdot';
      c.style.cssText = 'position:fixed;z-index:61;width:28px;height:28px;margin:-14px 0 0 -14px;border:3px solid #f00;border-radius:50%;pointer-events:none;box-sizing:border-box';
      document.body.appendChild(d); document.body.appendChild(c);
    }
    d.style.display = c.style.display = diagOn ? 'block' : 'none';
    if (diagOn) drawDiag(null);
  }
  let diagLast = null;
  function drawDiag(e) {
    if (e) diagLast = e;
    const d = document.getElementById('diag'), c = document.getElementById('diagdot'); if (!d) return;
    const m = diagLast, vv = window.visualViewport;
    let t = '役割 ' + role + '\n倍率 devicePixelRatio ' + window.devicePixelRatio + '\n窓の内側 ' + innerWidth + ' x ' + innerHeight + '　外側 ' + outerWidth + ' x ' + outerHeight
      + '\n画面 ' + screen.width + ' x ' + screen.height + '（使える領域 ' + screen.availWidth + ' x ' + screen.availHeight + '）\n窓の位置 ' + window.screenX + ', ' + window.screenY + (vv ? '\nvisualViewport 倍率 ' + vv.scale : '');
    if (m) {
      t += '\nマウス（ページ）' + m.clientX + ', ' + m.clientY + '\nマウス（画面）' + m.screenX + ', ' + m.screenY
        + '\n画面 − 窓の位置 − ページ = ' + (m.screenX - window.screenX - m.clientX) + ', ' + (m.screenY - window.screenY - m.clientY);
      c.style.left = m.clientX + 'px'; c.style.top = m.clientY + 'px';
    }
    d.textContent = t + '\n（Ctrl+Shift+D で閉じる。赤い輪が、カーソルと重なるか）';
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
  // ---- 部分拡大は、「スライド上の枠」（中心 zc と、大きさ = 1/倍率）で決める。マウスの位置から毎回は計算しない（縁まで映せる・解除で飛ばない）
  // 倍率 1 のとき、画面に映るスライドの範囲（スライドに対する比率）。窓の形がスライドと違うと、1 を超える（余白の分だけ、広く映る）。
  // 発表者ビューは、聴衆の画面の窓の形（audAspect）で数える
  function fit1() {
    const a = role === 'presenter' ? audAspect : innerWidth / Math.max(1, innerHeight), r = W / H;
    if (!(a > 0)) return { x: 1, y: 1 };
    return a >= r ? { x: a / r, y: 1 } : { x: 1, y: r / a };
  }
  // 枠の半分の大きさ（スライドに対する比率）。聴衆の画面に映る範囲そのもの
  function halfExtent() { const f = fit1(); return { x: f.x / (2 * zoomK), y: f.y / (2 * zoomK) }; }
  // 囲んだ範囲（スライドに対する比率 du・dv）が、画面いっぱいになる倍率
  function fitK(du, dv) { const f = fit1(); return Math.round(Math.min(5, Math.max(1.1, Math.min(f.x / du, f.y / dv))) * 100) / 100; }
  function clampCenter(u, v) {                                         // 枠が、スライドの外へ出ないように（縁は、ちょうど届く）
    const h = halfExtent(), f = (c, e) => e >= 0.5 ? 0.5 : Math.min(1 - e, Math.max(e, c));
    return { u: f(u, h.x), v: f(v, h.y) };
  }
  function setFrame(u, v, k) {
    if (typeof k === 'number') zoomK = Math.min(5, Math.max(1, k));
    zc = clampCenter(u, v); mapActive = Date.now(); applyTransform();
  }
  // 窓の座標を、スライド上の位置（0〜1）にする。拡大中の画面の上の点も、拡大前に戻して数える
  function viewportToSlide(p) {
    const vw = innerWidth, vh = innerHeight, sc = Math.min(vw / W, vh / H), tx = (vw - W * sc) / 2, ty = (vh - H * sc) / 2;
    let x = p.x, y = p.y;
    if (zoomOn && zoomK > 1) { x = (p.x - vw / 2) / zoomK + tx + zc.u * W * sc; y = (p.y - vh / 2) / zoomK + ty + zc.v * H * sc; }
    return { u: (x - tx) / (W * sc), v: (y - ty) / (H * sc) };
  }
  // 枠を出す入れ物（発表者ビュー: 「いまのスライド」。1 画面のとき: 右下の小さな地図）と、その中の枠の位置（窓の座標）
  function frameBox() {
    if (!zoomOn || zoomK <= 1.01 || overviewOn) return null;
    let c = null;
    if (role === 'presenter') { const inner = document.querySelector('#presenter .cur-pane .inner'); if (inner) c = inner.getBoundingClientRect(); }
    else if (alone()) { const m = zmapEl(); c = m.getBoundingClientRect(); }
    if (!c || !c.width) return null;
    const h = halfExtent(), ex = Math.min(0.5, h.x), ey = Math.min(0.5, h.y);
    return { c: c, left: c.left + (zc.u - ex) * c.width, top: c.top + (zc.v - ey) * c.height, right: c.left + (zc.u + ex) * c.width, bottom: c.top + (zc.v + ey) * c.height };
  }
  // 1 画面で操作する画面か（枠の地図を出し、つかんで動かせる）。PDF 書き出しなどの単独の画面と、発表者ビューの無い聴衆の画面
  const alone = () => role === 'standalone' || (role === 'audience' && (!presenterOn || cfg.zmap === true));       // 設定で、発表者ビューがあるときも、聴衆の画面に地図を出せる
  function zmapEl() {
    let m = document.getElementById('zmap');
    if (!m) {
      m = document.createElement('div'); m.id = 'zmap';
      m.addEventListener('mouseenter', () => { mapHover = true; }); m.addEventListener('mouseleave', () => { mapHover = false; });
      m.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:30;border:2px solid #333;box-shadow:0 2px 14px rgba(0,0,0,.7);background:#000;overflow:hidden;display:none;cursor:move';
      m.innerHTML = '<div id="zmapf" style="position:absolute;border:2px solid #ffd43b;background:rgba(255,212,59,.22);box-sizing:border-box;pointer-events:none"></div>';
      document.body.appendChild(m);
    }
    const mw = Math.round(Math.min(480, Math.max(240, innerWidth * 0.24)));                // 画面の 24%（240〜480px）。小さすぎると、枠をつかめない
    m.style.width = mw + 'px'; m.style.height = Math.round(mw * H / W) + 'px';
    return m;
  }
  function frameEl() {
    let f = document.getElementById('zframe');
    if (!f) { f = document.createElement('div'); f.id = 'zframe'; f.style.cssText = 'position:fixed;z-index:30;pointer-events:none;box-sizing:border-box;border:4px solid #ffd43b;background:rgba(255,212,59,.10);display:none'; document.body.appendChild(f); }
    return f;
  }
  function drawFrame() {
    if (role === 'audience' && presenterOn && cfg.zmap !== true) { const z = document.getElementById('zmap'); if (z) z.style.display = 'none'; return; }
    const f = frameEl(), want = zoomOn && zoomK > 1.01 && !overviewOn;
    if (alone()) {
      const m = zmapEl(), hide = !want || (!zgrab && !mapHover && Date.now() - mapActive > 5000);        // 1 画面のときの地図は、マウスが 5 秒止まれば消える（地図の上にいる間は消えない）
      m.style.display = hide ? 'none' : 'block'; f.style.display = 'none';
      if (hide) return;
      const fb = frameBox(), mf = document.getElementById('zmapf'); if (!fb) return;
      // 地図に、いまのスライドの縮小画像を入れる（どのスライドの、どこが映っているかが分かる。スライドや大きさが変わったときだけ作り直す）
      const mw = m.offsetWidth, key = idx + '|' + W + '|' + mw;
      if (m.dataset.thumb !== key && slides[idx]) {
        const old = m.querySelector('.zthumb'); if (old) old.remove();
        const t = document.createElement('div'); t.className = 'zthumb';
        t.style.cssText = 'position:absolute;left:0;top:0;width:' + W + 'px;height:' + H + 'px;transform-origin:0 0;transform:scale(' + (mw / W) + ');pointer-events:none;overflow:hidden;background:#fff;opacity:.9';
        const c = slides[idx].cloneNode(true); c.removeAttribute('id'); c.querySelectorAll('[id]').forEach(e => e.removeAttribute('id')); c.classList.add('cur');
        t.appendChild(c); m.insertBefore(t, m.firstChild); m.dataset.thumb = key;
      }
      mf.style.left = (fb.left - fb.c.left) + 'px'; mf.style.top = (fb.top - fb.c.top) + 'px'; mf.style.width = (fb.right - fb.left) + 'px'; mf.style.height = (fb.bottom - fb.top) + 'px';
      return;
    }
    const b = frameBox();
    if (!b) { f.style.display = 'none'; return; }
    f.style.display = 'block'; f.style.left = b.left + 'px'; f.style.top = b.top + 'px'; f.style.width = (b.right - b.left) + 'px'; f.style.height = (b.bottom - b.top) + 'px';
  }
  // 枠の縁（見た目より少し広く）の上か。発表者ビューの枠は縁だけをつかめる（内側のドラッグは、範囲の選択に使う）。1 画面の地図は、枠の内側も、地図の中も、つかめる
  const GRAB_BAND = 9;
  function onFrameEdge(x, y) {
    const b = frameBox(); if (!b) return false;
    if (alone()) return x >= b.c.left && x <= b.c.right && y >= b.c.top && y <= b.c.bottom;
    const o = x >= b.left - GRAB_BAND && x <= b.right + GRAB_BAND && y >= b.top - GRAB_BAND && y <= b.bottom + GRAB_BAND;
    const i = x > b.left + GRAB_BAND && x < b.right - GRAB_BAND && y > b.top + GRAB_BAND && y < b.bottom - GRAB_BAND;
    return o && !i;
  }
  let lastFrameSend = 0;
  function sendFrame(force) {
    if (role === 'standalone') return;
    const now = Date.now(); if (!force && now - lastFrameSend < 30) return; lastFrameSend = now;
    send({ zk: zoomK, zc: [zc.u, zc.v] });
  }
  function applyTransform() {
    const vw = innerWidth, vh = innerHeight;
    scale = Math.min(vw / W, vh / H);
    const tx = (vw - W * scale) / 2, ty = (vh - H * scale) / 2;
    const el = $('scaler');
    if (zoomOn) {
      const k = zoomK;
      el.style.transform = 'translate(' + (vw / 2 - k * zc.u * W * scale) + 'px,' + (vh / 2 - k * zc.v * H * scale) + 'px) scale(' + (k * scale) + ')';
    } else {
      el.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + scale + ')';
    }
    applyLaser(); drawFrame();
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
  let penColor = 0, penTool = 0, marks = {}, byId = {}, strokeSeq = 0, press = null, live = null, suppressClick = false, outbox = [], outTimer = null;
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
    + '<br><b>L</b>レーザーポインター　<b>[</b><b>]</b>大きさ　<b>C</b>色　<b>M</b>ペンの種類　<b>ドラッグ</b>書き込み（Shift 直線・Ctrl 矢印）　<b>U</b>戻す　<b>E</b>消す'
    + '<br><b>Z</b>部分拡大（等倍から）　<b>ドラッグ</b>囲んだ範囲を拡大（L が切れているとき）　<b>ホイール</b>倍率　<b>黄色い枠の縁をドラッグ</b>拡大の位置を動かす'
    + '<br><span class="sub">L が入っていれば、Z との順序に関係なく、ドラッグは書き込み</span>';
  function renderModes() {
    const el = $('pmodes'); if (!el) return;
    const tag = (cls, text) => '<span class="mode ' + cls + '">' + text + '</span>';
    let h = '';
    if (laserOn) {
      const col = PEN_COLORS[penColor], sz = LASER_SIZES.indexOf(nearestLaser(laserUnits)) + 1;
      h += tag('l', 'L 入：ドラッグ＝書き込み');
      h += tag('p', '<i class="sw" style="background:' + col[1] + '"></i>' + col[0] + '　' + PEN_TOOLS[penTool][1].split('（')[0] + '　太さ ' + sz + '/' + LASER_SIZES.length);
    }
    if (zoomOn) h += tag('z', 'Z 入：' + (zoomK <= 1 ? '等倍' : zoomK.toFixed(1) + ' 倍（黄色い枠の縁をドラッグで移動）') + (laserOn ? '' : '　ドラッグ＝範囲を拡大'));
    drawFrame();
    if (el.dataset.h !== h) { el.dataset.h = h; el.innerHTML = h; }
  }
  function buildPresenter() {
    const p = $('presenter');
    p.innerHTML = '<div class="pane cur-pane"><span class="label">いまのスライド</span><div class="modes" id="pmodes"></div><div class="inner"></div></div>'
      + '<div class="side"><div class="pane next-pane"><span class="label">次のスライド</span><div class="inner"></div></div><div class="notes empty"></div></div>'
      + '<div class="bar"><span class="big" id="pcount"></span><span class="big" id="pelapsed">00:00</span><span id="pclock"></span><span class="grow warnline" id="pwarn"></span>'
      + '<button id="pprev">◀ 前へ</button><button id="pnext">次へ ▶</button><button id="pblack">暗転</button><button id="ptimer">タイマーを戻す</button><button id="pnoteminus">ノート −</button><button id="pnoteplus">ノート ＋</button></div>'
      + '<div class="hint" id="phint">' + PRESENTER_HINT + '</div>';
    $('pprev').onclick = prev; $('pnext').onclick = next;
    setInterval(renderModes, 150);                                          // L・Z の入切と、拡大の状態を、いつも見える所に出す
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
    ['G / Tab', 'スライド一覧'], ['B / W', '暗転 / 白画面'], ['L', 'レーザーポインターの入切（入れている間、ドラッグで書き込める）'], ['[ / ]', 'ポインター・ペンの大きさ（小さく / 大きく）'], ['C', 'ペンの色'], ['M', 'ペンの種類（ペン・マーカー・直線・矢印）'],
    ['ドラッグ', '書き込み（Shift: 直線、Ctrl: 矢印）'], ['U / E / Shift+E', '1 本戻す / このスライドを消す / すべて消す'], ['Z', '部分拡大（入れた直後は等倍。L が切れているとき、ドラッグした範囲を拡大。ホイールで倍率 1〜5 倍。拡大中は、枠（発表者ビュー）または右下の地図（1 画面）の縁をドラッグして、位置を動かす）'],
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
      toast(laserOn ? (role === 'presenter' ? 'レーザーポインター: 入（「いまのスライド」の上で動かすと、聴衆の画面に出ます。ドラッグで書き込み、[ ] で大きさ）' : 'レーザーポインター: 入（ドラッグで書き込み、[ ] で大きさ）') : 'レーザーポインター: 切（書き込みはできません）');
      send({ laser: laserOn, u: null, v: null });
      if (!laserOn && press) { press = null; endStroke(); }
    }
    else if (k === 'z' || k === 'Z') {
      zoomOn = !zoomOn; zoomK = 1; zc = { u: 0.5, v: 0.5 }; applyTransform();                    // 入れた直後は、等倍（ドラッグで範囲を選べる）。切って入れ直すと、等倍に戻る
      toast(zoomOn ? '部分拡大: 入（等倍から。ドラッグで範囲を選ぶ・ホイールで倍率）' : '部分拡大: 切');
      send({ zoom: zoomOn, zk: zoomK, zc: [zc.u, zc.v] });
    }
    else if (k === 'r' || k === 'R') setRatio(RATIOS[(RATIOS.findIndex(r => r[0] === ratioKey) + 1) % RATIOS.length][0]);
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
      if (typeof s.laser === 'boolean') { laserOn = s.laser; document.body.classList.toggle('laser', laserOn); }              // レーザー（と書き込み）の入切は、両方の画面で同じ
      if (typeof s.lz === 'number' && role === 'presenter') setLaser(s.lz, true);
      if (typeof s.va === 'number' && s.va > 0.2 && s.va < 8 && role === 'presenter') { audAspect = s.va; drawFrame(); }
      if (role === 'presenter' && (typeof s.zk === 'number' || Array.isArray(s.zc) || typeof s.zoom === 'boolean')) {         // 聴衆の画面で変えた拡大（囲み・ホイール・Z）
        if (typeof s.zoom === 'boolean') zoomOn = s.zoom;
        if (typeof s.zk === 'number') zoomK = Math.min(5, Math.max(1, s.zk));
        if (Array.isArray(s.zc) && s.zc.length === 2 && typeof s.zc[0] === 'number' && typeof s.zc[1] === 'number') zc = clampCenter(s.zc[0], s.zc[1]);
        drawFrame();
      }
      if (role !== 'presenter') {                                                  // 発表者ビューからの、レーザー・部分拡大
        if (typeof s.lz === 'number') setLaser(s.lz, true);
        if (typeof s.zk === 'number') zoomK = Math.min(5, Math.max(1, s.zk));
        if (Array.isArray(s.zc) && s.zc.length === 2 && typeof s.zc[0] === 'number' && typeof s.zc[1] === 'number') zc = clampCenter(s.zc[0], s.zc[1]);
        else if (typeof s.zk === 'number') zc = clampCenter(zc.u, zc.v);
        if (typeof s.zoom === 'boolean') zoomOn = s.zoom;
        if (typeof s.zk === 'number' || Array.isArray(s.zc) || typeof s.zoom === 'boolean') applyTransform();
        if ('u' in s || 'v' in s) {
          const l = $('laser');
          if (typeof s.u !== 'number' || typeof s.v !== 'number') l.style.visibility = 'hidden';
          else { const p = slideToViewport(s.u, s.v); ptr = p; l.style.left = p.x + 'px'; l.style.top = p.y + 'px'; l.style.visibility = ''; }
        }
      }
      if (typeof s.i === 'number') show(s.i, true); },
    state: () => ({ i: idx, n: slides.length, black: black, ratio: ratioKey, W: W, scale: scale, laser: laserOn, zoom: zoomOn, zk: zoomK, zc: [zc.u, zc.v], va: audAspect, draw: laserOn, tool: PEN_TOOLS[penTool][0], color: penColor, ink: (marks[idx] || []).length, inkAll: Object.values(marks).reduce((n, a) => n + a.length, 0), lz: laserUnits, lpx: parseFloat(($('laser') || { style: {} }).style.width) || 0, overview: overviewOn, role: role, t0: startTime }),
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
    setInterval(() => { if (alone()) drawFrame(); }, 400);            // 1 画面のときの地図は、マウスが止まれば消える
    let lastVa = 0;
    if (role === 'audience') setInterval(() => {                                    // 発表者ビューが開いているかを、Python に聞く（O キーで、あとから開くこともある）
      try { const a = window.pywebview && window.pywebview.api; if (a && a.has_presenter) a.has_presenter().then(v => { const was = presenterOn; presenterOn = !!v; if (was !== presenterOn) { lastVa = 0; drawFrame(); } if (presenterOn) { const va = innerWidth / Math.max(1, innerHeight); if (Math.abs(va - lastVa) > 0.001) { lastVa = va; send({ va: va }); } } }); } catch (e) { /* 聞けなければ、そのまま */ }
    }, 700);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitAll);
    window.addEventListener('load', fitAll);
    document.querySelectorAll('img').forEach(im => { if (!im.complete) im.addEventListener('load', fitAll); });
    window.addEventListener('resize', () => { layout(); if (ratioKey === 'auto') fitAll(); });
    document.addEventListener('keydown', onKey);
    document.addEventListener('keydown', e => { if (e.ctrlKey && e.shiftKey && (e.key === 'D' || e.key === 'd')) { toggleDiag(); e.preventDefault(); } });
    document.addEventListener('mousemove', e => { if (diagOn) drawDiag(e); });
    document.addEventListener('mousemove', e => {
      ptr = { x: e.clientX, y: e.clientY };
      const l = $('laser'); l.style.left = e.clientX + 'px'; l.style.top = e.clientY + 'px';
      if (role !== 'presenter') l.style.visibility = '';                                   // 手元から消された点も、この画面のマウスが動けば、また出る
      if (role === 'presenter' && laserOn) pointerToAudience(e);
      if (!zgrab) document.body.classList.toggle('zgrab', zoomOn && onFrameEdge(e.clientX, e.clientY));       // 枠の縁の上では、移動の形のカーソルにする
      if (alone()) { mapActive = Date.now(); setTimeout(drawFrame, 0); }
      document.body.classList.remove('idle'); clearTimeout(idleTimer); idleTimer = setTimeout(() => document.body.classList.add('idle'), 2500);
    });
    $('stage').addEventListener('click', e => { if (suppressClick) { suppressClick = false; return; } if (e.button === 0 && !overviewOn) { if (!zoomOn) next(); } });
    $('screen').addEventListener('click', () => setScreen(''));                                          // 暗転は、クリックでも戻る
    $('stage').addEventListener('contextmenu', e => { e.preventDefault(); prev(); });                       // 右クリック = 前のスライド（書き込みの入切に関わらず、従来どおり）
    // 書き込み: レーザーポインター（L）が入っているときだけ。左ボタンのドラッグ（5px 以上動いたら始まる）。動かさずに離せば、ふつうのクリック（次へ）
    const inDrawArea = t => role === 'presenter' ? !!(t.closest && t.closest('#presenter .cur-pane')) : !!(t.closest && t.closest('#stage'));
    document.addEventListener('mousedown', e => {
      if (zoomOn && !laserOn && e.button === 0 && !overviewOn && !$('help').classList.contains('on') && onFrameEdge(e.clientX, e.clientY)) {
        const b = frameBox(), u = (e.clientX - b.c.left) / b.c.width, v = (e.clientY - b.c.top) / b.c.height;
        const inside = e.clientX >= b.left && e.clientX <= b.right && e.clientY >= b.top && e.clientY <= b.bottom;
        zgrab = alone() && !inside ? { du: 0, dv: 0 } : { du: u - zc.u, dv: v - zc.v };           // つかんだ位置と中心の差を保つ（飛ばない）。地図の枠の外は、その点が中心になる
        if (zgrab.du === 0 && zgrab.dv === 0) { setFrame(u, v); sendFrame(true); }
        document.body.classList.add('zgrab'); e.preventDefault();
        return;
      }
      if (zoomOn && !laserOn && e.button === 0 && !overviewOn && !$('help').classList.contains('on') && inDrawArea(e.target)) {
        zsel = { x: e.clientX, y: e.clientY, started: false };
        return;
      }
      if (!laserOn || overviewOn || $('help').classList.contains('on') || !inDrawArea(e.target)) return;
      if (e.button === 0) press = { x: e.clientX, y: e.clientY, shift: e.shiftKey, ctrl: e.ctrlKey, started: false };
    });
    document.addEventListener('mousemove', e => {
      if (zgrab) {
        if (!(e.buttons & 1)) { zgrab = null; document.body.classList.remove('zgrab'); sendFrame(true); return; }
        const b = frameBox(); if (!b) return;
        setFrame((e.clientX - b.c.left) / b.c.width - zgrab.du, (e.clientY - b.c.top) / b.c.height - zgrab.dv); sendFrame(false);
        return;
      }
      if (zsel) {
        if (!(e.buttons & 1)) { cancelZsel(); return; }
        if (!zsel.started && Math.hypot(e.clientX - zsel.x, e.clientY - zsel.y) > 5) zsel.started = true;
        if (zsel.started) {
          const b = zselBox(), x = Math.min(zsel.x, e.clientX), y = Math.min(zsel.y, e.clientY);
          b.style.display = 'block'; b.style.left = x + 'px'; b.style.top = y + 'px'; b.style.width = Math.abs(e.clientX - zsel.x) + 'px'; b.style.height = Math.abs(e.clientY - zsel.y) + 'px';
        }
        return;
      }
      if (!press) return;
      if (!(e.buttons & 1)) { press = null; endStroke(); return; }
      if (!press.started && Math.hypot(e.clientX - press.x, e.clientY - press.y) > 5) { press.started = true; startStroke(press.x, press.y, press.shift, press.ctrl); }
      if (press.started) extendStroke(e.clientX, e.clientY);
    });
    function cancelZsel() {
      if (!zsel) return;
      zselBox().style.display = 'none'; zsel = null;
    }
    document.addEventListener('mouseup', e => {
      if (zgrab && e.button === 0) { zgrab = null; document.body.classList.remove('zgrab'); sendFrame(true); suppressClick = true; setTimeout(() => { suppressClick = false; }, 0); return; }
      if (zsel && e.button === 0) {
        const s = zsel, was = s.started;
        zselBox().style.display = 'none';
        if (!was) { zsel = null; return; }                              // 動かさずに離したときは、ふつうのクリック（拡大中は、何もしない）
        zsel = null;
        suppressClick = true; setTimeout(() => { suppressClick = false; }, 0);
        let u1, v1, u2, v2;
        if (role === 'presenter') {
          const inner = document.querySelector('#presenter .cur-pane .inner'); if (!inner) return;
          const r = inner.getBoundingClientRect();
          u1 = (s.x - r.left) / r.width; v1 = (s.y - r.top) / r.height; u2 = (e.clientX - r.left) / r.width; v2 = (e.clientY - r.top) / r.height;
        } else {
          if (Math.abs(e.clientX - s.x) < 8 || Math.abs(e.clientY - s.y) < 8) return;
          const a = viewportToSlide({ x: s.x, y: s.y }), b = viewportToSlide({ x: e.clientX, y: e.clientY });
          u1 = a.u; v1 = a.v; u2 = b.u; v2 = b.v;
        }
        const du = Math.abs(u2 - u1), dv = Math.abs(v2 - v1);
        if (du < 0.01 || dv < 0.01) return;
        setFrame((u1 + u2) / 2, (v1 + v2) / 2, fitK(du, dv));
        sendFrame(true);
        toast('選んだ範囲を拡大しました（' + zoomK.toFixed(1) + ' 倍。縁をドラッグして位置を動かせます）');
        return;
      }
      if (e.button === 0 && press) { if (press.started) { endStroke(); suppressClick = true; setTimeout(() => { suppressClick = false; }, 0); } press = null; }
    });

    if (role === 'presenter') {                                                                        // 手元の画面でも、スライドの上のクリックで進める（左: 次、右: 前）
      const inPane = t => !!(t.closest && t.closest('#presenter .cur-pane, #presenter .next-pane'));
      document.addEventListener('click', e => { if (e.button !== 0 || !inPane(e.target)) return; if (suppressClick) { suppressClick = false; return; } if (!zoomOn) next(); });
      document.addEventListener('contextmenu', e => { if (inPane(e.target)) { e.preventDefault(); prev(); } });
    }
    document.addEventListener('click', e => { const a = e.target.closest && e.target.closest('a'); if (a) e.preventDefault(); }, true);     // 発表中は、リンクを開かない（ウィンドウが別のページに変わらないように）
    document.addEventListener('wheel', e => {
      if (overviewOn) return;
      if (zoomOn) { const up = e.deltaY < 0; zoomK = Math.round(Math.min(5, Math.max(1, zoomK + (up ? (zoomK < 2 ? 0.1 : 0.25) : (zoomK <= 2 ? -0.1 : -0.25)))) * 100) / 100; zc = clampCenter(zc.u, zc.v); mapActive = Date.now(); applyTransform(); toast(zoomK <= 1 ? '等倍' : '拡大 ' + zoomK.toFixed(2) + ' 倍'); sendFrame(true); e.preventDefault(); return; }
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
