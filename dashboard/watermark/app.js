// PDF watermarker — fully client-side.
// Coordinates are stored as fractions of page width/height so a single global
// box renders correctly across mixed page sizes. Per-page overrides win when set.

import * as pdfjsLib from "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.0.379/pdf.min.mjs";
pdfjsLib.GlobalWorkerOptions.workerSrc =
  "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.0.379/pdf.worker.min.mjs";

const { PDFDocument } = PDFLib;

const $ = (id) => document.getElementById(id);
const pdfInput  = $("pdf-input");
const logoInput = $("logo-input");
const stage     = $("stage");
const canvas    = $("pdf-canvas");
const overlay   = $("overlay");
const logoBox   = $("logo-box");
const logoImg   = $("logo-img");
const pageLabel = $("page-label");
const applyAllChk = $("apply-all");
const statusEl  = $("status");

const state = {
  pdfBytes: null,        // ArrayBuffer of original PDF
  logoBytes: null,       // ArrayBuffer of logo
  logoMime: null,        // "image/png" | "image/jpeg"
  pdfDoc: null,          // pdf.js doc
  pageNum: 1,
  pageCount: 0,
  globalRect: null,      // {x, y, w, h} in fractions of page (origin top-left)
  overrides: new Map(),  // pageIndex -> rect (overrides global)
  renderedSize: null,    // {w, h} px of rendered canvas, for hit-testing
};

// ── File loading ─────────────────────────────────────────────────────────────
pdfInput.addEventListener("change", async (e) => {
  const file = e.target.files[0]; if (!file) return;
  $("pdf-name").textContent = file.name;
  state.pdfBytes = await file.arrayBuffer();
  // pdf.js consumes the buffer — keep a copy for pdf-lib later.
  state.pdfDoc = await pdfjsLib.getDocument({ data: state.pdfBytes.slice(0) }).promise;
  state.pageCount = state.pdfDoc.numPages;
  state.pageNum = 1;
  state.overrides.clear();
  state.globalRect = null;
  await renderPage();
  $("step-place").classList.remove("hidden");
  maybeShowDownload();
});

logoInput.addEventListener("change", async (e) => {
  const file = e.target.files[0]; if (!file) return;
  $("logo-name").textContent = file.name;
  state.logoBytes = await file.arrayBuffer();
  state.logoMime = file.type;
  logoImg.src = URL.createObjectURL(file);
  if (!state.globalRect) {
    // Default placement: bottom-right, 15% width, preserving aspect after image loads.
    logoImg.onload = () => {
      const ar = logoImg.naturalWidth / logoImg.naturalHeight;
      const w = 0.15;
      const h = w * (state.renderedSize.w / state.renderedSize.h) / ar;
      state.globalRect = { x: 1 - w - 0.04, y: 1 - h - 0.04, w, h };
      drawBox();
    };
  } else {
    drawBox();
  }
  maybeShowDownload();
});

// ── Page render ──────────────────────────────────────────────────────────────
async function renderPage() {
  const page = await state.pdfDoc.getPage(state.pageNum);
  const maxW = Math.min(900, document.body.clientWidth - 96);
  const baseViewport = page.getViewport({ scale: 1 });
  const scale = maxW / baseViewport.width;
  const viewport = page.getViewport({ scale });
  canvas.width = viewport.width; canvas.height = viewport.height;
  await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
  state.renderedSize = { w: viewport.width, h: viewport.height };
  pageLabel.textContent = `page ${state.pageNum} / ${state.pageCount}`;
  drawBox();
}

$("prev-page").addEventListener("click", async () => {
  if (state.pageNum > 1) { state.pageNum--; await renderPage(); }
});
$("next-page").addEventListener("click", async () => {
  if (state.pageNum < state.pageCount) { state.pageNum++; await renderPage(); }
});
$("reset-page").addEventListener("click", () => {
  state.overrides.delete(state.pageNum - 1);
  drawBox();
});

// ── Box drawing/manipulation ─────────────────────────────────────────────────
function activeRect() {
  return state.overrides.get(state.pageNum - 1) || state.globalRect;
}
function commitRect(r) {
  if (applyAllChk.checked) {
    state.globalRect = r;
    state.overrides.delete(state.pageNum - 1);
  } else {
    state.overrides.set(state.pageNum - 1, r);
  }
}
function drawBox() {
  const r = activeRect();
  if (!r || !state.renderedSize) { logoBox.classList.add("hidden"); return; }
  logoBox.classList.remove("hidden");
  const { w: pw, h: ph } = state.renderedSize;
  logoBox.style.left   = (r.x * pw) + "px";
  logoBox.style.top    = (r.y * ph) + "px";
  logoBox.style.width  = (r.w * pw) + "px";
  logoBox.style.height = (r.h * ph) + "px";
}

// Mouse interactions: draw new box on overlay, drag/resize existing box.
let drag = null;

overlay.addEventListener("mousedown", (e) => {
  if (e.target !== overlay) return; // box/handles handle their own
  const { x, y } = stagePoint(e);
  const fx = x / state.renderedSize.w, fy = y / state.renderedSize.h;
  drag = { mode: "draw", startFx: fx, startFy: fy };
  commitRect({ x: fx, y: fy, w: 0, h: 0 });
  drawBox();
});

logoBox.addEventListener("mousedown", (e) => {
  if (e.target.classList.contains("handle")) {
    drag = { mode: "resize", dir: e.target.dataset.dir, start: stagePoint(e), orig: { ...activeRect() } };
  } else {
    drag = { mode: "move", start: stagePoint(e), orig: { ...activeRect() } };
  }
  e.stopPropagation();
});

window.addEventListener("mousemove", (e) => {
  if (!drag) return;
  const p = stagePoint(e);
  const { w: pw, h: ph } = state.renderedSize;
  if (drag.mode === "draw") {
    const fx = Math.min(drag.startFx, p.x / pw);
    const fy = Math.min(drag.startFy, p.y / ph);
    const fw = Math.abs(p.x / pw - drag.startFx);
    const fh = Math.abs(p.y / ph - drag.startFy);
    commitRect({ x: fx, y: fy, w: fw, h: fh });
  } else if (drag.mode === "move") {
    const dx = (p.x - drag.start.x) / pw, dy = (p.y - drag.start.y) / ph;
    const r = drag.orig;
    commitRect(clamp({ x: r.x + dx, y: r.y + dy, w: r.w, h: r.h }));
  } else if (drag.mode === "resize") {
    const dx = (p.x - drag.start.x) / pw, dy = (p.y - drag.start.y) / ph;
    let { x, y, w, h } = drag.orig;
    if (drag.dir.includes("e")) w += dx;
    if (drag.dir.includes("s")) h += dy;
    if (drag.dir.includes("w")) { x += dx; w -= dx; }
    if (drag.dir.includes("n")) { y += dy; h -= dy; }
    if (w < 0.01) w = 0.01;
    if (h < 0.01) h = 0.01;
    commitRect(clamp({ x, y, w, h }));
  }
  drawBox();
});
window.addEventListener("mouseup", () => { drag = null; });

function stagePoint(e) {
  const rect = canvas.getBoundingClientRect();
  const sx = canvas.width / rect.width;
  return { x: (e.clientX - rect.left) * sx, y: (e.clientY - rect.top) * sx };
}
function clamp(r) {
  r.x = Math.max(0, Math.min(1 - r.w, r.x));
  r.y = Math.max(0, Math.min(1 - r.h, r.y));
  return r;
}

// ── Download ─────────────────────────────────────────────────────────────────
function maybeShowDownload() {
  if (state.pdfBytes && state.logoBytes && state.globalRect) {
    $("step-download").classList.remove("hidden");
  }
}

$("download-btn").addEventListener("click", async () => {
  if (!state.pdfBytes || !state.logoBytes || !state.globalRect) return;
  statusEl.textContent = "stamping…";
  try {
    const pdfDoc = await PDFDocument.load(state.pdfBytes);
    const embed = state.logoMime === "image/png"
      ? await pdfDoc.embedPng(state.logoBytes)
      : await pdfDoc.embedJpg(state.logoBytes);
    const pages = pdfDoc.getPages();
    pages.forEach((page, i) => {
      const r = state.overrides.get(i) || state.globalRect;
      const { width: pw, height: ph } = page.getSize();
      // Convert top-left fractional rect → pdf-lib bottom-left points.
      const w = r.w * pw, h = r.h * ph;
      const x = r.x * pw;
      const y = ph - (r.y * ph) - h;
      page.drawImage(embed, { x, y, width: w, height: h, opacity: 1 });
    });
    const out = await pdfDoc.save();
    const blob = new Blob([out], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    const origName = pdfInput.files[0]?.name?.replace(/\.pdf$/i, "") || "document";
    const a = document.createElement("a");
    a.href = url; a.download = `${origName}-watermarked.pdf`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    statusEl.textContent = "done";
  } catch (err) {
    statusEl.textContent = "error: " + err.message;
    console.error(err);
  }
});
