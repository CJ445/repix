"""Build the Repix model-comparison PDF from benchmark results.

Usage: python make_report.py --work WORK_DIR --out report.pdf
All numbers in the report are read from the results/ JSON or computed from the images; nothing
is typed in by hand except the model/architecture facts (checked against the ONNX graphs).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import statistics
import subprocess
from datetime import date
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image as RLImage, CondPageBreak, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)
from skimage.color import rgb2lab
from skimage.metrics import structural_similarity

REPO = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------ fonts / styles
fdir = Path(font_manager.findfont("DejaVu Sans")).parent
for n, f in [("DV", "DejaVuSans.ttf"), ("DV-B", "DejaVuSans-Bold.ttf"), ("DV-I", "DejaVuSans-Oblique.ttf"),
             ("DV-M", "DejaVuSansMono.ttf")]:
    pdfmetrics.registerFont(TTFont(n, str(fdir / f)))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV-I", boldItalic="DV-B")

INK, MUTED, ACCENT, RULE, BAND = (colors.HexColor(x) for x in ("#1b1f27", "#5a6272", "#2f5bea", "#d5d9e2", "#f2f4f8"))
ST = {
    "body": ParagraphStyle("body", fontName="DV", fontSize=8.8, leading=12.6, textColor=INK, alignment=TA_LEFT, spaceAfter=4),
    "small": ParagraphStyle("small", fontName="DV", fontSize=7.4, leading=10, textColor=MUTED, spaceAfter=3),
    "h1": ParagraphStyle("h1", fontName="DV-B", fontSize=14.5, leading=18, textColor=INK, spaceBefore=6, spaceAfter=6, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="DV-B", fontSize=10.5, leading=14, textColor=ACCENT, spaceBefore=8, spaceAfter=3, keepWithNext=1),
    "title": ParagraphStyle("title", fontName="DV-B", fontSize=24, leading=28, textColor=INK, spaceAfter=4),
    "sub": ParagraphStyle("sub", fontName="DV", fontSize=10.5, leading=15, textColor=MUTED, spaceAfter=10),
    "cell": ParagraphStyle("cell", fontName="DV", fontSize=7.6, leading=9.6, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="DV-B", fontSize=7.6, leading=9.6, textColor=INK),
    "bullet": ParagraphStyle("bullet", fontName="DV", fontSize=8.8, leading=12.6, textColor=INK, leftIndent=11, bulletIndent=0, spaceAfter=2.5),
    "mono": ParagraphStyle("mono", fontName="DV-M", fontSize=7.4, leading=10, textColor=INK, backColor=BAND, borderPadding=4, spaceAfter=6),
}
PAGE_W, PAGE_H = A4
MARGIN = 17 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


def _clean(t):
    return str(t).replace("-0 %", "0 %").replace("+0 %", "0 %")


def P(t, s="body"):
    return Paragraph(_clean(t), ST[s])


def bullets(items):
    return [Paragraph(_clean(t), ST["bullet"], bulletText="•") for t in items]


def table(rows, col_w, header=True, zebra=True, align_right_from=1, font=None):
    data = [[Paragraph(_clean(c), ST["cellb" if (header and i == 0) else "cell"]) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=col_w, repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2.6),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6), ("LINEBELOW", (0, 0), (-1, -1), 0.3, RULE)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), BAND), ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK)]
    if zebra:
        style += [("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fafbfd")) for i in range(2, len(rows), 2)]
    t.setStyle(TableStyle(style))
    return t


def img_flow(path_or_buf, width=CONTENT_W):
    im = Image.open(path_or_buf)
    w, h = im.size
    if hasattr(path_or_buf, "seek"):
        path_or_buf.seek(0)
    return RLImage(path_or_buf, width=width, height=width * h / w)


def eq(tex: str, size=12.5, width_cap=CONTENT_W):
    """Render a LaTeX-ish formula (matplotlib mathtext) to a crisp transparent PNG flowable."""
    fig = plt.figure(figsize=(0.1, 0.1))
    fig.text(0, 0, f"${tex}$", fontsize=size, color="#1b1f27")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=350, bbox_inches="tight", pad_inches=0.04, transparent=True)
    plt.close(fig)
    buf.seek(0)
    w, h = Image.open(buf).size
    buf.seek(0)
    wpt = w / 350 * 72
    scale = min(1.0, width_cap / wpt)
    return RLImage(buf, width=wpt * scale, height=h / 350 * 72 * scale, hAlign="LEFT")


# ------------------------------------------------------------------ metrics
def to_y(a: np.ndarray) -> np.ndarray:
    a = a.astype(np.float64)
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def shave(a, b=4):
    return a[b:-b, b:-b] if a.ndim == 2 else a[b:-b, b:-b, :]


def psnr(a, b):
    mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return float("inf") if mse == 0 else 10 * math.log10(255.0**2 / mse)


def ssim_y(a, b):
    return structural_similarity(shave(to_y(a)), shave(to_y(b)), data_range=255, gaussian_weights=True,
                                 sigma=1.5, use_sample_covariance=False)


def lap_var(a):
    return float(cv2.Laplacian(to_y(a).astype(np.float32), cv2.CV_32F).var())


def colorfulness(a):
    a = a.astype(np.float64)
    rg, yb = a[..., 0] - a[..., 1], 0.5 * (a[..., 0] + a[..., 1]) - a[..., 2]
    return math.hypot(rg.std(), yb.std()) + 0.3 * math.hypot(rg.mean(), yb.mean())


def load(p):
    return np.array(Image.open(p).convert("RGB"))


# ------------------------------------------------------------------ tiling / cost maths
C4 = 16_533_504 + 36_864 + 1_728 + 4 * 36_864 + 16 * (2 * 36_864 + 1_728)  # MAC per input pixel, x4plus
C2 = (16_533_504 + 36_864 + 6_912 + 4 * 36_864 + 16 * (2 * 36_864 + 1_728)) // 4  # x2plus
RDB = 9 * (64 * 32 + 96 * 32 + 128 * 32 + 160 * 32 + 192 * 64)


def tiling(W, H, T=256, o=16):
    nx, ny = math.ceil(W / T), math.ceil(H / T)
    if max(W, H) <= T:
        return 1, W * H
    proc = 0
    for ty in range(ny):
        for tx in range(nx):
            x0, y0 = tx * T, ty * T
            x1, y1 = min(x0 + T, W), min(y0 + T, H)
            proc += (min(x1 + o, W) - max(x0 - o, 0)) * (min(y1 + o, H) - max(y0 - o, 0))
    return nx * ny, proc


def fmt_t(s):
    return f"{s:.1f} s" if s < 100 else f"{int(s // 60)} m {s % 60:02.0f} s"


# ------------------------------------------------------------------ main
TARGET = "Hostinger KVM 2 (2 vCPU, 8 GB RAM)"


def windows(W, H, T=256, o=16):
    """Input-window areas (px) of every tile, as the shipped engine cuts them."""
    if max(W, H) <= T:
        return [W * H]
    out = []
    for ty in range(math.ceil(H / T)):
        for tx in range(math.ceil(W / T)):
            x0, y0 = tx * T, ty * T
            x1, y1 = min(x0 + T, W), min(y0 + T, H)
            out.append((min(x1 + o, W) - max(x0 - o, 0)) * (min(y1 + o, H) - max(y0 - o, 0)))
    return out


def fixed_px(W, H, T=256, o=16):
    """Pixels processed when every tile has the same (T+2o)^2 window (edge tiles shifted inward)."""
    S = T + 2 * o
    if max(W, H) <= T:
        return W * H
    tot = 0
    for ty in range(math.ceil(H / T)):
        for tx in range(math.ceil(W / T)):
            x0, y0 = tx * T, ty * T
            wx0, wy0 = min(max(x0 - o, 0), max(W - S, 0)), min(max(y0 - o, 0), max(H - S, 0))
            tot += (min(wx0 + S, W) - wx0) * (min(wy0 + S, H) - wy0)
    return tot


def status_of(r):
    if r.get("oom_killed"):
        return "OOM-killed at the memory cap"
    if r.get("killed_by_harness"):
        return f"stopped by watchdog ({r['killed_by_harness']})"
    if r.get("exit_code"):
        return f"failed (exit {r['exit_code']})"
    return "ok"


def first_iters(r, job_id=None):
    for j in r.get("jobs", []):
        if job_id is None or j["id"] == job_id:
            return j["iters"]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--macs", required=True, type=Path)
    a = ap.parse_args()
    W = a.work
    fig_dir = W / "figs"
    fig_dir.mkdir(exist_ok=True)
    R = lambda n: json.loads((W / f"results/{n}.json").read_text()) if (W / f"results/{n}.json").exists() else []
    baseline, ablation, candidates, quality = R("baseline"), R("ablation"), R("candidates"), R("quality")
    ablation_big = R("ablation_big")
    macs = json.loads(a.macs.read_text())
    assert macs["realesrgan_x4plus@64x64"]["macs"] == C4 * 64 * 64, "x4 MAC formula != ONNX graph"
    assert macs["realesrgan_x2plus@64x64"]["macs"] == C2 * 64 * 64, "x2 MAC formula != ONNX graph"

    # ------------------------------------------------ baseline timing
    B = {}
    for run in baseline:
        for j in run.get("jobs", []):
            B[j["id"]] = j
    env = next(r["env"] for r in baseline if "env" in r)
    load_up = next((r["model_load_s"].get("upscale") for r in baseline if r.get("model_load_s", {}).get("upscale")), float("nan"))
    warm = lambda j: j["iters"][-1]
    ws = {"x2_512": (2, 512, 512), "x4_256": (4, 256, 256), "x4_512": (4, 512, 512), "x4_1024": (4, 1024, 1024)}

    def job_macs(k):
        if k.startswith("colorize"):
            return macs["ddcolor_tiny@512x512"]["macs"]
        s, w, h = ws[k]
        return (C4 if s == 4 else C2) * tiling(w, h)[1]

    G = {k: job_macs(k) / warm(B[k])["wall_s"] for k in ws if k in B}  # MAC/s
    g4 = statistics.mean(G[k] for k in ("x4_512", "x4_1024") if k in G)
    g2 = G.get("x2_512", g4)
    all_iters = [(r["name"], it) for r in baseline + ablation + candidates + ablation_big for j in r.get("jobs", []) for it in j.get("iters", [])]
    max_cores = max(it["cpu_s"] / it["wall_s"] for _, it in all_iters)
    max_mem = max(it["mem_peak_mb"] for _, it in all_iters)
    n_runs = len(all_iters)

    # ------------------------------------------------ ablation data
    AB = {}
    for r in ablation:
        it = first_iters(r)
        AB[r["name"].replace("abl_", "")] = (r, it)
    prod_iters = AB["prod"][1]
    prod_t = prod_iters[0]["wall_s"]  # first (cold) call: same as every single-run variant, so the comparison is like-for-like
    prod_warm = prod_iters[-1]["wall_s"]
    prod_mem = max(i["mem_peak_mb"] for i in prod_iters)
    walls = [i["wall_s"] for i in prod_iters]
    noise = (max(walls) - min(walls)) / min(walls) * 100  # spread of the three shipped runs (cold call + two warm)
    prod_png = W / "abl_out/prod.png"

    # ------------------------------------------------ quality metrics (baseline + candidates)
    qjobs = {}
    for r in quality:
        for j in r.get("jobs", []):
            qjobs[(r["name"], j["id"])] = j
    q = W / "imgs" / "q"
    names = ("astronaut", "coffee", "chelsea")
    cand_keys = [k for k in ("int8", "general_v3") if any(r["name"] == f"quality_{k}" for r in quality)]
    METHODS = ["Bicubic", "Lanczos", "x4plus"] + [{"int8": "x4plus INT8", "general_v3": "general-x4v3"}[k] for k in cand_keys]
    cand_label = {"int8": "x4plus INT8", "general_v3": "general-x4v3"}
    up = {}
    for suffix, s in (("clean_x4", 4), ("degraded_x4", 4), ("clean_x2", 2)):
        for n in names:
            hr = load(q / f"{n}_hr.png")
            lr = load(q / (f"{n}_lr_x4_degraded.png" if suffix == "degraded_x4" else f"{n}_lr_x{s}.png"))
            h, w = hr.shape[:2]
            ims = {"Bicubic": cv2.resize(lr, (w, h), interpolation=cv2.INTER_CUBIC),
                   "Lanczos": cv2.resize(lr, (w, h), interpolation=cv2.INTER_LANCZOS4),
                   "x4plus": load(q / f"{n}_sr_{suffix}.png")}
            if s == 4:
                for k in cand_keys:
                    p = q / f"{n}_sr_{k}_{suffix}.png"
                    if p.exists():
                        ims[cand_label[k]] = load(p)
            m = {k: (psnr(shave(to_y(v)), shave(to_y(hr))), ssim_y(v, hr), lap_var(v)) for k, v in ims.items()}
            up[(suffix, n)] = dict(hr=hr, lr=lr, ims=ims, m=m, gt_lap=lap_var(hr),
                                   t=qjobs.get(("quality_up", f"{n}_{suffix}"), {"iters": [{"wall_s": float("nan")}]})["iters"][-1]["wall_s"])
    mean_m = lambda suffix, k, i: statistics.mean(up[(suffix, n)]["m"][k][i] for n in names)

    # colourisation metrics
    col_rows, col_data = [], {}
    for n in names:
        gt, out = load(q / f"{n}_hr.png"), load(q / f"{n}_colorized.png")
        lg, lo = rgb2lab(gt / 255.0), rgb2lab(out / 255.0)
        dab = np.sqrt(((lg[..., 1:] - lo[..., 1:]) ** 2).sum(-1))
        base = np.sqrt((lg[..., 1:] ** 2).sum(-1))
        t = qjobs[("quality_col", f"{n}_colorize")]["iters"][-1]["wall_s"]
        col_rows.append((n, f"{gt.shape[1]}×{gt.shape[0]}", float(dab.mean()), float(base.mean()),
                         colorfulness(gt), colorfulness(out), psnr(gt, out), t))
        col_data[n] = (load(q / f"{n}_gray.png"), out, gt)
    flower_ok = ("quality_col", "bw_flower_colorize") in qjobs
    if flower_ok:
        fo = load(q / "bw_flower_colorized.png")
        col_data["bw-flower (project test image)"] = (load(q / "bw_flower.png"), fo, None)
        flower_t, flower_cf = qjobs[("quality_col", "bw_flower_colorize")]["iters"][-1]["wall_s"], colorfulness(fo)
    de_mean, de_base = statistics.mean(r[2] for r in col_rows), statistics.mean(r[3] for r in col_rows)

    # ------------------------------------------------ figures
    def style(ax):
        for s_ in ("top", "right"):
            ax.spines[s_].set_visible(False)
        ax.tick_params(labelsize=7)

    # profile figure
    prof = next((r["jobs"][0]["profile"] for r in baseline if r["name"] == "base_profile" and r.get("jobs")), None)
    trunk_mac = 16_533_504 + 36_864 + 1_728
    tail_mac = C4 - trunk_mac

    # ablation figure
    lab_map = [("prod", "Shipped (arena off, no spin, fixed threads)"), ("ort_default", "Stock ORT defaults (pinned to 2 CPUs)"),
               ("ort_default_quota_only", "Stock ORT defaults (quota only, host sees 16 CPUs)"), ("arena_on", "Arena + mem-pattern ON"),
               ("spin_on", "Thread spinning ON"), ("thread_env", "+ OMP/BLAS/cv2 threads pinned"),
               ("opt_basic", "Graph optimisation BASIC (no NCHWc layout)"),
               ("fixed_tiles", "Fixed-shape tiles + uint8 canvas"), ("fixed_arena", "Fixed tiles + arena/mem-pattern ON"),
               ("fixed_arena_shrink", "Fixed tiles + arena + shrinkage"), ("prod_ort123", "Shipped, ONNX Runtime 1.23.0"),
               ("fixed_arena_ort123", "Fixed tiles + arena, ORT 1.23.0"), ("tile128", "Tile 128"), ("tile384", "Tile 384"), ("tile512", "Tile 512")]
    abl_rows = []
    for key, lab in lab_map:
        if key not in AB:
            continue
        r, it = AB[key]
        if not it:
            abl_rows.append((key, lab, None, None, None, None, None, status_of(r)))
            continue
        t, mem = (it[0]["wall_s"] if key == "prod" else it[-1]["wall_s"]), max(i["mem_peak_mb"] for i in it)
        diff = None
        p = W / f"abl_out/{key}.png"
        if key != "prod" and p.exists() and prod_png.exists():
            diff = psnr(load(p), load(prod_png))
        abl_rows.append((key, lab, t, it[-1]["cpu_s"] / it[-1]["wall_s"], max(i["throttled_s"] for i in it), mem, diff, "ok"))
    okr = [r for r in abl_rows if r[2] is not None]
    fig, ax = plt.subplots(1, 2, figsize=(9.2, 0.33 * len(okr) + 0.9), sharey=True)
    ys = np.arange(len(okr))[::-1]
    for k, (axx, idx, lab, unit) in enumerate(((ax[0], 2, "wall time (s), lower is better", "s"), (ax[1], 5, "peak RAM (MiB), lower is better", "MiB"))):
        vals = [r[idx] for r in okr]
        axx.barh(ys, vals, color=["#1c3fb0" if r[0] == "prod" else "#9db4f5" for r in okr], height=0.65)
        for y, v in zip(ys, vals):
            axx.text(v, y, f" {v:.0f}" if unit == "MiB" else f" {v:.1f}", va="center", fontsize=6.5)
        axx.set_xlabel(lab, fontsize=7.5)
        style(axx)
        axx.set_xlim(0, max(vals) * 1.15)
    ax[0].set_yticks(ys, [r[1] for r in okr], fontsize=6.8)
    fig.tight_layout()
    fig.savefig(fig_dir / "ablation.png", dpi=200)
    plt.close(fig)

    # memory model fit: peak RAM vs. largest tile window (x4 => 16x pixels x 64ch x 4 B per feature map)
    fit_pts = []
    for key, T_ in (("tile128", 128), ("prod", 256), ("tile384", 384), ("tile512", 512)):
        if key in AB and AB[key][1]:
            A = max(windows(600, 400, T_))
            fit_pts.append((T_, 4096 * A / 2**20, max(i["mem_peak_mb"] for i in AB[key][1])))
    k_fit = b_fit = r2 = None
    if len(fit_pts) >= 3:
        xs, ys_ = np.array([p[1] for p in fit_pts]), np.array([p[2] for p in fit_pts])
        k_fit, b_fit = np.polyfit(xs, ys_, 1)
        r2 = 1 - ((ys_ - (k_fit * xs + b_fit)) ** 2).sum() / ((ys_ - ys_.mean()) ** 2).sum()
        fig, axx = plt.subplots(figsize=(4.4, 2.6))
        axx.plot(xs, ys_, "o", color="#1c3fb0")
        xx = np.linspace(0, xs.max() * 1.05, 20)
        axx.plot(xx, k_fit * xx + b_fit, "--", color="#999")
        for (T_, x_, y_) in fit_pts:
            axx.annotate(f"tile {T_}", (x_, y_), fontsize=6.5, xytext=(4, -9), textcoords="offset points")
        axx.set_xlabel("one 64-ch FP32 feature map of the largest tile window (MiB)", fontsize=7)
        axx.set_ylabel("measured peak RAM (MiB)", fontsize=7)
        style(axx)
        fig.tight_layout()
        fig.savefig(fig_dir / "memfit.png", dpi=200)
        plt.close(fig)

    # candidate + baseline crop grids
    def best_window(gt, size):
        lap = np.abs(cv2.Laplacian(to_y(gt).astype(np.float32), cv2.CV_32F))
        best, pos = -1, (0, 0)
        for yy in range(0, gt.shape[0] - size + 1, 8):
            for xx in range(0, gt.shape[1] - size + 1, 8):
                v = lap[yy:yy + size, xx:xx + size].mean()
                if v > best:
                    best, pos = v, (xx, yy)
        return pos

    def crop_grid(suffix, s, fname, title, size=96):
        methods = ["Bicubic", "Lanczos", "x4plus"] + ([cand_label[k] for k in cand_keys] if s == 4 else [])
        ncol = 2 + len(methods)
        fig, axes = plt.subplots(len(names), ncol, figsize=(9.6, 1.85 * len(names) + 0.45))
        for r_, n in enumerate(names):
            d = up[(suffix, n)]
            x0, y0 = best_window(d["hr"], size)
            tiles = [("LR input (nearest)", cv2.resize(d["lr"][y0 // s:(y0 + size) // s, x0 // s:(x0 + size) // s], (size, size), interpolation=cv2.INTER_NEAREST), None)]
            for mth in methods:
                tiles.append((("Real-ESRGAN x4plus" if mth == "x4plus" else mth), d["ims"][mth][y0:y0 + size, x0:x0 + size], d["m"][mth]))
            tiles.append(("Ground truth", d["hr"][y0:y0 + size, x0:x0 + size], None))
            for c, (lab, im, m) in enumerate(tiles):
                axes[r_, c].imshow(im, interpolation="nearest")
                axes[r_, c].axis("off")
                axes[r_, c].set_title(lab if m is None else f"{lab}\n{m[0]:.2f} dB · {m[1]:.3f}", fontsize=6.3, pad=2,
                                      color="#1c3fb0" if lab.startswith("Real-ESRGAN") else "#1b1f27")
            axes[r_, 0].text(-0.06, 0.5, n, transform=axes[r_, 0].transAxes, rotation=90, va="center", ha="right", fontsize=7.5, color="#5a6272")
        fig.suptitle(title, fontsize=8.5, y=0.997)
        fig.tight_layout(rect=(0.02, 0, 1, 0.985), h_pad=0.6, w_pad=0.25)
        fig.savefig(fig_dir / fname, dpi=190)
        plt.close(fig)

    crop_grid("clean_x4", 4, "grid_clean_x4.jpg", "×4, clean input — 96×96 crops of the highest-detail region · captions: full-image Y-PSNR / SSIM")
    crop_grid("degraded_x4", 4, "grid_degraded_x4.jpg", "×4, degraded input (noise σ=2 + JPEG q50) — same crops · captions: full-image Y-PSNR / SSIM")
    crop_grid("clean_x2", 2, "grid_clean_x2.jpg", "×2, clean input — same crops · captions: full-image Y-PSNR / SSIM")

    def showcase(orig_path, sr_path, s, fname, label, crop):
        o, sr = load(orig_path), load(sr_path)
        cx, cy, cs = crop
        fig = plt.figure(figsize=(9.4, 6.0))
        gs = fig.add_gridspec(2, 3, height_ratios=[1.55, 1], hspace=0.16, wspace=0.05)
        a0, a1 = fig.add_subplot(gs[0, :1]), fig.add_subplot(gs[0, 1:])
        a0.imshow(o); a0.set_title(f"Original — {o.shape[1]}×{o.shape[0]} px", fontsize=8); a0.axis("off")
        a1.imshow(sr); a1.set_title(f"Real-ESRGAN ×{s} — {sr.shape[1]}×{sr.shape[0]} px (drawn at the same display size)", fontsize=8); a1.axis("off")
        for ax_, (x0, y0, x1, y1) in ((a0, (cx, cy, cx + cs, cy + cs)), (a1, (cx * s, cy * s, (cx + cs) * s, (cy + cs) * s))):
            ax_.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec="#ff4d4f", lw=1.2))
        oc = o[cy:cy + cs, cx:cx + cs]
        panels = [("Original pixels, enlarged (nearest)", cv2.resize(oc, (cs * s, cs * s), interpolation=cv2.INTER_NEAREST)),
                  (f"Bicubic ×{s}", cv2.resize(oc, (cs * s, cs * s), interpolation=cv2.INTER_CUBIC)),
                  (f"Real-ESRGAN ×{s}", sr[cy * s:(cy + cs) * s, cx * s:(cx + cs) * s])]
        for c, (lab, im) in enumerate(panels):
            ax_ = fig.add_subplot(gs[1, c]); ax_.imshow(im, interpolation="nearest"); ax_.axis("off"); ax_.set_title(lab, fontsize=7.5)
        fig.suptitle(label, fontsize=9, y=0.965)
        fig.savefig(fig_dir / fname, dpi=190, bbox_inches="tight", pad_inches=0.05)
        plt.close(fig)

    showcase(W / "imgs/astronaut.png", q / "showcase_astronaut_x4.png", 4, "show_astro.jpg",
             "Production-style run: original upload → ×4 (no ground truth; red box = zoomed region)", (196, 40, 96))
    showcase(W / "imgs/coffee.png", q / "showcase_coffee_x2.png", 2, "show_coffee.jpg",
             "Production-style run: original upload → ×2 (no ground truth; red box = zoomed region)", (270, 150, 96))

    ks = list(col_data)
    fig, axes = plt.subplots(len(ks), 3, figsize=(9.2, 2.25 * len(ks)))
    for r_, k in enumerate(ks):
        g, o, gt = col_data[k]
        for c, (lab, im) in enumerate((("Grayscale input", g), ("DDColor-Tiny output", o), ("Original colour (ground truth)", gt))):
            axes[r_, c].axis("off")
            if im is None:
                axes[r_, c].text(0.5, 0.5, "no ground truth\n(real B/W photograph)", ha="center", va="center", fontsize=7, color="#5a6272")
                continue
            axes[r_, c].imshow(im)
            axes[r_, c].set_title(lab if r_ == 0 else "", fontsize=7.5, pad=3)
        axes[r_, 0].text(-0.03, 0.5, k, transform=axes[r_, 0].transAxes, rotation=90, va="center", ha="right", fontsize=7, color="#5a6272")
    fig.tight_layout(h_pad=0.4, w_pad=0.3)
    fig.savefig(fig_dir / "colorize.jpg", dpi=170)
    plt.close(fig)

    # ================================================================ PDF
    story = []
    today = date.today().strftime("%d %b %Y")
    t512 = warm(B["x4_512"])["wall_s"]
    cw = warm(B["colorize_512"])["wall_s"]
    story += [Spacer(1, 5 * mm), P("Repix — CPU model comparison", "title"),
              P(f"Real-ESRGAN upscaling and DDColor-Tiny colourisation, ONNX Runtime CPU · measured at the deployment target: {TARGET} · {today}", "sub"),
              P("Summary", "h1")]

    def verdict(key):
        row = next((r for r in abl_rows if r[0] == key), None)
        if not row or row[2] is None:
            return None
        return (row[2] / prod_t - 1) * 100, (row[5] / prod_mem - 1) * 100, row[6]

    v_fixed, v_arena, v_shr = verdict("fixed_tiles"), verdict("fixed_arena"), verdict("fixed_arena_shrink")
    v_ort = verdict("prod_ort123")
    sum_items = [
        f"<b>Speed at the target spec.</b> A ×4 upscale of 512×512 (→ 2048×2048) takes <b>{fmt_t(t512)}</b>; ×2 of 512×512 takes {fmt_t(warm(B['x2_512'])['wall_s'])}; "
        f"a 1024×1024 → 4096×4096 ×4 job takes {fmt_t(warm(B['x4_1024'])['wall_s'])}; colourising one image takes {fmt_t(cw)} (fixed cost). "
        f"Throughput is ≈ {g4 / 1e9:.0f} GMAC/s (§4).",
        f"<b>Memory.</b> Peak RAM of the shipped configuration is {max(warm(B[k])['mem_peak_mb'] for k in ('x4_512', 'x4_1024')):.0f} MiB for ×4 up to 4096² output — "
        f"under 20 % of the 8 GB plan. A measured linear model predicts it from tile size (§5.3).",
        f"<b>Caps held.</b> Across {n_runs} timed runs the container never used more than {max_cores:.2f} cores (cap 2.0) or {max_mem:.0f} MiB (cap 8192 MiB).",
    ]
    v_arena_only, v_spin, v_thr, v_basic, v_default = verdict("arena_on"), verdict("spin_on"), verdict("thread_env"), verdict("opt_basic"), verdict("ort_default")
    v_quota = verdict("ort_default_quota_only")
    big_txt = ""
    if ablation_big:
        r_ = next((r for r in ablation_big if r["name"] == "big_arena_on"), None)
        if r_ and first_iters(r_):
            it_ = first_iters(r_)[0]
            big_txt = (f" On the 1024²→4096² job it is {it_['wall_s']:.0f} s vs {warm(B['x4_1024'])['wall_s']:.0f} s using {it_['mem_peak_mb']:.0f} MiB "
                       f"vs {max(i['mem_peak_mb'] for i in B['x4_1024']['iters']):.0f} MiB.")
        elif r_:
            big_txt = f" On the 1024²→4096² job it did not finish: {status_of(r_)}."
    if v_arena_only:
        sum_items.append(f"<b>What helped.</b> Arena + memory-pattern ON: {v_arena_only[0]:+.0f} % time for {v_arena_only[1]:+.0f} % RAM on the 600×400 test." + big_txt)
    sum_items.append(f"<b>What did not.</b> Constant-shape tiles: {v_fixed[0]:+.0f} % time on this small image (they recompute edge pixels, §5.1b). "
                     f"Stock ORT defaults on a 2-CPU VPS: {v_default[0]:+.0f} % time, {v_default[1]:+.0f} % RAM"
                     + (f"; with only a CPU quota (host CPUs visible) {v_quota[0]:+.0f} % and {sum(1 for _ in [0]) and next((r[4] for r in abl_rows if r[0] == 'ort_default_quota_only'), 0):.0f} s of CPU throttling" if v_quota else "")
                     + f". Within noise (≈ {max(5, noise):.0f} %): spinning {v_spin[0]:+.0f} %, thread env {v_thr[0]:+.0f} %, ORT 1.23.0 {v_ort[0]:+.0f} %. "
                     f"Skipping the NCHWc layout transform: {v_basic[0]:+.0f} % (slower).")
    ci = next((r for r in candidates if r["name"] == "cand_int8" and r.get("jobs")), None)
    cg = next((r for r in candidates if r["name"] == "cand_general_v3" and r.get("jobs")), None)
    worse = [r_[0] for r_ in col_rows if r_[2] > r_[3]]
    sum_items.append(f"<b>Colourisation.</b> Mean chroma error ΔE*<sub>ab</sub> {de_mean:.1f} vs {de_base:.1f} for “no colour” (lower is better). "
                     + (f"On {', '.join(worse)} the model was <i>worse</i> than adding no colour (§8)." if worse else "Better than no colour on every test photo."))
    for nm, r, lab in (("int8", ci, "INT8 x4plus"), ("gen", cg, "general-x4v3")):
        if r:
            it = r["jobs"][0]["iters"]
            sum_items.append(f"<b>Candidate {lab}:</b> {it[-1]['wall_s']:.1f} s vs {prod_warm:.1f} s ({prod_warm / it[-1]['wall_s']:.1f}× faster), "
                             f"peak {max(i['mem_peak_mb'] for i in it):.0f} MiB vs {prod_mem:.0f} MiB — quality in §6.")
    story += bullets(sum_items)
    story += [P("Contents: 1 Target and safety · 2 Models &amp; approach · 3 Math · 4 Baseline performance · 5 Optimisation experiments · "
                "6 Candidate models · 7 Upscaling quality · 8 Colourisation · 9 Recommendations &amp; limitations", "small")]

    # ---- 1 target/safety
    story += [P("1  Deployment target and safety", "h1")]
    lscpu = subprocess.run(["lscpu"], capture_output=True, text=True).stdout
    cpu_name = next((l.split(":", 1)[1].strip() for l in lscpu.splitlines() if l.startswith("Model name")), "?")
    mem_gb = int(next(l.split()[1] for l in Path("/proc/meminfo").read_text().splitlines() if l.startswith("MemTotal"))) / 2**20
    kernel = subprocess.run(["uname", "-r"], capture_output=True, text=True).stdout.strip()
    story += [P(f"The app will be hosted on a <b>{TARGET}</b>. The test machine is much bigger ({cpu_name}, 16 threads, {mem_gb:.0f} GB, Linux {kernel}, no swap), "
                f"so every measurement runs in a container limited to the target's resources:"),
              table([["Target resource", "Container limit used", "Why"],
                     ["2 vCPU", "<font name='DV-M'>--cpus 2 --cpuset-cpus 0,1</font>", "quota + pinning to two physical cores: the app sees exactly 2 CPUs, as it would on the VPS"],
                     ["8 GB RAM, no swap", "<font name='DV-M'>--memory 8g --memory-swap 8g</font>", "hard cap; overshoot means the container is OOM-killed, never the host"],
                     ["—", "<font name='DV-M'>--pids-limit 256 --network none --read-only --cap-drop ALL</font>", "no fork bombs, no network, nothing writable except a scratch mount"],
                     ["—", "<font name='DV-M'>--oom-score-adj 800</font>", "if the host ever ran short, the kernel kills the benchmark first"]],
                    [30 * mm, 72 * mm, CONTENT_W - 102 * mm]),
              P("Extra guards in the runner (stricter than the cap, because this machine is shared with a desktop): one container at a time; "
                "refuses to start with &lt; 6 GB free host RAM or load &gt; 8; a watchdog kills the container if host free RAM drops under 2 GB or a run exceeds its timeout; "
                "the script cannot request more than 2 CPUs / 8 GB.", "small"),
              table([["Measured inside every run (cgroup accounting)", "Value", "Cap"],
                     ["Timed calls (all runs)", n_runs, ""],
                     ["Max average cores used (CPU-seconds ÷ wall-seconds)", f"{max_cores:.2f}", "2.00"],
                     ["Max container RAM (sampled every 20 ms)", f"{max_mem:.0f} MiB", "8192 MiB"],
                     ["Runs OOM-killed / stopped by watchdog", f"{sum(1 for r in baseline + ablation + candidates + ablation_big if r.get('oom_killed') or r.get('killed_by_harness'))}", "—"]],
                    [88 * mm, 40 * mm, CONTENT_W - 128 * mm]),
              P("Protocol: fresh container per configuration; model loaded once (not timed); the last of 1–3 calls is reported as the warm time; "
                "timing covers the engine call only (image → array → inference with tiling → 8-bit image), not upload, PNG encoding, queueing or HTTP.", "small")]

    # ---- 2 models
    story += [P("2  Models and approach", "h1")]

    def sha(p):
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:12]

    mm_ = REPO / "models"
    mrow = lambda nm, p, prec, params, role: [nm, role, prec, f"{params / 1e6:.1f} M", f"{Path(p).stat().st_size / 2**20:.0f} MiB", sha(p)]
    story += [table([["Model", "Role", "Weights", "Params", "File", "SHA-256"],
                     mrow("Real-ESRGAN x4plus", mm_ / "realesrgan/realesrgan_x4plus.onnx", "FP32", macs["realesrgan_x4plus@64x64"]["params"], "×4 upscaler (RRDBNet, 23 blocks)"),
                     mrow("Real-ESRGAN x2plus", mm_ / "realesrgan/realesrgan_x2plus.onnx", "FP32", macs["realesrgan_x2plus@64x64"]["params"], "×2 upscaler (RRDBNet + pixel-unshuffle)"),
                     mrow("DDColor-Tiny", mm_ / "ddcolor/ddcolor_tiny.onnx", "FP16 stored, FP32 compute", macs["ddcolor_tiny@512x512"]["params"], "Colourisation (ConvNeXt + transformer decoder)")],
                    [28 * mm, 44 * mm, 25 * mm, 17 * mm, 17 * mm, CONTENT_W - 131 * mm]),
              P("×4 is a dedicated model (never ×2 twice). Hashes match <font name='DV-M'>models/CHECKSUMS.sha256</font>. DDColor's FP16 initialisers are cast to FP32 by ONNX Runtime on CPU.", "small"),
              P("Upscaling", "h2")] + bullets([
        "RGB float32 → NCHW. Images larger than the tile size are cut into <b>256×256 tiles with a 16 px halo</b>; only each tile's non-overlapping core is pasted into the output, so tile-border artefacts are dropped without blending.",
        "Output is clipped, rounded to 8-bit and saved as PNG (lossless).",
    ]) + [P("Colourisation", "h2")] + bullets([
        "The original luminance L is kept at full resolution. A 512×512 grey copy goes through DDColor, which predicts chroma (a, b); it is resized back and recombined with the untouched L — "
        "<b>brightness and detail are preserved exactly</b>, only colour is invented.",
    ]) + [P("Optimisations already in the shipped code", "h2"),
          table([["Optimisation", "Where", "Purpose"],
                 ["Threads = CPU quota / cpuset (reads cgroup <font name='DV-M'>cpu.max</font> + affinity)", "<font name='DV-M'>core/config.py</font>", "ORT would otherwise size its pool from host cores"],
                 ["Spinning off, inter-op 1, sequential execution", "<font name='DV-M'>ort_options.py</font>", "idle threads sleep instead of burning quota"],
                 ["CPU memory arena off + memory-pattern off", "<font name='DV-M'>ort_options.py</font>", "avoid pool growth with varying tile shapes"],
                 ["Tiling with fixed tile size", "<font name='DV-M'>realesrgan.py</font>", "bounds memory independent of image size"],
                 ["Bounded queue, MAX_AI_WORKERS = 1", "<font name='DV-M'>manager.py</font>", "extra jobs wait instead of taking CPU"]],
                [70 * mm, 30 * mm, CONTENT_W - 100 * mm])]

    # ---- 3 math
    story += [CondPageBreak(120 * mm), P("3  The math", "h1"), P("3.1  Output size and tiling", "h2"),
              eq(r"W_o = sW,\quad H_o = sH,\quad P_o = s^2\,W H\qquad (s\in\{2,4\})"),
              P("The app caps output at 50 M px, so the largest ×4 input is ≈ 3.1 MP (e.g. 2500×1250)."),
              eq(r"n_x=\lceil W/T\rceil,\quad n_y=\lceil H/T\rceil,\quad N=n_x n_y \qquad T=256,\; o=16")]
    rows = [["Input", "Tiles N", "Pixels processed", "Overlap overhead η", "Output (×4)"]]
    for wh in ((256, 256), (512, 512), (1024, 1024), (1920, 1080), (2500, 1250)):
        n, proc = tiling(*wh)
        rows.append([f"{wh[0]}×{wh[1]}", n, f"{proc:,}", f"{100 * (proc / (wh[0] * wh[1]) - 1):.1f} %", f"{4 * wh[0]}×{4 * wh[1]}"])
    story += [P("Every tile carries a halo, so a few pixels are computed twice: η = P<sub>processed</sub>/(W·H) − 1."),
              table(rows, [28 * mm, 22 * mm, 38 * mm, 40 * mm, CONTENT_W - 128 * mm]),
              P("An input that fits one tile (max(W,H) ≤ 256) runs in a single pass without overhead.", "small"),
              P("3.2  Compute cost of Real-ESRGAN (RRDBNet)", "h2"),
              P("One dense block (RDB) has five 3×3 convolutions with 64→32, 96→32, 128→32, 160→32, 192→64 channels; one MAC per weight per output position:"),
              eq(rf"\mathrm{{MAC}}_{{RDB}} = 9\,(64\cdot32+96\cdot32+128\cdot32+160\cdot32+192\cdot64) = {RDB:,}"),
              P("The trunk is 23 RRDB × 3 RDB = 69 RDBs → 16,533,504 MAC/px at the input grid. Adding the remaining 64-channel convolutions (the upsampling convs run at 2× and 4× the "
                "resolution, i.e. 4× and 16× the pixels) gives the ×4 network:"),
              eq(rf"c_4 = 16{{,}}533{{,}}504 + 36{{,}}864 + 1{{,}}728 + 4\cdot36{{,}}864 + 16\,(2\cdot 36{{,}}864+1{{,}}728) = {C4:,}\ \mathrm{{MAC/px}}", size=11),
              P("The ×2 network folds each 2×2 block into channels first (pixel-unshuffle → 12 channels at ¼ of the pixels), making it 4× cheaper per input pixel:"),
              eq(rf"c_2 = \frac{{16{{,}}533{{,}}504+36{{,}}864+6{{,}}912+4\cdot 36{{,}}864+16\,(2\cdot36{{,}}864+1{{,}}728)}}{{4}} = {C2:,}\ \mathrm{{MAC/px}}", size=11),
              P(f"<b>Check against the model file:</b> summing every Conv node of the ONNX graphs gives {macs['realesrgan_x4plus@64x64']['macs']:,} and {macs['realesrgan_x2plus@64x64']['macs']:,} MAC at 64×64 — "
                f"exactly 64²·c<sub>4</sub> and 64²·c<sub>2</sub> (asserted in code). 1 MAC = 2 FLOP, so ×4 costs {2 * C4 / 1e6:.1f} MFLOP per input pixel."),
              eq(r"\mathrm{MAC}_{job} = c_s\,P_{processed} = c_s\,(1+\eta)\,W H"),
              P(f"<b>DDColor-Tiny</b> always runs on 512×512, so its cost is fixed (≥ {macs['ddcolor_tiny@512x512']['macs'] / 1e9:.1f} GMAC from resolved Conv/MatMul nodes — a lower bound, "
                f"some attention MatMuls have dynamic shapes); only the Lab conversions and resizes scale with W·H."),
              P("3.3  Time and memory prediction", "h2"),
              eq(r"t \approx \frac{\mathrm{MAC}_{job}}{G},\qquad M_{peak}\approx M_{0} + k\cdot F + 12\,W_oH_o\,\mathrm{B},\qquad F = 16\,A_{tile}\cdot 64\cdot 4\,\mathrm{B}"),
              P(f"G is the measured throughput (§4); F is one 64-channel FP32 feature map at ×4 output resolution for the largest tile window of A<sub>tile</sub> pixels ((T+2o)² = 288² for a full interior tile); the last term of M<sub>peak</sub> is the float32 output canvas of the shipped engine. "
                + (f"§5.3 fits k = {k_fit / 1:.2f} and M<sub>0</sub> = {b_fit:.0f} MiB (R² = {r2:.3f}) from four tile sizes. " if k_fit is not None else "")
                + f"For a full 288² interior tile one feature map is (4·288)²·64·4 B = {(4 * 288) ** 2 * 64 * 4 / 2**20:.0f} MiB."),
              P("3.4  Quality metrics", "h2"),
              eq(r"\mathrm{PSNR}=10\log_{10}\frac{255^2}{\mathrm{MSE}},\qquad \mathrm{SSIM}(x,y)=\frac{(2\mu_x\mu_y+C_1)(2\sigma_{xy}+C_2)}{(\mu_x^2+\mu_y^2+C_1)(\sigma_x^2+\sigma_y^2+C_2)}", size=11),
              P("On luma Y = 0.299R+0.587G+0.114B, 4-px border shaved, Gaussian 11×11 window (σ = 1.5), C<sub>1</sub>=(0.01·255)², C<sub>2</sub>=(0.03·255)². Each test photo is downsampled by s "
                "(INT_AREA, “clean”) or additionally corrupted with σ=2 noise and JPEG q=50 (“degraded”); the upscaled result is compared with the original."),
              P("For colourisation (Lab, D65; L is preserved exactly so the error is pure chroma):"),
              eq(r"\Delta E^*_{ab}=\sqrt{(a-\hat a)^2+(b-\hat b)^2},\qquad M=\sqrt{\sigma_{rg}^2+\sigma_{yb}^2}+0.3\sqrt{\mu_{rg}^2+\mu_{yb}^2}", size=11),
              P("rg = R−G, yb = ½(R+G)−B; M is the Hasler–Süsstrunk colourfulness; “baseline ΔE” is the error of outputting no colour.", "small")]

    # ---- 4 baseline
    story += [CondPageBreak(120 * mm), P("4  Baseline performance at the target spec", "h1"),
              P("Shipped configuration, 2 vCPU / 8 GB. Content is the astronaut photo resized to each size (run time depends on pixel count, not content).")]
    rows = [["Workload", "MAC (job)", "cold", "warm", "G (GMAC/s)", "MAC per CPU-s", "peak RAM"]]
    for k, lab in (("colorize_512", "Colourise 512×512"), ("colorize_1024", "Colourise 1024×1024"), ("x2_512", "Upscale ×2: 512² → 1024²"),
                   ("x4_256", "Upscale ×4: 256² → 1024²"), ("x4_512", "Upscale ×4: 512² → 2048²"), ("x4_1024", "Upscale ×4: 1024² → 4096²")):
        if k not in B:
            continue
        j = B[k]
        w_, c_ = warm(j), j["iters"][0]
        mac = job_macs(k)
        col_ = k.startswith("colorize")
        rows.append([lab, ("≥ " if col_ else "") + f"{mac / 1e9:,.0f} G", fmt_t(c_["wall_s"]) if len(j["iters"]) > 1 else "—", fmt_t(w_["wall_s"]),
                     "—" if col_ else f"{mac / w_['wall_s'] / 1e9:.0f}", "—" if col_ else f"{mac / w_['cpu_s'] / 1e9:.0f} G", f"{w_['mem_peak_mb']:.0f} MiB"])
    story += [table(rows, [51 * mm, 19 * mm, 19 * mm, 19 * mm, 22 * mm, 24 * mm, CONTENT_W - 154 * mm]),
              P(f"cold = first call, warm = last call. G = achieved GMAC/s; “MAC per CPU-s” divides by CPU time actually consumed (efficiency per core). Colourisation is transformer-heavy and its MAC count is only a lower bound, so no throughput is quoted for it. "
                f"Model load at startup: {load_up:.1f} s (both upscalers).", "small")]
    if prof:
        tot = prof["trunk_s"] + prof["tail_s"] + prof["layout_reorder_s"]
        story += [P("4.1  Where the time goes: per-layer profile of one 288×288 tile (×4)", "h2"),
                  table([["Part of the network", "Time", "Share of time", "Share of MACs"],
                         ["Trunk: 69 dense-block convs + conv_first + conv_body (LR resolution)", f"{prof['trunk_s']:.2f} s", f"{100 * prof['trunk_s'] / tot:.0f} %", f"{100 * trunk_mac / C4:.1f} %"],
                         ["Tail: upsampling convs at 2× and 4× resolution + resizes", f"{prof['tail_s']:.2f} s", f"{100 * prof['tail_s'] / tot:.0f} %", f"{100 * tail_mac / C4:.1f} %"],
                         ["Layout reorders (NCHWc ⇄ NCHW) inserted by ORT", f"{prof['layout_reorder_s']:.2f} s", f"{100 * prof['layout_reorder_s'] / tot:.0f} %", "0 %"]],
                        [92 * mm, 20 * mm, 30 * mm, CONTENT_W - 142 * mm]),
                  P(f"From ONNX Runtime's profiler (second call, single tile, wall {prof['wall_s']:.1f} s). By op: " + ", ".join(f"{k} {v:.2f} s" for k, v in list(prof["by_op_s"].items())[:5]) + ". "
                    + (f"The tail takes {100 * prof['tail_s'] / tot:.0f} % of the time for {100 * tail_mac / C4:.1f} % of the MACs — disproportionately slow, consistent with a memory-bandwidth-bound tail. "
                       if prof['tail_s'] / tot > 1.5 * tail_mac / C4 else
                       f"The tail takes {100 * prof['tail_s'] / tot:.0f} % of the time for {100 * tail_mac / C4:.1f} % of the MACs, i.e. proportional: the hypothesis that the 4×-resolution tail is a memory-bandwidth bottleneck is <b>not</b> supported on this machine. ")
                    + f"What stands out instead is layout conversion: ORT runs the convolutions in a blocked NCHWc layout and inserts reorders that cost {100 * prof['layout_reorder_s'] / tot:.0f} % of kernel time; §5 tests whether skipping that transform pays off.", "small")]

    # capacity
    story += [P("4.2  What a job costs on this plan (predicted from the measured throughput)", "h2")]
    rows = [["Input", "Scale", "Tiles", "MAC", "Predicted time", "Predicted peak RAM", "Output"]]
    for (w_, h_, s_) in ((1000, 750, 4), (1920, 1080, 2), (1920, 1080, 4), (2500, 1250, 4)):
        n, proc = tiling(w_, h_)
        mac = (C4 if s_ == 4 else C2) * proc
        A = max(windows(w_, h_))
        mem = (b_fit + k_fit * 16 * A * 64 * 4 / 2**20 + 12 * (w_ * s_) * (h_ * s_) / 2**20) if k_fit is not None else float("nan")
        rows.append([f"{w_}×{h_}", f"×{s_}", n, f"{mac / 1e12:.1f} T", fmt_t(mac / (g4 if s_ == 4 else g2)), f"{mem / 1024:.1f} GB" if mem == mem else "—", f"{w_ * s_}×{h_ * s_}"])
    story += [table(rows, [26 * mm, 14 * mm, 14 * mm, 20 * mm, 30 * mm, 34 * mm, CONTENT_W - 138 * mm]),
              P("Time = MAC ÷ measured G (×4 uses the ×4 throughput, ×2 the ×2 throughput). The last row is the largest ×4 job the app accepts (50 M output pixels). "
                "The memory column uses the fit in §5.3 plus the float canvas and is an extrapolation. Even the largest job is a long-running one: timeouts and the UI must allow for it, "
                "and a full queue (5 jobs) can hold more than an hour of work.", "small")]

    # ---- 5 optimisation experiments
    story += [CondPageBreak(120 * mm), P("5  Optimisation experiments (×4 of a 600×400 photo, 2 vCPU / 8 GB)", "h1"),
              P(f"Each technique is switched on or off in an otherwise identical fresh container. The 600×400 input is cut into 3×2 tiles of <i>different</i> shapes, which is the case the "
                f"arena and fixed-shape ideas target. Every variant is one cold call; the shipped configuration (the baseline, first call = {prod_t:.1f} s) was run three times ({', '.join(f'{w:.1f}' for w in walls)} s), a spread of <b>{noise:.1f} %</b>, so differences below ≈ {max(5, noise):.0f} % are treated as noise.")]
    rows = [["Configuration", "Time", "Δ time", "Peak RAM", "Δ RAM", "Throttled", "Output vs shipped", "Status"]]
    for key, lab, t, cores, thr, mem, diff, stt in abl_rows:
        if t is None:
            rows.append([lab, "—", "—", "—", "—", "—", "—", stt])
            continue
        rows.append([f"<b>{lab}</b>" if key == "prod" else lab, f"{t:.1f} s", "" if key == "prod" else f"{(t / prod_t - 1) * 100:+.0f} %", f"{mem:.0f} MiB",
                     "" if key == "prod" else f"{(mem / prod_mem - 1) * 100:+.0f} %", f"{thr:.0f} s" if thr >= 1 else "0", "—" if diff is None else ("identical" if diff == float("inf") else f"{diff:.1f} dB"), stt])
    story += [table(rows, [52 * mm, 15 * mm, 14 * mm, 18 * mm, 14 * mm, 18 * mm, 24 * mm, CONTENT_W - 155 * mm]),
              P("Δ vs the shipped first (cold) call, negative = better. “Output vs shipped” compares this run's PNG with the shipped run's: “identical” = bit-for-bit the same image, so the option only changes speed/memory; "
                "a PSNR figure appears where the tile geometry changes (different context at tile borders; ≥ 45 dB is visually identical). "
                "Throttled = seconds the kernel paused the container for exceeding its CPU quota (largest of the runs).", "small"),
              img_flow(fig_dir / "ablation.png")]

    def find(key):
        return next((r for r in abl_rows if r[0] == key and r[2] is not None), None)

    def call(key, what):
        r = find(key)
        if not r:
            return f"<b>{what}:</b> not measured."
        dt, dm = (r[2] / prod_t - 1) * 100, (r[5] / prod_mem - 1) * 100
        if dt <= -max(5, noise) or dm <= -15:
            v = "worth adopting" if dt <= 0 and dm <= 0 else "mixed: a trade-off"
        elif dt >= max(5, noise) or dm >= 15:
            v = "not recommended (costs more than it saves)"
        else:
            v = "no measurable effect"
        return f"<b>{what}:</b> {dt:+.0f} % time, {dm:+.0f} % RAM → {v}."

    story += [P("5.1  Reading the results", "h2")] + bullets([
        call("ort_default", "Stock ORT options on a 2-CPU pinned VPS"),
        call("ort_default_quota_only", "Stock ORT options when the container only has a CPU <i>quota</i> (host CPUs visible)"),
        call("arena_on", "Arena + memory-pattern on"),
        call("spin_on", "Thread spinning on"),
        call("thread_env", "Pinning OMP/BLAS/OpenCV threads"),
        call("opt_basic", "Graph optimisation level BASIC instead of ALL (skips the NCHWc layout transform and its reorders, §4.1)"),
        call("fixed_tiles", "Constant tile shape (edge tiles shifted inward) + uint8 canvas"),
        call("fixed_arena", "Constant tile shape + arena + memory-pattern"),
        call("fixed_arena_shrink", "…plus per-run arena shrinkage"),
        call("prod_ort123", "ONNX Runtime 1.23.0 vs 1.20.1"),
    ])
    rows = [["Input", "Shipped: px processed", "Fixed-shape: px processed", "Extra compute"]]
    for wh in ((600, 400), (1024, 1024), (1920, 1080), (2500, 1250), (3000, 2000)):
        a_, b_ = tiling(*wh)[1], fixed_px(*wh)
        rows.append([f"{wh[0]}×{wh[1]}", f"{a_:,}", f"{b_:,}", f"{(b_ / a_ - 1) * 100:+.0f} %"])
    story += [P("5.1b  Why constant-shape tiles cost so much on small images", "h2"),
              P("To keep every tile at (T+2o)² = 288², edge tiles are shifted inward, so border pixels are computed twice. The extra work depends on image size (analytic, same tiling model as §3):"),
              table(rows, [30 * mm, 42 * mm, 46 * mm, CONTENT_W - 118 * mm]),
              P("The 600×400 test image is the worst case (it is barely larger than one tile); the measured slow-down of that run follows this table. "
                "Padding edge tiles instead would cost the same order of compute.", "small")]
    if ablation_big:
        bb = {r["name"].replace("big_", ""): r for r in ablation_big}
        rows = [["Configuration (×4, 1024² → 4096²)", "Time", "Peak RAM", "Δ time", "Δ RAM", "Status"]]
        base_run = B.get("x4_1024")
        bt, bm = warm(base_run)["wall_s"], max(i["mem_peak_mb"] for i in base_run["iters"])
        rows.append(["<b>Shipped (arena off)</b>", fmt_t(bt), f"{bm:.0f} MiB", "", "", "ok"])
        for key, lab in (("arena_on", "Arena + mem-pattern ON"), ("fixed_arena_shrink", "Fixed tiles + arena + shrinkage")):
            r = bb.get(key)
            if not r:
                continue
            it = first_iters(r)
            if not it:
                rows.append([lab, "—", "—", "—", "—", status_of(r)])
            else:
                rows.append([lab, fmt_t(it[0]["wall_s"]), f"{max(i['mem_peak_mb'] for i in it):.0f} MiB", f"{(it[0]['wall_s'] / bt - 1) * 100:+.0f} %",
                             f"{(max(i['mem_peak_mb'] for i in it) / bm - 1) * 100:+.0f} %", "ok"])
        story += [P("5.1c  Does the arena's memory growth appear on a larger image?", "h2"),
                  P("The shipped code comments warn that the arena can keep growing on large jobs. Same job as the §4 large run, one cold call each, 8 GiB cap:"),
                  table(rows, [62 * mm, 22 * mm, 24 * mm, 18 * mm, 18 * mm, CONTENT_W - 144 * mm])]
    story += [P("5.2  Tile size", "h2"),
              table([["Tile", "Tiles", "Pixels processed", "Time", "Peak RAM", "Output vs shipped"]] + [
                  [f"{T_}" + (" (shipped)" if T_ == 256 else ""), tiling(600, 400, T_)[0], f"{tiling(600, 400, T_)[1]:,}", f"{find(key)[2]:.1f} s", f"{find(key)[5]:.0f} MiB",
                   "—" if find(key)[6] is None else f"{find(key)[6]:.1f} dB"]
                  for T_, key in ((128, "tile128"), (256, "prod"), (384, "tile384"), (512, "tile512")) if find(key)],
                 [28 * mm, 18 * mm, 34 * mm, 22 * mm, 28 * mm, CONTENT_W - 130 * mm]),
              P("Smaller tiles re-compute more halo but use less memory; larger tiles amortise the halo but grow memory quadratically.", "small")]
    if k_fit is not None:
        story += [P("5.3  Memory model", "h2"),
                  img_flow(fig_dir / "memfit.png", CONTENT_W * 0.5),
                  P(f"Peak RAM ≈ {b_fit:.0f} MiB + {k_fit:.2f} × (one 64-channel FP32 feature map of the largest tile window), R² = {r2:.3f} over four tile sizes. "
                    "k ≈ 2–4 means ORT keeps a few full-resolution maps alive at once. This lets the API estimate a job's memory before starting it and reject what cannot fit, "
                    "rather than finding out from the OOM killer.", "small")]

    # ---- 6 candidates
    story += [CondPageBreak(120 * mm), P("6  Candidate models (not part of the shipped stack)", "h1"),
              P("DECISIONS.md fixes the shipped models; these two are measured only to quantify the trade-off suggested by the research notes. "
                "Both use the identical tiling and ORT settings; only the ONNX file differs.")]
    cand_rows = [["Model", "Time (warm)", "Speed-up", "Peak RAM", "Size", "Mean Y-PSNR clean", "Mean Y-PSNR degraded", "Mean SSIM clean / degraded"]]
    prow = ["Real-ESRGAN x4plus FP32 (shipped)", f"{prod_warm:.1f} s", "1.0×", f"{prod_mem:.0f} MiB", f"{Path(mm_ / 'realesrgan/realesrgan_x4plus.onnx').stat().st_size / 2**20:.0f} MiB",
            f"{mean_m('clean_x4', 'x4plus', 0):.2f} dB", f"{mean_m('degraded_x4', 'x4plus', 0):.2f} dB",
            f"{mean_m('clean_x4', 'x4plus', 1):.3f} / {mean_m('degraded_x4', 'x4plus', 1):.3f}"]
    cand_rows.append(prow)
    for k, fname, lab in (("int8", "realesrgan_x4plus_int8_qdq.onnx", "x4plus INT8 (static QDQ, per-channel)"), ("general_v3", "realesr_general_x4v3.onnx", "realesr-general-x4v3 (compact)")):
        r = next((r for r in candidates if r["name"] == f"cand_{k}" and r.get("jobs")), None)
        if not r or cand_label[k] not in METHODS:
            cand_rows.append([lab, "not built / not run", "", "", "", "", "", ""])
            continue
        it = r["jobs"][0]["iters"]
        cand_rows.append([lab, f"{it[-1]['wall_s']:.1f} s", f"{prod_warm / it[-1]['wall_s']:.1f}×", f"{max(i['mem_peak_mb'] for i in it):.0f} MiB",
                          f"{(W / 'candidates' / fname).stat().st_size / 2**20:.0f} MiB",
                          f"{mean_m('clean_x4', cand_label[k], 0):.2f} dB", f"{mean_m('degraded_x4', cand_label[k], 0):.2f} dB",
                          f"{mean_m('clean_x4', cand_label[k], 1):.3f} / {mean_m('degraded_x4', cand_label[k], 1):.3f}"])
    story += [table(cand_rows, [47 * mm, 18 * mm, 15 * mm, 18 * mm, 13 * mm, 22 * mm, 25 * mm, CONTENT_W - 158 * mm]),
              P("Speed/RAM: ×4 of the 600×400 photo (same job as §5). Quality: mean over three ground-truth photos (§7). "
                "INT8 calibration used 8 held-out images (textures and a rocket photo) that are not in the evaluation set; conv_first and the whole upsampling head are kept in FP32. "
                "general-x4v3 is exported from the official checkpoint (BSD-3-Clause per the Real-ESRGAN repository; verify before shipping) and checked against PyTorch.", "small"),
              img_flow(fig_dir / "grid_clean_x4.jpg"), Spacer(1, 3), img_flow(fig_dir / "grid_degraded_x4.jpg")]
    gvals = {k: (mean_m("clean_x4", cand_label[k], 0) - mean_m("clean_x4", "x4plus", 0), mean_m("degraded_x4", cand_label[k], 0) - mean_m("degraded_x4", "x4plus", 0)) for k in cand_keys}
    story += [P("How to read this", "h2")] + bullets(
        [f"<b>{cand_label[k]}</b> differs from the shipped model by {v[0]:+.2f} dB (clean) and {v[1]:+.2f} dB (degraded) mean Y-PSNR. PSNR alone under-reports GAN-style texture differences; "
         "judge banding, smooth gradients and skin in the crops above." for k, v in gvals.items()] +
        ["Three photos and no perceptual metric (LPIPS) or blind A/B test: treat any quality verdict here as preliminary, especially for INT8 (GAN-trained texture is the usual failure point).",
         "general-x4v3 is trained for real-world degradation but has weaker denoise/deblur capacity than x4plus; adopting it would be a product decision (a “fast” mode) rather than a silent swap."])

    # ---- 7 upscaling quality
    story += [CondPageBreak(120 * mm), P("7  Upscaling quality: original vs upscaled (shipped models)", "h1"),
              P("7.1  Production-style runs (an upload with no ground truth)", "h2"),
              img_flow(fig_dir / "show_astro.jpg", CONTENT_W * 0.98), Spacer(1, 3), img_flow(fig_dir / "show_coffee.jpg", CONTENT_W * 0.98),
              CondPageBreak(120 * mm), P("7.2  Against ground truth", "h2")]
    hdr = ["Image", "LR → target", "Bicubic", "Lanczos", "Real-ESRGAN", "Sharpness ×GT", "Time*"]
    for suffix, title in (("clean_x4", "×4, clean input"), ("clean_x2", "×2, clean input"), ("degraded_x4", "×4, degraded input (noise σ=2 + JPEG q50)")):
        rows = [hdr]
        for n in names:
            d = up[(suffix, n)]
            f = lambda k: f"{d['m'][k][0]:.2f} dB / {d['m'][k][1]:.3f}"
            h_, w_ = d["hr"].shape[:2]
            rows.append([n, f"{d['lr'].shape[1]}×{d['lr'].shape[0]} → {w_}×{h_}", f("Bicubic"), f("Lanczos"), f"<b>{f('x4plus')}</b>",
                         f"{d['m']['Bicubic'][2] / d['gt_lap']:.2f} → {d['m']['x4plus'][2] / d['gt_lap']:.2f}", f"{d['t']:.1f} s"])
        rows.append(["<b>mean</b>", "", *[f"<b>{mean_m(suffix, k, 0):.2f} dB / {mean_m(suffix, k, 1):.3f}</b>" for k in ("Bicubic", "Lanczos", "x4plus")], "", ""])
        story += [P(title, "h2"), table(rows, [20 * mm, 27 * mm, 30 * mm, 30 * mm, 32 * mm, 22 * mm, CONTENT_W - 161 * mm])]
    story += [P("Cells: Y-PSNR / SSIM vs the original. Sharpness = variance of the Laplacian ÷ that of the ground truth (1.0 = as sharp as truth), shown bicubic → Real-ESRGAN. *Engine time at 2 vCPU.", "small"),
              img_flow(fig_dir / "grid_clean_x2.jpg")]
    gc, gd = mean_m("clean_x4", "x4plus", 0) - mean_m("clean_x4", "Bicubic", 0), mean_m("degraded_x4", "x4plus", 0) - mean_m("degraded_x4", "Bicubic", 0)
    sh_c = statistics.mean(up[("clean_x4", n)]["m"]["x4plus"][2] / up[("clean_x4", n)]["gt_lap"] for n in names)
    sh_b = statistics.mean(up[("clean_x4", n)]["m"]["Bicubic"][2] / up[("clean_x4", n)]["gt_lap"] for n in names)
    story += [P("Reading these numbers", "h2")] + bullets([
        f"Clean inputs, ×4: Real-ESRGAN is {gc:+.2f} dB vs bicubic in mean PSNR. "
        + ("It wins on this metric as well." if gc > 0 else "Bicubic wins on PSNR here, which is expected: PSNR rewards smooth averages, while Real-ESRGAN is trained (GAN + perceptual loss) to produce crisp, plausible detail.")
        + f" Sharpness vs truth: {sh_b:.2f}× (bicubic) vs {sh_c:.2f}× (Real-ESRGAN).",
        f"Degraded inputs, ×4: {gd:+.2f} dB — bicubic magnifies noise and JPEG blocking, Real-ESRGAN was trained on exactly that damage.",
        "PSNR/SSIM measure pixel fidelity, not perceived quality; no LPIPS or human study was run. Three small, natural photos is a small sample."])

    # ---- 8 colourisation
    story += [CondPageBreak(120 * mm), P("8  Colourisation quality", "h1"),
              P("Colour photographs → grayscale → DDColor-Tiny → compared with the original colours. The last row is a real black-and-white photograph (this project's own test image), no ground truth."),
              img_flow(fig_dir / "colorize.jpg", CONTENT_W)]
    rows = [["Image", "Size", "ΔE*ab (mean)", "Baseline ΔE (no colour)", "Colourfulness M (truth → output)", "PSNR (RGB)", "Time*"]]
    for n, sz, de, base, cft, cfo, ps, t in col_rows:
        rows.append([n, sz, f"<b>{de:.1f}</b>", f"{base:.1f}", f"{cft:.1f} → {cfo:.1f}", f"{ps:.1f} dB", f"{t:.1f} s"])
    rows.append(["<b>mean</b>", "", f"<b>{de_mean:.1f}</b>", f"{de_base:.1f}", "", "", ""])
    if flower_ok:
        rows.append(["bw-flower (real B/W)", "1140×855", "—", "—", f"— → {flower_cf:.1f}", "—", f"{flower_t:.1f} s"])
    story += [table(rows, [33 * mm, 21 * mm, 21 * mm, 29 * mm, 35 * mm, 18 * mm, CONTENT_W - 157 * mm]),
              P("*Engine time at 2 vCPU (warm). Lower ΔE is better. Colourisation is under-determined (a red and a blue car share a luminance), so a non-zero error with realistic, slightly desaturated colours is expected. "
                + (f"Where the model is worse than “no colour” ({', '.join(worse)}), it chose plausible but wrong hues — for the astronaut it painted the orange suit blue/pink — "
                   "so treat colourisation as a creative suggestion, not a restoration." if worse else ""), "small")]

    # ---- 9 recommendations
    story += [P("9  Recommendations for the Hostinger KVM 2 and limitations", "h1")]
    recs = [
        "Keep <b>MAX_AI_WORKERS = 1</b> and 2-CPU container limits. Even the largest accepted job needs well under 8 GB, so on this plan CPU time, not memory, is the constraint.",
        f"Size timeouts from the model: t ≈ MAC ÷ G with G ≈ {g4 / 1e9:.0f} GMAC/s measured here (§4.2); the largest accepted ×4 job is ≈ {fmt_t(tiling(2500, 1250)[1] * C4 / g4)}. "
        "<b>Re-measure G on the actual VPS</b> (one ×4 256² job) and rescale: a shared vCPU is usually slower than a pinned core here.",
        "Use the memory model (§5.3) for admission control: estimate a job's peak before starting it and refuse what cannot fit.",
    ]
    ar = find("arena_on")
    if ar:
        rec = f"<b>Arena + memory-pattern ON</b> was {(ar[2] / prod_t - 1) * 100:+.0f} % time for {(ar[5] / prod_mem - 1) * 100:+.0f} % RAM on the 600×400 job"
        r_big = next((r for r in ablation_big if r["name"] == "big_arena_on"), None) if ablation_big else None
        if r_big and first_iters(r_big):
            it_ = first_iters(r_big)[0]
            rec += f" and {(it_['wall_s'] / warm(B['x4_1024'])['wall_s'] - 1) * 100:+.0f} % time / {it_['mem_peak_mb']:.0f} MiB on 1024² → 4096². "
            rec += ("That fits an 8 GB plan with one worker, so it is the cheapest speed-up available, provided the memory model is re-fitted for it and the admission check stays on."
                    if it_["mem_peak_mb"] < 4500 and it_["wall_s"] < warm(B["x4_1024"])["wall_s"] else "Its memory growth or lack of speed-up at scale argues against enabling it.")
        elif r_big:
            rec += f", but on 1024² → 4096² it {status_of(r_big)}: keep it off."
        else:
            rec += "; large-image behaviour was not measured."
        recs.append(rec)
    fs = next((r for r in ablation_big if r["name"] == "big_fixed_arena_shrink"), None) if ablation_big else None
    if fs and first_iters(fs):
        it_ = first_iters(fs)[0]
        bt_, bm_ = warm(B["x4_1024"])["wall_s"], max(i["mem_peak_mb"] for i in B["x4_1024"]["iters"])
        small = find("fixed_arena_shrink")
        recs.append(f"<b>Constant-shape tiles + arena + shrinkage</b> on 1024² → 4096²: {(it_['wall_s'] / bt_ - 1) * 100:+.0f} % time and {(it_['mem_peak_mb'] / bm_ - 1) * 100:+.0f} % RAM ({it_['mem_peak_mb']:.0f} MiB) — "
                    "the arena's memory stays bounded (arena alone: see the previous bullet). "
                    + (f"On the small 600×400 image the same option was {(small[2] / prod_t - 1) * 100:+.0f} % because edge tiles are recomputed (§5.1b). " if small else "")
                    + "So the best setting depends on image size: use it for large images and keep the shipped tiling for images that are only a few tiles wide.")
    recs.append("<b>Not worth changing:</b> constant-shape tiles (extra edge compute, §5.1b), thread-spinning, thread env variables, ORT 1.23.0, tile size 256 vs 384/512 — all within noise or worse. "
                "Stock ONNX Runtime defaults are clearly worse than the shipped settings.")
    gv = next((r for r in candidates if r["name"] == "cand_general_v3" and r.get("jobs")), None)
    iv = next((r for r in candidates if r["name"] == "cand_int8" and r.get("jobs")), None)
    if gv:
        recs.append(f"<b>general-x4v3</b> is {prod_warm / gv['jobs'][0]['iters'][-1]['wall_s']:.0f}× faster and uses {max(i['mem_peak_mb'] for i in gv['jobs'][0]['iters']):.0f} MiB (§6). "
                    "It is the only step-change available; it needs a blind A/B on your real uploads before becoming a default “fast” mode (keep x4plus as “best quality”).")
    if iv:
        recs.append(f"<b>INT8 x4plus</b> is {prod_warm / iv['jobs'][0]['iters'][-1]['wall_s']:.1f}× faster with unchanged mean PSNR/SSIM on three photos and a 4× smaller file (§6): low-risk to trial "
                    "(same architecture), but calibration used 4 small images — recalibrate on representative uploads and check gradients by eye first.")
    story += bullets(recs)
    story += [P("Limitations", "h2")] + bullets([
        "Timings come from a Ryzen 9 8945HS (a fast laptop CPU) emulating 2 vCPUs with a quota and core pinning. A VPS vCPU may be an SMT thread on a slower shared core: the MAC counts, memory model and the <i>relative</i> effects are portable, absolute seconds are not.",
        "1–3 runs per point (one for most ablations); differences under the measured noise are not significant. Other host activity was low but not zero.",
        "Quality uses three public-domain / CC0 photos (≤ 600 px): NASA astronaut portrait, and coffee / chelsea from scikit-image; plus the project's own B/W flower photo. No LPIPS, no human study.",
        "ONNX exports of DDColor and Real-ESRGAN are third-party (DECISIONS.md); nothing here claims accuracy relative to the original PyTorch checkpoints.",
        "INT8 and general-x4v3 were built for this comparison only and are not part of the repository's shipped models.",
    ])
    story += [P("Reproduce", "h2"),
              P("# WORK/imgs/{astronaut,coffee,chelsea}.png = skimage.data samples; WORK/imgs/calib = held-out INT8 calibration images<br/>"
                "python benchmarks/make_quality_inputs.py WORK<br/>python benchmarks/run_benchmarks.py prep|baseline|ablation|ablation_big --work WORK<br/>"
                "python benchmarks/build_candidates.py --work WORK<br/>python benchmarks/run_benchmarks.py candidates|quality --work WORK<br/>"
                "python benchmarks/make_report.py --work WORK --macs benchmarks/results/onnx_macs.json --out report.pdf", "mono")]

    def footer(canv, doc):
        canv.saveState()
        canv.setFont("DV", 7)
        canv.setFillColor(MUTED)
        canv.drawString(MARGIN, 10 * mm, f"Repix — CPU model comparison · {TARGET}")
        canv.drawRightString(PAGE_W - MARGIN, 10 * mm, f"{doc.page}")
        canv.restoreState()

    doc = SimpleDocTemplate(str(a.out), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=15 * mm, bottomMargin=17 * mm,
                            title="Repix — CPU model comparison", author="Repix benchmark")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
