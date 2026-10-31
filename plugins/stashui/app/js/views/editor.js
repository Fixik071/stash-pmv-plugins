// Editor: a simple video editor. Pick pieces of any of your scenes, set where each one starts and ends (and how fast), put them in order
// and let them become ONE new video – with fades between them if you like. ffmpeg runs in the plugin's backend (mode edit_render,
// "clip_status" tells how far it is); the new file is added to Stash afterwards.

import { esc, icon, store, toast, errorToast, debounce, fmtDuration, confirmDialog } from "../ui.js";
import { t } from "../i18n.js";
import { gql, pathNameFilter } from "../api.js";
import { runBackend } from "../interactive.js";
import { parseTime } from "../audiox.js";
import { intoStash } from "./clipcut.js";
import { applyClipsDir } from "../clipsdir.js";

const ft = (sec) => {
  sec = Math.max(0, Number(sec) || 0);
  const m = Math.floor(sec / 60);
  return `${m}:${(sec - m * 60).toFixed(1).padStart(4, "0")}`;
};
const SPEEDS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4];
const SIZES = [
  ["auto", "Like the first piece"],
  ["1920x1080", "1080p, wide (1920×1080)"],
  ["1280x720", "720p, wide (1280×720)"],
  ["854x480", "480p, wide (854×480)"],
  ["1080x1920", "Tall (1080×1920)"],
  ["1080x1080", "Square (1080×1080)"],
];
const Q = `id title files { path basename duration width height } paths { screenshot stream }`;
// A scene without a title (cam recordings, clips …) is named after its file
const nameOf = (sc) => sc.title || (sc.files && sc.files[0] && (sc.files[0].basename || String(sc.files[0].path || "").split(/[\\/]/).pop())) || "#" + sc.id;

let uid = 0;
const pieceOf = (sc, start, end) => ({ uid: ++uid, scene: { id: sc.id, title: nameOf(sc), dur: (sc.files[0] || {}).duration || 0, w: (sc.files[0] || {}).width || 0, h: (sc.files[0] || {}).height || 0, shot: sc.paths.screenshot, stream: sc.paths.stream }, start, end, speed: 1 });

export async function render(main) {
  const o = Object.assign({ name: "", size: "auto", fade: 0, audio: "keep", folder: "Clips" }, store.get("editorOpts", {}));
  let items = [];
  try {
    const draft = store.get("editorDraft", []);
    items = (Array.isArray(draft) ? draft : []).map((d) => Object.assign({ uid: ++uid }, d));
  } catch (e) {
    items = [];
  }
  let sel = -1;
  let busy = false;
  let alive = true;
  let playAll = false;
  const saveDraft = () => store.set("editorDraft", items.map(({ scene, start, end, speed }) => ({ scene, start, end, speed })));
  const saveOpts = () => store.set("editorOpts", o);

  main.innerHTML = `
    <header class="kb-head">
      <div class="kb-head-title"><h1 class="kb-h1">${t("Editor")}</h1><p class="kb-sub" data-sub></p></div>
      <div class="kb-head-tools"><button class="kb-btn" data-clear>${icon("trash")}<span>${t("Start over")}</span></button></div>
    </header>
    <div class="kb-ed">
      <section class="kb-ed-add">
        <label class="kb-search">${icon("search")}<input class="kb-field" type="search" data-q placeholder="${t("Find a scene to take pieces from")}" autocomplete="off"></label>
        <div class="kb-ed-found" data-found><p class="kb-hint">${t("Search for a scene, then add it – the whole video or a piece of it.")}</p></div>
      </section>
      <section class="kb-ed-main">
        <div class="kb-ed-view"><video data-video controls playsinline preload="metadata"></video><div class="kb-ed-viewbar"><span data-now class="kb-hint"></span></div></div>
        <div class="kb-ed-list" data-list></div>
        <div class="kb-ed-out">
          <label class="kb-form-row"><span>${t("Name")}</span><input class="kb-field" data-name type="text" placeholder="${esc(t("Edit"))}" value="${esc(o.name)}"></label>
          <label class="kb-form-row"><span>${t("Size")}</span><select class="kb-field" data-size>${SIZES.map(([v, l]) => `<option value="${v}"${o.size === v ? " selected" : ""}>${t(l)}</option>`).join("")}</select></label>
          <label class="kb-form-row"><span>${t("Fade between pieces")}</span><select class="kb-field" data-fade>${[[0, "None"], [0.3, "Short"], [0.6, "Medium"], [1, "Long"]].map(([v, l]) => `<option value="${v}"${Number(o.fade) === v ? " selected" : ""}>${t(l)}</option>`).join("")}</select></label>
          <label class="kb-form-row"><span>${t("Sound")}</span><select class="kb-field" data-audio><option value="keep"${o.audio === "keep" ? " selected" : ""}>${t("Keep the sound of the pieces")}</option><option value="mute"${o.audio === "mute" ? " selected" : ""}>${t("No sound")}</option></select></label>
          <label class="kb-form-row"><span>${t("Save in")}</span><select class="kb-field" data-folder><option value="Clips"${o.folder === "Clips" ? " selected" : ""}>${t("A “Clips” folder next to the first video")}</option><option value=""${o.folder === "" ? " selected" : ""}>${t("The folder of the first video")}</option></select></label>
          <div class="kb-ed-go"><button class="kb-btn" data-playall>${icon("play")}<span>${t("Preview all")}</span></button><button class="kb-btn is-primary" data-render>${icon("film")}<span>${t("Make the video")}</span></button></div>
          <div class="kb-ed-prog" data-prog hidden><i data-bar></i><span data-progtext></span></div>
        </div>
      </section>
    </div>`;
  const $ = (s) => main.querySelector(s);
  const video = $("[data-video]");
  applyClipsDir($("[data-folder]"));

  // ---- the list of pieces ----
  const len = (it) => Math.max(0, (it.end - it.start) / it.speed);
  const total = () => items.reduce((a, it) => a + len(it), 0);
  const sub = () => {
    $("[data-sub]").textContent = items.length ? `${t("{n} pieces", { n: items.length })} · ${fmtDuration(Math.round(total()))}` : t("Nothing yet");
  };
  function paintList() {
    sub();
    saveDraft();
    $("[data-list]").innerHTML = items.length
      ? items
          .map(
            (it, i) => `<div class="kb-ed-seg${i === sel ? " is-sel" : ""}" data-i="${i}">
        <span class="kb-ed-thumb" data-pick>${it.scene.shot ? `<img alt="" loading="lazy" src="${esc(it.scene.shot)}">` : ""}<b>${i + 1}</b></span>
        <div class="kb-ed-info">
          <b title="${esc(it.scene.title)}">${esc(it.scene.title)}</b>
          <div class="kb-ed-times">
            <label>${t("From")} <input class="kb-field" data-in value="${ft(it.start)}" size="7"></label><button class="kb-btn is-ghost" data-here="in" title="${esc(t("Take the time of the preview"))}">${t("Here")}</button>
            <label>${t("to")} <input class="kb-field" data-out value="${ft(it.end)}" size="7"></label><button class="kb-btn is-ghost" data-here="out" title="${esc(t("Take the time of the preview"))}">${t("Here")}</button>
            <label>${t("Speed")} <select class="kb-field" data-speed>${SPEEDS.map((s) => `<option value="${s}"${s === it.speed ? " selected" : ""}>${s}×</option>`).join("")}</select></label>
            <small>${fmtDuration(Math.round(len(it)))}${it.scene.dur ? ` · ${t("of {len}", { len: fmtDuration(Math.round(it.scene.dur)) })}` : ""}</small>
          </div>
        </div>
        <div class="kb-ed-acts">
          <button class="kb-btn is-icon is-ghost" data-act="play" title="${esc(t("Preview this piece"))}">${icon("play")}</button>
          <button class="kb-btn is-icon is-ghost" data-act="up" title="${esc(t("Move up"))}"${i ? "" : " disabled"}>↑</button>
          <button class="kb-btn is-icon is-ghost" data-act="down" title="${esc(t("Move down"))}"${i < items.length - 1 ? "" : " disabled"}>↓</button>
          <button class="kb-btn is-icon is-ghost" data-act="dup" title="${esc(t("Copy this piece"))}">${icon("copies")}</button>
          <button class="kb-btn is-icon is-ghost" data-act="del" title="${esc(t("Remove"))}">${icon("close")}</button>
        </div></div>`,
          )
          .join("")
      : `<div class="kb-empty"><b>${t("No pieces yet")}</b><p>${t("Search for a scene on the left and add it. Then set where each piece starts and ends – the preview shows it.")}</p></div>`;
  }

  // ---- preview ----
  let watching = -1; // the piece the preview shows
  function show(i, autoplay) {
    const it = items[i];
    if (!it) return;
    watching = i;
    sel = i;
    const go = () => {
      video.currentTime = it.start;
      video.playbackRate = it.speed;
      if (autoplay) video.play().catch(() => {});
    };
    if (video.dataset.src !== it.scene.stream) {
      video.dataset.src = it.scene.stream;
      video.src = it.scene.stream;
      video.addEventListener("loadedmetadata", go, { once: true });
    } else go();
    main.querySelectorAll(".kb-ed-seg").forEach((e) => e.classList.toggle("is-sel", Number(e.dataset.i) === i));
  }
  video.addEventListener("timeupdate", () => {
    const it = items[watching];
    if (!it) return;
    $("[data-now]").textContent = `${t("Piece {n}", { n: watching + 1 })} · ${ft(video.currentTime)}`;
    if (video.currentTime >= it.end - 0.05 && !video.paused) {
      if (playAll && watching < items.length - 1) show(watching + 1, true);
      else {
        video.pause();
        playAll = false;
      }
    }
  });

  // ---- searching and adding scenes ----
  const found = $("[data-found]");
  let findRun = 0;
  async function find() {
    const my = ++findRun;
    const q = $("[data-q]").value.trim();
    found.innerHTML = `<p class="kb-hint">${t("Loading …")}</p>`;
    try {
      const d = await gql(`query EdFind($f: FindFilterType) { findScenes(filter: $f) { count scenes { ${Q} } } }`, { f: { q: q || undefined, per_page: 30, sort: q ? "title" : "created_at", direction: q ? "ASC" : "DESC" } });
      if (my !== findRun || !alive) return;
      found.innerHTML =
        d.findScenes.scenes
          .map(
            (s) => `<div class="kb-ed-hit" data-sid="${esc(s.id)}"><span class="kb-ed-thumb">${s.paths.screenshot ? `<img alt="" loading="lazy" src="${esc(s.paths.screenshot)}">` : ""}</span>
        <span class="kb-ed-hitinfo"><b title="${esc(s.title || "")}">${esc(nameOf(s))}</b><small>${s.files[0] ? fmtDuration(Math.round(s.files[0].duration)) + " · " + s.files[0].height + "p" : ""}</small></span>
        <button class="kb-btn" data-addscene>${icon("plus")}${t("Add")}</button></div>`,
          )
          .join("") || `<p class="kb-hint">${t("No scene found.")}</p>`;
      found._scenes = new Map(d.findScenes.scenes.map((s) => [s.id, s]));
    } catch (e) {
      if (my === findRun) found.innerHTML = `<p class="kb-hint kb-pe-err">${esc(e.message)}</p>`;
    }
  }
  $("[data-q]").addEventListener("input", debounce(find, 300));
  found.addEventListener("click", (e) => {
    const b = e.target.closest("[data-addscene]");
    if (!b) return;
    const sc = found._scenes && found._scenes.get(b.closest("[data-sid]").dataset.sid);
    if (!sc || !sc.files[0]) return;
    // from where the preview stands (if it shows this scene), else the whole video
    const dur = sc.files[0].duration || 0;
    const it = pieceOf(sc, 0, dur);
    items.push(it);
    paintList();
    show(items.length - 1, false);
    toast(t("Added – set the start and end below"), "ok");
  });

  // ---- editing the pieces ----
  const list = $("[data-list]");
  const idx = (e) => Number(e.target.closest("[data-i]").dataset.i);
  const clamp = (it) => {
    const dur = it.scene.dur || Infinity;
    it.start = Math.max(0, Math.min(it.start, dur - 0.2));
    it.end = Math.max(it.start + 0.2, Math.min(it.end, dur));
  };
  list.addEventListener("change", (e) => {
    const row = e.target.closest("[data-i]");
    if (!row) return;
    const it = items[Number(row.dataset.i)];
    if (e.target.matches("[data-in]")) {
      const v = parseTime(e.target.value);
      if (Number.isFinite(v)) it.start = v;
    } else if (e.target.matches("[data-out]")) {
      const v = parseTime(e.target.value);
      if (Number.isFinite(v)) it.end = v;
    } else if (e.target.matches("[data-speed]")) it.speed = Number(e.target.value) || 1;
    else return;
    clamp(it);
    paintList();
    show(Number(row.dataset.i), false);
  });
  list.addEventListener("click", (e) => {
    const row = e.target.closest("[data-i]");
    if (!row) return;
    const i = Number(row.dataset.i);
    const it = items[i];
    const h = e.target.closest("[data-here]");
    const a = e.target.closest("[data-act]");
    if (h) {
      if (watching !== i) return toast(t("Press play on this piece first – “Here” takes the time of the preview"), "warn");
      const now = video.currentTime;
      if (h.dataset.here === "in") it.start = now;
      else it.end = now;
      clamp(it);
      paintList();
    } else if (a) {
      const act = a.dataset.act;
      if (act === "play") {
        playAll = false;
        show(i, true);
      } else if (act === "del") {
        items.splice(i, 1);
        if (watching >= items.length) watching = -1;
        sel = Math.min(sel, items.length - 1);
        paintList();
      } else if (act === "dup") {
        items.splice(i + 1, 0, Object.assign({}, it, { uid: ++uid }));
        paintList();
      } else if (act === "up" && i > 0) {
        [items[i - 1], items[i]] = [items[i], items[i - 1]];
        if (watching === i) watching = i - 1;
        paintList();
      } else if (act === "down" && i < items.length - 1) {
        [items[i + 1], items[i]] = [items[i], items[i + 1]];
        if (watching === i) watching = i + 1;
        paintList();
      }
    } else if (e.target.closest("[data-pick]")) {
      playAll = false;
      show(i, false);
    }
  });
  $("[data-playall]").onclick = () => {
    if (!items.length) return;
    playAll = true;
    show(0, true);
  };
  $("[data-clear]").onclick = async () => {
    if (items.length && !(await confirmDialog({ title: t("Start over"), text: t("Remove all pieces?"), ok: t("Remove"), danger: true }))) return;
    items = [];
    watching = -1;
    paintList();
  };
  for (const [sel2, key, num] of [["[data-name]", "name"], ["[data-size]", "size"], ["[data-fade]", "fade", true], ["[data-audio]", "audio"], ["[data-folder]", "folder"]]) {
    $(sel2).addEventListener("change", (e) => {
      o[key] = num ? Number(e.target.value) : e.target.value;
      saveOpts();
    });
  }

  // ---- making the video ----
  const sizeOf = () => {
    if (o.size !== "auto") return o.size.split("x").map(Number);
    const f = items[0].scene;
    const ev = (n) => n - (n % 2);
    return [ev(f.w || 1280), ev(f.h || 720)];
  };
  $("[data-render]").onclick = async () => {
    if (busy) return;
    if (!items.length) return toast(t("Add a piece first"), "warn");
    busy = true;
    const btn = $("[data-render]");
    btn.disabled = true;
    const prog = $("[data-prog]");
    const bar = $("[data-bar]");
    const txt = $("[data-progtext]");
    prog.hidden = false;
    bar.style.width = "0%";
    txt.textContent = t("Starting …");
    try {
      const [w, h] = sizeOf();
      const r = await runBackend({
        mode: "edit_render",
        items: items.map((it) => ({ scene_id: it.scene.id, start: it.start, end: it.end, speed: it.speed })),
        name: o.name || t("Edit"),
        w,
        h,
        fps: 30,
        fade: o.fade,
        audio: o.audio,
        folder: o.folder,
      });
      let st;
      for (;;) {
        await new Promise((res) => setTimeout(res, 1000));
        if (!alive) return;
        st = await runBackend({ mode: "clip_status", job: r.job });
        bar.style.width = (st.pct || 0) + "%";
        txt.textContent = t("Making the video … {n} %", { n: st.pct || 0 });
        if (st.state === "done" || st.state === "error") break;
      }
      if (st.state === "error") throw new Error(st.error || "ffmpeg failed");
      txt.textContent = t("Adding it to Stash …");
      bar.style.width = "100%";
      await intoStash({ performers: [], tags: [] }, st.files, { meta: false });
      const name = st.files[0].split(/[\\/]/).pop();
      const s = await gql(`query($f: SceneFilterType) { findScenes(scene_filter: $f, filter: { per_page: 5 }) { scenes { id files { path } } } }`, { f: { path: pathNameFilter(name) } });
      const sc = s.findScenes.scenes.find((v) => v.files.some((fl) => fl.path.split(/[\\/]/).pop() === name));
      txt.innerHTML = sc ? `${t("Done.")} <a href="#/scene/${esc(sc.id)}">${t("Open the new video")}</a>` : esc(t("Done – Stash will show it after its next scan."));
    } catch (e) {
      txt.textContent = "";
      prog.hidden = true;
      errorToast(e, "Editor");
    } finally {
      busy = false;
      btn.disabled = false;
    }
  };

  paintList();
  find();
  if (items.length) show(0, false);
  return () => {
    alive = false;
    video.pause();
    video.removeAttribute("src");
    video.load();
  };
}
