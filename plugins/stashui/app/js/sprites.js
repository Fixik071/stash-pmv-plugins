// Stash's timeline pictures of a scene: a VTT file says which part of one big "sprite" picture shows which moment.
// Read once per scene (the picture is fetched ahead too). Used by the player's hover picture and by the timelines (trimbar.js).

const spriteCache = new Map();

// → { cues: [{ start, end, xywh: [x, y, w, h] }], url, w } or null (no timeline pictures made for this scene)
export function loadSprites(vttUrl, spriteUrl) {
  const key = vttUrl + "|" + spriteUrl;
  if (!spriteCache.has(key)) spriteCache.set(key, readSprites(vttUrl, spriteUrl).then((s) => (s ? s : (spriteCache.delete(key), null))));
  return spriteCache.get(key);
}

async function readSprites(vttUrl, spriteUrl) {
  try {
    const res = await fetch(vttUrl);
    if (!res.ok) return null;
    const txt = await res.text();
    const cues = [];
    const re = /(\d+):(\d+):(\d+)\.(\d+)\s+-->\s+(\d+):(\d+):(\d+)\.(\d+)\s*\n([^\n]+)/g;
    let m;
    const secs = (h, mi, s, ms) => +h * 3600 + +mi * 60 + +s + +ms / 1000;
    while ((m = re.exec(txt))) {
      const xywh = (m[9].match(/#xywh=(\d+),(\d+),(\d+),(\d+)/) || []).slice(1).map(Number);
      if (xywh.length === 4) cues.push({ start: secs(m[1], m[2], m[3], m[4]), end: secs(m[5], m[6], m[7], m[8]), xywh });
    }
    if (cues.length) new Image().src = spriteUrl; // load the picture now, so the first use isn't empty
    return cues.length ? { cues, url: spriteUrl, w: Math.max(...cues.map((c) => c.xywh[0] + c.xywh[2])) } : null;
  } catch (e) {
    return null;
  }
}

// The cue that shows this moment (cues are in time order: a binary search)
export function spriteAt(sprites, sec) {
  const c = sprites && sprites.cues;
  if (!c || !c.length) return null;
  let lo = 0;
  let hi = c.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (c[mid].start <= sec) lo = mid;
    else hi = mid - 1;
  }
  return c[lo];
}
