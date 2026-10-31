// "GIF" in a scene's info panel: pick a part of the video (start and end from the video you're watching), the size and how smooth it
// should be, and it becomes an animated GIF next to the video – optionally added to Stash as an image with the scene's performers,
// tags and studio. ffmpeg runs in the stashui backend (mode gif_make; "clip_status" says how far it is).

import { esc, icon, toast, errorToast, openDrawer, store, fmtBytes } from "../ui.js";
import { t } from "../i18n.js";
import { gql } from "../api.js";
import { runBackend } from "../interactive.js";
import { parseTime } from "../audiox.js";
import { createCropper } from "../cropbox.js";
import { fmt } from "./clipcut.js";
import { applyClipsDir } from "../clipsdir.js";

const WIDTHS = [[320, "320 px"], [480, "480 px"], [640, "640 px"], [800, "800 px"], [1280, "1280 px"]];
const FPS = [10, 12, 15, 20, 25];
const SPEEDS = [0.5, 0.75, 1, 1.5, 2];
const QUALITY = [["small", "Small file"], ["good", "Good"], ["best", "Best colors"]];
const LENGTHS = [3, 5, 8, 12];
const SIZES = [1, 2, 5, 8, 10, 25]; // MB – what sites take (Discord 10, many boards 5 …)

export function openGifMaker(x, video) {
  const dur = (x.files[0] || {}).duration || 0;
  const o = Object.assign({ width: 480, fps: 15, speed: 1, quality: "good", loop: true, sub: true, stash: true, meta: true, targetMb: 0 }, store.get("gifOpts", {}));
  let cropper = null;
  let stopAt = null;
  let busy = false;
  const cropKey = "gifCrop." + x.id;
  const now = () => (video ? video.currentTime : 0);
  const short = dur > 0 && dur <= 60; // a GIF can be 60 seconds long at most: a video that short is taken whole
  if (!o.fromMode) o.fromMode = short ? "start" : "now"; // where the length buttons start: the beginning of the video or the current time

  const d = openDrawer({
    dock: true,
    title: t("Make a GIF"),
    body: `
      <p class="kb-hint">${t("Play or scrub the video, press “Here” at the start and the end of the part you want – or a length from the current time – and make the GIF. The video itself stays as it is.")}</p>
      <div class="kb-music-range">
        <label class="kb-form-row"><span>${t("Start time")}</span><span class="kb-music-t"><input class="kb-field" data-from value="${short ? fmt(0) : fmt(Math.max(0, Math.min(now(), Math.max(0, dur - 1))))}"><button type="button" class="kb-btn is-ghost" data-here="from">${t("Here")}</button></span></label>
        <label class="kb-form-row"><span>${t("End")}</span><span class="kb-music-t"><input class="kb-field" data-to value="${short ? fmt(dur) : fmt(Math.min(dur || 1e9, now() + 5))}"><button type="button" class="kb-btn is-ghost" data-here="to">${t("Here")}</button></span></label>
      </div>
      <div class="kb-gif-len">${short ? `<button type="button" class="kb-btn is-primary" data-whole>${t("Whole video")}</button>` : ""}<span class="kb-hint">${t("Start from:")}</span><span class="kb-seg" data-frommode><button type="button" data-fm="start">${t("Beginning")}</button><button type="button" data-fm="now">${t("Current time")}</button></span></div>
      <div class="kb-gif-len"><span class="kb-hint">${t("Length:")}</span>${LENGTHS.map((n) => `<button type="button" class="kb-btn is-ghost" data-len="${n}">${n} s</button>`).join("")}<button type="button" class="kb-btn is-ghost" data-play>${icon("play")}${t("Play this part")}</button></div>
      <div class="kb-gif-grid">
        <label class="kb-form-row"><span>${t("Width")}</span><select class="kb-field" data-width>${WIDTHS.map(([v, l]) => `<option value="${v}"${o.width === v ? " selected" : ""}>${l}</option>`).join("")}</select></label>
        <label class="kb-form-row"><span>${t("Pictures per second")}</span><select class="kb-field" data-fps>${FPS.map((v) => `<option value="${v}"${o.fps === v ? " selected" : ""}>${v}</option>`).join("")}</select></label>
        <label class="kb-form-row"><span>${t("Speed")}</span><select class="kb-field" data-speed>${SPEEDS.map((v) => `<option value="${v}"${o.speed === v ? " selected" : ""}>${v}×</option>`).join("")}</select></label>
        <label class="kb-form-row"><span>${t("Quality")}</span><select class="kb-field" data-quality>${QUALITY.map(([v, l]) => `<option value="${v}"${o.quality === v ? " selected" : ""}>${t(l)}</option>`).join("")}</select></label>
      </div>
      <div class="kb-gif-target">
        <label class="kb-form-row"><span>${t("Keep it under")}</span><span class="kb-music-t"><input class="kb-field" data-target type="number" min="0.5" max="200" step="0.5" placeholder="${esc(t("no limit"))}" value="${o.targetMb || ""}"><b>MB</b></span></label>
        <div class="kb-gif-len">${SIZES.map((n) => `<button type="button" class="kb-btn is-ghost" data-size="${n}">${n} MB</button>`).join("")}<button type="button" class="kb-btn is-ghost" data-size="0">${t("no limit")}</button></div>
        <p class="kb-hint" data-targethint></p>
      </div>
      <p class="kb-hint" data-estimate></p>
      ${
        video
          ? `<div class="kb-crop-sec">
        <label class="kb-cut-opt"><input type="checkbox" data-cropon><span><b>${t("Crop / zoom in")}</b> ${t("– drag the frame on the picture to choose the part that is kept")}</span></label>
        <div class="kb-crop-tools" data-croptools hidden>
          <div class="kb-crop-asp" data-asps>${[["0", "Free"], ["video", "Like the video"], ["1.7778", "16:9"], ["0.5625", "9:16"], ["1", "1:1"], ["0.8", "4:5"]].map(([v, l]) => `<button type="button" class="kb-btn is-ghost" data-asp="${v}">${t(l)}</button>`).join("")}</div>
          <div class="kb-crop-row"><button type="button" class="kb-btn is-ghost" data-cropreset>${t("Whole picture")}</button><span class="kb-hint" data-cropinfo></span></div>
        </div>
      </div>`
          : ""
      }
      <div class="kb-cut-opts">
        <label class="kb-form-row"><span>${t("Name")}</span><input class="kb-field" data-name type="text" placeholder="${esc(t("Name (optional)"))}"></label>
        <label class="kb-cut-opt"><input type="checkbox" data-loop${o.loop ? " checked" : ""}><span>${t("Play again and again")}</span></label>
        <label class="kb-cut-opt"><input type="checkbox" data-sub${o.sub ? " checked" : ""}><span>${t("Put it in a subfolder “Clips” next to the original")}</span></label>
        <label class="kb-cut-opt"><input type="checkbox" data-stash${o.stash ? " checked" : ""}><span>${t("Add it to Stash as an image")}</span></label>
        <label class="kb-cut-opt"><input type="checkbox" data-meta${o.meta ? " checked" : ""}><span>${t("Take over performers, tags and studio, and tag it “GIF”")}</span></label>
      </div>
      <div class="kb-job-bar" data-barwrap hidden><i data-bar style="width:0%"></i></div>
      <p class="kb-hint" data-note></p>`,
    onClose: () => {
      stopAt = null;
      if (video) {
        video.removeEventListener("timeupdate", onTime);
        video.playbackRate = 1;
      }
      cropper && cropper.destroy();
    },
    foot: `<span class="kb-spacer"></span><button class="kb-btn is-primary" data-make>${icon("film")}${t("Make the GIF")}</button>`,
  });
  const el = d.el;
  const $ = (s) => el.querySelector(s);
  el.classList.add("kb-cut", "kb-gif");
  applyClipsDir($("[data-sub]"));

  const range = () => [parseTime($("[data-from]").value), parseTime($("[data-to]").value)];
  const estimate = () => {
    const [a, b] = range();
    const len = b - a;
    const p = $("[data-estimate]");
    if (!(len > 0)) return (p.textContent = "");
    const sp = Number($("[data-speed]").value) || 1;
    const frames = Math.round((len / sp) * (Number($("[data-fps]").value) || 15));
    const big = frames > 400 || Number($("[data-width]").value) >= 800;
    p.textContent = t("{n} pictures, {s} seconds long", { n: frames, s: (len / sp).toFixed(1) }) + (len > 60 ? " – " + t("a GIF can be 60 seconds long at most") : big ? " – " + t("GIFs get big quickly: a smaller width or fewer pictures per second keeps the file small") : "");
    p.classList.toggle("is-warn", len > 60 || big);
  };
  el.querySelectorAll("[data-here]").forEach((b) => (b.onclick = () => (($(b.dataset.here === "from" ? "[data-from]" : "[data-to]").value = fmt(now())), estimate())));
  const paintMode = () => el.querySelectorAll("[data-fm]").forEach((b) => b.classList.toggle("is-on", b.dataset.fm === o.fromMode));
  el.querySelectorAll("[data-fm]").forEach(
    (b) =>
      (b.onclick = () => {
        o.fromMode = b.dataset.fm;
        paintMode();
      }),
  );
  paintMode();
  const whole = $("[data-whole]");
  if (whole)
    whole.onclick = () => {
      $("[data-from]").value = fmt(0);
      $("[data-to]").value = fmt(dur);
      estimate();
    };
  el.querySelectorAll("[data-len]").forEach(
    (b) =>
      (b.onclick = () => {
        const a = o.fromMode === "start" ? 0 : now();
        $("[data-from]").value = fmt(a);
        $("[data-to]").value = fmt(dur ? Math.min(dur, a + Number(b.dataset.len)) : a + Number(b.dataset.len));
        estimate();
      }),
  );
  ["[data-from]", "[data-to]", "[data-speed]", "[data-fps]", "[data-width]"].forEach((s) => $(s).addEventListener("input", estimate));
  const targetHint = () => {
    const mb = Number($("[data-target]").value);
    $("[data-targethint]").textContent = mb > 0 ? t("The best settings that fit into {n} MB are picked – width, pictures per second and quality above are then the most it may use.", { n: mb }) : "";
    el.classList.toggle("has-target", mb > 0);
  };
  $("[data-target]").addEventListener("input", targetHint);
  el.querySelectorAll("[data-size]").forEach(
    (b) =>
      (b.onclick = () => {
        $("[data-target]").value = Number(b.dataset.size) || "";
        targetHint();
      }),
  );
  targetHint();
  estimate();

  // the part plays over and over in the player
  const onTime = () => {
    if (stopAt != null && video.currentTime >= stopAt) video.currentTime = parseTime($("[data-from]").value);
  };
  video && video.addEventListener("timeupdate", onTime);
  $("[data-play]").onclick = () => {
    if (!video) return;
    const [a, b] = range();
    if (!(b > a)) return toast(t("Start/end don't fit – the end must be after the start"), "error");
    video.currentTime = a;
    stopAt = b;
    video.playbackRate = Number($("[data-speed]").value) || 1;
    video.play().catch(() => {});
  };
  // ---- crop ----
  const cropOn = $("[data-cropon]");
  if (cropOn) {
    const info = () => {
      const r = cropper.get();
      const w = video.videoWidth || (x.files[0] || {}).width || 0;
      const h = video.videoHeight || (x.files[0] || {}).height || 0;
      $("[data-cropinfo]").textContent = w ? t("Result: {w} × {h} pixels", { w: Math.round(r.w * w), h: Math.round(r.h * h) }) : "";
      store.set(cropKey, r);
    };
    cropOn.onchange = () => {
      if (cropOn.checked && !cropper) {
        cropper = createCropper(video, store.get(cropKey, null));
        cropper.onChange(info);
      }
      $("[data-croptools]").hidden = !cropOn.checked;
      if (cropper) {
        cropper.show(cropOn.checked);
        if (cropOn.checked) (cropper.set({}, true), info());
      }
    };
    $("[data-asps]").onclick = (e) => {
      const b = e.target.closest("[data-asp]");
      if (!b || !cropper) return;
      el.querySelectorAll("[data-asp]").forEach((q) => q.classList.toggle("is-on", q === b));
      cropper.setAspect(b.dataset.asp === "video" ? "video" : Number(b.dataset.asp));
    };
    $("[data-cropreset]").onclick = () => cropper && cropper.set({ x: 0, y: 0, w: 1, h: 1 });
  }

  // ---- make it ----
  const note = $("[data-note]");
  async function intoStashAsImage(file, name) {
    const job = (await gql(`mutation($i: ScanMetadataInput!) { metadataScan(input: $i) }`, { i: { paths: [file] } })).metadataScan;
    for (let i = 0; i < 100; i++) {
      await new Promise((r) => setTimeout(r, 1200));
      const j = await gql(`query($i: FindJobInput!) { findJob(input: $i) { status } }`, { i: { id: job } }).catch(() => ({ findJob: null }));
      if (!j.findJob || ["FINISHED", "CANCELLED", "FAILED"].includes(j.findJob.status)) break;
    }
    // the scan can still be working when its job is gone – look for the new image for up to half a minute
    let img = null;
    for (let i = 0; i < 15 && !img; i++) {
      const r = await gql(`query($f: ImageFilterType) { findImages(image_filter: $f, filter: { per_page: 10 }) { images { id visual_files { ... on ImageFile { path } ... on VideoFile { path } } } } }`, { f: { path: { value: name, modifier: "INCLUDES" } } }).catch(() => null);
      img = r && r.findImages.images.find((v) => (v.visual_files || []).some((f) => String(f.path || "").normalize("NFC").toLowerCase().endsWith(name.normalize("NFC").toLowerCase())));
      if (!img) await new Promise((r2) => setTimeout(r2, 2000));
    }
    if (!img) return null;
    if ($("[data-meta]").checked) {
      let tag = (await gql(`query { findTags(tag_filter: { name: { value: "GIF", modifier: EQUALS } }, filter: { per_page: 1 }) { tags { id } } }`)).findTags.tags[0];
      if (!tag) tag = (await gql(`mutation { tagCreate(input: { name: "GIF" }) { id } }`)).tagCreate;
      const input = { id: img.id, performer_ids: (x.performers || []).map((p) => p.id), tag_ids: [...new Set([...(x.tags || []).map((tg) => tg.id), tag.id])] };
      if (x.studio) input.studio_id = x.studio.id;
      await gql(`mutation($i: ImageUpdateInput!) { imageUpdate(input: $i) { id } }`, { i: input });
    }
    return img.id;
  }

  $("[data-make]").onclick = async () => {
    if (busy) return;
    const [a, b] = range();
    if (!(a >= 0) || !(b > a) || (dur && a >= dur)) return toast(t("Start/end don't fit – the end must be after the start"), "error");
    if (b - a > 60) return toast(t("a GIF can be 60 seconds long at most"), "error");
    Object.assign(o, {
      width: Number($("[data-width]").value),
      fps: Number($("[data-fps]").value),
      speed: Number($("[data-speed]").value),
      quality: $("[data-quality]").value,
      loop: $("[data-loop]").checked,
      sub: $("[data-sub]").checked,
      stash: $("[data-stash]").checked,
      meta: $("[data-meta]").checked,
      targetMb: Math.max(0, Number($("[data-target]").value) || 0),
    });
    store.set("gifOpts", o);
    busy = true;
    const btn = $("[data-make]");
    btn.disabled = true;
    $("[data-barwrap]").hidden = false;
    const bar = $("[data-bar]");
    bar.style.width = "0%";
    note.textContent = t("Starting …");
    try {
      const r = await runBackend({
        mode: "gif_make",
        scene_id: x.id,
        start: a,
        end: dur ? Math.min(b, dur) : b,
        width: o.width,
        fps: o.fps,
        speed: o.speed,
        quality: o.quality,
        loop: o.loop,
        crop: cropper && cropOn && cropOn.checked ? cropper.get() : undefined,
        folder: o.sub ? "Clips" : "",
        name: $("[data-name]").value.trim(),
        target_mb: o.targetMb || undefined,
      });
      let st;
      for (;;) {
        await new Promise((res) => setTimeout(res, 900));
        if (!el.isConnected) return;
        st = await runBackend({ mode: "clip_status", job: r.job });
        bar.style.width = (st.pct || 0) + "%";
        note.textContent = st.phase === "probe" ? t("Finding the best settings for {n} MB …", { n: o.targetMb }) : t("Making the GIF … {n} %", { n: st.pct || 0 });
        if (st.state === "done" || st.state === "error") break;
      }
      if (st.state === "error") throw new Error(st.error || "ffmpeg failed");
      const file = st.files[0];
      bar.style.width = "100%";
      const sizeText = fmtBytes ? fmtBytes(st.size || 0) : "";
      const used = st.chosen ? ` · ${esc(t("{w} px wide, {f} pictures per second, {q}", { w: st.chosen.width, f: st.chosen.fps, q: t(({ small: "Small file", good: "Good", best: "Best colors" })[st.chosen.quality]) }))}` : "";
      const over = st.over ? ` · ${esc(t("It stays above {n} MB even with the smallest settings – use a shorter part.", { n: o.targetMb }))}` : "";
      note.innerHTML = `${esc(t("GIF saved: {name}", { name: file.split(/[\\/]/).pop() }))}${sizeText ? ` · ${esc(sizeText)}` : ""}${used}${over}`;
      if (o.stash) {
        note.textContent += " – " + t("adding it to Stash …");
        const id = await intoStashAsImage(file, file.split(/[\\/]/).pop());
        note.innerHTML = `${esc(t("GIF saved: {name}", { name: file.split(/[\\/]/).pop() }))}${sizeText ? ` · ${esc(sizeText)}` : ""}${used}${over} – ` + (id ? `<a href="#/image/${esc(id)}">${esc(t("Open the image"))}</a>` : esc(t("Stash will show it after its next scan.")));
      }
      toast(t("GIF made"), "ok");
    } catch (e) {
      note.textContent = "";
      $("[data-barwrap]").hidden = true;
      errorToast(e, "GIF");
    } finally {
      busy = false;
      btn.disabled = false;
    }
  };
}
