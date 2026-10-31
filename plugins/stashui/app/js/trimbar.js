// A timeline to cut a part out of a video, the way editors do it: the whole video as a strip of pictures, the chosen part highlighted with
// a handle on each side, a playhead. Drag the handles to trim, drag the part to move it, press (or drag) in the strip to look at that
// spot in the video. Zoom for long videos. Keys on a handle: ← → one frame, Shift a second, Alt a tenth of a second, Home / End.
// Used next to the time fields of Cut clips, GIF and parts (markers), and in the Editor – the fields keep working, the bar follows them.

import { t } from "./i18n.js";
import { fmtExact } from "./frames.js";
import { loadSprites, spriteAt } from "./sprites.js";

const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
const NICE = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];
const round3 = (v) => Math.round(v * 1000) / 1000;
const MAX_ZOOM = 400;

// "1:05" / "1:05.5" / "1:02:03": the labels of the ruler
function tickText(sec, step) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  const ss = step < 1 ? s.toFixed(1).padStart(4, "0") : String(Math.round(s)).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

// Programmatic changes of an <input>'s value (other code sets them after "Here" …) don't fire an event: this tells us anyway
export function watchValue(input, fn) {
  const desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
  Object.defineProperty(input, "value", {
    configurable: true,
    get() {
      return desc.get.call(this);
    },
    set(v) {
      desc.set.call(this, v);
      fn();
    },
  });
  input.addEventListener("input", fn);
  input.addEventListener("change", fn);
}

// ---- pictures for the strip when Stash made no timeline pictures: a few frames taken from the video itself (once per video) ----
const frameCache = new Map(); // video address → { count, frames: [data URL], aspect, done, listeners }
function waitFor(el, ev, ms) {
  return new Promise((res, rej) => {
    const ok = () => (clean(), res());
    const bad = () => (clean(), rej(new Error(ev)));
    const timer = setTimeout(bad, ms);
    const clean = () => {
      clearTimeout(timer);
      el.removeEventListener(ev, ok);
      el.removeEventListener("error", bad);
    };
    el.addEventListener(ev, ok, { once: true });
    el.addEventListener("error", bad, { once: true });
  });
}
function frameStrip(src, duration) {
  let e = frameCache.get(src);
  if (e) return e;
  e = { count: 28, frames: [], aspect: 16 / 9, done: false, listeners: new Set() };
  frameCache.set(src, e);
  (async () => {
    const v = document.createElement("video");
    v.muted = true;
    v.preload = "auto";
    v.playsInline = true;
    v.src = src;
    try {
      await waitFor(v, "loadeddata", 10000);
      const w = 160;
      const h = Math.max(20, Math.round(w * ((v.videoHeight || 9) / (v.videoWidth || 16))));
      const cv = document.createElement("canvas");
      cv.width = w;
      cv.height = h;
      const ctx = cv.getContext("2d");
      e.aspect = w / h;
      for (let k = 0; k < e.count; k++) {
        v.currentTime = ((k + 0.5) / e.count) * duration;
        await waitFor(v, "seeked", 7000);
        ctx.drawImage(v, 0, 0, w, h);
        e.frames[k] = cv.toDataURL("image/jpeg", 0.6);
        e.listeners.forEach((f) => f());
      }
    } catch (err) {
      /* a video the browser can't play: no pictures, the bar still works */
    }
    e.done = true;
    v.removeAttribute("src");
    v.load();
  })();
  return e;
}

// ---------------------------------------------------------------------------------------------------------------------------------
// o: { video, duration, fps, start, end (null = no end), optionalEnd, minLen, sprite: { vtt, url } | null, src (video address for the
//      fallback pictures), height, onChange({ start, end }, final) }
export function createTrim(host, o = {}) {
  const video = o.video || null;
  let dur = Number(o.duration) || 0;
  let fps = o.fps > 1 && o.fps < 1000 ? o.fps : 30;
  const minLen = o.minLen || 0.1;
  const s = { start: Number(o.start) || 0, end: o.end == null ? null : Number(o.end) };
  let sprites = null;
  let frames = null; // the frame strip entry
  let zoom = 1;
  let drag = null;
  let dead = false;
  let raf = 0;
  let quiet = false;
  let srcKey = "";

  const root = document.createElement("div");
  root.className = "kb-tb" + (o.compact ? " is-compact" : "");
  root.innerHTML = `
    <div class="kb-tb-tools">
      <span class="kb-tb-read"><b data-r="in"></b><i>→</i><b data-r="out"></b><small data-r="len"></small></span>
      <span class="kb-tb-end" data-endbtns${o.optionalEnd ? "" : " hidden"}>
        <button type="button" class="kb-btn is-ghost" data-endadd>${t("Add an end")}</button>
        <button type="button" class="kb-btn is-ghost" data-endrm>${t("No end")}</button>
      </span>
      <span class="kb-tb-zoom" role="group" aria-label="${t("Zoom")}">
        <button type="button" class="kb-btn is-ghost" data-z="out" aria-label="${t("Zoom out")}" title="${t("Zoom out")}">−</button>
        <button type="button" class="kb-btn is-ghost" data-z="fit" title="${t("Show the whole video")}">${t("Fit")}</button>
        <button type="button" class="kb-btn is-ghost" data-z="in" aria-label="${t("Zoom in")}" title="${t("Zoom in")}">+</button>
      </span>
    </div>
    <div class="kb-tb-scroll" data-scroll>
      <div class="kb-tb-track" data-track title="${t("Drag the ends to trim, drag the part to move it, press in the pictures to look at that spot. Ctrl + wheel zooms.")}">
        <div class="kb-tb-ruler" data-ruler></div>
        <div class="kb-tb-strip" data-strip></div>
        <div class="kb-tb-shade is-l" data-shl></div>
        <div class="kb-tb-shade is-r" data-shr></div>
        <div class="kb-tb-sel" data-sel title="${t("Drag to move the whole part")}"></div>
        <button type="button" class="kb-tb-h is-in" data-h="in" role="slider" aria-label="${t("Start time")}" title="${t("Drag to trim the start")}"><i></i></button>
        <button type="button" class="kb-tb-h is-out" data-h="out" role="slider" aria-label="${t("End")}" title="${t("Drag to trim the end")}"><i></i></button>
        <div class="kb-tb-head" data-head></div>
        <div class="kb-tb-tip" data-tip hidden></div>
      </div>
    </div>`;
  host.appendChild(root);
  const $ = (q) => root.querySelector(q);
  const scroll = $("[data-scroll]");
  const track = $("[data-track]");
  const strip = $("[data-strip]");
  const ruler = $("[data-ruler]");
  const handles = { in: $('[data-h="in"]'), out: $('[data-h="out"]') };
  const sel = $("[data-sel]");
  const head = $("[data-head]");
  const tip = $("[data-tip]");
  if (o.height) root.style.setProperty("--tb-h", o.height + "px");

  const pct = (sec) => (dur ? clamp(sec / dur, 0, 1) * 100 : 0) + "%";
  const snapT = (sec) => round3(Math.round(sec * fps) / fps);
  const timeAt = (clientX) => {
    const r = track.getBoundingClientRect();
    return r.width ? clamp(((clientX - r.left) / r.width) * dur, 0, dur) : 0;
  };

  // ---- what is shown ----
  function paint() {
    const hasEnd = s.end != null;
    root.classList.toggle("has-end", hasEnd);
    root.classList.toggle("no-dur", !dur);
    $("[data-r='in']").textContent = fmtExact(s.start);
    $("[data-r='out']").textContent = hasEnd ? fmtExact(s.end) : t("(none)");
    $("[data-r='len']").textContent = hasEnd ? fmtExact(Math.max(0, s.end - s.start)) : "";
    sel.style.left = pct(s.start);
    sel.style.width = hasEnd && dur ? ((s.end - s.start) / dur) * 100 + "%" : "0";
    $("[data-shl]").style.width = pct(s.start);
    $("[data-shr]").style.left = hasEnd ? pct(s.end) : "100%";
    handles.in.style.left = pct(s.start);
    handles.out.style.left = pct(hasEnd ? s.end : dur);
    for (const k of ["in", "out"]) {
      const h = handles[k];
      const v = k === "in" ? s.start : s.end;
      h.setAttribute("aria-valuemin", "0");
      h.setAttribute("aria-valuemax", String(round3(dur)));
      if (v != null) {
        h.setAttribute("aria-valuenow", String(round3(v)));
        h.setAttribute("aria-valuetext", fmtExact(v));
      }
    }
    $("[data-endadd]").hidden = hasEnd;
    $("[data-endrm]").hidden = !hasEnd;
    paintHead();
  }
  function paintHead() {
    if (!video || !dur) {
      head.hidden = true;
      return;
    }
    head.hidden = false;
    head.style.left = pct(video.currentTime || 0);
    if (!drag && !video.paused && zoom > 1) {
      const x = ((video.currentTime || 0) / dur) * track.clientWidth;
      if (x < scroll.scrollLeft + 12 || x > scroll.scrollLeft + scroll.clientWidth - 12) scroll.scrollLeft = x - scroll.clientWidth * 0.25;
    }
  }
  function loop() {
    raf = 0;
    paintHead();
    if (!dead && video && !video.paused) raf = requestAnimationFrame(loop);
  }
  const kick = () => {
    paintHead();
    if (!raf && video && !video.paused && !dead) raf = requestAnimationFrame(loop);
  };
  if (video) for (const ev of ["timeupdate", "seeked", "seeking", "play", "playing", "pause", "loadedmetadata"]) video.addEventListener(ev, kick);

  // Zoomed in on a long video there would be thousands of ticks and pictures: only what is on screen (and one view to each side) is drawn
  let drawn = null; // the time range that is drawn
  function windowOf(margin) {
    const W = track.clientWidth;
    if (!W || !dur) return [0, dur];
    const v = scroll.clientWidth;
    return [clamp((scroll.scrollLeft - margin * v) / W, 0, 1) * dur, clamp((scroll.scrollLeft + v + margin * v) / W, 0, 1) * dur];
  }

  // the ruler: ticks with a label about every 70 px
  function paintRuler(win) {
    const W = track.clientWidth;
    ruler.textContent = "";
    if (!dur || !W) return;
    const pps = W / dur;
    const step = NICE.find((n) => n * pps >= 70) || NICE[NICE.length - 1];
    const sub = step / 2;
    const frag = document.createDocumentFragment();
    const k0 = Math.max(0, Math.floor(win[0] / sub));
    const k1 = Math.min(Math.floor(dur / sub + 1e-6), Math.ceil(win[1] / sub));
    for (let k = k0; k <= k1; k++) {
      const v = k * sub;
      const major = k % 2 === 0;
      const i = document.createElement("i");
      i.style.left = (v / dur) * 100 + "%";
      if (major) {
        i.className = "is-major";
        i.textContent = tickText(v, step);
      }
      frag.appendChild(i);
    }
    ruler.appendChild(frag);
  }

  // the strip of pictures
  let stripTimer = 0;
  function paintStrip(win) {
    const W = track.clientWidth;
    const H = strip.clientHeight;
    strip.textContent = "";
    if (!dur || !W || !H) return;
    const cue0 = sprites && sprites.cues[0];
    const aspect = cue0 ? cue0.xywh[2] / cue0.xywh[3] : frames ? frames.aspect : 16 / 9;
    const n = Math.max(1, Math.round(W / (H * aspect)));
    const tw = W / n;
    const i0 = Math.max(0, Math.floor((win[0] / dur) * n));
    const i1 = Math.min(n - 1, Math.ceil((win[1] / dur) * n));
    const frag = document.createDocumentFragment();
    for (let i = i0; i <= i1; i++) {
      const tile = document.createElement("i");
      tile.style.left = (i / n) * 100 + "%";
      tile.style.width = 100 / n + "%";
      const at = ((i + 0.5) / n) * dur;
      const cue = spriteAt(sprites, at);
      if (cue) {
        const [x, y, w] = cue.xywh;
        const k = tw / w;
        tile.style.background = `url("${sprites.url}") -${Math.round(x * k)}px -${Math.round(y * k)}px / ${Math.round(sprites.w * k)}px auto no-repeat`;
      } else if (frames && frames.frames.length) {
        const j = clamp(Math.round((at / dur) * frames.count - 0.5), 0, frames.count - 1);
        let f = frames.frames[j];
        for (let d = 1; !f && d < frames.count; d++) f = frames.frames[j - d] || frames.frames[j + d]; // the nearest picture taken so far
        if (f) tile.style.background = `url("${f}") center / cover no-repeat`;
      }
      frag.appendChild(tile);
    }
    strip.appendChild(frag);
  }
  function paintAll() {
    drawn = windowOf(1);
    paintRuler(drawn);
    paintStrip(drawn);
  }
  const repaintStrip = () => {
    clearTimeout(stripTimer);
    stripTimer = setTimeout(() => !dead && paintAll(), 60);
  };

  // where the pictures come from: Stash's timeline pictures, else frames of the video
  async function loadPictures() {
    const key = JSON.stringify([o.sprite && o.sprite.vtt, o.src, dur > 0]);
    if (key === srcKey) return;
    srcKey = key;
    sprites = null;
    frames = null;
    if (o.sprite && o.sprite.vtt && o.sprite.url) {
      const mine = key;
      const sp = await loadSprites(o.sprite.vtt, o.sprite.url);
      if (dead || mine !== srcKey) return;
      sprites = sp;
    }
    if (!sprites && o.src && dur) {
      frames = frameStrip(o.src, dur);
      frames.listeners.add(repaintStrip);
    }
    repaintStrip();
  }

  // ---- zoom ----
  let scrollRaf = 0;
  scroll.addEventListener("scroll", () => {
    if (scrollRaf || !drawn || zoom <= 1.001) return;
    scrollRaf = requestAnimationFrame(() => {
      scrollRaf = 0;
      if (dead || !drawn) return;
      const [a, b] = windowOf(0);
      if ((a < drawn[0] - 1e-6 && drawn[0] > 1e-6) || (b > drawn[1] + 1e-6 && drawn[1] < dur - 1e-6)) paintAll();
    });
  });
  const maxZoom = () => clamp(dur / 2, 1, MAX_ZOOM);
  function setZoom(z, frac, offset) {
    const view = scroll.clientWidth;
    if (frac == null) {
      const w = track.clientWidth || 1;
      frac = (scroll.scrollLeft + view / 2) / w;
      offset = view / 2;
    }
    zoom = clamp(z, 1, maxZoom());
    track.style.width = zoom * 100 + "%";
    scroll.scrollLeft = frac * track.clientWidth - (offset == null ? view / 2 : offset);
    root.classList.toggle("is-zoomed", zoom > 1.001);
    repaintStrip();
  }
  const showTime = (sec) => {
    const x = (sec / dur) * track.clientWidth;
    if (x < scroll.scrollLeft + 20 || x > scroll.scrollLeft + scroll.clientWidth - 20) scroll.scrollLeft = x - scroll.clientWidth / 2;
  };
  root.querySelectorAll("[data-z]").forEach(
    (b) =>
      (b.onclick = () => {
        const k = b.dataset.z;
        if (k === "fit") setZoom(1);
        else setZoom(k === "in" ? zoom * 1.8 : zoom / 1.8);
      }),
  );
  scroll.addEventListener(
    "wheel",
    (e) => {
      if (!dur) return;
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        const r = track.getBoundingClientRect();
        setZoom(zoom * (e.deltaY < 0 ? 1.25 : 1 / 1.25), (e.clientX - r.left) / r.width, e.clientX - scroll.getBoundingClientRect().left);
      } else if (zoom > 1.001 && Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
        e.preventDefault();
        scroll.scrollLeft += e.deltaY;
      }
    },
    { passive: false },
  );
  sel.addEventListener("dblclick", () => {
    if (s.end == null || !dur) return;
    const len = Math.max(s.end - s.start, minLen);
    setZoom(Math.min(dur / (len * 1.3), maxZoom()), (s.start + len / 2) / dur, scroll.clientWidth / 2);
  });

  // ---- changing the part ----
  const emit = (final) => {
    if (quiet) return;
    o.onChange && o.onChange({ start: s.start, end: s.end }, !!final);
  };
  function look(sec, exact) {
    if (!video) return;
    if (!video.paused) video.pause();
    try {
      if (!exact && video.fastSeek) video.fastSeek(sec);
      else video.currentTime = sec;
    } catch (e) {
      video.currentTime = sec;
    }
  }
  function showTip(sec, leftPct) {
    tip.hidden = false;
    tip.textContent = fmtExact(sec);
    tip.style.left = leftPct;
  }
  function apply(clientX) {
    const raw = timeAt(clientX);
    let at = snapT(raw);
    if (drag.kind === "in") {
      s.start = clamp(at, 0, s.end != null ? Math.max(0, s.end - minLen) : dur);
      look(s.start);
      showTip(s.start, pct(s.start));
    } else if (drag.kind === "out") {
      s.end = clamp(at, Math.min(dur, s.start + minLen), dur);
      look(s.end);
      showTip(s.end, pct(s.end));
    } else if (drag.kind === "move") {
      const len = drag.e0 - drag.s0;
      const a = snapT(clamp(drag.s0 + (raw - drag.t0), 0, Math.max(0, dur - len)));
      s.start = a;
      s.end = round3(a + len);
      look(s.start);
      showTip(s.start, pct(s.start));
    } else {
      look(at);
      showTip(at, pct(at));
    }
    paint();
    emit(false);
  }
  function onDown(e) {
    if (!dur || (e.button != null && e.button !== 0)) return;
    const hEl = e.target.closest("[data-h]");
    const inSel = e.target.closest("[data-sel]");
    const kind = hEl ? hEl.dataset.h : inSel && s.end != null ? "move" : "scrub";
    if (hEl && hEl.dataset.h === "out" && s.end == null) return;
    e.preventDefault();
    if (hEl) hEl.focus({ preventScroll: true });
    drag = { kind, s0: s.start, e0: s.end, t0: timeAt(e.clientX), x: e.clientX, id: e.pointerId };
    root.classList.add("is-drag", "is-" + kind);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    apply(e.clientX);
  }
  function onMove(e) {
    if (!drag || (drag.id != null && e.pointerId != null && e.pointerId !== drag.id)) return;
    // near the edge of a zoomed bar: it scrolls along
    if (zoom > 1.001) {
      const r = scroll.getBoundingClientRect();
      if (e.clientX < r.left + 24) scroll.scrollLeft -= 14;
      else if (e.clientX > r.right - 24) scroll.scrollLeft += 14;
    }
    apply(e.clientX);
  }
  function onUp(e) {
    if (!drag) return;
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    window.removeEventListener("pointercancel", onUp);
    const kind = drag.kind;
    drag = null;
    root.classList.remove("is-drag", "is-in", "is-out", "is-move", "is-scrub");
    tip.hidden = true;
    // the exact frame (during the drag the video only jumped to the nearest key frame)
    look(kind === "out" ? s.end : kind === "scrub" ? timeAt(e && e.clientX != null ? e.clientX : 0) : s.start, true);
    if (kind !== "scrub") emit(true);
  }
  track.addEventListener("pointerdown", onDown);

  // keys on a handle
  root.addEventListener("keydown", (e) => {
    const h = e.target.closest && e.target.closest("[data-h]");
    if (!h || !dur) return;
    const which = h.dataset.h;
    let d = 0;
    const one = e.shiftKey ? 1 : e.altKey ? 0.1 : 1 / fps;
    if (e.key === "ArrowLeft" || e.key === "ArrowDown") d = -one;
    else if (e.key === "ArrowRight" || e.key === "ArrowUp") d = one;
    else if (e.key === "PageDown") d = -10;
    else if (e.key === "PageUp") d = 10;
    else if (e.key !== "Home" && e.key !== "End") return;
    e.preventDefault();
    e.stopPropagation();
    if (which === "in") {
      const max = s.end != null ? Math.max(0, s.end - minLen) : dur;
      s.start = e.key === "Home" ? 0 : e.key === "End" ? max : clamp(round3(s.start + d), 0, max);
      look(s.start, true);
    } else if (s.end != null) {
      s.end = e.key === "Home" ? Math.min(dur, s.start + minLen) : e.key === "End" ? dur : clamp(round3(s.end + d), Math.min(dur, s.start + minLen), dur);
      look(s.end, true);
    }
    paint();
    showTime(which === "in" ? s.start : s.end);
    emit(true);
  });

  // an end for a part that has none yet / none any more (markers)
  $("[data-endadd]").onclick = () => {
    if (!dur) return;
    s.end = round3(Math.min(dur, s.start + 5));
    if (s.end - s.start < minLen) s.start = Math.max(0, round3(s.end - minLen));
    paint();
    emit(true);
  };
  $("[data-endrm]").onclick = () => {
    s.end = null;
    paint();
    emit(true);
  };

  // ---- size changes ----
  const ro = typeof ResizeObserver === "function" ? new ResizeObserver(() => repaintStrip()) : null;
  ro && ro.observe(scroll);

  paint();
  loadPictures();
  repaintStrip();

  return {
    el: root,
    get: () => ({ start: s.start, end: s.end }),
    // from outside (the time fields): no onChange
    set(start, end) {
      if (drag) return;
      s.start = Number.isFinite(start) ? clamp(start, 0, dur || start) : s.start;
      s.end = end == null || !Number.isFinite(end) ? null : clamp(end, 0, dur || end);
      paint();
    },
    reveal() {
      dur && showTime(s.start);
    },
    setSource(n = {}) {
      if (n.duration != null && Number(n.duration) !== dur) {
        dur = Number(n.duration) || 0;
        zoom = Math.min(zoom, maxZoom());
      }
      if (n.fps > 1 && n.fps < 1000) fps = n.fps;
      if ("sprite" in n) o.sprite = n.sprite;
      if ("src" in n) o.src = n.src;
      paint();
      loadPictures();
      repaintStrip();
    },
    setDuration(d) {
      this.setSource({ duration: d });
    },
    destroy() {
      dead = true;
      cancelAnimationFrame(raf);
      cancelAnimationFrame(scrollRaf);
      clearTimeout(stripTimer);
      ro && ro.disconnect();
      if (frames) frames.listeners.delete(repaintStrip);
      if (video) for (const ev of ["timeupdate", "seeked", "seeking", "play", "playing", "pause", "loadedmetadata"]) video.removeEventListener(ev, kick);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
      root.remove();
    },
  };
}

// Binds a bar to two text fields (start / end) that other code keeps: typing in the fields moves the bar, dragging the bar writes the
// fields (and fires "input" on them, so what listens there – the GIF estimate – keeps up).
// o: { from, to (inputs; `to` may be empty = no end), parse(text) → seconds | NaN, format(sec) → text, ...createTrim options }
export function bindTrim(host, o) {
  const { from, to, parse, format } = o;
  let own = false;
  const read = () => {
    const a = parse(from.value);
    const raw = to.value.trim();
    const b = raw ? parse(raw) : null;
    return [Number.isFinite(a) ? a : 0, b == null ? null : Number.isFinite(b) ? b : null];
  };
  const tb = createTrim(host, Object.assign({}, o, { start: read()[0], end: read()[1] }, {
    onChange(r) {
      own = true;
      from.value = format(r.start);
      to.value = r.end == null ? "" : format(r.end);
      from.dispatchEvent(new Event("input", { bubbles: true }));
      to.dispatchEvent(new Event("input", { bubbles: true }));
      own = false;
      o.onChange && o.onChange(r);
    },
  }));
  const fromFields = () => {
    if (own) return;
    const [a, b] = read();
    tb.set(a, b);
  };
  watchValue(from, fromFields);
  watchValue(to, fromFields);
  return tb;
}
