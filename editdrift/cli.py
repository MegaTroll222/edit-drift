"""editdrift command line.

  editdrift steps   <benchmark>                      print the edit chain to run
  editdrift mask    <benchmark> <step> <image> <out> [--convention alpha|black-edits|white-edits]
  editdrift score   <benchmark> <run_dir>            score a finished (or partial) chain
  editdrift report  <benchmark> <results_dir>        table + charts for every model in results_dir
  editdrift video   <benchmark> <run_a> <run_b> <out.mp4>   side-by-side demo video
  editdrift grid    <benchmark> <results_dir> <out.mp4>     every model at once
"""
from __future__ import annotations
import argparse, glob, json, os, re, sys
from . import metric


def bench_paths(b):
    orig = next(p for p in glob.glob(os.path.join(b, "original.*")))
    return orig, json.load(open(os.path.join(b, "steps.json"))), json.load(open(os.path.join(b, "rois.json")))


def run_steps(run_dir, n):
    files = {int(re.search(r"step(\d+)", p).group(1)): p for p in glob.glob(os.path.join(run_dir, "step*.*"))
             if re.search(r"step(\d+)\.(png|jpe?g|webp)$", p)}
    last = max(files) if files else 0
    blocked = set(json.load(open(os.path.join(run_dir, "blocked.json")))) if os.path.exists(os.path.join(run_dir, "blocked.json")) else set()
    upto = max([last] + list(blocked))
    return [(i, files.get(i)) for i in range(1, min(n, upto) + 1)]


def cmd_steps(a):
    _, steps, _ = bench_paths(a.benchmark)
    for s in steps:
        print(f"{s['step']:02d}  {s['instruction']}")


def cmd_mask(a):
    from PIL import Image, ImageDraw
    _, steps, _ = bench_paths(a.benchmark)
    s = next(x for x in steps if x["step"] == a.step)
    im = Image.open(a.image); W, H = im.size; pad = a.pad
    edit = Image.new("L", (W, H), 0); d = ImageDraw.Draw(edit)
    for t, l, b, r in s["edit_boxes"]:
        d.rectangle([max(0, (l - pad) * W / 1000), max(0, (t - pad) * H / 1000), min(W, (r + pad) * W / 1000), min(H, (b + pad) * H / 1000)], fill=255)
    if a.convention == "alpha":
        m = Image.new("RGBA", (W, H), (0, 0, 0, 255)); m.putalpha(Image.eval(edit, lambda v: 255 - v))
    elif a.convention == "black-edits":
        m = Image.eval(edit, lambda v: 255 - v).convert("RGB")
    else:
        m = edit.convert("RGB")
    m.save(a.out); print(a.out)


def cmd_score(a):
    orig, steps, rois = bench_paths(a.benchmark)
    sc = metric.chain_scores(orig, run_steps(a.run_dir, len(steps)), rois, align=not a.no_align)
    out = {"summary": metric.summarize(sc), "steps": sc}
    json.dump(out, open(os.path.join(a.run_dir, "scores.json"), "w"), indent=1)
    print(json.dumps(out["summary"], indent=1))


def cmd_report(a):
    from . import report
    report.build(a.benchmark, a.results_dir, a.out)


def cmd_video(a):
    from . import video
    print(video.compare(a.benchmark, a.run_a, a.run_b, a.out, a.logo))


def cmd_grid(a):
    from . import video
    print(video.grid(a.benchmark, a.results_dir, a.out, a.logo, a.cols))


def main(argv=None):
    p = argparse.ArgumentParser(prog="editdrift")
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("steps"); s.add_argument("benchmark"); s.set_defaults(f=cmd_steps)
    s = sp.add_parser("mask"); s.add_argument("benchmark"); s.add_argument("step", type=int); s.add_argument("image"); s.add_argument("out")
    s.add_argument("--convention", default="alpha", choices=["alpha", "black-edits", "white-edits"]); s.add_argument("--pad", type=int, default=30); s.set_defaults(f=cmd_mask)
    s = sp.add_parser("score"); s.add_argument("benchmark"); s.add_argument("run_dir"); s.add_argument("--no-align", action="store_true"); s.set_defaults(f=cmd_score)
    s = sp.add_parser("report"); s.add_argument("benchmark"); s.add_argument("results_dir"); s.add_argument("--out", default="report"); s.set_defaults(f=cmd_report)
    s = sp.add_parser("video"); s.add_argument("benchmark"); s.add_argument("run_a"); s.add_argument("run_b"); s.add_argument("out"); s.add_argument("--logo"); s.set_defaults(f=cmd_video)
    s = sp.add_parser("grid"); s.add_argument("benchmark"); s.add_argument("results_dir"); s.add_argument("out"); s.add_argument("--logo"); s.add_argument("--cols", type=int, default=4); s.set_defaults(f=cmd_grid)
    a = p.parse_args(argv); a.f(a)


if __name__ == "__main__":
    main()
