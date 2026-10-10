"""Visual stages: one keyframe -> upscaled plate -> seamless animated loop (all motion periodic in loop_s),
thumbnail, region preview overlay. Region coordinates in scene.yaml are NORMALISED (0..1) to the 16:9 frame,
so the same config works whatever size the keyframe is."""
import os, math, subprocess, numpy as np, cv2
from multiprocessing import Pool
from realtime.catalog import BUILTIN_EFFECTS, BUILTIN_MOTIONS, MOTIONS, register_effect as _catalog_effect
from realtime.period import snap
from realtime.runtime import current

TAU = 2 * math.pi
S = {}   # per-render state (inherited by forked workers)
PREP = {}

# ---------- plate ----------
def load_plate(cfg, W, H, log=print):
    kf = cfg['keyframe'] if os.path.isabs(cfg['keyframe']) else os.path.join(cfg['_dir'], cfg['keyframe'])
    img = cv2.imread(kf)
    if img is None: raise FileNotFoundError(f'keyframe not found: {kf}')
    if cfg['visual'].get('crop'):
        x0, y0, x1, y1 = cfg['visual']['crop']; h, w = img.shape[:2]
        img = img[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]
    h, w = img.shape[:2]
    if w < W or h < H:
        model = current().find('models', 'EDSR_x2.pb') or ''
        if os.path.exists(model) and w * h <= 2_200_000:
            sr = cv2.dnn_superres.DnnSuperResImpl_create(); sr.readModel(model); sr.setModel('edsr', 2)
            log(f'  upscaling {w}x{h} with EDSR x2 (a few minutes on CPU)'); img = sr.upsample(img)
        else: log('  EDSR model missing or image large: Lanczos upscale')
    h, w = img.shape[:2]; s = max(W / w, H / h)
    img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LANCZOS4)
    h, w = img.shape[:2]; x0, y0 = (w - W) // 2, (h - H) // 2
    return img[y0:y0 + H, x0:x0 + W].copy()

def region_mask(R, W, H, feather=2.0):
    m = np.zeros((H, W), np.uint8)
    def draw(r, val):
        if 'poly' in r: cv2.fillPoly(m, [np.array([(x * W, y * H) for x, y in r['poly']], np.int32)], val)
        elif 'rect' in r:
            x0, y0, x1, y1 = r['rect']; cv2.rectangle(m, (int(x0 * W), int(y0 * H)), (int(x1 * W), int(y1 * H)), val, -1)
        elif 'circle' in r:
            cx, cy, rr = r['circle']; cv2.circle(m, (int(cx * W), int(cy * H)), int(rr * W), val, -1)
        elif 'ellipse' in r:
            cx, cy, rx, ry = r['ellipse']; cv2.ellipse(m, (int(cx * W), int(cy * H)), (int(rx * W), int(ry * H)), 0, 0, 360, val, -1)
    if isinstance(R, list):
        for r in R: draw(r, 255)
    else:
        draw(R, 255)
        for ex in R.get('exclude', []): draw(ex, 0)
    f = m.astype(np.float32) / 255
    return cv2.GaussianBlur(f, (0, 0), feather) if feather > 0 else f

def bbox(mask):
    ys, xs = np.where(mask > 0.01)
    return (int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1) if len(xs) else (0, 1, 0, 1)

def loop_noise(t, seed, terms, L):
    r = np.random.default_rng(seed); s = 0
    for n in terms: s += math.sin(TAU * n * t / L + r.uniform(0, TAU)) / math.sqrt(n)
    return s / 2.2

# ---------- effects ----------
def prep_parallax(e, plate, W, H, L):
    m = region_mask(e['region'], W, H, e.get('feather', 1.6)); x0, x1, y0, y1 = bbox(m)
    src = plate[y0:y1, x0:x1].astype(np.float32) / 255
    if e.get('source'):
        src = cv2.resize(cv2.imread(os.path.join(S['dir'], e['source'])), (x1 - x0, y1 - y0)).astype(np.float32) / 255
    if e.get('source_blur'): src = cv2.GaussianBlur(src, (0, 0), e['source_blur'])
    pano = np.concatenate([src, src[:, ::-1]], 1); PW = pano.shape[1]; h = y1 - y0
    bands = e.get('bands', [[0, 0.6, 1, 9], [0.6, 0.8, 2, 17], [0.8, 1.0, 3, 29]])  # [from, to, pano-widths per loop, blur px]
    imgs, ws = [], []; yy = np.arange(h, dtype=np.float32) / h
    for (a, b, k, bl) in bands:
        p3 = np.concatenate([pano] * 3, 1)
        imgs.append(cv2.filter2D(p3, -1, np.ones((1, int(bl) | 1), np.float32) / (int(bl) | 1))[:, PW:2 * PW].copy() if bl > 1 else pano)
        ws.append((np.clip((yy - (a - .025)) / .05, 0, 1) if a > 0 else 1) * (np.clip(((b + .025) - yy) / .05, 0, 1) if b < 1 else 1) + 0 * yy)
    ws = np.stack(ws); ws /= ws.sum(0, keepdims=True) + 1e-9
    gx = np.tile(np.arange(x1 - x0, dtype=np.float32), (h, 1)); gy = np.tile(np.arange(h, dtype=np.float32)[:, None], (1, x1 - x0))
    sign = -1 if e.get('direction', 'left') == 'left' else 1
    def render(t):
        out = 0
        for i, (a, b, k, bl) in enumerate(bands):
            mx = ((gx - sign * (t / L) * k * PW) % PW).astype(np.float32)
            out = out + cv2.remap(imgs[i], mx, gy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP) * ws[i][:, None, None]
        return out
    return dict(kind='parallax', mask=m[y0:y1, x0:x1, None], box=(x0, x1, y0, y1), render=render)

def prep_rain(e, W, H, L, test):
    m = region_mask(e['region'], W, H, e.get('feather', 1.6)); x0, x1, y0, y1 = bbox(m); w, h = x1 - x0, y1 - y0
    rs = np.random.default_rng(e.get('seed', 7)); dens = e.get('drops_per_mpx', 2000) * (0.5 if test else 1)
    NS = int(dens * w * h / 1e6); NR = int(e.get('rivulets_per_mpx', 62) * w * h / 1e6)
    sc = e.get('drop_scale', 1.0)
    d = dict(x=rs.uniform(0, w, NS), y=rs.uniform(0, h, NS), r=rs.choice([1.2, 1.5, 1.8, 2.2, 2.8, 3.5], NS, p=[.25, .25, .2, .15, .1, .05]) * sc,
             b=rs.uniform(0, L, NS), l=rs.uniform(8, 40, NS),
             rx=rs.uniform(w * 0.2, w + 60, NR), ry=rs.uniform(-20, h * 0.72, NR), rb=rs.uniform(0, L, NR), rl=rs.uniform(2.5, 5, NR),
             vx=rs.uniform(18, 40, NR) * e.get('slant', -1.0), vy=rs.uniform(10, 26, NR), rr=rs.uniform(2.2, 3.6, NR) * sc, ph=rs.uniform(0, TAU, NR))
    gx = np.tile(np.arange(w, dtype=np.float32), (h, 1)); gy = np.tile(np.arange(h, dtype=np.float32)[:, None], (1, w))
    warm = np.array(e.get('highlight_bgr', [0.38, 0.62, 0.95]), np.float32)
    def heightmap(t):
        Hm = np.zeros((h, w), np.float32); age = (t - d['b']) % L
        for i in np.where(age < d['l'])[0]:
            a = age[i]; f = min(1, a / 0.6) * min(1, (d['l'][i] - a) / 2.0)
            cv2.circle(Hm, (int(d['x'][i] * 16), int(d['y'][i] * 16)), int(d['r'][i] * 16), float(f * d['r'][i]), -1, cv2.LINE_AA, 4)
        for i in range(NR):
            a = (t - d['rb'][i]) % L
            if a > d['rl'][i] + 2.5: continue
            run = min(a, d['rl'][i]); pts = []
            for s in np.linspace(0, run, max(2, int(run * 8))):
                px = d['rx'][i] + d['vx'][i] * s + 4 * math.sin(s * 3.1 + d['ph'][i]) + 2 * math.sin(s * 7.3 + d['ph'][i] * 2)
                py = d['ry'][i] + d['vy'][i] * s + 0.01 * d['vy'][i] * s * s; pts.append((int(px * 16), int(py * 16)))
            fade = 1.0 if a <= d['rl'][i] else max(0, 1 - (a - d['rl'][i]) / 2.5); pa = np.array(pts, np.int32); cut = int(len(pa) * 0.4)
            if len(pa) - cut >= 2: cv2.polylines(Hm, [pa[cut:]], False, float(0.45 * fade), 1, cv2.LINE_AA, 4)
            if cut >= 2: cv2.polylines(Hm, [pa[:cut + 1]], False, float(0.18 * fade), 1, cv2.LINE_AA, 4)
            if a <= d['rl'][i]: cv2.circle(Hm, pts[-1], int(d['rr'][i] * 16), float(d['rr'][i] * 1.1), -1, cv2.LINE_AA, 4)
        return cv2.GaussianBlur(Hm, (0, 0), 1.3)
    k = e.get('refraction', 9.0)
    def apply(t, under):
        Hm = heightmap(t); sx = cv2.Sobel(Hm, cv2.CV_32F, 1, 0, ksize=3); sy = cv2.Sobel(Hm, cv2.CV_32F, 0, 1, ksize=3)
        ref = cv2.remap(under, gx - k * sx, gy - k * sy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        shade = 1 - np.clip(np.sqrt(sx * sx + sy * sy) * 0.07, 0, 0.25)
        spec = np.clip(-sx * 0.7 + sy * 0.7, 0, None) * 0.075
        return ref * shade[..., None] + (spec ** 1.3)[..., None] * warm * 0.9
    return dict(kind='rain', mask=m[y0:y1, x0:x1, None], box=(x0, x1, y0, y1), apply=apply)

LIGHT = {  # noise terms (cycles per loop), amount scale, dips per loop
    'lamp':    ((2, 3, 5, 7, 11, 13), (37, 53, 71, 97), 1.0, 5),
    'candle':  ((5, 7, 11, 13, 17), (61, 89, 113, 149), 2.2, 9),
    'fire':    ((7, 11, 13, 17, 23), (71, 97, 131, 173), 3.0, 14),
    'neon':    ((1, 2), (), 0.4, 3),
    'breathe': ((1, 2, 3), (), 0.8, 0),
    'daylight':((1, 2), (), 0.5, 0),     # clouds passing: very slow, very soft
}

def prep_horizon(e, W, H, L):
    """Ship roll seen correctly: the camera is fixed to the ship, so only the sea + sky behind the rails tilt/heave.
    Everything outside the region (deck, columns, rails) stays perfectly still."""
    m = region_mask(e['region'], W, H, e.get('feather', 1.5)); x0, x1, y0, y1 = bbox(m)
    per = snap(e.get('period_s', 11.0), L); roll = e.get('roll_deg', 0.25); heave = e.get('heave_px', 2.5)
    piv = e.get('pivot', [0.5, 0.5]); pc = (piv[0] * W - x0, piv[1] * H - y0)
    def apply(t, under):
        a = roll * math.sin(TAU * t / per) + 0.08 * roll * math.sin(TAU * t / snap(per / 2.3, L))
        M = cv2.getRotationMatrix2D(pc, a, 1.0); M[1, 2] += heave * math.sin(TAU * t / per + 1.6)
        return cv2.warpAffine(under, M, (x1 - x0, y1 - y0), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    return dict(kind='horizon', mask=m[y0:y1, x0:x1, None], box=(x0, x1, y0, y1), apply=apply)

def prep_twinkle(e, base8, W, H, L, idx):
    """String lights / tree bulbs: each bright blob in the region gently pulses on its own phase."""
    m = region_mask(e['region'], W, H, 0); x0, x1, y0, y1 = bbox(m)
    reg = base8[y0:y1, x0:x1].astype(np.float32); lum = reg.max(2)
    thr = e.get('threshold', 170); bm = ((lum > thr) & (m[y0:y1, x0:x1] > 0.5)).astype(np.uint8)
    n, lab = cv2.connectedComponents(cv2.dilate(bm, np.ones((3, 3), np.uint8)))
    rs = np.random.default_rng(700 + idx); ph = rs.uniform(0, TAU, n); k = rs.integers(e.get('min_cycles', 2), e.get('max_cycles', 7), n)
    halo = cv2.GaussianBlur((lab > 0).astype(np.float32), (0, 0), e.get('halo_px', 2.5)); halo /= max(1e-6, halo.max())
    labs = cv2.dilate(lab.astype(np.float32), np.ones((7, 7), np.uint8)).astype(np.int32)   # spread labels into the halo
    amt = e.get('amount', 0.18)
    def apply(t, under):
        f = amt * np.sin(TAU * k * t / L + ph); f[0] = 0
        return under * (1 + f[labs] * halo)[..., None]
    return dict(kind='twinkle', mask=np.ones((y1 - y0, x1 - x0, 1), np.float32), box=(x0, x1, y0, y1), apply=apply, count=n - 1)

def prep_light(e, W, H, L, idx):
    kind = e.get('kind', 'lamp'); slow, fast, scale, dips = LIGHT[kind]
    cx, cy, r = e['circle'] if 'circle' in e else (e['center'][0], e['center'][1], e.get('radius', 0.15))
    Y, X = np.mgrid[0:H, 0:W].astype(np.float32)
    m = np.exp(-(((X - cx * W) ** 2 + (Y - cy * H) ** 2) / (2 * (r * W) ** 2)))[..., None]
    rl = np.random.default_rng(300 + idx); ft = rl.uniform(0, L, dips); fd = rl.uniform(0.08, 0.25, dips)
    amt = e.get('amount', 0.022) * scale
    tint = np.array(e.get('tint_bgr', [1, 1, 1]), np.float32)
    def factor(t):
        f = amt * loop_noise(t, 101 + idx, slow, L) + (amt * 0.27 * loop_noise(t, 202 + idx, fast, L) if fast else 0)
        for a, dd in zip(ft, fd):
            dt = (t - a) % L
            if dt < dd: f -= amt * 1.4 * math.sin(math.pi * dt / dd)
        return f
    return dict(kind='light', mask=m * tint, factor=factor, gain=e.get('gain', 1.6))

def prep_particles(e, W, H, L, idx, test):
    kind = e.get('kind', 'snow'); m = region_mask(e['region'], W, H, 0) if 'region' in e else np.ones((H, W), np.float32)
    x0, x1, y0, y1 = bbox(m); w, h = x1 - x0, y1 - y0; rs = np.random.default_rng(500 + idx)
    n = int(e.get('count', {'snow': 900, 'dust': 140, 'steam': 26, 'smoke': 20}[kind]) * (0.6 if test else 1))
    p = dict(x=rs.uniform(0, w, n), off=rs.uniform(0, 1, n), ph=rs.uniform(0, TAU, n), ph2=rs.uniform(0, TAU, n),
             size=rs.uniform(*e.get('size_px', {'snow': [1.0, 3.2], 'dust': [0.8, 2.0], 'steam': [18, 46], 'smoke': [20, 60]}[kind]), n),
             a=rs.uniform(0.35, 1.0, n), y=rs.uniform(0, h, n))
    fall = e.get('fall_s', 9.0 if kind == 'snow' else 6.0)
    p['k'] = np.maximum(1, np.round(L / (fall * rs.uniform(0.75, 1.35, n))))      # integer cycles per loop
    color = np.array(e.get('color_bgr', {'snow': [0.95, 0.95, 0.97], 'dust': [0.55, 0.78, 1.0], 'steam': [0.9, 0.9, 0.9], 'smoke': [0.7, 0.72, 0.75]}[kind]), np.float32)
    op = e.get('opacity', {'snow': 0.75, 'dust': 0.6, 'steam': 0.22, 'smoke': 0.12}[kind]); src = e.get('source', [0.5, 1.0])
    ds = 4 if kind in ('steam', 'smoke') else 1
    def render(t):
        lay = np.zeros((h // ds + 1, w // ds + 1), np.float32)
        if kind == 'snow':
            ph = (p['k'] * t / L + p['off']) % 1
            xs = p['x'] + 14 * np.sin(TAU * 2 * t / L + p['ph']) + 6 * np.sin(TAU * 5 * t / L + p['ph2']); ys = ph * (h + 20) - 10
            al = p['a'] * np.minimum(1, np.minimum(ph, 1 - ph) * 12)
        elif kind == 'dust':
            xs = p['x'] + 30 * np.sin(TAU * t / L + p['ph']) + 8 * np.sin(TAU * 3 * t / L + p['ph2'])
            ys = p['y'] + 22 * np.sin(TAU * t / L + p['ph2']) - 10 * np.cos(TAU * 2 * t / L + p['ph'])
            al = p['a'] * (0.5 + 0.5 * np.sin(TAU * 4 * t / L + p['ph'])) ** 2
        else:   # steam / smoke rising from a source point, spreading and fading
            ph = (p['k'] * t / L + p['off']) % 1
            xs = src[0] * W - x0 + (p['x'] / w - 0.5) * 40 * ph + 25 * ph * np.sin(TAU * 3 * ph + p['ph'])
            ys = src[1] * H - y0 - ph * h * 0.95; al = p['a'] * np.sin(np.pi * ph) ** 1.5
            sz = p['size'] * (0.4 + 1.6 * ph)
        for i in range(n):
            r = (sz[i] if kind in ('steam', 'smoke') else p['size'][i]) / ds
            if al[i] > 0.02: cv2.circle(lay, (int(xs[i] / ds * 8), int(ys[i] / ds * 8)), max(1, int(r * 8)), float(al[i]), -1, cv2.LINE_AA, 3)
        lay = cv2.GaussianBlur(lay, (0, 0), {'snow': 0.7, 'dust': 1.2}.get(kind, 4.0))
        if ds > 1: lay = cv2.resize(lay, (w, h), interpolation=cv2.INTER_LINEAR)
        return np.clip(lay[:h, :w], 0, 1)[..., None] * op
    return dict(kind='particles', box=(x0, x1, y0, y1), mask=m[y0:y1, x0:x1, None], render=render, color=color,
                mode=e.get('blend', 'screen'))

def prep_shimmer(e, W, H, L):
    """Water: small ripple displacement + glints, from smooth random fields that drift sideways in opposite
    directions (whole-number wraps per loop, so it repeats seamlessly). No regular sine pattern."""
    m = region_mask(e['region'], W, H, e.get('feather', 3)); x0, x1, y0, y1 = bbox(m); w, h = x1 - x0, y1 - y0
    rs = np.random.default_rng(e.get('seed', 11))
    def field(sx, sy):
        n = rs.standard_normal((h, w)).astype(np.float32)   # blur a 3x tile so it wraps seamlessly left-right
        f = cv2.GaussianBlur(np.concatenate([n, n, n], 1), (0, 0), sigmaX=sx, sigmaY=sy)[:, w:2 * w]
        return f / (f.std() + 1e-9)
    D1, D2, D3, D4 = field(9, 2.2), field(7, 1.8), field(9, 2.2), field(7, 1.8)
    S1, S2 = field(2.5, 1.0), field(2.0, 0.9)
    gx = np.tile(np.arange(w, dtype=np.float32), (h, 1)); gy = np.tile(np.arange(h, dtype=np.float32)[:, None], (1, w))
    a = e.get('amount_px', 1.4); sp = e.get('sparkle', 0.15); persp = (0.3 + 0.7 * (gy / max(1, h))) ** 1.5
    k1, k2 = e.get('drift', [1, 2])
    def sh(F, k, t): return np.roll(F, int(round(k * w * t / L)) % w, axis=1)
    def apply(t, under):
        dx = a * persp * 0.5 * (sh(D1, k1, t) - sh(D2, -k2, t)); dy = a * persp * 0.35 * (sh(D3, -k1, t) + sh(D4, k2, t))
        out = cv2.remap(under, gx + dx, gy + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        lum = out.mean(2, keepdims=True); hi = np.clip((lum - 0.5) / 0.35, 0, 1)
        g = np.clip(sh(S1, k2, t) * sh(S2, -k1, t), 0, None)
        return out * (1 + sp * hi * (g[..., None] - 0.4))
    return dict(kind='shimmer', mask=m[y0:y1, x0:x1, None], box=(x0, x1, y0, y1), apply=apply)

def motion(cfg, L):
    mo = cfg['visual']['motion']; typ = mo.get('type', 'none')
    if typ in MOTIONS:
        return MOTIONS[typ](mo, L)
    A = mo.get('amplitude', 1.0)
    P = lambda p: snap(p, L)
    if typ == 'train':
        bump = snap(mo.get('bump_period_s', 1.2), L); bumps = mo.get('bumps', 0.45) * A
        def f(t):
            dx = A * (1.4 * math.sin(TAU * t / P(12) + .4) + .5 * math.sin(TAU * t / P(8) + 1.3)); dy = A * .9 * math.sin(TAU * t / P(9) + 2)
            ph = t % bump
            for off in (0.0, 0.16):
                dd = ph - off
                if dd >= 0 and bumps: dy += bumps * math.exp(-dd * 9) * math.sin(dd * 40)
            return dx, dy, A * .025 * math.sin(TAU * t / P(18) + .7), 1.008
        return f
    if typ == 'ship':
        roll = mo.get('roll_deg', 0.35); per = mo.get('period_s', 11.0)
        return lambda t: (A * 1.2 * math.sin(TAU * t / P(per * 1.7) + 1.1), A * 3.0 * math.sin(TAU * t / P(per) + 1.6),
                          roll * math.sin(TAU * t / P(per)) + 0.08 * roll * math.sin(TAU * t / P(per / 2.3)), 1.0 + roll * 0.045)
    if typ == 'gentle':
        return lambda t: (A * .7 * math.sin(TAU * t / P(17)), A * .45 * math.sin(TAU * t / P(13) + 1), 0.0, 1.004)
    if typ == 'none':
        return lambda t: (0.0, 0.0, 0.0, 1.0)
    known = ', '.join(sorted(set(BUILTIN_MOTIONS) | set(MOTIONS)))
    raise ValueError(f'unknown motion {typ!r}. known: {known}')

# ---------- build ----------
def prepare(cfg, plate, test=False):
    v = cfg['visual']; W, H = v['width'], v['height']; L = float(v['loop_s'])
    S.clear(); S.update(W=W, H=H, L=L, FPS=v['fps'], NF=int(round(L * v['fps'])), dir=cfg['_dir'], cfg=cfg)
    img = plate.copy()
    for e in v['effects']:
        if e['type'] == 'blur':    # soften garbled AI text / logos
            m = region_mask(e['region'], W, H, 6)[..., None]
            img = (img * (1 - m) + cv2.GaussianBlur(img, (0, 0), e.get('sigma', 2.0)) * m).astype(np.uint8)
    base = img.astype(np.float32) / 255; gr = v['grade']
    base = gr.get('lift', 0.012) + base * (1 - gr.get('lift', 0.012))
    if gr.get('warmth'): base = base * np.array([1 - gr['warmth'], 1, 1 + gr['warmth']], np.float32)
    if gr.get('saturation', 1) != 1:
        l = base.mean(2, keepdims=True); base = l + (base - l) * gr['saturation']
    S['base'] = np.clip(base, 0, 1); S['plate8'] = img
    lum = S['base'].mean(2); br = np.clip((lum - 0.55) / 0.45, 0, 1) ** 1.5
    S['bloom'] = ((cv2.GaussianBlur(br, (0, 0), 30) * .55 + cv2.GaussianBlur(br, (0, 0), 9) * .35)[..., None]
                  * np.array([.35, .62, 1.0], np.float32) * v.get('bloom', 0.5))
    fx = []
    ctx_base = dict(img=img, W=W, H=H, L=L, test=test)
    for i, e in enumerate(v['effects']):
        t = e['type']
        if t == 'blur':
            continue
        fn = PREP.get(t)
        if fn is None:
            known = ', '.join(sorted(set(BUILTIN_EFFECTS) | set(PREP)))
            raise ValueError(f'unknown effect type {t!r}. known: {known}')
        fx.append(fn(e, dict(ctx_base, i=i)))
    S['fx'] = fx; S['motion'] = motion(cfg, L)
    Y, X = np.mgrid[0:H, 0:W].astype(np.float32); vc = v.get('vignette_center', [0.5, 0.48])
    r2 = ((X - vc[0] * W) / (W * .62)) ** 2 + ((Y - vc[1] * H) / (H * .68)) ** 2
    S['vign'] = (1 - v['vignette'] * np.clip(r2, 0, 1.6) ** 1.25)[..., None].astype(np.float32)

def frame(fi, grain=True):
    W, H, L = S['W'], S['H'], S['L']; t = (fi % S['NF']) / S['FPS']; img = S['base'].copy(); lights = 0
    regional = {}
    for e in S['fx']:
        k = e['kind']
        if k == 'parallax':
            x0, x1, y0, y1 = e['box']; img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - e['mask']) + e['render'](t) * e['mask']
        elif k in ('rain', 'shimmer', 'horizon', 'twinkle'):
            x0, x1, y0, y1 = e['box']; reg = img[y0:y1, x0:x1]
            img[y0:y1, x0:x1] = reg * (1 - e['mask']) + e['apply'](t, reg.copy()) * e['mask']
        elif k == 'light': lights = lights + e['factor'](t) * e['gain'] * e['mask']
    lf = (lights if not isinstance(lights, int) else 0)
    img = img * (1 + lf) + S['bloom'] * (1 + (lf.mean(2, keepdims=True) * 2 if not isinstance(lf, int) else 0))
    for e in S['fx']:
        if e['kind'] == 'particles':
            x0, x1, y0, y1 = e['box']; a = e['render'](t) * e['mask']; reg = img[y0:y1, x0:x1]
            img[y0:y1, x0:x1] = 1 - (1 - reg) * (1 - a * e['color']) if e['mode'] == 'screen' else reg * (1 - a) + a * e['color']
    dx, dy, rot, zoom = S['motion'](t)
    if dx or dy or rot or zoom != 1:
        M = cv2.getRotationMatrix2D((W / 2, H / 2), rot, zoom); M[0, 2] += dx; M[1, 2] += dy
        img = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    img = img * S['vign']
    if grain and S['cfg']['visual']['grain'] > 0:
        g = cv2.resize(np.random.default_rng(1000 + fi % S['NF']).standard_normal((H // 2, W // 2)).astype(np.float32), (W, H))
        l = img.mean(2, keepdims=True); img = img + g[..., None] * S['cfg']['visual']['grain'] * (0.35 + 2.4 * l * (1 - l))
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)

def render_loop(out, procs=6, crf=21, log=print):
    W, H, FPS, NF = S['W'], S['H'], S['FPS'], S['NF']; cv2.setNumThreads(1)
    ff = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                           '-c:v', 'libx264', '-preset', 'slow', '-crf', str(crf), '-tune', 'film', '-maxrate', '9M', '-bufsize', '18M',
                           '-pix_fmt', 'yuv420p', '-g', str(FPS * 4), '-movflags', '+faststart', out], stdin=subprocess.PIPE)
    with Pool(procs) as p:
        for k, fr in enumerate(p.imap(frame, range(NF), chunksize=4)):
            ff.stdin.write(fr.tobytes())
            if k % 240 == 0: log(f'  frame {k}/{NF}')
    ff.stdin.close(); ff.wait()
    if ff.returncode: raise RuntimeError('ffmpeg loop encode failed')

def regions_preview(cfg, plate, out):
    """Draw every effect region + light centre on the plate with labels, for tuning scene.yaml quickly."""
    W, H = plate.shape[1], plate.shape[0]; img = plate.copy(); ov = img.copy()
    cols = {'parallax': (255, 200, 0), 'rain_glass': (255, 120, 40), 'flicker': (0, 200, 255), 'breathe': (0, 255, 160),
            'particles': (255, 255, 255), 'shimmer': (255, 0, 200), 'blur': (0, 0, 255),
            'horizon_roll': (0, 140, 255), 'twinkle': (180, 255, 255)}
    for i, e in enumerate(cfg['visual']['effects']):
        c = cols.get(e['type'], (0, 255, 0)); label = f"{i}:{e['type']}" + (f"/{e.get('kind')}" if e.get('kind') else '')
        if 'region' in e:
            m = region_mask(e['region'], W, H, 0); ov[m > 0.5] = (ov[m > 0.5] * 0.5 + np.array(c) * 0.5).astype(np.uint8)
            cnt, _ = cv2.findContours((m > 0.5).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(img, cnt, -1, c, 2); x0, x1, y0, y1 = bbox(m); pos = (x0 + 6, y0 + 28)
        else:
            cx, cy, r = e['circle'] if 'circle' in e else (e['center'][0], e['center'][1], e.get('radius', 0.15))
            cv2.circle(img, (int(cx * W), int(cy * H)), int(r * W), c, 2); cv2.drawMarker(img, (int(cx * W), int(cy * H)), c, cv2.MARKER_CROSS, 24, 2)
            pos = (int(cx * W) + 8, int(cy * H) - 8)
        cv2.putText(img, label, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, label, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.8, c, 2, cv2.LINE_AA)
    out_img = cv2.addWeighted(ov, 0.35, img, 0.65, 0)
    for gx in range(1, 10):   # 10% grid to read coordinates off
        x = int(gx * W / 10); y = int(gx * H / 10)
        cv2.line(out_img, (x, 0), (x, H), (80, 80, 80), 1); cv2.line(out_img, (0, y), (W, y), (80, 80, 80), 1)
        cv2.putText(out_img, f'{gx/10:.1f}', (x + 3, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.putText(out_img, f'{gx/10:.1f}', (3, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    cv2.imwrite(out, out_img)

def register_effect(name, fn):
    """Register a loop effect. fn(effect_dict, ctx) -> the dict frame() already understands.

    ctx keys: img (uint8 plate), W, H, L (loop seconds), test (bool), i (effect index).
    Built-in kinds are parallax, rain, shimmer, horizon, twinkle, light, particles.
    """
    PREP[name] = fn
    _catalog_effect(name, fn)

def _flicker(e, ctx):
    e = dict(e); e.setdefault('kind', 'lamp')
    return prep_light(e, ctx['W'], ctx['H'], ctx['L'], ctx['i'])

def _breathe(e, ctx):
    e = dict(e); e.setdefault('kind', 'breathe')
    return prep_light(e, ctx['W'], ctx['H'], ctx['L'], ctx['i'])

register_effect('parallax', lambda e, ctx: prep_parallax(e, ctx['img'], ctx['W'], ctx['H'], ctx['L']))
register_effect('rain_glass', lambda e, ctx: prep_rain(e, ctx['W'], ctx['H'], ctx['L'], ctx['test']))
register_effect('flicker', _flicker)
register_effect('breathe', _breathe)
register_effect('particles', lambda e, ctx: prep_particles(e, ctx['W'], ctx['H'], ctx['L'], ctx['i'], ctx['test']))
register_effect('shimmer', lambda e, ctx: prep_shimmer(e, ctx['W'], ctx['H'], ctx['L']))
register_effect('horizon_roll', lambda e, ctx: prep_horizon(e, ctx['W'], ctx['H'], ctx['L']))
register_effect('twinkle', lambda e, ctx: prep_twinkle(e, ctx['img'], ctx['W'], ctx['H'], ctx['L'], ctx['i']))
register_effect('blur', lambda e, ctx: None)
