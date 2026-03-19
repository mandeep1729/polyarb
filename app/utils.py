"""Shared utility functions."""


def first_float(raw: dict, *keys: str) -> float | None:
    """Return the first non-None float value from the given keys in a dict.

    Handles string, int, and float values. Returns None if no key
    produces a valid float.
    """
    for key in keys:
        val = raw.get(key)
        if val is None:
            continue
        try:
            return float(val)
        except (ValueError, TypeError):
            continue
    return None
