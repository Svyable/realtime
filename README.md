# realtime

One still image and one scene file become a seamless hour: original piano heard from another room, a soft bed of room tone, and a picture that loops without showing the join.

This is the engine used by [Vintage Era Radio](https://github.com/Svyable/vintage-era-radio), packaged so any project can add a scene. The channel repo keeps titles, upload copy, and its own recordings. This repo is the builder.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
realtime setup          # piano soundfont, upscaler, thumbnail fonts
realtime doctor
realtime new porch
# drop a 16:9 keyframe.jpg into scenes/porch/, then:
realtime regions scenes/porch/scene.yaml
realtime build scenes/porch/scene.yaml --test
realtime build scenes/porch/scene.yaml
```

You also need `ffmpeg`, `fluidsynth`, and `7z` (to unpack the piano once) on your PATH. Renders go to `./media/<slug>/` (or `$REALTIME_MEDIA`). They are not part of the package.

## A scene file

`scene.yaml` is the whole video.

| Section | What it decides |
|---|---|
| `music.mood` | Tempo, keys, how many waltzes, swing. `late_night`, `evening`, `daytime`, `morning`, `holiday`, or one you register. |
| `piano.distance` | How the dry piano is heard: `closed_door` (1.1 kHz), `hallway`, `open_doorway`, `same_room_soft`, `old_radio`, `radio_next_room`. |
| `mix.bed_lu_below_piano` | How far under the piano the room sits. **10** is the default (the room is felt). The first night-train mix was about 2–3.5, which is why the rails got tiring. |
| `visual.motion` | `none`, `gentle`, `train` (sway plus a soft bump on the rail joints), `ship` (a slow roll). |
| `visual.effects` | Small motions on the still: window parallax, rain on glass, lamp flicker, snow, water shimmer, a horizon that rolls behind a still deck. |

`realtime catalog` prints every mood, distance, motion, and effect. `realtime inspect scene.yaml` prints the set list that seed will compose.

## Materials

The git repo carries a license-checked nature library (CC0 or public domain, 18 beds, credits in `materials/sfx/nature/CREDITS.md`), a public-domain environmental reservoir in `materials/sfx/pdsounds/`, a northeastern night-wildlife shelf in `materials/sfx/wildlife/`, and eight scene kits. `realtime materials` lists the kits, the carol tunes, the beds, the reservoir, the wildlife, and the engines.

```bash
realtime kit yule-love
# drop keyframe.jpg into scenes/yule-love/ using the prompt.md written beside it
realtime build scenes/yule-love/scene.yaml --root . --test
```

Yule Love is a Christmas parlor: hearth, one lamp, snow at the window, piano heard through an open doorway, the room 11 LU under the piano. The carols are Greensleeves (the same public-domain tune as What Child Is This), The Water Is Wide, Silent Night, and Auld Lang Syne, with original pieces titled between them. Nothing in that hour is a modern arrangement.

Other kits: `hearth-rain`, `summer-porch`, `cove-window`, `parish-bells`, `peepers`, `loons`. `night-train` needs `realtime setup --sfx` for the carriage-wheel recording. The PDSounds reservoir already includes rain, storms, water, birds, streets, a train ride, and church bells.

`peepers` is the April sleep kit: a dark window and one twenty-minute Ontario night (spring peepers, tree frogs, and loons) sitting 7 LU under the piano, with loons from a second Ontario lake about six times an hour. `loons` is the lake itself: twelve minutes of Bray Lake loons as the bed, and a Yellowstone tremolo four times an hour. The same birds as a New Hampshire lake, recorded in Ontario, Minnesota, and Yellowstone. Summer crickets stay on `summer-porch`. Those months do not stack. Credits are in `materials/sfx/wildlife/CREDITS.md`.

The reservoir is the environmental slice of [PDSounds](https://commons.wikimedia.org/wiki/Category:PDsounds.org) on Wikimedia Commons: 592 public-domain ogg files live there, and the weather, water, nature, town, transit, and interior recordings are copied into this repo with a sha256 manifest. Speech, music, and close-miked foley were left on Commons.

Pass `--root` as this clone. Kit scenes point at `materials/sfx/nature/…`, and those files are in the repository, not inside the installed wheel.

Every motion period is snapped so it divides the loop. Frame 0 and the last frame are the same picture, so repeating the loop for an hour has no seam.

## Stages

`compose → piano → ambience → mix → master` runs beside `plate → loop → thumbnail`. They meet at `video`, then `preview`, `qc`, and an optional `release` encode under 2 GiB.

A stage is skipped when its scene inputs, the hash of the code that implements it, and the keys of the stages it depends on are unchanged. `--force compose` rebuilds that stage. `--only loop` also runs `plate`, because a loop cannot exist without it. `--test` is a 3-minute cut with a 12-second loop and one short piece.

## Extending it

Registries are ordinary dicts. A plugin does not edit the core.

```python
from realtime import register_mood, register_distance, register_motion, register_effect

register_mood(
    'parade',
    dict(bpm=(88, 104), keys=['Bb', 'Eb'], waltz=0.1, swing=0.08),
    (['Brass', 'Banner'], ['March', 'Promenade']),
)

register_distance('behind_the_bar', dict(
    lpf=1800, hpf=70, rt=0.7, wet=0.35, dry=0.8,
    listen=0.1, width=0.25, wow=0.4, drive=1.3, body_db=1.0,
))
```

An effect is a function `(effect_dict, ctx) -> piece` that `frame()` already knows how to paint. `ctx` carries `img`, `W`, `H`, `L` (loop seconds), `test`, and `i`. Ship it as an entry point:

```toml
[project.entry-points."realtime.effects"]
my_glow = "my_package.effects:install"
```

`install` calls `register_effect("glow", prep_glow)`. `realtime build` loads those entry points before it renders.

A layer's `file` is looked up in the scene directory, the project you pass with `--root`, then `$REALTIME_ASSETS` and `~/.cache/realtime` (and an existing Vintage Era Radio cache, if you have one). Use CC0 or public-domain recordings if the video will be published. The nature beds in this repo already are. Do not add CC-BY, ShareAlike, NonCommercial, BBC RemArc, or a modern chart of a public-domain tune. The refused list is in `materials/catalog.yaml`.

## What `realtime setup` downloads

| Asset | Licence |
|---|---|
| FreePats Upright Piano KW | CC0 |
| EDSR ×2 super-resolution weights | Apache-2.0 (a tool; nothing from it is in the picture except sharper pixels) |
| Limelight, DM Serif Display, Poiret One | SIL OFL 1.1 |

The composer writes new chord progressions, motifs, and voicings. It does not quote existing songs. Public-domain carol tunes in `realtime.music.carols` can be named in `music.carols` and are re-harmonised by the same engine. Those tunes are public domain. A modern arrangement of them is not, and this package does not include any.

## Layout

```
src/realtime/
  catalog.py     moods, distances, motions, effects
  scene.py       scene.yaml defaults, extends, validation
  graph.py       stage order and cache keys
  runner.py      build, with audio and picture in parallel
  kits/          ready scenes, including yule-love
  music/         set list, composer, carols, progression templates
  audio/         room chain, beds, mix, master
  visual/        the loop
materials/       CC0 and public-domain beds, and the agent index
```

## Tests

```bash
pytest
```

## License

MIT. Copyright 2026 Svyable.
