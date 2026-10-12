"""Ports: the window between the camera (in air) and the water.

Flat port
---------
A ray leaving the camera at angle theta_a from the axis crosses a flat,
parallel-sided window and enters water at theta_w with

    n_air sin(theta_a) = n_water sin(theta_w)        (Snell; the window's own
                                                       index cancels)

so the field of view narrows: tan(half_w) is about tan(half_a) / n for small
angles, and the water-side half angle can never exceed asin(1 / n_water)
(48.6 degrees in fresh water, a 97 degree full field of view, however wide
the lens). Rays at different angles do not seem to come from one point (the
axial caustic, `flat_port_caustic_mm`), so the pinhole model only holds
near the axis, and different wavelengths bend by different amounts
(`flat_port_chromatic_deg`). Source: Treibitz, Schechner, Kunz and Singh
(2012), "Flat refractive geometry", IEEE PAMI 34(1).

Dome port
---------
A concentric spherical shell with the camera's entrance pupil at its centre:
every ray hits both surfaces along the normal and goes straight through, so
the field of view is unchanged by the port. The shell acts as a diverging
lens for the scene: objects at any range appear as a virtual image closer
than infinity, about 3 dome radii out for a distant object in water
(`dome_virtual_image`), so the lens must focus close. If the pupil is off
centre by `offset`, rays are refracted away from normal incidence and the
single-viewpoint model breaks down (`dome_trace`). Source: Kunz and Singh
(2008), "Hemispherical refraction and camera calibration in underwater
vision", OCEANS 2008; Menna et al. (2016) for practical offsets.
"""
import numpy as np

from .media import N_AIR


def flat_port_angle_rad(theta_air_rad, n_water, n_air=N_AIR):
    """Water-side ray angle (rad) for a camera-side angle (rad)."""
    return np.arcsin(np.clip(n_air * np.sin(theta_air_rad) / n_water, -1, 1))


def flat_port_max_half_fov_deg(n_water, n_air=N_AIR):
    """Largest half field of view (deg) any lens can have in water behind a
    flat port: asin(n_air / n_water)."""
    return float(np.degrees(np.arcsin(n_air / n_water)))


def flat_port_caustic_mm(theta_air_rad, gap_mm, n_water, n_air=N_AIR):
    """Where, behind the window, the water-side ray at this angle appears to
    cross the axis (mm behind the window), for a pupil `gap_mm` behind it.
    Small angles give gap * n_water / n_air; large angles differ, and the
    spread is the lack of a single viewpoint."""
    ta = np.asarray(theta_air_rad, float)
    tw = flat_port_angle_rad(ta, n_water, n_air)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = gap_mm * np.tan(ta) / np.tan(tw)
    return np.where(np.abs(ta) < 1e-9, gap_mm * n_water / n_air, out)


def flat_port_chromatic_deg(theta_air_rad, n_blue, n_red, n_air=N_AIR):
    """Difference (deg) in water-side angle between blue and red light for the
    same camera-side angle: lateral colour fringing of a flat port."""
    return float(np.degrees(flat_port_angle_rad(theta_air_rad, n_blue, n_air)
                            - flat_port_angle_rad(theta_air_rad, n_red, n_air)))


def _refract(u, normal, n1, n2):
    """Vector Snell's law in 2D. `normal` is any unit normal; returns the
    refracted unit direction, or None for total internal reflection."""
    n = normal if np.dot(u, normal) < 0 else -normal     # faces the incoming ray
    eta = n1 / n2
    c1 = -np.dot(u, n)
    k = 1 - eta ** 2 * (1 - c1 ** 2)
    if k < 0:
        return None
    return eta * u + (eta * c1 - np.sqrt(k)) * n


def _hit_sphere(p, u, radius):
    """Far intersection of a ray starting inside a circle (centre origin)."""
    b = np.dot(p, u)
    c = np.dot(p, p) - radius ** 2
    return p + (-b + np.sqrt(b * b - c)) * u


def dome_trace(theta_air_rad, offset_mm, r_out_mm, thickness_mm,
               n_glass, n_water, n_air=N_AIR):
    """Trace rays through a dome in 2D (the plane containing the axis).

    The dome's centre of curvature is the origin and +z points into the
    water. The camera's entrance pupil is on the axis at z = -offset_mm
    (positive: behind the centre, farther from the water). The ray leaves it
    at `theta_air_rad` from the axis (scalar or array).

    Returns (theta_water_rad, axis_crossing_mm): the ray's angle from the
    axis in the water, and the z where the water-side ray, extended
    backwards, crosses the axis (with zero offset it is 0 for every ray, the
    single viewpoint). Both are NaN for total internal reflection."""
    t = np.asarray(theta_air_rad, float)
    out = np.array([_dome_one(float(a), offset_mm, r_out_mm, thickness_mm,
                              n_glass, n_water, n_air) for a in np.atleast_1d(t)])
    if t.ndim == 0:
        return float(out[0, 0]), float(out[0, 1])
    return out[:, 0], out[:, 1]


def _dome_one(theta, offset, r_out, thickness, n_glass, n_water, n_air):
    nan = (np.nan, np.nan)
    r_in = r_out - thickness
    p = np.array([0.0, -offset])
    u = np.array([np.sin(theta), np.cos(theta)])
    h1 = _hit_sphere(p, u, r_in)
    u1 = _refract(u, h1 / r_in, n_air, n_glass)
    if u1 is None:
        return nan
    h2 = _hit_sphere(h1, u1, r_out)
    u2 = _refract(u1, h2 / r_out, n_glass, n_water)
    if u2 is None:
        return nan
    angle = np.arctan2(u2[0], u2[1])
    if abs(u2[0]) < 1e-12:
        return angle, 0.0
    return angle, h2[1] - h2[0] * u2[1] / u2[0]


def dome_virtual_image_mm(object_distance_mm, r_out_mm, thickness_mm,
                          n_glass, n_water, n_air=N_AIR):
    """Paraxial (small-angle) image of an object seen through a dome whose
    centre of curvature is at the camera's pupil.

    `object_distance_mm` is measured in the water from the dome's outer
    surface on the axis (np.inf for a far object). Two refracting surfaces
    in turn, each n1/s + n2/s' = (n2 - n1)/R with R positive because the
    centre of curvature lies ahead of the light. Returns the distance from
    the pupil (the dome centre) to the virtual image, in mm: the distance the
    lens has to focus at. Source: Hecht, Optics, 5th ed., eq. 5.8."""
    s = float(object_distance_mm)
    inv = 0.0 if np.isinf(s) else n_water / s
    s1 = n_glass / ((n_glass - n_water) / r_out_mm - inv)    # outer: water -> glass
    r_in = r_out_mm - thickness_mm
    s2 = n_air / ((n_air - n_glass) / r_in - n_glass / (thickness_mm - s1))   # inner: glass -> air
    return float(r_in - s2)
