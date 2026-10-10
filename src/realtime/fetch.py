"""Download the engine's own assets into the first asset cache. Sound effects stay with the project."""
import hashlib, os, shutil, subprocess, urllib.request
from pathlib import Path

from realtime.runtime import asset_dirs

UA = 'realtime-setup/0.1 (github.com/Svyable/realtime)'
# (relative path under the cache, url, sha256, unpacker or None)
ENGINE_ASSETS = [
    ('soundfonts/UprightPianoKW-SF2-20220221.7z',
     'https://freepats.zenvoid.org/Piano/UprightPianoKW/UprightPianoKW-SF2-20220221.7z',
     '17c084c6e4205233dc49b34e4bc44a9b2d7c7a2c02b04729ecda77079b07c826', '7z'),
    ('models/EDSR_x2.pb',
     'https://github.com/Saafke/EDSR_Tensorflow/raw/master/models/EDSR_x2.pb',
     '585623221baa070279a0d1e7e113a4c3faba0f318ca7fdd9a65d9afc0763d9b4', None),
    ('fonts/Limelight-Regular.ttf',
     'https://github.com/google/fonts/raw/main/ofl/limelight/Limelight-Regular.ttf',
     'f5bf8a9159adfc5b9c756c85d812a4fd1299b8916fefdf39ad4b24ade6d8d0cf', None),
    ('fonts/DMSerifDisplay-Regular.ttf',
     'https://github.com/google/fonts/raw/main/ofl/dmserifdisplay/DMSerifDisplay-Regular.ttf',
     '8cc3643535edf039aa5d95440a8542735e9197e4f4b8d9303e980fefbf5ab616', None),
    ('fonts/PoiretOne-Regular.ttf',
     'https://github.com/google/fonts/raw/main/ofl/poiretone/PoiretOne-Regular.ttf',
     '457f2d03263f58e5a6dbcc1b607b10dff6581e7cf9c4ebdf330ec3e6772a3558', None),
]


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _seven_zip():
    for name in ('7z', '7zz'):
        if shutil.which(name):
            return name
    return None


def cache_dir():
    """Where `realtime setup` writes. An explicit REALTIME_ASSETS wins; otherwise ~/.cache/realtime."""
    if os.environ.get('REALTIME_ASSETS'):
        return Path(os.environ['REALTIME_ASSETS']).expanduser()
    return Path.home() / '.cache' / 'realtime'


def setup(log=print):
    dest_root = cache_dir()
    dest_root.mkdir(parents=True, exist_ok=True)
    for rel, url, digest, unpack in ENGINE_ASSETS:
        dest = dest_root / rel
        if dest.exists() and _sha256(dest) == digest:
            log(f'ok   {dest}')
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            part = dest.with_suffix(dest.suffix + '.part')
            log(f'get  {dest.name}')
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=120) as resp, open(part, 'wb') as out:
                shutil.copyfileobj(resp, out)
            got = _sha256(part)
            if got != digest:
                part.unlink(missing_ok=True)
                raise RuntimeError(f'checksum mismatch for {url}: {got}')
            os.replace(part, dest)
        if unpack == '7z':
            sf2 = dest_root / 'soundfonts' / 'UprightPianoKW-SF2-20220221' / 'UprightPianoKW-20220221.sf2'
            if not sf2.exists():
                tool = _seven_zip()
                if not tool:
                    raise RuntimeError('7z is required to unpack the piano soundfont (p7zip or 7zip)')
                subprocess.run([tool, 'x', '-y', f'-o{dest.parent}', str(dest)], check=True, stdout=subprocess.DEVNULL)
    log(f'setup complete -> {dest_root}')
    return dest_root


def doctor():
    """Return a list of (ok, name, detail) rows."""
    rows = []
    for tool in ('ffmpeg', 'ffprobe', 'fluidsynth'):
        rows.append((bool(shutil.which(tool)), tool, shutil.which(tool) or 'not on PATH'))
    rows.append((bool(_seven_zip()), '7z', _seven_zip() or 'not on PATH (needed once, to unpack the piano)'))
    caches = asset_dirs()
    sf2 = []
    edsr = None
    fonts = []
    for cache in caches:
        sf2 += list(cache.glob('soundfonts/**/*.sf2'))
        model = cache / 'models' / 'EDSR_x2.pb'
        if model.exists():
            edsr = model
        fonts += list((cache / 'fonts').glob('*.ttf')) if (cache / 'fonts').exists() else []
    rows.append((bool(sf2), 'piano soundfont', str(sf2[0]) if sf2 else 'missing, run `realtime setup`'))
    rows.append((bool(edsr), 'EDSR x2 model', str(edsr) if edsr else 'missing, run `realtime setup` (Lanczos is used without it)'))
    rows.append((len(fonts) >= 1, 'thumbnail fonts', f'{len(fonts)} found' if fonts else 'missing, run `realtime setup`'))
    return rows
