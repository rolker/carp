"""Putting the pieces together: a sensor, a lens, a port and a medium make
`Optics` (what one camera sees in that medium); a rig and a scene's settings
make a stereo summary. Still pure functions on plain dicts (the contents of
the workspace objects), no Qt.

Every choice is an argument. Nothing here assumes a medium or an error
level.
"""
from dataclasses import dataclass

import numpy as np

from . import imaging, ports, projection, stereo
from .media import N_AIR, water_refractive_index


def medium_index(medium):
    """Refractive index of a medium object: air, or water from its
    temperature, salinity and wavelength (Quan and Fry)."""
    if medium["kind"] == "air":
        return N_AIR
    return float(water_refractive_index(medium.get("wavelength_nm", 550.0),
                                        medium.get("temperature_c", 15.0),
                                        medium.get("salinity_psu", 0.0)))


@dataclass
class Optics:
    """One camera (sensor + lens + port) looking into a medium.

    Angles named `theta_a` are camera-side (in air, from the optical axis),
    `theta_w` are in the medium."""
    width_px: float
    height_px: float
    pitch_mm: float                 # effective pixel pitch (after any scaling)
    focal_mm: float
    projection: str
    n_medium: float
    port_kind: str
    fov_air_deg: tuple              # horizontal, vertical, diagonal
    fov_deg: tuple                  # the same in the medium
    px_per_rad_axis: float          # pixels per radian of medium-side angle, on axis
    _theta_w: np.ndarray            # table: medium-side angle ...
    _ppr: np.ndarray                # ... and local pixels per radian there
    warnings: tuple = ()
    _theta_a: np.ndarray = None     # table: camera-side angle for _theta_w
    _extent_mm: tuple = (0.0, 0.0)  # sensor width, height (physical, mm)

    def rays(self, x_mm, y_mm):
        """Unit direction vectors (N x 3: right, down, ahead) in the medium
        of the rays seen at sensor points (x right, y down, mm from the
        centre). Points the lens cannot see give NaN."""
        x, y = np.asarray(x_mm, float), np.asarray(y_mm, float)
        r = np.hypot(x, y)
        ta = projection.ray_angle_rad(r, self.focal_mm, self.projection)
        tw = np.interp(ta, self._theta_a, self._theta_w, right=np.nan)
        phi = np.arctan2(y, x)
        return np.column_stack([np.sin(tw) * np.cos(phi), np.sin(tw) * np.sin(phi), np.cos(tw)])

    def boundary_rays(self, per_edge=24):
        """Rays along the edge of the image, going round the sensor
        rectangle, closed (first point repeated); and the four corners."""
        hw, hh = self._extent_mm[0] / 2, self._extent_mm[1] / 2
        t = np.linspace(0, 1, per_edge, endpoint=False)
        xs = np.concatenate([-hw + 2 * hw * t, np.full(per_edge, hw), hw - 2 * hw * t, np.full(per_edge, -hw)])
        ys = np.concatenate([np.full(per_edge, -hh), -hh + 2 * hh * t, np.full(per_edge, hh), hh - 2 * hh * t])
        loop = self.rays(xs, ys)
        return np.vstack([loop, loop[:1]]), self.rays([-hw, hw, hw, -hw], [-hh, -hh, hh, hh])

    @property
    def f_px(self):
        """Focal length in pixels (in air, before the port)."""
        return self.focal_mm / self.pitch_mm

    def px_per_rad(self, theta_w_rad):
        """Local pixels per radian of medium-side angle at `theta_w_rad`
        from the axis, along a radius."""
        return np.interp(np.abs(theta_w_rad), self._theta_w, self._ppr)


def optics(sensor, lens, port, medium, image_scale=1.0, n_table=181):
    """Build `Optics` from workspace objects (dicts). `image_scale` is the
    output image width over the sensor's native width (1 = native pixels;
    2/3 = an ISP-scaled 720p from a 1080p sensor)."""
    warnings = []
    pitch_native = sensor["pixel_um"] / 1000.0
    pitch = pitch_native / image_scale
    w_mm, h_mm = sensor["width_px"] * pitch_native, sensor["height_px"] * pitch_native
    f, model = lens["focal_mm"], lens["projection"]
    d_mm = float(np.hypot(w_mm, h_mm))
    half_a = []
    for extent in (w_mm, h_mm, d_mm):
        a = float(projection.ray_angle_rad(extent / 2, f, model))
        if not np.isfinite(a):
            warnings.append("the lens cannot cover the whole sensor in this projection")
            a = np.pi / 2
        half_a.append(min(a, np.pi / 2 * 0.999) if model == "rectilinear" else a)
    in_water = port.get("kind", "none") != "none"
    n_med = medium_index(medium) if in_water or medium["kind"] == "air" else N_AIR
    if port.get("kind", "none") == "none" and medium["kind"] != "air":
        warnings.append("no port: the camera is treated as if it were in air")
    kind = port.get("kind", "none")
    n_glass = port.get("n_glass", 1.49)

    def to_medium(theta_a):
        theta_a = np.asarray(theta_a, float)
        if kind == "flat":
            return ports.flat_port_angle_rad(theta_a, n_med)
        if kind == "dome":
            return ports.dome_trace(theta_a, port.get("pupil_offset_mm", 0.0),
                                    port["radius_mm"], port["thickness_mm"],
                                    n_glass, n_med)[0]
        return theta_a

    # Table of the mapping over the lens's field, for local scales.
    theta_a = np.linspace(0, max(half_a), n_table)
    theta_w = to_medium(theta_a)
    ok = np.isfinite(theta_w)
    if not ok.all():
        warnings.append("total internal reflection at the largest angles")
    theta_a, theta_w = theta_a[ok], theta_w[ok]
    ppr_air = projection.radial_scale_mm_per_rad(theta_a, f, model) / pitch
    ppr_w = ppr_air / np.gradient(theta_w, theta_a)
    fov_w = tuple(float(np.degrees(2 * np.interp(a, theta_a, theta_w)))
                  if a <= theta_a[-1] else float("nan") for a in half_a)
    if kind == "dome" and abs(port.get("pupil_offset_mm", 0.0)) > 0.5:
        warnings.append(f"pupil {port['pupil_offset_mm']:+.1f} mm off the dome centre: "
                        "no single viewpoint, stereo geometry degrades")
    if kind == "flat" and fov_w[0] >= 2 * ports.flat_port_max_half_fov_deg(n_med) - 1e-6:
        warnings.append("flat port: the field of view is at the water-side limit")
    return Optics(
        width_px=sensor["width_px"] * image_scale, height_px=sensor["height_px"] * image_scale,
        pitch_mm=pitch, focal_mm=f, projection=model, n_medium=n_med, port_kind=kind,
        fov_air_deg=tuple(float(np.degrees(2 * a)) for a in half_a), fov_deg=fov_w,
        px_per_rad_axis=float(ppr_w[0]), _theta_w=theta_w, _ppr=ppr_w,
        warnings=tuple(warnings), _theta_a=theta_a, _extent_mm=(w_mm, h_mm))


def stereo_summary(optics_, rig, scene):
    """Numbers for a stereo pair of `optics_` at `rig['baseline_mm']`, with
    the assumptions in `scene` (disparity error, tolerance, search range,
    overlap fraction, visibility, speed) and the rig's sync error.
    Ranges in mm."""
    B = rig["baseline_mm"]
    f_px = optics_.px_per_rad_axis
    dd = scene["disparity_error_px"]
    h_fov = optics_.fov_deg[0]
    out = dict(
        baseline_mm=B, f_px=f_px,
        error_mm={z: float(stereo.depth_error_mm(z * 1000, f_px, B, dd))
                  for z in (1.0, 2.0, 3.0)},
        z_min_search_mm=float(stereo.min_range_for_disparity_mm(f_px, B, scene["max_disparity_px"])),
        z_first_overlap_mm=float(stereo.first_overlap_range_mm(B, h_fov)) if h_fov < 180 else 0.0,
        z_overlap_mm=float(stereo.range_for_overlap_mm(scene["overlap_fraction"], B, h_fov))
        if h_fov < 180 else 0.0,
        z_tolerance_mm=float(stereo.range_for_relative_error_mm(
            scene["depth_tolerance"], f_px, B, dd)),
        visibility_mm=scene["visibility_m"] * 1000.0,
    )
    out["z_near_mm"] = max(out["z_min_search_mm"], out["z_overlap_mm"])
    out["z_far_mm"] = min(out["z_tolerance_mm"], out["visibility_mm"])
    out["far_limited_by"] = ("depth tolerance" if out["z_tolerance_mm"] <= out["visibility_mm"]
                             else "visibility")
    out["near_limited_by"] = ("disparity search range"
                              if out["z_min_search_mm"] >= out["z_overlap_mm"] else "overlap")
    return out


def ground_summary(optics_, rig, scene, ranges_m=(1.0, 2.0, 3.0)):
    """Footprints and resolution on target at the given ranges (m)."""
    rows = []
    for z in ranges_m:
        zmm = z * 1000.0
        gsd = float(imaging.ground_sample_mm(zmm, optics_.px_per_rad_axis))
        rows.append(dict(
            range_m=z,
            width_mm=float(stereo.footprint_width_mm(zmm, optics_.fov_deg[0])),
            height_mm=float(stereo.footprint_width_mm(zmm, optics_.fov_deg[1])),
            gsd_mm=gsd, px_per_mm=1.0 / gsd,
            blur_px=float(imaging.motion_blur_px(
                scene["speed_m_s"] * 1000, rig["exposure_ms"] / 1000, zmm,
                optics_.px_per_rad_axis))))
    return rows
