"""Route A: code-animated vertical video from still paintings.

Layers: depth parallax + camera drift, thought-storm swirl (shot 1), fireflies,
voice-reactive bloom, crossfades, breathing ring (last shot), vignette + grain.
Usage: animate.py OUT.mp4 AUDIO.mp3 [max_seconds]
"""
import subprocess
import sys

import cv2
import numpy as np

W, H, FPS = 1080, 1920, 30
HERE = __file__.rsplit("/", 1)[0]
OUT, AUDIO = sys.argv[1], sys.argv[2]
MAXT = float(sys.argv[3]) if len(sys.argv) > 3 else None

# img, duration, zoom, x_from, x_to, y_from, y_to, subjects[(cx,cy,sx,sy,strength)], tint
SHOTS = [
    ("s1.png", 5.6, 1.12, 0.14, 0.40, 0.00, 0.25, [(0.30, 0.45, 0.25, 0.35, 0.5)], (255, 205, 120)),
    ("s2.png", 2.4, 1.12, 0.10, 0.55, 0.30, 0.30, [(0.17, 0.68, 0.10, 0.25, 0.5), (0.52, 0.42, 0.04, 0.05, 0.3)], (255, 215, 110)),
    ("s3.png", 2.3, 1.12, 0.00, 0.35, 0.50, 0.50, [(0.15, 0.70, 0.18, 0.18, 0.55), (0.43, 0.35, 0.06, 0.08, 0.4)], (255, 205, 110)),
    ("s3.png", 4.4, 1.12, 1.00, 0.60, 0.50, 0.50, [(0.88, 0.45, 0.05, 0.05, 0.3)], (255, 190, 100)),
    ("s2.png", 2.7, 1.12, 0.55, 0.90, 0.00, 0.00, [(0.55, 0.50, 0.05, 0.05, 0.3)], (200, 225, 255)),
    ("s3.png", 4.6, 1.12, 0.40, 0.62, 0.50, 0.35, [(0.43, 0.35, 0.06, 0.08, 0.4)], (255, 200, 110)),
]
XFADE = 0.35
STARTS = np.cumsum([0] + [s[1] for s in SHOTS])
TOTAL = float(STARTS[-1])


def smooth(p):
    p = min(max(p, 0.0), 1.0)
    return p * p * (3 - 2 * p)


class Shot:
    def __init__(self, spec):
        name, self.dur, z, self.xa, self.xb, self.ya, self.yb, subj, self.tint = spec
        src = cv2.cvtColor(cv2.imread(f"{HERE}/{name}"), cv2.COLOR_BGR2RGB)
        hh = int(H * z)
        ww = int(src.shape[1] * hh / src.shape[0])
        self.img = cv2.resize(src, (ww, hh), interpolation=cv2.INTER_LANCZOS4)
        self.w, self.h = ww, hh
        self.is_storm = name == "s1.png" and spec is SHOTS[0]
        # pseudo-depth: bottom + dark = near, plus subject blobs
        gray = cv2.cvtColor(self.img, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
        lum = cv2.GaussianBlur(gray, (0, 0), 30)
        ys = np.linspace(0, 1, hh, dtype=np.float32)[:, None]
        d = 0.55 * ys + 0.45 * (1 - lum)
        yy, xx = np.mgrid[0:hh, 0:ww].astype(np.float32)
        for cx, cy, sx, sy, s in subj:
            d += s * np.exp(-(((xx - cx * ww) / (sx * ww)) ** 2 + ((yy - cy * hh) / (sy * hh)) ** 2))
        d = (d - d.min()) / (d.max() - d.min() + 1e-6)
        self.depth = cv2.GaussianBlur(d, (0, 0), 12)
        self.ux, self.uy = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))

    def frame(self, t):
        p = min(max(t / self.dur, 0.0), 1.0)
        e = smooth(p)
        x0 = (self.w - W) * (self.xa + (self.xb - self.xa) * e)
        y0 = (self.h - H) * (self.ya + (self.yb - self.ya) * e)
        xi, yi = int(x0), int(y0)
        dc = self.depth[yi:yi + H, xi:xi + W]
        a = 34 * (2 * p - 1)
        ay = 12 * np.sin(p * np.pi)
        mx = self.ux + x0 + (dc - 0.5) * a
        my = self.uy + y0 + (dc - 0.5) * ay
        if self.is_storm:  # swirling thought-cloud that settles
            cx, cy = 0.485 * self.w, 0.33 * self.h
            sx, sy = mx - cx, my - cy
            amp = 0.55 * (1 - 0.85 * smooth(p / 0.9))
            ang = amp * np.exp(-(sx * sx + sy * sy) / (2 * 190.0 ** 2)) * np.sin(2 * np.pi * t / 2.2)
            c, s = np.cos(ang), np.sin(ang)
            mx, my = cx + sx * c - sy * s, cy + sx * s + sy * c
        mx, my = mx.astype(np.float32), my.astype(np.float32)
        return cv2.remap(self.img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def load_env():
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", AUDIO, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    hop = 16000 // FPS
    n = len(a) // hop
    rms = np.sqrt((a[: n * hop].reshape(n, hop) ** 2).mean(1))
    rms = rms / (np.percentile(rms, 95) + 1e-6)
    env = np.zeros_like(rms)
    for i, v in enumerate(np.clip(rms, 0, 1.3)):  # fast attack, slow release
        env[i] = max(v, env[i - 1] * 0.88) if i else v
    return env


def sprite(r):
    k = np.arange(-r, r + 1, dtype=np.float32)
    g = np.exp(-((k[None, :] ** 2 + k[:, None] ** 2) / (2 * (r / 2.6) ** 2)))
    return g


SPR = {r: sprite(r) for r in (6, 10, 15, 22)}
rs = np.random.RandomState(7)
N = 55
P = dict(x=rs.uniform(0, W, N), y=rs.uniform(0, H, N), z=rs.uniform(0.25, 1, N), ph=rs.uniform(0, 6.28, N),
         vy=rs.uniform(12, 40, N), vx=rs.uniform(-8, 8, N), tw=rs.uniform(1.5, 4, N))
DIST = np.hypot(*np.meshgrid(np.arange(W, dtype=np.float32) - W / 2, np.arange(H, dtype=np.float32) - 820))
VIG = (1 - 0.38 * np.clip((np.hypot(*np.meshgrid((np.arange(W) - W / 2) / (W / 2), (np.arange(H) - H / 2) / (H / 2))) - 0.55), 0, 1) ** 1.5)[..., None].astype(np.float32)


def tint_at(t):
    i = int(np.searchsorted(STARTS, t, side="right") - 1)
    return np.array(SHOTS[min(i, len(SHOTS) - 1)][8], dtype=np.float32) / 255


def add_particles(f, t, env):
    tint = tint_at(t)
    for i in range(N):
        z = P["z"][i]
        x = (P["x"][i] + 70 * z * np.sin(0.7 * t + P["ph"][i]) + P["vx"][i] * t) % W
        y = (P["y"][i] - P["vy"][i] * z * t) % H
        r = 6 if z < 0.4 else 10 if z < 0.65 else 15 if z < 0.88 else 22
        tw = 0.45 + 0.55 * np.sin(P["tw"][i] * t + P["ph"][i]) ** 2
        b = tw * (0.35 + 0.65 * z) * (0.75 + 0.5 * env)
        xi, yi = int(x), int(y)
        x1, x2, y1, y2 = max(xi - r, 0), min(xi + r + 1, W), max(yi - r, 0), min(yi + r + 1, H)
        if x2 <= x1 or y2 <= y1:
            continue
        s = SPR[r][y1 - (yi - r): y2 - (yi - r), x1 - (xi - r): x2 - (xi - r)]
        f[y1:y2, x1:x2] += s[..., None] * tint * b


def add_bloom(f, env):
    small = cv2.resize(f, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    hi = np.clip(small - 0.5, 0, 1)
    bl = cv2.GaussianBlur(hi, (0, 0), 7)
    bl = cv2.resize(bl, (W, H), interpolation=cv2.INTER_LINEAR)
    f += bl * (0.30 + 1.0 * env)


def add_ring(f, t):
    rt = t - STARTS[-2]
    if rt < 0:
        return
    fade = smooth(rt / 0.8) * (1 - smooth((rt - (SHOTS[-1][1] - 0.5)) / 0.5))
    r = 130 + 105 * (0.5 - 0.5 * np.cos(2 * np.pi * rt / 4.6))
    ring = np.exp(-(((DIST - r) / 16) ** 2)) * 0.55 + np.exp(-((DIST / (r * 0.8)) ** 2)) * 0.10
    f += ring[..., None] * np.array([1.0, 0.82, 0.5], dtype=np.float32) * fade


def render_at(shots, t, env):
    i = int(min(np.searchsorted(STARTS, t, side="right") - 1, len(SHOTS) - 1))
    f = shots[i].frame(t - STARTS[i]).astype(np.float32) / 255
    if i + 1 < len(SHOTS) and STARTS[i + 1] - t < XFADE:
        a = smooth(1 - (STARTS[i + 1] - t) / XFADE)
        f = f * (1 - a) + shots[i + 1].frame(t - STARTS[i + 1]).astype(np.float32) / 255 * a
    k = min(int(t * FPS), len(env) - 1)
    e = float(env[k])
    gray = f.mean(2, keepdims=True)
    f = gray + (f - gray) * 1.12  # saturation
    add_bloom(f, e)
    add_particles(f, t, e)
    add_ring(f, t)
    f *= VIG
    f += np.random.normal(0, 0.012, (H, W, 1)).astype(np.float32)
    return (np.clip(f, 0, 1) * 255).astype(np.uint8)


def main():
    env = load_env()
    shots = [Shot(s) for s in SHOTS]
    total = min(TOTAL, MAXT) if MAXT else TOTAL
    n = int(total * FPS)
    ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                           "-i", "-", "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", OUT],
                          stdin=subprocess.PIPE)
    for k in range(n):
        ff.stdin.write(render_at(shots, k / FPS, env).tobytes())
        if k % 90 == 0:
            print(f"frame {k}/{n}", flush=True)
    ff.stdin.close()
    ff.wait()
    print("done", OUT)


if __name__ == "__main__":
    main()
