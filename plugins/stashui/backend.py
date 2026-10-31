"""Stash UI – a small backend for what the browser can't do on its own.

Called through Stash's `runPluginOperation` (interface: raw):

* mode "funscript_list": every .funscript in the Stash library folders (to pick one in the player).
      args:   {"mode": "funscript_list", "scene_id": "12"}
      output: {"files": [{"path", "name", "dir", "size", "mtime", "paired"}], "current": "<path or null>",
               "truncated": bool}
  "paired": a video with the same name lies next to it (it already belongs to one); "current": the
  funscript the scene has now (next to its video).

* mode "funscript_save": give a scene a funscript. Stash finds funscripts by their name – next to
  the video, with the same name and the extension .funscript (video.mp4 → video.funscript) – so the
  file is written there; then the video is scanned again so Stash marks the scene as interactive.
  That's what keeps the choice: it stays with the video, also after a restart and in classic Stash.
      args:   {"mode": "funscript_save", "scene_id": "12", "source": "<a .funscript in the library>"}
          or  {"mode": "funscript_save", "scene_id": "12", "content": "<the .funscript as text>"}
      output: {"path": "...", "replaced": bool}
  The video's path comes from Stash (not from the browser); a source must lie in a library folder.
  A funscript that was there before is kept as "<name>.funscript.bak".

* mode "funscript_remove": the scene's funscript goes aside (renamed to .funscript.bak), Stash scans.
      args:   {"mode": "funscript_remove", "scene_id": "12"}
      output: {"removed": bool}

* mode "funscript_variants": the funscripts next to a scene's video that start with its name
  ("V.funscript", "V (Soft).funscript", "V - Hard.funscript" …), each read: length, speed stripes
  (for the heatmap), number of movements, a hash of the movements, problems.
      args:   {"mode": "funscript_variants", "scene_id": "12"}
      output: {"video", "duration", "variants": [{"path", "name", "label", "main", "length", "actions",
               "speed": [..], "peak", "hash", "issues": ["broken"|"unsorted"|"long"|"short"]}]}
  "long"/"short": the script is more than max(5 s, 5 %) longer, or max(10 s, 10 %) shorter than the video.

* mode "funscript_read": the text of one library funscript (the Handy gets a chosen variant this way).
      args:   {"mode": "funscript_read", "path": "<a .funscript in the library>"}   output: {"content"}

* mode "funscript_scan": all interactive scenes, checked: {"scanned", "unreachable",
  "problems": [{"id", "title", "screenshot", "variants": [{"name", "label", "issues", "length"}]}],
  "multi": [{"id", "title", "screenshot", "count"}]}

* mode "funscript_dupes": every .funscript in the library read, scripts with exactly the same movements
  (hash over at/pos – names and metadata don't matter) grouped.
      output: {"scanned", "truncated", "groups": [{"hash", "files": [{"path", "name", "dir", "size", "mtime",
               "length", "actions", "video"}]}], "aside": [{"path", "name", "dir", "restore"}]}
  "video": the video of the same name next to the script (it belongs to a scene), else null.

* mode "funscript_dupe_aside" {"paths": [...]}: duplicates go aside, x.funscript → x.funscriptdupe (nothing is
  deleted; Stash ignores the extension). Scripts that belong to a video: Stash scans that video again.
  mode "funscript_dupe_restore" {"paths": [... .funscriptdupe]}: the other way round (not over an existing file).
      output: {"done": [paths], "skipped": [{"path", "reason"}]}

* mode "funscript_overview": numbers for all interactive scenes: {"total", "scanned", "read", "with_variants",
  "with_problems", "issues": {"broken", "long", "short"}, "avg_speed" (units/s), "edges", "hist" (scripts per intensity
  range), "avg_cover", "intense", "calm" (scenes: id, title, screenshot, speed, gap, gap_at, gaps, cover),
  "gap_scenes", "longest_gaps"}. A gap is a pause in the movements of more than 20 s.

* mode "funscript_save_variant": an edited script becomes a new variant next to the video:
  "<video> (<label>).funscript" (a taken name gets " 2", " 3" …) – the original isn't touched.
      args:   {"mode": "funscript_save_variant", "scene_id": "12", "label": "Soft", "content": "<funscript text>"}
      output: {"path", "name"}

* mode "clips_dir_check": is a folder usable for all new clips / GIFs / edits (Settings → This interface)? {"path"} → {"ok", "created",
  "in_library", "why"}. With the setting "clipsDir" (plugin settings) every new clip, GIF and edit is saved there, together.

* mode "gif_make": a part of a scene as an animated GIF (width, fps, speed, quality, optional crop), rendered by ffmpeg in its own
  process; "clip_status" says how far it is.
      args:   {"mode": "gif_make", "scene_id", "start", "end", "width", "fps", "speed", "quality": "small"|"good"|"best", "loop", "crop", "folder", "name",
               "target_mb": keep it under this size – width / fps / quality are then the most it may use and the best that fits is picked}
      output: {"job"}

* mode "video_edit" / "video_edit_swap" / "video_edit_drop": crop / shorten the video itself and replace the file (the original can be kept as
  "<name>.orig"); ffmpeg runs in its own process, "clip_status" says how far it is.
      args:   {"mode": "video_edit", "scene_id", "start", "end", "crop": {x,y,w,h}, "precise", "keep"}  →  {"job"}
              {"mode": "video_edit_swap", "job"}  →  {"path", "backup"}
* mode "edit_render": the Editor – pieces of several scenes, one after the other (trimmed, faster / slower, fading), as one new
  video, rendered by ffmpeg in its own process; "clip_status" says how far it is.
      args:   {"mode": "edit_render", "items": [{"scene_id", "start", "end", "speed"}], "name", "w", "h", "fps", "fade", "audio": "keep"|"mute",
               "folder": "Clips"|""}      output: {"job"}

* mode "box_gql": one GraphQL question (queries only) to a stash-box set up in Stash, with the API key Stash has for it –
  for the Discover overview (stashDiscover by ufousox007). Modes "ssd_search" (Jackett) and "ssd_push" (qBittorrent) are its
  resource search and download hand-over, set up under Discover → Settings.
      args:   {"mode": "box_gql", "endpoint": "<stash-box>", "query": "...", "variables": {}, "timeout": 15}
      output: {"data"} | {"errors"} | {"kind": "timeout|network|auth|blocked|parse", "message"}
  "box_rest" asks the REST list of ThePornDB (api.theporndb.net, only when that box is set up in Stash) the same way – its stash-box
  list questions are broken, the new Discover version reads the lists from there.
      args:   {"mode": "box_rest", "endpoint": "<stash-box>", "path": "/scenes?...", "timeout": 15}      output: like box_gql

* mode "box_images": up to 16 cover pictures of a stash-box in one call (fetched side by side): {"endpoint", "urls": [...]} →
  {"data": {url: data address}} – "box_image" is the same for one picture.

* mode "reveal": shows a file in the file manager of the computer Stash runs on (Explorer /select, Finder -R, xdg-open
  on the folder). Only files inside a library folder.
      args:   {"mode": "reveal", "path": "<full file path>"}
      output: {"opened": true} or {"opened": false, "why": "outside" | "missing"}

* modes "phone_status" / "phone_start" / "phone_stop": "Phone upload". phoneup.py (next to this file) is a small
  receiver in the home network: the phone opens its page (QR code in Stash UI), picks photos and videos from the
  gallery and they are written into one folder inside a library folder. One receiver at a time; its port, token and
  folder are kept in <temp>/stashui-phone.json.
      phone_status: {"mode": "phone_status"}  → {"running", "roots", "folder", "urls", "port", "token", "ips"}
      phone_start:  {"mode": "phone_start", "root": "<a library folder>", "name": "Phone uploads"}
                    (the upload folder is <root>/<name>; name may be a path below root) → like phone_status
      phone_stop:   {"mode": "phone_stop"} → {"running": false}
"""

import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

MAX_SIZE = 30 * 1024 * 1024


class Stash:
    def __init__(self, conn):
        conn = {str(k).lower(): v for k, v in (conn or {}).items()}
        host = str(conn.get("host") or "localhost")
        if host in ("0.0.0.0", ""):
            host = "127.0.0.1"
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        self.url = f"{str(conn.get('scheme') or 'http').lower()}://{host}:{int(conn.get('port') or 9999)}/graphql"
        self.headers = {"Content-Type": "application/json"}
        if conn.get("apikey"):
            self.headers["ApiKey"] = str(conn["apikey"])
        cookie = conn.get("sessioncookie")
        if isinstance(cookie, dict):
            cookie = {str(k).lower(): v for k, v in cookie.items()}
            if cookie.get("value"):
                self.headers["Cookie"] = f"{cookie.get('name') or 'session'}={cookie['value']}"

    def gql(self, query, variables=None):
        req = urllib.request.Request(self.url, json.dumps({"query": query, "variables": variables or {}}).encode(), self.headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as res:
            d = json.load(res)
        if d.get("errors"):
            raise RuntimeError("Stash: " + "; ".join(e.get("message", "") for e in d["errors"]))
        return d["data"]


MAX_LIST = 20000
SKIP_DIRS = {".git", "$recycle.bin", "system volume information", "node_modules", ".trash", "@eadir"}


def libraries(stash):
    st = stash.gql("query { configuration { general { stashes { path excludeVideo } videoExtensions } } }")["configuration"]["general"]
    roots = [os.path.realpath(s["path"]) for s in (st.get("stashes") or []) if s.get("path")]
    exts = {"." + e.lower().lstrip(".") for e in (st.get("videoExtensions") or ["mp4", "m4v", "mov", "wmv", "avi", "mpg", "mpeg", "mkv", "webm", "flv"])}
    return roots, exts


def inside(path, roots):
    p = os.path.normcase(os.path.realpath(path))
    for r in roots:
        r = os.path.normcase(r)
        try:
            if os.path.commonpath([p, r]) == r:
                return True
        except ValueError:
            pass  # another drive
    return False


def scene_video(stash, sid):
    if not sid.isdigit():
        raise ValueError("no scene")
    files = stash.gql("query($id: ID!) { findScene(id: $id) { files { path } } }", {"id": sid})["findScene"]
    if not files or not files.get("files"):
        raise ValueError("the scene has no file")
    return files["files"][0]["path"]


def funscript_list(stash, args):
    roots, exts = libraries(stash)
    current = None
    sid = str(args.get("scene_id") or "")
    if sid:
        try:
            f = os.path.splitext(scene_video(stash, sid))[0] + ".funscript"
            current = f if os.path.isfile(f) else None
        except Exception:
            pass
    out = []
    truncated = False
    for root in roots:
        for d, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x.lower() not in SKIP_DIRS and not x.startswith(".")]
            low = {f.lower() for f in files}
            for f in files:
                if not f.lower().endswith(".funscript"):
                    continue
                p = os.path.join(d, f)
                stem = f[: -len(".funscript")].lower()
                try:
                    stt = os.stat(p)
                except OSError:
                    continue
                out.append({"path": p, "name": f, "dir": d, "size": stt.st_size, "mtime": int(stt.st_mtime),
                            "paired": any(stem + e in low for e in exts)})
                if len(out) >= MAX_LIST:
                    truncated = True
                    break
            if truncated:
                break
        if truncated:
            break
    return {"files": out, "current": current, "truncated": truncated}


def funscript_save(stash, args):
    sid = str(args.get("scene_id") or "")
    if not sid.isdigit():
        raise ValueError("no scene")
    source = str(args.get("source") or "")
    if source:
        roots, _ = libraries(stash)
        if not source.lower().endswith(".funscript") or not os.path.isfile(source) or not inside(source, roots):
            raise ValueError("that funscript isn't in a Stash library folder")
        with open(source, encoding="utf-8-sig", errors="replace") as f:
            args = dict(args, content=f.read())
    content = str(args.get("content") or "")
    if len(content.encode()) > MAX_SIZE:
        raise ValueError("the funscript is too big")
    try:
        fs = json.loads(content)
    except Exception:
        raise ValueError("that's not a funscript (not JSON)")
    acts = fs.get("actions") if isinstance(fs, dict) else None
    if not isinstance(acts, list) or not acts or not all(isinstance(a, dict) and "at" in a and "pos" in a for a in acts[:50]):
        raise ValueError("that's not a funscript (no actions with at/pos)")
    files = stash.gql("query($id: ID!) { findScene(id: $id) { files { path } } }", {"id": sid})["findScene"]
    if not files or not files.get("files"):
        raise ValueError("the scene has no file")
    video = files["files"][0]["path"]
    if not os.path.isfile(video):
        raise ValueError(f"the video file can't be reached from here: {video}")
    target = os.path.splitext(video)[0] + ".funscript"  # like Stash: the extension replaced
    if source and os.path.normcase(os.path.realpath(source)) == os.path.normcase(os.path.realpath(target)):
        # it's already the one next to the video – only let Stash look again
        stash.gql("mutation($i: ScanMetadataInput!) { metadataScan(input: $i) }", {"i": {"paths": [video], "rescan": True}})
        return {"path": target, "replaced": False}
    replaced = os.path.exists(target)
    if replaced:
        os.replace(target, target + ".bak")
    tmp = target + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    os.replace(tmp, target)
    # Stash notices the funscript when it scans the video again
    stash.gql("mutation($i: ScanMetadataInput!) { metadataScan(input: $i) }", {"i": {"paths": [video], "rescan": True}})
    return {"path": target, "replaced": replaced}


def funscript_remove(stash, args):
    video = scene_video(stash, str(args.get("scene_id") or ""))
    target = os.path.splitext(video)[0] + ".funscript"
    if not os.path.isfile(target):
        return {"removed": False}
    os.replace(target, target + ".bak")
    stash.gql("mutation($i: ScanMetadataInput!) { metadataScan(input: $i) }", {"i": {"paths": [video], "rescan": True}})
    return {"removed": True}


# ---------- Variants: several funscripts for one video ----------
BUCKETS = 160  # the heatmap of a script: this many stripes
GAP_MS = 20000  # a pause in the movements longer than this counts as a gap
SPEED_UNITS = 400  # units per second that count as "full intensity" in the picture (the front end scales)


def scene_file(stash, sid):
    if not sid.isdigit():
        raise ValueError("no scene")
    sc = stash.gql("query($id: ID!) { findScene(id: $id) { files { path duration } } }", {"id": sid})["findScene"]
    if not sc or not sc.get("files"):
        raise ValueError("the scene has no file")
    return sc["files"][0]["path"], float(sc["files"][0].get("duration") or 0)


def find_variants(video, exts):
    """The funscripts next to a video that start with its name: "V.funscript", "V (Soft).funscript",
    "V - Hard.funscript" … → [(path, label)], the one with the exact name first (label "")."""
    d = os.path.dirname(video)
    stem = os.path.splitext(os.path.basename(video))[0]
    low = stem.lower()
    try:
        names = os.listdir(d)
    except OSError:
        return []
    others = {os.path.splitext(n)[0].lower() for n in names if os.path.splitext(n)[1].lower() in exts} - {low}
    out = []
    for n in sorted(names, key=str.lower):
        if not n.lower().endswith(".funscript"):
            continue
        s = n[: -len(".funscript")]
        sl = s.lower()
        if not sl.startswith(low):
            continue
        rest = s[len(stem):]
        if rest and rest[0].isalnum():
            continue  # "Video2" – another name
        if sl in others or any(len(o) > len(low) and o.startswith(low) and sl.startswith(o) and (len(sl) == len(o) or not sl[len(o)].isalnum()) for o in others):
            continue  # that one belongs to another video ("Video 2.funscript" next to "Video 2.mp4")
        label = rest.strip(" -_.()[]{}") if rest else ""
        out.append((os.path.join(d, n), label))
    out.sort(key=lambda x: (x[1] != "", x[1].lower()))
    return out


def analyze(path, duration, buckets=True):
    """Read a funscript: length, speed stripes for the heatmap, a hash over the movements and problems:
    broken (not readable / no movements), unsorted, long / short (against the video's length)."""
    info = {"path": path, "name": os.path.basename(path), "issues": []}
    try:
        st = os.stat(path)
        info.update(size=st.st_size, mtime=int(st.st_mtime))
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            fs = json.load(f)
        acts = fs.get("actions") if isinstance(fs, dict) else None
        if not isinstance(acts, list):
            raise ValueError
    except Exception:
        info.update(actions=0, length=0, hash="", speed=[], issues=["broken"])
        return info
    good = []
    for a in acts:
        try:
            at, pos = float(a["at"]), float(a["pos"])
        except Exception:
            continue
        if at == at and pos == pos and at >= 0:
            good.append((at, pos))
    if len(good) < 2 or len(good) < len(acts) * 0.95:
        info["issues"].append("broken")
    if any(good[i][0] > good[i + 1][0] for i in range(len(good) - 1)):
        info["issues"].append("unsorted")
        good.sort()
    length = good[-1][0] / 1000 if good else 0
    info.update(actions=len(good), length=round(length, 1))
    # intensity (units moved per second over the whole script) and pauses (a gap between two movements; the start counts too)
    if good and length:
        travel = sum(abs(p1 - p0) for (_, p0), (_, p1) in zip(good, good[1:]))
        info["mean_speed"] = round(travel / length)
        gaps = [(good[0][0], 0)] + [(b[0] - a[0], a[0]) for a, b in zip(good, good[1:])]
        g, at = max(gaps)
        info.update(gap_max=round(g / 1000, 1), gap_at=round(at / 1000, 1), gaps=sum(1 for x, _ in gaps if x > GAP_MS))
    # the same movements → the same hash (name, metadata, rounding noise don't matter)
    h = hashlib.sha1()
    for at, pos in good:
        h.update(f"{round(at)}:{round(pos)};".encode())
    info["hash"] = h.hexdigest()[:16] if good else ""
    if duration and length and "broken" not in info["issues"]:
        if length > duration + max(5, duration * 0.05):
            info["issues"].append("long")
        elif length < duration - max(10, duration * 0.1):
            info["issues"].append("short")
    if buckets:
        span = max(good[-1][0], 1) if good else 1
        sp = [0.0] * BUCKETS
        w = span / BUCKETS  # ms per stripe
        for (a0, p0), (a1, p1) in zip(good, good[1:]):
            if a1 <= a0:
                continue
            d = abs(p1 - p0) / (a1 - a0)  # movement per ms, spread over the stripes the stroke touches
            for i in range(int(a0 / w), min(BUCKETS - 1, int(a1 / w)) + 1):
                ov = min(a1, (i + 1) * w) - max(a0, i * w)
                if ov > 0:
                    sp[i] += d * ov
        info["speed"] = [min(999, round(x / (w / 1000))) for x in sp]
        info["peak"] = max(info["speed"]) if good else 0
    return info


def funscript_variants(stash, args):
    video, duration = scene_file(stash, str(args.get("scene_id") or ""))
    _, exts = libraries(stash)
    main = os.path.splitext(video)[0] + ".funscript"
    out = []
    for p, label in find_variants(video, exts):
        a = analyze(p, duration)
        a["label"] = label
        a["main"] = os.path.normcase(p) == os.path.normcase(main)
        out.append(a)
    return {"video": video, "duration": duration, "variants": out}


def funscript_read(stash, args):
    path = str(args.get("path") or "")
    roots, _ = libraries(stash)
    if not path.lower().endswith(".funscript") or not os.path.isfile(path) or not inside(path, roots):
        raise ValueError("that funscript isn't in a Stash library folder")
    if os.path.getsize(path) > MAX_SIZE:
        raise ValueError("the funscript is too big")
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        return {"content": f.read()}


def funscript_scan(stash, args):
    """All interactive scenes: which ones have a problem (broken / too long / too short), which have several scripts."""
    d = stash.gql("query { findScenes(scene_filter: {interactive: true}, filter: {per_page: -1}) { scenes { id title paths { screenshot } files { path duration } } } }")
    _, exts = libraries(stash)
    problems, multi, n, unreachable = [], [], 0, 0
    for sc in d["findScenes"]["scenes"]:
        if not sc.get("files"):
            continue
        video, dur = sc["files"][0]["path"], float(sc["files"][0].get("duration") or 0)
        if not os.path.isdir(os.path.dirname(video)):
            unreachable += 1
            continue
        n += 1
        vs = find_variants(video, exts)
        bad = []
        for p, label in vs:
            a = analyze(p, dur, buckets=False)
            iss = [i for i in a["issues"] if i != "unsorted"]
            if iss:
                bad.append({"name": a["name"], "label": label, "issues": iss, "length": a["length"]})
        row = {"id": sc["id"], "title": sc.get("title") or os.path.basename(video), "screenshot": (sc.get("paths") or {}).get("screenshot"), "duration": dur}
        if bad:
            problems.append(dict(row, variants=bad))
        if len(vs) > 1:
            multi.append(dict(row, count=len(vs)))
    return {"scanned": n, "unreachable": unreachable, "problems": problems, "multi": multi}


# ---------- Duplicates: the same movements in more than one file ----------
ASIDE = ".funscriptdupe"  # a set-aside duplicate: "x.funscript" ↔ "x.funscriptdupe" (Stash doesn't look at it)


def paired_video(path, exts):
    """The video with the same name next to a funscript (or None)."""
    stem = os.path.splitext(path)[0]
    for e in sorted(exts):
        for cand in (stem + e, stem + e.upper()):
            if os.path.isfile(cand):
                return cand
    return None


def funscript_dupes(stash, args):
    """Funscripts in the library whose movements are exactly the same (name, metadata, formatting don't matter),
    grouped – plus the ones already set aside (.funscriptdupe)."""
    roots, exts = libraries(stash)
    groups, aside, n, truncated = {}, [], 0, False
    for root in roots:
        for d, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x.lower() not in SKIP_DIRS and not x.startswith(".")]
            for f in files:
                low = f.lower()
                p = os.path.join(d, f)
                if low.endswith(ASIDE):
                    aside.append({"path": p, "name": f, "dir": d, "restore": p[: -len("dupe")]})
                elif low.endswith(".funscript"):
                    n += 1
                    if n > MAX_LIST:
                        truncated = True
                        continue
                    a = analyze(p, 0, buckets=False)
                    if a["hash"] and "broken" not in a["issues"]:
                        v = paired_video(p, exts)
                        groups.setdefault(a["hash"], []).append({"path": p, "name": f, "dir": d, "size": a["size"], "mtime": a["mtime"],
                                                                 "length": a["length"], "actions": a["actions"], "video": os.path.basename(v) if v else None})
    out = [{"hash": h, "files": sorted(fl, key=lambda x: (x["video"] is None, x["mtime"]))} for h, fl in groups.items() if len(fl) > 1]
    out.sort(key=lambda g: (-len(g["files"]), g["files"][0]["name"].lower()))
    return {"scanned": min(n, MAX_LIST), "groups": out, "aside": sorted(aside, key=lambda x: x["path"].lower()), "truncated": truncated}


def funscript_dupe_aside(stash, args):
    """Put duplicates aside: x.funscript → x.funscriptdupe (nothing is deleted). A script that belongs to a video
    (same name next to it) makes that scene lose its funscript – Stash scans the video again then."""
    roots, exts = libraries(stash)
    done, skipped, scan = [], [], []
    for p in args.get("paths") or []:
        p = str(p)
        if not p.lower().endswith(".funscript") or not os.path.isfile(p) or not inside(p, roots):
            skipped.append({"path": p, "reason": "not a funscript in a library folder"})
        elif os.path.exists(p + "dupe"):
            skipped.append({"path": p, "reason": "already a set-aside file with that name"})
        else:
            v = paired_video(p, exts)
            os.rename(p, p + "dupe")
            done.append(p)
            if v:
                scan.append(v)
    if scan:
        stash.gql("mutation($i: ScanMetadataInput!) { metadataScan(input: $i) }", {"i": {"paths": scan, "rescan": True}})
    return {"done": done, "skipped": skipped}


def funscript_dupe_restore(stash, args):
    """Bring set-aside files back: x.funscriptdupe → x.funscript (not over an existing file)."""
    roots, exts = libraries(stash)
    done, skipped, scan = [], [], []
    for p in args.get("paths") or []:
        p = str(p)
        t = p[: -len("dupe")]
        if not p.lower().endswith(ASIDE) or not os.path.isfile(p) or not inside(p, roots):
            skipped.append({"path": p, "reason": "not a set-aside file in a library folder"})
        elif os.path.exists(t):
            skipped.append({"path": p, "reason": "a funscript with that name exists already"})
        else:
            os.rename(p, t)
            done.append(t)
            v = paired_video(t, exts)
            if v:
                scan.append(v)
    if scan:
        stash.gql("mutation($i: ScanMetadataInput!) { metadataScan(input: $i) }", {"i": {"paths": scan, "rescan": True}})
    return {"done": done, "skipped": skipped}


def funscript_save_variant(stash, args):
    """Save an edited script as a new variant next to the video: "<video> (<label>).funscript". Never overwrites –
    a taken name gets " 2", " 3" … – and the original stays as it is."""
    sid = str(args.get("scene_id") or "")
    video, _ = scene_file(stash, sid)
    if not os.path.isfile(video):
        raise ValueError(f"the video file can't be reached from here: {video}")
    content = str(args.get("content") or "")
    if len(content.encode()) > MAX_SIZE:
        raise ValueError("the funscript is too big")
    try:
        fs = json.loads(content)
    except Exception:
        raise ValueError("that's not a funscript (not JSON)")
    acts = fs.get("actions") if isinstance(fs, dict) else None
    if not isinstance(acts, list) or not acts or not all(isinstance(a, dict) and "at" in a and "pos" in a for a in acts[:50]):
        raise ValueError("that's not a funscript (no actions with at/pos)")
    label = "".join(c for c in str(args.get("label") or "") if c not in '\\/:*?"<>|' and c.isprintable()).strip(" .")[:40] or "Edited"
    base = os.path.splitext(video)[0] + f" ({label})"
    target, n = base + ".funscript", 1
    while os.path.exists(target):
        n += 1
        target = f"{base} {n}.funscript"
    tmp = target + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    os.replace(tmp, target)
    return {"path": target, "name": os.path.basename(target)}


def funscript_overview(stash, args):
    """Numbers for all interactive scenes: scripts, variants, problems, intensity (histogram, most intense / calmest),
    pauses (scenes with gaps, the longest), how much of the video the script covers."""
    d = stash.gql("query { stats { scene_count } findScenes(scene_filter: {interactive: true}, filter: {per_page: -1}) { scenes { id title paths { screenshot } files { path duration } } } }")
    _, exts = libraries(stash)
    rows, n, with_var, bad, unreachable = [], 0, 0, 0, 0
    kinds = {"broken": 0, "long": 0, "short": 0}
    for sc in d["findScenes"]["scenes"]:
        if not sc.get("files"):
            continue
        video, dur = sc["files"][0]["path"], float(sc["files"][0].get("duration") or 0)
        if not os.path.isdir(os.path.dirname(video)):
            unreachable += 1
            continue
        n += 1
        vs = find_variants(video, exts)
        if len(vs) > 1:
            with_var += 1
        main_path = os.path.splitext(video)[0] + ".funscript"
        flagged = False
        for p, label in vs:
            a = analyze(p, dur, buckets=False)
            for k in ("broken", "long", "short"):
                if k in a["issues"]:
                    kinds[k] += 1
                    flagged = True
            if os.path.normcase(p) == os.path.normcase(main_path) and a.get("mean_speed") is not None:
                rows.append({"id": sc["id"], "title": sc.get("title") or os.path.basename(video), "screenshot": (sc.get("paths") or {}).get("screenshot"),
                             "speed": a["mean_speed"], "gap": a["gap_max"], "gap_at": a["gap_at"], "gaps": a["gaps"], "cover": round(min(1.0, a["length"] / dur), 2) if dur else 1})
        bad += flagged
    edges = [0, 50, 100, 150, 200, 300, 400]  # units per second
    hist = [0] * len(edges)
    for r in rows:
        hist[max(i for i, e in enumerate(edges) if r["speed"] >= e)] += 1
    by_speed = sorted(rows, key=lambda r: r["speed"])
    return {
        "total": int(d["stats"]["scene_count"]), "scanned": n, "unreachable": unreachable, "read": len(rows), "with_variants": with_var, "with_problems": bad, "issues": kinds,
        "avg_speed": round(sum(r["speed"] for r in rows) / len(rows)) if rows else 0, "edges": edges, "hist": hist,
        "avg_cover": round(sum(r["cover"] for r in rows) / len(rows), 2) if rows else 0,
        "intense": by_speed[::-1][:6], "calm": by_speed[:6],
        "gap_scenes": sum(1 for r in rows if r["gaps"]), "longest_gaps": sorted((r for r in rows if r["gaps"]), key=lambda r: -r["gap"])[:10],
    }


# ---------- Phone upload ----------
PHONE_STATE = os.path.join(tempfile.gettempdir(), "stashui-phone.json")  # (not the plugin folder: an update would replace it)


def lan_ips():
    """This PC's addresses in the local network, the likeliest first (192.168.x, 10.x, 172.16-31.x)."""
    found = []
    try:  # the address the PC uses to reach the outside – no packet is sent
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        found.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass

    def rank(ip):
        if ip.startswith("192.168."):
            return 0
        if ip.startswith("10."):
            return 1
        if ip.startswith("172.") and 16 <= int(ip.split(".")[1]) <= 31:
            return 2
        return 3

    ips = [ip for ip in dict.fromkeys(found) if not ip.startswith("127.") and not ip.startswith("169.254.") and ip != "0.0.0.0"]
    return sorted(ips, key=rank)


def phone_load():
    try:
        with open(PHONE_STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def phone_ping(st):
    try:
        url = f"http://127.0.0.1:{st['port']}/api/ping?k={urllib.parse.quote(st['token'])}"
        with urllib.request.urlopen(url, timeout=2) as r:
            return json.load(r)
    except Exception:  # noqa: BLE001 – not running / not answering
        return None


def phone_info(st, roots, running):
    ips = lan_ips()
    return {
        "running": running,
        "roots": roots,
        "folder": (st or {}).get("folder", ""),
        "port": (st or {}).get("port"),
        "token": (st or {}).get("token", "") if running else "",
        "ips": ips,
        "urls": [f"http://{ip}:{st['port']}/?k={st['token']}" for ip in ips] if running and st else [],
    }


def phone_stop_server(st):
    if not st:
        return
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{st['port']}/api/stop?k={urllib.parse.quote(st['token'])}", timeout=3).read()
    except Exception:  # noqa: BLE001
        pass
    try:
        os.remove(PHONE_STATE)
    except OSError:
        pass


def phone_status(stash, args):
    roots, _ = libraries(stash)
    st = phone_load()
    running = bool(st and phone_ping(st))
    if st and not running:
        st = None
    return phone_info(st, roots, running)


def phone_start(stash, args):
    roots, _ = libraries(stash)
    if not roots:
        raise RuntimeError("Stash has no library folder yet")
    root = os.path.realpath(str(args.get("root") or roots[0]))
    if not inside(root, roots):
        raise ValueError("the upload folder has to be inside a library folder of Stash")
    name = str(args.get("name") or "Phone uploads").replace("\\", "/").strip("/ ")
    if not name or any(part in ("..", ".") for part in name.split("/")):
        raise ValueError("bad folder name")
    folder = os.path.realpath(os.path.join(root, *name.split("/")))
    if not inside(folder, roots):
        raise ValueError("the upload folder has to be inside a library folder of Stash")
    os.makedirs(folder, exist_ok=True)
    st = phone_load()
    if st and phone_ping(st):
        if os.path.normcase(st.get("folder", "")) == os.path.normcase(folder):
            return phone_info(st, roots, True)
        phone_stop_server(st)  # another folder wanted: restart
        time.sleep(0.4)
    s = socket.socket()
    s.bind(("0.0.0.0", 0))
    port = s.getsockname()[1]
    s.close()
    token = secrets.token_urlsafe(9)
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200 | 0x08000000  # detached, own process group, no window
    subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "phoneup.py"), str(port), token, folder],
                     creationflags=flags, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                     start_new_session=(os.name != "nt"))
    st = {"port": port, "token": token, "folder": folder}
    for _ in range(50):
        if phone_ping(st):
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("the upload receiver didn't start")
    with open(PHONE_STATE, "w", encoding="utf-8") as f:
        json.dump(st, f)
    return phone_info(st, roots, True)


def phone_stop(stash, args):
    roots, _ = libraries(stash)
    phone_stop_server(phone_load())
    return phone_info(None, roots, False)



# ---------- Sharing ----------
# sharing.py (next to this file) is a small receiver: people with one of your sharing links send photos, videos and
# messages to an inbox, you accept or reject them in Stash UI → Sharing. Data (settings, links, inbox, messages) lives
# in <Stash folder>/stashui-sharing, so a plugin update doesn't touch it. Modes:
#   share_status: {"mode": "share_status", "ensure": bool} → {"running", "publicPort", "adminPort", "token", "lan", "roots", "dir"}
#                 (ensure = start the receiver if it isn't running)
#   share_stop:   {"mode": "share_stop"} → {"running": false}
#   share_accept: {"mode": "share_accept", "ids": [...], "root": "<library folder>", "name": "Shared"} → the receiver moves the
#                 files into <root>/<name>/<sender> (checked to lie inside a library folder) → {"moved", "failed", "dirs", "folder"}
SHARE_STATE = os.environ.get("STASHUI_SHARE_STATE") or os.path.join(tempfile.gettempdir(), "stashui-share.json")  # (the variable is for tests: a separate receiver)
SHARE_V = 3


def share_dir(conn):
    c = {str(k).lower(): v for k, v in (conn or {}).items()}
    base = str(c.get("dir") or "") or os.path.join(os.path.expanduser("~"), ".stash")
    return os.path.join(base, "stashui-sharing")


def share_load():
    try:
        with open(SHARE_STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def share_call(st, path, body=None, timeout=5):
    url = f"http://127.0.0.1:{st['adminPort']}{path}?k={urllib.parse.quote(st['token'])}"
    req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None, {"Content-Type": "text/plain"}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def share_ping(st):
    try:
        return share_call(st, "/admin/ping", timeout=2)
    except Exception:  # noqa: BLE001 – not running / not answering
        return None


def port_free(p):
    s = socket.socket()
    try:
        s.bind(("0.0.0.0", p))
        return True
    except OSError:
        return False
    finally:
        s.close()


def free_port():
    s = socket.socket()
    s.bind(("0.0.0.0", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def share_info(st, roots, running, folder):
    ips = lan_ips()
    pub = (st or {}).get("publicPort")
    return {
        "running": running, "roots": roots, "dir": folder,
        "publicPort": pub, "adminPort": (st or {}).get("adminPort"), "token": (st or {}).get("token", "") if running else "",
        "lan": [f"http://{ip}:{pub}" for ip in ips] if running and pub else [],
    }


def share_stop_server(st):
    if not st:
        return
    try:
        share_call(st, "/admin/stop", {}, timeout=3)
    except Exception:  # noqa: BLE001
        pass
    try:
        os.remove(SHARE_STATE)
    except OSError:
        pass


def share_status(stash, args, conn):
    roots, _ = libraries(stash)
    folder = share_dir(conn)
    st = share_load()
    ping = share_ping(st) if st else None
    if ping and ping.get("v") != SHARE_V:  # an older receiver: restart it (everything it knows is in files)
        share_stop_server(st)
        time.sleep(0.5)
        st, ping = None, None
    if not ping:
        st = None
    if not st and args.get("ensure"):
        os.makedirs(folder, exist_ok=True)
        pub = 8787
        try:
            with open(os.path.join(folder, "port.txt"), encoding="utf-8") as f:
                pub = int(f.read().strip())
        except (OSError, ValueError):
            pass
        if not port_free(pub):
            pub = free_port()
        with open(os.path.join(folder, "port.txt"), "w", encoding="utf-8") as f:
            f.write(str(pub))
        adm = free_port()
        token = secrets.token_urlsafe(18)
        flags = 0
        if os.name == "nt":
            flags = 0x00000008 | 0x00000200 | 0x08000000  # detached, own process group, no window
        subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "sharing.py"), str(pub), str(adm), token, folder],
                         creationflags=flags, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                         start_new_session=(os.name != "nt"))
        st = {"publicPort": pub, "adminPort": adm, "token": token}
        for _ in range(60):
            if share_ping(st):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("the sharing receiver didn't start")
        with open(SHARE_STATE, "w", encoding="utf-8") as f:
            json.dump(st, f)
        ping = True
    return share_info(st, roots, bool(st and ping), folder)


def share_stop(stash, args, conn):
    roots, _ = libraries(stash)
    try:
        share_net(stash, {"action": "stop"}, conn)  # the internet access goes with it
    except Exception:  # noqa: BLE001
        pass
    share_stop_server(share_load())
    return share_info(None, roots, False, share_dir(conn))


def share_accept(stash, args, conn):
    roots, _ = libraries(stash)
    st = share_load()
    if not st or not share_ping(st):
        raise RuntimeError("sharing isn't running")
    if not roots:
        raise RuntimeError("Stash has no library folder yet")
    root = os.path.realpath(str(args.get("root") or roots[0]))
    if not inside(root, roots):
        raise ValueError("the folder has to be inside a library folder of Stash")
    name = str(args.get("name") or "Shared").replace(chr(92), "/").strip("/ ")
    if not name or any(part in ("..", ".") for part in name.split("/")):
        raise ValueError("bad folder name")
    folder = os.path.realpath(os.path.join(root, *name.split("/")))
    if not inside(folder, roots):
        raise ValueError("the folder has to be inside a library folder of Stash")
    os.makedirs(folder, exist_ok=True)
    ids = [str(i) for i in (args.get("ids") or [])]
    return share_call(st, "/admin/inbox", {"action": "move", "ids": ids, "folder": folder}, timeout=600)


# Watch links: a public link to ONE video – anybody can watch it in a normal browser (no Stash UI needed), as long as the link is
# valid. The receiver (sharing.py) serves the page and the file; this mode only checks which file it is.
#   watch_new: {"mode": "watch_new", "scene": "<id>", "hours": 24 | null, "maxViews": 0, "title": "…", "quality": 0 | 720 | 480 | 360} → {"link": {…}, "watches": [...]}
#              (quality > 0: the receiver makes a smaller MP4 copy with ffmpeg first – the link says "preparing" until it is done)
#              (the file has to lie inside a library folder of Stash; the receiver is started if it isn't running)
def watch_new(stash, args, conn):
    sid = str(args.get("scene") or "")
    if not sid.isdigit():
        raise ValueError("no scene")
    f = stash.gql("query($id: ID!) { findScene(id: $id) { files { path basename duration } title } }", {"id": sid})["findScene"]
    if not f or not f.get("files"):
        raise ValueError("the scene has no file")
    path = f["files"][0]["path"]
    roots, _ = libraries(stash)
    if not inside(path, roots):
        raise ValueError("only videos inside a library folder of Stash can be shared")
    if not os.path.isfile(path):
        raise ValueError("this file can't be found on the computer Stash runs on")
    share_status(stash, {"ensure": True}, conn)
    st = share_load()
    title = str(args.get("title") or "").strip() or f.get("title") or os.path.splitext(f["files"][0].get("basename") or "Video")[0]
    q = int(args.get("quality") or 0)
    return share_call(st, "/admin/watch", {"action": "new", "path": path, "scene": sid, "title": title, "hours": args.get("hours") or None, "maxViews": args.get("maxViews") or 0,
                                           "quality": q, "ffmpeg": find_ffmpeg(stash) if q else "", "duration": f["files"][0].get("duration") or 0})


# Internet access for the receiver (Sharing → Public address → "Make reachable from the internet"): runs a program that is
# already installed on this PC – Tailscale Funnel (a fixed address) or a Cloudflare quick tunnel (a new address every start) –
# for the receiver's PUBLIC port only. Nothing is downloaded. State (which program, the address) is kept in <data>/net.json.
#   share_net: {"mode": "share_net", "action": "status" | "start" | "stop", "provider": "tailscale" | "cloudflared" (optional)}
#              → {"providers": {"tailscale": bool, "cloudflared": bool}, "running", "provider", "url"}
TS_URL = re.compile(r"https://[A-Za-z0-9.-]+\.ts\.net")
CF_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def net_find(name):
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt":
        sub = {"tailscale": "Tailscale\\tailscale.exe", "cloudflared": "cloudflared\\cloudflared.exe"}[name]
        for var in ("ProgramFiles", "ProgramFiles(x86)"):
            p = os.path.join(os.environ.get(var) or "", sub)
            if os.environ.get(var) and os.path.isfile(p):
                return p
    return None


def net_run(args, timeout):
    flags = 0x08000000 if os.name == "nt" else 0  # no console window
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, stdin=subprocess.DEVNULL, creationflags=flags)
    return (r.stdout or "") + (r.stderr or "")


def pid_alive(pid):
    try:
        if os.name == "nt":
            return str(pid) in net_run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"], 10)
        os.kill(int(pid), 0)
        return True
    except Exception:  # noqa: BLE001
        return False


def pid_kill(pid):
    try:
        if os.name == "nt":
            net_run(["taskkill", "/PID", str(int(pid)), "/T", "/F"], 10)
        else:
            os.kill(int(pid), 15)
    except Exception:  # noqa: BLE001
        pass


def share_net(stash, args, conn):
    folder = share_dir(conn)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "net.json")
    st = share_load()
    if not st or not share_ping(st):
        raise RuntimeError("sharing isn't running")
    port = int(st["publicPort"])
    progs = {"tailscale": net_find("tailscale"), "cloudflared": net_find("cloudflared")}
    try:
        with open(path, encoding="utf-8") as f:
            cur = json.load(f)
    except (OSError, ValueError):
        cur = None

    def alive(c):
        if c.get("provider") == "tailscale" and progs["tailscale"]:
            try:
                return c["url"].lower() in net_run([progs["tailscale"], "funnel", "status"], 10).lower()
            except Exception:  # noqa: BLE001
                return False
        return c.get("provider") == "cloudflared" and c.get("pid") and pid_alive(c["pid"])

    if cur and not alive(cur):
        cur = None
        try:
            os.remove(path)
        except OSError:
            pass
    act = str(args.get("action") or "status")
    if act == "install":  # cloudflared from Windows' own package manager (the official package, nothing else is downloaded by us)
        if os.name != "nt" or not shutil.which("winget"):
            raise RuntimeError("Installing from here needs Windows with winget – install cloudflared yourself (cloudflared releases on github.com/cloudflare)")
        out = net_run(["winget", "install", "--id", "Cloudflare.cloudflared", "-e", "--silent", "--accept-source-agreements", "--accept-package-agreements"], 300)
        progs["cloudflared"] = net_find("cloudflared")
        if not progs["cloudflared"]:
            raise RuntimeError("cloudflared wasn't found after installing – restart Stash and try again. " + re.sub(r"\s+", " ", out).strip()[-200:])
    if act == "stop" and cur:
        if cur["provider"] == "tailscale":
            net_run([progs["tailscale"], "funnel", str(port), "off"], 20)
        else:
            pid_kill(cur["pid"])
        cur = None
        try:
            os.remove(path)
        except OSError:
            pass
    elif act == "start" and not cur:
        want = str(args.get("provider") or "")
        prov = want if want in progs and progs[want] else ("tailscale" if progs["tailscale"] else "cloudflared" if progs["cloudflared"] else "")
        if not prov:
            raise RuntimeError("neither Tailscale nor cloudflared is installed")
        if prov == "tailscale":
            problem = ""
            try:
                out = net_run([progs["tailscale"], "funnel", "--bg", str(port)], 30)
                m = TS_URL.search(out)
                if m:
                    cur = {"provider": "tailscale", "url": m.group(0)}
                else:
                    text = re.sub(r"\s+", " ", out).strip()
                    if re.search(r"NoState|NeedsLogin|Stopped|not running|logged out|connect", text, re.I):
                        problem = "Tailscale isn't connected – open Tailscale, sign in and make sure it says Connected (" + text[:120] + ")"
                    else:
                        problem = text[:400] or "Tailscale Funnel didn't start"
            except subprocess.TimeoutExpired:
                problem = "Tailscale didn't answer – is it running and signed in?"
            if not cur:
                if not (progs["cloudflared"] and not want):  # no other way (or Tailscale was asked for): say why
                    raise RuntimeError(problem)
                prov = "cloudflared"  # Tailscale isn't usable right now: a Cloudflare tunnel does the same job (with a changing address)
        if prov == "cloudflared":
            log = os.path.join(folder, "cloudflared.log")
            flags = 0
            if os.name == "nt":
                flags = 0x00000008 | 0x00000200 | 0x08000000
            with open(log, "w", encoding="utf-8") as lf:
                p = subprocess.Popen([progs["cloudflared"], "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"], stdin=subprocess.DEVNULL, stdout=lf, stderr=lf,
                                     creationflags=flags, close_fds=True, start_new_session=(os.name != "nt"))
            url = None
            for _ in range(60):
                time.sleep(0.5)
                try:
                    with open(log, encoding="utf-8", errors="replace") as lf:
                        m = CF_URL.search(lf.read())
                except OSError:
                    m = None
                if m:
                    url = m.group(0)
                    break
                if p.poll() is not None:
                    break
            if not url:
                pid_kill(p.pid)
                raise RuntimeError("the Cloudflare tunnel didn't start")
            cur = {"provider": "cloudflared", "url": url, "pid": p.pid}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cur, f)
    return {"providers": {k: bool(v) for k, v in progs.items()}, "canInstall": os.name == "nt" and bool(shutil.which("winget")), "running": bool(cur), "provider": (cur or {}).get("provider", ""), "url": (cur or {}).get("url", "")}


# ---------- Cut clips (player → "Cut clips") ----------
# {"mode": "clip_cut", "scene_id", "clips": [{"start", "end", "name"}], "precise": bool, "join": bool, "folder": "same"|"Clips"}
#   → {"job"}: ffmpeg runs in its own process (the page may be closed); the page scans the new files into Stash itself.
# {"mode": "clip_status", "job"} → {"state": "running"|"done"|"error", "i", "n", "files": [paths], "error"}

CUT_DIR = tempfile.gettempdir()
BAD_NAME = r'<>:"/\|?*'


def find_ffmpeg(stash):
    import shutil
    try:
        p = stash.gql("query { configuration { general { ffmpegPath } } }")["configuration"]["general"].get("ffmpegPath")
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    found = shutil.which("ffmpeg")
    if found:
        return found
    for name in ("ffmpeg.exe", "ffmpeg"):
        p = os.path.join(os.path.expanduser("~"), ".stash", name)
        if os.path.isfile(p):
            return p
    raise RuntimeError("ffmpeg not found – Stash normally brings its own")


def clean_name(s):
    s = "".join("_" if c in BAD_NAME or ord(c) < 32 else c for c in str(s)).strip(" .")
    return s[:80]


def clip_cut(stash, args):
    sid = str(args.get("scene_id") or "")
    video = scene_video(stash, sid)
    if not os.path.isfile(video):
        raise ValueError(f"the video file can't be reached from here: {video}")
    clips = []
    for c in args.get("clips") or []:
        a, b = float(c.get("start")), float(c.get("end"))
        if not (a >= 0 and b > a):
            raise ValueError("a clip ends before it starts")
        clip = {"start": a, "end": b, "name": clean_name(c.get("name") or "")}
        cr = c.get("crop")
        if cr:  # a part of the picture (fractions of the width/height), e.g. {"x": .2, "y": .1, "w": .5, "h": .5}
            x0, y0, w0, h0 = (max(0.0, min(1.0, float(cr.get(k)))) for k in ("x", "y", "w", "h"))
            if w0 < 0.02 or h0 < 0.02 or x0 + w0 > 1.0005 or y0 + h0 > 1.0005:
                raise ValueError("the cropped area doesn't fit into the picture")
            clip["crop"] = {"x": x0, "y": y0, "w": min(w0, 1 - x0), "h": min(h0, 1 - y0)}
        clips.append(clip)
    if not clips or len(clips) > 100:
        raise ValueError("no clips")
    base, ext = os.path.splitext(os.path.basename(video))
    folder = out_folder(stash, video, args.get("folder"))
    job = secrets.token_hex(4)
    def even(n, fallback=0):
        n = int(float(n or 0))
        return n - n % 2 if n >= 2 else fallback

    spec = {"job": job, "video": video, "ffmpeg": find_ffmpeg(stash), "clips": clips, "precise": bool(args.get("precise")) or any("crop" in c for c in clips),
            "join": bool(args.get("join")), "folder": folder, "base": base, "ext": ".mp4",
            "upscale": bool(args.get("upscale")), "ref_w": even(args.get("ref_w")), "ref_h": even(args.get("ref_h"))}
    path = os.path.join(CUT_DIR, f"stashui-cut-{job}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec, f)
    flags = (0x08000000 | 0x00000200) if os.name == "nt" else 0
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "--cutjob", path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    return {"job": job}


def clips_dir_setting(stash):
    """The one folder for all new clips and GIFs (Settings → This interface), or "" = next to each original."""
    try:
        plugins = stash.gql("query { configuration { plugins } }")["configuration"].get("plugins") or {}
        return str((plugins.get("stashui") or {}).get("clipsDir") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def out_folder(stash, video, folder_arg):
    """Where a new clip / GIF / edit goes: the one folder of the setting if there is one (all of them end up together),
    else the folder of the original – in a subfolder "Clips" if asked for."""
    d = clips_dir_setting(stash)
    if d:
        if not os.path.isabs(d):
            raise ValueError("The folder for new clips (Settings) has to be a full path")
        os.makedirs(d, exist_ok=True)
        return d
    folder = os.path.dirname(video)
    if folder_arg == "Clips":
        folder = os.path.join(folder, "Clips")
        os.makedirs(folder, exist_ok=True)
    return folder


def clips_dir_check(stash, args):
    """Is this folder usable for new clips? {"path"} → {"ok", "created", "in_library", "why"}."""
    d = str(args.get("path") or "").strip()
    if not d:
        return {"ok": True, "empty": True}
    if not os.path.isabs(d):
        return {"ok": False, "why": "relative"}
    created = not os.path.isdir(d)
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".stashui-write-test")
        with open(probe, "w") as f:
            f.write("x")
        os.remove(probe)
    except OSError as e:
        return {"ok": False, "why": str(e.strerror or e)}
    roots, _ = libraries(stash)
    return {"ok": True, "created": created, "in_library": inside(d, roots)}


def cut_status_path(job):
    if not str(job).isalnum():
        raise ValueError("bad job")
    return os.path.join(CUT_DIR, f"stashui-cut-{job}.status.json")


def clip_status(stash, args):
    try:
        with open(cut_status_path(args.get("job")), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"state": "running", "i": 0, "n": 0, "files": []}


def unique(path):
    root, ext = os.path.splitext(path)
    n, p = 2, path
    while os.path.exists(p):
        p = f"{root} ({n}){ext}"
        n += 1
    return p


def crop_filter(cr, spec, any_crop):
    """ffmpeg -vf for a cropped (zoomed-in) clip: cut the area out (even sizes for H.264), optionally scale it back up to the
    original's height. Clips that get joined must have one size: then every part (cropped or not) is fitted into the original size."""
    if not cr and not (spec["join"] and any_crop):
        return ""
    f = []
    if cr:
        f.append("crop=trunc(iw*{w:.5f}/2)*2:trunc(ih*{h:.5f}/2)*2:trunc(iw*{x:.5f}/2)*2:trunc(ih*{y:.5f}/2)*2".format(**cr))
    rw, rh = spec.get("ref_w") or 0, spec.get("ref_h") or 0
    if spec["join"] and any_crop and rw and rh:
        f.append(f"scale={rw}:{rh}:force_original_aspect_ratio=decrease:flags=lanczos,pad={rw}:{rh}:(ow-iw)/2:(oh-ih)/2,setsar=1")
    elif cr and spec.get("upscale") and rh:
        f.append(f"scale=-2:'if(lt(ih,{rh}),{rh},ih)':flags=lanczos")
    return ",".join(f)


def cut_job(spec_path):
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    st = {"state": "running", "i": 0, "n": len(spec["clips"]), "files": [], "error": ""}
    sp = cut_status_path(spec["job"])

    def save():
        with open(sp + ".tmp", "w", encoding="utf-8") as f:
            json.dump(st, f)
        os.replace(sp + ".tmp", sp)

    save()
    flags = 0x08000000 if os.name == "nt" else 0
    parts = []
    try:
        for i, c in enumerate(spec["clips"]):
            st["i"] = i
            save()
            if spec["join"]:
                out = os.path.join(CUT_DIR, f"stashui-cut-{spec['job']}-{i}.mp4")
            else:
                label = c["name"] or f"clip {i + 1}"
                out = unique(os.path.join(spec["folder"], f"{spec['base']} - {label}{spec['ext']}"))
            cmd = [spec["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{c['start']:.3f}", "-i", spec["video"], "-t", f"{c['end'] - c['start']:.3f}", "-map", "0:v:0", "-map", "0:a?"]
            vf = crop_filter(c.get("crop"), spec, any("crop" in k for k in spec["clips"]))
            if vf:
                cmd += ["-vf", vf]
            if spec["precise"]:
                cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
            else:
                cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
            cmd += ["-movflags", "+faststart", out]
            r = subprocess.run(cmd, capture_output=True, text=True, creationflags=flags)
            if r.returncode != 0 or not os.path.isfile(out):
                raise RuntimeError((r.stderr or "ffmpeg failed").strip().splitlines()[-1])
            parts.append(out)
            if not spec["join"]:
                st["files"].append(out)
        if spec["join"]:
            lst = os.path.join(CUT_DIR, f"stashui-cut-{spec['job']}.txt")
            with open(lst, "w", encoding="utf-8") as f:
                f.write("".join("file '" + p.replace("\\", "/").replace("'", "'\''") + "'\n" for p in parts))
            out = unique(os.path.join(spec["folder"], f"{spec['base']} - clips{spec['ext']}"))
            r = subprocess.run([spec["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", out],
                               capture_output=True, text=True, creationflags=flags)
            if r.returncode != 0 or not os.path.isfile(out):
                raise RuntimeError((r.stderr or "ffmpeg failed").strip().splitlines()[-1])
            st["files"].append(out)
            for p in parts + [lst]:
                try:
                    os.remove(p)
                except OSError:
                    pass
        st["state"] = "done"
        st["i"] = st["n"]
    except Exception as e:  # noqa: BLE001
        st["state"] = "error"
        st["error"] = str(e)
    save()


# ---------- GIF maker: a part of a scene as an animated GIF ----------
# {"mode": "gif_make", "scene_id", "start", "end", "width", "fps", "speed", "quality": "small"|"good"|"best", "loop": bool, "crop": {x,y,w,h},
#  "folder": "Clips"|"", "name"} → {"job"}; "clip_status" says how far it is ({"state", "pct", "files", "error"}).

def gif_make(stash, args):
    sid = str(args.get("scene_id") or "")
    video = scene_video(stash, sid)
    if not os.path.isfile(video):
        raise ValueError(f"the video file can't be reached from here: {video}")
    a, b = float(args.get("start")), float(args.get("end"))
    if not (a >= 0 and b > a + 0.2):
        raise ValueError("the end must be after the start")
    if b - a > 60:
        raise ValueError("a GIF can be 60 seconds long at most")
    spec = {"job": secrets.token_hex(4), "ffmpeg": find_ffmpeg(stash), "video": video, "start": a, "end": b,
            "width": max(120, min(1920, int(args.get("width") or 480))), "fps": max(5, min(30, int(args.get("fps") or 15))),
            "speed": max(0.25, min(4.0, float(args.get("speed") or 1.0))), "quality": args.get("quality") if args.get("quality") in ("small", "good", "best") else "good",
            "loop": bool(args.get("loop", True))}
    if args.get("target_mb"):  # "keep it under n MB": the job picks the best width / pictures per second / colours that fit
        spec["target"] = int(max(0.2, min(200.0, float(args["target_mb"]))) * 1024 * 1024)
    cr = args.get("crop")
    if cr:
        x0, y0, w0, h0 = (max(0.0, min(1.0, float(cr.get(k)))) for k in ("x", "y", "w", "h"))
        if w0 < 0.02 or h0 < 0.02 or x0 + w0 > 1.0005 or y0 + h0 > 1.0005:
            raise ValueError("the cropped area doesn't fit into the picture")
        spec["crop"] = {"x": x0, "y": y0, "w": min(w0, 1 - x0), "h": min(h0, 1 - y0)}
    folder = out_folder(stash, video, args.get("folder"))
    base = os.path.splitext(os.path.basename(video))[0]
    name = clean_name(args.get("name") or "") or f"{base} - GIF {int(a // 60)}-{int(a % 60):02d}"
    spec["out"] = unique(os.path.join(folder, name + ".gif"))
    path = os.path.join(CUT_DIR, f"stashui-gif-{spec['job']}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec, f)
    flags = (0x08000000 | 0x00000200) if os.name == "nt" else 0
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "--gifjob", path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    return {"job": spec["job"]}


# the settings a size limit chooses from, best looking first: (width, pictures per second, quality)
GIF_LADDER = [(1280, 20, "good"), (960, 20, "good"), (800, 20, "good"), (800, 15, "good"), (640, 15, "good"), (560, 15, "good"), (480, 15, "good"), (480, 12, "good"),
              (400, 12, "good"), (360, 12, "small"), (320, 12, "small"), (320, 10, "small"), (280, 10, "small"), (240, 10, "small"), (200, 10, "small"), (160, 8, "small")]


def gif_graph(spec, width, fps, quality):
    vf = []
    cr = spec.get("crop")
    if cr:
        vf.append("crop=trunc(iw*{w:.5f}/2)*2:trunc(ih*{h:.5f}/2)*2:trunc(iw*{x:.5f}/2)*2:trunc(ih*{y:.5f}/2)*2".format(**cr))
    if spec["speed"] != 1:
        vf.append(f"setpts=PTS/{spec['speed']:.4f}")
    vf.append(f"fps={fps}")
    vf.append(f"scale='min({width},iw)':-1:flags=lanczos")
    # the palette is made from the picture itself (much better colours than the default palette)
    gen = "palettegen=max_colors=" + ("128:stats_mode=diff" if quality == "small" else "256:stats_mode=diff" if quality == "good" else "256:stats_mode=full")
    use = "paletteuse=dither=" + ("bayer:bayer_scale=5:diff_mode=rectangle" if quality == "small" else "bayer:bayer_scale=3:diff_mode=rectangle" if quality == "good" else "sierra2_4a")
    return ",".join(vf) + f",split[a][b];[a]{gen}[p];[b][p]{use}"


def gif_encode(spec, out, width, fps, quality, start, span, on_progress=None):
    """One encode of `span` seconds from `start` → size of the file."""
    cmd = [spec["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y", "-progress", "pipe:1", "-nostats", "-ss", f"{start:.3f}", "-t", f"{span:.3f}", "-i", spec["video"],
           "-an", "-filter_complex", gif_graph(spec, width, fps, quality), "-loop", "0" if spec["loop"] else "-1", out]
    total = span / spec["speed"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=0x08000000 if os.name == "nt" else 0)
    last = 0.0
    for line in proc.stdout:
        line = line.strip()
        if on_progress and (line.startswith("out_time_us=") or line.startswith("out_time_ms=")):
            try:
                t_out = int(line.split("=", 1)[1]) / 1e6
            except ValueError:
                continue
            if time.time() - last > 0.5:
                on_progress(max(0.0, min(0.99, t_out / total)) if total > 0 else 0.0)
                last = time.time()
    err = proc.stderr.read()
    proc.wait()
    if proc.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError((err or "ffmpeg failed").strip().splitlines()[-1] if (err or "").strip() else "ffmpeg failed")
    return os.path.getsize(out)


def gif_job(spec_path):
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    st = {"state": "running", "i": 0, "n": 1, "pct": 0, "files": [], "error": "", "phase": "encode"}
    sp = cut_status_path(spec["job"])

    def save():
        with open(sp + ".tmp", "w", encoding="utf-8") as f:
            json.dump(st, f)
        os.replace(sp + ".tmp", sp)

    save()
    try:
        span = spec["end"] - spec["start"]
        width, fps, quality = spec["width"], spec["fps"], spec["quality"]
        target = spec.get("target")
        if not target:
            def prog(x):
                st["pct"] = int(99 * x)
                save()
            size = gif_encode(spec, spec["out"], width, fps, quality, spec["start"], span, prog)
        else:
            # a size limit: the chosen width / pictures per second are the most it may use; below that the best that fits is searched.
            # A short sample from the middle of the part is encoded for each try (size per second × length = what the whole will be).
            ladder = [c for c in GIF_LADDER if c[0] <= width and c[1] <= fps] or [GIF_LADDER[-1]]
            if (width, fps, quality) not in ladder and ladder[0][0] < width:
                ladder.insert(0, (width, fps, quality if quality != "best" else "good"))
            sample = min(span, 2.0)
            s0 = spec["start"] + (span - sample) / 2
            tmp = spec["out"] + ".probe.gif"
            st["phase"] = "probe"

            def fits(i):
                w, f, q = ladder[i]
                sz = gif_encode(spec, tmp, w, f, q, s0, sample)
                est = sz / sample * span
                st["pct"] = min(25, st["pct"] + 5)
                save()
                return est <= target * 0.93

            lo, hi = 0, len(ladder) - 1  # the first that fits (bigger index = smaller GIF)
            if fits(0):
                pick = 0
            else:
                while lo < hi:
                    mid = (lo + hi) // 2
                    if fits(mid):
                        hi = mid
                    else:
                        lo = mid + 1
                pick = lo
            try:
                os.remove(tmp)
            except OSError:
                pass
            st["phase"] = "encode"
            size = None
            for i in range(pick, min(len(ladder), pick + 4)):  # (the estimate can be a bit off: one step down per miss)
                w, f, q = ladder[i]
                base = 25
                size = gif_encode(spec, spec["out"], w, f, q, spec["start"], span, lambda x: (st.__setitem__("pct", base + int((99 - base) * x)), save()))
                st["chosen"] = {"width": w, "fps": f, "quality": q}
                if size <= target:
                    break
            if size is not None and size > target:
                st["over"] = True  # even the smallest try was above the limit – the file is kept, the page says so
        st["files"].append(spec["out"])
        st["size"] = size
        st["pct"] = 100
        st["state"] = "done"
        st["i"] = 1
    except Exception as e:  # noqa: BLE001
        st["state"] = "error"
        st["error"] = str(e)
    save()


# ---------- Editor: pieces of several scenes, in a row, as one new video ----------
# {"mode": "edit_render", "items": [{"scene_id", "start", "end", "speed"}], "name", "w", "h", "fps", "fade", "audio": "keep"|"mute",
#  "folder": "Clips"|""} → {"job"}; "clip_status" says how far it is ({"state", "pct", "files", "error"}).

def has_audio(ffmpeg, path):
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", path], capture_output=True, text=True, creationflags=0x08000000 if os.name == "nt" else 0)
    return " Audio:" in (r.stderr or "")


def atempo_chain(sp):
    out = []
    while sp > 2.0:
        out.append("atempo=2.0")
        sp /= 2.0
    while sp < 0.5:
        out.append("atempo=0.5")
        sp /= 0.5
    out.append(f"atempo={sp:.4f}")
    return ",".join(out)


def edit_render(stash, args):
    items = []
    ffmpeg = find_ffmpeg(stash)
    for c in args.get("items") or []:
        video = scene_video(stash, str(c.get("scene_id") or ""))
        if not os.path.isfile(video):
            raise ValueError(f"the video file can't be reached from here: {video}")
        a, b = float(c.get("start")), float(c.get("end"))
        if not (a >= 0 and b > a + 0.1):
            raise ValueError("a piece ends before it starts")
        sp = max(0.25, min(4.0, float(c.get("speed") or 1.0)))
        items.append({"path": video, "start": a, "end": b, "speed": sp, "audio": has_audio(ffmpeg, video)})
    if not items or len(items) > 60:
        raise ValueError("no pieces (or more than 60)")

    def even(n, lo, hi):
        n = int(float(n or 0))
        n = max(lo, min(hi, n))
        return n - n % 2

    w, h = even(args.get("w"), 160, 3840), even(args.get("h"), 160, 2160)
    folder = out_folder(stash, items[0]["path"], args.get("folder"))
    name = clean_name(args.get("name") or "") or "Edit"
    job = secrets.token_hex(4)
    spec = {"job": job, "ffmpeg": ffmpeg, "items": items, "w": w, "h": h, "fps": max(10, min(60, int(args.get("fps") or 30))),
            "fade": max(0.0, min(2.0, float(args.get("fade") or 0))), "keep": args.get("audio") != "mute", "out": unique(os.path.join(folder, name + ".mp4"))}
    path = os.path.join(CUT_DIR, f"stashui-edit-{job}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec, f)
    flags = (0x08000000 | 0x00000200) if os.name == "nt" else 0
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "--editjob", path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    return {"job": job}


def edit_job(spec_path):
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    st = {"state": "running", "i": 0, "n": 1, "pct": 0, "files": [], "error": ""}
    sp = cut_status_path(spec["job"])

    def save():
        with open(sp + ".tmp", "w", encoding="utf-8") as f:
            json.dump(st, f)
        os.replace(sp + ".tmp", sp)

    save()
    flags = 0x08000000 if os.name == "nt" else 0
    try:
        items, w, h, fps, fade, keep = spec["items"], spec["w"], spec["h"], spec["fps"], spec["fade"], spec["keep"]
        cmd = [spec["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y", "-progress", "pipe:1", "-nostats"]
        fc, total = [], 0.0
        for i, it in enumerate(items):
            span, spd = it["end"] - it["start"], it["speed"]
            out_dur = span / spd
            total += out_dur
            cmd += ["-ss", f"{it['start']:.3f}", "-t", f"{span:.3f}", "-i", it["path"]]
            v = f"[{i}:v:0]scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={fps},format=yuv420p,setpts=PTS-STARTPTS"
            if spd != 1:
                v += f",setpts=PTS/{spd:.4f}"
            f_d = min(fade, out_dur / 2) if fade > 0 else 0
            if f_d > 0:
                v += f",fade=t=in:st=0:d={f_d:.3f},fade=t=out:st={out_dur - f_d:.3f}:d={f_d:.3f}"
            fc.append(v + f"[v{i}]")
            if keep:
                if it["audio"]:
                    a = f"[{i}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
                    if spd != 1:
                        a += "," + atempo_chain(spd)
                    a += ",asetpts=PTS-STARTPTS"
                    if f_d > 0:
                        a += f",afade=t=in:st=0:d={f_d:.3f},afade=t=out:st={out_dur - f_d:.3f}:d={f_d:.3f}"
                else:
                    a = f"anullsrc=r=48000:cl=stereo,atrim=0:{out_dur:.3f},asetpts=PTS-STARTPTS"
                fc.append(a + f"[a{i}]")
        join = "".join(f"[v{i}]" + (f"[a{i}]" if keep else "") for i in range(len(items)))
        fc.append(f"{join}concat=n={len(items)}:v=1:a={1 if keep else 0}[v]" + ("[a]" if keep else ""))
        # (inline: "-filter_complex_script" is gone from newer ffmpeg versions; 60 pieces stay far below the command line limit)
        cmd += ["-filter_complex", ";".join(fc), "-map", "[v]"] + (["-map", "[a]"] if keep else ["-an"])
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-b:a", "192k"] if keep else []) + ["-movflags", "+faststart", spec["out"]]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=flags)
        last = 0.0
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                try:
                    t_out = int(line.split("=", 1)[1]) / 1e6
                except ValueError:
                    continue
                if time.time() - last > 0.7:
                    st["pct"] = max(0, min(99, int(100 * t_out / total))) if total > 0 else 0
                    save()
                    last = time.time()
        err = proc.stderr.read()
        proc.wait()
        if proc.returncode != 0 or not os.path.isfile(spec["out"]):
            raise RuntimeError((err or "ffmpeg failed").strip().splitlines()[-1] if (err or "").strip() else "ffmpeg failed")
        st["files"].append(spec["out"])
        st["pct"] = 100
        st["state"] = "done"
        st["i"] = 1
    except Exception as e:  # noqa: BLE001
        st["state"] = "error"
        st["error"] = str(e)
    save()


# ---------- Crop / edit the video itself: a new start, end and/or picture area, replacing the file ----------
# {"mode": "video_edit", "scene_id", "start", "end", "crop": {x,y,w,h}, "precise": bool, "keep": bool} → {"job"}: ffmpeg writes the result next to
#   the original under a temporary name (own process); "clip_status" says how far it is ({"state": "running"|"ready"|"error", "pct", "error"}).
# {"mode": "video_edit_swap", "job"} → {"path", "backup"}: puts the finished file where the original is. With "keep" the original becomes
#   "<name>.orig" (Stash doesn't scan that), otherwise it is gone. {"mode": "video_edit_drop", "job"} throws a finished result away.
# The paths never come from the page: they are in the job's spec file.

VEDIT_FORMATS = {".mp4": "mp4", ".m4v": "mp4", ".mov": "mov", ".mkv": "matroska", ".webm": "webm", ".avi": "avi"}
VEDIT_ENCODE = {".mp4", ".m4v", ".mov", ".mkv"}  # (containers that take H.264 + AAC)


def vedit_spec_path(job):
    if not str(job).isalnum():
        raise ValueError("bad job")
    return os.path.join(CUT_DIR, f"stashui-vedit-{job}.json")


def video_edit(stash, args):
    sid = str(args.get("scene_id") or "")
    if not sid.isdigit():
        raise ValueError("no scene")
    sc = stash.gql("query($id: ID!) { findScene(id: $id) { files { path duration } } }", {"id": sid})["findScene"]
    if not sc or not sc.get("files"):
        raise ValueError("the scene has no file")
    video, dur = sc["files"][0]["path"], float(sc["files"][0].get("duration") or 0)
    if not os.path.isfile(video):
        raise ValueError(f"the video file can't be reached from here: {video}")
    roots, _ = libraries(stash)
    if not inside(video, roots):
        raise ValueError("this video isn't in a library folder of Stash")
    ext = os.path.splitext(video)[1].lower()
    if ext not in VEDIT_FORMATS:
        raise ValueError(f"{ext or 'this kind of'} files can't be changed in place – use Cut clips to make a new video")
    a, b = float(args.get("start") or 0), float(args.get("end") or 0)
    if dur and b > dur:
        b = dur
    if not (a >= 0 and b > a + 0.2):
        raise ValueError("the end must be after the start")
    crop = None
    cr = args.get("crop")
    if cr:
        x0, y0, w0, h0 = (max(0.0, min(1.0, float(cr.get(k)))) for k in ("x", "y", "w", "h"))
        if w0 < 0.02 or h0 < 0.02 or x0 + w0 > 1.0005 or y0 + h0 > 1.0005:
            raise ValueError("the cropped area doesn't fit into the picture")
        if w0 < 0.995 or h0 < 0.995:
            crop = {"x": x0, "y": y0, "w": min(w0, 1 - x0), "h": min(h0, 1 - y0)}
    if not crop and a < 0.05 and (not dur or dur - b < 0.05):
        raise ValueError("nothing to change – the whole video is kept")
    precise = bool(args.get("precise")) or bool(crop)
    if precise and ext not in VEDIT_ENCODE:
        raise ValueError(f"{ext} files can only be shortened without re-encoding (Fast), and not cropped")
    job = secrets.token_hex(4)
    spec = {"job": job, "ffmpeg": find_ffmpeg(stash), "video": video, "tmp": f"{video}.stashui-{job}.tmp", "start": a, "end": b, "crop": crop,
            "precise": precise, "keep": bool(args.get("keep")), "fmt": VEDIT_FORMATS[ext]}
    with open(vedit_spec_path(job), "w", encoding="utf-8") as f:
        json.dump(spec, f)
    flags = (0x08000000 | 0x00000200) if os.name == "nt" else 0
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "--vedit", vedit_spec_path(job)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    return {"job": job}


def vedit_job(spec_path):
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    st = {"state": "running", "pct": 0, "files": [], "error": ""}
    sp = cut_status_path(spec["job"])

    def save():
        with open(sp + ".tmp", "w", encoding="utf-8") as f:
            json.dump(st, f)
        os.replace(sp + ".tmp", sp)

    save()
    flags = 0x08000000 if os.name == "nt" else 0
    total = spec["end"] - spec["start"]
    try:
        cmd = [spec["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y", "-progress", "pipe:1", "-nostats", "-ss", f"{spec['start']:.3f}", "-i", spec["video"],
               "-t", f"{total:.3f}", "-map", "0:v:0", "-map", "0:a?", "-map_metadata", "0"]
        vf = crop_filter(spec.get("crop"), {"join": False}, False)
        if vf:
            cmd += ["-vf", vf]
        if spec["precise"]:
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"]
        else:
            cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
        if spec["fmt"] in ("mp4", "mov"):
            cmd += ["-movflags", "+faststart"]
        cmd += ["-f", spec["fmt"], spec["tmp"]]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=flags)
        last = 0.0
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                try:
                    t_out = int(line.split("=", 1)[1]) / 1e6
                except ValueError:
                    continue
                if time.time() - last > 0.7:
                    st["pct"] = max(0, min(99, int(100 * t_out / total))) if total > 0 else 0
                    save()
                    last = time.time()
        err = proc.stderr.read()
        proc.wait()
        if proc.returncode != 0 or not os.path.isfile(spec["tmp"]) or os.path.getsize(spec["tmp"]) < 1024:
            raise RuntimeError((err or "ffmpeg failed").strip().splitlines()[-1] if (err or "").strip() else "ffmpeg failed")
        st["pct"] = 100
        st["state"] = "ready"
    except Exception as e:  # noqa: BLE001
        st["state"] = "error"
        st["error"] = str(e)
        try:
            os.remove(spec["tmp"])
        except OSError:
            pass
    save()


def vedit_load(job, need_ready=False):
    try:
        with open(vedit_spec_path(job), encoding="utf-8") as f:
            spec = json.load(f)
    except (OSError, ValueError):
        raise ValueError("this edit is not known any more")
    if need_ready:
        try:
            with open(cut_status_path(job), encoding="utf-8") as f:
                ok = json.load(f).get("state") == "ready"
        except (OSError, ValueError):
            ok = False
        if not ok:
            raise ValueError("the new video isn't finished")
    return spec


def vedit_forget(job):
    for p in (vedit_spec_path(job), cut_status_path(job)):
        try:
            os.remove(p)
        except OSError:
            pass


def video_edit_swap(stash, args):
    job = str(args.get("job") or "")
    spec = vedit_load(job, True)
    video, tmp = spec["video"], spec["tmp"]
    if not os.path.isfile(tmp):
        raise ValueError("the new video is gone")
    if not os.path.isfile(video):
        raise ValueError("the original video is gone")
    backup = unique(video + ".orig") if spec.get("keep") else ""
    # (Stash or the browser may still hold the file for a moment: try again for half a minute)
    err = None
    for _ in range(40):
        try:
            if backup:
                os.replace(video, backup)
                try:
                    os.replace(tmp, video)
                except OSError:
                    os.replace(backup, video)
                    raise
            else:
                os.replace(tmp, video)
            err = None
            break
        except OSError as e:
            err = e
            time.sleep(0.75)
    if err:
        raise RuntimeError(f"the video is in use and can't be replaced right now ({err.strerror or err})")
    vedit_forget(job)
    return {"path": video, "backup": backup}


def video_edit_drop(stash, args):
    job = str(args.get("job") or "")
    try:
        spec = vedit_load(job)
        os.remove(spec["tmp"])
    except (ValueError, OSError):
        pass
    vedit_forget(job)
    return {"ok": True}


# ---------- Match two videos by their sound (O video ↔ the video playing in its background) ----------
# {"mode": "sync_audio", "scene_a": main video, "scene_b": O video} → {"offset", "score", "sure"}
#   offset: the O video's own start lies this many seconds into the main video (negative: the O video started earlier and the
#   main video is already running in it at its start). O time = main time − offset. Works on the loudness changes of the two
#   soundtracks (beats, cuts), so it also works when the O video has voices and room noise over the music. Needs numpy.

SYNC_RATE = 8000
SYNC_HOP = 80  # 10 ms


def sync_envelope(ffmpeg, path, max_sec):
    import numpy as np
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-t", str(max_sec), "-i", path, "-vn", "-ac", "1", "-ar", str(SYNC_RATE), "-f", "s16le", "-"]
    r = subprocess.run(cmd, capture_output=True, creationflags=0x08000000 if os.name == "nt" else 0)
    if r.returncode != 0 or len(r.stdout) < SYNC_RATE * 4:
        raise RuntimeError("no sound found in " + os.path.basename(path))
    x = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    win = 1024
    n = (len(x) - win) // SYNC_HOP
    if n < 100:
        raise RuntimeError("too short")
    hann = np.hanning(win).astype(np.float32)
    lo, hi = int(60 * win / SYNC_RATE), int(2500 * win / SYNC_RATE)  # 60 Hz – 2.5 kHz
    flux = np.zeros(n, dtype=np.float32)
    prev = None
    for a in range(0, n, 4000):
        b = min(n, a + 4000)
        idx = np.arange(a, b)[:, None] * SYNC_HOP + np.arange(win)[None, :]
        mag = np.log1p(40.0 * np.abs(np.fft.rfft(x[idx] * hann, axis=1))[:, lo:hi])
        d = np.diff(mag, axis=0, prepend=(mag[:1] if prev is None else prev[None, :]))
        flux[a:b] = np.maximum(d, 0).sum(axis=1)
        prev = mag[-1]
    # a calm baseline: subtract a slow average, keep what stands out
    k = 100
    base = np.convolve(flux, np.ones(k, dtype=np.float32) / k, mode="same")
    f = flux - base
    f = np.maximum(f, 0)
    s = f.std()
    return f / s if s > 0 else f


def sync_audio(stash, args):
    try:
        import numpy as np
    except ImportError:
        raise RuntimeError("numpy is needed for this (pip install numpy)")
    ffmpeg = find_ffmpeg(stash)
    va = scene_video(stash, str(args.get("scene_a") or ""))
    vb = scene_video(stash, str(args.get("scene_b") or ""))
    if not (os.path.isfile(va) and os.path.isfile(vb)):
        raise ValueError("a video file can't be reached from here")
    a = sync_envelope(ffmpeg, va, 900)
    b = sync_envelope(ffmpeg, vb, 3600)
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    fa, fb = np.fft.rfft(a, n), np.fft.rfft(b, n)
    corr = np.fft.irfft(fb * np.conj(fa), n)  # corr[l] = sum a[t] * b[t + l]
    lags = np.concatenate([np.arange(0, len(b)), np.arange(-len(a) + 1, 0)])
    vals = np.concatenate([corr[0:len(b)], corr[n - len(a) + 1:n]])
    # an overlap shorter than 10 s says nothing
    ov = np.minimum(len(a), len(b) - lags)
    ov = np.where(lags < 0, np.minimum(len(b), len(a) + lags), ov)
    vals = np.where(ov >= 1000, vals, -1e9)
    i = int(np.argmax(vals))
    best = float(vals[i])
    ok = vals > -1e8
    mean, sd = float(vals[ok].mean()), float(vals[ok].std() or 1.0)
    # the next best peak far away from the best one
    far = ok & (np.abs(lags - lags[i]) > 100)
    second = float(vals[far].max()) if far.any() else mean
    score = (best - mean) / sd
    ratio = best / second if second > 0 else 99.0
    return {"offset": round(-float(lags[i]) * SYNC_HOP / SYNC_RATE, 3), "score": round(score, 1), "ratio": round(ratio, 2), "sure": bool(score > 9 and ratio > 1.25)}


def reveal(stash, args):
    """Show a file in the computer's file manager (Explorer / Finder). Only files inside a library folder of Stash, and only
    on the machine Stash runs on – otherwise {"opened": false, "why": ...} and the page copies the path instead."""
    path = str(args.get("path") or "")
    if not path:
        raise ValueError("no path")
    roots, _ = libraries(stash)
    if not inside(path, roots):
        return {"opened": False, "why": "outside"}
    if not os.path.exists(path):
        return {"opened": False, "why": "missing"}
    real = os.path.realpath(path)
    if os.name == "nt":
        # as one raw command line: /select,"<path>" – a list would quote the whole "/select,<path>" argument, which Explorer
        # misreads for paths with spaces or commas (it then opens some default folder instead of selecting the file)
        subprocess.Popen('explorer /select,"' + os.path.normpath(real) + '"', creationflags=0x08000000, close_fds=True)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", real], close_fds=True)
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(real)], close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"opened": True}


def cover_of(images):
    """The address of the cover picture of a stash-box scene: the widest landscape one, otherwise the first."""
    best, best_w = "", -1
    for im in images or []:
        u = str((im or {}).get("url") or "")
        if not re.match(r"^https?://", u, re.I):
            continue
        w, h = int(im.get("width") or 0), int(im.get("height") or 0)
        k = (1 if w >= h else 0) * 100000 + min(w, 1600)
        if k > best_w:
            best, best_w = u, k
    return best


def box_image_one(endpoint, url):
    """One cover picture of a stash-box as a data address (checks are done by the callers)."""
    import base64
    from urllib.parse import urlparse
    eh, uh = (urlparse(endpoint).hostname or "").lower(), (urlparse(url).hostname or "").lower()
    us = urlparse(url).scheme.lower()
    dom = lambda h: ".".join(h.split(".")[-2:])
    if us not in ("http", "https") or not uh or not (uh == eh or (us == "https" and dom(uh) == dom(eh) and not re.match(r"^[\d.]+$", uh))):
        raise ValueError("picture not allowed")
    req = urllib.request.Request(url, headers={"User-Agent": "Stash-UI-plugin", "Accept": "image/*"})
    with urllib.request.urlopen(req, timeout=20) as res:
        ctype = (res.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if not ctype.startswith("image/"):
            raise ValueError("not a picture")
        raw = res.read(3 * 1024 * 1024 + 1)
    if len(raw) > 3 * 1024 * 1024:
        raise ValueError("picture too big")
    return "data:" + ctype + ";base64," + base64.b64encode(raw).decode()


def box_image_check(stash, endpoint):
    endpoint = str(endpoint or "").strip().rstrip("/")
    boxes = stash.gql("query { configuration { general { stashBoxes { endpoint } } } }")["configuration"]["general"].get("stashBoxes") or []
    if not any(str(b.get("endpoint") or "").rstrip("/") == endpoint for b in boxes):
        raise ValueError("This stash-box isn't set up in Stash")
    return endpoint


def box_image(stash, args):
    """One cover picture of a stash-box as a data address (Stash's page policy blocks foreign pictures, so the plugin fetches it).
    Only from a stash-box set up in Stash, and only from its own host (or a host of the same domain, https) – never an address
    of the page's choosing."""
    endpoint = box_image_check(stash, args.get("endpoint"))
    return {"data": box_image_one(endpoint, str(args.get("url") or "").strip())}


def box_images(stash, args):
    """Up to 16 cover pictures in one call, fetched side by side: {"data": {url: data address or ""}}."""
    from concurrent.futures import ThreadPoolExecutor
    endpoint = box_image_check(stash, args.get("endpoint"))
    urls = [str(u).strip() for u in (args.get("urls") or [])][:16]

    def one(u):
        try:
            return box_image_one(endpoint, u)
        except Exception:  # noqa: BLE001
            return ""
    with ThreadPoolExecutor(max_workers=8) as ex:
        return {"data": dict(zip(urls, ex.map(one, urls)))}


def box_scenes(stash, args):
    """One page (up to 100) of the scenes a stash-box (StashDB …) lists for a performer – the performer page uses it to
    show which scenes the library is missing. The box is asked with the API key Stash has for it (read here, never sent
    to the page) and only if it is one of the stash-boxes set up in Stash."""
    endpoint = str(args.get("endpoint") or "").strip()
    pid = str(args.get("performer") or "").strip()
    page = max(1, int(args.get("page") or 1))
    text = str(args.get("text") or "").strip()[:200]  # Discover: a free text search instead of one performer's scenes
    sort = str(args.get("sort") or "DATE").upper()
    if sort not in ("DATE", "TRENDING", "TITLE", "CREATED_AT", "UPDATED_AT"):
        sort = "DATE"
    direction = "ASC" if str(args.get("direction") or "").upper() == "ASC" else "DESC"
    per_page = max(5, min(100, int(args.get("per_page") or 100)))
    if not endpoint or not (pid or text or args.get("browse")):
        raise ValueError("endpoint and performer (or a search text) needed")
    boxes = stash.gql("query { configuration { general { stashBoxes { endpoint name api_key } } } }")["configuration"]["general"].get("stashBoxes") or []
    box = next((b for b in boxes if str(b.get("endpoint") or "").rstrip("/") == endpoint.rstrip("/")), None)
    if not box:
        raise ValueError("This stash-box isn't set up in Stash (Settings → Metadata Providers)")
    if not re.match(r"^https?://", endpoint, re.I):
        raise ValueError("bad stash-box address")
    headers = {"Content-Type": "application/json", "User-Agent": "Stash-UI-plugin"}
    if box.get("api_key"):
        headers["ApiKey"] = str(box["api_key"])
    # the field names differ a little between stash-box versions: try the likely ones
    base_f = [
        "id title release_date duration studio { id name } performers { performer { id name } }",
        "id title date duration studio { id name } performers { performer { id name } }",
        "id title release_date studio { id name } performers { performer { id name } }",
    ]
    # first with the cover pictures, details and tags, then only the pictures, then without in case this stash-box doesn't know them
    extras = [" images { url width height } details tags { name }", " images { url width height }", ""]
    fields = [f + ex for ex in extras for f in base_f]
    since = str(args.get("since") or "").strip()  # Discover: only scenes released after this day (YYYY-MM-DD)
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", since):
        since = ""
    only_perf = [str(x)[:64] for x in (args.get("performers_in") or []) if x][:400]  # Discover: scenes with one of these (box) performers
    plain = bool(args.get("_plain"))
    last = None
    empty = None
    for fl in fields:
        for variant in ("sorted", "plain", "minimal"):
            ordered = variant == "sorted"
            inp = {"page": page} if variant == "minimal" else {"page": page, "per_page": per_page}
            if pid:
                inp["performers"] = {"value": [pid], "modifier": "INCLUDES"}
            elif only_perf and not plain:
                inp["performers"] = {"value": only_perf, "modifier": "INCLUDES"}
            if since and not plain:
                inp["date"] = {"value": since, "modifier": "GREATER_THAN"}
            if text:
                inp["title" if args.get("_title") else "text"] = text
            if ordered:
                inp.update({"sort": sort, "direction": direction})
            body = json.dumps({"query": "query($i: SceneQueryInput!) { queryScenes(input: $i) { count scenes { " + fl + " } } }", "variables": {"i": inp}}).encode()
            req = urllib.request.Request(endpoint, body, headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=40) as res:
                    d = json.load(res)
            except urllib.error.HTTPError as e:
                try:
                    d = json.load(e)
                except Exception:  # noqa: BLE001
                    raise RuntimeError(f"{box.get('name') or endpoint}: HTTP {e.code}")
            if d.get("errors"):
                last = "; ".join(str(x.get("message", "")) for x in d["errors"])
                if (since or only_perf) and not plain and re.search(r"SceneQueryInput|DateCriterion|\"date\"", last):
                    return box_scenes(stash, dict(args, _plain=True))  # this box doesn't know the date / performer criteria
                continue  # another field set / without the sort
            q = (d.get("data") or {}).get("queryScenes") or {}
            out = []
            for x in q.get("scenes") or []:
                out.append({
                    "id": x.get("id"),
                    "title": x.get("title") or "",
                    "date": x.get("release_date") or x.get("date") or "",
                    "duration": x.get("duration") or 0,
                    "studio": (x.get("studio") or {}).get("name") or "",
                    "performers": [((q2 or {}).get("performer") or {}).get("name") or "" for q2 in (x.get("performers") or [])],
                    "performer_ids": [str(((q2 or {}).get("performer") or {}).get("id") or "") for q2 in (x.get("performers") or [])],
                    "tags": [str((g or {}).get("name") or "") for g in (x.get("tags") or []) if g][:30],
                    "details": str(x.get("details") or "")[:3000],
                    "image": cover_of(x.get("images")),
                })
            res = {"count": q.get("count") or 0, "page": page, "scenes": out, "name": box.get("name") or "", "client": plain and bool(since or only_perf)}
            if not out and res["count"] and variant != "minimal":
                # says it has scenes but sent none: maybe the sort or the page size is the problem – try plainer questions
                res["debug"] = json.dumps(d, ensure_ascii=False)[:400]
                empty = res
                continue
            if not out and res["count"]:
                res["debug"] = json.dumps(d, ensure_ascii=False)[:400]
            return res
        if empty:
            return empty  # answered without an error, just with no scenes: other field names won't change that
    if text and not args.get("_title"):
        return box_scenes(stash, dict(args, _title=True))  # a stash-box without the `text` search: try the title filter
    if (since or only_perf) and not plain:
        return box_scenes(stash, dict(args, _plain=True))  # a stash-box without the date / performer criteria: the page filters instead
    raise RuntimeError(f"{box.get('name') or endpoint}: {last or 'no answer'}")


# ── Discover overview (the page is the stashDiscover plugin by ufousox007, used with the author's permission) ──

def box_of(stash, endpoint):
    boxes = stash.gql("query { configuration { general { stashBoxes { endpoint name api_key } } } }")["configuration"]["general"].get("stashBoxes") or []
    box = next((b for b in boxes if str(b.get("endpoint") or "").rstrip("/") == str(endpoint or "").rstrip("/")), None)
    if not box:
        raise ValueError("This stash-box isn't set up in Stash (Settings → Metadata Providers)")
    if not re.match(r"^https?://", str(endpoint), re.I):
        raise ValueError("bad stash-box address")
    return box


def box_gql(stash, args):
    """One GraphQL question to a stash-box set up in Stash, with the API key Stash has for it (the key stays here). Questions only –
    nothing that changes data on the box. The answer says what went wrong in "kind" (the page shows it): timeout / network / auth /
    blocked / parse; GraphQL errors come back as "errors"."""
    box = box_of(stash, args.get("endpoint"))
    query = str(args.get("query") or "")
    if not re.match(r"^\s*(query\b|\{)", query) or re.search(r"\b(mutation|subscription)\b", query):
        raise ValueError("only questions are allowed")
    payload = {"query": query}
    if isinstance(args.get("variables"), dict) and args["variables"]:
        payload["variables"] = args["variables"]
    headers = {"Content-Type": "application/json", "User-Agent": "Stash-UI-plugin"}
    if box.get("api_key"):
        headers["ApiKey"] = str(box["api_key"])
    timeout = max(5, min(60, int(args.get("timeout") or 15)))
    req = urllib.request.Request(str(args["endpoint"]), json.dumps(payload).encode(), headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read()
    except urllib.error.HTTPError as e:
        return {"kind": "auth" if e.code in (401, 403) else "blocked", "message": f"HTTP {e.code}"}
    except (socket.timeout, TimeoutError):
        return {"kind": "timeout", "message": "timeout"}
    except urllib.error.URLError as e:
        return {"kind": "timeout" if isinstance(e.reason, (socket.timeout, TimeoutError)) else "network", "message": str(e.reason)}
    try:
        d = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return {"kind": "parse", "message": "non-JSON response"}
    if d.get("errors"):
        return {"errors": d["errors"]}
    return {"data": d.get("data")}


def box_rest(stash, args):
    """GET on the REST API of ThePornDB, with the key Stash has for that box. Only https://api.theporndb.net, only when the box is
    set up in Stash with a theporndb.net address; the page gives the path (no host)."""
    box = box_of(stash, args.get("endpoint"))
    if not re.search(r"(^|//|\.)theporndb\.net(/|$)", str(box.get("endpoint") or ""), re.I):
        raise ValueError("this is not a ThePornDB box")
    path = str(args.get("path") or "")
    if not re.match(r"^/[A-Za-z0-9_\-./?=&%,\[\]+:]*$", path) or path.startswith("//"):
        raise ValueError("bad path")
    headers = {"Accept": "application/json", "User-Agent": "Stash-UI-plugin"}
    if box.get("api_key"):
        headers["Authorization"] = "Bearer " + str(box["api_key"])
    timeout = max(5, min(60, int(args.get("timeout") or 15)))
    req = urllib.request.Request("https://api.theporndb.net" + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read()
    except urllib.error.HTTPError as e:
        return {"kind": "auth" if e.code in (401, 403) else "blocked", "message": f"HTTP {e.code}"}
    except (socket.timeout, TimeoutError):
        return {"kind": "timeout", "message": "timeout"}
    except urllib.error.URLError as e:
        return {"kind": "timeout" if isinstance(e.reason, (socket.timeout, TimeoutError)) else "network", "message": str(e.reason)}
    try:
        return {"data": json.loads(raw.decode("utf-8", "replace"))}
    except ValueError:
        return {"kind": "parse", "message": "non-JSON response"}


def ssd_settings(stash):
    plugins = stash.gql("query { configuration { plugins } }")["configuration"].get("plugins") or {}
    raw = (plugins.get("stashui") or {}).get("ssd")
    try:
        return (json.loads(raw) if isinstance(raw, str) else raw) or {}
    except ValueError:
        return {}


def ssd_http(url, method="GET", data=None, headers=None, timeout=30):
    h = dict(headers or {})
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        h.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace"), resp.headers
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode("utf-8", errors="replace") if e.fp else ""), (e.headers or {})
    except Exception as e:  # noqa: BLE001
        return 0, str(e), {}


def ssd_human_size(n):
    if not n or n <= 0:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def ssd_torznab(xml_text):
    import xml.etree.ElementTree as ET
    results = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return results
    ns = {"torznab": "http://torznab.com/schemas/2015/feed"}
    channel = root.find("channel")
    if channel is None:
        return results
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        guid = (item.findtext("guid") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        try:
            size = int(item.findtext("size") or "0")
        except ValueError:
            size = 0
        seeders = leechers = None
        magnet = tracker = None
        for attr in item.findall("torznab:attr", ns):
            name, value = attr.get("name", ""), attr.get("value", "")
            if name == "seeders":
                try:
                    seeders = int(value)
                except ValueError:
                    pass
            elif name == "peers":
                try:
                    leechers = int(value)
                except ValueError:
                    pass
            elif name == "magneturl":
                magnet = value
            elif name == "tracker":
                tracker = value
        if not magnet and link.startswith("magnet:"):
            magnet = link
        if not magnet and guid.startswith("magnet:"):
            magnet = guid
        if not title and magnet:
            m = re.search(r"dn=([^&]+)", magnet)
            if m:
                title = urllib.parse.unquote_plus(m.group(1))
        results.append({"title": title, "magnet": magnet or "", "link": link or guid, "size": size, "size_human": ssd_human_size(size),
                        "seeders": seeders if seeders is not None else -1, "leechers": leechers if leechers is not None else -1,
                        "pub_date": pub_date, "tracker": tracker or ""})
    results.sort(key=lambda r: (bool(r["magnet"]), r["seeders"]), reverse=True)  # magnets first, then by seeders
    return results


SSD_SEARCH_LIMIT = 200  # stashDiscover 2.5.5: the answer is no longer squeezed through the Stash log, so more fit


def ssd_search(stash, args):
    """Jackett (Torznab) search for a scene – the "Search Resources" button of the Discover scene window."""
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError("No search query provided.")
    cfg = ssd_settings(stash)
    url = str(cfg.get("jackettUrl") or "").strip().rstrip("/")
    key = str(cfg.get("jackettApiKey") or "").strip()
    if not url or not key:
        raise ValueError("Jackett not configured. Set the Jackett URL and API key in Discover → Settings.")
    if not re.match(r"^https?://", url, re.I):
        raise ValueError("The Jackett URL has to start with http:// or https://")
    if not url.endswith("/torznab"):
        url = url + "/torznab" if "/api/v2." in url else url + "/api/v2.0/indexers/all/results/torznab"
    full = f"{url}{'&' if '?' in url else '?'}apikey={urllib.parse.quote(key)}&q={urllib.parse.quote(query)}"
    try:  # a search over many indexers can take a while: 120 s unless set otherwise (10 to 600)
        wait = max(10, min(600, int(str(cfg.get("jackettTimeout") or "120").strip())))
    except ValueError:
        wait = 120
    status, body, _ = ssd_http(full, timeout=wait)
    if status != 200:
        raise RuntimeError(f"Jackett request failed (HTTP {status}): {body[:200]}")
    results = ssd_torznab(body)
    shown = results[:SSD_SEARCH_LIMIT]
    # count is everything Jackett found, "shown" what is sent on – the page says so when the list is cut
    return {"mode": "search", "query": query, "count": len(results), "shown": len(shown), "truncated": len(results) > SSD_SEARCH_LIMIT, "results": shown}


def ssd_session_cookie(headers):
    """qBittorrent up to 5.1 sends SID=..., 5.2 and later QBT_SID_<port>=... (maybe in several Set-Cookie lines)."""
    lines = []
    try:
        lines = headers.get_all("Set-Cookie") or []
    except AttributeError:
        lines = [v for k, v in (headers or {}).items() if k.lower() == "set-cookie"]
    pairs = []
    for line in lines:
        for part in re.split(r",\s*(?=[^=;,\s]+=)", line or ""):
            m = re.match(r"\s*([^=;,\s]+)=([^;,]*)", part)
            if m and "SID" in m.group(1).upper():
                pairs.append(f"{m.group(1)}={m.group(2)}")
    return "; ".join(pairs)


def ssd_push(stash, args):
    """Hand a magnet link to qBittorrent."""
    magnet = str(args.get("magnet") or "").strip()
    if not magnet.startswith("magnet:"):
        raise ValueError("No magnet link provided.")
    cfg = ssd_settings(stash)
    base = str(cfg.get("downloaderUrl") or "").strip().rstrip("/")
    if not base:
        raise ValueError("Downloader URL not configured.")
    if not re.match(r"^https?://", base, re.I):
        raise ValueError("The downloader URL has to start with http:// or https://")
    status, body, headers = ssd_http(base + "/api/v2/auth/login", "POST", {"username": str(cfg.get("downloaderUsername") or ""), "password": str(cfg.get("downloaderPassword") or "")}, timeout=15)
    if not (status == 204 or (status == 200 and body.strip() == "Ok.")):  # 5.3 answers 204 without a body
        raise RuntimeError(f"qBittorrent login failed (HTTP {status}): {body[:100]}")
    cookie = ssd_session_cookie(headers)
    if not cookie:
        raise RuntimeError("qBittorrent login did not return a session cookie.")
    status, body, _ = ssd_http(base + "/api/v2/torrents/add", "POST", {"urls": magnet}, {"Cookie": cookie}, timeout=15)
    if status != 200:
        raise RuntimeError(f"qBittorrent add failed (HTTP {status}): {body[:200]}")
    return {"mode": "push_download", "ok": True}


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--cutjob":
        return cut_job(sys.argv[2])
    if len(sys.argv) > 2 and sys.argv[1] == "--editjob":
        return edit_job(sys.argv[2])
    if len(sys.argv) > 2 and sys.argv[1] == "--gifjob":
        return gif_job(sys.argv[2])
    if len(sys.argv) > 2 and sys.argv[1] == "--vedit":
        return vedit_job(sys.argv[2])
    data = json.loads(sys.stdin.read() or "{}")
    args = data.get("args") or {}
    mode = str(args.get("mode") or "")
    try:
        if mode == "funscript_overview":
            out = funscript_overview(Stash(data.get("server_connection")), args)
        elif mode == "funscript_save_variant":
            out = funscript_save_variant(Stash(data.get("server_connection")), args)
        elif mode == "funscript_dupes":
            out = funscript_dupes(Stash(data.get("server_connection")), args)
        elif mode == "funscript_dupe_aside":
            out = funscript_dupe_aside(Stash(data.get("server_connection")), args)
        elif mode == "funscript_dupe_restore":
            out = funscript_dupe_restore(Stash(data.get("server_connection")), args)
        elif mode == "funscript_variants":
            out = funscript_variants(Stash(data.get("server_connection")), args)
        elif mode == "funscript_read":
            out = funscript_read(Stash(data.get("server_connection")), args)
        elif mode == "funscript_scan":
            out = funscript_scan(Stash(data.get("server_connection")), args)
        elif mode == "funscript_list":
            out = funscript_list(Stash(data.get("server_connection")), args)
        elif mode == "funscript_save":
            out = funscript_save(Stash(data.get("server_connection")), args)
        elif mode == "funscript_remove":
            out = funscript_remove(Stash(data.get("server_connection")), args)
        elif mode == "clip_cut":
            out = clip_cut(Stash(data.get("server_connection")), args)
        elif mode == "clip_status":
            out = clip_status(None, args)
        elif mode == "sync_audio":
            out = sync_audio(Stash(data.get("server_connection")), args)
        elif mode == "reveal":
            out = reveal(Stash(data.get("server_connection")), args)
        elif mode == "box_image":
            out = box_image(Stash(data.get("server_connection")), args)
        elif mode == "box_images":
            out = box_images(Stash(data.get("server_connection")), args)
        elif mode == "box_scenes":
            out = box_scenes(Stash(data.get("server_connection")), args)
        elif mode == "clips_dir_check":
            out = clips_dir_check(Stash(data.get("server_connection")), args)
        elif mode == "gif_make":
            out = gif_make(Stash(data.get("server_connection")), args)
        elif mode == "edit_render":
            out = edit_render(Stash(data.get("server_connection")), args)
        elif mode == "video_edit":
            out = video_edit(Stash(data.get("server_connection")), args)
        elif mode == "video_edit_swap":
            out = video_edit_swap(Stash(data.get("server_connection")), args)
        elif mode == "video_edit_drop":
            out = video_edit_drop(None, args)
        elif mode == "box_gql":
            out = box_gql(Stash(data.get("server_connection")), args)
        elif mode == "box_rest":
            out = box_rest(Stash(data.get("server_connection")), args)
        elif mode == "ssd_search":
            out = ssd_search(Stash(data.get("server_connection")), args)
        elif mode == "ssd_push":
            out = ssd_push(Stash(data.get("server_connection")), args)
        elif mode == "phone_status":
            out = phone_status(Stash(data.get("server_connection")), args)
        elif mode == "phone_start":
            out = phone_start(Stash(data.get("server_connection")), args)
        elif mode == "phone_stop":
            out = phone_stop(Stash(data.get("server_connection")), args)
        elif mode == "share_status":
            out = share_status(Stash(data.get("server_connection")), args, data.get("server_connection"))
        elif mode == "watch_new":
            out = watch_new(Stash(data.get("server_connection")), args, data.get("server_connection"))
        elif mode == "share_net":
            out = share_net(Stash(data.get("server_connection")), args, data.get("server_connection"))
        elif mode == "share_stop":
            out = share_stop(Stash(data.get("server_connection")), args, data.get("server_connection"))
        elif mode == "share_accept":
            out = share_accept(Stash(data.get("server_connection")), args, data.get("server_connection"))
        else:
            raise ValueError(f"unknown mode: {mode or '(empty)'}")
    except Exception as e:
        print(f"\x01e\x02[Stash UI] {e}", file=sys.stderr, flush=True)
        print(json.dumps({"error": str(e)}))
        return
    print(json.dumps({"output": out}))


if __name__ == "__main__":
    main()
