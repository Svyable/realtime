"""Stage graph. A stage reruns when its own inputs, its code, or an upstream stage key changes.

Audio and picture share no files until `video`, so a runner may build them at the same time.
"""
import hashlib, json
from pathlib import Path

from realtime.version import __version__

STAGES = ['compose', 'piano', 'ambience', 'mix', 'master', 'plate', 'loop', 'video', 'preview', 'thumbnail', 'qc', 'release']

NEEDS = {
    'compose': (),
    'piano': ('compose',),
    'ambience': ('piano',),
    'mix': ('piano', 'ambience'),
    'master': ('mix',),
    'plate': (),
    'loop': ('plate',),
    'video': ('master', 'loop'),
    'preview': ('video',),
    'thumbnail': ('plate',),
    'qc': ('video', 'master'),
    'release': ('video',),
}

# Top-level scene keys that affect each stage. Upstream stage keys carry the rest.
SLICES = {
    'compose': ('seed', 'duration_min', 'music'),
    'piano': ('seed', 'duration_min', 'music', 'piano', 'mix'),
    'ambience': ('seed', 'duration_min', 'ambience', 'mix'),
    'mix': ('mix',),
    'master': ('master', 'mix'),
    'plate': ('keyframe', 'visual'),
    'loop': ('visual',),
    'video': ('duration_min', 'visual'),
    'preview': ('preview', 'duration_min'),
    'thumbnail': ('thumbnail', 'visual'),
    'qc': ('master', 'mix', 'duration_min', 'visual'),
    'release': ('duration_min', 'release_encode'),
}

CODE = {
    'compose': ('music/setlist.py', 'music/compose.py', 'music/carols.py', 'music/data/progressions.json'),
    'piano': ('audio/mix.py', 'audio/dsp.py'),
    'ambience': ('audio/mix.py', 'audio/dsp.py'),
    'mix': ('audio/mix.py',),
    'master': ('audio/mix.py', 'audio/dsp.py'),
    'plate': ('visual/engine.py',),
    'loop': ('visual/engine.py',),
    'video': ('runner.py',),
    'preview': ('runner.py',),
    'thumbnail': ('runner.py', 'visual/engine.py'),
    'qc': ('runner.py', 'audio/mix.py'),
    'release': ('runner.py',),
}

AUDIO = ('compose', 'piano', 'ambience', 'mix', 'master')
VISUAL = ('plate', 'loop', 'thumbnail')


def expand_needs(only):
    """Include every stage an explicitly requested stage depends on."""
    need = set(only)
    growing = True
    while growing:
        growing = False
        for stage in list(need):
            for dep in NEEDS[stage]:
                if dep not in need:
                    need.add(dep)
                    growing = True
    return need


def _code_hash(stage):
    root = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for rel in CODE[stage]:
        h.update(rel.encode())
        path = root / rel
        h.update(path.read_bytes() if path.exists() else b'missing')
    return h.hexdigest()


def stage_key(stage, cfg, upstream, test=False, version=None, extra=None):
    payload = {
        'version': version or __version__,
        'stage': stage,
        'test': bool(test),
        'inputs': {k: cfg.get(k) for k in SLICES[stage]},
        'upstream': {k: upstream.get(k) for k in NEEDS[stage]},
        'code': _code_hash(stage),
        'extra': extra or {},
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()
