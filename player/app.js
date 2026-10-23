// Read-along player: plays the audiobook and highlights the passage on the PDF page.
// Input is the folder that `audiobook` writes: book.json, chapter audio files, and the source PDF.
// Load it with ?book=path/to/book.json (optional &pdf=... and &audio=one-combined-file.mp3, both relative
// to book.json),
// with ?demo=1, or with the Open button (pick book.json, the PDF and the audio files together).
"use strict";

const $ = (id) => document.getElementById(id);
const audio = $("audio");
const SPEEDS = [1, 1.25, 1.5, 1.75, 2, 0.75];
const DEMO = { book: "demo/book.json", pdf: "sample-paper.pdf", audio: "narration.mp3" };

const state = {
  book: null,
  resolve: null,      // file name in book.json -> URL
  combined: null,     // URL of one audio file for the whole book, if used
  chapter: -1,        // chapter loaded in <audio> (chapter mode only)
  segment: -1,
  follow: true,
  speed: 0,
  pageEls: [],
  seeking: false,
};

pdfjsLib.GlobalWorkerOptions.workerSrc = "vendor/pdfjs/pdf.worker.min.js";

// ---------- loading ----------

async function start() {
  const params = new URLSearchParams(location.search);
  if (params.has("demo") || window.READALONG_DEMO) return loadFromUrls(DEMO);
  if (params.has("book")) {
    return loadFromUrls({ book: params.get("book"), pdf: params.get("pdf"), audio: params.get("audio") });
  }
}

async function loadFromUrls({ book, pdf, audio: combined }) {
  try {
    const res = await fetch(book);
    if (!res.ok) throw new Error(`Cannot load ${book} (HTTP ${res.status})`);
    const data = await res.json();
    const base = new URL(book, location.href);
    const resolve = (name) => new URL(name, base).href;
    await open(data, resolve, pdf ? resolve(pdf) : resolve(basename(data.source_pdf)),
               combined ? resolve(combined) : null);
  } catch (e) { fail(e); }
}

async function loadFromFiles(fileList) {
  try {
    const files = new Map([...fileList].map((f) => [f.name, f]));
    const bookFile = [...files.values()].find((f) => f.name.endsWith(".json") && f.name !== "script.json");
    if (!bookFile) throw new Error("Select book.json together with the PDF and the audio files.");
    const data = JSON.parse(await bookFile.text());
    const pdfFile = files.get(basename(data.source_pdf)) || [...files.values()].find((f) => /\.pdf$/i.test(f.name));
    if (!pdfFile) throw new Error("No PDF selected. Select the PDF together with book.json.");
    const urls = new Map([...files].map(([name, f]) => [name, URL.createObjectURL(f)]));
    const resolve = (name) => urls.get(basename(name)) || null;
    const audioFiles = [...files.values()].filter((f) => /\.(mp3|m4a|wav|aac)$/i.test(f.name));
    const chapterFiles = data.chapters.filter((c) => urls.has(c.file));
    let combined = null;
    if (chapterFiles.length < data.chapters.length) {
      if (audioFiles.length === 1) combined = urls.get(audioFiles[0].name);
      else throw new Error(`Missing audio: select all ${data.chapters.length} chapter files (or one audio file for the whole book).`);
    }
    await open(data, resolve, urls.get(pdfFile.name), combined);
  } catch (e) { fail(e); }
}

async function open(book, resolve, pdfUrl, combined) {
  state.book = book;
  state.resolve = resolve;
  state.combined = combined;
  state.chapter = -1;
  state.segment = -1;
  $("title").textContent = book.title || "Untitled";
  document.title = book.title || "Read-along";
  $("chapters").replaceChildren(...book.chapters.map((c, i) => new Option(c.title, i)));
  $("seek").max = totalDuration();
  $("empty")?.remove();
  $("now").hidden = false;
  setupMediaSession();
  await renderPages(pdfUrl);
  const saved = Number(storage("get", posKey()) || 0);
  await seekTo(saved > 0 && saved < totalDuration() - 1 ? saved : 0, false);
  $("play").disabled = false;
}

// ---------- pages ----------

async function renderPages(pdfUrl) {
  const pdf = await pdfjsLib.getDocument({ url: pdfUrl }).promise;
  const main = $("pages");
  main.replaceChildren();
  state.pageEls = [];
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) if (e.isIntersecting) drawPage(pdf, e.target);
  }, { rootMargin: "800px 0px" });
  for (let i = 0; i < pdf.numPages; i++) {
    const [w, h] = pageSize(i) || (await pdf.getPage(i + 1).then((p) => { const v = p.getViewport({ scale: 1 }); return [v.width, v.height]; }));
    const el = document.createElement("div");
    el.className = "page";
    el.dataset.index = i;
    el.style.aspectRatio = `${w} / ${h}`;
    el.addEventListener("click", (ev) => onPageTap(i, el, ev));
    main.append(el);
    state.pageEls.push(el);
    io.observe(el);
  }
}

async function drawPage(pdf, el) {
  if (el.dataset.drawn) return;
  el.dataset.drawn = "1";
  const page = await pdf.getPage(Number(el.dataset.index) + 1);
  const base = page.getViewport({ scale: 1 });
  // Sharp on high-density screens, but keep canvases small enough for iOS memory limits.
  const scale = Math.min((el.clientWidth * (window.devicePixelRatio || 1)) / base.width, 2000 / base.width);
  const vp = page.getViewport({ scale });
  const canvas = document.createElement("canvas");
  canvas.width = Math.floor(vp.width);
  canvas.height = Math.floor(vp.height);
  el.prepend(canvas);
  await page.render({ canvasContext: canvas.getContext("2d"), viewport: vp }).promise;
}

function pageSize(i) { return state.book.page_sizes && state.book.page_sizes[i]; }

// Tap a passage on the page to jump the narration there.
function onPageTap(pageIndex, el, ev) {
  const [w, h] = pageSize(pageIndex) || [1, 1];
  const r = el.getBoundingClientRect();
  const x = ((ev.clientX - r.left) / r.width) * w;
  const y = ((ev.clientY - r.top) / r.height) * h;
  const hit = state.book.segments.find((s) => s.kind !== "aside" && s.anchors.some((a) =>
    a.page === pageIndex && x >= a.bbox[0] && x <= a.bbox[2] && y >= a.bbox[1] && y <= a.bbox[3]));
  if (hit) {
    state.follow = true;
    $("follow").hidden = true;
    seekTo(hit.start, !audio.paused);
  }
}

// ---------- audio and time ----------

function totalDuration() {
  const b = state.book;
  return b.duration || b.chapters.reduce((t, c) => Math.max(t, c.start + c.duration), 0);
}

function now() {
  if (state.combined) return audio.currentTime;
  const c = state.book.chapters[state.chapter];
  return c ? c.start + audio.currentTime : 0;
}

function chapterAt(t) {
  const ch = state.book.chapters;
  let i = 0;
  while (i + 1 < ch.length && ch[i + 1].start <= t) i++;
  return i;
}

async function seekTo(t, play) {
  t = Math.max(0, Math.min(t, totalDuration()));
  state.seeking = true;
  try {
    if (state.combined) {
      await setSource(state.combined);
      audio.currentTime = t;
    } else {
      const i = chapterAt(t);
      const c = state.book.chapters[i];
      if (i !== state.chapter) {
        state.chapter = i;
        await setSource(state.resolve(c.file));
      }
      audio.currentTime = Math.max(0, t - c.start);
    }
  } finally { state.seeking = false; }
  update(t);
  if (play) await playAudio();
}

function setSource(url) {
  if (audio.src === url) return Promise.resolve();
  audio.src = url;
  audio.playbackRate = audio.defaultPlaybackRate = SPEEDS[state.speed];
  return new Promise((resolve) => {
    if (audio.readyState >= 1) return resolve();
    const done = () => { audio.removeEventListener("loadedmetadata", done); resolve(); };
    audio.addEventListener("loadedmetadata", done);
    audio.load();
    // iOS may hold metadata until playback starts; do not block the seek on it.
    setTimeout(done, 1500);
  });
}

async function playAudio() {
  try { await audio.play(); } catch (e) { if (e.name !== "AbortError") fail(e); }
}

audio.addEventListener("ended", async () => {
  if (!state.combined && state.chapter + 1 < state.book.chapters.length) {
    await seekTo(state.book.chapters[state.chapter + 1].start, true);
  }
});
audio.addEventListener("play", () => { $("play").textContent = "Pause"; tick(); });
audio.addEventListener("pause", () => { $("play").textContent = "Play"; storage("set", posKey(), now()); });
audio.addEventListener("timeupdate", () => { if (!state.seeking) update(now()); });
audio.addEventListener("error", () => fail(new Error(`Cannot play the audio file (${audio.src.split("/").pop()}).`)));

function tick() {
  if (audio.paused) return;
  if (!state.seeking) update(now());
  requestAnimationFrame(tick);
}

// ---------- read-along view ----------

let lastSaved = 0;
function update(t) {
  $("time").textContent = `${fmt(t)} / ${fmt(totalDuration())}`;
  if (!seekDragging) $("seek").value = t;
  const ci = chapterAt(t);
  if ($("chapters").selectedIndex !== ci) $("chapters").selectedIndex = ci;
  if (Math.abs(t - lastSaved) > 5) { lastSaved = t; storage("set", posKey(), t); }

  const segs = state.book.segments;
  let i = 0;
  while (i + 1 < segs.length && segs[i + 1].start <= t) i++;
  const seg = segs[i];
  if (seg.kind === "pause") return;  // keep the last passage on screen during a pause
  const sentence = seg.sentences.findIndex((s) => t >= s.start && t < s.end + 0.2);
  showCaption(seg, sentence);
  if (i !== state.segment) {
    state.segment = i;
    highlight(seg);
  }
}

function showCaption(seg, sentence) {
  const key = `${seg.id}:${sentence}`;
  const box = $("nowText");
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  const kind = $("nowKind");
  kind.textContent = seg.kind === "aside" ? "Explanation" : seg.kind === "heading" ? "Heading" : "Reading";
  kind.className = `now-kind ${seg.kind}`;
  box.replaceChildren(...seg.sentences.map((s, j) => {
    const span = document.createElement("span");
    span.textContent = s.text + " ";
    if (j !== sentence) span.className = "dim";
    return span;
  }));
  const current = box.children[sentence];
  if (current) box.scrollTop = current.offsetTop - box.offsetTop;
}

function highlight(seg) {
  document.querySelectorAll(".hl").forEach((n) => n.remove());
  let first = null;
  for (const a of seg.anchors) {
    const el = state.pageEls[a.page];
    const size = pageSize(a.page);
    if (!el || !size) continue;
    const [w, h] = size;
    const pad = 2;
    const box = document.createElement("div");
    box.className = `hl ${seg.kind}`;
    box.style.left = `${((a.bbox[0] - pad) / w) * 100}%`;
    box.style.top = `${((a.bbox[1] - pad) / h) * 100}%`;
    box.style.width = `${((a.bbox[2] - a.bbox[0] + 2 * pad) / w) * 100}%`;
    box.style.height = `${((a.bbox[3] - a.bbox[1] + 2 * pad) / h) * 100}%`;
    el.append(box);
    first = first || box;
  }
  // Put the passage in the upper part of the screen, clear of the caption and controls.
  if (first && state.follow) {
    window.scrollTo({ top: first.getBoundingClientRect().top + window.scrollY - window.innerHeight * 0.2, behavior: "smooth" });
  }
}

// Stop following the narration when the reader scrolls by hand; offer a button to resume.
for (const ev of ["touchmove", "wheel"]) {
  window.addEventListener(ev, () => {
    if (state.book && state.follow) { state.follow = false; $("follow").hidden = false; }
  }, { passive: true });
}
$("follow").addEventListener("click", () => {
  state.follow = true;
  $("follow").hidden = true;
  const seg = state.book.segments[state.segment];
  if (seg) highlight(seg);
});

// ---------- controls ----------

let seekDragging = false;
$("play").addEventListener("click", () => (audio.paused ? playAudio() : audio.pause()));
$("back").addEventListener("click", () => seekTo(now() - 15, !audio.paused));
$("fwd").addEventListener("click", () => seekTo(now() + 15, !audio.paused));
$("seek").addEventListener("input", () => { seekDragging = true; $("time").textContent = `${fmt(+$("seek").value)} / ${fmt(totalDuration())}`; });
$("seek").addEventListener("change", () => { seekDragging = false; seekTo(+$("seek").value, !audio.paused); });
$("chapters").addEventListener("change", () => {
  state.follow = true;
  $("follow").hidden = true;
  seekTo(state.book.chapters[$("chapters").value].start, !audio.paused);
});
$("speed").addEventListener("click", () => {
  state.speed = (state.speed + 1) % SPEEDS.length;
  audio.playbackRate = audio.defaultPlaybackRate = SPEEDS[state.speed];
  $("speed").textContent = `${SPEEDS[state.speed]}×`;
});
$("open").addEventListener("click", () => $("files").click());
$("files").addEventListener("change", (e) => { if (e.target.files.length) loadFromFiles(e.target.files); });

function setupMediaSession() {
  if (!("mediaSession" in navigator)) return;
  navigator.mediaSession.metadata = new MediaMetadata({ title: state.book.title, artist: "Read-along" });
  const handlers = {
    play: () => playAudio(),
    pause: () => audio.pause(),
    seekbackward: () => seekTo(now() - 15, !audio.paused),
    seekforward: () => seekTo(now() + 15, !audio.paused),
  };
  for (const [action, fn] of Object.entries(handlers)) {
    try { navigator.mediaSession.setActionHandler(action, fn); } catch (_) { /* not supported here */ }
  }
}

// ---------- helpers ----------

function basename(path) { return String(path || "").split(/[\\/]/).pop(); }
function fmt(t) { t = Math.max(0, Math.floor(t)); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`; }
function posKey() { return `readalong:${state.book.title}:${state.book.mode}`; }
function storage(op, key, value) {
  try { return op === "get" ? localStorage.getItem(key) : localStorage.setItem(key, String(value)); } catch (_) { return null; }
}
function fail(e) {
  console.error(e);
  const box = $("error");
  box.textContent = e.message || String(e);
  box.hidden = false;
  setTimeout(() => { box.hidden = true; }, 8000);
}

start();
