"""Public-domain carol melodies, transcribed by hand from the traditional/original tunes (see each 'basis'),
re-harmonised with our own jazz-ballad chords and arranged by the same piano engine as the originals.
Nothing here is taken from a modern arrangement.

Bar format: (melody, chords). melody = "G4:.75 A4:.25 R:1 ..." (pitch:beats, R = rest), written in the tune's
'written_key'; chords use compose.py symbols ("degree:quality", degree = semitones above the key)."""
import math
from realtime.music.compose import Piece, NOTE, TONES

TUNES = {
 'silent-night': dict(
    title='Silent Night', basis='Franz Xaver Gruber, "Stille Nacht" (1818); public domain worldwide',
    written_key='C', beats_per_bar=3, bars=[
    ('G4:.75 A4:.25 G4:.5 E4:1.5', '0:69'), ('G4:.75 A4:.25 G4:.5 E4:1.5', '0:maj7'),
    ('D5:1 D5:.5 B4:1.5', '7:7'), ('C5:1 C5:.5 G4:1.5', '0:69'),
    ('A4:1 A4:.5 C5:.75 B4:.25 A4:.5', '5:maj7'), ('G4:.75 A4:.25 G4:.5 E4:1.5', '0:maj7'),
    ('A4:1 A4:.5 C5:.75 B4:.25 A4:.5', '5:maj7'), ('G4:.75 A4:.25 G4:.5 E4:1.5', '0:69'),
    ('D5:1 D5:.5 F5:.75 D5:.25 B4:.5', '7:7'), ('C5:1.5 E5:1.5', '0:maj7'),
    ('C5:.5 G4:.5 E4:.5 G4:.75 F4:.25 D4:.5', ['0:69', '7:7']), ('C4:3', '0:69')]),
 'o-christmas-tree': dict(
    title='O Christmas Tree', basis='German folk melody "O Tannenbaum" (traditional; lyrics Ernst Anschütz 1824); public domain',
    written_key='G', beats_per_bar=3, bars=[
    ('R:2 D4:1', '7:7'),
    ('G4:.75 G4:.25 G4:1.5 A4:.5', '0:69'), ('B4:.75 B4:.25 B4:1.5 B4:.5', '0:maj7'),
    ('A4:.5 B4:.5 C5:1 F#4:1', ['9:m7', '2:7']), ('A4:1 G4:1 D5:1', '0:69'),
    ('D5:.5 B4:.5 E5:1.5 D5:.5', '4:m7'), ('D5:.5 C5:.5 C5:1.5 C5:.5', '2:7'),
    ('C5:.5 A4:.5 D5:1.5 C5:.5', '2:7'), ('C5:.5 B4:.5 B4:1 D4:1', '0:maj7'),
    ('G4:.75 G4:.25 G4:1.5 A4:.5', '0:69'), ('B4:.75 B4:.25 B4:1.5 B4:.5', '0:maj7'),
    ('A4:.5 B4:.5 C5:1 F#4:1', ['9:m7', '2:7']), ('A4:1 G4:2', '0:69')]),
 'the-first-noel': dict(
    title='The First Noel', basis='Traditional English carol (Cornish origin; printed by Davies Gilbert 1823 and William Sandys 1833); public domain',
    written_key='C', beats_per_bar=3, bars=[
    ('R:2 E4:.5 D4:.5', '7:7'),
    ('C4:1.5 D4:.5 E4:.5 F4:.5', '0:maj7'), ('G4:2 A4:.5 B4:.5', '0:69'), ('C5:1 B4:1 A4:1', '9:m7'), ('G4:2 A4:.5 B4:.5', '0:69'),
    ('C5:1 B4:1 A4:1', '9:m7'), ('G4:1 A4:1 B4:1', '4:m7'), ('C5:1 G4:1 F4:1', ['2:m7', '7:7']), ('E4:2 E4:.5 D4:.5', '0:maj7'),
    ('C4:1.5 D4:.5 E4:.5 F4:.5', '0:maj7'), ('G4:2 C5:.5 B4:.5', '0:69'), ('A4:2 A4:1', '5:maj7'), ('G4:3', '0:69'),
    ('C5:1 B4:1 A4:1', '9:m7'), ('G4:1 A4:1 B4:1', '4:m7'), ('C5:1 G4:1 F4:1', ['2:m7', '7:7']), ('E4:3', '0:69')]),
 'deck-the-halls': dict(
    title='Deck the Halls', basis='Welsh traditional melody "Nos Galan" (16th-18th c.); public domain',
    written_key='F', beats_per_bar=4, bars=[
    ('C5:1.5 Bb4:.5 A4:1 G4:1', '0:maj7'), ('F4:1 G4:1 A4:1 F4:1', ['0:69', '2:m7']),
    ('G4:.5 A4:.5 Bb4:.5 G4:.5 A4:1.5 G4:.5', ['2:m7', '7:7']), ('F4:1 E4:1 F4:2', ['7:7', '0:69']),
    ('C5:1.5 Bb4:.5 A4:1 G4:1', '0:maj7'), ('F4:1 G4:1 A4:1 F4:1', ['0:69', '2:m7']),
    ('G4:.5 A4:.5 Bb4:.5 G4:.5 A4:1.5 G4:.5', ['2:m7', '7:7']), ('F4:1 E4:1 F4:2', ['7:7', '0:69']),
    ('G4:1.5 A4:.5 Bb4:1 G4:1', '7:7'), ('A4:1.5 Bb4:.5 C5:1 G4:1', '5:maj7'),
    ('A4:.5 B4:.5 C5:1 D5:.5 E5:.5 F5:1', ['2:m7', '7:7']), ('E5:1 D5:1 C5:2', '7:7sus'),
    ('C5:1.5 Bb4:.5 A4:1 G4:1', '0:maj7'), ('F4:1 G4:1 A4:1 F4:1', ['0:69', '2:m7']),
    ('D5:.5 D5:.5 D5:.5 D5:.5 C5:1.5 Bb4:.5', ['5:maj7', '7:7']), ('A4:1 G4:1 F4:2', ['7:7', '0:69'])]),
 'jingle-bells': dict(
    title='Jingle Bells', basis='James Lord Pierpont, "One Horse Open Sleigh" (1857; the familiar chorus as republished in 1859); public domain. Chorus only, as a slow ballad',
    written_key='C', beats_per_bar=4, bars=[
    ('E4:1 E4:1 E4:2', '0:maj7'), ('E4:1 E4:1 E4:2', '9:m7'), ('E4:1 G4:1 C4:1.5 D4:.5', ['2:m7', '7:7']), ('E4:4', '0:69'),
    ('F4:1 F4:1 F4:1.5 F4:.5', '5:maj7'), ('F4:1 E4:1 E4:1 E4:.5 E4:.5', ['5:maj7', '0:69']), ('E4:1 D4:1 D4:1 E4:1', '2:7'), ('D4:2 G4:2', '7:7'),
    ('E4:1 E4:1 E4:2', '0:maj7'), ('E4:1 E4:1 E4:2', '9:m7'), ('E4:1 G4:1 C4:1.5 D4:.5', ['2:m7', '7:7']), ('E4:4', '0:69'),
    ('F4:1 F4:1 F4:1 F4:1', '5:maj7'), ('F4:1 E4:1 E4:1 E4:.5 E4:.5', ['5:maj7', '0:69']), ('G4:1 G4:1 F4:1 D4:1', '7:7'), ('C4:4', '0:69')]),
 'we-wish-you': dict(
    title='We Wish You a Merry Christmas', basis='Traditional English West Country carol (folk tune, 19th c. or earlier); transcribed from the traditional tune, not from Arthur Warrell\'s 1935 arrangement; public domain',
    written_key='G', beats_per_bar=3, bars=[
    ('R:2 D4:1', '7:7'),
    ('G4:1 G4:.5 A4:.5 G4:.5 F#4:.5', '0:69'), ('E4:1 C4:1 E4:1', '5:maj7'), ('A4:1 A4:.5 B4:.5 A4:.5 G4:.5', '2:7'), ('F#4:1 D4:1 D4:1', '7:7'),
    ('B4:1 B4:.5 C5:.5 B4:.5 A4:.5', '4:7b9'), ('G4:1 E4:1 D4:.5 D4:.5', '9:m7'), ('E4:1 A4:1 F#4:1', ['9:m7', '2:7']), ('G4:2 R:1', '0:69')]),
}

def parse_melody(s):
    out = []
    for tok in s.split():
        p, d = tok.split(':'); d = float(d)
        if p == 'R': out.append((None, d)); continue
        name, octv = p[:-1], int(p[-1]); acc = {'#': 1, 'b': -1}.get(name[1:2], 0) if len(name) > 1 else 0
        out.append((12 * (octv + 1) + NOTE[name[0]] + acc, d))
    return out

class Carol(Piece):
    """Arrangement: intro (last bars' harmony) -> chorus plain -> chorus with fills/broken comp ->
    chorus with locked-hands block chords -> (short tunes: a soft fourth chorus) -> tag."""
    def build(self):
        s = self.s; r = self.r; T = TUNES[s['carol']]; bpb = self.bpb
        shift = (NOTE[s['key']] - NOTE[T['written_key']]) % 12
        if shift > 6: shift -= 12
        bars = T['bars']; mel_bars = [parse_melody(m) for m, _ in bars]
        pitches = [p for mb in mel_bars for p, _ in mb if p is not None]
        center = (min(pitches) + max(pitches)) / 2 + shift
        octv = 12 * round((71 - center) / 12)          # melody centred around B4/C5
        chords = [c for _, c in bars]
        beat = 0.0; mel_base = s.get('mel_vel', 64)
        # intro: last 4 bars' chords, sparse, slower
        intro = chords[-4:]; tl = self._tl(intro, beat); mel = []
        for (b0, du, root, q) in tl:
            pcs = [(root + t) % 12 for t in TONES[q]]; mel.append((b0 + 0.6, du - 0.6, self.snap(76 + r.randint(-2, 3), pcs)))
        self.comp(tl, 'sparse', 34, mel)
        for (b, d, p) in mel: self.add(b, d, p, mel_base - 12 + r.randint(-3, 3), 'mel')
        nb = len(intro) * bpb; self.tempo_marks[('intro', beat, beat + nb)] = 0.86; self.tempo_marks[('ferm', beat + nb - 1, beat + nb)] = 0.5
        beat += nb
        chorus_beats = len(bars) * bpb
        n_ch = 4 if chorus_beats < 50 else 3
        for c in range(n_ch):
            tl = self._tl(chords, beat); mel = []; b = beat
            for mb in mel_bars:
                for p, d in mb:
                    if p is not None: mel.append((b, d, p + shift + octv + (12 if c == 2 and n_ch == 4 else 0)))
                    b += d
            style = ['sustain', 'broken', 'pulse', 'sustain'][c]
            if c == 1: mel = self.embellish(mel, tl, 0.15)
            vel = mel_base + [0, 2, 4, -6][c]
            if c == 2 and s.get('block', True): self.block([m for m in mel if m[1] >= 0.9], tl, vel)
            self.comp(tl, style, [36, 38, 40, 33][c], mel)
            if c in (1, 3): self.fills(tl, mel, beat, beat + chorus_beats, vel)
            for (bb, d, p) in mel:
                ph = ((bb - beat) % (4 * bpb)) / (4 * bpb)
                self.add(bb, d * 0.97, p, vel + 6 * math.sin(math.pi * ph) + r.randint(-4, 4), 'mel')
            self.mel_last = mel[-1][2] if mel else self.mel_last
            beat += chorus_beats
        # tag: final rolled tonic chord with a sparkle, long ritardando over the last chorus' final bars
        self.tempo_marks[('rit', beat - 2 * bpb, beat + 8)] = 'rit'
        root = self.key; v = self.voicing(root, '69')
        self.add(beat, 8, self.bass(root), 42, 'bass')
        for j, p in enumerate(v + [x + 12 for x in v[-2:]]): self.add(beat + 0.15 + j * 0.22, 8 - j * 0.2, p, 34 + j, 'lh')
        self.add(beat + 2.2, 6, self.snap(84, [(root + 2) % 12, (root + 7) % 12]), 32, 'mel')
        self.pedal += [(beat - 0.02, 0), (beat + 0.1, 127), (beat + 10.0, 0)]
        self.total_beats = beat + 8
