"""Shared DSP helpers (filters, synthetic room IRs, wow/flutter, transient taming, loudness)."""
import subprocess, numpy as np, scipy.signal as ss, pyloudnorm as pyln

SR = 48000
_meter = pyln.Meter(SR)

def load(p, ch=2, start=None, end=None):
    cmd = ['ffmpeg', '-v', 'error']
    if start: cmd += ['-ss', str(start)]
    if end: cmd += ['-to', str(end)]
    cmd += ['-i', p, '-f', 'f32le', '-ac', str(ch), '-ar', str(SR), '-']
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, ch).astype(np.float64)

def lufs(x):
    x = np.asarray(x, np.float64)
    if len(x) < SR: return -70.0
    v = _meter.integrated_loudness(x if x.ndim == 2 else np.stack([x, x], 1))
    return v if np.isfinite(v) else -70.0

def sos(kind, f, order=2):
    return ss.butter(order, f, btype=kind, fs=SR, output='sos')

def filt(x, kind, f, order=2):
    return ss.sosfilt(sos(kind, f, order), x, axis=0)

def peaking(f0, gain_db, q):
    A = 10 ** (gain_db / 40); w = 2 * np.pi * f0 / SR; al = np.sin(w) / (2 * q)
    b = [1 + al * A, -2 * np.cos(w), 1 - al * A]; a = [1 + al / A, -2 * np.cos(w), 1 - al / A]
    return np.array(b) / a[0], np.array(a) / a[0]

def peq(x, f0, gain_db, q=0.8):
    b, a = peaking(f0, gain_db, q); return ss.lfilter(b, a, x, axis=0)

def make_ir(rt60, predelay, seconds, seed, er=True):
    """Synthetic stereo room impulse response with frequency-dependent decay + early reflections."""
    r = np.random.default_rng(seed); n = int(seconds * SR); t = np.arange(n) / SR; out = []
    for c in range(2):
        noise = r.standard_normal(n)
        lo = ss.sosfilt(sos('lowpass', 500), noise) * np.exp(-6.9 * t / (rt60 * 1.15))
        mid = ss.sosfilt(sos('bandpass', [500, 3000]), noise) * np.exp(-6.9 * t / rt60)
        hi = ss.sosfilt(sos('highpass', 3000), noise) * np.exp(-6.9 * t / (rt60 * 0.55))
        tail = (lo + mid + 0.6 * hi) * np.minimum(1, t / 0.03)
        ir = np.zeros(n + int(predelay * SR)); ir[int(predelay * SR):] = tail
        if er:
            for k in range(8):
                ir[int(r.uniform(0.004, 0.045) * SR)] += r.uniform(-1, 1) * 2.0
        out.append(ir / np.sqrt(np.sum(ir ** 2)))
    return np.stack(out, 1)

def convolve(x, ir):
    return np.stack([ss.oaconvolve(x[:, c], ir[:, c])[:len(x)] for c in range(2)], 1)

def var_delay(x, d):
    idx = np.arange(len(x)) - d; i0 = np.floor(idx).astype(np.int64); fr = idx - i0
    i0 = np.clip(i0, 0, len(x) - 2); return x[i0] * (1 - fr) + x[i0 + 1] * fr

def one_pole(x, tau):
    a = np.exp(-1 / (tau * SR)); return ss.lfilter([1 - a], [1, -a], x)

def compressor_gain(m, thr_db, ratio, att, rel):
    p = one_pole(m ** 2, 0.05); lev = 10 * np.log10(p + 1e-12)
    gr = -np.maximum(0, lev - thr_db) * (1 - 1 / ratio)
    g = np.empty_like(gr); s = 0.0; aa = np.exp(-64 / (att * SR)); ar = np.exp(-64 / (rel * SR))
    for i in range(0, len(gr), 64):
        v = gr[i]; s = aa * s + (1 - aa) * v if v < s else ar * s + (1 - ar) * v; g[i:i + 64] = s
    return 10 ** (g / 20)

def tame_transients(x, amount=0.7, crest=1.6):
    """Smooth out clacks/knocks: where the fast envelope jumps above `crest` x the slow RMS envelope,
    pull it back down. amount 0 = off, 1 = flatten fully. Used on every bed for the 'subtle & smooth' default."""
    if amount <= 0: return x
    m = np.abs(x).mean(1) if x.ndim == 2 else np.abs(x)
    a_att, a_rel = np.exp(-1 / (0.001 * SR)), np.exp(-1 / (0.040 * SR))
    fast = ss.lfilter([1 - a_rel], [1, -a_rel], m)            # 40 ms peak-ish follower
    fast = np.maximum(fast, ss.lfilter([1 - a_att], [1, -a_att], m)) + 1e-9
    slow = np.sqrt(one_pole(m ** 2, 0.4)) * 1.2 + 1e-9         # 400 ms RMS
    g = np.minimum(1.0, crest * slow / fast) ** amount
    g = one_pole(g, 0.004)                                     # de-click the gain itself
    return x * (g[:, None] if x.ndim == 2 else g)

def level_ride(x, block_s=2.0):
    """Slow gain-levelling (removes louder/quieter halves of a field recording)."""
    m = x.mean(1) if x.ndim == 2 else x; bl = int(SR * block_s)
    rms = np.array([np.sqrt(np.mean(m[j:j + bl] ** 2)) + 1e-9 for j in range(0, len(m) - bl, bl)])
    if len(rms) < 3: return x
    rms = ss.medfilt(rms, min(9, len(rms) // 2 * 2 - 1 if len(rms) % 2 == 0 else len(rms)))
    env = np.interp(np.arange(len(m)), np.arange(len(rms)) * bl + bl / 2, rms)
    g = np.median(rms) / env
    return x * (g[:, None] if x.ndim == 2 else g)

def pseudo_stereo(mono):
    r = ss.lfilter([0.6, 1], [1, 0.6], ss.lfilter([-0.3, 1], [1, -0.3], mono))
    return np.stack([mono, r], 1)
