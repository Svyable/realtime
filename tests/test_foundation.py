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
