"""Fully procedural animated short: no photos, no AI images. Everything is drawn by code.

Usage:
  procedural.py OUT.mp4 AUDIO.mp3            # full render
  procedural.py --stills 1,6,9 AUDIO.mp3     # write still_<t>.png for quick looks
"""
import subprocess
import sys

import cv2
import numpy as np

W, H, FPS = 1080, 1920, 30
F32 = np.float32
DUR = [5.6, 2.4, 2.3, 4.4, 2.7, 4.6]
STARTS = np.cumsum([0] + DUR)
TOTAL = float(STARTS[-1])
XFADE = 0.35
INK = (7, 9, 24)


def smooth(p):
    p = min(max(p, 0.0), 1.0)
    return p * p * (3 - 2 * p)


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def arr(c):
    return np.array(c, dtype=F32)


# ---------------------------------------------------------------- primitives
def sky(top, mid, hor, yh):
    cv = np.zeros((H, W, 3), np.uint8)
    ys = np.linspace(0, 1, yh, dtype=F32)[:, None]
    a, b = np.clip(ys / 0.6, 0, 1), np.clip((ys - 0.6) / 0.4, 0, 1)
    col = arr(top) + (arr(mid) - arr(top)) * a + (arr(hor) - arr(mid)) * b
    cv[:yh] = np.clip(col, 0, 255).astype(np.uint8)[:, None, :]
    return cv


def water_base(cv, yh, hor, deep):
    n = H - yh
    wt = np.linspace(0, 1, n, dtype=F32)[:, None]
    col = arr(hor) * 0.5 * (1 - wt) + arr(deep) * wt
    cv[yh:] = np.clip(col, 0, 255).astype(np.uint8)[:, None, :]


def mountains(cv, yh, off, base_off, amp, color, seed):
    xs = np.arange(-40, W + 60, 18, dtype=F32)
    r = np.random.RandomState(seed)
    p = r.uniform(0, 6.28, 3)
    h = 0.55 * np.sin(0.0055 * (xs + off) + p[0]) + 0.3 * np.sin(0.0131 * (xs + off) + p[1]) + 0.15 * np.sin(0.031 * (xs + off) + p[2])
    ys = yh - base_off - amp * (0.5 + 0.5 * h)
    pts = np.stack([xs, ys], 1).astype(np.int32)
    poly = np.vstack([pts, [[W + 60, yh + 2], [-40, yh + 2]]])
    cv2.fillPoly(cv, [poly], tuple(int(v) for v in color), cv2.LINE_AA)


def pine(cv, x, by, h, color):
    c = tuple(int(v) for v in color)
    cv2.rectangle(cv, (int(x - h * 0.02), int(by - h * 0.12)), (int(x + h * 0.02), int(by)), c, -1)
    for k in range(5):
        top = by - h + k * h * 0.16
        bot = top + h * 0.36
        hw = h * 0.075 * (k + 1.6)
        cv2.fillPoly(cv, [np.array([[x, top], [x - hw, bot], [x + hw, bot]], np.int32)], c, cv2.LINE_AA)


def pines(cv, off, by, hmin, hmax, spacing, color, seed):
    r = np.random.RandomState(seed)
    n = int((W + 400) / spacing) + 2
    hs = r.uniform(hmin, hmax, n)
    jit = r.uniform(-spacing * 0.3, spacing * 0.3, n)
    for i in range(n):
        x = (i * spacing + jit[i] + off) % (n * spacing) - 150
        pine(cv, x, by, hs[i], color)


def lake(cv, yh, t, sigma=2.0):
    R = min(yh, H - yh)
    src = np.ascontiguousarray(cv[yh - R:yh][::-1])
    src = cv2.GaussianBlur(src, (0, 0), sigmaX=sigma * 1.5, sigmaY=sigma)
    ys = np.arange(R, dtype=F32)[:, None]
    xs = np.arange(W, dtype=F32)[None, :]
    dx = (4 + ys * 0.07) * np.sin(ys * 0.09 + t * 1.6 + xs * 0.004)
    mx = (xs + dx).astype(F32)
    my = np.broadcast_to(ys, (R, W)).astype(F32)
    refl = cv2.remap(src, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    fade = (1 - 0.75 * ys / R)[..., None]
    wat = cv[yh:yh + R].astype(F32)
    cv[yh:yh + R] = np.clip(wat * (1 - 0.8 * fade) + refl * 0.8 * fade, 0, 255).astype(np.uint8)


def stars(fx, t, alpha, seed=3, n=170, ymax=900, rot=0.0):
    r = np.random.RandomState(seed)
    xs, ys = r.uniform(0, W, n), r.uniform(0, ymax, n)
    ph, sp = r.uniform(0, 6.28, n), r.uniform(1, 3.5, n)
    for i in range(n):
        tw = 0.35 + 0.65 * np.sin(sp[i] * t + ph[i]) ** 2
        v = int(255 * alpha * tw * (0.45 + 0.55 * (i % 3) / 2))
        x = (xs[i] + rot * t) % W
        cv2.circle(fx, (int(x), int(ys[i])), 1 + (i % 7 == 0), (v, v, int(v * 0.95)), -1, cv2.LINE_AA)


def ground(cv, by, color, seed=5, t=0.0, tuft=(30, 50, 40)):
    pts = [[-20, H + 10], [-20, by + 55], [260, by + 18], [540, by - 4], [820, by + 16], [W + 20, by + 60], [W + 20, H + 10]]
    cv2.fillPoly(cv, [np.array(pts, np.int32)], tuple(int(v) for v in color), cv2.LINE_AA)
    r = np.random.RandomState(seed)
    for i in range(46):
        x = r.uniform(-10, W + 10)
        yb = by + 55 - 38 * np.sin(np.clip(x / W, 0, 1) * np.pi) + r.uniform(0, 60)
        hgt = r.uniform(40, 120)
        sw = np.sin(t * 1.3 + i) * 10
        cv2.fillPoly(cv, [np.array([[x - 7, yb], [x + sw, yb - hgt], [x + 7, yb]], np.int32)], tuple(int(v) for v in color), cv2.LINE_AA)
    return r


def add_glow(buf, x, y, r, color, k):
    """buf is half-res float; gaussian glow patch."""
    k = k * 0.26
    hx, hy, hr = x / 2, y / 2, r / 2
    ext = int(hr * 3)
    x1, x2, y1, y2 = int(hx) - ext, int(hx) + ext + 1, int(hy) - ext, int(hy) + ext + 1
    cx1, cx2, cy1, cy2 = max(x1, 0), min(x2, buf.shape[1]), max(y1, 0), min(y2, buf.shape[0])
    if cx2 <= cx1 or cy2 <= cy1:
        return
    gx = np.arange(cx1, cx2, dtype=F32)[None, :] - hx
    gy = np.arange(cy1, cy2, dtype=F32)[:, None] - hy
    g = np.exp(-(gx * gx + gy * gy) / (2 * hr * hr))
    buf[cy1:cy2, cx1:cx2] += g[..., None] * arr(color)[None, None, :] / 255 * k


# ------------------------------------------------------------------ characters
def figure(cv, fx, cx, by, sc, t, rim):
    br = np.sin(2 * np.pi * t / 4.6)
    lift = 1 + 0.02 * br

    def T(p, scale_y=1.0, around=-70):
        return [(cx + x * sc / 1.5 * 1.0, by + (around + (y - around) * scale_y) * sc / 1.5) for x, y in p]

    legs = [(-190, -18), (-135, -64), (0, -78), (135, -64), (190, -18), (140, 6), (0, 14), (-140, 6)]
    torso = [(-74, -70), (-88, -185), (-100, -205), (-24, -240), (24, -240), (100, -205), (88, -185), (74, -70)]
    head_c = (0, -282)
    arms = [((-96, -200), (-128, -120), (-158, -40)), ((96, -200), (128, -120), (158, -40))]
    for col, dx_, dy_ in ((rim, 3.5, -3.5), (INK, 0, 0)):
        o = np.array([dx_ * sc / 1.5, dy_ * sc / 1.5])
        cv2.fillPoly(cv, [(np.array(T(legs)) + o).astype(np.int32)], col, cv2.LINE_AA)
        cv2.fillPoly(cv, [(np.array(T(torso, lift)) + o).astype(np.int32)], col, cv2.LINE_AA)
        for a in arms:
            pts = (np.array(T(a, lift)) + o).astype(np.int32)
            cv2.polylines(cv, [pts], False, col, int(34 * sc / 1.5), cv2.LINE_AA)
        hc = np.array(T([head_c], lift)[0]) + o
        cv2.circle(cv, (int(hc[0]), int(hc[1])), int(42 * sc / 1.5), col, -1, cv2.LINE_AA)
    return {"head": T([head_c], lift)[0], "chest": T([(0, -170)], lift)[0], "rhand": T([(158, -40)])[0], "lhand": T([(-158, -40)])[0],
            "top": T([(0, -330)], lift)[0]}


def butterfly(fx, x, y, s, t, heading=0.0, k=1.0):
    f = 0.18 + 0.82 * abs(np.cos(2 * np.pi * 2.6 * t))
    c, sn = np.cos(heading), np.sin(heading)

    def P(pts, side):
        out = []
        for px, py in pts:
            px = px * f * side
            out.append((x + (px * c - py * sn) * s, y + (px * sn + py * c) * s))
        return np.array(out, np.int32)

    up = [(0.05, -0.05), (0.55, -1.15), (1.55, -1.0), (1.3, -0.1), (0.4, 0.1)]
    lo = [(0.05, 0.05), (0.95, 0.15), (1.1, 0.95), (0.5, 1.15), (0.1, 0.45)]
    cA, cB = tuple(int(v * k) for v in (255, 190, 80)), tuple(int(v * k) for v in (255, 238, 175))
    for side in (-1, 1):
        for pts, scale in ((up, 1.0), (lo, 1.0)):
            cv2.fillPoly(fx, [P(pts, side)], cA, cv2.LINE_AA)
            cen = np.mean(np.array(pts), 0)
            small = [(cen[0] + (px - cen[0]) * 0.55, cen[1] + (py - cen[1]) * 0.55) for px, py in pts]
            cv2.fillPoly(fx, [P(small, side)], cB, cv2.LINE_AA)
    cv2.line(fx, (int(x - 0.1 * sn * s), int(y - 0.55 * c * s)), (int(x + 0.1 * sn * s), int(y + 0.9 * c * s)), (255, 245, 210), max(2, int(s * 0.12)), cv2.LINE_AA)


def firefly(fx, light, pts_fn, t, dur, color=(255, 225, 130)):
    for k in range(18):
        u = t - k * 0.03
        if u < 0:
            continue
        x, y = pts_fn(min(u / dur, 1.0))
        a = (1 - k / 18) ** 1.6
        cv2.circle(fx, (int(x), int(y)), max(1, int(5 * a + 1)), tuple(int(c * a) for c in color), -1, cv2.LINE_AA)
    x, y = pts_fn(min(t / dur, 1.0))
    cv2.circle(fx, (int(x), int(y)), 7, (255, 250, 220), -1, cv2.LINE_AA)
    add_glow(light, x, y, 60, color, 1.4)


def storm(fx, cx, cy, t, calm, R=235):
    """Chaotic scribbles that relax into concentric calm circles as calm -> 1."""
    ch = 1 - calm
    for k in range(15):
        th = np.linspace(0, 2 * np.pi * (1.4 + 0.1 * (k % 4)), 260)
        base = R * (0.5 + 0.5 * (k / 14)) * (0.5 + 0.5 * th / th[-1] * (1 - calm * 0.6) + 0.5 * calm)
        ph = k * 1.7 + t * (2.3 + (k % 3))
        noise = ch * R * (0.28 * np.sin(3.1 * th + ph) + 0.2 * np.sin(5.3 * th - ph * 1.3) + 0.12 * np.sin(9 * th + ph * 0.7))
        r = base + noise
        rot = t * (1.6 * ch + 0.15)
        x = cx + r * np.cos(th + rot + k) + ch * 22 * np.sin(t * 7 + k)
        y = cy + r * np.sin(th + rot + k) * 0.82 + ch * 22 * np.cos(t * 6 + k)
        pts = np.stack([x, y], 1).astype(np.int32)
        v = 0.3 - 0.08 * calm
        col = (int(150 * v + 80 * (k % 2)), int(185 * v + 40 * (k % 2)), int(255 * v))
        cv2.polylines(fx, [pts], False, col, 2, cv2.LINE_AA)


# ---------------------------------------------------------------------- scenes
def scene1(tl, gt, env):  # chaos -> calm  (0-5.6s)
    p = tl / DUR[0]
    yh = 1180
    cv = sky((16, 20, 62), (74, 58, 132), (255, 150, 92), yh)
    fx = np.zeros_like(cv)
    light = np.zeros((H // 2, W // 2, 3), F32)
    stars(fx, gt, 0.9 * (1 - p * 0.5), 3, 150, 780)
    sx = 790 - 30 * p
    cv2.circle(cv, (int(sx), yh - 8), 62, (255, 214, 130), -1, cv2.LINE_AA)
    mountains(cv, yh, 40 * tl, 0, 180, (74, 60, 120), 11)
    mountains(cv, yh, 80 * tl, 0, 120, (44, 40, 92), 12)
    water_base(cv, yh, (255, 150, 92), (12, 14, 44))
    lake(cv, yh, gt)
    add_glow(light, sx, yh - 8, 230, (255, 170, 95), 1.3 * (0.8 + 0.4 * env))
    by = 1590
    ground(cv, by, INK, 5, gt)
    info = figure(cv, fx, 540, by, 1.5, gt, (255, 170, 100))
    calm = smooth((tl - 3.3) / 2.0)
    storm(fx, info["head"][0], info["head"][1] - 330, gt, calm)
    add_glow(light, info["head"][0], info["head"][1] - 330, 150, (150, 190, 255), 0.18 + 0.25 * (1 - calm))
    return cv, fx, light


def scene2(tl, gt, env):  # firefly in the forest  (5.6-8.0)
    p = tl / DUR[1]
    yh = 1050
    cv = sky((6, 10, 36), (22, 38, 84), (60, 88, 130), yh)
    fx = np.zeros_like(cv)
    light = np.zeros((H // 2, W // 2, 3), F32)
    stars(fx, gt, 0.85, 9, 140, 650)
    cv2.circle(cv, (770, 470), 92, (232, 238, 255), -1, cv2.LINE_AA)
    add_glow(light, 770, 470, 260, (140, 170, 255), 1.0 + 0.3 * env)
    mountains(cv, yh, 30 * tl, 0, 210, (34, 52, 98), 21)
    mountains(cv, yh, 60 * tl, 0, 130, (22, 36, 76), 22)
    cv[yh:] = np.array([14, 24, 46], np.uint8)
    pines(cv, 40 * tl, yh + 40, 230, 330, 130, (14, 28, 54), 31)
    # path ribbon in perspective
    ys = np.linspace(yh, H, 30)
    cxp = 560 + 150 * np.sin((ys - yh) * 0.0042 + 0.6) * (ys - yh) / (H - yh) * 1.4
    wd = 14 + (ys - yh) * 0.42
    poly = np.vstack([np.stack([cxp - wd, ys], 1), np.stack([cxp + wd, ys], 1)[::-1]]).astype(np.int32)
    cv2.fillPoly(cv, [poly], (36, 52, 88), cv2.LINE_AA)
    pines(cv, 80 * tl, H - 20, 650, 900, 360, (6, 12, 26), 33)
    by = 1560
    info = figure(cv, fx, 230, by, 1.0, gt, (140, 170, 255))

    def fpath(u):
        yy = by - 330 - (by - 330 - yh) * smooth(u) ** 0.9
        xx = 300 + (cxp[min(int((yy - yh) / (H - yh) * 29), 29)] - 300) * smooth(u) + 60 * np.sin(u * 9) * (1 - u)
        return xx, yy
    firefly(fx, light, fpath, tl, DUR[1] * 0.95)
    mist = np.exp(-((np.arange(H, dtype=F32)[:, None] - 1130) / 90) ** 2) * (0.5 + 0.5 * np.sin(np.arange(W, dtype=F32)[None, :] * 0.004 + gt * 0.6))
    cv = np.clip(cv.astype(F32) + mist[..., None] * np.array([40, 55, 80], F32), 0, 255).astype(np.uint8)
    return cv, fx, light


def scene3(tl, gt, env):  # butterfly returns  (8.0-10.3)
    p = tl / DUR[2]
    yh = 1150
    cv = sky((24, 28, 82), (110, 70, 130), (255, 170, 100), yh)
    fx = np.zeros_like(cv)
    light = np.zeros((H // 2, W // 2, 3), F32)
    stars(fx, gt, 0.35, 4, 80, 500)
    sx = 800
    cv2.circle(cv, (sx, yh - 5), 64, (255, 218, 140), -1, cv2.LINE_AA)
    mountains(cv, yh, 20 * tl, 0, 170, (96, 62, 120), 41)
    mountains(cv, yh, 50 * tl, 0, 110, (52, 42, 96), 42)
    water_base(cv, yh, (255, 170, 100), (14, 16, 48))
    lake(cv, yh, gt)
    add_glow(light, sx, yh - 5, 240, (255, 180, 100), 1.3 * (0.8 + 0.4 * env))
    by = 1600
    ground(cv, by, INK, 6, gt)
    info = figure(cv, fx, 540, by, 1.7, gt, (255, 180, 110))
    hx, hy = info["rhand"]
    u = smooth(p)
    bx = hx + 330 * np.sin(np.pi * u) * 1.0 + 40 * np.sin(u * 14)
    by_ = hy - 80 - 520 * np.sin(np.pi * u) ** 0.8
    hd = 0.35 * np.sin(u * 9)
    butterfly(fx, bx, by_ - 0, 62, gt, hd)
    add_glow(light, bx, by_, 120, (255, 190, 90), 1.5 * (0.8 + 0.4 * env))
    return cv, fx, light


def hover(info, gt, dy=170):
    hx, hy = info["rhand"]
    return hx + 26 * np.sin(gt * 1.1), hy - dy + 18 * np.sin(gt * 1.9 + 1)


def scene4(tl, gt, env):  # calm, stress dissolves (10.3-14.7)
    p = tl / DUR[3]
    yh = 1180
    cv = sky(mix((24, 28, 82), (60, 62, 130), p), mix((110, 70, 130), (230, 130, 120), p), mix((255, 170, 100), (255, 205, 130), p), yh)
    fx = np.zeros_like(cv)
    light = np.zeros((H // 2, W // 2, 3), F32)
    stars(fx, gt, 0.35 * (1 - p), 4, 80, 500)
    sy = yh - 8 - 150 * smooth(p)
    cv2.circle(cv, (700, int(sy)), 74, (255, 226, 150), -1, cv2.LINE_AA)
    mountains(cv, yh, 20 * tl, 0, 170, mix((96, 62, 120), (150, 96, 130), p), 51)
    mountains(cv, yh, 50 * tl, 0, 110, mix((52, 42, 96), (86, 64, 110), p), 52)
    water_base(cv, yh, (255, 190, 110), (14, 18, 52))
    lake(cv, yh, gt)
    add_glow(light, 700, sy, 270, (255, 195, 110), 1.4 * (0.8 + 0.4 * env))
    by = 1600
    lay = np.zeros_like(cv)
    for k in range(3):  # ripples on the lake (behind the figure)
        ph = ((tl * 0.55 + k / 3) % 1.0)
        rx = 60 + 520 * ph
        a = (1 - ph) ** 1.3
        cv2.ellipse(lay, (540, 1400), (int(rx), int(rx * 0.16)), 0, 0, 360, (int(255 * a), int(200 * a), int(120 * a)), 3, cv2.LINE_AA)
    cv = cv2.add(cv, lay)
    ground(cv, by, INK, 6, gt)
    info = figure(cv, fx, 540, by, 1.55, gt, (255, 190, 120))
    for k in range(9):  # stress wisps dissolving upward
        ph = ((tl * 0.45 + k / 9) % 1.0)
        wx = info["head"][0] + 70 * np.sin(k * 2.1 + ph * 5) * ph
        wy = info["head"][1] - 70 - 380 * ph
        a = (1 - ph) ** 1.5 * 0.7
        cv2.circle(fx, (int(wx), int(wy)), int(16 + 36 * ph), (int(120 * a), int(135 * a), int(190 * a)), -1, cv2.LINE_AA)
    bx, by_ = hover(info, gt)
    butterfly(fx, bx, by_, 52, gt, 0.15 * np.sin(gt))
    add_glow(light, bx, by_, 90, (255, 190, 90), 1.2)
    return cv, fx, light


def scene5(tl, gt, env):  # focus + deep sleep (14.7-17.4)
    p = tl / DUR[4]
    yh = 1180
    cv = sky((4, 6, 28), (16, 24, 70), (52, 70, 120), yh)
    fx = np.zeros_like(cv)
    light = np.zeros((H // 2, W // 2, 3), F32)
    stars(fx, gt, 1.0, 17, 230, 1000, rot=6)
    mx, my = 560, 520
    cv2.circle(cv, (mx, my), 120, (236, 241, 255), -1, cv2.LINE_AA)
    cv2.circle(cv, (mx + 38, my - 22), 22, (214, 222, 245), -1, cv2.LINE_AA)
    cv2.circle(cv, (mx - 36, my + 34), 15, (216, 224, 247), -1, cv2.LINE_AA)
    add_glow(light, mx, my, 330, (140, 170, 255), 1.2 * (0.85 + 0.3 * env))
    mountains(cv, yh, 15 * tl, 0, 170, (26, 38, 82), 61)
    mountains(cv, yh, 40 * tl, 0, 105, (16, 24, 58), 62)
    water_base(cv, yh, (60, 82, 130), (6, 8, 30))
    lake(cv, yh, gt)
    # moonbeam focusing on the figure
    by = 1600
    beam = np.array([[mx - 50, my + 80], [mx + 50, my + 80], [540 + 280, by + 10], [540 - 280, by + 10]], np.int32)
    lay = np.zeros_like(cv)
    cv2.fillPoly(lay, [beam], (20, 30, 60), cv2.LINE_AA)
    cv = cv2.add(cv, cv2.GaussianBlur(lay, (0, 0), 6))
    ground(cv, by, INK, 6, gt)
    info = figure(cv, fx, 540, by, 1.45, gt, (150, 180, 255))
    # shooting star
    if 0.5 < tl < 1.3:
        q = (tl - 0.5) / 0.8
        x0, y0 = 880 - 560 * q, 180 + 340 * q
        cv2.line(fx, (int(x0), int(y0)), (int(x0 + 150), int(y0 - 90)), (int(255 * (1 - q)), int(255 * (1 - q)), int(255 * (1 - q))), 3, cv2.LINE_AA)
    bx, by_ = hover(info, gt, 150)
    butterfly(fx, bx, by_, 50, gt, 0.15 * np.sin(gt), 0.85)
    add_glow(light, bx, by_, 90, (180, 200, 255), 1.0)
    return cv, fx, light


def scene6(tl, gt, env):  # sunrise + breathing  (17.4-22.0)
    p = tl / DUR[5]
    yh = 1180
    cv = sky(mix((40, 40, 110), (90, 80, 160), p), mix((190, 110, 130), (255, 170, 120), p), mix((255, 180, 110), (255, 225, 150), p), yh)
    fx = np.zeros_like(cv)
    light = np.zeros((H // 2, W // 2, 3), F32)
    sy = yh - 40 - 240 * smooth(p)
    sx = 540
    lay = np.zeros_like(cv)
    for k in range(14):  # slow god rays
        a = gt * 0.05 + k * np.pi * 2 / 14
        x2, y2 = sx + 2400 * np.cos(a), sy + 2400 * np.sin(a)
        cv2.line(lay, (sx, int(sy)), (int(x2), int(y2)), (26, 18, 8), 70, cv2.LINE_AA)
    cv = cv2.add(cv, cv2.GaussianBlur(lay, (0, 0), 8))
    cv2.circle(cv, (sx, int(sy)), 118, (255, 240, 190), -1, cv2.LINE_AA)
    mountains(cv, yh, 12 * tl, 0, 170, mix((120, 80, 130), (170, 110, 140), p), 71)
    mountains(cv, yh, 30 * tl, 0, 105, mix((70, 54, 112), (110, 80, 124), p), 72)
    water_base(cv, yh, (255, 200, 120), (30, 28, 70))
    lake(cv, yh, gt)
    add_glow(light, sx, sy, 380, (255, 205, 120), 1.6 * (0.85 + 0.3 * env))
    by = 1600
    # sun glitter column on the water
    lay2 = np.zeros_like(cv)
    r = np.random.RandomState(2)
    for i in range(40):
        yy = yh + 20 + r.uniform(0, 380)
        ww = r.uniform(20, 140) * (0.4 + (yy - yh) / 400)
        a = 0.5 + 0.5 * np.sin(gt * 3 + i)
        xx = sx + r.uniform(-1, 1) * (30 + (yy - yh) * 0.25) + 14 * np.sin(gt * 2 + i)
        cv2.line(lay2, (int(xx - ww / 2), int(yy)), (int(xx + ww / 2), int(yy)), (int(255 * a * 0.7), int(225 * a * 0.7), int(150 * a * 0.7)), 2, cv2.LINE_AA)
    cv = cv2.add(cv, lay2)
    ground(cv, by, INK, 6, gt)
    info = figure(cv, fx, 540, by, 1.55, gt, (255, 205, 130))
    # breathing ring around the chest: inhale / exhale
    cxr, cyr = info["chest"]
    ph = 0.5 - 0.5 * np.cos(2 * np.pi * tl / 4.6)
    rad = 150 + 120 * ph
    fade = smooth(tl / 0.7) * (1 - smooth((tl - 4.2) / 0.4))
    for r_, a_ in ((rad, 1.0), (rad * 1.28, 0.45), (rad * 1.55, 0.2)):
        v = a_ * fade
        cv2.circle(fx, (int(cxr), int(cyr)), int(r_), (int(255 * v), int(215 * v), int(140 * v)), 5, cv2.LINE_AA)
    add_glow(light, cxr, cyr, rad * 1.1, (255, 200, 120), 0.5 * fade)
    bx, by_ = hover(info, gt, 190)
    butterfly(fx, bx, by_, 56, gt, 0.15 * np.sin(gt))
    add_glow(light, bx, by_, 100, (255, 200, 100), 1.3)
    return cv, fx, light


SCENES = [scene1, scene2, scene3, scene4, scene5, scene6]
TINTS = [(255, 205, 120), (210, 230, 255), (255, 205, 110), (255, 200, 110), (200, 225, 255), (255, 215, 130)]

# ------------------------------------------------------------ global post-fx
rs = np.random.RandomState(7)
N = 50
P = dict(x=rs.uniform(0, W, N), y=rs.uniform(0, H, N), z=rs.uniform(0.25, 1, N), ph=rs.uniform(0, 6.28, N),
         vy=rs.uniform(10, 36, N), vx=rs.uniform(-8, 8, N), tw=rs.uniform(1.5, 4, N))


def spr(r):
    k = np.arange(-r, r + 1, dtype=F32)
    return np.exp(-((k[None, :] ** 2 + k[:, None] ** 2) / (2 * (r / 2.6) ** 2)))


SPR = {r: spr(r) for r in (5, 8, 12, 18)}
VIG = (1 - 0.40 * np.clip(np.hypot(*np.meshgrid((np.arange(W) - W / 2) / (W / 2), (np.arange(H) - H / 2) / (H / 2))) - 0.55, 0, 1) ** 1.5)[..., None].astype(F32)


def tint_at(t):
    i = int(min(np.searchsorted(STARTS, t, side="right") - 1, 5))
    return arr(TINTS[i]) / 255


def particles(f, t, env):
    tint = tint_at(t)
    for i in range(N):
        z = P["z"][i]
        x = (P["x"][i] + 60 * z * np.sin(0.7 * t + P["ph"][i]) + P["vx"][i] * t) % W
        y = (P["y"][i] - P["vy"][i] * z * t) % H
        r = 5 if z < 0.4 else 8 if z < 0.65 else 12 if z < 0.88 else 18
        b = (0.45 + 0.55 * np.sin(P["tw"][i] * t + P["ph"][i]) ** 2) * (0.3 + 0.7 * z) * (0.7 + 0.6 * env)
        xi, yi = int(x), int(y)
        x1, x2, y1, y2 = max(xi - r, 0), min(xi + r + 1, W), max(yi - r, 0), min(yi + r + 1, H)
        if x2 > x1 and y2 > y1:
            f[y1:y2, x1:x2] += SPR[r][y1 - (yi - r):y2 - (yi - r), x1 - (xi - r):x2 - (xi - r)][..., None] * tint * b


def compose(i, tl, gt, env):
    cv, fx, light = SCENES[i](tl, gt, env)
    f = cv.astype(F32) / 255
    fxf = fx.astype(F32) / 255
    sm = cv2.resize(fxf, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    gl = cv2.resize(cv2.GaussianBlur(sm, (0, 0), 5), (W, H), interpolation=cv2.INTER_LINEAR)
    lg = cv2.resize(light, (W, H), interpolation=cv2.INTER_LINEAR)
    return f + fxf + gl * 0.7 + lg


def render_at(t, env):
    i = int(min(np.searchsorted(STARTS, t, side="right") - 1, 5))
    f = compose(i, t - STARTS[i], t, env_at(env, t))
    if i + 1 < 6 and STARTS[i + 1] - t < XFADE:
        a = smooth(1 - (STARTS[i + 1] - t) / XFADE)
        f = f * (1 - a) + compose(i + 1, t - STARTS[i + 1], t, env_at(env, t)) * a
    e = env_at(env, t)
    small = cv2.resize(f, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    bl = cv2.resize(cv2.GaussianBlur(np.clip(small - 0.6, 0, 1), (0, 0), 7), (W, H), interpolation=cv2.INTER_LINEAR)
    f = f + bl * (0.12 + 0.5 * e)
    particles(f, t, e)
    g = f.mean(2, keepdims=True)
    f = g + (f - g) * 1.08
    f *= VIG
    f += np.random.normal(0, 0.011, (H, W, 1)).astype(F32)
    return (np.clip(f, 0, 1) * 255).astype(np.uint8)


def load_env(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.int16).astype(F32) / 32768
    hop = 16000 // FPS
    n = len(a) // hop
    rms = np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(1))
    rms = np.clip(rms / (np.percentile(rms, 95) + 1e-6), 0, 1.3)
    env = np.zeros_like(rms)
    for k, v in enumerate(rms):
        env[k] = max(v, env[k - 1] * 0.88) if k else v
    return env


def env_at(env, t):
    return float(env[min(int(t * FPS), len(env) - 1)])


def main():
    if sys.argv[1] == "--stills":
        ts = [float(x) for x in sys.argv[2].split(",")]
        env = load_env(sys.argv[3])
        for t in ts:
            cv2.imwrite(f"still_{t}.png", cv2.cvtColor(render_at(t, env), cv2.COLOR_RGB2BGR))
        return
    out, audio = sys.argv[1], sys.argv[2]
    env = load_env(audio)
    n = int(TOTAL * FPS)
    ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    for k in range(n):
        ff.stdin.write(render_at(k / FPS, env).tobytes())
        if k % 90 == 0:
            print(f"frame {k}/{n}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("done", out)


if __name__ == "__main__":
    main()
