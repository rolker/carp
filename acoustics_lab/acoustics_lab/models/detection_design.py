"""Detection designs: every choice about how a return is found and measured.

A detection design is the receiving-side counterpart of a ping design (see
docs/design.md, "Ping designs and detection designs"). The line between the
two: if changing a setting changes what is recorded, it belongs to the ping
design or the rig; if it can be changed afterwards on a saved recording, it
is here. So a saved recording can be analysed again with another detection
design and compared honestly.

Principle 7 of the design: no hidden processing choices. Each setting has a
name, a unit, the limits that make sense and a sentence saying what it does,
all in SETTINGS below, which is the one place they are described: the
dataclass, the workspace object's validation, the editor and the notes read
it. The defaults are the values the lab was built and tested with.

No Qt, no audio, no workspace.
"""
import dataclasses
from dataclasses import dataclass

KINDS = ("arrival", "bottom", "decoding", "level")
KIND_TEXT = {
    "arrival": "arrival detection: interrogation, reply, beacon, measurement timing",
    "bottom": "bottom detection: soundings",
    "decoding": "decoding: data pings",
    "level": "level measurement: measurement and calibration pings"}
METHODS = ("matched", "envelope")
RESOLUTIONS = ("first_null", "minus3db", "minus6db")
CHOICES = {"method": METHODS, "resolution": RESOLUTIONS}   # settings that are words


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    default: object
    unit: str
    low: float
    high: float
    text: str


SETTINGS = (
    Setting("method", "How a return is found", "matched", "", 0, 0,
            "matched: correlate with what was sent (best against noise, needs the "
            "signal); envelope: rectify and smooth over the signal's length, no "
            "template (any loud sound counts, and arrivals are as wide as the "
            "signal is long)"),
    Setting("resolution", "Resolution measure", "first_null", "", 0, 0,
            "How the spacing below which two arrivals merge is read off the "
            "signal's own matched-filter peak: first_null, the first null either "
            "side (equal echoes this far apart do not overlap at all; the "
            "careful figure); minus3db or minus6db, the peak's full width that "
            "far down (the figures usually quoted)"),
    Setting("detect_snr", "Event detection threshold", 8.0, "x noise", 1.0, 1e6,
            "A ping's event counts as heard when its strongest peak is this many "
            "times the typical (median) level of the filter output"),
    Setting("search_s", "Search window", 0.03, "s", 0.0005, 5.0,
            "How far either side of its expected time an event is looked for; "
            "events of one signal closer than twice this cannot be told apart"),
    Setting("first_fraction", "First-arrival fraction", 0.3, "of the peak", 0.01, 1.0,
            "An earlier peak this fraction of the strongest (0.3 = -10.5 dB) or "
            "more counts as the first arrival; a stronger echo can follow the "
            "direct sound"),
    Setting("listed_fraction", "Listed-arrival fraction", 0.05, "of the peak", 0.001, 1.0,
            "Peaks above this fraction of the strongest are listed after the "
            "first one (echoes); the arrival after a loopback copy is read from "
            "this list"),
    Setting("min_separation_s", "Peak separation", 0.0005, "s", 0.00001, 1.0,
            "Peaks closer than this are one arrival"),
    Setting("max_arrivals", "Most arrivals listed", 8, "", 1, 100,
            "The tallest this many peaks of an event's window are kept"),
    Setting("leak_db", "Leak warning", -25.0, "dB", -120.0, 0.0,
            "Two signals that overlap in time and leak into each other's filter "
            "less than this far down are warned about"),
    Setting("hit_snr", "Live hit threshold", 10.0, "x noise", 1.0, 1e6,
            "Streaming detection of one signal (hardware checks, the room sonar's "
            "direct sound): a peak must be this many times the typical level"),
    Setting("same_arrival", "Same-arrival window", 1.0, "signal lengths", 0.0, 20.0,
            "Peaks closer than this are one arrival: sidelobes of a loud ping, "
            "and a second hit just after the one reported, are not new arrivals"),
    Setting("final_lengths", "Wait before a hit is final", 2.0, "signal lengths", 1.0, 1000.0,
            "A hit is reported once this many signal lengths (plus the margin) "
            "of input follow it, so that no stronger peak can still come"),
    Setting("margin_samples", "Margin", 64, "samples", 0, 100000,
            "Extra input held before a hit is final, and context kept either "
            "side of a window"),
    Setting("group_samples", "Grouping tolerance", 5.0, "samples", 0.1, 100000.0,
            "Offsets this close to the median are one group; the others are set "
            "aside and counted as echoes or stray hits"),
    Setting("upsample", "Interpolation", 16, "x", 1, 256,
            "A peak is located to 1/this of a sample by interpolating the "
            "band-limited output and fitting a parabola"),
    Setting("refine_half", "Interpolation window", 48, "samples", 4, 4096,
            "Samples either side of a peak that are interpolated"),
    Setting("settle_s", "Settle time", 2.0, "s", 0.0, 120.0,
            "Input to let go by after a stream opens (inputs often start with a "
            "thump or a DC offset)"),
    Setting("check_s", "Input check length", 1.0, "s", 0.05, 60.0,
            "How much of the settled, quiet input the level check reads"),
    Setting("clip_fraction", "Clipping limit", 0.001, "of samples", 0.0, 1.0,
            "More of the quiet input than this at full scale: the input clips"),
    Setting("dc_fraction", "DC offset limit", 0.02, "of full scale", 0.0, 1.0,
            "A mean this far from zero: too much capture gain, or a mic input "
            "still settling"),
    Setting("noise_dbfs", "Quiet-input noise limit", -30.0, "dBFS rms", -140.0, 0.0,
            "Quiet input louder than this: too much capture gain, or a loud room"),
)
SETTING = {s.key: s for s in SETTINGS}


@dataclass(frozen=True)
class DetectionDesign:
    """How returns are found and measured. Plain numbers and words; SETTINGS
    says what each one is. The workspace stores one as
    detection_designs/<id>.json."""
    name: str = "Default arrival detection"
    kind: str = "arrival"
    description: str = ""
    method: str = "matched"
    resolution: str = "first_null"
    detect_snr: float = 8.0
    search_s: float = 0.03
    first_fraction: float = 0.3
    listed_fraction: float = 0.05
    min_separation_s: float = 0.0005
    max_arrivals: int = 8
    leak_db: float = -25.0
    hit_snr: float = 10.0
    same_arrival: float = 1.0
    final_lengths: float = 2.0
    margin_samples: int = 64
    group_samples: float = 5.0
    upsample: int = 16
    refine_half: int = 48
    settle_s: float = 2.0
    check_s: float = 1.0
    clip_fraction: float = 0.001
    dc_fraction: float = 0.02
    noise_dbfs: float = -30.0

    def to_dict(self):
        return dataclasses.asdict(self)

    def changed(self, **changes):
        """A copy with some settings changed (and checked)."""
        return from_dict(dict(self.to_dict(), **changes))

    def differences(self, other=None):
        """{key: (this, other's)} for the settings that differ from another
        design (default: the built-in one)."""
        other = other or DEFAULT
        return {s.key: (getattr(self, s.key), getattr(other, s.key))
                for s in SETTINGS if getattr(self, s.key) != getattr(other, s.key)}

    def summary(self):
        """One line: the method and what differs from the defaults."""
        diff = self.differences()
        for key in CHOICES:
            diff.pop(key, None)
        text = f"{self.name} ({self.method}"
        if diff:
            text += "; " + ", ".join(f"{k} {getattr(self, k):g}" for k in diff)
        if self.resolution != DEFAULT_RESOLUTION:
            text += f"; resolution {self.resolution}"
        return text + ")"


def check_values(data):
    """Raise ValueError, with a message a person can act on, if `data` (a
    dict of settings) holds a value outside what makes sense."""
    if data.get("kind", "arrival") not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    for key, allowed in CHOICES.items():
        if key in data and data[key] not in allowed:
            raise ValueError(f"{key} must be one of {', '.join(allowed)}")
    for s in SETTINGS:
        if s.key in CHOICES or s.key not in data:
            continue
        value = data[s.key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{s.label} needs a number, not {value!r}")
        if not s.low <= value <= s.high:
            raise ValueError(f"{s.label} must be between {s.low:g} and {s.high:g}"
                             + (f" {s.unit}" if s.unit else ""))


def from_dict(data):
    """A DetectionDesign from a stored dict. Missing settings take their
    defaults; unknown keys are ignored. Raises ValueError for bad values."""
    check_values(data)
    names = {f.name for f in dataclasses.fields(DetectionDesign)}
    kwargs = {k: v for k, v in data.items() if k in names}
    for s in SETTINGS:
        if s.key not in kwargs or s.key in CHOICES:
            continue
        kwargs[s.key] = int(round(kwargs[s.key])) if isinstance(s.default, int) \
            else float(kwargs[s.key])
    return DetectionDesign(**kwargs)


DEFAULT = DetectionDesign()
DEFAULT_RESOLUTION = DEFAULT.resolution


def new_default(name="Default arrival detection"):
    """The data of the design a new workspace starts with."""
    return dict(DEFAULT.to_dict(), name=name, description=(
        "The settings the lab was built with: matched filter, first arrival "
        "within -10.5 dB of the strongest peak."))
