"""Profil coureur : courbe vitesse/pente, vitesse critique, FC, durabilité (Theil-Sen).

Références : coût énergétique de la course en pente (Minetti et al., 2002, J Appl Physiol) ;
modèle vitesse/puissance critique (Monod & Scherrer 1965 ; Jones et al. 2019) ;
durabilité (Maunder et al., 2021, Sports Med).
"""
import numpy as np
from scipy.stats import theilslopes

from .course import smooth

W = 30  # fenêtre d'analyse (s)


def minetti_cost(g):
    """Coût de la course (J/kg/m), g = pente en fraction. Valide pour |g| <= 0.45."""
    g = np.clip(g, -0.45, 0.45)
    return 155.4 * g**5 - 30.4 * g**4 - 43.3 * g**3 + 46.3 * g**2 + 19.5 * g + 3.6


def gap_factor(g):
    """Facteur multiplicatif vitesse réelle -> vitesse équivalente à plat (iso-coût énergétique)."""
    return minetti_cost(g) / minetti_cost(0.0)


def _fill(x):
    x = x.copy()
    ok = np.isfinite(x)
    if ok.sum() < 2:
        return x
    idx = np.arange(len(x))
    x[~ok] = np.interp(idx[~ok], idx[ok], x[ok])
    return x


def to_1hz(a):
    """Ramène une activité sur une grille d'1 s (les trous > 10 s restent à NaN)."""
    t = a["t"]
    grid = np.arange(0, int(t[-1]) + 1)
    out = {"t": grid.astype(float)}
    for k in ("dist", "alt", "hr", "power"):
        v = a[k]
        ok = np.isfinite(v)
        out[k] = np.interp(grid, t[ok], v[ok]) if ok.sum() > 2 else np.full(len(grid), np.nan)
    # trous d'enregistrement (pauses automatiques) -> NaN
    gaps = np.diff(t, prepend=t[0]) > 10
    for i in np.where(gaps)[0]:
        out["dist"][int(t[i - 1]):int(t[i])] = np.nan
    return out


def windows(a):
    """Fenêtres de 30 s : vitesse, pente, vitesse équivalente à plat, FC, puissance."""
    g = to_1hz(a)
    n = (len(g["t"]) - 1) // W
    if n < 5 or not np.isfinite(g["dist"]).any():
        return None
    alt = smooth(_fill(g["alt"]), 9) if np.isfinite(g["alt"]).any() else None
    if alt is None:
        return None
    rows = []
    for i in range(n):
        s, e = i * W, (i + 1) * W
        dd = g["dist"][e] - g["dist"][s]
        if not np.isfinite(dd) or dd <= 0:
            continue
        v = dd / W
        grade = (alt[e] - alt[s]) / dd
        hr = np.nanmean(g["hr"][s:e]) if np.isfinite(g["hr"][s:e]).any() else np.nan
        pw = np.nanmean(g["power"][s:e]) if np.isfinite(g["power"][s:e]).any() else np.nan
        rows.append((s, v, grade, hr, pw, alt[e] - alt[s]))
    if not rows:
        return None
    r = np.array(rows)
    return {"t": r[:, 0], "v": r[:, 1], "grade": r[:, 2], "hr": r[:, 3], "power": r[:, 4], "dalt": r[:, 5],
            "gap": r[:, 1] * gap_factor(r[:, 2])}


BINS = [(-30, -15), (-15, -8), (-8, -3), (-3, 3), (3, 8), (8, 15), (15, 25), (25, 45)]
BIN_LABELS = ["descente raide <-15%", "descente -15/-8%", "descente douce -8/-3%", "roulant ±3%",
              "montée douce 3/8%", "montée 8/15%", "montée raide 15/25%", "très raide >25%"]


def estimate_hrmax(wins):
    allhr = np.concatenate([w["hr"][np.isfinite(w["hr"])] for w in wins])
    return float(np.percentile(allhr, 99.8))


def grade_profile(wins, hrmax):
    """Vitesse médiane par classe de pente en effort sous-maximal (70-90 % FCmax), et indice vs Minetti."""
    v = np.concatenate([w["v"] for w in wins])
    g = np.concatenate([w["grade"] for w in wins]) * 100
    hr = np.concatenate([w["hr"] for w in wins])
    dalt = np.concatenate([w["dalt"] for w in wins])
    pw = np.concatenate([w["power"] for w in wins])
    sub = np.isfinite(hr) & (hr >= 0.70 * hrmax) & (hr <= 0.90 * hrmax) & (v > 0.7)
    res = []
    base_v = None
    for (lo, hi), label in zip(BINS, BIN_LABELS):
        m = sub & (g >= lo) & (g < hi)
        n = int(m.sum())
        if n < 20:
            res.append({"label": label, "n_min": n * W / 60, "speed_kmh": None})
            continue
        gm = np.median(g[m]) / 100
        row = {"label": label, "n_min": n * W / 60, "grade_med": float(gm * 100),
               "speed_kmh": float(np.median(v[m]) * 3.6),
               "hr": float(np.median(hr[m])),
               "vam": float(np.median(dalt[m]) / W * 3600) if lo >= 3 else None,
               "power": float(np.nanmedian(pw[m])) if np.isfinite(pw[m]).any() else None}
        res.append(row)
        if label.startswith("roulant"):
            base_v = row["speed_kmh"]
    # indice = vitesse observée / vitesse attendue (Minetti, à effort constant) rapportée au roulant
    if base_v:
        exp_costs = {}
        for row in res:
            if row["speed_kmh"] is None:
                continue
            expected = base_v * minetti_cost(0.0) / minetti_cost(row["grade_med"] / 100)
            row["expected_kmh"] = float(expected)
            row["index"] = row["speed_kmh"] / expected
        idx = [r["index"] for r in res if r.get("index")]
        ref = np.median(idx) if idx else 1
        for row in res:
            if row.get("index"):
                row["index_rel"] = row["index"] / ref
    return res


DURATIONS = [60, 120, 180, 300, 600, 1200, 1800, 2700, 3600, 5400, 7200]


def mean_max(x, d):
    c = np.cumsum(np.insert(np.nan_to_num(x), 0, 0))
    if len(x) < d:
        return None, None
    s = (c[d:] - c[:-d]) / d
    i = int(np.argmax(s))
    return float(s[i]), i


def critical_model(acts_1hz):
    """Courbe vitesse équivalente (GAP) et puissance max moyenne ; modèle CS/D' et CP/W' (3-30 min)."""
    out = {"gap": {}, "power": {}, "hr_at_best": {}, "hr_at_best_power": {}}
    for d in DURATIONS:
        best, bestp, hr_best, hr_bestp = 0, 0, None, None
        for g in acts_1hz:
            v = np.diff(g["dist"], prepend=g["dist"][0])
            ok = np.isfinite(v) & (v >= 0) & (v < 8)
            alt = smooth(_fill(g["alt"]), 9) if np.isfinite(g["alt"]).any() else None
            if alt is None or ok.sum() < d:
                continue
            gr = np.gradient(smooth(alt, 15)) / np.maximum(smooth(np.where(ok, v, 0.0), 15), 0.5)
            gap_s = np.where(ok, v * gap_factor(gr), 0.0)
            m, i = mean_max(gap_s, d)
            if m and m > best:
                best = m
                seg_hr = g["hr"][i:i + d]
                hr_best = float(np.nanmean(seg_hr)) if np.isfinite(seg_hr).any() else None
            p, ip = mean_max(np.where(np.isfinite(g["power"]), g["power"], 0.0), d)
            if p and p > bestp:
                bestp = p
                seg_hr = g["hr"][ip:ip + d]
                hr_bestp = float(np.nanmean(seg_hr)) if np.isfinite(seg_hr).any() else None
        if best:
            out["gap"][d] = best
            out["hr_at_best"][d] = hr_best
        if bestp:
            out["power"][d] = bestp
            out["hr_at_best_power"][d] = hr_bestp
    for key in ("gap", "power"):
        ds = np.array([d for d in (180, 300, 600, 1200, 1800) if d in out[key]], dtype=float)
        if len(ds) >= 3:
            vals = np.array([out[key][int(d)] for d in ds])
            work = vals * ds   # distance équivalente (m) ou travail (J/kg ou J)
            slope, intercept = np.polyfit(ds, work, 1)
            out[key + "_cs"] = float(slope)
            out[key + "_dprime"] = float(intercept)
    return out


def durability(acts, hrmax, min_dur_s=5400, warmup_s=1200, blk=600):
    """Dérive de l'efficience (vitesse équivalente / FC) au fil des sorties longues, pente de Theil-Sen.

    Pour ne pas confondre fatigue et profil du terrain, on ne garde que les fenêtres en terrain
    modéré (pente entre -3 % et +8 %), en course (> 1,5 m/s) et en effort sous-maximal (65-92 % FCmax),
    après l'échauffement. Pente exprimée en %/h relative à l'efficience du début de sortie.
    """
    per, px, py = [], [], []
    for info, w in acts:
        if info["duration_s"] < min_dur_s or w is None:
            continue
        t, hr, gap, gr, v = w["t"], w["hr"], w["gap"], w["grade"] * 100, w["v"]
        ok = (t >= warmup_s) & np.isfinite(hr) & (gr > -3) & (gr < 8) & (v > 1.5) &              (hr >= 0.65 * hrmax) & (hr <= 0.92 * hrmax)
        xs, ys = [], []
        for b in range(int(t.max() // blk) + 1):
            m = ok & (t >= b * blk) & (t < (b + 1) * blk)
            if m.sum() < 6:        # au moins 3 min de données valides dans le bloc
                continue
            xs.append((b + 0.5) * blk / 3600)
            ys.append(np.median(gap[m] / hr[m]))
        if len(xs) < 5 or max(xs) - min(xs) < 0.75:
            continue
        xs, ys = np.array(xs), np.array(ys)
        slope, intercept, lo, hi = theilslopes(ys, xs)
        ref = float(np.median(ys[: max(2, len(ys) // 4)]))
        px.extend(xs.tolist())
        py.extend((ys / ref).tolist())
        per.append({"file": info["file"], "dur_h": info["duration_s"] / 3600, "n_blocks": len(xs),
                    "pct_per_h": float(slope / ref * 100), "ci_lo": float(lo / ref * 100), "ci_hi": float(hi / ref * 100)})
    agg = None
    if per:
        vals = np.array([p["pct_per_h"] for p in per])
        agg = {"median_pct_per_h": float(np.median(vals)), "n": len(per),
               "q25": float(np.percentile(vals, 25)), "q75": float(np.percentile(vals, 75))}
        sl, _, lo, hi = theilslopes(np.array(py), np.array(px))
        agg.update({"pooled_pct_per_h": float(sl * 100), "pooled_lo": float(lo * 100), "pooled_hi": float(hi * 100),
                    "pooled_blocks": len(px)})
    return per, agg
