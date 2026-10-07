"""Drift metric.

drift_n = (1/|R|) * sum_{roi in R} mean_{x,y,c} |I_n(x,y,c) - I_0(x,y,c)|   (8-bit RGB, 0-255)

I_0 is the original image, I_n the output after n chained edits, R a set of control
rectangles that no edit in the chain touches. Every step is scored against I_0, so error
that accumulates across the chain is what gets measured.
"""
from __future__ import annotations
import numpy as np
from PIL import Image

try:
    import cv2
except ImportError:  # registration is optional
    cv2 = None

GATE = 0.04  # max |scale-1|, |shear|, |translation|/size accepted from the registration


def load_rgb(path, size=None):
    im = Image.open(path).convert("RGB")
    if size and im.size != size:
        im = im.resize(size, Image.LANCZOS)
    return np.asarray(im)


def _gate(M, W, H):
    return bool(abs(M[0, 0] - 1) > GATE or abs(M[1, 1] - 1) > GATE or abs(M[0, 1]) > GATE or abs(M[1, 0]) > GATE
                or abs(M[0, 2]) > GATE * W or abs(M[1, 2]) > GATE * H)


def _ecc(g0, g1, scale):
    M = np.eye(2, 3, dtype=np.float32)
    g0s, g1s = cv2.resize(g0, None, fx=scale, fy=scale), cv2.resize(g1, None, fx=scale, fy=scale)
    try:
        _, M = cv2.findTransformECC(g0s, g1s, M, cv2.MOTION_AFFINE,
                                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), None, 5)
    except cv2.error:
        return None
    M[:, 2] /= scale
    return M  # maps ref coords -> img coords (used with WARP_INVERSE_MAP)


def _orb(g0, g1, min_inliers=50):
    orb = cv2.ORB_create(5000)
    k0, d0 = orb.detectAndCompute(g0.astype(np.uint8), None)
    k1, d1 = orb.detectAndCompute(g1.astype(np.uint8), None)
    if d0 is None or d1 is None:
        return None
    mt = sorted(cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d0, d1), key=lambda m: m.distance)[:1500]
    if len(mt) < min_inliers:
        return None
    p0 = np.float32([k0[m.queryIdx].pt for m in mt]); p1 = np.float32([k1[m.trainIdx].pt for m in mt])
    M, inl = cv2.estimateAffinePartial2D(p0, p1, method=cv2.RANSAC, ransacReprojThreshold=2.0)
    if M is None or inl is None or int(inl.sum()) < min_inliers:
        return None
    return M.astype(np.float32)  # ref -> img, same convention as ECC


def register(ref: np.ndarray, img: np.ndarray, scale: float = 0.5):
    """Align img onto ref. Tries ECC (affine), then ORB+RANSAC (similarity); each must pass the sanity
    gate. If neither does, no alignment is applied. Returns (aligned, transform, method) where method is
    'ecc', 'orb' or 'none'. 'none' happens on flat control areas (nothing to lock onto) or on outputs that
    changed so much no transform fits; in both cases the unaligned comparison is the correct one."""
    if cv2 is None:
        return img.astype(float), np.eye(2, 3), "none"
    H, W = ref.shape[:2]
    g0 = cv2.cvtColor(ref, cv2.COLOR_RGB2GRAY).astype(np.float32)
    g1 = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32)
    method, M = "none", np.eye(2, 3, dtype=np.float32)
    for name, fit in (("ecc", lambda: _ecc(g0, g1, scale)), ("orb", lambda: _orb(g0, g1))):
        cand = fit()
        if cand is not None and not _gate(cand, W, H):
            method, M = name, cand
            break
    out = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE)
    return out.astype(float), M, method


def roi_pixels(rois, W, H):
    """rois: list of [x0, y0, x1, y1] as fractions of width/height."""
    return [(int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)) for x0, y0, x1, y1 in rois]


ASPECT_TOL = 0.01  # outputs whose aspect ratio differs from the original by more than 1% are flagged


def drift(original, edited, rois, align=True):
    """Drift of one edited image against the original.

    Every output is brought onto the original's exact pixel grid before comparison: resized to the
    original's width x height (Lanczos), then registered. Returns total drift, per-ROI drift, the
    unaligned score, the registration method and an aspect-ratio flag."""
    ref = load_rgb(original)
    H, W = ref.shape[:2]
    raw_im = Image.open(edited)
    aspect_delta = abs((raw_im.width / raw_im.height) / (W / H) - 1)
    img = load_rgb(edited, (W, H))
    method = "off"
    if align:
        aligned, M, method = register(ref, img)
    else:
        aligned, M = img.astype(float), np.eye(2, 3)
    ref_f, img_f = ref.astype(float), img.astype(float)
    boxes = roi_pixels(rois, W, H)
    per = [float(np.abs(aligned[y0:y1, x0:x1] - ref_f[y0:y1, x0:x1]).mean()) for x0, y0, x1, y1 in boxes]
    raw = float(np.mean([np.abs(img_f[y0:y1, x0:x1] - ref_f[y0:y1, x0:x1]).mean() for x0, y0, x1, y1 in boxes]))
    return {"drift": float(np.mean(per)), "per_roi": per, "drift_unaligned": raw,
            "registration": method, "transform": [[round(float(v), 4) for v in row] for row in M],
            "output_size": list(raw_im.size), "aspect_mismatch": bool(aspect_delta > ASPECT_TOL)}


def chain_scores(original, steps, rois, align=True):
    """steps: list of (step_number, path or None). None = blocked/failed step, carries the last image forward."""
    out, last = [], original
    for n, p in steps:
        blocked = p is None
        cur = last if blocked else p
        r = drift(original, cur, rois, align) if cur != original else {"drift": 0.0, "per_roi": [0.0] * len(rois), "drift_unaligned": 0.0, "registration": "n/a", "transform": None, "output_size": None, "aspect_mismatch": False}
        r.update(step=n, file=None if blocked else p, blocked=blocked)
        out.append(r)
        last = cur
    return out


def summarize(scores):
    d = [s["drift"] for s in scores]
    n = len(d)
    slope = float(np.polyfit(np.arange(1, n + 1), d, 1)[0]) if n > 1 else 0.0
    return {
        "fidelity_score": round(max(0.0, 100.0 - float(np.mean(d))), 1) if d else None,  # higher is better
        "final_drift": round(d[-1], 2) if d else None,
        "mean_drift": round(float(np.mean(d)), 2) if d else None,   # area under the drift curve / steps
        "max_drift": round(float(np.max(d)), 2) if d else None,
        "slope_per_edit": round(slope, 3),
        "steps": n,
        "blocked_steps": sum(1 for s in scores if s["blocked"]),
        "registration": {k: sum(1 for s in scores if s.get("registration") == k) for k in ("ecc", "orb", "none")},
        "aspect_mismatch_steps": sum(1 for s in scores if s.get("aspect_mismatch")),
    }
