"""An original set list from a mood. Chord templates are scale degrees, so every seed is a new piece."""
import json, os, random

from realtime.catalog import MOODS, WORDS

HERE = os.path.dirname(os.path.abspath(__file__))
FORMS = [['intro', 'A', 'A2', 'B', 'A3', 'solo', 'Bh', 'A3h', 'tag'],
         ['intro', 'A', 'A2', 'B', 'A3', 'Bh', 'A3h', 'tag'],
         ['intro', 'A', 'A2', 'B', 'A3', 'tag']]
TEST_FORM = ['intro', 'A', 'A3', 'tag']


def est_minutes(form, bpm, bpb):
    bars = {'intro': 4, 'A': 8, 'A2': 8, 'B': 8, 'A3': 8, 'solo': 8, 'Bh': 8, 'A3h': 8, 'tag': 6}
    beats = sum(bars.get(f, 8) for f in form) * bpb
    return beats / bpm * 1.3


def generate(cfg, music_minutes, test=False):
    m = cfg['music']
    if m['mood'] not in MOODS:
        raise KeyError(f'unknown mood {m["mood"]!r}. known: {", ".join(sorted(MOODS))}')
    mood = MOODS[m['mood']]
    r = random.Random(cfg['seed'] * 7919 + 13)
    tpls = json.load(open(os.path.join(HERE, 'data', 'progressions.json')))['templates']
    bpm = m['bpm'] or mood['bpm']
    keys = m['keys'] or mood['keys']
    waltz = mood['waltz'] if m['waltz_share'] is None else m['waltz_share']
    swing = mood['swing'] if m['swing'] is None else m['swing']
    w4 = [t for t in tpls if t.get('beats_per_bar', 4) == 4]
    w3 = [t for t in tpls if t.get('beats_per_bar', 4) == 3]
    adj, nouns = WORDS[m['mood']]
    used = set()
    pieces, tot, i = [], 0.0, 0
    target_n = None if m['pieces'] == 'auto' else int(m['pieces'])
    carols = list(m.get('carols') or [])
    if carols:
        from realtime.music.carols import TUNES
        car_specs = []
        for j, cid in enumerate(carols):
            T = TUNES[cid]
            bpb = T['beats_per_bar']
            cb = len(T['bars']) * bpb
            nch = 4 if cb < 50 else 3
            sp = dict(carol=cid, title=T['title'], basis=T['basis'], beats_per_bar=bpb, key=r.choice(keys),
                      bpm=int(r.uniform(*bpm)) - (6 if bpb == 3 else 0), seed=cfg['seed'] * 1000 + 500 + j * 41, swing=0.0)
            sp['slug'] = cid
            car_specs.append((sp, (16 + cb * nch + 8) / sp['bpm'] * 1.3))
        music_minutes -= sum(m_ for _, m_ in car_specs)
        if test:
            return {'generated_by': 'realtime', 'mood': m['mood'], 'pieces': [dict(car_specs[0][0])]}
    while (target_n is None and tot < music_minutes) or (target_n is not None and i < target_n):
        t = dict(r.choice(w3 if (w3 and r.random() < waltz) else w4))
        bpb = t.get('beats_per_bar', 4)
        p = {k: t[k] for k in ('A', 'A_last', 'B', 'tag') if k in t}
        p.update(beats_per_bar=bpb, key=keys[i % len(keys)] if i < len(keys) else r.choice(keys),
                 bpm=int(r.uniform(*bpm)) - (4 if bpb == 3 else 0), seed=cfg['seed'] * 1000 + i * 37 + 5,
                 swing=round(swing * r.uniform(0.7, 1.2), 3) if swing and bpb == 4 else 0.0,
                 form=TEST_FORM if test else r.choice(FORMS), template=t['source'])
        if i < len(m['titles']):
            title = m['titles'][i]
        else:
            for _ in range(50):
                title = f"{r.choice(adj)} {r.choice(nouns)}"
                if title not in used:
                    break
        used.add(title)
        p['title'] = title
        p['slug'] = ''.join(c if c.isalnum() else '-' for c in title.lower()).strip('-')
        pieces.append(p)
        tot += est_minutes(p['form'], p['bpm'], bpb)
        i += 1
        if test:
            break
    if carols:
        out, ci = [], 0
        for k, p in enumerate(pieces):
            out.append(p)
            if ci < len(car_specs) and k % 1 == 0:
                out.append(car_specs[ci][0])
                ci += 1
        out += [c for c, _ in car_specs[ci:]]
        pieces = out
    return {'generated_by': 'realtime', 'mood': m['mood'], 'pieces': pieces}
