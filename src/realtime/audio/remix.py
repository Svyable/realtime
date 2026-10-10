"""Remix an already-built episode from its saved buses (work/*.npy) with a lighter ambience preset,
without re-rendering piano or visuals. Used for the Night Train 'light mix' (scenes/night-train-dining-car/remix-light.yaml).

  python -m pipeline.remix scenes/night-train-dining-car/remix-light.yaml [--window START DUR] [--video SRC.mp4 --out OUT.mp4]
"""
import argparse, os, json, subprocess, numpy as np, yaml, soundfile as sf
from realtime.audio.dsp import SR, filt, peq, tame_transients, lufs
from realtime.audio.mix import ebur128

def process(x, P):
    if P.get('hpf'): x = filt(x, 'highpass', P['hpf'], 2)
    if P.get('lpf'): x = filt(x, 'lowpass', P['lpf'], P.get('lpf_order', 2))
    for f0, g, q in P.get('peaks', []): x = peq(x, f0, g, q)
    return tame_transients(x, P.get('smooth', 0))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('preset'); ap.add_argument('--window', nargs=2, type=float)
    ap.add_argument('--video'); ap.add_argument('--out'); a = ap.parse_args()
    P = yaml.safe_load(open(a.preset)); work = P['work']; buses = P['buses']
    b = {n: np.load(f'{work}/{n}.npy', mmap_mode='r') for n in list(buses) + ['piano']}
    N = len(b['piano']); s0, dur = (int(a.window[0] * SR), a.window[1]) if a.window else (0, N / SR)
    pre = 10 * SR; lo = max(0, s0 - pre); hi = min(N, s0 + int(dur * SR))
    piano = np.asarray(b['piano'][lo:hi], np.float64)
    target = P['piano_lufs'] - P['bed_lu_below_piano']
    # measure each processed bus on sparse 20 s windows across the whole hour so the gain is window-independent
    bed = 0; levels = {}
    for n, cfg in buses.items():
        if cfg.get('accent'): continue
        idx = np.linspace(0, N - 30 * SR, 12).astype(int)
        ref = np.vstack([process(np.asarray(b[n][i:i + 30 * SR], np.float64), cfg)[5 * SR:] for i in idx])
        g = 10 ** ((target + cfg.get('gain_db', 0) - lufs(ref)) / 20); levels[n] = round(20 * np.log10(g), 1)
        bed = bed + process(np.asarray(b[n][lo:hi], np.float64), cfg) * g
    idx = np.linspace(0, N - 30 * SR, 12).astype(int)   # trim the summed bed to the exact target (layers overlap/correlate)
    tot = 0
    for n, cfg in buses.items():
        if cfg.get('accent'): continue
        tot = tot + np.vstack([process(np.asarray(b[n][i:i + 30 * SR], np.float64), cfg)[5 * SR:] for i in idx]) * 10 ** (levels[n] / 20)
    fix = target - lufs(tot); bed = bed * 10 ** (fix / 20)
    for n, cfg in buses.items():
        if cfg.get('accent'):   # level the accent bus by its ACTIVE parts to piano - lu_below
            ev = b[n]; act = [i for i in range(0, N - 10 * SR, 10 * SR) if np.abs(ev[i:i + 10 * SR:480]).max() > 1e-5]
            ref = np.vstack([process(np.asarray(ev[i:i + 10 * SR], np.float64), cfg) for i in act]) if act else None
            g = 10 ** ((P['piano_lufs'] - cfg['lu_below_piano'] - lufs(ref)) / 20) if act else 0
            levels[n] = round(20 * np.log10(g), 1) if g else None
            bed = bed + process(np.asarray(ev[lo:hi], np.float64), cfg) * g
    mix = (piano + bed)[s0 - lo:]
    raw = '/tmp/remix_raw.wav'; sf.write(raw, mix.astype(np.float32), SR, subtype='FLOAT')
    m = ebur128(raw) if len(mix) > 3 * SR else None
    g = P['master']['lufs'] - (P.get('reference_raw_lufs') or m['lufs'])
    tp = P['master']['true_peak'] - 0.7
    wav = (a.out or 'remix') + '.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', raw, '-af', f'volume={g:.2f}dB,alimiter=limit={10 ** (tp / 20):.4f}:attack=4:release=120:level=disabled',
                    '-c:a', 'pcm_s24le', wav], check=True)
    rep = {'bus_gains_db': levels, 'bed_trim_db': round(fix, 2), 'master_gain_db': round(g, 2), 'master': ebur128(wav)}
    pw = piano[s0 - lo:]; bw = bed[s0 - lo:]; d = []
    for t in range(0, len(pw) - 10 * SR, 10 * SR):
        pa, ba = lufs(pw[t:t + 10 * SR]), lufs(bw[t:t + 10 * SR])
        if pa > -50: d.append(round(pa - ba, 1))
    rep['piano_minus_bed_LU_10s_windows'] = d
    if a.video and a.out:
        st = s0 / SR
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(st), '-i', a.video, '-i', wav, '-t', str(dur), '-map', '0:v', '-map', '1:a',
                        '-c:v', 'libx264', '-crf', '20', '-preset', 'medium', '-vf', 'fade=in:d=1,fade=out:st=%.2f:d=1.5' % (dur - 1.5),
                        '-af', 'afade=in:d=2,afade=out:st=%.2f:d=3' % (dur - 3), '-c:a', 'aac', '-b:a', '256k', '-movflags', '+faststart', a.out], check=True)
        os.remove(wav)
    print(json.dumps(rep, indent=1)); return rep

if __name__ == '__main__': main()
