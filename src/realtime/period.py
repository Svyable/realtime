"""Loop timing. Every motion period is snapped so the last frame lands on the first."""


def snap(period, loop):
    """Return the nearest period that divides `loop` an integer number of times."""
    return loop / max(1, round(loop / period))
