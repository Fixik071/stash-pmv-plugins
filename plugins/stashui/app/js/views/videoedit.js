// "Crop / edit" in the player: shorten the video (a new start and end) and/or crop its picture, and the file is REPLACED by the result.
// While it is open, the player's own timeline at the bottom is replaced by an editing timeline (trimbar.js): drag the ends, drag the part,
// press in the pictures to look at a spot, the mouse wheel zooms in and out for coarser or finer work.
// ffmpeg runs in the stashui backend (modes video_edit / video_edit_swap / video_edit_drop) as its own process; the page unloads the
// video before the file is swapped, then has Stash rescan it and opens the scene again.

import { esc, icon, toast, errorToast, openDrawer, confirmDialog, store, fmtDuration } from "../ui.js";
import { t } from "../i18n.js";
import { gql } from "../api.js";
import { go } from "../main.js";
import { runBackend } from "../interactive.js";
import { typeInfo } from "../forms.js";
import { parseTime } from "../audiox.js";
import { createCropper } from "../cropbox.js";
import { bindTrim } from "../trimbar.js";
import { fpsOf, fmtExact } from "../frames.js";

const ENCODE_EXT = [".mp4", ".m4v", ".mov", ".mkv"]; // (the same list as the backend: containers that take H.264 + AAC)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function openVideoEdit(x, video) {
  const stage = video && video.closest(".kb-stage");
  const controls = stage && stage.querySelector(".kb-controls");
  const timeline = stage && stage.querySelector(".kb-timeline");
  if (!controls || !timeline || stage.classList.contains("is-editing")) return;
  const f = x.files[0] || {};
  const dur = f.duration || 0;
  const file = (f.path || "").split(/[\\/]/).pop();
  const ext = (file.match(/\.[^.]+$/) || [""])[0].toLowerCase();
  const canEncode = ENCODE_EXT.includes(ext);
  const opts = Object.assign({ keep: true, precise: true }, store.get("videoEditOpts", {}));
  const cropKey = "cropRect." + x.id;
  let cropper = null;
  let tb = null;
  let stopAt = null;
  let busy = false;

  const d = openDrawer({
    dock: true,
    title: t("Crop / edit the video"),
    body: `
      <p class="kb-hint">${t("Drag the ends on the timeline at the bottom of the player to choose what stays. The mouse wheel on the timeline zooms in and out, Shift + wheel moves along it. The video file is replaced by the result.")}</p>
      ${canEncode ? "" : `<p class="kb-hint">${t("This kind of file can only be shortened (“Fast”), not cropped.")}</p>`}
      <div class="kb-music-range">
        <label class="kb-form-row"><span>${t("Start time")}</span><span class="kb-music-t"><input class="kb-field" data-from value="0:00.000"><button type="button" class="kb-btn is-ghost" data-here="from">${t("Here")}</button></span></label>
        <label class="kb-form-row"><span>${t("End")}</span><span class="kb-music-t"><input class="kb-field" data-to value="${fmtExact(dur)}"><button type="button" class="kb-btn is-ghost" data-here="to">${t("Here")}</button></span></label>
      </div>
      <div class="kb-cut-add"><button type="button" class="kb-btn is-ghost" data-playpart>${icon("play")}${t("Play this part")}</button><button type="button" class="kb-btn is-ghost" data-whole>${t("Whole video")}</button></div>
      <p class="kb-hint" data-result></p>
      ${
        canEncode
          ? `<div class="kb-crop-sec">
        <label class="kb-cut-opt"><input type="checkbox" data-cropon><span><b>${t("Crop / zoom in")}</b> ${t("– drag the frame on the picture to choose the part that is kept")}</span></label>
        <div class="kb-crop-tools" data-croptools hidden>
          <div class="kb-crop-asp" data-asps>${[["0", "Free"], ["video", "Like the video"], ["1.7778", "16:9"], ["0.5625", "9:16"], ["1", "1:1"], ["0.8", "4:5"]].map(([v, l]) => `<button type="button" class="kb-chip" data-asp="${v}">${/^\d/.test(l) ? l : t(l)}</button>`).join("")}</div>
          <div class="kb-crop-row"><button type="button" class="kb-btn is-ghost" data-zoomprev>${icon("search")}${t("Preview the zoom")}</button><button type="button" class="kb-btn is-ghost" data-cropreset>${t("Whole picture")}</button><span class="kb-hint" data-cropinfo></span></div>
        </div>
      </div>`
          : ""
      }
      <div class="kb-cut-opts">
        <label class="kb-cut-opt"><input type="radio" name="kb-ve-q" value="fast" data-q${opts.precise && canEncode ? "" : " checked"}><span><b>${t("Fast")}</b> ${t("– no re-encoding, same quality; the start snaps to the nearest earlier keyframe (can be a second or two off)")}</span></label>
        ${canEncode ? `<label class="kb-cut-opt"><input type="radio" name="kb-ve-q" value="precise" data-q${opts.precise ? " checked" : ""}><span><b>${t("Exact")}</b> ${t("– re-encoded (H.264), frame-accurate, takes longer")}</span></label>` : ""}
        <label class="kb-cut-opt"><input type="checkbox" data-keep${opts.keep ? " checked" : ""}><span>${t("Keep the original next to it as “{name}.orig” (Stash doesn't list it – delete it yourself when you're happy)", { name: esc(file) })}</span></label>
      </div>
      ${x.interactive ? `<p class="kb-hint">${t("The funscript isn't changed – if the start is cut off, it no longer fits.")}</p>` : ""}
      <div class="kb-job-bar" data-barwrap hidden><i data-bar style="width:0%"></i></div>
      <p class="kb-hint" data-note></p>`,
    onClose: () => {
      if (busy) return;
      video.removeEventListener("timeupdate", onTime);
      stage.classList.remove("is-editing");
      cropper && cropper.destroy();
      tb && tb.destroy();
      barHost.remove();
    },
    foot: `<span class="kb-spacer"></span><button class="kb-btn is-danger" data-save>${icon("check")}${t("Replace the video")}</button>`,
  });
  const el = d.el;
  const $ = (s) => el.querySelector(s);
  el.classList.add("kb-cut", "kb-ve");

  // the editing timeline takes the place of the player's own one
  const barHost = document.createElement("div");
  barHost.className = "kb-ve-bar";
  controls.insertBefore(barHost, timeline);
  stage.classList.add("is-editing");
  tb = bindTrim(barHost, {
    video,
    duration: dur,
    fps: fpsOf(x),
    from: $("[data-from]"),
    to: $("[data-to]"),
    parse: parseTime,
    format: fmtExact,
    wheelZoom: true,
    src: x.paths && x.paths.stream,
    sprite: x.paths && x.paths.vtt && x.paths.sprite ? { vtt: x.paths.vtt, url: x.paths.sprite } : null,
    height: 46,
  });

  const range = () => {
    const a = parseTime($("[data-from]").value);
    const b = parseTime($("[data-to]").value);
    return [a, dur ? Math.min(b, dur) : b];
  };
  const changed = () => {
    const [a, b] = range();
    return (a > 0.04 || (dur && b < dur - 0.04) || (cropper && $("[data-cropon]").checked && !isWhole(cropper.get()))) && b > a + 0.2;
  };
  const isWhole = (r) => r.w > 0.995 && r.h > 0.995;
  function paintResult() {
    const [a, b] = range();
    const ok = a >= 0 && b > a;
    let text = ok ? t("The new video will be {d} long (now {o}).", { d: fmtDuration(b - a), o: fmtDuration(dur) }) : t("Start/end don't fit – the end must be after the start");
    if (cropper && $("[data-cropon]").checked) {
      const r = cropper.get();
      const w = video.videoWidth || f.width || 0;
      const h = video.videoHeight || f.height || 0;
      if (w) text += " " + t("Result: {w} × {h} pixels", { w: Math.round(r.w * w), h: Math.round(r.h * h) });
    }
    $("[data-result]").textContent = text;
    $("[data-save]").disabled = busy || !ok || !changed();
  }
  $("[data-from]").addEventListener("input", paintResult);
  $("[data-to]").addEventListener("input", paintResult);
  paintResult();

  const now = () => video.currentTime || 0;
  el.querySelectorAll("[data-here]").forEach((b) => (b.onclick = () => ($(b.dataset.here === "from" ? "[data-from]" : "[data-to]").value = fmtExact(now()))));
  $("[data-whole]").onclick = () => {
    $("[data-from]").value = fmtExact(0);
    $("[data-to]").value = fmtExact(dur);
  };
  const onTime = () => {
    if (stopAt != null && video.currentTime >= stopAt) {
      video.pause();
      stopAt = null;
    }
  };
  video.addEventListener("timeupdate", onTime);
  $("[data-playpart]").onclick = () => {
    const [a, b] = range();
    if (!(b > a)) return;
    video.currentTime = a;
    stopAt = b;
    video.play().catch(() => {});
  };

  // ---- crop ----
  const cropOn = $("[data-cropon]");
  if (cropOn) {
    const info = () => {
      store.set(cropKey, cropper.get());
      paintResult();
    };
    cropOn.onchange = () => {
      if (cropOn.checked && !cropper) {
        cropper = createCropper(video, store.get(cropKey, null));
        cropper.onChange(info);
      }
      $("[data-croptools]").hidden = !cropOn.checked;
      if (cropper) {
        cropper.show(cropOn.checked);
        if (!cropOn.checked) cropper.zoom(false);
        if (cropOn.checked) (cropper.set({}, true), info());
      }
      // a cropped picture has to be re-encoded
      el.querySelectorAll("[data-q]").forEach((q) => {
        if (q.value === "fast") q.disabled = cropOn.checked;
        if (q.value === "precise" && cropOn.checked) q.checked = true;
      });
      $("[data-zoomprev]").classList.remove("is-on");
      paintResult();
    };
    $("[data-asps]").onclick = (e) => {
      const b = e.target.closest("[data-asp]");
      if (!b || !cropper) return;
      cropper.zoom(false);
      $("[data-zoomprev]").classList.remove("is-on");
      el.querySelectorAll("[data-asp]").forEach((q) => q.classList.toggle("is-on", q === b));
      cropper.setAspect(b.dataset.asp === "video" ? "video" : Number(b.dataset.asp));
    };
    $("[data-zoomprev]").onclick = (e) => {
      if (!cropper) return;
      const on = !cropper.zoomed;
      cropper.zoom(on);
      e.currentTarget.classList.toggle("is-on", on);
    };
    $("[data-cropreset]").onclick = () => {
      if (!cropper) return;
      cropper.zoom(false);
      $("[data-zoomprev]").classList.remove("is-on");
      cropper.set({ x: 0, y: 0, w: 1, h: 1 });
    };
  }

  // ---- make the new video, swap the file, have Stash look at it again ----
  async function save() {
    const [a, b] = range();
    if (!(b > a) || !changed()) return toast(t("Nothing to change yet – move the ends or crop the picture"), "error");
    const crop = cropper && cropOn.checked && !isWhole(cropper.get()) ? cropper.get() : null;
    const precise = !!crop || (!!$("[data-q][value=precise]") && $("[data-q][value=precise]").checked);
    const keep = $("[data-keep]").checked;
    store.set("videoEditOpts", { keep, precise: canEncode ? precise : opts.precise });
    const verdict = await confirmDialog({
      title: t("Replace the video?"),
      text: t("{name} will be replaced by the new version, {d} long.", { name: file, d: fmtDuration(b - a) }) + " " + (keep ? t("The original stays next to it as “{name}.orig”.", { name: file }) : t("The original is deleted – this can't be undone.")),
      ok: t("Replace the video"),
      danger: true,
    });
    if (!verdict.ok) return;
    busy = true;
    el.querySelectorAll(".kb-drawer-foot .kb-btn").forEach((q) => (q.disabled = true));
    const wrap = $("[data-barwrap]");
    const bar = $("[data-bar]");
    const note = $("[data-note]");
    wrap.hidden = false;
    bar.style.width = "3%";
    let job = null;
    let swapped = false;
    let unloaded = false;
    try {
      video.pause();
      job = (await runBackend({ mode: "video_edit", scene_id: x.id, start: a, end: b, crop, precise, keep })).job;
      let st;
      for (;;) {
        await sleep(900);
        st = await runBackend({ mode: "clip_status", job });
        bar.style.width = Math.max(3, st.pct || 0) + "%";
        note.textContent = st.state === "running" ? t("Making the new video … {p} %", { p: st.pct || 0 }) : "";
        if (st.state !== "running") break;
      }
      if (st.state !== "ready") throw new Error(st.error || "ffmpeg failed");
      // let go of the file (the browser and Stash may hold it), then swap
      note.textContent = t("Replacing the video …");
      bar.style.width = "100%";
      video.removeAttribute("src");
      video.load();
      unloaded = true;
      await sleep(1200);
      const res = await runBackend({ mode: "video_edit_swap", job });
      swapped = true;
      job = null;
      note.textContent = t("Saved – Stash is scanning the new video …");
      await rescan(res.path);
      toast(t("The video was replaced"), "ok");
    } catch (err) {
      errorToast(err, t("Crop / edit the video"));
      if (job && !swapped) runBackend({ mode: "video_edit_drop", job }).catch(() => {});
    } finally {
      busy = false;
      if (unloaded) {
        // (the player has let go of the video: the scene opens again, with the new file)
        d.close();
        go(`scene/${x.id}?e=${Date.now() % 1000000}`, true);
      } else {
        wrap.hidden = true;
        note.textContent = "";
        el.querySelectorAll(".kb-drawer-foot .kb-btn").forEach((q) => (q.disabled = false));
        paintResult();
      }
    }
  }
  $("[data-save]").onclick = save;
}

// Stash has to see that the file changed (length, size, fingerprints), and the pictures made from the old video are stale
async function rescan(path) {
  const info = ((await typeInfo("ScanMetadataInput").catch(() => null)) || {}).inputFields || [];
  const known = (k) => info.some((i) => i.name === k);
  const input = { paths: [path], rescan: true };
  for (const k of ["scanGenerateCovers", "scanGeneratePreviews", "scanGenerateSprites", "scanGeneratePhashes"]) if (known(k)) input[k] = true;
  let job;
  try {
    job = (await gql(`mutation($i: ScanMetadataInput!) { metadataScan(input: $i) }`, { i: input })).metadataScan;
  } catch (e) {
    if (!("rescan" in input)) throw e;
    delete input.rescan; // (an older Stash without the option)
    job = (await gql(`mutation($i: ScanMetadataInput!) { metadataScan(input: $i) }`, { i: input })).metadataScan;
  }
  for (let i = 0; i < 200; i++) {
    await sleep(1500);
    const j = await gql(`query($i: FindJobInput!) { findJob(input: $i) { status } }`, { i: { id: job } }).catch(() => ({ findJob: null }));
    if (!j.findJob || ["FINISHED", "CANCELLED", "FAILED"].includes(j.findJob.status)) break;
  }
}
