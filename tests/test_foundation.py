import textwrap
from pathlib import Path

import pytest

from realtime.catalog import MOODS, WORDS, register_distance, register_mood
from realtime.graph import expand_needs, stage_key
from realtime.period import snap
from realtime.scene import SceneError, load


def test_snap_divides_the_loop():
    loop = 72
    period = snap(1.2, loop)
    assert loop % period == pytest.approx(0)
    assert abs(period - 1.2) < 0.05


def test_scene_round_trip_and_unknown_effect(tmp_path):
    path = tmp_path / 'scene.yaml'
    path.write_text(textwrap.dedent('''
        title: Lamp
        seed: 3
        music: {mood: morning}
        piano: {distance: old_radio}
        visual:
          motion: {type: ship}
          effects:
            - {type: not_a_real_effect}
    '''))
    with pytest.raises(SceneError) as caught:
        load(path)
    assert 'not_a_real_effect' in str(caught.value)


def test_unknown_top_level_key(tmp_path):
    path = tmp_path / 'scene.yaml'
    path.write_text('title: x\ncolour_grade: warm\n')
    with pytest.raises(SceneError) as caught:
        load(path)
    assert 'colour_grade' in str(caught.value)


def test_extends_overrides_distance(tmp_path):
    parent = tmp_path / 'base.yaml'
    child = tmp_path / 'child.yaml'
    parent.write_text('title: Base\npiano: {distance: hallway, pan: 0.4}\n')
    child.write_text('extends: base.yaml\npiano: {distance: closed_door}\n')
    cfg = load(child)
    assert cfg['piano']['distance'] == 'closed_door'
    assert cfg['piano']['pan'] == 0.4
    assert cfg['mix']['bed_lu_below_piano'] == 10


def test_setlist_is_deterministic_and_moods_are_extendable():
    from realtime.music.setlist import generate
    cfg = {'seed': 11, 'music': {'mood': 'daytime', 'pieces': 4, 'titles': [], 'waltz_share': None,
                                 'swing': None, 'bpm': None, 'keys': None, 'carols': []}}
    a = generate(cfg, 40)
    b = generate(cfg, 40)
    assert [p['title'] for p in a['pieces']] == [p['title'] for p in b['pieces']]
    assert len(a['pieces']) == 4
    register_mood('parade', dict(bpm=(90, 100), keys=['C'], waltz=0, swing=0.1), (['Brass'], ['March']))
    cfg['music'] = dict(cfg['music'], mood='parade', pieces=2)
    titles = [p['title'] for p in generate(cfg, 40)['pieces']]
    assert all('Brass' in t or 'March' in t for t in titles)
    MOODS.pop('parade', None)
    WORDS.pop('parade', None)


def test_stage_key_follows_the_slice_and_the_upstream_stage():
    cfg = {'seed': 1, 'duration_min': 60, 'music': {'mood': 'evening'}, 'visual': {'grain': 0.02},
           'mix': {'bed_lu_below_piano': 10}}
    compose = stage_key('compose', cfg, {})
    assert stage_key('compose', cfg, {}) == compose
    changed = dict(cfg, seed=2)
    assert stage_key('compose', changed, {}) != compose
    # A picture-only change does not touch the compose key.
    picture = dict(cfg, visual={'grain': 0.2})
    assert stage_key('compose', picture, {}) == compose
    loop_a = stage_key('loop', cfg, {'plate': 'aaa'})
    loop_b = stage_key('loop', cfg, {'plate': 'bbb'})
    assert loop_a != loop_b


def test_only_video_pulls_in_its_parents():
    need = expand_needs(['video'])
    assert {'video', 'master', 'loop', 'plate', 'mix', 'ambience', 'piano', 'compose'} <= need
    assert 'thumbnail' not in need
    assert 'preview' not in need


def test_register_distance_is_visible_to_validation(tmp_path):
    register_distance('behind_the_bar', dict(lpf=2000, hpf=80, rt=0.9, wet=0.4, dry=0.7,
                                              listen=0.1, width=0.2, wow=0.4, drive=1.2, body_db=1))
    path = tmp_path / 'scene.yaml'
    path.write_text('piano: {distance: behind_the_bar}\n')
    assert load(path)['piano']['distance'] == 'behind_the_bar'
    from realtime.catalog import DISTANCE
    DISTANCE.pop('behind_the_bar', None)


def test_cli_catalog_and_new(tmp_path, capsys):
    from realtime.cli import main
    with pytest.raises(SystemExit) as exc:
        main(['catalog'])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert 'closed_door' in out and 'rain_glass' in out and 'late_night' in out
    with pytest.raises(SystemExit) as exc:
        main(['new', 'porch', '--dir', str(tmp_path)])
    assert exc.value.code == 0
    scene = Path(tmp_path / 'porch' / 'scene.yaml')
    assert scene.exists()
    load(scene)


def _bar_beats(melody):
    return sum(float(tok.split(':')[1]) for tok in melody.split())


def test_every_carol_bar_fills_the_meter_and_arranges():
    from realtime.music.carols import TUNES, Carol, parse_melody
    from realtime.music.compose import TONES
    for cid, tune in TUNES.items():
        bpb = tune['beats_per_bar']
        for i, (mel, chords) in enumerate(tune['bars']):
            got = _bar_beats(mel)
            assert abs(got - bpb) < 1e-6, f'{cid} bar {i} sums to {got}, meter is {bpb}'
            parse_melody(mel)
            for chord in (chords if isinstance(chords, list) else [chords]):
                degree, quality = chord.split(':')
                int(degree)
                assert quality in TONES, (cid, chord)
        piece = Carol(dict(carol=cid, key='C', beats_per_bar=bpb, mel_vel=60, block=True), 1)
        piece.build()
        assert piece.events and piece.total_beats > bpb


def test_kits_catalog_and_materials(tmp_path, capsys):
    import yaml
    from realtime.cli import main
    from realtime.fetch import SFX_ASSETS
    from realtime.music.carols import TUNES
    root = Path(__file__).resolve().parents[1]
    catalog = yaml.safe_load((root / 'materials' / 'catalog.yaml').read_text())
    assert len(catalog['beds']) >= 18
    for bed in catalog['beds']:
        assert (root / bed['path']).is_file(), bed['path']
    by_id = {row['id']: row for row in catalog['fetch']}
    for rel, url, digest in SFX_ASSETS:
        fid = rel.split('/', 1)[1]
        assert by_id[fid]['sha256'] == digest
        assert by_id[fid]['url'] == url
    for name in ('yule-love', 'hearth-rain', 'summer-porch', 'cove-window', 'parish-bells', 'night-train', 'peepers', 'loons', 'window-rain'):
        parent = tmp_path / name
        parent.mkdir()
        with pytest.raises(SystemExit) as exc:
            main(['kit', name, '--dir', str(parent)])
        assert exc.value.code == 0
        cfg = load(parent / name / 'scene.yaml')
        for cid in cfg['music']['carols']:
            assert cid in TUNES
        assert (parent / name / 'prompt.md').is_file()
    yule = load(tmp_path / 'yule-love' / 'yule-love' / 'scene.yaml')
    assert yule['title'] == 'Yule Love'
    assert yule['piano']['distance'] == 'open_doorway'
    assert yule['mix']['bed_lu_below_piano'] == 11
    assert yule['music']['carols'] == ['greensleeves', 'the-water-is-wide', 'silent-night', 'auld-lang-syne']
    peepers = load(tmp_path / 'peepers' / 'peepers' / 'scene.yaml')
    assert peepers['title'] == 'The Marsh at Night'
    assert peepers['music']['mood'] == 'late_night'
    assert peepers['music']['carols'] == []
    assert peepers['mix']['bed_lu_below_piano'] == 7
    assert len(peepers['ambience']['layers']) == 1
    bed = peepers['ambience']['layers'][0]['file']
    assert bed.endswith('ontario-peepers-treefrogs-loons_pd.mp3')
    assert (root / bed).is_file()
    assert len(peepers['ambience']['accents']) == 1
    accent = peepers['ambience']['accents'][0]
    assert accent['file'].endswith('bray-lake-ontario-may10_pd.mp3')
    assert accent['per_hour'] == 6
    assert (root / accent['file']).is_file()
    loons = load(tmp_path / 'loons' / 'loons' / 'scene.yaml')
    assert loons['title'] == 'Across the Water'
    assert loons['music']['carols'] == []
    assert loons['mix']['bed_lu_below_piano'] == 7
    assert len(loons['ambience']['layers']) == 1
    loon_bed = loons['ambience']['layers'][0]['file']
    assert loon_bed.endswith('bray-lake-ontario-apr29_pd.mp3')
    assert (root / loon_bed).is_file()
    assert loons['ambience']['accents'][0]['file'].endswith('yellowstone-common-loon_pd.mp3')
    rain = load(tmp_path / 'window-rain' / 'window-rain' / 'scene.yaml')
    assert rain['title'] == 'Rain on the Glass'
    assert rain['mix']['bed_lu_below_piano'] == 10
    assert len(rain['ambience']['layers']) == 1
    rain_bed = rain['ambience']['layers'][0]['file']
    assert rain_bed.endswith('barcelona-window-rain_pd.mp3')
    assert (root / rain_bed).is_file()
    assert any(effect.get('type') == 'rain_glass' for effect in rain['visual']['effects'])
    with pytest.raises(SystemExit) as exc:
        main(['materials', '--root', str(root)])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert 'yule-love' in out and 'greensleeves' in out and 'fireplace' in out and 'offline' in out
    assert 'reservoir' in out and 'pdsounds' in out
    assert 'wildlife' in out and 'peepers' in out
    assert 'loops' in out and 'window-rain' in out


def test_pdsounds_reservoir_matches_its_manifest():
    import hashlib
    import yaml
    root = Path(__file__).resolve().parents[1]
    manifest = yaml.safe_load((root / 'materials' / 'sfx' / 'pdsounds' / 'manifest.yaml').read_text())
    files = manifest['files']
    assert len(files) >= 50
    assert manifest['license'] == 'Public domain'
    for row in files:
        assert row['license'] == 'Public domain'
        path = root / row['path']
        assert path.is_file(), row['path']
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == row['sha256'], row['path']


def test_wildlife_shelf_matches_its_manifest():
    import hashlib
    import yaml
    root = Path(__file__).resolve().parents[1]
    manifest = yaml.safe_load((root / 'materials' / 'sfx' / 'wildlife' / 'manifest.yaml').read_text())
    files = manifest['files']
    assert len(files) == 15
    allowed = {'Public Domain Mark 1.0', 'Public domain (U.S. government work)', 'Public domain'}
    roles = set()
    for row in files:
        assert row['license'] in allowed, row['path']
        lowered = row['license'].lower()
        assert 'by-sa' not in lowered and 'noncommercial' not in lowered
        path = root / row['path']
        assert path.is_file(), row['path']
        assert path.stat().st_size == row['bytes'], row['path']
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == row['sha256'], row['path']
        roles.add(row['role'])
    assert roles == {'peepers', 'frogs', 'night', 'insects', 'loons'}
    assert sum(1 for row in files if row['role'] == 'loons') == 6
    catalog = yaml.safe_load((root / 'materials' / 'catalog.yaml').read_text())
    shelf = catalog['wildlife'][0]
    assert shelf['manifest'] == 'materials/sfx/wildlife/manifest.yaml'
    assert any(row['id'] == 'peepers' and row['offline'] for row in catalog['kits'])


def test_long_rain_loops_match_their_manifest():
    import hashlib
    import yaml
    root = Path(__file__).resolve().parents[1]
    manifest = yaml.safe_load((root / 'materials' / 'sfx' / 'loops' / 'manifest.yaml').read_text())
    files = manifest['files']
    assert len(files) == 3
    for row in files:
        assert row['license'] == 'Public Domain Mark 1.0'
        assert row['duration_s'] >= 900
        path = root / row['path']
        assert path.is_file(), row['path']
        assert path.stat().st_size == row['bytes'], row['path']
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == row['sha256'], row['path']
    catalog = yaml.safe_load((root / 'materials' / 'catalog.yaml').read_text())
    assert catalog['loops'][0]['manifest'] == 'materials/sfx/loops/manifest.yaml'
