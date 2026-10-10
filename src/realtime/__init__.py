"""One still and one scene file become a seamless hour of piano and room tone."""
from realtime.catalog import register_distance, register_mood, register_motion
from realtime.version import __version__

__all__ = ['__version__', 'register_distance', 'register_effect', 'register_mood', 'register_motion']


def register_effect(name, fn):
    """Register a visual-loop effect. Imports the visual engine on first use."""
    from realtime.visual.engine import register_effect as reg
    return reg(name, fn)
