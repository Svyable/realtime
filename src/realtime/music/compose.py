#!/usr/bin/env python3
"""
Vintage Era Radio: original slow jazz-ballad piano composer.

Generates ORIGINAL solo-piano ballads as MIDI (no existing melodies are used):
hand-written original chord progressions (generic jazz-ballad harmony: ii-V-I,
turnarounds, bridges to IV / relative minor), algorithmically composed motivic
melodies, rootless left-hand voicings with voice leading, bass roots, rolled
chords, fills, block-chord passages, rubato tempo map, velocity humanisation,
and legato sustain pedal.

Usage: compose.py <setlist.json> <outdir>
Spec keys: key, bpm, seed, beats_per_bar (3 = waltz), A/A_last/B/tag progressions, form, swing (0..0.16).
Moved here from videos/2026-10-night-train-dining-car/tools/compose.py (identical output when swing is 0).
"""
import json, math, random, sys, os
import mido

NOTE = {'C':0,'Db':1,'D':2,'Eb':3,'E':4,'F':5,'Gb':6,'G':7,'Ab':8,'A':9,'Bb':10,'B':11}

# ---- chord vocabulary -------------------------------------------------------
# rootless voicing forms (intervals above root, stacked ascending)
VOICINGS = {
 'maj7': [[4,7,11,14],[11,14,16,19],[4,7,9,14]],
 '69':   [[4,7,9,14],[9,14,16,19],[2,4,7,9]],
 'm7':   [[3,7,10,14],[10,14,15,19],[3,5,7,10]],
 'm6':   [[3,7,9,14],[9,14,15,19]],
 'mM7':  [[3,7,11,14],[11,14,15,19]],
 '7':    [[4,9,10,14],[10,14,16,21]],
 '7b9':  [[4,9,10,13],[10,13,16,21]],
 '7alt': [[4,10,15,20],[10,16,20,27]],
 '7s11': [[4,10,14,18],[10,14,16,18]],
 'm7b5': [[3,6,10,14],[10,15,17,18],[0,3,6,10]],
 'dim7': [[0,3,6,9],[3,6,9,12]],
 '7sus': [[5,10,14,21],[10,14,17,21]],
}
SCALE = {
 'maj7':[0,2,4,7,9,11], '69':[0,2,4,7,9,11], 'm7':[0,2,3,5,7,9,10], 'm6':[0,2,3,5,7,9],
 'mM7':[0,2,3,5,7,9,11], '7':[0,2,4,7,9,10], '7b9':[0,1,3,4,7,8,10], '7alt':[0,1,3,4,6,8,10],
 '7s11':[0,2,4,6,7,9,10], 'm7b5':[0,3,5,6,8,10], 'dim7':[0,2,3,5,6,8,9,11], '7sus':[0,2,5,7,9,10],
}
TONES = {  # melody targets for strong / long notes
 'maj7':[4,7,11,2], '69':[4,7,9,2], 'm7':[3,7,10,2], 'm6':[3,7,9,2], 'mM7':[3,7,11,2],
 '7':[4,10,2,9], '7b9':[4,10,1,7], '7alt':[4,10,3,8], '7s11':[4,10,2,6], 'm7b5':[3,6,10,0],
 'dim7':[0,3,6,9], '7sus':[5,10,2,7],
}

def parse_chord(sym, key):
    """sym like 'ii:m7' where degree is semitones e.g. '2:m7' relative to key."""
    deg, q = sym.split(':')
    return ((key + int(deg)) % 12, q)

# ---- rhythm cells (onset, dur) in beats over 2 bars ------------------------
CELLS44 = [
 [(0,1.5),(1.5,0.5),(2,2),(4,3)],
 [(0,0.67),(0.67,0.67),(1.33,0.67),(2,2),(4,1),(5,2.5)],
 [(1,1),(2,1),(3,1),(4,3.5)],
 [(0,3),(3,0.5),(3.5,0.5),(4,1),(5,1),(6,1.5)],
 [(0.5,0.5),(1,0.5),(1.5,1.5),(3,1),(4,3.5)],
 [(0,2),(2,1),(3,1),(4,2),(6,1)],
 [(0,0.33),(0.33,0.33),(0.67,0.33),(1,2),(3,0.5),(3.5,0.5),(4,3.5)],
 [(0,1),(1,1),(2,1.5),(3.5,0.5),(4,3)],
 [(2,0.5),(2.5,0.5),(3,1),(4,1.5),(5.5,0.5),(6,1.5)],
 [(0,4),(4,0.5),(4.5,0.5),(5,0.5),(5.5,2)],
]
CELLS34 = [
 [(0,2),(2,1),(3,2.5)],
 [(0,1),(1,1),(2,1),(3,2.5)],
 [(1,1),(2,1),(3,2),(5,0.5)],
 [(0,1.5),(1.5,0.5),(2,1),(3,2.5)],
 [(0,0.67),(0.67,0.67),(1.33,0.67),(2,1),(3,2.5)],
 [(0,3),(3,1),(4,1.5)],
]

class Piece:
    def __init__(self, spec, seed):
        self.s = spec
        self.r = random.Random(seed)
        self.key = NOTE[spec['key']]
        self.bpb = spec.get('beats_per_bar', 4)
        self.events = []   # (beat, dur_beats, pitch, vel, track)
        self.pedal = []    # (beat, value)
        self.tempo_marks = {}  # beat -> factor overrides
        self.prev_voicing = None
        self.prev_bass = 43
        self.mel_last = 74 + self.r.choice([-2,0,2])

    # -- helpers --
    def chords_of(self, section):
        out = []
        for bar in section:
            if isinstance(bar, str): bar = [bar]
            n = len(bar); d = self.bpb / n
            for c in bar:
                out.append((parse_chord(c, self.key), d))
        return out

    def voicing(self, root, q):
        best = None
        for form in VOICINGS[q]:
            for octv in range(3, 7):
                base = 12*octv + root
                v = [base + i for i in form]
                if v[0] < 50 or v[-1] > 71: continue
                cost = 0 if self.prev_voicing is None else sum(abs(a-b) for a,b in zip(sorted(v), sorted(self.prev_voicing)))
                cost += self.r.random()*2
                if best is None or cost < best[0]: best = (cost, v)
        if best is None:
            v = [48 + root + i for i in VOICINGS[q][0]]
            while v[-1] > 71: v = [x-12 for x in v]
            best = (0, v)
        self.prev_voicing = best[1]
        return best[1]

    def bass(self, root):
        cands = [p for p in range(33, 52) if p % 12 == root]
        p = min(cands, key=lambda c: abs(c - self.prev_bass) + (3 if c > 47 else 0))
        self.prev_bass = p
        return p

    def add(self, beat, dur, pitch, vel, track):
        vel = max(18, min(100, int(vel)))
        self.events.append((beat, max(0.1, dur), int(pitch), vel, track))

    # -- melody --
    def snap(self, p, pcs, direction=0):
        for d in range(0, 12):
            for s in ([d, -d] if direction >= 0 else [-d, d]):
                if (p + s) % 12 in pcs: return p + s
        return p

    def chord_at(self, timeline, beat):
        for (b0, dur, root, q) in timeline:
            if b0 <= beat < b0 + dur: return root, q
        return timeline[-1][2], timeline[-1][3]

    def gen_phrase(self, timeline, start, cell, template=None, cadence=False):
        """returns list of (beat, dur, pitch)"""
        notes = []
        r = self.r
        prev = self.mel_last
        contour = r.choice(['arch', 'down', 'up', 'arch', 'valley'])
        n = len(cell)
        for i, (on, du) in enumerate(cell):
            b = start + on
            root, q = self.chord_at(timeline, b)
            tones = [(root + t) % 12 for t in TONES[q]]
            scale = [(root + t) % 12 for t in SCALE[q]]
            strong = (on % 2 == 0) or du >= 1.5 or i == n-1
            if template is not None and i < len(template):
                target = prev + template[i]
            else:
                pos = i / max(1, n-1)
                if contour == 'arch': d = 1 if pos < 0.5 else -1
                elif contour == 'down': d = -1
                elif contour == 'up': d = 1 if pos < 0.8 else -1
                else: d = -1 if pos < 0.5 else 1
                step = r.choice([1,2,2,3]) if not strong else r.choice([2,3,4,5])
                target = prev + d*step if i > 0 else prev + r.choice([-3,-1,0,2,4])
            # register pull toward centre
            if target > 84: target -= r.choice([3,4,5])
            if target < 66: target += r.choice([3,4,5])
            pcs = tones if strong else scale
            if cadence and i == n-1:
                pcs = [(root + t) % 12 for t in (TONES[q][:1] + TONES[q][3:4] + TONES[q][1:2])]
            p = self.snap(target, pcs, 1 if target >= prev else -1)
            if notes and p == notes[-1][2] and r.random() < 0.6:
                p = self.snap(p + r.choice([-2, 2]), pcs)
            notes.append((b, du, p))
            prev = p
        self.mel_last = prev
        return notes

    def melody_for_section(self, timeline, start, nbars, motif_cells, reuse=None, cadence_end=True):
        """returns melody notes for one section; if reuse given, replays with refit."""
        span = 2 * self.bpb
        out = []
        cells = CELLS44 if self.bpb == 4 else CELLS34
        if reuse is not None:
            for (b, du, p) in reuse['notes']:
                nb = b - reuse['start'] + start
                root, q = self.chord_at(timeline, nb)
                strong = du >= 1.5 or ((nb - start) % 2 == 0)
                pcs = [(root + t) % 12 for t in (TONES[q] if strong else SCALE[q])]
                out.append((nb, du, self.snap(p, pcs)))
            return out
        stmt = None
        for ph in range(nbars // 2):
            s = start + ph * span
            last = (ph == nbars//2 - 1)
            if ph % 2 == 0:
                cell = motif_cells[(ph // 2) % len(motif_cells)]
                notes = self.gen_phrase(timeline, s, cell)
                stmt = notes
            else:
                # answer: same rhythm, sequenced contour (or a fresh cell to cadence)
                if last or self.r.random() < 0.35:
                    cell = self.r.choice(cells)
                    notes = self.gen_phrase(timeline, s, cell, cadence=last and cadence_end)
                else:
                    tmpl = [0] + [stmt[k][2] - stmt[k-1][2] for k in range(1, len(stmt))]
                    shift = self.r.choice([-2, -3, 2, -4])
                    self.mel_last = stmt[0][2] + shift
                    tmpl[0] = 0
                    cell = [(b - (s - span), du) for (b, du, p) in stmt]
                    notes = self.gen_phrase(timeline, s, cell, template=tmpl)
            out.extend(notes)
        return out

    def embellish(self, notes, timeline, amount):
        r = self.r; out = []
        for k, (b, du, p) in enumerate(notes):
            nxt = notes[k+1] if k+1 < len(notes) else None
            if nxt and du >= 2 and r.random() < amount and nxt[0] - (b + du) < 0.6:
                keep = du - 1.0
                out.append((b, keep, p))
                root, q = self.chord_at(timeline, b + keep)
                sc = sorted(set((root + t) % 12 for t in SCALE[q]))
                # triplet run toward next note
                tgt = nxt[2]; cur = p; run = []
                direction = 1 if tgt > p else -1
                for j in range(3):
                    cur = self.snap(cur + direction*2, sc, direction)
                    run.append(cur)
                for j, rp in enumerate(run):
                    out.append((b + keep + j/3, 1/3, rp))
            elif du >= 1 and r.random() < amount*0.5 and k > 0:
                # chromatic enclosure into this note
                out.append((b - 0.33, 0.17, p + 1))
                out.append((b - 0.17, 0.17, p - 1))
                out.append((b, du, p))
            else:
                out.append((b, du, p))
        return out

    # -- accompaniment --
    def comp(self, timeline, style, vel_base, mel_notes):
        r = self.r
        for (b0, dur, root, q) in timeline:
            v = self.voicing(root, q)
            # keep voicing below melody
            top_mel = [p for (b, d, p) in mel_notes if b0 <= b < b0 + dur]
            if top_mel:
                lim = min(top_mel) - 2
                while v[-1] > lim and v[0] - 12 >= 45: v = [x - 12 for x in v]
                v = [x for x in v if x <= lim] or v[:2]
            bp = self.bass(root)
            self.add(b0, dur, bp, vel_base + 8 + r.randint(-3, 3), 'bass')
            if dur >= 4 and r.random() < 0.3 and style != 'sparse':
                self.add(b0 + 2, dur - 2, bp + r.choice([7, 12, 15, 16]) if bp + 16 < 60 else bp + 7, vel_base - 2, 'bass')
            if style == 'broken':
                step = r.choice([0.5, 0.67])
                for j, p in enumerate(v):
                    t = b0 + 0.5 + j*step
                    if t < b0 + dur - 0.2:
                        self.add(t, b0 + dur - t, p, vel_base - 4 + r.randint(-4, 4), 'lh')
            else:
                roll = r.choice([0.03, 0.05, 0.08, 0.15]) if style != 'sparse' else 0.2
                delay = r.choice([0.0, 0.05, 0.5]) if dur >= 2 else 0.0
                for j, p in enumerate(v):
                    self.add(b0 + delay + j*roll, dur - delay - j*roll, p, vel_base + r.randint(-5, 4), 'lh')
                if style == 'pulse' and dur >= 4:
                    for j, p in enumerate(v):
                        self.add(b0 + 2.5 + j*0.03, dur - 2.6, p, vel_base - 8 + r.randint(-3, 3), 'lh')
            # pedal: legato change
            self.pedal.append((b0 - 0.02, 0))
            self.pedal.append((b0 + 0.12, 127))

    def fills(self, timeline, mel_notes, start, end, vel):
        """small arpeggio fills in melody gaps >= 1.5 beats"""
        r = self.r
        ms = sorted(mel_notes)
        for k in range(len(ms)):
            gap_start = ms[k][0] + ms[k][1]
            gap_end = ms[k+1][0] if k+1 < len(ms) else end
            if gap_end - gap_start >= 1.5 and r.random() < 0.55 and gap_start < end:
                root, q = self.chord_at(timeline, gap_start)
                tones = sorted(set((root + t) % 12 for t in TONES[q]))
                p = 67 + r.randint(0, 6); seq = []
                for j in range(r.choice([3, 4, 6])):
                    p = self.snap(p + (2 if j else 0), tones, 1); seq.append(p); p += 1
                if r.random() < 0.5: seq = seq[::-1]
                t0 = gap_start + 0.25
                for j, pp in enumerate(seq):
                    t = t0 + j/3
                    if t < gap_end - 0.2:
                        self.add(t, max(0.3, gap_end - t), pp, vel - 6 - j + r.randint(-3, 3), 'mel')

    def block(self, mel_notes, timeline, vel):
        """Locked-hands style block chords under melody notes (dur >= 1)."""
        for (b, du, p) in mel_notes:
            if du < 0.9: continue
            root, q = self.chord_at(timeline, b)
            tones = [(root + t) % 12 for t in TONES[q]]
            under = []; x = p - 1
            while len(under) < 3 and x > p - 12:
                if x % 12 in tones and (not under or under[-1] - x >= 2): under.append(x)
                x -= 1
            for u in under:
                self.add(b + 0.02, du, u, vel - 12, 'mel')
            if self.r.random() < 0.5: self.add(b + 0.02, du, p - 12, vel - 14, 'mel')

    # -- build --
    def build(self):
        s = self.s; r = self.r
        A = s['A']; B = s.get('B', A)
        A_last = s.get('A_last', A)
        intro = s.get('intro', A_last[-4:] if len(A_last) >= 4 else A_last)
        form = s.get('form', ['intro', 'A', 'A2', 'B', 'A3', 'solo', 'Bh', 'A3h', 'tag'])
        cells = CELLS44 if self.bpb == 4 else CELLS34
        motif = [r.choice(cells), r.choice(cells)]
        motifB = [r.choice(cells), r.choice(cells)]
        beat = 0.0
        sections = []
        memo = {}
        mel_base = s.get('mel_vel', 62)
        for name in form:
            if name == 'intro':
                tl = self._tl(intro, beat)
                mel = []
                for (b0, du, root, q) in tl:
                    pcs = [(root + t) % 12 for t in TONES[q]]
                    p = self.snap(76 + r.randint(-2, 3), pcs)
                    mel.append((b0 + 0.6, du - 0.6, p))
                self.comp(tl, 'sparse', 36, mel)
                for (b, d, p) in mel: self.add(b, d, p, mel_base - 10 + r.randint(-3, 3), 'mel')
                nb = len(intro) * self.bpb
                self.tempo_marks[('intro', beat, beat + nb)] = 0.86
                self.tempo_marks[('ferm', beat + nb - 1, beat + nb)] = 0.5
                beat += nb
                continue
            if name == 'tag':
                tag = s.get('tag', A_last[-4:])
                tl = self._tl(tag + s.get('final', ['0:69']), beat)
                mel = []
                for (b0, du, root, q) in tl[:-1]:
                    pcs = [(root + t) % 12 for t in TONES[q]]
                    mel.append((b0, du - 0.3, self.snap(self.mel_last + r.choice([-2, -1, 1]), pcs)))
                    self.mel_last = mel[-1][2]
                last = tl[-1]
                self.comp(tl[:-1], 'sustain', 38, mel)
                for (b, d, p) in mel: self.add(b, d, p, mel_base - 6 + r.randint(-3, 3), 'mel')
                # final rolled chord: bass, voicing, sparkle on top
                root, q = last[2], last[3]
                b0 = last[0]
                self.add(b0, 8, self.bass(root), 44, 'bass')
                v = self.voicing(root, q)
                for j, p in enumerate(v + [x + 12 for x in v[-2:]]):
                    self.add(b0 + 0.15 + j*0.22, 8 - j*0.2, p, 36 + j, 'lh')
                spark = self.snap(84, [(root + 2) % 12, (root + 7) % 12])
                self.add(b0 + 2.2, 6, spark, 34, 'mel')
                self.pedal.append((b0 - 0.02, 0)); self.pedal.append((b0 + 0.1, 127))
                self.pedal.append((b0 + 10.0, 0))
                nb = (len(tag)) * self.bpb
                self.tempo_marks[('rit', beat, beat + nb + 8)] = 'rit'
                beat += nb + 8
                self.end_beat = beat
                continue
            base = name.rstrip('h0123456789') if name != 'solo' else 'solo'
            half = name.endswith('h')
            if base == 'A': sec = A_last if name.startswith('A3') else A
            elif base == 'B': sec = B
            else: sec = A + B + A_last if self.bpb == 4 else A + A_last
            tl = self._tl(sec, beat)
            nb = len(sec) * self.bpb
            if name == 'A2' and 'A' in memo:
                mel = self.melody_for_section(tl, beat, len(sec), motif, reuse=memo['A'])
                # vary the ending of second A
                mel = [m for m in mel if m[0] < beat + nb - 2 * self.bpb] + \
                      self.gen_phrase(tl, beat + nb - 2*self.bpb, r.choice(cells), cadence=True)
            elif name.startswith('A3') and 'A3' in memo:
                mel = self.melody_for_section(tl, beat, len(sec), motif, reuse=memo['A3'])
            elif name.startswith('A3') and 'A' in memo:
                mel = self.melody_for_section(tl, beat, len(sec), motif, reuse=memo['A'])
                mel = [m for m in mel if m[0] < beat + nb - 2 * self.bpb] + \
                      self.gen_phrase(tl, beat + nb - 2*self.bpb, r.choice(cells), cadence=True)
            elif base == 'B' and 'B' in memo:
                mel = self.melody_for_section(tl, beat, len(sec), motifB, reuse=memo['B'])
            else:
                mel = self.melody_for_section(tl, beat, len(sec), motifB if base == 'B' else motif)
            mkey = 'A3' if name.startswith('A3') else base
            if base in ('A', 'B') and mkey not in memo and not half:
                memo[mkey] = {'start': beat, 'notes': mel}
            if base == 'solo':
                mel = self.melody_for_section(tl, beat, len(sec), [r.choice(cells), r.choice(cells)])
                mel = self.embellish(mel, tl, 0.45)
                style = r.choice(['broken', 'pulse', 'sustain'])
                vel = mel_base + 2
                # block chords on the middle third
                blk = [m for m in mel if beat + nb/3 <= m[0] < beat + 2*nb/3]
                if s.get('block', True): self.block(blk, tl, vel)
            else:
                if half: mel = self.embellish(mel, tl, 0.2)
                style = 'broken' if base == 'B' and r.random() < 0.6 else r.choice(['sustain', 'sustain', 'pulse'])
                vel = mel_base + (3 if base == 'B' else 0) - (4 if half else 0)
            self.comp(tl, style, 38 if base != 'solo' else 40, mel)
            self.fills(tl, mel, beat, beat + nb, vel)
            for (b, d, p) in mel:
                # phrase dynamics: swell toward middle of 4-bar phrase
                ph = ((b - beat) % (4*self.bpb)) / (4*self.bpb)
                arc = 6 * math.sin(math.pi * ph)
                self.add(b, d * 0.97, p, vel + arc + r.randint(-4, 4), 'mel')
            beat += nb
        self.total_beats = beat

    def _tl(self, section, start):
        tl = []; b = start
        for (ch, d) in self.chords_of(section):
            tl.append((b, d, ch[0], ch[1])); b += d
        return tl

    # -- tempo / output --
    def tempo_factor(self, beat):
        f = 1.0
        phrase = 4 * self.bpb
        pos = (beat % phrase) / phrase
        f *= 1.0 + 0.035 * math.sin(2 * math.pi * pos) - (0.10 if pos > 1 - 1.5/phrase else 0)
        for k, val in self.tempo_marks.items():
            kind, a, b = k
            if a <= beat < b:
                if val == 'rit':
                    x = (beat - a) / (b - a)
                    f *= max(0.45, 1.0 - 0.55 * x)
                else:
                    f *= val
        return f

    def write(self, path):
        bpm = self.s['bpm']
        mid = mido.MidiFile(type=1, ticks_per_beat=480)
        tracks = {n: mido.MidiTrack() for n in ['tempo', 'mel', 'lh', 'bass', 'pedal']}
        for n, t in tracks.items():
            mid.tracks.append(t); t.append(mido.MetaMessage('track_name', name=n, time=0))
        tracks['tempo'].append(mido.MetaMessage('time_signature', numerator=self.bpb, denominator=4, time=0))
        tracks['mel'].append(mido.Message('program_change', program=0, channel=0, time=0))
        # tempo per half beat
        tev = []
        b = 0.0
        while b < self.total_beats + 16:
            tempo = mido.bpm2tempo(bpm * self.tempo_factor(b) * (1 + self.r.uniform(-0.012, 0.012)))
            tev.append((int(b * 480), mido.MetaMessage('set_tempo', tempo=int(tempo))))
            b += 0.5
        evs = {n: [] for n in tracks}
        evs['tempo'] = tev
        for (b, d, p, v, tr) in self.events:
            jit = self.r.gauss(0, 0.012)
            if tr == 'mel': jit -= 0.015
            sw = self.s.get('swing', 0)          # 0 = straight; 0.08-0.16 = lazy swing feel on off-beat 8ths
            if sw and 0.4 < (b % 1) < 0.6:
                b = b + sw; d = max(0.1, d - sw)
            on = max(0, b + jit); off = on + d
            evs[tr].append((int(on * 480), mido.Message('note_on', note=p, velocity=v, channel=0)))
            evs[tr].append((int(off * 480), mido.Message('note_off', note=p, velocity=0, channel=0)))
        for (b, val) in self.pedal:
            evs['pedal'].append((int(max(0, b) * 480), mido.Message('control_change', control=64, value=val, channel=0)))
        evs['pedal'].append((int((self.total_beats + 2) * 480), mido.Message('control_change', control=64, value=0, channel=0)))
        for n, t in tracks.items():
            lst = sorted(evs[n], key=lambda e: (e[0], 0 if getattr(e[1], 'type', '') == 'note_off' else 1))
            last = 0
            for (tick, msg) in lst:
                t.append(msg.copy(time=tick - last)); last = tick
        mid.save(path)
        return mid.length

def compose_setlist(setlist, outdir, log=print):
    os.makedirs(outdir, exist_ok=True)
    files = []
    for i, spec in enumerate(setlist['pieces']):
        if spec.get('carol'):
            from .carols import Carol
            pc = Carol(spec, spec.get('seed', 1000 + i))
        else:
            pc = Piece(spec, spec.get('seed', 1000 + i))
        pc.build()
        fn = os.path.join(outdir, f"{i+1:02d}_{spec['slug']}.mid")
        L = pc.write(fn); files.append((fn, L))
        log(f"  {os.path.basename(fn)} key={spec['key']} bpm={spec['bpm']} {L/60:.2f} min")
    return files

if __name__ == '__main__':
    setlist = json.load(open(sys.argv[1])); outdir = sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    tot = 0
    for i, spec in enumerate(setlist['pieces']):
        pc = Piece(spec, spec.get('seed', 1000 + i))
        pc.build()
        fn = os.path.join(outdir, f"{i+1:02d}_{spec['slug']}.mid")
        L = pc.write(fn)
        tot += L
        print(f"{fn}  key={spec['key']} bpm={spec['bpm']} beats={pc.total_beats:.0f} len={L/60:.2f} min")
    print(f"total {tot/60:.2f} min")
