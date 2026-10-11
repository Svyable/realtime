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


# Optional room tone. Checked hashes, CC0 or public domain. Not required for the offline kits.
# Scene files name these as train/wheels_ru_cc0.ogg (the cache's sfx/ directory is on the search path).
SFX_ASSETS = [
    ('sfx/train/wheels_ru_cc0.ogg',
     'https://upload.wikimedia.org/wikipedia/commons/3/36/%D0%A1%D1%82%D1%83%D0%BA_%D0%BA%D0%BE%D0%BB%D1%91%D1%81_%D0%BF%D0%BE%D0%B5%D0%B7%D0%B4%D0%B0.ogg',
     '3319448a22e30ee1ca36a4c5ef98e14e062077b1c985ce166e80ebf6a0df30b5'),
    ('sfx/train/trainride_pd.ogg',
     'https://upload.wikimedia.org/wikipedia/commons/a/a2/Complete_train_ride_4_minutes.ogg',
     'f97d0ed990b7024faf5935438fea5e682cd47aed2e765371fb5a618776e0aff3'),
    ('sfx/train/parovoz_pd.ogg',
     'https://upload.wikimedia.org/wikipedia/commons/c/c6/Parovoz_sound.ogg',
     '838251a89da43f8994b95a1bdaa07064d38291fa96a1314e63e2a18f57991f3e'),
    ('sfx/town/church-bells-leverkusen_pd.oga',
     'https://upload.wikimedia.org/wikipedia/commons/3/36/Church_bells_-_Leverkusen%2C_2007.oga',
     '40e87d6b283fa4ea42438717db94a93f8aff4187ac5968166e7189b441b70a13'),
]


def setup(log=print, sfx=False):
    dest_root = cache_dir()
    dest_root.mkdir(parents=True, exist_ok=True)
    assets = list(ENGINE_ASSETS)
    if sfx:
        assets += [(rel, url, digest, None) for rel, url, digest in SFX_ASSETS]
    for rel, url, digest, unpack in assets:
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
    sfx_n = 0
    for cache in caches:
        folder = cache / 'sfx'
        if folder.exists():
            sfx_n += sum(1 for p in folder.rglob('*') if p.is_file() and p.suffix in {'.ogg', '.oga', '.mp3', '.wav', '.flac'})
    detail = f'{sfx_n} cached' if sfx_n else 'none yet; `realtime setup --sfx` fetches train and bells'
    rows.append((True, 'optional sfx', detail))
    return rows
