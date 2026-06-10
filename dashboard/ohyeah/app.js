/* OH YEAH™ — core recovery loop prototype
 * Architecture:
 *   1. Thought stream   — captures utterances (demo player OR live Web Speech API)
 *   2. Retrieval layer  — instant (<300ms): last utterance, topic, thread
 *   3. Smart layer      — streams in a beat later: prediction + next thoughts
 *                         (heuristic by default; optional local Ollama hook)
 */

/* ─────────────────────────── DOM ─────────────────────────── */
const $ = (id) => document.getElementById(id);
const el = {
  orb: $('orb'), recall: $('recall'),
  crawl: $('crawl'), crawlPlane: $('crawlPlane'), interim: $('interim'), streamHint: $('streamHint'),
  warpflash: $('warpflash'),
  topicChip: $('topicChip'), topicValue: $('topicValue'), status: $('status'),
  scrim: $('cardScrim'), card: $('card'), cardClose: $('cardClose'),
  cardSaid: $('cardSaid'), cardTopic: $('cardTopic'), cardThread: $('cardThread'),
  recallMs: $('recallMs'),
  smartBadge: $('smartBadge'), cardPredict: $('cardPredict'), cardNext: $('cardNext'),
  ohyeah: $('ohyeah'),
  modeBtns: [...document.querySelectorAll('.mode__btn')],
};

/* ─────────────────────────── State ─────────────────────────── */
const state = {
  mode: 'demo',          // 'demo' | 'live'
  listening: false,
  utterances: [],        // { text, t } finalized
  startedAt: 0,
};

const OLLAMA = {
  enabled: false,                          // flip true to use a real local model
  url: 'http://localhost:11434/api/generate',
  model: 'llama3.2:3b',
};

/* ═══════════════════════ 0. STARFIELD (parallax + hyperspace warp) ═══════════════════════ */
let warpStars = () => {};            // assigned by sky(); recover() calls it
let constellationLayer = () => {};   // assigned by the memory module; sky() calls it per frame
let burstSky = () => {};             // assigned by sky(); the knock delighter calls it
(function sky() {
  const cv = document.getElementById('sky');
  const ctx = cv.getContext('2d');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let stars = [], W = 0, H = 0, dpr = Math.min(window.devicePixelRatio || 1, 2);
  let cx = 0, cy = 0;                 // warp/vanishing center
  let px = 0, py = 0, tpx = 0, tpy = 0;  // parallax offset (smoothed) + target
  let warpStart = 0, warpEnd = 0;

  function resize() {
    W = cv.clientWidth = innerWidth; H = cv.clientHeight = innerHeight;
    cv.width = W * dpr; cv.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    cx = W / 2; cy = H * 0.42;        // a touch above center, toward the crawl/orb
    const count = Math.round((W * H) / 8200);
    stars = Array.from({ length: count }, (_, i) => {
      const depth = 0.35 + Math.random();                 // parallax depth far→near
      const big = i % 9 === 0;
      return {
        x: Math.random() * W, y: Math.random() * H,
        r: (big ? 1.1 + Math.random() * 1.4 : 0.4 + Math.random() * 0.9) * (0.6 + depth * 0.5),
        a: 0.25 + Math.random() * 0.6,
        ph: (i * 1.7) % (Math.PI * 2),
        sp: 0.5 + (i % 7) * 0.16,
        dx: (Math.random() - 0.5) * 0.03,
        dy: 0.015 + Math.random() * 0.035,
        depth,
        hue: big ? (i % 2 ? 'rgba(60,224,255,' : 'rgba(164,114,255,') : 'rgba(244,246,251,',
      };
    });
  }

  warpStars = (ms = 760) => { if (reduce) return; warpStart = performance.now(); warpEnd = warpStart + ms; };

  /* short-lived spark particles (the knock delighter) — drawn in the same frame loop */
  const sparks = [];
  burstSky = (x, y, n = 24, power = 3, gold = false, drift = -0.18) => {
    if (reduce) return;
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2, v = power * (0.35 + Math.random());
      sparks.push({
        x, y,
        vx: Math.cos(a) * v, vy: Math.sin(a) * v + power * drift,
        life: 1, dk: 0.012 + Math.random() * 0.022,
        r: 0.8 + Math.random() * (gold ? 2.6 : 1.8),
        hue: gold && i % 3 !== 2 ? 'rgba(255,215,106,' : (i % 2 ? 'rgba(60,224,255,' : 'rgba(164,114,255,'),
      });
    }
  };

  let t = 0;
  function frame(now) {
    t += 0.016;
    px += (tpx - px) * 0.06; py += (tpy - py) * 0.06;
    ctx.clearRect(0, 0, W, H);
    const warping = now < warpEnd;
    const wp = warping ? 1 - (warpEnd - now) / (warpEnd - warpStart) : 0;   // 0→1
    for (const s of stars) {
      if (!reduce) {
        s.y += s.dy; s.x += s.dx;
        if (s.y > H + 2) { s.y = -2; s.x = Math.random() * W; }
        if (s.x < -2) s.x = W + 2; else if (s.x > W + 2) s.x = -2;
      }
      const sx = s.x + px * s.depth, sy = s.y + py * s.depth;   // parallax by depth
      const tw = reduce ? 1 : 0.55 + 0.45 * Math.sin(t * s.sp + s.ph);
      if (warping) {
        // streak outward from the warp center (lightspeed)
        const ease = Math.sin(wp * Math.PI);                    // ramp up then down
        const stretch = 1 + ease * 7 * s.depth;
        const ex = cx + (sx - cx) * stretch, ey = cy + (sy - cy) * stretch;
        ctx.strokeStyle = s.hue + (s.a * tw * 0.85).toFixed(3) + ')';
        ctx.lineWidth = Math.max(0.6, s.r);
        ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(ex, ey); ctx.stroke();
      } else {
        ctx.beginPath();
        ctx.arc(sx, sy, s.r, 0, Math.PI * 2);
        ctx.fillStyle = s.hue + (s.a * tw).toFixed(3) + ')';
        if (s.r > 1) { ctx.shadowBlur = 8; ctx.shadowColor = s.hue + '0.7)'; }
        else ctx.shadowBlur = 0;
        ctx.fill();
      }
    }
    for (let i = sparks.length - 1; i >= 0; i--) {
      const p = sparks[i];
      p.x += p.vx; p.y += p.vy; p.vy += 0.05; p.vx *= 0.985; p.vy *= 0.985;
      p.life -= p.dk;
      if (p.life <= 0) { sparks.splice(i, 1); continue; }
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = p.hue + (p.life * 0.9).toFixed(3) + ')';
      ctx.fill();
    }
    ctx.shadowBlur = 0;
    constellationLayer(ctx, W, H, px, py, t);
    if (!reduce) requestAnimationFrame(frame);
  }

  if (!reduce) {
    addEventListener('pointermove', (e) => { tpx = (e.clientX / W - 0.5) * 30; tpy = (e.clientY / H - 0.5) * 22; }, { passive: true });
    addEventListener('deviceorientation', (e) => {
      if (e.gamma == null) return;
      tpx = Math.max(-1, Math.min(1, e.gamma / 30)) * 26;
      tpy = Math.max(-1, Math.min(1, (e.beta - 45) / 30)) * 20;
    }, { passive: true });
  }
  addEventListener('resize', resize, { passive: true });
  resize();
  frame(performance.now());          // draws once; self-schedules only if !reduce
})();

/* ═══════════════════════ 1. THOUGHT STREAM ═══════════════════════ */

function pushUtterance(text) {
  text = text.trim();
  if (!text) return;
  const ut = { text, t: Date.now() };
  state.utterances.push(ut);
  renderStream();
  updateTopicChip();
  memAdd(ut.text, ut.t);
}

function setInterim(text) {
  el.interim.textContent = text || '';   // flat sibling near the orb — not part of the 3D scroller
}

/* ── 3D crawl engine ──────────────────────────────────────────────────────────
 * The scroller (.crawl) is UNtransformed — only `perspective` — so native scroll
 * stays vanilla. Each line gets a per-frame translateZ/rotateX/opacity from its
 * cached offsetTop vs scrollTop → a true ascending recede. Lines are in normal
 * flow, so they can never overlap. CSS :nth-last-child is the always-correct floor;
 * JS refines the depth on top. */
const CRAWL = { ZMAX: 560, ROT: 16, DIM: 0.62, GAIN: 1.7, HALO: 170 };
let crawlDirty = true, crawlStick = true, crawlRAF = 0;
const crawlReduce = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

function measureLine(ln) { ln._top = ln.offsetTop; ln._h = ln.offsetHeight; }
function remeasureCrawl() {
  for (const ln of el.crawlPlane.children) measureLine(ln);
  crawlDirty = true;
  scrollFeedToBottom();        // re-pin when the viewport resolves its height (0 → real)
}

let renderedCount = 0;
function renderStream() {
  const u = state.utterances;
  if (u.length < renderedCount) { el.crawlPlane.innerHTML = ''; renderedCount = 0; }  // reset/cleared
  el.streamHint.style.display = u.length ? 'none' : '';
  for (let i = renderedCount; i < u.length; i++) {          // append only new lines (push old up)
    const line = document.createElement('p');
    line.className = 'crawl__line';
    line.textContent = u[i].text;
    el.crawlPlane.appendChild(line);
    measureLine(line);                                       // cache before first paint
  }
  renderedCount = u.length;
  while (el.crawlPlane.children.length > 240) el.crawlPlane.removeChild(el.crawlPlane.firstChild);  // bound DOM
  crawlDirty = true;
  scrollFeedToBottom();
}

/* pin to newest unless the user has scrolled up to read history */
function scrollFeedToBottom(force) {
  const c = el.crawl; if (!c) return;
  if (force) crawlStick = true;
  if (crawlStick) c.scrollTop = c.scrollHeight;
  crawlDirty = true;
}

function onCrawlScroll() {
  const c = el.crawl;
  crawlStick = (c.scrollHeight - c.scrollTop - c.clientHeight) < 60;
  crawlDirty = true;
}

/* the per-line foreshortening pass — only repaints on a dirty frame */
function crawlTick() {
  if (crawlDirty && !crawlReduce()) {
    const c = el.crawl, H = c.clientHeight, st = c.scrollTop, lines = el.crawlPlane.children;
    for (let i = 0; i < lines.length; i++) {
      const ln = lines[i];
      if (ln._top == null) measureLine(ln);
      const yTop = ln._top - st, yc = yTop + ln._h * 0.5;          // center vs viewport
      if (yc < -CRAWL.HALO || yTop > H + CRAWL.HALO) {             // off-halo → strip transform
        if (ln._on) { ln.style.transform = ''; ln.style.opacity = ''; ln.style.willChange = 'auto'; ln._on = false; }
        continue;
      }
      ln._on = true; ln.style.willChange = 'transform, opacity';
      // 0 = near (bottom/orb) → 1 = far. GAIN makes the recede fully develop over the
      // bottom ~60% of the viewport, so it reads strong on tall desktop windows too.
      const d = Math.min(1, Math.max(0, (1 - yc / H) * CRAWL.GAIN));
      ln.style.transform = `translateZ(${(-CRAWL.ZMAX * d).toFixed(1)}px) rotateX(${(CRAWL.ROT * d).toFixed(1)}deg)`;
      ln.style.opacity = (1 - CRAWL.DIM * d).toFixed(2);
    }
    crawlDirty = false;
  }
  crawlRAF = requestAnimationFrame(crawlTick);
}

/* ═══════════════════════ 2. NLP (retrieval) ═══════════════════════ */

const STOP = new Set(('a about above after again against all am an and any are arent as at be because been before being below between both but by cant cannot could couldnt did didnt do does doesnt doing dont down during each few for from further had hadnt has hasnt have havent having he her here hers herself him himself his how i im id if in into is isnt it its itself just like me more most my myself no nor not of off on once only or other ought our ours ourselves out over own really same she should shouldnt so some such than that thats the their theirs them themselves then there theres these they theyre this those through to too under until up very was wasnt we were werent what whats when where which while who whom why will with wont would wouldnt you youre your yours yourself yourselves oh okay ok um uh so wait sorry kind sort thing things gonna wanna got get really actually honestly maybe probably basically yeah right now one two also even still well ' +
  // discourse fillers & connectors that masquerade as topics
  'whole point side idea ideas core lot bit part parts stuff way ways much many big plus reminds means make makes made need needs want wants going stuff thats theres heres everywhere obviously ' +
  'instead becomes become already around across without within toward towards along among able actual probably basically literally').split(' '));

function tokenize(s) {
  return (s.toLowerCase().match(/[a-z][a-z'’]+/g) || []).map(w => w.replace(/['’]/g, ''));
}

/** Score keywords across a window. recencyStrength=0 → pure frequency (stable topic);
 *  higher → favors recently-opened threads. */
function keywordScores(utterances, windowSize = 10, recencyStrength = 0.25) {
  const win = utterances.slice(-windowSize);
  const scores = new Map();
  win.forEach((u, idx) => {
    const r = win.length > 1 ? idx / (win.length - 1) : 1;   // 0 oldest … 1 newest
    const recency = 1 + recencyStrength * r;
    for (const w of tokenize(u.text)) {
      if (w.length < 4 || STOP.has(w)) continue;
      scores.set(w, (scores.get(w) || 0) + recency);
    }
  });
  return scores;
}

/** Find the strongest noun-ish bigram for a nicer topic label.
 *  Only trusts a bigram that actually RECURS (count>=2) — this blocks single-shot
 *  discourse/adjacency phrases ("whole point", "institutions people") from hijacking
 *  the topic via recency. Non-recurring conversations fall back to the keyword form. */
function topBigram(utterances, scores, windowSize = 10) {
  const win = utterances.slice(-windowSize);
  const counts = new Map();
  for (const u of win) {
    const toks = tokenize(u.text);
    for (let i = 0; i < toks.length - 1; i++) {
      const [a, b] = [toks[i], toks[i + 1]];
      if (a.length < 4 || b.length < 4 || STOP.has(a) || STOP.has(b)) continue;
      counts.set(a + ' ' + b, (counts.get(a + ' ' + b) || 0) + 1);
    }
  }
  let best = null, bestScore = 0;
  for (const [bg, c] of counts) {
    if (c < 2) continue;                       // must recur to be trusted
    const [a, b] = bg.split(' ');
    const s = c * 3 + (scores.get(a) || 0) + (scores.get(b) || 0);
    if (s > bestScore) { best = bg; bestScore = s; }
  }
  return best;
}

function titleCase(s) { return s.replace(/\b\w/g, c => c.toUpperCase()); }

function rankedKeywords(scores, n) {
  return [...scores.entries()].sort((a, b) => b[1] - a[1]).slice(0, n).map(e => e[0]);
}

/** The instant retrieval payload. Pure synchronous JS → effectively 0ms. */
function retrieve() {
  const u = state.utterances;
  const last = u.length ? u[u.length - 1].text : '';

  // TOPIC = stable subject → frequency-dominant
  const topicScores = keywordScores(u, 10, 0.25);
  const bg = topBigram(u, topicScores);
  const top = rankedKeywords(topicScores, 3);
  const topic = bg ? titleCase(bg) : (top.slice(0, 2).map(titleCase).join(' · ') || '—');
  // only the *shown* topic words are off-limits as "next thoughts"
  const topicTokens = new Set(bg ? bg.split(' ') : top.slice(0, 2));

  const thread = u.slice(-4, -1).map(x => x.text);   // fragments just before the last
  return { last, topic, thread, topicScores, keywords: top, topicTokens };
}

/* ═══════════════════════ 3. SMART LAYER ═══════════════════════ */

/** The headline of a single utterance = its strongest content word.
 *  Tiebreak by earliest position (the object usually leads the clause). */
function utteranceHead(text, topicScores) {
  const toks = tokenize(text);
  const cand = [];
  toks.forEach((w, i) => { if (!STOP.has(w) && w.length >= 4) cand.push({ w, i }); });
  if (!cand.length) return null;
  cand.sort((a, b) => (topicScores.get(b.w) || 0) - (topicScores.get(a.w) || 0) || a.i - b.i);
  return cand[0].w;
}

/** Headlines of recent thoughts you opened but didn't close — most recent first.
 *  Excludes the just-said thought and the main topic. */
function recentThreadHeads(r) {
  const u = state.utterances;
  const heads = [], seen = new Set(tokenize(r.last));
  for (let i = u.length - 2; i >= 0; i--) {
    const h = utteranceHead(u[i].text, r.topicScores);
    if (!h || seen.has(h) || r.topicTokens.has(h)) continue;
    seen.add(h); heads.push(h);
  }
  return heads;
}

function last_trailing(s) {
  s = s.trim();
  return s.endsWith('…') || s.endsWith('-') || s.endsWith('—') ||
         /\b(but|and|so|because|which|then|plus|like)\s*[.,…-]*$/i.test(s);
}

/** Heuristic "where you were going" — built from open threads, not canned. */
function predictContinuation(r) {
  const heads = recentThreadHeads(r);
  const nextThread = titleCase(heads[0] || r.keywords[1] || r.keywords[0] || 'where it leads');

  if (last_trailing(r.last)) {
    // what were they mid-sentence ON? → strongest topical word in the last utterance
    const inLast = tokenize(r.last)
      .filter(w => !STOP.has(w) && w.length >= 4)
      .sort((a, b) => (r.topicScores.get(b) || 0) - (r.topicScores.get(a) || 0));
    const anchor = titleCase(inLast[0] || r.keywords[0] || 'it');
    return `You trailed off on ${anchor} — you were about to tie it back to ${nextThread}.`;
  }
  const anchor = titleCase(r.keywords[0] || 'this');
  return `You were building toward ${nextThread}, with ${anchor} as the anchor — the next move was connecting them.`;
}

/** 2–3 "potential next thoughts" — headlines of recent open threads. */
function nextThoughts(r) {
  let picks = recentThreadHeads(r).slice(0, 3).map(titleCase);
  if (picks.length < 2) {                                  // very short conversation → backfill
    const seen = new Set(picks.map(p => p.toLowerCase()));
    for (const kw of r.keywords) {
      if (!seen.has(kw)) { seen.add(kw); picks.push(titleCase(kw)); }
      if (picks.length >= 3) break;
    }
  }
  const frames = [
    (k) => `Back to ${k} — you opened that and never closed it`,
    (k) => `The ${k} angle`,
    (k) => `What about ${k}?`,
  ];
  return picks.map((k, i) => frames[i % frames.length](k));
}

/** Optional: ask a local Ollama model for the smart layer. Falls back silently. */
async function askOllama(payload) {
  if (!OLLAMA.enabled) return null;
  const transcript = state.utterances.map(u => u.text).join(' ');
  const prompt =
    `Someone was talking and lost their train of thought. Here is what they said:\n"""${transcript}"""\n\n` +
    `In one short sentence, tell them where they were going next. Then list 3 short bullet "next thoughts". ` +
    `Reply as JSON: {"prediction": "...", "next": ["...","...","..."]}`;
  try {
    const ctrl = new AbortController();
    const to = setTimeout(() => ctrl.abort(), 8000);
    const res = await fetch(OLLAMA.url, {
      method: 'POST', signal: ctrl.signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: OLLAMA.model, prompt, stream: false, format: 'json' }),
    });
    clearTimeout(to);
    if (!res.ok) return null;
    const data = await res.json();
    const parsed = JSON.parse(data.response);
    if (parsed && parsed.prediction) return parsed;
  } catch (_) { /* fall back to heuristic */ }
  return null;
}

/* ═══════════════════════ RECOVERY — the moment ═══════════════════════ */

let cardOpenedAt = 0;   // guards against the opening tap also closing the scrim

async function recover() {
  if (!state.utterances.length) {
    flashStatus('Nothing captured yet — start talking first');
    return;
  }
  const t0 = performance.now();
  const r = retrieve();
  const ms = Math.max(1, Math.round(performance.now() - t0));

  // ── THE WARP: yank the lost thread back out of deep space ──
  triggerWarp();

  // ── instant retrieval layer (prepped now, revealed out of the warp) ──
  el.cardSaid.textContent = r.last || '—';
  el.cardTopic.textContent = r.topic;
  el.cardThread.innerHTML = '';
  (r.thread.length ? r.thread : ['(this was the start of the thread)']).forEach(t => {
    const li = document.createElement('li'); li.textContent = t; el.cardThread.appendChild(li);
  });
  el.recallMs.textContent = `· ${ms}ms`;

  // reset smart layer
  el.cardPredict.innerHTML = '<span class="cursor"></span>';
  el.cardNext.innerHTML = '';
  el.smartBadge.textContent = '✦ thinking…';
  el.smartBadge.classList.add('is-thinking');

  // card materializes a beat later, out of the lightspeed streak
  await wait(reducedMotion() ? 0 : 380);
  cardOpenedAt = performance.now();
  el.scrim.hidden = false;

  // ── smart layer, a beat later (dramatizes 300ms retrieval vs generation) ──
  const smart = (await askOllama(r)) || {
    prediction: predictContinuation(r),
    next: nextThoughts(r),
  };

  await wait(reducedMotion() ? 0 : 420);
  el.smartBadge.textContent = OLLAMA.enabled ? '✦ local model' : '✦ predicted';
  el.smartBadge.classList.remove('is-thinking');
  await typeInto(el.cardPredict, smart.prediction, 16);

  smart.next.forEach((txt, i) => {
    const li = document.createElement('li');
    li.style.animationDelay = (i * 90) + 'ms';
    li.innerHTML = `<span class="spark">✦</span><span>${escapeHtml(txt)}</span>`;
    el.cardNext.appendChild(li);
  });

  fireOhYeah();
}

function closeCard() { el.scrim.hidden = true; }

/* ═══════════════════════ The brand beat ═══════════════════════ */
function fireOhYeah() {
  el.ohyeah.classList.remove('is-on');
  void el.ohyeah.offsetWidth;          // reflow → restart animation
  el.ohyeah.classList.add('is-on');
  setTimeout(() => el.ohyeah.classList.remove('is-on'), 1700);
}

const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

/* The recall warp: flatten the crawl toward the viewer, streak the stars, flash. */
function triggerWarp() {
  scrollFeedToBottom(true);     // snap to the newest thread on recall
  if (reducedMotion()) return;
  if (el.crawl) {
    el.crawl.classList.add('is-recalling');
    setTimeout(() => el.crawl && el.crawl.classList.remove('is-recalling'), 900);
  }
  warpStars(760);
  if (el.warpflash) {
    el.warpflash.classList.remove('is-on');
    void el.warpflash.offsetWidth;
    el.warpflash.classList.add('is-on');
    setTimeout(() => el.warpflash.classList.remove('is-on'), 760);
  }
}

/* ═══════════════════════ INPUT: demo player ═══════════════════════ */

const DEMO_SCRIPT = [
  "Okay so the core idea is a citywide festival that connects museums and neighborhoods.",
  "Instead of one big venue, the whole city becomes the venue for a weekend.",
  "Each neighborhood hosts its own thing — galleries, food, local artists, music on the corners.",
  "And the museums act as anchors, so there's a spine of institutions people already know.",
  "Which means we'd need sponsors, obviously, probably tiered, civic plus corporate.",
  "Oh and ticketing — it should be one pass that works everywhere, tap to enter, no paper.",
  "That reminds me, the app could do wayfinding too, a living map of what's happening right now.",
  "And then there's the community side, which is honestly the whole point, but…",
];

let demoTimer = null;
let demoIdx = 0;

function startDemo() {
  if (demoIdx >= DEMO_SCRIPT.length) { demoIdx = 0; state.utterances = []; memRollover(); renderStream(); }
  streamNextDemoLine();
}

function streamNextDemoLine() {
  if (demoIdx >= DEMO_SCRIPT.length) {
    setInterim('');
    setStatus('Demo · you lost the thread. Hit the button ↓');
    stopListeningVisual();
    return;
  }
  const line = DEMO_SCRIPT[demoIdx];
  const words = line.split(' ');
  let i = 0;
  const tick = () => {
    if (!state.listening) return;             // paused
    i++;
    setInterim(words.slice(0, i).join(' '));
    if (i >= words.length) {
      pushUtterance(line);
      setInterim('');
      demoIdx++;
      demoTimer = setTimeout(streamNextDemoLine, 650 + Math.random() * 500);
    } else {
      demoTimer = setTimeout(tick, 95 + Math.random() * 120);
    }
  };
  demoTimer = setTimeout(tick, 250);
}

function pauseDemo() { clearTimeout(demoTimer); }

/* ═══════════════════════ INPUT: live Web Speech API ═══════════════════════ */

let recog = null;
function getRecognizer() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return null;
  const r = new SR();
  r.continuous = true;
  r.interimResults = true;
  r.lang = 'en-US';
  r.onresult = (e) => {
    let interim = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const res = e.results[i];
      if (res.isFinal) pushUtterance(res[0].transcript);
      else interim += res[0].transcript;
    }
    setInterim(interim);
  };
  r.onerror = (e) => {
    if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
      flashStatus('Mic blocked — allow microphone, or use Demo mode', true);
      stopAll();
    } else if (e.error === 'no-speech') {
      setStatus('Listening… (say something)');
    }
  };
  r.onend = () => { if (state.listening && state.mode === 'live') { try { r.start(); } catch (_) {} } };
  return r;
}

/* ═══════════════════════ Listening control ═══════════════════════ */

function startListening() {
  state.listening = true;
  if (!state.startedAt) state.startedAt = Date.now();
  el.orb.classList.add('is-live');
  el.orb.setAttribute('aria-label', 'Stop listening');

  if (state.mode === 'demo') {
    setStatus('Demo · listening…');
    startDemo();
  } else {
    if (!recog) recog = getRecognizer();
    if (!recog) { flashStatus('Live mic unsupported in this browser — use Demo', true); stopListeningVisual(); state.listening = false; return; }
    try { recog.start(); setStatus('Live · listening…'); }
    catch (_) { /* already started */ }
  }
}

function stopListeningVisual() {
  el.orb.classList.remove('is-live');
  el.orb.setAttribute('aria-label', 'Start listening');
}

function stopAll() {
  state.listening = false;
  stopListeningVisual();
  pauseDemo();
  if (recog) { try { recog.stop(); } catch (_) {} }
  setInterim('');
}

function toggleListening() {
  if (state.listening) {
    stopAll();
    setStatus(state.mode === 'demo' ? 'Demo · paused' : 'Live · paused');
  } else {
    startListening();
  }
}

/* ═══════════════════════ Mode switching ═══════════════════════ */
function setMode(mode) {
  if (mode === state.mode) return;
  stopAll();
  state.mode = mode;
  state.utterances = [];
  demoIdx = 0;
  state.startedAt = 0;
  memRollover();               // the finished thread crystallizes into the sky
  renderStream();
  el.streamHint.style.opacity = '0.8';
  updateTopicChip();
  el.modeBtns.forEach(b => {
    const active = b.dataset.mode === mode;
    b.classList.toggle('is-active', active);
    b.setAttribute('aria-selected', String(active));
  });
  setStatus(mode === 'demo' ? 'Demo mode · ready' : 'Live mic · ready');
}

/* ═══════════════════════ Topic chip ═══════════════════════ */
function updateTopicChip() {
  if (state.utterances.length < 1) { el.topicChip.hidden = true; return; }
  const { topic } = retrieve();
  if (topic && topic !== '—') {
    el.topicValue.textContent = topic;
    el.topicChip.hidden = false;
  }
}

/* ═══════════════════════ Status helpers ═══════════════════════ */
let statusTimer = null;
function setStatus(t) { el.status.textContent = t; el.status.classList.remove('is-error'); }
function flashStatus(t, isError = false) {
  el.status.textContent = t;
  el.status.classList.toggle('is-error', isError);
  clearTimeout(statusTimer);
  statusTimer = setTimeout(() => {
    setStatus(state.listening ? (state.mode === 'demo' ? 'Demo · listening…' : 'Live · listening…')
                              : (state.mode === 'demo' ? 'Demo mode · ready' : 'Live mic · ready'));
  }, 3200);
}

/* ═══════════════════════ Utils ═══════════════════════ */
const wait = (ms) => new Promise(r => setTimeout(r, ms));
function escapeHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function typeInto(node, text, speed = 18) {
  return new Promise(resolve => {
    node.innerHTML = '';
    const cursor = document.createElement('span'); cursor.className = 'cursor';
    node.appendChild(cursor);
    let i = 0;
    const step = () => {
      if (i >= text.length) { cursor.remove(); resolve(); return; }
      cursor.insertAdjacentText('beforebegin', text[i]);
      i++;
      setTimeout(step, speed + (text[i - 1] === ' ' ? 18 : 0));
    };
    step();
  });
}

/* ═══════════════════════ Wiring ═══════════════════════ */
el.orb.addEventListener('click', toggleListening);
el.recall.addEventListener('click', recover);
el.cardClose.addEventListener('click', closeCard);
el.scrim.addEventListener('click', (e) => {
  // ignore the click that opened the card (its release can land on the fresh scrim)
  if (e.target === el.scrim && performance.now() - cardOpenedAt > 350) closeCard();
});
el.modeBtns.forEach(b => b.addEventListener('click', () => setMode(b.dataset.mode)));

document.addEventListener('keydown', (e) => {
  if (e.code === 'Space' && !e.repeat) {
    if (document.activeElement && /BUTTON/.test(document.activeElement.tagName)) document.activeElement.blur();
    e.preventDefault();
    if (!el.scrim.hidden) return;
    recover();
  } else if (e.code === 'Escape') {
    if (!el.scrim.hidden) closeCard();
    dismissNova();
  } else if (e.code === 'Enter' && e.target === document.body) {
    toggleListening();
  }
});

/* ═══════════════════════ Crawl engine wiring ═══════════════════════ */
el.crawl.addEventListener('scroll', onCrawlScroll, { passive: true });
if ('ResizeObserver' in window) new ResizeObserver(remeasureCrawl).observe(el.crawl);
addEventListener('orientationchange', () => requestAnimationFrame(remeasureCrawl));
if (document.fonts && document.fonts.ready) document.fonts.ready.then(remeasureCrawl);
crawlTick();

/* ═══════════════════════ Intro splash ═══════════════════════ */
const splash = document.getElementById('splash');
function hideSplash() {
  if (!splash || splash.classList.contains('is-hiding')) return;
  splash.classList.add('is-hiding');
  setTimeout(() => { splash.style.display = 'none'; }, 650);
}
if (splash) {
  splash.addEventListener('click', hideSplash);
  setTimeout(hideSplash, 2000);
}

/* ═══════════════════════ 4. MEMORY — constellations ═══════════════════════
 * The app's promise is "never lose a thought" — so the app itself must not
 * forget. Every utterance is appended to an IndexedDB event log
 * ({session, text, t} — the portable schema; see .design/northstar.md).
 * Finished sessions render as faint constellations in the sky: connected
 * star-threads, shape and position deterministic from the session id.
 * Tap one and it returns its memory. All best-effort: if IndexedDB is
 * unavailable (private browsing), capture and recall work exactly as before. */
const MEM = { db: null, sessionId: null, constellations: [], hits: [], MAXSKY: 12 };

function memOpen() {
  return new Promise((res) => {
    try {
      const rq = indexedDB.open('ohyeah', 1);
      rq.onupgradeneeded = () => {
        const db = rq.result;
        db.createObjectStore('utterances', { autoIncrement: true }).createIndex('by-session', 'session');
        db.createObjectStore('sessions', { keyPath: 'id' });
      };
      rq.onsuccess = () => res(rq.result);
      rq.onerror = () => res(null);
    } catch (_) { res(null); }
  });
}

function memAdd(text, t) {
  if (!MEM.db) return;
  try {
    if (!MEM.sessionId) MEM.sessionId = 's' + t.toString(36) + Math.random().toString(36).slice(2, 6);
    const topic = retrieve().topic;
    const tx = MEM.db.transaction(['utterances', 'sessions'], 'readwrite');
    tx.objectStore('utterances').add({ session: MEM.sessionId, text, t });
    const ss = tx.objectStore('sessions');
    const g = ss.get(MEM.sessionId);
    g.onsuccess = () => {
      const row = g.result || { id: MEM.sessionId, startedAt: t, mode: state.mode, count: 0, first: text };
      row.endedAt = t; row.count += 1; row.topic = topic;
      ss.put(row);
    };
  } catch (_) { /* memory is best-effort; capture never blocks on it */ }
}

function memRollover() {
  MEM.sessionId = null;
  memLoadConstellations();
}

function hash32(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

/* A constellation is a thread: stars connected in the order the walk lays them
 * down. Everything derives from the session id, so a thread always rises in
 * the same place in your sky. */
function buildConstellation(row) {
  let h = hash32(row.id) || 1;
  const rnd = () => (h = (Math.imul(h, 1664525) + 1013904223) >>> 0) / 4294967296;
  const cx = 0.07 + rnd() * 0.86;          // fraction of viewport width
  const cy = 0.06 + rnd() * 0.30;          // upper sky band, above the orb
  const n = Math.min(8, Math.max(3, Math.round(2 + Math.log2(row.count + 1))));
  const pts = [];
  let x = 0, y = 0;
  for (let i = 0; i < n; i++) {
    x = Math.max(-90, Math.min(90, x + (rnd() - 0.5) * 76));
    y = Math.max(-55, Math.min(55, y + (rnd() - 0.5) * 52));
    pts.push({ x, y, r: 0.9 + rnd() * 1.5 });
  }
  return { row, cx, cy, pts, ph: rnd() * Math.PI * 2 };
}

function memLoadConstellations() {
  if (!MEM.db) return;
  try {
    const rq = MEM.db.transaction('sessions').objectStore('sessions').getAll();
    rq.onsuccess = () => {
      MEM.constellations = (rq.result || [])
        .filter(s => s.count >= 2 && s.id !== MEM.sessionId)
        .sort((a, b) => b.endedAt - a.endedAt)
        .slice(0, MEM.MAXSKY)
        .map(buildConstellation);
    };
  } catch (_) {}
}

constellationLayer = (ctx, W, H, px, py, t) => {
  MEM.hits.length = 0;
  for (const c of MEM.constellations) {
    const bx = c.cx * W + px * 0.5, by = c.cy * H + py * 0.5;   // mid-field parallax
    const tw = 0.5 + 0.5 * Math.sin(t * 0.4 + c.ph);
    ctx.strokeStyle = 'rgba(140,170,255,' + (0.07 + 0.06 * tw).toFixed(3) + ')';
    ctx.lineWidth = 1;
    ctx.beginPath();
    c.pts.forEach((p, i) => { i ? ctx.lineTo(bx + p.x, by + p.y) : ctx.moveTo(bx + p.x, by + p.y); });
    ctx.stroke();
    ctx.fillStyle = 'rgba(244,240,220,' + (0.35 + 0.3 * tw).toFixed(3) + ')';
    for (const p of c.pts) {
      ctx.beginPath();
      ctx.arc(bx + p.x, by + p.y, p.r, 0, Math.PI * 2);
      ctx.fill();
    }
    MEM.hits.push({ x: bx, y: by, c });
  }
};

async function showConstellation(row) {
  if (NOVA.busy) return;
  NOVA.busy = true;
  tone(523, 0.5, 0.035); tone(659, 0.6, 0.03, 0.12);
  const d = new Date(row.startedAt);
  const when = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) +
               ' · ' + d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  const first = row.first.length > 70 ? row.first.slice(0, 70).trimEnd() + '…' : row.first;
  novaEl.code.style.opacity = '0';
  novaEl.poem.textContent = '';
  novaEl.wrap.hidden = false;
  await typeInto(novaEl.poem, `${row.topic || 'A thread'}\n${row.count} thoughts · ${when}\nit began: “${first}”`, 22);
  novaEl.code.textContent = '✦ constellation · this thread lives in your sky';
  novaEl.code.style.opacity = '1';
}

addEventListener('click', (e) => {
  if (!novaEl.wrap.hidden || !el.scrim.hidden || !MEM.hits.length) return;
  if (e.target.closest('button, .card, .topbar, .orbwrap, .recall, .nova')) return;
  const hit = MEM.hits.find(p => Math.hypot(e.clientX - p.x, e.clientY - p.y) < 72);
  if (hit) showConstellation(hit.c.row);
});

/** Export the entire memory as a plain object — the portability promise. */
function exportMemory() {
  return new Promise((res) => {
    if (!MEM.db) return res({ sessions: [], utterances: [] });
    try {
      const tx = MEM.db.transaction(['sessions', 'utterances']);
      const out = {};
      tx.objectStore('sessions').getAll().onsuccess = (e) => { out.sessions = e.target.result; };
      tx.objectStore('utterances').getAll().onsuccess = (e) => { out.utterances = e.target.result; };
      tx.oncomplete = () => res(out);
      tx.onerror = () => res({ sessions: [], utterances: [] });
    } catch (_) { res({ sessions: [], utterances: [] }); }
  });
}

/** Clear the sky (dev/QA utility — destructive, console-only on purpose). */
function forgetSky() {
  if (!MEM.db) return;
  const tx = MEM.db.transaction(['sessions', 'utterances'], 'readwrite');
  tx.objectStore('sessions').clear();
  tx.objectStore('utterances').clear();
  tx.oncomplete = () => { MEM.constellations = []; MEM.hits.length = 0; MEM.sessionId = null; };
}

memOpen().then((db) => { MEM.db = db; if (db) memLoadConstellations(); });

/* ═══════════════ HIDDEN DELIGHTER: knock on the edge of now ═══════════════
 * Bounce the crawl at its BOTTOM edge (past the newest thought) and stardust
 * pops near the orb. Seven knocks inside a rolling window charge a supernova:
 * flash + spark storm, then a typed cosmic poem and a hidden code.
 * Sound is synth-only, fires on user gestures, kill switch: OHYEAH.NOVA.sound=false */
const NOVA = {
  KNOCKS: 7, WINDOW: 2600, THROTTLE: 240,
  sound: true,
  combo: 0, lastKnock: 0, busy: false,
};
const novaEl = { wrap: $('nova'), poem: $('novaPoem'), code: $('novaCode'), flash: $('novaflash') };
const NOVA_POEM = 'You reached the edge of now.\nNothing past this point is lost —\nit was just waiting to be said.\n— the sky';
const NOVA_CODE = '✦ OHYEAH-NOVA · constellations are coming';
const NOVA_SCALE = [0, 3, 5, 7, 10, 12, 15];   // pentatonic-ish rise, one step per knock

let audioCtx = null;
function tone(freq, dur = 0.2, gain = 0.04, delay = 0, type = 'sine') {
  if (!NOVA.sound) return;
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
    const t0 = audioCtx.currentTime + delay;
    const o = audioCtx.createOscillator(), g = audioCtx.createGain();
    o.type = type; o.frequency.value = freq;
    g.gain.setValueAtTime(gain, t0);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g); g.connect(audioCtx.destination);
    o.start(t0); o.stop(t0 + dur + 0.03);
  } catch (_) { /* no audio — the delighter stays visual */ }
}

function orbCenter() {
  const r = el.orb.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
}

function knock() {
  const now = performance.now();
  if (NOVA.busy || now - NOVA.lastKnock < NOVA.THROTTLE) return;
  if (!state.utterances.length || !el.scrim.hidden) return;
  NOVA.combo = (now - NOVA.lastKnock > NOVA.WINDOW) ? 1 : NOVA.combo + 1;
  NOVA.lastKnock = now;

  const { x, y } = orbCenter();
  burstSky(x, y, 10 + NOVA.combo * 5, 2.4 + NOVA.combo * 0.55);
  tone(392 * Math.pow(2, NOVA_SCALE[Math.min(NOVA.combo - 1, 6)] / 12), 0.22);
  if (!reducedMotion()) {
    el.orb.style.transform = `scale(${(1 + 0.04 * NOVA.combo).toFixed(2)})`;
    setTimeout(() => { el.orb.style.transform = ''; }, 150);
  }
  if (NOVA.combo >= NOVA.KNOCKS) { NOVA.busy = true; setTimeout(supernova, 260); }
}

async function supernova() {
  const { x, y } = orbCenter();
  [392, 494, 587, 784].forEach((f, i) => tone(f, 0.9, 0.04, i * 0.07));
  tone(98, 1.2, 0.05, 0, 'triangle');
  if (!reducedMotion()) {
    burstSky(x, y, 90, 8, true);
    burstSky(x, y, 70, 4.5);
    if (novaEl.flash) {
      novaEl.flash.classList.remove('is-on'); void novaEl.flash.offsetWidth;
      novaEl.flash.classList.add('is-on');
      setTimeout(() => novaEl.flash.classList.remove('is-on'), 950);
    }
    await wait(700);
  }
  novaEl.code.style.opacity = '0';
  novaEl.poem.textContent = '';
  novaEl.wrap.hidden = false;
  await typeInto(novaEl.poem, NOVA_POEM, 26);
  novaEl.code.textContent = NOVA_CODE;
  novaEl.code.style.opacity = '1';
}

/* ── the mirror egg: knock on the EVENT HORIZON (top edge = the past) ──
 * Bouncing at the very top of history sends ghost-dust drifting down and a
 * DESCENDING plink (going back in time). Seven knocks → time echo: a rewind
 * wave travels newest→oldest, your actual first thought of the session turns
 * gold, and the overlay returns it to you. */
const ECHO = { combo: 0, lastKnock: 0 };
const ECHO_CODE = '✦ OHYEAH-ECHO · nothing said is ever gone';
let echoGoldLine = null;

function echoKnock() {
  const now = performance.now();
  if (NOVA.busy || now - ECHO.lastKnock < NOVA.THROTTLE) return;
  if (!state.utterances.length || !el.scrim.hidden) return;
  ECHO.combo = (now - ECHO.lastKnock > NOVA.WINDOW) ? 1 : ECHO.combo + 1;
  ECHO.lastKnock = now;

  const r = el.crawl.getBoundingClientRect();
  burstSky(r.left + r.width / 2, r.top + 24, 8 + ECHO.combo * 4, 1.6 + ECHO.combo * 0.4, false, 0.35);
  tone(392 * Math.pow(2, -NOVA_SCALE[Math.min(ECHO.combo - 1, 6)] / 12), 0.24);
  const first = el.crawlPlane.firstElementChild;          // the past flickers awake
  if (first && !reducedMotion()) {
    first.style.color = '#dfe6ff';
    setTimeout(() => { if (first !== echoGoldLine) first.style.color = ''; }, 250);
  }
  if (ECHO.combo >= NOVA.KNOCKS) { NOVA.busy = true; setTimeout(timeEcho, 260); }
}

async function timeEcho() {
  [784, 587, 494, 392].forEach((f, i) => tone(f, 0.8, 0.04, i * 0.08));
  tone(98, 1.2, 0.05, 0, 'triangle');
  const lines = [...el.crawlPlane.children];
  if (!reducedMotion() && lines.length) {
    el.crawl.scrollTo({ top: 0, behavior: 'smooth' });
    const stagger = Math.min(60, 1600 / lines.length);      // rewind wave, newest → oldest
    lines.slice().reverse().forEach((ln, i) => {
      setTimeout(() => {
        ln.style.color = '#dfe6ff';
        setTimeout(() => { if (ln !== echoGoldLine) ln.style.color = ''; }, 280);
      }, i * stagger);
    });
    await wait(lines.length * stagger + 300);
    echoGoldLine = lines[0];
    echoGoldLine.style.color = 'var(--gold)';
    echoGoldLine.style.textShadow = '0 0 18px rgba(255,215,106,.55)';
    const r = el.crawl.getBoundingClientRect();
    burstSky(r.left + r.width / 2, r.top + 60, 40, 3, true, 0.1);
    await wait(550);
  }
  const firstSaid = state.utterances[0].text;
  const shown = firstSaid.length > 80 ? firstSaid.slice(0, 80).trimEnd() + '…' : firstSaid;
  novaEl.code.style.opacity = '0';
  novaEl.poem.textContent = '';
  novaEl.wrap.hidden = false;
  await typeInto(novaEl.poem, `Time echo.\nThe past kept every word you gave it —\nyour first thought tonight, returned:\n“${shown}”`, 26);
  novaEl.code.textContent = ECHO_CODE;
  novaEl.code.style.opacity = '1';
}

function dismissNova() {
  if (novaEl.wrap.hidden) return;
  novaEl.wrap.hidden = true;
  NOVA.busy = false; NOVA.combo = 0; NOVA.lastKnock = 0;
  ECHO.combo = 0; ECHO.lastKnock = 0;
  if (echoGoldLine) { echoGoldLine.style.color = ''; echoGoldLine.style.textShadow = ''; echoGoldLine = null; }
}

/* knock detection — wheel (desktop), touch pull (mobile), iOS momentum overshoot.
 * Direction picks the egg: down past the newest = nova, up past the oldest = echo. */
el.crawl.addEventListener('wheel', (e) => {
  const c = el.crawl;
  if (e.deltaY > 18 && c.scrollTop + c.clientHeight >= c.scrollHeight - 2) knock();
  else if (e.deltaY < -18 && c.scrollTop <= 1) echoKnock();
}, { passive: true });

let novaTouchY = 0, novaTouchArmed = false, echoTouchArmed = false, novaTouchSpent = false;
el.crawl.addEventListener('touchstart', (e) => {
  const c = el.crawl;
  novaTouchY = e.touches[0].clientY;
  novaTouchArmed = c.scrollTop + c.clientHeight >= c.scrollHeight - 2;
  echoTouchArmed = c.scrollTop <= 1;
  novaTouchSpent = false;
}, { passive: true });
el.crawl.addEventListener('touchmove', (e) => {
  if (novaTouchSpent) return;
  const dy = e.touches[0].clientY - novaTouchY;
  if (novaTouchArmed && dy < -26) { novaTouchSpent = true; knock(); }
  else if (echoTouchArmed && dy > 26) { novaTouchSpent = true; echoKnock(); }
}, { passive: true });
el.crawl.addEventListener('scroll', () => {
  const c = el.crawl;
  if (c.scrollTop + c.clientHeight - c.scrollHeight > 6) knock();
  else if (c.scrollTop < -6) echoKnock();
}, { passive: true });

novaEl.wrap.addEventListener('click', dismissNova);

/* ═══════════════════════ PWA service worker ═══════════════════════ */
if ('serviceWorker' in navigator) {
  // when a NEW worker takes control, reload once so updates show immediately
  const hadController = !!navigator.serviceWorker.controller;
  let reloaded = false;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (!hadController || reloaded) return;     // skip the first-ever install
    reloaded = true; location.reload();
  });
  addEventListener('load', () => {
    navigator.serviceWorker.register('sw.js').catch(() => { /* offline/unsupported — app still runs */ });
  });
}

// expose a tiny hook for tinkering / enabling the local model from the console
window.OHYEAH = { state, OLLAMA, NOVA, ECHO, MEM, recover, setMode, pushUtterance, retrieve, DEMO_SCRIPT, hideSplash, exportMemory, forgetSky };

setStatus('Demo mode · ready');
