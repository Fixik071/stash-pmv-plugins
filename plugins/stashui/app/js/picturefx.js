// Picture settings of the player (gear menu → Picture): a CSS filter on the video.
// brightness / contrast / saturation / hue are CSS filter functions; gamma, warmth and sharpness go through one small SVG filter
// (feComponentTransfer / feConvolveMatrix). Kept for every video in this browser (prefs.pfx of the player).

export const PFX_ROWS = [
  ["b", "Brightness", 40, 180, "%"],
  ["c", "Contrast", 40, 180, "%"],
  ["s", "Saturation", 0, 250, "%"],
  ["h", "Hue", -180, 180, "°"],
  ["g", "Gamma", 50, 200, "%"],
  ["w", "Warmth", -50, 50, ""],
  ["x", "Sharpness", 0, 100, "%"],
];
export const PFX_DEFAULT = { b: 100, c: 100, s: 100, h: 0, g: 100, w: 0, x: 0 };
export const pfxOf = (prefs) => Object.assign({}, PFX_DEFAULT, (prefs && prefs.pfx) || {});
export const pfxFlat = (prefs) => {
  const p = pfxOf(prefs);
  return Object.keys(PFX_DEFAULT).every((k) => p[k] === PFX_DEFAULT[k]);
};
export const pfxUnit = (k) => (PFX_ROWS.find((r) => r[0] === k) || [])[4] || "";

// The SVG filters live once in the page: "kb-pfx-c" (colour only) and "kb-pfx-cs" (colour + sharpening, a bit more work for the browser)
function svg() {
  let s = document.getElementById("kb-pfx-svg");
  if (s) return s;
  const ct = `<feComponentTransfer><feFuncR type="gamma" amplitude="1" exponent="1"/><feFuncG type="gamma" amplitude="1" exponent="1"/><feFuncB type="gamma" amplitude="1" exponent="1"/></feComponentTransfer>`;
  document.body.insertAdjacentHTML(
    "beforeend",
    `<svg id="kb-pfx-svg" width="0" height="0" style="position:absolute;pointer-events:none" aria-hidden="true"><filter id="kb-pfx-c" color-interpolation-filters="sRGB">${ct}</filter><filter id="kb-pfx-cs" color-interpolation-filters="sRGB">${ct}<feConvolveMatrix order="3" kernelMatrix="0 0 0 0 1 0 0 0 0" preserveAlpha="true"/></filter></svg>`
  );
  return document.getElementById("kb-pfx-svg");
}

// The value of the CSS filter property for these settings ("none" when nothing is changed)
export function pfxFilter(prefs) {
  if (pfxFlat(prefs)) return "none";
  const p = pfxOf(prefs);
  let f = `brightness(${p.b}%) contrast(${p.c}%) saturate(${p.s}%)${p.h ? ` hue-rotate(${p.h}deg)` : ""}`;
  if (p.g !== 100 || p.w !== 0 || p.x !== 0) {
    const root = svg();
    const id = p.x ? "kb-pfx-cs" : "kb-pfx-c";
    const exp = (100 / p.g).toFixed(3);
    const amp = [1 + p.w * 0.004, 1, 1 - p.w * 0.004].map((a) => a.toFixed(3));
    root.querySelectorAll(`#${id} feComponentTransfer > *`).forEach((fn, i) => {
      fn.setAttribute("exponent", exp);
      fn.setAttribute("amplitude", amp[i]);
    });
    const cv = root.querySelector(`#${id} feConvolveMatrix`);
    if (cv) {
      const s = p.x / 100;
      cv.setAttribute("kernelMatrix", `0 ${-s} 0 ${-s} ${1 + 4 * s} ${-s} 0 ${-s} 0`);
    }
    f += ` url(#${id})`;
  }
  return f;
}

// The mini player keeps the picture too: the setting is also put on the page (the player's own stage has its own copy)
export function pfxPage(prefs) {
  const flat = pfxFlat(prefs);
  document.documentElement.classList.toggle("kb-has-pfx", !flat);
  document.documentElement.style.setProperty("--pfx-page", pfxFilter(prefs));
}
