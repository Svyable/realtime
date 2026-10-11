"""Scene kits and the material index. Kits ship with the package. The nature beds live in the git repo."""
import os
from pathlib import Path

import yaml

from realtime.version import __version__

KITS = Path(__file__).resolve().parent / 'kits'


def kit_names():
    return sorted(p.stem for p in KITS.glob('*.yaml'))


def read_kit(name):
    path = KITS / f'{name}.yaml'
    if not path.is_file():
        known = ', '.join(kit_names()) or '(none)'
        raise SystemExit(f'unknown kit {name!r}. known: {known}')
    return path.read_text()


def write_kit(name, dest_dir):
    """Write scenes/<name>/scene.yaml and prompt.md. Refuses to replace an existing directory."""
    dest = Path(dest_dir) / name
    dest.mkdir(parents=True, exist_ok=False)
    (dest / 'scene.yaml').write_text(read_kit(name))
    prompt = KITS / f'{name}.md'
    if prompt.is_file():
        (dest / 'prompt.md').write_text(prompt.read_text())
    return dest


def find_catalog(root=None):
    bases = []
    if root:
        bases.append(Path(root).expanduser())
    bases.append(Path.cwd())
    bases.append(Path(__file__).resolve().parents[2])
    seen = set()
    for base in bases:
        p = (base / 'materials' / 'catalog.yaml').resolve()
        if p in seen:
            continue
        seen.add(p)
        if p.is_file():
            return p
    return None


def report(root=None):
    """Text an agent can scan before it picks a kit, a bed, or a carol."""
    from realtime.music.carols import TUNES
    lines = [f'realtime {__version__} materials', '']
    catalog_path = find_catalog(root)
    catalog = yaml.safe_load(catalog_path.read_text()) if catalog_path else {}
    repo = catalog_path.parents[1] if catalog_path else None

    lines.append('kits    realtime kit <name>')
    described = {row['id']: row for row in catalog.get('kits') or []}
    for name in kit_names():
        row = described.get(name, {})
        flag = ''
        if row:
            flag = '  offline' if row.get('offline') else '  needs realtime setup --sfx'
        lines.append(f'  {name}{flag}')
        if row.get('picture'):
            lines.append(f'      picture  {row["picture"]}')
        if row.get('music'):
            lines.append(f'      music    {row["music"]}')
        if row.get('sound'):
            lines.append(f'      sound    {row["sound"]}')
    lines.append('')
    lines.append('carols  name these in music.carols')
    for cid in sorted(TUNES):
        tune = TUNES[cid]
        lines.append(f'  {cid:24} {tune["title"]}  (written {tune["written_key"]}, {tune["beats_per_bar"]} beats/bar)')
    lines.append('')
    if catalog_path:
        lines.append(f'beds    {catalog_path}')
        present = 0
        for bed in catalog.get('beds') or []:
            ok = repo is not None and (repo / bed['path']).is_file()
            present += bool(ok)
            mark = 'ok  ' if ok else 'MISS'
            lines.append(f'  {mark} {bed["role"]:16} {bed["path"]}')
        lines.append(f'  {present} of {len(catalog.get("beds") or [])} beds on disk')
        manifest_path = repo / 'materials' / 'sfx' / 'pdsounds' / 'manifest.yaml'
        if manifest_path.is_file():
            manifest = yaml.safe_load(manifest_path.read_text()) or {}
            files = manifest.get('files') or []
            counts = {}
            for item in files:
                counts[item['role']] = counts.get(item['role'], 0) + 1
            summary = ', '.join(f'{role} {counts[role]}' for role in sorted(counts))
            mb = sum(item.get('bytes') or 0 for item in files) / 1e6
            lines.append('')
            lines.append(f'reservoir  {len(files)} public-domain environmental recordings, {mb:.0f} MB')
            lines.append('  materials/sfx/pdsounds')
            lines.append(f'  {summary}')
            lines.append('  PDSounds.org via Wikimedia Commons. Speech, music, and close-miked foley were not copied.')
    else:
        lines.append('beds    catalog not found. Clone the realtime repo and pass --root.')
    lines.append('')
    lines.append('fetch   realtime setup --sfx')
    for row in catalog.get('fetch') or []:
        lines.append(f'  {row["id"]:42} {row["license"]:22} {row["role"]}')
    lines.append('')
    lines.append('engines')
    for row in catalog.get('engines') or []:
        lines.append(f'  {row["id"]:16} {row["license"]}')
        lines.append(f'      {row["what"]}')
    if not catalog:
        lines.append('  composer, carols, fluidsynth, ffmpeg, visual-loop')
        lines.append('  FreePats upright piano and EDSR weights: realtime setup')
    return os.linesep.join(lines) + '\n'
