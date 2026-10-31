// Gallery picker with suggestions (several galleries). Used when editing scenes and images: put them into a gallery.
// Galleries can be many, so it asks Stash while you type instead of loading them all.
// opts: { include: [id], names: { id: name }, locked: [id] (stay in the list, no ×: e.g. the folder gallery an image is in),
//         userOnly (only galleries made by hand – images can't be put into a folder or zip gallery), create (a typed-in new name
//         makes a gallery), exclude: [id], placeholder, onChange(ids) }

import { esc, fmtNum, errorToast } from "../ui.js";
import { t } from "../i18n.js";
import { gql } from "../api.js";

const base = (p) => String(p || "").split(/[\\/]/).filter(Boolean).pop() || "";
export const galleryName = (g) => (g && (g.title || base(g.files && g.files[0] && g.files[0].path) || base(g.folder && g.folder.path))) || (g ? "#" + g.id : "");
// made by hand = no folder and no zip file behind it
export const isHandMade = (g) => !(g && (g.folder || (g.files && g.files.length)));

const Q = `query GalleryPick($f: FindFilterType, $gf: GalleryFilterType) { findGalleries(filter: $f, gallery_filter: $gf) { galleries { id title image_count folder { id path } files { path } } } }`;

async function findGalleries(q, userOnly) {
  const f = q ? { q, per_page: 40, sort: "title", direction: "ASC" } : { per_page: 40, sort: "created_at", direction: "DESC" };
  let list;
  try {
    list = (await gql(Q, { f, gf: userOnly ? { path: { value: "", modifier: "IS_NULL" } } : undefined })).findGalleries.galleries;
  } catch (e) {
    // the filter by "no path" isn't known here: ask for more and leave the folder / zip galleries out ourselves
    list = (await gql(Q, { f: Object.assign({}, f, { per_page: userOnly ? 200 : 40 }) })).findGalleries.galleries;
  }
  return userOnly ? list.filter(isHandMade) : list;
}

export async function createGallery(title) {
  const d = await gql(`mutation($i: GalleryCreateInput!) { galleryCreate(input: $i) { id title } }`, { i: { title } });
  return d.galleryCreate;
}

export function galleryPicker(host, opts = {}) {
  let inc = [...(opts.include || [])];
  const locked = new Set(opts.locked || []);
  const known = Object.assign({}, opts.names || {});
  let shown = [];
  let active = -1;
  let seq = 0;
  let timer = 0;

  host.innerHTML = `<div class="kb-chips" data-chips></div>
    <input class="kb-field" type="text" placeholder="${esc(opts.placeholder || t("Search or create a gallery"))}" autocomplete="off" spellcheck="false" aria-label="${t("Galleries")}">
    <div class="kb-sugg" hidden role="listbox"></div>`;
  const chips = host.querySelector("[data-chips]");
  const input = host.querySelector("input");
  const sugg = host.querySelector(".kb-sugg");

  const name = (id) => known[id] || "#" + id;
  function renderChips() {
    chips.innerHTML = inc
      .map((id) => `<span class="kb-chip is-on${locked.has(id) ? " is-locked" : ""}" data-id="${esc(id)}"${locked.has(id) ? ` title="${esc(t("A folder or zip gallery – images can't be moved in or out of it here"))}"` : ""}>${esc(name(id))}${locked.has(id) ? "" : `<button type="button" data-rm="${esc(id)}" aria-label="${t("Remove")}">×</button>`}</span>`)
      .join("");
    chips.hidden = !inc.length;
  }
  const emit = () => opts.onChange && opts.onChange([...inc]);

  function paint(list, q) {
    shown = list.filter((g) => !inc.includes(g.id) && !(opts.exclude || []).includes(g.id));
    const create = opts.create && q && !list.some((g) => galleryName(g).toLowerCase() === q.toLowerCase());
    sugg.innerHTML =
      shown.map((g, i) => `<button type="button" role="option" data-i="${i}" class="${i === active ? "is-active" : ""}">${esc(galleryName(g))}<small>${fmtNum(g.image_count || 0)}</small></button>`).join("") +
      (create ? `<button type="button" data-create class="${active === shown.length ? "is-active" : ""}">${esc(t("New gallery “{name}”", { name: q }))}</button>` : "") +
      (!shown.length && !create ? `<button type="button" disabled>${t("No matching gallery")}</button>` : "");
    sugg.hidden = false;
  }
  let last = { list: [], q: "" };
  function ask() {
    const q = input.value.trim();
    const mine = ++seq;
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        const list = await findGalleries(q, !!opts.userOnly);
        if (mine !== seq) return; // a newer search is on its way
        last = { list, q };
        paint(list, q);
      } catch (e) {
        if (mine === seq) sugg.hidden = true;
      }
    }, q ? 220 : 0);
  }
  function add(g) {
    if (!g) return;
    known[g.id] = galleryName(g);
    inc = [...inc, g.id];
    input.value = "";
    active = -1;
    sugg.hidden = true;
    renderChips();
    emit();
  }
  async function createFromInput() {
    const n = input.value.trim();
    if (!n) return;
    try {
      add(await createGallery(n));
    } catch (e) {
      errorToast(e, "Gallery");
    }
  }

  input.addEventListener("focus", ask);
  input.addEventListener("input", () => {
    active = -1;
    ask();
  });
  input.addEventListener("blur", () => setTimeout(() => (sugg.hidden = true), 150));
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const max = shown.length + (sugg.querySelector("[data-create]") ? 1 : 0);
      active = active < 0 ? (e.key === "ArrowDown" ? 0 : max - 1) : (active + (e.key === "ArrowDown" ? 1 : -1) + max) % Math.max(max, 1);
      paint(last.list, last.q);
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (active >= 0 && active < shown.length) add(shown[active]);
      else if (sugg.querySelector("[data-create]") && (active === shown.length || !shown.length)) createFromInput();
    } else if (e.key === "Backspace" && !input.value) {
      const idx = inc.map((id, i) => (locked.has(id) ? -1 : i)).filter((i) => i >= 0).pop();
      if (idx !== undefined) {
        inc.splice(idx, 1);
        renderChips();
        emit();
      }
    }
  });
  sugg.addEventListener("mousedown", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    e.preventDefault();
    if (b.dataset.create != null) createFromInput();
    else if (b.dataset.i != null) add(shown[Number(b.dataset.i)]);
  });
  chips.addEventListener("click", (e) => {
    const rm = e.target.closest("[data-rm]");
    if (!rm) return;
    inc = inc.filter((x) => x !== rm.dataset.rm);
    renderChips();
    emit();
  });
  renderChips();

  return {
    get include() {
      return [...inc];
    },
  };
}
