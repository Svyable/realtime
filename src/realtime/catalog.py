"""Registries. Importing this module does not load audio or video libraries.

Moods, distance presets, motions, and effects are data other packages can extend.
Built-in names stay valid even before the visual engine is imported.
"""

MOODS = {
    'late_night': dict(bpm=(54, 64), keys=['Db', 'Eb', 'Ab', 'F', 'Bb', 'Gb'], waltz=0.25, swing=0.0),
    'evening':    dict(bpm=(58, 70), keys=['F', 'Bb', 'Eb', 'Ab', 'C'], waltz=0.25, swing=0.04),
    'daytime':    dict(bpm=(72, 92), keys=['C', 'F', 'G', 'Bb', 'D', 'Eb'], waltz=0.2, swing=0.12),
    'morning':    dict(bpm=(66, 82), keys=['C', 'G', 'F', 'D', 'Bb'], waltz=0.3, swing=0.08),
    'holiday':    dict(bpm=(60, 74), keys=['F', 'Bb', 'Eb', 'G', 'C'], waltz=0.35, swing=0.05),
}

WORDS = {
    'late_night': (['Lamplight', 'Midnight', 'Last Call', 'Quiet Hours', 'Rain', 'Moonlight', 'Slow Dance', 'Nightcap', 'Blue Hour', 'Candle', 'Streetlight', 'Velvet'],
                   ['Waltz', 'Ballad', 'Serenade', 'Reverie', 'Lullaby', 'Song', 'Nocturne', 'After Hours', 'Blues']),
    'evening':    (['Twilight', 'Supper Club', 'Porch Light', 'Dusk', 'Harbor Lights', 'Ember', 'Silver Screen', 'Lantern'],
                   ['Ballad', 'Waltz', 'Serenade', 'Song', 'Interlude', 'Reverie']),
    'daytime':    (['Sunday', 'Soda Fountain', 'Main Street', 'Sunshine', 'Bluebird', 'Jukebox', 'Lemonade', 'Picnic', 'Two Straws'],
                   ['Stroll', 'Swing', 'Shuffle', 'Song', 'Waltz', 'Afternoon', 'Rag']),
    'morning':    (['Morning', 'Coffee', 'Sunrise', 'Front Porch', 'Kitchen Window', 'Bluebird', 'Sunday Paper', 'Linen'],
                   ['Song', 'Waltz', 'Stroll', 'Hymn', 'Daydream', 'Ballad']),
    'holiday':    (['Snowfall', 'Hearth', 'Evergreen', 'Mistletoe', 'Frost', 'Window Candle', 'Sleigh Bell'],
                   ['Waltz', 'Lullaby', 'Ballad', 'Carol', 'Song', 'Reverie']),
}

# lpf / hpf in Hz. rt is the source-room decay in seconds. width 0 is mono.
DISTANCE = {
    'closed_door':     dict(lpf=1100, hpf=60, rt=1.1, wet=0.55, dry=0.62, listen=0.12, width=0.30, wow=0.7, drive=1.6, body_db=1.5),
    'hallway':         dict(lpf=1500, hpf=70, rt=1.5, wet=0.70, dry=0.50, listen=0.22, width=0.40, wow=0.7, drive=1.5, body_db=1.0, predelay=0.035),
    'open_doorway':    dict(lpf=2600, hpf=55, rt=1.0, wet=0.45, dry=0.70, listen=0.15, width=0.45, wow=0.6, drive=1.4, body_db=1.0),
    'same_room_soft':  dict(lpf=5200, hpf=45, rt=0.8, wet=0.30, dry=0.85, listen=0.10, width=0.60, wow=0.5, drive=1.3, body_db=0.5),
    'old_radio':       dict(lpf=3200, hpf=320, rt=0.5, wet=0.20, dry=0.90, listen=0.10, width=0.0, wow=1.0, drive=2.4, body_db=0.0, speaker_db=4.0),
    'radio_next_room': dict(lpf=1500, hpf=300, rt=0.9, wet=0.45, dry=0.65, listen=0.12, width=0.0, wow=1.0, drive=2.2, body_db=0.5, speaker_db=3.0),
}

BUILTIN_EFFECTS = frozenset({
    'parallax', 'rain_glass', 'flicker', 'breathe', 'particles',
    'shimmer', 'blur', 'horizon_roll', 'twinkle',
})
BUILTIN_MOTIONS = frozenset({'none', 'gentle', 'train', 'ship'})

EFFECTS = {}   # name -> prep function, filled when the visual engine imports
MOTIONS = {}   # name -> fn(motion_dict, loop_seconds) -> fn(t) -> dx, dy, rot, zoom


def register_mood(name, spec, words):
    """Add a music mood. spec needs bpm=(lo, hi), keys, waltz (0..1), swing (0..0.16). words is (adjectives, nouns)."""
    MOODS[name] = dict(spec)
    WORDS[name] = (list(words[0]), list(words[1]))
    return name


def register_distance(name, preset):
    """Add a piano-distance preset. See DISTANCE for the keys the room chain reads."""
    DISTANCE[name] = dict(preset)
    return name


def register_effect(name, fn=None):
    """Record an effect name. The visual engine also stores the prep function."""
    EFFECTS[name] = fn
    return name


def register_motion(name, fn):
    """Override or add a camera motion. fn(motion_dict, loop_seconds) returns fn(t) -> (dx, dy, rot_deg, zoom)."""
    MOTIONS[name] = fn
    return name


def known_effects():
    return set(BUILTIN_EFFECTS) | set(EFFECTS)


def known_motions():
    return set(BUILTIN_MOTIONS) | set(MOTIONS)
