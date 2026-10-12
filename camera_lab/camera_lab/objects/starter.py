"""The objects a new workspace starts with: CARP's actual camera set-up and
a few alternatives to compare it with.

Verified (2026-10-12, manufacturer pages, see docs/design.md "Camera
facts"): Arducam B0444 is a Sony IMX462 module, 2.9 um pixels, 1920 x 1080,
RAW10 up to 60 fps, M12 lens with f 2.1 mm +-5 %, F2.1 +-10 %, listed field
of view 141.4 H x 81.7 V x 161 D degrees. Unverified: the projection (not
published; equidistant reproduces all three listed angles within 2.3 deg
once f is 2.256 mm, 7 % above the nominal 2.1, so the nominal f and the
listed angles disagree), the lens distortion, the dome's pupil position.
"""
from . import schema

IMX462_SOURCE = ("Arducam B0444 listing via switch-science.com/products/9985 and "
                 "docs.arducam.com Pivariety IMX462 page: IMX462, 2.9 um pixels, "
                 "1920x1080, RAW10, 60 fps. Sony IMX462: framos.com. Unverified: "
                 "the 120 fps sensor figure (not offered by the Arducam module).")
LENS_SOURCE = ("Arducam B0444 listing: f 2.1 mm +-5 %, F2.1 +-10 %, FOV 141.4 H x "
               "81.7 V x 161 D deg. Projection not published: equidistant assumed "
               "and f fitted (2.256 mm) so the model reproduces the listed 141.4 deg; "
               "it then gives V 79.4 and D 162.0 (listed 81.7, 161). Unverified.")

OBJECTS = {
    "sensors": {
        "imx462": dict(name="Sony IMX462 (Arducam B0444)", width_px=1920, height_px=1080,
                       pixel_um=2.9, bits=10, max_fps=60.0, shutter="rolling",
                       source=IMX462_SOURCE + " Rolling shutter assumed from the sensor family: unverified."),
    },
    "lenses": {
        "b0444_141": dict(name="Arducam B0444 141 deg M12", focal_mm=2.256,
                          projection="equidistant", f_number=2.1,
                          listed_fov_h_deg=141.4, source=LENS_SOURCE),
        "hypo_4mm": dict(name="Hypothetical 4 mm rectilinear M12", focal_mm=4.0,
                         projection="rectilinear", f_number=2.0, listed_fov_h_deg=0,
                         source="Hypothetical, for comparison only: not a product."),
    },
    "ports": {
        "dome_2in": dict(name="2 in acrylic dome, pupil at centre", kind="dome",
                         thickness_mm=2.0, radius_mm=26.3, n_glass=1.49, pupil_offset_mm=0.0,
                         source="docs/sled.md (R 26.3 measured), docs/bom.md (2.0 mm wall). "
                                "Acrylic index 1.49 is a textbook value, unmeasured. "
                                "Pupil position is tuned wet (sled.md), so 0 is the design intent."),
        "dome_2in_off3": dict(name="2 in dome, pupil 3 mm behind centre", kind="dome",
                              thickness_mm=2.0, radius_mm=26.3, n_glass=1.49, pupil_offset_mm=3.0,
                              source="What if the pupil sits 3 mm off (sled.md's fore-aft tolerance)."),
        "flat_3mm": dict(name="Flat acrylic window 3 mm, pupil 10 mm behind", kind="flat",
                         thickness_mm=3.0, radius_mm=26.3, n_glass=1.49, pupil_offset_mm=10.0,
                         source="Hypothetical flat port for comparison (ADR-003 rejected it)."),
        "none": dict(name="No port (in air)", kind="none", thickness_mm=1.0, radius_mm=26.3,
                     n_glass=1.49, pupil_offset_mm=0.0, source=""),
    },
    "media": {
        "air": dict(name="Air", kind="air", temperature_c=20.0, salinity_psu=0.0, wavelength_nm=550.0),
        "fresh": dict(name="Fresh water 15 C", kind="water", temperature_c=15.0, salinity_psu=0.0, wavelength_nm=550.0),
        "salt": dict(name="Salt water 15 C", kind="water", temperature_c=15.0, salinity_psu=35.0, wavelength_nm=550.0),
    },
}

_RIG = dict(sensor="imx462", lens="b0444_141", port="dome_2in", cameras=2, baseline_mm=95.0,
            toe_in_deg=0.0, image_scale=1.0, fps=10.0, exposure_ms=10.0, sync_us=23.0,
            encoded_bpp=0.016)
# encoded_bpp: ADR-015 caps each camera at 3 Mbit/s; 3e6 / (1920*1080*10) = 0.145.
# The measured 1080p10 bench bitrate was ~330 kbit/s = 0.016 bit per pixel.
OBJECTS["rigs"] = {
    "carp_95": dict(_RIG, name="CARP 95 mm (printed bracket)"),
    "carp_74": dict(_RIG, name="CARP 74 mm (minimum allowed)", baseline_mm=74.0),
    "narrow_4mm": dict(_RIG, name="Compare: 4 mm rectilinear lens, 95 mm",
                       lens="hypo_4mm"),
    "wide_150": dict(_RIG, name="Compare: 150 mm baseline", baseline_mm=150.0),
    "flat_port": dict(_RIG, name="Compare: flat port, 95 mm", port="flat_3mm"),
}
OBJECTS["scenes"] = {
    "carp_site": dict(name="Shallow turbid site", medium="fresh", visibility_m=3.0,
                      speed_m_s=0.5, target_small_mm=300.0, target_large_mm=1000.0,
                      target_range_m=2.0, disparity_error_px=0.25, depth_tolerance_pct=5.0,
                      max_disparity_px=256.0, overlap_pct=90.0, pixels_needed=24.0,
                      blur_limit_px=1.0),
}


def populate(workspace):
    """Create the starter objects (IDs are the keys above), in an order that
    satisfies references; one undo step."""
    with workspace.macro("create starter objects"):
        for kind in schema.KINDS:
            for key, data in OBJECTS[kind].items():
                data = dict(data)
                workspace.create(kind, data.pop("name"), data, object_id=key)
