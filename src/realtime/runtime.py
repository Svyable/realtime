"""The active workspace: where a scene looks for assets and where a build writes.

Search order for a relative asset path:
  1. the scene directory
  2. the project root (--root, or the current directory)
  3. each asset cache, then <cache>/sfx

Asset caches, first match wins for downloads:
  $REALTIME_ASSETS, $VER_ASSETS, ~/.cache/realtime, ~/.cache/vintage-era-radio
"""
import contextvars, glob, os
from pathlib import Path

_current = contextvars.ContextVar('realtime_workspace', default=None)


class Workspace:
    def __init__(self, scene_file, root, out, asset_dirs):
        self.scene_file = Path(scene_file).resolve()
        self.scene_dir = self.scene_file.parent
        self.root = Path(root).resolve()
        self.out = Path(out).resolve()
        self.asset_dirs = [Path(p).expanduser().resolve() for p in asset_dirs]

    def resolve(self, rel):
        raw = Path(rel)
        if raw.is_absolute() and raw.exists():
            return str(raw)
        bases = [self.scene_dir, self.root]
        for cache in self.asset_dirs:
            bases.append(cache)
            bases.append(cache / 'sfx')
        for base in bases:
            cand = base / rel
            if cand.exists():
                return str(cand)
        looked = '\n  '.join(str(b) for b in bases)
        raise FileNotFoundError(f'asset not found: {rel}\nlooked in:\n  {looked}\nRun `realtime setup`, or pass --root to the project that holds the files.')

    def find(self, *parts):
        for cache in self.asset_dirs:
            cand = cache.joinpath(*parts)
            if cand.exists():
                return str(cand)
        return None

    def soundfonts(self):
        hits = []
        for cache in self.asset_dirs:
            hits += glob.glob(str(cache / 'soundfonts' / '**' / '*.sf2'), recursive=True)
        return hits


def asset_dirs():
    dirs = []
    for key in ('REALTIME_ASSETS', 'VER_ASSETS'):
        if os.environ.get(key):
            dirs.append(Path(os.environ[key]).expanduser())
    dirs.append(Path.home() / '.cache' / 'realtime')
    dirs.append(Path.home() / '.cache' / 'vintage-era-radio')
    out, seen = [], set()
    for d in dirs:
        s = str(d)
        if s not in seen:
            seen.add(s)
            out.append(d)
    return out


def default_media():
    for key in ('REALTIME_MEDIA', 'VER_MEDIA'):
        if os.environ.get(key):
            return Path(os.environ[key]).expanduser()
    return Path.cwd() / 'media'


def activate(ws):
    _current.set(ws)
    return ws


def current():
    ws = _current.get()
    if ws is None:
        raise RuntimeError('no realtime workspace is active')
    return ws
