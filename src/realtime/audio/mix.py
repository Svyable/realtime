"""Audio stages: render piano -> 'another room' chain -> ambience bed + rare accents -> mix -> master.
Long buses are float32 memmaps in <work>/ so an hour-long mix fits in little RAM."""
import os, json, subprocess, re, numpy as np, scipy.signal as ss, soundfile as sf
from realtime.audio.dsp import *
from realtime.catalog import DISTANCE
from realtime.runtime import current

def preset(cfg):
    name = cfg['piano']['distance']
    if name not in DISTANCE:
        known = ', '.join(sorted(DISTANCE))
        raise KeyError(f'unknown piano distance {name!r}. known: {known}')
    p = dict(DISTANCE[name]); p.update(cfg['piano'].get('overrides') or {}); return p

def soundfont_path(name):
    if name.endswith('.sf2') and os.path.exists(name): return name
    hits = current().soundfonts()
    if name == 'freepats-upright-kw': hits = [h for h in hits if 'UprightPianoKW' in h]
    if not hits: raise FileNotFoundError('Piano soundfont missing: run `realtime setup`')
    return hits[0]

def render_piano(mid, out, sf2, gain=0.7):
    subprocess.run(['fluidsynth', '-ni', '-R', '0', '-C', '0', '-g', str(gain), '-r', str(SR), '-F', out, sf2, mid],
                   check=True, capture_output=True)

def trim_tail(x, floor_db=-62):
    a = np.abs(x).max(1); pk = a.max(); idx = np.where(a > pk * 10 ** (floor_db / 20))[0]
    y = x[max(0, idx[0] - int(0.05 * SR)):min(len(x), idx[-1] + SR)].copy()
    fo = int(1.5 * SR); y[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 2; return y

def room_chain(x, p, pan=-0.25, door=None, seed=0):
    """The 'from the next room' sound. x: dry stereo piano. door: (t_open, hold, open_s, close_s, lpf_open)."""
    r = np.random.default_rng(seed)
    x = filt(x, 'highpass', p['hpf'], 2)
    x = p['dry'] * x + p['wet'] * convolve(x, make_ir(p['rt'], p.get('predelay', 0.02), p['rt'] * 1.7, 11))
    closed = filt(x, 'lowpass', p['lpf'], 4)
    if door:
        t0, hold, o, c, lpf_open = door
        opened = filt(x, 'lowpass', lpf_open, 4); t = np.arange(len(x)) / SR
        env = np.clip((t - t0) / o, 0, 1) * np.clip(1 - (t - (t0 + o + hold)) / c, 0, 1)
        env = 0.5 - 0.5 * np.cos(np.pi * env); x = closed * (1 - env)[:, None] + opened * env[:, None]
    else: x = closed
    if p.get('body_db'): x = peq(x, 200, p['body_db'])
    if p.get('speaker_db'): x = peq(x, 1000, p['speaker_db'], 1.2)        # small cabinet speaker honk
    mid = x.mean(1); side = (x[:, 0] - x[:, 1]) / 2 * p['width']
    t = np.arange(len(mid)) / SR; w = p['wow'] / 1000 * SR
    d = 0.003 * SR + w * (np.sin(2 * np.pi * 0.45 * t + r.uniform(0, 6)) + 0.4 * np.sin(2 * np.pi * 0.17 * t + r.uniform(0, 6))) \
        + 0.00003 * SR * np.sin(2 * np.pi * 6.3 * t)
    mid = var_delay(mid, d); side = var_delay(side, d)
    pk = np.max(np.abs(mid)) + 1e-9; dr = p['drive']
    mid = np.tanh(dr * mid / pk * 0.6) / np.tanh(dr * 0.6) * pk
    a = (1 + pan) * np.pi / 4; gL, gR = np.cos(a), np.sin(a)
    y = np.stack([(mid + side) * gL, (mid - side) * gR], 1) * np.sqrt(2)
    y = y + p['listen'] * convolve(y, make_ir(0.25, 0.003, 0.4, 12))
    return y * compressor_gain(y.mean(1), -30, 1.8, 0.03, 0.6)[:, None]

# ---- ambience -----------------------------------------------------------------------------
def prep_source(L):
    """Load + shape one bed/accent source according to its layer config."""
    x = load(current().resolve(L['file']), 2, L.get('start'), L.get('end'))
    if L.get('mono'): x = pseudo_stereo(x.mean(1))
    if L.get('level_ride'): x = level_ride(x)
    if L.get('hpf'): x = filt(x, 'highpass', L['hpf'], 2)
    if L.get('lpf'): x = filt(x, 'lowpass', L['lpf'], L.get('lpf_order', 2))
    for f0, g, q in L.get('peaks', []): x = peq(x, f0, g, q)
    x = tame_transients(x, L.get('smooth', 0.6))
    if L.get('lpf_after_smooth'): x = filt(x, 'lowpass', L['lpf_after_smooth'], 2)
    return x * np.array(L.get('pan', [1.0, 1.0]))

def bed_into(out, src, rng, seg=(30, 80), xf=4.0, gain=1.0):
    """Random-offset re-sequencing with equal-power crossfades: no audible loop period."""
    N = len(out); L = len(src); X = int(xf * SR)
    seg = (min(seg[0], (L - X - 1) / SR * 0.8), min(seg[1], (L - X - 1) / SR))
    fi = np.sin(np.linspace(0, np.pi / 2, X)); fo = np.cos(np.linspace(0, np.pi / 2, X)); pos, last = 0, None
    while pos < N:
        ln = int(rng.uniform(*seg) * SR); st = int(rng.uniform(0, max(1, L - ln - X)))
        if last is not None and abs(st - last) < 5 * SR: st = (st + L // 2) % max(1, L - ln - X)
        last = st; piece = src[st:st + ln + X].copy()
        piece[:X] *= fi[:, None]; piece[-X:] *= fo[:, None]; e = min(N, pos + len(piece))
        out[pos:e] += (piece[:e - pos] * gain).astype(np.float32); pos += ln

def place_accents(out, accents, rng, dur, log, base_lufs):
    """Rare accents (thunder, far whistle, ship's bell, horn). times: explicit [s] or per_hour."""
    for A in accents:
        x = prep_source(A)
        if A.get('distance_reverb'): x = 0.3 * x + 0.8 * convolve(x, make_ir(A['distance_reverb'], 0.06, A['distance_reverb'] * 1.5, 21))
        clip = A.get('clip_s', len(x) / SR); n = min(len(x), int(clip * SR))
        g = 10 ** ((base_lufs - A.get('extra_lu_below', 0) - lufs(x[:n])) / 20)
        times = A.get('times_s')
        if not times and dur < 600: times = [dur * 0.45] if A.get('in_test', True) else []   # test renders: one, mid-way
        elif not times:   # stratified: one per equal slice of the video, so they never bunch up
            cnt = max(0, int(round(A.get('per_hour', 1) * dur / 3600))); sl = (dur - 240) / max(1, cnt)
            times = [120 + k * sl + rng.uniform(0.15, 0.85) * sl for k in range(cnt)]
        for tt in times:
            st = int(rng.uniform(0, max(1, len(x) - n))); c = x[st:st + n].copy()
            fi, fo = int(min(3, clip / 4) * SR), int(min(6, clip / 3) * SR)
            c[:fi] *= np.linspace(0, 1, fi)[:, None]; c[-fo:] *= np.linspace(1, 0, fo)[:, None]
            s0 = int(tt * SR); e = min(len(out), s0 + n); out[s0:e] += (c[:e - s0] * g).astype(np.float32)
            log.append({'accent': A.get('name', A['file']), 'at': round(float(tt), 1)})

# ---- stages -------------------------------------------------------------------------------
def mm(work, name, N):
    return np.lib.format.open_memmap(f'{work}/{name}.npy', mode='w+', dtype=np.float32, shape=(N, 2))

def build_piano_bus(cfg, work, midis, dur, log):
    """Render + process each piece, place with gaps, return memmap bus and timeline."""
    SRN = int(dur * SR); p = preset(cfg); mx = cfg['mix']; rng = np.random.default_rng(cfg['seed'])
    sf2 = soundfont_path(cfg['music']['soundfont']); door = cfg['piano'].get('door')
    pieces = []
    for i, (mid, spec) in enumerate(midis):
        wav = f'{work}/dry_{i:02d}.wav'
        if not os.path.exists(wav): render_piano(mid, wav, sf2, cfg['music']['gain'])
        pieces.append((wav, spec))
    lens = [sf.info(w).duration for w, _ in pieces]
    avail = dur - mx['first_piece_at'] - mx['end_padding']
    while len(pieces) > 1 and sum(lens) + mx['gap_s'][0] * (len(pieces) - 1) > avail:
        pieces.pop(); lens.pop()
    gap_total = max(0, avail - sum(lens)); ng = max(1, len(pieces) - 1)
    raw = rng.uniform(0.7, 1.3, ng); gaps = np.minimum(raw / raw.sum() * gap_total, mx['gap_s'][1] * 1.5)
    bus = mm(work, 'piano', SRN); t = mx['first_piece_at']; tl = []
    door_at = door and door.get('at_min', dur / 60 * 0.58) * 60
    for k, (wav, spec) in enumerate(pieces):
        y = trim_tail(load(wav)); d = None
        if door and t <= door_at < t + len(y) / SR - 30:
            d = (door_at - t, door.get('hold_s', 120), door.get('open_s', 8), door.get('close_s', 10), door.get('open_lpf', p['lpf'] * 1.65))
        y = room_chain(y, p, cfg['piano']['pan'], d, seed=k)
        y *= 10 ** ((mx['piano_lufs'] - lufs(y)) / 20)
        s0 = int(t * SR); e = min(SRN, s0 + len(y)); bus[s0:e] += y[:e - s0].astype(np.float32)
        ent = {'title': spec['title'], 'key': spec['key'], 'bpm': spec['bpm'], 'start': round(t, 1), 'end': round(t + len(y) / SR, 1)}
        if d: ent['door_open'] = round(t + d[0], 1); ent['door_closed'] = round(t + d[0] + d[1] + d[2] + d[3], 1)
        tl.append(ent); log(f"  piano {k+1}/{len(pieces)} {spec['title']}  {ent['start']:.0f}-{ent['end']:.0f}s")
        t += len(y) / SR + (gaps[k] if k < len(gaps) else 0)
    bus.flush(); return tl

def build_ambience(cfg, work, dur, log):
    N = int(dur * SR); mx = cfg['mix']; rng = np.random.default_rng(cfg['seed'] + 1)
    bed = mm(work, 'bed', N); layers = cfg['ambience']['layers']
    bed_target = mx['piano_lufs'] - mx['bed_lu_below_piano']
    for L in layers:   # each layer pre-levelled to its share of the bed, then the bed as a whole is set
        x = prep_source(L); g = 10 ** ((bed_target + L.get('gain_db', 0) - lufs(x)) / 20)
        bed_into(bed, x, rng, tuple(L.get('seg', (30, 80))), L.get('xf', 4.0), g)
        log(f"  bed layer {L.get('name', L['file'])}: share {L.get('gain_db', 0):+.1f} dB")
    if layers:
        idx = np.linspace(0, N - 10 * SR, 20).astype(int)
        lv = lufs(np.vstack([bed[i:i + 10 * SR] for i in idx]))
        g = 10 ** ((bed_target - lv) / 20)
        for s in range(0, N, 60 * SR): bed[s:s + 60 * SR] *= g
    bed.flush()
    acc = mm(work, 'accents', N); evlog = []
    place_accents(acc, cfg['ambience'].get('accents', []), rng, dur, evlog, mx['piano_lufs'] - mx['accent_lu_below_piano'])
    acc.flush(); return evlog

def mixdown(cfg, work, dur, buses=('piano', 'bed', 'accents'), gains_db=None):
    N = int(dur * SR); mx = cfg['mix']; gains_db = gains_db or {}
    b = {n: np.load(f'{work}/{n}.npy', mmap_mode='r') for n in buses}
    out = mm(work, 'mix', N); fi, fo = int(mx['fade_in'] * SR), int(mx['fade_out'] * SR)
    for s0 in range(0, N, 60 * SR):
        e = min(N, s0 + 60 * SR); idx = np.arange(s0, e)
        env = np.sin(np.minimum(np.clip(idx / fi, 0, 1), np.clip((N - idx) / fo, 0, 1)) * np.pi / 2) ** 2
        m = sum(np.asarray(b[n][s0:e], np.float64) * 10 ** (gains_db.get(n, 0) / 20) for n in buses if n != 'piano')
        m = m * env[:, None] + np.asarray(b['piano'][s0:e], np.float64) * 10 ** (gains_db.get('piano', 0) / 20)
        out[s0:e] = m.astype(np.float32)
    out.flush()

def ebur128(path):
    o = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', path, '-af', 'ebur128=peak=true', '-f', 'null', '-'],
                       capture_output=True, text=True).stderr
    return {'lufs': float(re.findall(r'I:\s+(-?[\d.]+) LUFS', o)[-1]), 'true_peak': float(re.findall(r'Peak:\s+(-?[\d.]+) dBFS', o)[-1]),
            'lra': float(re.findall(r'LRA:\s+(-?[\d.]+) LU', o)[-1])}

def master(cfg, work, out_wav, mix_name='mix'):
    mix = np.load(f'{work}/{mix_name}.npy', mmap_mode='r'); raw = f'{work}/{mix_name}_raw.wav'
    with sf.SoundFile(raw, 'w', SR, 2, 'FLOAT') as f:
        for i in range(0, len(mix), SR * 60): f.write(np.asarray(mix[i:i + SR * 60]))
    m = ebur128(raw); g = cfg['master']['lufs'] - m['lufs']; tp = cfg['master']['true_peak'] - 0.7   # limiter ceiling w/ ISP margin
    af = f'volume={g:.2f}dB,alimiter=limit={10 ** (tp / 20):.4f}:attack=4:release=120:level=disabled'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', raw, '-af', af, '-c:a', 'pcm_s24le', out_wav], check=True)
    res = ebur128(out_wav); os.remove(raw); return res

def bed_vs_piano(work, timeline, n=12):
    """Measured LU gap between piano and bed on 10 s windows inside pieces (QC)."""
    pb = np.load(f'{work}/piano.npy', mmap_mode='r'); bb = np.load(f'{work}/bed.npy', mmap_mode='r'); d = []
    for p in timeline:
        for t in np.linspace(p['start'] + 20, p['end'] - 30, 3):
            if t <= p['start']: continue
            s = int(t * SR); a, b = lufs(pb[s:s + 10 * SR]), lufs(bb[s:s + 10 * SR])
            if a > -60 and b > -60: d.append(a - b)
    return (round(float(np.median(d)), 1), round(float(np.min(d)), 1), round(float(np.max(d)), 1)) if d else None
