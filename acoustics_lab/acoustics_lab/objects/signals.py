"""Turning a signal object into samples, and describing what it is worth."""
from ..models import detection, signals as sig
from .schema import WorkspaceError


def band(get, signal_id):
    """(f0, f1, duration) in Hz, Hz, s for a signal, following derived ones
    to their source. A reversed chirp swaps its ends."""
    data = get(signal_id)
    if data is None:
        raise WorkspaceError(f"no signal with ID '{signal_id}'")
    if data["type"] == "chirp":
        return data["f0"], data["f1"], data["duration"]
    f0, f1, duration = band(get, data["source"])
    if data["op"] == "time_reverse":
        f0, f1 = f1, f0
    return f0, f1, duration


def samples(get, signal_id, rate):
    """The signal as float64 samples at `rate` Hz, amplitude included.

    get(id) returns a signal's dict, or None. Raises ValueError for a band
    the rate cannot carry, and WorkspaceError for a missing source.
    """
    data = get(signal_id)
    if data is None:
        raise WorkspaceError(f"no signal with ID '{signal_id}'")
    if data["type"] == "chirp":
        return data["amplitude"] * sig.make_chirp(
            rate, data["f0"], data["f1"], data["duration"], data.get("taper", 1.0))
    source = samples(get, data["source"], rate)
    if data["op"] == "time_reverse":
        return sig.time_reverse(source)
    if data["op"] == "invert":
        return sig.invert(source)
    raise WorkspaceError(f"unknown operation {data['op']!r}")


def level(get, signal_id):
    """Peak level 0..1 of a signal (derived ones follow their source)."""
    data = get(signal_id)
    while data["type"] == "derived":
        data = get(data["source"])
    return data["amplitude"]


def worth(get, signal_id, rate=48000.0, measure="first_null"):
    """What a signal is worth, for the read-only columns: a dict with
    duration_ms, bandwidth_hz, gain_db (processing gain against white noise)
    and resolution_ms (arrivals closer than this merge, read off the signal's
    own matched-filter peak by `measure`, a detection design's resolution
    setting)."""
    f0, f1, duration = band(get, signal_id)
    width = sig.bandwidth(f0, f1)
    resolution = None
    if width > 0:
        try:
            resolution = detection.resolution(
                f0, f1, template=samples(get, signal_id, rate), rate=rate,
                measure=measure) * 1e3
        except ValueError:                     # a band the rate cannot carry
            resolution = None
    return dict(
        duration_ms=duration * 1e3, bandwidth_hz=width,
        gain_db=sig.processing_gain_db(f0, f1, duration),
        resolution_ms=resolution, resolution_measure=measure)
