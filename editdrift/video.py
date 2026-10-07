"""Demo videos.

  compare: two models side by side, one edit per beat, live drift counters.
  grid:    every model in a results folder at once, one tile per model.
Square 1080x1080, H.264. Needs ffmpeg on PATH.
"""
from __future__ import annotations
import glob, json, os, re, shutil, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont
from .cli import bench_paths, run_steps
from . import metric

A = os.path.join(os.path.dirname(__file__), "assets")
F = lambda w, s: ImageFont.truetype(os.path.join(A, w + ".ttf"), s)
CREAM, INK, GRAY, WHITE = (247, 245, 241), (10, 11, 15), (138, 133, 120), (255, 255, 255)
BAD, GOOD, AMBER, BAR_BG = (229, 72, 77), (40, 160, 100), (176, 92, 0), (90, 90, 90)
SZ, FPS = 1080, 30


def _tabw(d, txt, font):
    dw = max(d.textlength(c, font=font) for c in "0123456789")
    return sum(dw if c.isdigit() else d.textlength(c, font=font) for c in txt)


def _tab(d, x, y, txt, font, fill):
    dw = max(d.textlength(c, font=font) for c in "0123456789")
    for c in txt:
        w = dw if c.isdigit() else d.textlength(c, font=font)
        d.text((x + (w - d.textlength(c, font=font)) / 2, y), c, font=font, fill=fill); x += w


def _cover(path, w, h, cache):
    k = (path, w, h)
    if k not in cache:
        im = Image.open(path).convert("RGB"); r = max(w / im.width, h / im.height)
        im = im.resize((round(im.width * r), round(im.height * r)), Image.LANCZOS)
        ox, oy = (im.width - w) // 2, round((im.height - h) * 0.3)
        cache[k] = im.crop((ox, oy, ox + w, oy + h))
    return cache[k]


def _mask(w, h, r):
    m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], r, fill=255); return m


def _shade(w, gh=210):
    g = Image.new("L", (1, gh))
    for y in range(gh):
        g.putpixel((0, y), int(235 * min(1, y / (gh * .55)) ** 1.3))
    return g.resize((w, gh))


def _series(benchmark, run_dir):
    orig, steps, rois = bench_paths(benchmark)
    sp = os.path.join(run_dir, "scores.json")
    sc = json.load(open(sp))["steps"] if os.path.exists(sp) else metric.chain_scores(orig, run_steps(run_dir, len(steps)), rois)
    files, last = [orig], orig
    for s in sc:
        last = s["file"] or last; files.append(last)
    return files, [0.0] + [s["drift"] for s in sc], [False] + [s["blocked"] for s in sc]


def _meta(run_dir):
    p = os.path.join(run_dir, "meta.json")
    return json.load(open(p)) if os.path.exists(p) else {"name": os.path.basename(run_dir.rstrip("/"))}


def _topbar(d, k, total, label, flash, M=16, y0=14, y1=100):
    d.rounded_rectangle([M, y0, SZ - M, y1], 22, fill=(234, 231, 224), outline=INK, width=3)
    sm, big = F("Inter-Bold", 17), F("InterDisplay-Black", 44)
    d.text((M + 26, y0 + 14), "EDIT", font=sm, fill=AMBER)
    _tab(d, M + 24, y0 + 32, f"{k:02d}", big, INK)
    d.text((M + 24 + _tabw(d, "00", big) + 6, y0 + 50), f"/ {total}", font=F("Inter-SemiBold", 20), fill=GRAY)
    d.line([(M + 150, y0 + 18), (M + 150, y1 - 18)], fill=(200, 195, 185), width=2)
    d.text((M + 172, y0 + 14), "WHAT IS THE CHANGE?", font=sm, fill=AMBER)
    d.text((M + 172, y0 + 36), label, font=F("Inter-Bold", 34), fill=INK)
    cx, cy = SZ - M - 50, (y0 + y1) // 2
    d.ellipse([cx - 24, cy - 24, cx + 24, cy + 24], fill=(245, 165, 36) if flash else INK)
    d.polygon([(cx - 7, cy - 10), (cx - 7, cy + 10), (cx + 10, cy)], fill=INK if flash else WHITE)


def _footer(im, logo):
    d = ImageDraw.Draw(im); d.rectangle([0, 944, SZ, SZ], fill=INK)
    if logo:
        lg = Image.open(logo).convert("RGBA"); lg = lg.resize((int(lg.width * 62 / lg.height), 62), Image.LANCZOS)
        w = Image.new("RGBA", lg.size, (255, 255, 255, 255)); w.putalpha(lg.getchannel("A"))
        im.paste(w, ((SZ - w.width) // 2, 944 + (SZ - 944 - w.height) // 2), w)
    else:
        t = "edit-drift benchmark"; f = F("Inter-Bold", 30); tw = d.textlength(t, font=f)
        d.text(((SZ - tw) / 2, 944 + 50), t, font=f, fill=WHITE)


def _tile(im, x, y, w, h, path, name, dv, col, cache, nf=66, pill=32, refused=False):
    pn = _cover(path, w, h, cache).copy(); gh = min(210, h // 3)
    pn.paste(Image.new("RGB", (w, gh)), (0, h - gh), _shade(w, gh))
    im.paste(pn, (x, y), _mask(w, h, 22 if w > 300 else 14)); d = ImageDraw.Draw(im)
    hf = F("InterDisplay-Black", pill); hw = d.textlength(name, font=hf); pad = pill // 2
    d.rounded_rectangle([x + 12, y + 12, x + 12 + hw + 2 * pad, y + 12 + pill + 20], 14, fill=col)
    d.text((x + 12 + pad, y + 16), name, font=hf, fill=WHITE)
    yb = y + h; nfnt = F("InterDisplay-Black", nf); num = f"{dv:.1f}"
    _tab(d, x + w - 16 - _tabw(d, num, nfnt), yb - nf * 1.48, num, nfnt, WHITE)
    lab = "REFUSED · DRIFT" if refused else "DRIFT"
    d.text((x + 16, yb - nf * 1.38), lab, font=F("Inter-Bold", max(14, nf // 3)), fill=(235, 235, 235))
    slot = _tabw(d, "00.0", nfnt); bx0, bx1, by = x + 16, x + w - 16 - slot - 16, yb - nf * 0.8
    d.rounded_rectangle([bx0, by, bx1, by + 10], 5, fill=BAR_BG)
    d.rounded_rectangle([bx0, by, bx0 + max(10, (bx1 - bx0) * min(dv, 40) / 40), by + 10], 5, fill=col)


def _encode(frames_dir, out):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", f"{frames_dir}/%05d.png",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", out], check=True)


def _timeline(n):
    """Yield (k, prev_k, t, frames) beats: 1.5 s on the original, 0.6 s per edit, 2.5 s hold."""
    yield 0, 0, None, 45
    for k in range(1, n + 1):
        for t in range(18):
            yield k, k - 1, t, 1
    yield n, n, None, 75


def compare(benchmark, run_a, run_b, out, logo=None):
    _, steps, _ = bench_paths(benchmark)
    labels = ["The original photo"] + [s.get("label") or s["instruction"].split(". Keep")[0] for s in steps]
    (fa, da, ba), (fb, db, bb) = _series(benchmark, run_a), _series(benchmark, run_b)
    n = min(len(fa), len(fb)) - 1
    na, nb = _meta(run_a)["name"], _meta(run_b)["name"]
    M, PY = 16, 114; PH = 944 - 14 - PY; PW = (SZ - 3 * M) // 2; cache = {}
    tmp = tempfile.mkdtemp(); i = 0
    for k, pk, t, reps in _timeline(n):
        a = 1 if t is None else 1 - (1 - min(1, (t + 1) / 8)) ** 3
        im = Image.new("RGB", (SZ, SZ), CREAM); d = ImageDraw.Draw(im)
        _topbar(d, k, n, labels[k], t is not None and t < 5)
        va, vb = da[pk] + (da[k] - da[pk]) * a, db[pk] + (db[k] - db[pk]) * a
        # colour follows what is on screen: the side with lower drift right now is green
        ca, cb = (GOOD, BAD) if round(va, 1) <= round(vb, 1) else (BAD, GOOD)
        _tile(im, M, PY, PW, PH, fa[k], na, va, ca, cache, refused=ba[k])
        _tile(im, 2 * M + PW, PY, PW, PH, fb[k], nb, vb, cb, cache, refused=bb[k])
        _footer(im, logo)
        for _ in range(reps):
            im.save(f"{tmp}/{i:05d}.png"); i += 1
    _encode(tmp, out); shutil.rmtree(tmp); return out


def grid(benchmark, results_dir, out, logo=None, cols=4):
    _, steps, _ = bench_paths(benchmark)
    labels = ["The original photo"] + [s.get("label") or s["instruction"].split(". Keep")[0] for s in steps]
    runs = [r for r in sorted(glob.glob(os.path.join(results_dir, "*/"))) if glob.glob(r + "step*.*")]
    ser = {r: _series(benchmark, r) for r in runs}
    n = min(len(v[0]) for v in ser.values()) - 1
    runs.sort(key=lambda r: ser[r][1][n])            # best (lowest final drift) first
    rows = (len(runs) + cols - 1) // cols
    M, PY = 10, 114; GW = (SZ - (cols + 1) * M) // cols; GH = (944 - 10 - PY - (rows - 1) * M) // rows
    cache = {}; tmp = tempfile.mkdtemp(); i = 0
    for k, pk, t, reps in _timeline(n):
        a = 1 if t is None else 1 - (1 - min(1, (t + 1) / 8)) ** 3
        im = Image.new("RGB", (SZ, SZ), CREAM); d = ImageDraw.Draw(im)
        _topbar(d, k, n, labels[k], t is not None and t < 5)
        for j, r in enumerate(runs):
            f, dv, bl = ser[r]; x = M + (j % cols) * (GW + M); y = PY + (j // cols) * (GH + M)
            v = dv[pk] + (dv[k] - dv[pk]) * a
            col = GOOD if v < 10 else (AMBER if v < 30 else BAD)
            _tile(im, x, y, GW, GH, f[k], _meta(r)["name"], v, col, cache, nf=34, pill=17, refused=bl[k])
        _footer(im, logo)
        for _ in range(reps):
            im.save(f"{tmp}/{i:05d}.png"); i += 1
    _encode(tmp, out); shutil.rmtree(tmp); return out
