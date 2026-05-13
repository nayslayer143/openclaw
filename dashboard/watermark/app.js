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
const downloadBtn = $("download-btn");

const state = {
  pdfBytes: null,        // ArrayBuffer of original PDF
  logoBytes: null,       // ArrayBuffer of logo (current — may be cropped)
  logoMime: null,        // "image/png" | "image/jpeg"
  logoNaturalW: 0,
  logoNaturalH: 0,
  pdfDoc: null,
  pageNum: 1,
  pageCount: 0,
  globalRect: null,      // {x, y, w, h} in fractions of page (origin top-left)
  overrides: new Map(),  // pageIndex -> rect
  renderedSize: null,    // {w, h} px of rendered canvas
};

// ── File loading ─────────────────────────────────────────────────────────────
pdfInput.addEventListener("change", async (e) => {
  const file = e.target.files[0]; if (!file) return;
  $("pdf-name").textContent = file.name;
  state.pdfBytes = await file.arrayBuffer();
  // Pre-fill the filename input with "<orig>-watermarked".
  const baseName = file.name.replace(/\.pdf$/i, "");
  $("filename-input").value = `${baseName}-watermarked`;
  state.pdfDoc = await pdfjsLib.getDocument({ data: state.pdfBytes.slice(0) }).promise;
  state.pageCount = state.pdfDoc.numPages;
  state.pageNum = 1;
  state.overrides.clear();
  state.globalRect = null;
  await renderPage();
  $("step-place").classList.remove("hidden");
  updateDownloadButton();
});

logoInput.addEventListener("change", async (e) => {
  const file = e.target.files[0]; if (!file) return;
  $("logo-name").textContent = file.name;
  $("crop-open").disabled = false;
  state.logoBytes = await file.arrayBuffer();
  state.logoMime = file.type;
  await setLogoFromBytes(state.logoBytes, state.logoMime);
  updateDownloadButton();
});

function setLogoFromBytes(bytes, mime) {
  return new Promise((resolve) => {
    const blob = new Blob([bytes], { type: mime });
    const url = URL.createObjectURL(blob);
    logoImg.onload = () => {
      state.logoNaturalW = logoImg.naturalWidth;
      state.logoNaturalH = logoImg.naturalHeight;
      if (!state.globalRect && state.renderedSize) {
        // Default placement: 15% page width, bottom-right, aspect preserved.
        const w = 0.15;
        const h = wToHFraction(w);
        state.globalRect = { x: 1 - w - 0.04, y: 1 - h - 0.04, w, h };
      }
      drawBox();
      resolve();
    };
    logoImg.src = url;
  });
}

// Convert a width-fraction to a height-fraction that preserves logo aspect on the current page render.
function wToHFraction(w) {
  if (!state.renderedSize || !state.logoNaturalW) return w;
  const imageAR = state.logoNaturalW / state.logoNaturalH;
  return (w * state.renderedSize.w) / (imageAR * state.renderedSize.h);
}
function hToWFraction(h) {
  if (!state.renderedSize || !state.logoNaturalH) return h;
  const imageAR = state.logoNaturalW / state.logoNaturalH;
  return (h * state.renderedSize.h * imageAR) / state.renderedSize.w;
}

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
  updateDownloadButton();
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

let drag = null;

overlay.addEventListener("mousedown", (e) => {
  if (e.target !== overlay) return;
  if (!state.logoBytes) return; // need a logo before drawing
  const { x, y } = stagePoint(e, canvas);
  const fx = x / state.renderedSize.w, fy = y / state.renderedSize.h;
  drag = { mode: "draw", startFx: fx, startFy: fy };
  commitRect({ x: fx, y: fy, w: 0, h: wToHFraction(0) });
  drawBox();
});

logoBox.addEventListener("mousedown", (e) => {
  if (e.target.classList.contains("handle")) {
    drag = { mode: "resize", dir: e.target.dataset.dir,
             start: stagePoint(e, canvas), orig: { ...activeRect() } };
  } else {
    drag = { mode: "move", start: stagePoint(e, canvas), orig: { ...activeRect() } };
  }
  e.stopPropagation();
});

window.addEventListener("mousemove", (e) => {
  if (!drag) return;
  if (drag.mode === "crop-draw" || drag.mode === "crop-move" || drag.mode === "crop-resize") {
    return handleCropDrag(e);
  }
  const p = stagePoint(e, canvas);
  const { w: pw, h: ph } = state.renderedSize;

  if (drag.mode === "draw") {
    // Lock aspect — derive width from horizontal drag, height from logo aspect.
    const fxRaw = p.x / pw;
    let w = Math.abs(fxRaw - drag.startFx);
    if (w < 0.005) w = 0.005;
    let h = wToHFraction(w);
    const x = fxRaw < drag.startFx ? drag.startFx - w : drag.startFx;
    const y = (p.y / ph) < drag.startFy ? drag.startFy - h : drag.startFy;
    commitRect(clamp({ x, y, w, h }));
  } else if (drag.mode === "move") {
    const dx = (p.x - drag.start.x) / pw, dy = (p.y - drag.start.y) / ph;
    const r = drag.orig;
    commitRect(clamp({ x: r.x + dx, y: r.y + dy, w: r.w, h: r.h }));
  } else if (drag.mode === "resize") {
    // Aspect-locked: width drives, height follows from logo aspect.
    // Pivot is the opposite corner.
    const o = drag.orig;
    const dir = drag.dir;
    const pivotFx = dir.includes("w") ? o.x + o.w : o.x;
    const pivotFy = dir.includes("n") ? o.y + o.h : o.y;
    const curFx = p.x / pw;
    let w = Math.abs(curFx - pivotFx);
    if (w < 0.01) w = 0.01;
    let h = wToHFraction(w);
    const x = dir.includes("w") ? pivotFx - w : pivotFx;
    const y = dir.includes("n") ? pivotFy - h : pivotFy;
    commitRect(clamp({ x, y, w, h }));
  }
  drawBox();
});
window.addEventListener("mouseup", () => { drag = null; });

function stagePoint(e, refCanvas) {
  const rect = refCanvas.getBoundingClientRect();
  const sx = refCanvas.width / rect.width;
  return { x: (e.clientX - rect.left) * sx, y: (e.clientY - rect.top) * sx };
}
function clamp(r) {
  r.x = Math.max(0, Math.min(1 - r.w, r.x));
  r.y = Math.max(0, Math.min(1 - r.h, r.y));
  return r;
}

// ── Crop tool ────────────────────────────────────────────────────────────────
const cropCanvas  = $("crop-canvas");
const cropOverlay = $("crop-overlay");
const cropBox     = $("crop-box");
const cropState = { rect: null, srcW: 0, srcH: 0, renderedW: 0, renderedH: 0 };

$("crop-open").addEventListener("click", openCrop);
$("crop-cancel").addEventListener("click", closeCrop);
$("crop-apply").addEventListener("click", applyCrop);

async function openCrop() {
  if (!state.logoBytes) return;
  const img = new Image();
  img.onload = () => {
    cropState.srcW = img.naturalWidth;
    cropState.srcH = img.naturalHeight;
    const maxW = Math.min(900, document.body.clientWidth - 96);
    const scale = Math.min(1, maxW / img.naturalWidth);
    cropState.renderedW = img.naturalWidth * scale;
    cropState.renderedH = img.naturalHeight * scale;
    cropCanvas.width = cropState.renderedW;
    cropCanvas.height = cropState.renderedH;
    cropCanvas.getContext("2d").drawImage(img, 0, 0, cropState.renderedW, cropState.renderedH);
    // Default crop = full image.
    cropState.rect = { x: 0, y: 0, w: 1, h: 1 };
    drawCropBox();
    $("step-crop").classList.remove("hidden");
    $("step-crop").scrollIntoView({ behavior: "smooth", block: "start" });
  };
  img.src = URL.createObjectURL(new Blob([state.logoBytes], { type: state.logoMime }));
}

function closeCrop() { $("step-crop").classList.add("hidden"); }

function drawCropBox() {
  const r = cropState.rect; if (!r) return;
  cropBox.classList.remove("hidden");
  cropBox.style.left   = (r.x * cropState.renderedW) + "px";
  cropBox.style.top    = (r.y * cropState.renderedH) + "px";
  cropBox.style.width  = (r.w * cropState.renderedW) + "px";
  cropBox.style.height = (r.h * cropState.renderedH) + "px";
}

cropOverlay.addEventListener("mousedown", (e) => {
  if (e.target !== cropOverlay) return;
  const p = stagePoint(e, cropCanvas);
  const fx = p.x / cropState.renderedW, fy = p.y / cropState.renderedH;
  drag = { mode: "crop-draw", startFx: fx, startFy: fy };
  cropState.rect = { x: fx, y: fy, w: 0, h: 0 };
  drawCropBox();
});
cropBox.addEventListener("mousedown", (e) => {
  if (e.target.classList.contains("handle")) {
    drag = { mode: "crop-resize", dir: e.target.dataset.dir,
             start: stagePoint(e, cropCanvas), orig: { ...cropState.rect } };
  } else {
    drag = { mode: "crop-move", start: stagePoint(e, cropCanvas), orig: { ...cropState.rect } };
  }
  e.stopPropagation();
});

function handleCropDrag(e) {
  const p = stagePoint(e, cropCanvas);
  const pw = cropState.renderedW, ph = cropState.renderedH;
  if (drag.mode === "crop-draw") {
    const fx = Math.min(drag.startFx, p.x / pw);
    const fy = Math.min(drag.startFy, p.y / ph);
    const fw = Math.abs(p.x / pw - drag.startFx);
    const fh = Math.abs(p.y / ph - drag.startFy);
    cropState.rect = clamp({ x: fx, y: fy, w: fw, h: fh });
  } else if (drag.mode === "crop-move") {
    const dx = (p.x - drag.start.x) / pw, dy = (p.y - drag.start.y) / ph;
    const r = drag.orig;
    cropState.rect = clamp({ x: r.x + dx, y: r.y + dy, w: r.w, h: r.h });
  } else if (drag.mode === "crop-resize") {
    const dx = (p.x - drag.start.x) / pw, dy = (p.y - drag.start.y) / ph;
    let { x, y, w, h } = drag.orig;
    if (drag.dir.includes("e")) w += dx;
    if (drag.dir.includes("s")) h += dy;
    if (drag.dir.includes("w")) { x += dx; w -= dx; }
    if (drag.dir.includes("n")) { y += dy; h -= dy; }
    if (w < 0.02) w = 0.02;
    if (h < 0.02) h = 0.02;
    cropState.rect = clamp({ x, y, w, h });
  }
  drawCropBox();
}

async function applyCrop() {
  const r = cropState.rect; if (!r) return closeCrop();
  // Crop in source-image pixel space for full quality.
  const sx = r.x * cropState.srcW;
  const sy = r.y * cropState.srcH;
  const sw = r.w * cropState.srcW;
  const sh = r.h * cropState.srcH;
  const off = document.createElement("canvas");
  off.width = Math.round(sw); off.height = Math.round(sh);
  const img = new Image();
  await new Promise((res) => {
    img.onload = res;
    img.src = URL.createObjectURL(new Blob([state.logoBytes], { type: state.logoMime }));
  });
  off.getContext("2d").drawImage(img, sx, sy, sw, sh, 0, 0, off.width, off.height);
  const blob = await new Promise((res) => off.toBlob(res, "image/png"));
  state.logoBytes = await blob.arrayBuffer();
  state.logoMime = "image/png";
  // Keep current global rect's x/y but recompute height to match new logo aspect.
  await setLogoFromBytes(state.logoBytes, state.logoMime);
  if (state.globalRect) {
    state.globalRect.h = wToHFraction(state.globalRect.w);
    state.globalRect = clamp(state.globalRect);
    // Recompute per-page overrides too.
    for (const [k, ov] of state.overrides) {
      ov.h = wToHFraction(ov.w);
      state.overrides.set(k, clamp(ov));
    }
    drawBox();
  }
  closeCrop();
}

// ── Download ─────────────────────────────────────────────────────────────────
function updateDownloadButton() {
  const ready = state.pdfBytes && state.logoBytes && state.globalRect
    && state.globalRect.w > 0 && state.globalRect.h > 0;
  downloadBtn.disabled = !ready;
  statusEl.textContent = ready ? "" : "upload a PDF, a logo, and draw a logo box";
}

downloadBtn.addEventListener("click", async () => {
  if (downloadBtn.disabled) return;
  statusEl.textContent = "stamping…";
  downloadBtn.disabled = true;
  try {
    const pdfDoc = await PDFDocument.load(state.pdfBytes);
    const embed = state.logoMime === "image/png"
      ? await pdfDoc.embedPng(state.logoBytes)
      : await pdfDoc.embedJpg(state.logoBytes);
    const pages = pdfDoc.getPages();
    pages.forEach((page, i) => {
      const r = state.overrides.get(i) || state.globalRect;
      const { width: pw, height: ph } = page.getSize();
      const w = r.w * pw, h = r.h * ph;
      const x = r.x * pw;
      const y = ph - (r.y * ph) - h;
      page.drawImage(embed, { x, y, width: w, height: h, opacity: 1 });
    });
    const out = await pdfDoc.save();
    const blob = new Blob([out], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    let chosen = ($("filename-input").value || "").trim();
    if (!chosen) {
      const orig = pdfInput.files[0]?.name?.replace(/\.pdf$/i, "") || "document";
      chosen = `${orig}-watermarked`;
    }
    chosen = chosen.replace(/\.pdf$/i, "").replace(/[\/\\:*?"<>|]/g, "_");
    const a = document.createElement("a");
    a.href = url; a.download = `${chosen}.pdf`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    statusEl.textContent = "done";
  } catch (err) {
    statusEl.textContent = "error: " + err.message;
    console.error(err);
  } finally {
    downloadBtn.disabled = false;
  }
});

updateDownloadButton();
