"""What the workspace objects contain, and how to check them.

Each kind lists its fields once; the editor forms, the validation and the
cross-references are all made from this table. A field has:

    key, label, kind ('float', 'int', 'choice', 'ref', 'text'), unit, help
    lo / hi / decimals     for numbers
    choices                for 'choice'
    ref                    for 'ref': the kind of object it points to

`help` is shown as a tooltip and in the notes: every number says what it is.
"""
import re

from ..models.projection import MODELS

KINDS = ("sensors", "lenses", "ports", "media", "rigs", "scenes")
SINGULAR = dict(sensors="sensor", lenses="lens", ports="port", media="medium",
                rigs="rig", scenes="scene")
TITLES = dict(sensors="Sensors", lenses="Lenses", ports="Ports", media="Media",
              rigs="Rigs", scenes="Scenes")


class WorkspaceError(ValueError):
    pass


class InUseError(WorkspaceError):
    def __init__(self, what, users):
        self.users = users
        super().__init__(f"{what} is used by " + ", ".join(f"{k}/{i}" for k, i in users))


def _f(key, label, unit="", help="", lo=-1e9, hi=1e9, decimals=3):
    return dict(key=key, label=label, kind="float", unit=unit, help=help,
                lo=lo, hi=hi, decimals=decimals)


def _i(key, label, unit="", help="", lo=0, hi=10 ** 9):
    return dict(key=key, label=label, kind="int", unit=unit, help=help, lo=lo, hi=hi)


def _c(key, label, choices, help=""):
    return dict(key=key, label=label, kind="choice", choices=list(choices), help=help, unit="")


def _r(key, label, ref, help=""):
    return dict(key=key, label=label, kind="ref", ref=ref, help=help, unit="")


def _t(key, label, help=""):
    return dict(key=key, label=label, kind="text", help=help, unit="")


FIELDS = {
    "sensors": [
        _i("width_px", "Width", "px", "Active pixels across, in the full-resolution mode.", 1),
        _i("height_px", "Height", "px", "Active pixels down.", 1),
        _f("pixel_um", "Pixel pitch", "um", "Distance between pixel centres, from the datasheet.", 0.1, 100, 2),
        _i("bits", "Raw bits per pixel", "bit", "Bit depth of the raw output (sets the uncompressed data rate).", 1, 32),
        _f("max_fps", "Largest frame rate in this mode", "fps", "What the sensor mode can deliver; the Pi may manage less.", 0.1, 1000, 1),
        _c("shutter", "Shutter", ["rolling", "global"], "Rolling shutters read rows one after another: fast motion shears."),
        _t("source", "Source", "Where the numbers come from, and what is unverified."),
    ],
    "lenses": [
        _f("focal_mm", "Focal length used", "mm", "The effective focal length the model uses. Where only a field of view is published this is the value that reproduces it.", 0.1, 500, 3),
        _c("projection", "Projection", MODELS, "How angle becomes distance from the image centre."),
        _f("f_number", "F-number", "", "Aperture; sets how much light reaches the sensor.", 0.5, 32, 2),
        _f("listed_fov_h_deg", "Listed horizontal field of view", "deg", "Manufacturer's figure, for comparison (0 = none).", 0, 360, 1),
        _t("source", "Source", "Where the numbers come from, and what is unverified."),
    ],
    "ports": [
        _c("kind", "Kind", ["none", "flat", "dome"], "none: the camera looks straight into the medium (only meaningful in air)."),
        _f("thickness_mm", "Wall thickness", "mm", "Thickness of the window or dome wall.", 0.1, 50, 2),
        _f("radius_mm", "Dome outer radius", "mm", "Outer radius of the dome (dome only).", 1, 500, 2),
        _f("n_glass", "Port material index", "", "Refractive index of the window material (acrylic is about 1.49).", 1.0, 3.0, 3),
        _f("pupil_offset_mm", "Pupil offset / gap", "mm", "Dome: distance of the lens's entrance pupil behind the dome centre (0 = centred). Flat: distance of the pupil behind the window.", -100, 100, 2),
        _t("source", "Source", "Where the numbers come from, and what is unverified."),
    ],
    "media": [
        _c("kind", "Kind", ["air", "water"], ""),
        _f("temperature_c", "Temperature", "C", "Sets the refractive index of water slightly.", -2, 40, 1),
        _f("salinity_psu", "Salinity", "PSU", "0 fresh, about 35 open ocean.", 0, 45, 1),
        _f("wavelength_nm", "Wavelength", "nm", "Refractive index depends on colour; green is the default.", 380, 780, 0),
    ],
    "rigs": [
        _r("sensor", "Sensor", "sensors"),
        _r("lens", "Lens", "lenses"),
        _r("port", "Port", "ports"),
        _i("cameras", "Cameras", "", "1 = a single camera, 2 = a stereo pair.", 1, 2),
        _f("baseline_mm", "Baseline", "mm", "Distance between the two entrance pupils.", 0, 2000, 1),
        _f("toe_in_deg", "Toe-in (each camera)", "deg", "Each camera turned towards the centre line by this angle; 0 = parallel. Affects the coverage views only; the stereo numbers assume rectified images.", -30, 30, 1),
        _f("image_scale", "Image scale", "", "Output image width over the sensor's native width (1 = native, 0.667 = 720p from 1080p).", 0.05, 1, 3),
        _f("fps", "Frame rate", "fps", "Frames per second actually recorded.", 0.1, 1000, 1),
        _f("exposure_ms", "Exposure time", "ms", "Shutter time per frame.", 0.001, 1000, 3),
        _f("sync_us", "Stereo sync error", "us", "Time between the two cameras' exposures.", 0, 1e6, 1),
        _f("encoded_bpp", "Encoded bits per pixel", "bit", "Size per pixel after video compression (depends on encoder and scene).", 0.001, 24, 3),
    ],
    "scenes": [
        _r("medium", "Medium", "media", "What the cameras look into."),
        _f("visibility_m", "Visibility", "m", "How far a diver would see a target; the water 'wall' for everything here.", 0.1, 100, 1),
        _f("speed_m_s", "Vehicle speed", "m/s", "Speed across the view (for motion blur and sync error).", 0, 20, 2),
        _f("target_small_mm", "Small target", "mm", "Size of a small object to find (marker on the views).", 1, 20000, 0),
        _f("target_large_mm", "Large target", "mm", "Size of a large object.", 1, 20000, 0),
        _f("target_range_m", "Range for the target markers", "m", "Where the target markers are drawn.", 0.1, 100, 1),
        _f("disparity_error_px", "Disparity accuracy", "px", "Typical error of the stereo matcher on a good texture; 0.25 is a common sub-pixel figure, not a measurement of this system.", 0.01, 10, 2),
        _f("depth_tolerance_pct", "Acceptable depth error", "% of range", "Depth error that still counts as useful.", 0.1, 100, 1),
        _f("max_disparity_px", "Matcher search range", "px", "Largest disparity the matcher looks for; sets the nearest range it can handle.", 8, 4096, 0),
        _f("overlap_pct", "Overlap that counts as full", "%", "Share of one view the other must also see.", 50, 99.9, 1),
        _f("pixels_needed", "Pixels across a target to recognise it", "px", "How many pixels a target needs for the job; 24 is a rough rule, set what your detector needs.", 2, 1000, 0),
        _f("blur_limit_px", "Acceptable motion blur", "px", "Blur length that still looks sharp.", 0.1, 50, 1),
    ],
}

# Fields stored under a different unit than the model wants are converted in
# one place: scene percentages become fractions in `scene_for_models`.


def field(kind, key):
    for f in FIELDS[kind]:
        if f["key"] == key:
            return f
    raise KeyError(key)


def references(kind, data):
    """(kind, id) pairs this object refers to."""
    return {(f["ref"], data[f["key"]]) for f in FIELDS[kind]
            if f["kind"] == "ref" and data.get(f["key"])}


def check(kind, data, exists):
    """Raise WorkspaceError if the data is not a valid object of this kind.
    `exists(kind, id)` says whether a referenced object exists."""
    if not str(data.get("name", "")).strip():
        raise WorkspaceError("an object needs a name")
    for f in FIELDS[kind]:
        key = f["key"]
        if key not in data:
            raise WorkspaceError(f"{SINGULAR[kind]} '{data['name']}' lacks '{key}'")
        v = data[key]
        if f["kind"] in ("float", "int"):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise WorkspaceError(f"{f['label']} must be a number")
            if not f["lo"] <= v <= f["hi"]:
                raise WorkspaceError(f"{f['label']} must be between {f['lo']} and {f['hi']}")
        elif f["kind"] == "choice" and v not in f["choices"]:
            raise WorkspaceError(f"{f['label']} must be one of {f['choices']}")
        elif f["kind"] == "ref" and not exists(f["ref"], v):
            raise WorkspaceError(f"{f['label']}: no {SINGULAR[f['ref']]} '{v}'")


def unique_id(name, existing, prefix):
    """A short readable ID from a name, not already in `existing`."""
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:32] or prefix
    candidate, n = base, 2
    while candidate in existing:
        candidate, n = f"{base}_{n}", n + 1
    return candidate


def defaults(kind):
    """A complete data dict for a new object of this kind (references left
    empty, to be filled by the caller)."""
    out = {}
    for f in FIELDS[kind]:
        if f["kind"] in ("float", "int"):
            out[f["key"]] = max(f["lo"], min(f["hi"], 1 if f["kind"] == "int" else 1.0))
        elif f["kind"] == "choice":
            out[f["key"]] = f["choices"][0]
        else:
            out[f["key"]] = ""
    return out
