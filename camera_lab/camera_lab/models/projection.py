"""Lens projection models: how an angle from the optical axis becomes a
distance from the image centre on the sensor.

For a ray at angle theta (rad) from the axis and a lens of focal length f (mm):

    rectilinear (pinhole)    r = f tan(theta)
    equidistant (f-theta)    r = f theta
    equisolid angle          r = 2 f sin(theta / 2)
    stereographic            r = 2 f tan(theta / 2)
    orthographic             r = f sin(theta)

Source: Kannala and Brandt (2006), "A generic camera model and calibration
method for conventional, wide-angle, and fish-eye lenses", IEEE PAMI 28(8),
and Ray, "Applied Photographic Optics". Every model has r = f theta for small
theta, so `f` is the same on-axis scale for all of them.
"""
import numpy as np

MODELS = ("rectilinear", "equidistant", "equisolid", "stereographic", "orthographic")


def _check(model):
    if model not in MODELS:
        raise ValueError(f"unknown projection '{model}'; choose from {MODELS}")


def image_radius_mm(theta_rad, focal_mm, model):
    """Distance from the image centre (mm) of a ray at `theta_rad`."""
    _check(model)
    t = np.asarray(theta_rad, float)
    f = focal_mm
    if model == "rectilinear":
        return f * np.tan(t)
    if model == "equidistant":
        return f * t
    if model == "equisolid":
        return 2 * f * np.sin(t / 2)
    if model == "stereographic":
        return 2 * f * np.tan(t / 2)
    return f * np.sin(t)


def ray_angle_rad(radius_mm, focal_mm, model):
    """Inverse of `image_radius_mm`: the ray angle (rad) seen at that radius.
    NaN where the model cannot reach that radius (orthographic beyond f,
    equisolid beyond 2 f)."""
    _check(model)
    r = np.asarray(radius_mm, float)
    f = focal_mm
    with np.errstate(invalid="ignore"):
        if model == "rectilinear":
            return np.arctan(r / f)
        if model == "equidistant":
            return r / f
        if model == "equisolid":
            return 2 * np.arcsin(r / (2 * f))
        if model == "stereographic":
            return 2 * np.arctan(r / (2 * f))
        return np.arcsin(r / f)


def radial_scale_mm_per_rad(theta_rad, focal_mm, model):
    """dr/dtheta: how many mm of sensor one radian of ray angle covers at
    this angle, along a radius. Divide by the pixel pitch for pixels per
    radian."""
    _check(model)
    t = np.asarray(theta_rad, float)
    f = focal_mm
    if model == "rectilinear":
        return f / np.cos(t) ** 2
    if model == "equidistant":
        return f + 0 * t
    if model == "equisolid":
        return f * np.cos(t / 2)
    if model == "stereographic":
        return f / np.cos(t / 2) ** 2
    return f * np.cos(t)


def full_fov_deg(extent_mm, focal_mm, model):
    """Full field of view (deg) across a sensor extent (mm), measured through
    the image centre: 2 * ray_angle(extent / 2)."""
    return np.degrees(2 * ray_angle_rad(np.asarray(extent_mm, float) / 2, focal_mm, model))


def sensor_fov_deg(width_mm, height_mm, focal_mm, model):
    """(horizontal, vertical, diagonal) full field of view in degrees."""
    diagonal = float(np.hypot(width_mm, height_mm))
    return tuple(float(full_fov_deg(e, focal_mm, model))
                 for e in (width_mm, height_mm, diagonal))


def focal_for_fov_mm(extent_mm, fov_deg, model):
    """The focal length (mm) that makes `extent_mm` of sensor span `fov_deg`
    of field of view in this projection."""
    _check(model)
    half = np.radians(fov_deg) / 2
    unit = float(image_radius_mm(half, 1.0, model))
    return extent_mm / 2 / unit
