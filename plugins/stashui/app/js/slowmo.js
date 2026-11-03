// Smooth slow motion in the player, no model to download: at a speed below 1× the video only shows a new picture a few
// times per second, so in between the frames are made up with WebGL.
//   "blend"  – cross-fades the last two pictures (cheap, but moving things leave a ghost)
//   "motion" – finds where everything moved to and builds the picture in between along that motion:
//              · a pyramid of smaller and smaller copies of both pictures (5 steps) – the big steps are found on the small
//                copy, each bigger copy only fixes the rest, so fast pans and big movements work, too
//              · one motion field per picture (forwards and backwards), 8×8 windows every 4 pixels, smooth and with
//                sub-pixel precision at the finest step
//              · for every pixel the better of the two fits wins; where neither fits (cuts, things that appear or
//                vanish) it falls back to the plain blend
// The video element keeps playing underneath; the canvas on top is only shown while it's slow and playing.

const VS = `#version 300 es
out vec2 uv;
void main() {
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  uv = p;
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

// brightness copy of a picture, half the size of the one it is made from (four taps = a small box filter)
const FS_LUMA = `#version 300 es
precision highp float;
uniform sampler2D src;
uniform vec2 dstSize;
in vec2 uv;
out vec4 o;
float luma(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }
void main() {
  vec2 e = 0.25 / dstSize;
  float l = luma(texture(src, uv + vec2(-e.x, -e.y)).rgb) + luma(texture(src, uv + vec2(e.x, -e.y)).rgb)
          + luma(texture(src, uv + vec2(-e.x, e.y)).rgb) + luma(texture(src, uv + vec2(e.x, e.y)).rgb);
  o = vec4(vec3(l * 0.25), 1.0);
}`;

// One fragment = one window (8×8 pixels, every 4th pixel): where does the window of picture A sit in picture B?
// It starts from the motion found one step coarser (×2) and only looks ±R pixels around it. Result: R,G = shift in
// pixels of this step, B = how well it fits (mean difference, 0 = perfect)
const FS_FLOW = `#version 300 es
precision highp float;
uniform sampler2D tA, tB, up;
uniform vec2 size;
uniform float hasUp, refine;
uniform int R;
out vec4 o;
float sad(vec2 c, vec2 v) {
  float s = 0.0;
  for (int j = 0; j < 8; j++) {
    for (int i = 0; i < 8; i++) {
      vec2 p = c + vec2(float(i) - 3.5, float(j) - 3.5);
      s += abs(texture(tA, p / size).r - texture(tB, (p + v) / size).r);
    }
  }
  return s / 64.0;
}
void main() {
  vec2 c = (floor(gl_FragCoord.xy) + 0.5) * 4.0;
  vec2 init = hasUp > 0.5 ? texture(up, c / size).xy * 2.0 : vec2(0.0);
  vec2 base = floor(init + 0.5);
  float best = 1e9;
  float bestSad = 1e9;
  vec2 bv = vec2(0.0);
  for (int dy = -R; dy <= R; dy++) {
    for (int dx = -R; dx <= R; dx++) {
      vec2 v = base + vec2(float(dx), float(dy));
      float s = sad(c, v);
      float cost = s + 0.0035 * length(v - init); // the motion of the neighbours is likelier than a wild jump
      if (cost < best) { best = cost; bestSad = s; bv = v; }
    }
  }
  float s0 = sad(c, vec2(0.0)); // standing still wins a tie (backgrounds don't wobble)
  if (s0 <= bestSad * 1.06 + 0.002) { bestSad = s0; bv = vec2(0.0); }
  if (refine > 0.5) {
    float l = sad(c, bv + vec2(-1.0, 0.0));
    float r = sad(c, bv + vec2(1.0, 0.0));
    float u = sad(c, bv + vec2(0.0, 1.0));
    float d = sad(c, bv + vec2(0.0, -1.0));
    float dxx = l - 2.0 * bestSad + r;
    float dyy = d - 2.0 * bestSad + u;
    if (dxx > 1e-5 && bestSad <= min(l, r)) bv.x += clamp(0.5 * (l - r) / dxx, -0.5, 0.5);
    if (dyy > 1e-5 && bestSad <= min(d, u)) bv.y += clamp(0.5 * (d - u) / dyy, -0.5, 0.5);
  }
  o = vec4(bv, bestSad, 1.0);
}`;

// The picture in between: B = shift of a block of the current picture in the previous one, F = shift of a block of the previous
// picture in the current one. Both give a try at the picture in between; the one whose two halves agree better wins.
const FS_OUT = `#version 300 es
precision highp float;
uniform sampler2D prev, cur, flowB, flowF;
uniform float alpha, useMv;
uniform vec2 meSize;
in vec2 uv;
out vec4 o;
void main() {
  vec3 a = texture(prev, uv).rgb;
  vec3 b = texture(cur, uv).rgb;
  vec3 plain = mix(a, b, alpha);
  if (useMv < 0.5) { o = vec4(plain, 1.0); return; }
  vec2 B = texture(flowB, uv).xy / meSize;
  vec2 F = texture(flowF, uv).xy / meSize;
  vec3 pA = texture(prev, uv + B * alpha).rgb;
  vec3 cA = texture(cur, uv - B * (1.0 - alpha)).rgb;
  vec3 pB = texture(prev, uv - F * alpha).rgb;
  vec3 cB = texture(cur, uv + F * (1.0 - alpha)).rgb;
  float eA = length(pA - cA);
  float eB = length(pB - cB);
  float wA = 1.0 / (0.01 + eA * eA);
  float wB = 1.0 / (0.01 + eB * eB);
  vec3 warp = (wA * mix(pA, cA, alpha) + wB * mix(pB, cB, alpha)) / (wA + wB);
  float fit = 1.0 - smoothstep(0.07, 0.28, min(eA, eB));
  o = vec4(mix(plain, warp, fit), 1.0);
}`;

const LEVELS = 5; // pyramid steps (the finest one is the "motion size" ≤ 640 wide)
const ME_WIDTH = 640;
const STEP = 4; // one motion vector per 4×4 pixels of its step
export const slowmoSupported = () => typeof HTMLVideoElement !== "undefined" && "requestVideoFrameCallback" in HTMLVideoElement.prototype;

// The picture maker, without any video: push(source, time) takes the next picture (video, canvas, image …), render(alpha) draws the
// picture alpha (0…1) of the way from the one before to the last one. Also used by the player below.
export function createInterp(canvas) {
  const gl = canvas.getContext("webgl2", { alpha: false, antialias: false, preserveDrawingBuffer: true });
  if (!gl) throw new Error("no WebGL2");
  const floatOk = !!(gl.getExtension("EXT_color_buffer_float") || gl.getExtension("EXT_color_buffer_half_float"));
  const mk = (type, src) => {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  };
  const program = (fs) => {
    const p = gl.createProgram();
    gl.attachShader(p, mk(gl.VERTEX_SHADER, VS));
    gl.attachShader(p, mk(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    const u = {};
    for (let i = 0; i < gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS); i++) {
      const n = gl.getActiveUniform(p, i).name;
      u[n] = gl.getUniformLocation(p, n);
    }
    return { p, u };
  };
  const prog = { luma: program(FS_LUMA), flow: floatOk ? program(FS_FLOW) : null, out: program(FS_OUT) };
  const vao = gl.createVertexArray();
  gl.bindVertexArray(vao);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);

  const texture = (w, h, kind) => {
    const t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    if (kind === "video") return { tex: t, w: 0, h: 0 };
    if (kind === "float") gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, w, h, 0, gl.RGBA, gl.HALF_FLOAT, null);
    else gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    const fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
    const ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    return { tex: t, fbo, w, h, ok };
  };
  const bind = (u, name, unit, t) => {
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, t.tex || t);
    gl.uniform1i(u[name], unit);
  };
  const pass = (target, w, h) => {
    gl.bindFramebuffer(gl.FRAMEBUFFER, target ? target.fbo : null);
    gl.viewport(0, 0, w, h);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  };

  const frame = [texture(0, 0, "video"), texture(0, 0, "video")]; // the pictures as they are (full size)
  let cur = 0; // which of frame[] is the last picture
  let lum = null; // lum[i][level]: brightness copies of frame[i]
  let flow = null; // flow[dir][level]: dir 0 = B (blocks of the last picture, searched in the one before), dir 1 = F (the other way)
  let sizes = []; // [w, h] of every step
  let vw = 0;
  let vh = 0;
  let count = 0; // pictures since the start / the last jump
  let tPrev = 0;
  let tCur = 0;
  let motionOk = floatOk;
  let pyr = [false, false]; // is the brightness pyramid of frame[i] made?

  function alloc(w, h) {
    if (lum) [...lum.flat(), ...flow.flat()].forEach((x) => (gl.deleteTexture(x.tex), gl.deleteFramebuffer(x.fbo)));
    vw = w;
    vh = h;
    pyr = [false, false];
    const w0 = Math.max(16, Math.min(w, ME_WIDTH));
    const h0 = Math.max(16, Math.round((w0 * h) / w));
    sizes = [];
    for (let k = 0; k < LEVELS; k++) sizes.push([Math.max(8, Math.ceil(w0 / 2 ** k)), Math.max(8, Math.ceil(h0 / 2 ** k))]);
    lum = [0, 1].map(() => sizes.map(([lw, lh]) => texture(lw, lh, "byte")));
    flow = [0, 1].map(() => sizes.map(([lw, lh]) => texture(Math.ceil(lw / STEP), Math.ceil(lh / STEP), floatOk ? "float" : "byte")));
    if (floatOk && !flow.flat().every((f) => f.ok)) motionOk = false;
    const k = Math.min(1, 2560 / w);
    canvas.width = Math.max(2, Math.round(w * k));
    canvas.height = Math.max(2, Math.round(h * k));
    count = 0;
  }
  const dims = (src) => [src.videoWidth || src.naturalWidth || src.width, src.videoHeight || src.naturalHeight || src.height];

  // brightness pyramid of frame[i]
  function pyramid(i) {
    gl.useProgram(prog.luma.p);
    for (let k = 0; k < LEVELS; k++) {
      bind(prog.luma.u, "src", 0, k ? lum[i][k - 1] : frame[i]);
      gl.uniform2f(prog.luma.u.dstSize, sizes[k][0], sizes[k][1]);
      pass(lum[i][k], sizes[k][0], sizes[k][1]);
    }
  }
  // motion of both directions, coarse to fine
  function motion() {
    gl.useProgram(prog.flow.p);
    const u = prog.flow.u;
    for (let dir = 0; dir < 2; dir++) {
      const a = dir === 0 ? cur : 1 - cur; // the blocks come from picture A, they are searched in picture B
      const b = 1 - a;
      for (let k = LEVELS - 1; k >= 0; k--) {
        bind(u, "tA", 0, lum[a][k]);
        bind(u, "tB", 1, lum[b][k]);
        bind(u, "up", 2, k < LEVELS - 1 ? flow[dir][k + 1] : lum[a][k]); // (the coarsest step has nothing coarser: any other texture will do)
        gl.uniform2f(u.size, sizes[k][0], sizes[k][1]);
        gl.uniform1f(u.hasUp, k < LEVELS - 1 ? 1 : 0);
        gl.uniform1f(u.refine, k === 0 ? 1 : 0);
        gl.uniform1i(u.R, k === LEVELS - 1 ? 4 : 2);
        pass(flow[dir][k], flow[dir][k].w, flow[dir][k].h);
      }
    }
  }

  // source: the next picture, t: its time in seconds, wantMotion: find the motion now (not needed for "blend")
  function push(src, t, wantMotion) {
    const [w, h] = dims(src);
    if (!w || !h) return;
    if (w !== vw || h !== vh) alloc(w, h);
    const jump = count && (t <= tCur || t - tCur > 0.3); // a seek: the old picture doesn't belong to this one
    const other = 1 - cur;
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, frame[other].tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, src);
    cur = other;
    pyr[other] = false;
    tPrev = count && !jump ? tCur : t - 1 / 24;
    tCur = t;
    count = jump ? 1 : count + 1;
    if (count === 1) {
      // (the first picture after a start or a jump: both sides are the same)
      gl.bindTexture(gl.TEXTURE_2D, frame[1 - cur].tex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, src);
      count = 2;
      tPrev = t - 1 / 24;
    }
    if (count === 2 && pyr[1 - cur]) pyr[1 - cur] = false; // (both sides are the same picture now)
    if (wantMotion && motionOk) {
      for (const i of [cur, 1 - cur])
        if (!pyr[i]) (pyramid(i), (pyr[i] = true));
      motion();
    }
  }
  // the share of the way from the previous picture (0) to the last one (1) at time `now`
  const alphaAt = (now) => Math.min(1, Math.max(0, (now - tCur) / Math.max(0.005, tCur - tPrev)));

  function render(alpha, useMotion) {
    if (count < 2) return false;
    const u = prog.out.u;
    gl.useProgram(prog.out.p);
    bind(u, "prev", 0, frame[1 - cur]);
    bind(u, "cur", 1, frame[cur]);
    const m = useMotion && motionOk;
    if (m) {
      bind(u, "flowB", 2, flow[0][0]);
      bind(u, "flowF", 3, flow[1][0]);
      gl.uniform2f(u.meSize, sizes[0][0], sizes[0][1]);
    } else {
      bind(u, "flowB", 2, frame[cur]);
      bind(u, "flowF", 3, frame[cur]);
      gl.uniform2f(u.meSize, 1, 1);
    }
    gl.uniform1f(u.alpha, alpha);
    gl.uniform1f(u.useMv, m ? 1 : 0);
    pass(null, canvas.width, canvas.height);
    return true;
  }
  return {
    push,
    render,
    alphaAt,
    get ready() {
      return count >= 2;
    },
    get motionOk() {
      return motionOk;
    },
    reset() {
      count = 0;
    },
    times: () => [tPrev, tCur],
  };
}

// video: the <video>; mode(): "off" | "blend" | "motion"; off(): true while something else draws the picture (VR)
export function createSlowmo(video, { mode, off }) {
  const canvas = document.createElement("canvas");
  canvas.className = "kb-slowmo";
  canvas.hidden = true;
  video.after(canvas);
  let ip = null;
  let running = false;
  let raf = 0;
  let rvfc = 0;
  let dead = !slowmoSupported();

  function init() {
    if (ip || dead) return !dead;
    try {
      ip = createInterp(canvas);
      return true;
    } catch (e) {
      console.warn("slow motion", e);
      dead = true;
      ip = null;
      return false;
    }
  }
  // a new picture of the video arrived
  function onFrame(now, meta) {
    rvfc = 0;
    if (!running) return;
    try {
      ip.push(video, meta && meta.mediaTime != null ? meta.mediaTime : video.currentTime, mode() === "motion");
      draw();
    } catch (e) {
      console.warn("slow motion", e); // (e.g. a picture the page may not read)
      dead = true;
      stop();
      return;
    }
    rvfc = video.requestVideoFrameCallback(onFrame);
  }
  function draw() {
    if (!ip.ready) return;
    ip.render(ip.alphaAt(video.currentTime), mode() === "motion");
    if (canvas.hidden) canvas.hidden = false;
  }
  function loop() {
    raf = 0;
    if (!running) return;
    try {
      draw();
    } catch (e) {
      dead = true;
      return stop();
    }
    raf = requestAnimationFrame(loop);
  }
  function start() {
    if (running || !init()) return;
    running = true;
    ip.reset();
    rvfc = video.requestVideoFrameCallback(onFrame);
    raf = requestAnimationFrame(loop);
  }
  function stop() {
    running = false;
    cancelAnimationFrame(raf);
    if (rvfc && video.cancelVideoFrameCallback) video.cancelVideoFrameCallback(rvfc);
    raf = rvfc = 0;
    canvas.hidden = true;
  }
  // call after anything that changes the speed, play / pause, the mode …
  function update() {
    const want = !dead && mode() !== "off" && !off() && !video.paused && !video.ended && video.playbackRate < 1 && video.readyState >= 2;
    want ? start() : stop();
  }
  ["ratechange", "play", "playing", "pause", "ended", "loadeddata", "emptied"].forEach((ev) => video.addEventListener(ev, update));
  return {
    update,
    get working() {
      return !dead;
    },
    destroy() {
      stop();
      canvas.remove();
      ip = null;
    },
  };
}
