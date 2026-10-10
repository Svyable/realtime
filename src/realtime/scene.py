"""Load a scene.yaml: defaults, `extends`, then checks against the registries."""
import copy, os
from pathlib import Path

import yaml

from realtime.catalog import DISTANCE, MOODS, known_effects, known_motions

DEFAULTS = {
    'title': 'Untitled scene',
    'duration_min': 60,
    'seed': 1,
    'keyframe': 'keyframe.jpg',
    'music': {
        'mood': 'late_night',
        'pieces': 'auto',
        'titles': [],
        'waltz_share': None,
        'swing': None,
        'bpm': None,
        'keys': None,
        'setlist': None,
        'carols': [],
        'soundfont': 'freepats-upright-kw',
        'gain': 0.7,
    },
    'piano': {
        'distance': 'closed_door',
        'pan': -0.25,
        'overrides': {},
        'door': None,
    },
    'ambience': {'layers': [], 'accents': []},
    'mix': {
        'piano_lufs': -20.0,
        'bed_lu_below_piano': 10.0,
        'accent_lu_below_piano': 12.0,
        'first_piece_at': 18.0,
        'end_padding': 45.0,
        'gap_s': [18, 40],
        'fade_in': 15.0,
        'fade_out': 25.0,
    },
    'master': {'lufs': -17.0, 'true_peak': -1.5},
    'visual': {
        'fps': 24, 'loop_s': 72, 'width': 1920, 'height': 1080,
        'crop': None,
        'grade': {'lift': 0.012, 'warmth': 0.0, 'saturation': 1.0},
        'motion': {'type': 'none'},
        'effects': [],
        'grain': 0.020, 'vignette': 0.32, 'bloom': 0.5,
    },
    'thumbnail': {
        'text': None, 'font': 'Limelight-Regular.ttf', 'color': '#EFE3C8', 'glow': '#E8A54B',
        'position': 'top-right', 'size': 110, 'lift': 0.08,
    },
    'preview': {'start_s': 'auto'},
    'release_encode': False,
}

_TOP = set(DEFAULTS) | {'extends', 'slug'}


class SceneError(ValueError):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__('\n'.join(self.errors))


def deep_merge(a, b):
    out = copy.deepcopy(a)
    for k, v in (b or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def _unknown(label, raw, known):
    extra = sorted(set(raw or {}) - set(known))
    if not extra:
        return []
    return [f'{label}: unknown {", ".join(extra)}. known: {", ".join(sorted(known))}']


def validate(cfg):
    """Raise SceneError listing every problem in an already-merged scene."""
    err = []
    if not isinstance(cfg.get('duration_min'), (int, float)) or cfg['duration_min'] <= 0:
        err.append('duration_min must be a positive number of minutes')
    music, piano, visual = cfg['music'], cfg['piano'], cfg['visual']
    err += _unknown('music', music, DEFAULTS['music'])
    err += _unknown('piano', piano, DEFAULTS['piano'])
    err += _unknown('mix', cfg['mix'], DEFAULTS['mix'])
    err += _unknown('visual', visual, DEFAULTS['visual'])
    if music['mood'] not in MOODS:
        err.append(f'music.mood {music["mood"]!r} is unknown. known: {", ".join(sorted(MOODS))}')
    if piano['distance'] not in DISTANCE:
        err.append(f'piano.distance {piano["distance"]!r} is unknown. known: {", ".join(sorted(DISTANCE))}')
    motion = (visual.get('motion') or {}).get('type', 'none')
    if motion not in known_motions():
        err.append(f'visual.motion.type {motion!r} is unknown. known: {", ".join(sorted(known_motions()))}')
    effects = known_effects()
    for i, effect in enumerate(visual.get('effects') or []):
        if not isinstance(effect, dict) or 'type' not in effect:
            err.append(f'visual.effects[{i}] needs a type')
            continue
        if effect['type'] not in effects:
            err.append(f'visual.effects[{i}].type {effect["type"]!r} is unknown. known: {", ".join(sorted(effects))}')
    for i, layer in enumerate((cfg.get('ambience') or {}).get('layers') or []):
        if not isinstance(layer, dict) or not layer.get('file'):
            err.append(f'ambience.layers[{i}] needs a file')
    if err:
        raise SceneError(err)
    return cfg


def load(path, overrides=None, check=True):
    path = os.path.abspath(path)
    raw = yaml.safe_load(open(path)) or {}
    if not isinstance(raw, dict):
        raise SceneError([f'{path} must be a mapping'])
    extra = sorted(set(raw) - _TOP)
    if extra:
        raise SceneError([f'unknown scene keys: {", ".join(extra)}. known: {", ".join(sorted(_TOP - {"extends"}))}'])
    base = DEFAULTS
    if raw.get('extends'):
        parent = os.path.join(os.path.dirname(path), raw.pop('extends'))
        base = load(parent, check=False)
    cfg = deep_merge(base, raw)
    cfg = deep_merge(cfg, overrides or {})
    cfg['_dir'] = os.path.dirname(path)
    cfg['_file'] = path
    cfg['slug'] = cfg.get('slug') or os.path.basename(cfg['_dir'])
    if check:
        validate(cfg)
    return cfg


def keyframe_path(cfg):
    kf = cfg['keyframe']
    return kf if os.path.isabs(kf) else os.path.join(cfg['_dir'], kf)


def write_template(dest_dir):
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=False)
    from importlib.resources import files
    src = files('realtime').joinpath('templates')
    for name in ('scene.yaml', 'prompt.md'):
        (dest / name).write_text(src.joinpath(name).read_text())
    return dest
