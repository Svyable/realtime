"""Command line. `realtime build scene.yaml` makes the hour. `realtime catalog` shows what you can extend."""
import argparse, os, sys

from realtime.catalog import DISTANCE, MOODS, known_effects, known_motions
from realtime.fetch import doctor, setup
from realtime.library import kit_names, report, write_kit
from realtime.scene import SceneError, load, write_template
from realtime.version import __version__


def _catalog(args):
    print(f'realtime {__version__}')
    print('\nmoods')
    for name in sorted(MOODS):
        m = MOODS[name]
        print(f'  {name:12} {m["bpm"][0]}-{m["bpm"][1]} bpm  waltz {m["waltz"]:.2f}  swing {m["swing"]}')
    print('\ndistances')
    for name in sorted(DISTANCE):
        d = DISTANCE[name]
        print(f'  {name:18} low-pass {d["lpf"]} Hz')
    print('\nmotions')
    for name in sorted(known_motions()):
        print(f'  {name}')
    print('\neffects')
    for name in sorted(known_effects()):
        print(f'  {name}')
    if args.plugins:
        _load_plugins()
        print('\nregistered effects after plugins')
        for name in sorted(known_effects()):
            print(f'  {name}')


def _load_plugins():
    from importlib.metadata import entry_points
    import realtime.visual.engine  # noqa: F401  registers the built-in effects
    try:
        group = entry_points(group='realtime.effects')
    except TypeError:
        group = entry_points().get('realtime.effects', ())
    for ep in group:
        ep.load()


def _inspect(args):
    cfg = load(args.scene)
    from realtime.music.setlist import est_minutes, generate
    music_min = (cfg['duration_min'] * 60 - cfg['mix']['first_piece_at'] - cfg['mix']['end_padding']) / 60 * 0.9
    data = generate(cfg, max(1, music_min), test=False) if not cfg['music'].get('setlist') else {'pieces': []}
    print(cfg['slug'])
    print(f'  title     {cfg["title"]}')
    print(f'  length    {cfg["duration_min"]} min   seed {cfg["seed"]}')
    print(f'  mood      {cfg["music"]["mood"]}')
    print(f'  piano     {cfg["piano"]["distance"]}   pan {cfg["piano"]["pan"]}')
    print(f'  bed       {cfg["mix"]["bed_lu_below_piano"]} LU under the piano')
    print(f'  motion    {cfg["visual"]["motion"].get("type", "none")}')
    print(f'  effects   {", ".join(e["type"] for e in cfg["visual"]["effects"]) or "(none)"}')
    if data['pieces']:
        minutes = sum(est_minutes(p['form'], p['bpm'], p['beats_per_bar']) for p in data['pieces'] if 'form' in p)
        print(f'  pieces    {len(data["pieces"])}  (~{minutes:.0f} min of music before gaps)')
        for p in data['pieces']:
            print(f'    {p["title"]}  {p.get("key", "")}  {p.get("bpm", "")} bpm')


def _build(args):
    _load_plugins()
    from realtime.runner import Build
    try:
        report = Build(args.scene, args.test, args.force or (), args.only, args.procs, args.out, args.root).run()
    except SceneError as e:
        sys.exit(str(e))
    if report is not None and not report.get('pass', True):
        sys.exit(2)


def _regions(args):
    _load_plugins()
    import cv2
    from realtime.runtime import Workspace, activate, asset_dirs
    import realtime.visual.engine as V
    cfg = load(args.scene)
    out = args.out or os.path.join(os.getcwd(), 'media', cfg['slug'])
    activate(Workspace(cfg['_file'], args.root or os.getcwd(), out, asset_dirs()))
    os.makedirs(out, exist_ok=True)
    plate = V.load_plate(cfg, cfg['visual']['width'], cfg['visual']['height'], print)
    dest = os.path.join(cfg['_dir'], 'regions-preview.jpg')
    V.regions_preview(cfg, plate, dest)
    cv2.imwrite(os.path.join(out, 'plate.png'), plate)
    print(dest)


def _still(args):
    _load_plugins()
    import cv2
    from realtime.runtime import Workspace, activate, asset_dirs
    import realtime.visual.engine as V
    cfg = load(args.scene)
    out = os.path.join(os.getcwd(), 'media', cfg['slug'])
    activate(Workspace(cfg['_file'], args.root or os.getcwd(), out, asset_dirs()))
    cached = os.path.join(out, 'plate.png')
    if os.path.exists(cached):
        plate = cv2.imread(cached)
    else:
        plate = V.load_plate(cfg, cfg['visual']['width'], cfg['visual']['height'], print)
    V.prepare(cfg, plate, test=True)
    for t in args.times or ['0']:
        dest = os.path.join(cfg['_dir'], f'still_{float(t):06.2f}.jpg')
        cv2.imwrite(dest, V.frame(int(float(t) * cfg['visual']['fps'])))
        print(dest)


def _new(args):
    parent = args.dir or os.path.join(os.getcwd(), 'scenes')
    dest = os.path.join(parent, args.slug)
    if os.path.exists(dest):
        sys.exit(f'{dest} already exists')
    write_template(dest)
    print(dest)


def _doctor(args):
    bad = False
    for ok, name, detail in doctor():
        print(f'{"ok  " if ok else "MISS"} {name:18} {detail}')
        bad = bad or not ok
    if bad and not args.quiet:
        print('\nSystem tools are installed separately. `realtime setup` fetches the piano, the upscaler, and the fonts.')
    return 1 if bad else 0


def _setup(args):
    setup(sfx=args.sfx)
    _doctor(argparse.Namespace(quiet=True))


def _materials(args):
    print(report(args.root), end='')


def _kit(args):
    parent = args.dir or os.path.join(os.getcwd(), 'scenes')
    try:
        dest = write_kit(args.name, parent)
    except FileExistsError:
        sys.exit(f'{os.path.join(parent, args.name)} already exists')
    print(dest)


def main(argv=None):
    p = argparse.ArgumentParser(prog='realtime', description='One still and one scene file become a seamless hour.')
    p.add_argument('--version', action='version', version=__version__)
    sub = p.add_subparsers(dest='cmd', required=True)

    b = sub.add_parser('build', help='render a scene')
    b.add_argument('scene')
    b.add_argument('--test', action='store_true', help='3-minute cut, 12-second loop, one short piece')
    b.add_argument('--force', nargs='*', default=[], help='stage names, or "all"')
    b.add_argument('--only', nargs='*', help='run these stages and the stages they depend on')
    b.add_argument('--procs', type=int, default=6)
    b.add_argument('--out', help='output directory (default $REALTIME_MEDIA/<slug> or ./media/<slug>)')
    b.add_argument('--root', help='project root used to find sound files (default: current directory)')
    b.set_defaults(func=_build)

    c = sub.add_parser('catalog', help='list moods, distances, motions, and effects')
    c.add_argument('--plugins', action='store_true', help='import the visual engine and entry-point effects')
    c.set_defaults(func=_catalog)

    i = sub.add_parser('inspect', help='print the resolved scene and the set list it will compose')
    i.add_argument('scene')
    i.set_defaults(func=_inspect)

    r = sub.add_parser('regions', help='draw effect regions on the keyframe')
    r.add_argument('scene')
    r.add_argument('--root')
    r.add_argument('--out')
    r.set_defaults(func=_regions)

    s = sub.add_parser('still', help='write a few animated frames')
    s.add_argument('scene')
    s.add_argument('times', nargs='*')
    s.add_argument('--root')
    s.set_defaults(func=_still)

    n = sub.add_parser('new', help='scaffold scenes/<slug>/ from the template')
    n.add_argument('slug')
    n.add_argument('--dir', help='parent directory (default ./scenes)')
    n.set_defaults(func=_new)

    d = sub.add_parser('doctor', help='check ffmpeg, fluidsynth, the piano, and the upscaler')
    d.add_argument('--quiet', action='store_true')
    d.set_defaults(func=_doctor)

    u = sub.add_parser('setup', help='download the piano soundfont, EDSR weights, and thumbnail fonts')
    u.add_argument('--sfx', action='store_true', help='also download the public-domain train and bell recordings')
    u.set_defaults(func=_setup)

    m = sub.add_parser('materials', help='list kits, carols, beds, and engines')
    m.add_argument('--root', help='clone that holds materials/ (default: the current directory, then this repo)')
    m.set_defaults(func=_materials)

    k = sub.add_parser('kit', help='write a ready scene (yule-love, hearth-rain, summer-porch, cove-window, …)')
    k.add_argument('name', choices=kit_names())
    k.add_argument('--dir', help='parent directory (default ./scenes)')
    k.set_defaults(func=_kit)

    args = p.parse_args(argv)
    try:
        code = args.func(args)
    except SceneError as e:
        print(e, file=sys.stderr)
        code = 2
    except KeyboardInterrupt:
        code = 130
    raise SystemExit(int(code or 0))


if __name__ == '__main__':
    main()
